"""F2, F3, F4 — Propriétaires, immeubles/unités, locataires, baux."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit import device_id_from, log_action
from ..security import get_db
from ..logique import (echeances_detail, ensure_echeances_agence, periode_courante,
                       regles_agence)
from ..models import (Bail, Echeance, Immeuble, Locataire, LoyerHistorique,
                      Proprietaire, Unite, User)
from ..security import current_user, normalize_phone, phone_valid, staff_or_responsable
from ..serializers import (ser_bail, ser_immeuble, ser_locataire, ser_proprietaire, ser_unite)

router = APIRouter(prefix="/api", tags=["fiches"])


def _check(db: AsyncSession, user: User):
    if user.role == "proprietaire" or not user.agence_id:
        raise HTTPException(403, "Compte propriétaire : lecture seule.")


# ---------------------------------------------------------------- Helpers de lecture enrichie

async def _immeuble_detail(db: AsyncSession, imm: Immeuble) -> dict:
    prop = await db.get(Proprietaire, imm.proprietaire_id)
    unites = (await db.execute(select(Unite).where(Unite.immeuble_id == imm.id)
                               .order_by(Unite.nom))).scalars().all()
    return {**ser_immeuble(imm), "proprietaire_nom": prop.nom if prop else "",
            "proprietaire_telephone": prop.telephone if prop else "",
            "unites": [dict(ser_unite(u), bail_actif=await _bail_actif(db, u.id)) for u in unites]}


async def _bail_actif(db: AsyncSession, unite_id: str):
    b = (await db.execute(select(Bail).where(Bail.unite_id == unite_id, Bail.statut == "actif"))).scalars().first()
    if not b:
        return None
    loc = await db.get(Locataire, b.locataire_id)
    unite = await db.get(Unite, b.unite_id)
    return {**ser_bail(b), "locataire_nom": loc.nom if loc else "", "unite_nom": unite.nom if unite else ""}


# ---------------------------------------------------------------- Propriétaires (F2)

class ProprietaireIn(BaseModel):
    nom: str = Field(min_length=2, max_length=200)
    telephone: str = ""
    email: str = ""
    mode_reversement: str = "mensuel"
    commission_pct: float = Field(default=0, ge=0, le=100)
    mandat_debut: date | None = None
    mandat_fin: date | None = None


class ProprietairePatch(ProprietaireIn):
    nom: str | None = None  # type: ignore[assignment]


@router.get("/proprietaires")
async def liste_proprietaires(q: str = "", user: User = Depends(current_user),
                              db: AsyncSession = Depends(get_db)):
    query = select(Proprietaire).where(Proprietaire.agence_id == user.agence_id)
    if user.role == "proprietaire":
        query = query.where(Proprietaire.id == user.proprietaire_id)
    if q:
        query = query.where(Proprietaire.nom.contains(q))
    props = (await db.execute(query.order_by(Proprietaire.nom))).scalars().all()
    # nombre d'immeubles pour affichage
    out = []
    for p in props:
        nb = len((await db.execute(select(Immeuble.id).where(Immeuble.proprietaire_id == p.id))).scalars().all())
        out.append({**ser_proprietaire(p), "nb_immeubles": nb})
    return {"proprietaires": out}


@router.post("/proprietaires")
async def creer_proprietaire(body: ProprietaireIn, request: Request,
                             user: User = Depends(staff_or_responsable), db: AsyncSession = Depends(get_db)):
    _check(db, user)
    tel = normalize_phone(body.telephone) if body.telephone else ""
    if body.mandat_debut and body.mandat_fin and body.mandat_fin < body.mandat_debut:
        raise HTTPException(422, "La date de fin du mandat doit suivre la date de début.")
    p = Proprietaire(agence_id=user.agence_id, nom=body.nom.strip(), telephone=tel,
                     email=body.email.strip(), mode_reversement=body.mode_reversement,
                     commission_pct=body.commission_pct,
                     mandat_debut=body.mandat_debut, mandat_fin=body.mandat_fin)
    db.add(p)
    await log_action(db, user, "proprietaire.cree", "proprietaire", p.id, p.nom,
                     {"commission_pct": body.commission_pct}, device_id_from(request))
    await db.commit()
    return {"proprietaire": ser_proprietaire(p),
            "invitation": f"Invitez {p.nom} à se connecter en lecture seule avec son numéro {tel or '(à compléter)'} "
                          f": il recevra ses rapports dès qu'il aura un compte."}


@router.get("/proprietaires/{pid}")
async def fiche_proprietaire(pid: str, user: User = Depends(current_user),
                             db: AsyncSession = Depends(get_db)):
    p = await db.get(Proprietaire, pid)
    if not p or p.agence_id != user.agence_id:
        raise HTTPException(404, "Propriétaire introuvable.")
    if user.role == "proprietaire" and user.proprietaire_id != pid:
        raise HTTPException(403, "Accès refusé.")
    immeubles = (await db.execute(select(Immeuble).where(Immeuble.proprietaire_id == pid))).scalars().all()
    return {"proprietaire": ser_proprietaire(p),
            "immeubles": [await _immeuble_detail(db, i) for i in immeubles]}


@router.patch("/proprietaires/{pid}")
async def modifier_proprietaire(pid: str, body: ProprietairePatch, request: Request,
                                user: User = Depends(staff_or_responsable), db: AsyncSession = Depends(get_db)):
    _check(db, user)
    p = await db.get(Proprietaire, pid)
    if not p or p.agence_id != user.agence_id:
        raise HTTPException(404, "Propriétaire introuvable.")
    modifs = {}
    for champ in ("nom", "email", "mode_reversement", "commission_pct",
                  "mandat_debut", "mandat_fin"):
        v = getattr(body, champ)
        if v is not None:
            setattr(p, champ, v)
            modifs[champ] = v.isoformat() if isinstance(v, date) else v
    if p.mandat_debut and p.mandat_fin and p.mandat_fin < p.mandat_debut:
        raise HTTPException(422, "La date de fin du mandat doit suivre la date de début.")
    if body.telephone is not None and body.telephone != "":
        p.telephone = normalize_phone(body.telephone)
        modifs["telephone"] = p.telephone
    await log_action(db, user, "proprietaire.modifie", "proprietaire", p.id, p.nom, modifs, device_id_from(request))
    await db.commit()
    return {"proprietaire": ser_proprietaire(p)}


@router.delete("/proprietaires/{pid}")
async def supprimer_proprietaire(pid: str, request: Request,
                                 user: User = Depends(staff_or_responsable), db: AsyncSession = Depends(get_db)):
    _check(db, user)
    p = await db.get(Proprietaire, pid)
    if not p or p.agence_id != user.agence_id:
        raise HTTPException(404, "Propriétaire introuvable.")
    nb = len((await db.execute(select(Immeuble.id).where(Immeuble.proprietaire_id == pid))).scalars().all())
    if nb:
        raise HTTPException(422, "Ce propriétaire possède encore des biens.")
    await log_action(db, user, "proprietaire.supprime", "proprietaire", p.id, p.nom)
    await db.delete(p)
    await db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- Immeubles & unités (F3)

class ImmeubleIn(BaseModel):
    nom: str = Field(min_length=2, max_length=200)
    proprietaire_id: str
    adresse: str = ""
    quartier: str = ""


class UniteIn(BaseModel):
    immeuble_id: str
    nom: str = Field(min_length=1, max_length=200)
    type: str = "chambre"
    loyer: int = Field(default=0, ge=0)
    charges: int = Field(default=0, ge=0)
    notes: str = ""


TYPES_UNITE = {"appartement", "maison", "chambre", "local", "bureau"}


@router.get("/immeubles")
async def liste_immeubles(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    query = select(Immeuble).where(Immeuble.agence_id == user.agence_id)
    if user.role == "proprietaire":
        query = query.join(Proprietaire).where(Proprietaire.id == user.proprietaire_id)
    imms = (await db.execute(query.order_by(Immeuble.nom))).scalars().all()
    return {"immeubles": [await _immeuble_detail(db, i) for i in imms]}


@router.get("/unites")
async def liste_unites(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    query = select(Unite).where(Unite.agence_id == user.agence_id)
    if user.role == "proprietaire":
        query = query.join(Immeuble).where(Immeuble.proprietaire_id == user.proprietaire_id)
    unites = (await db.execute(query.order_by(Unite.nom))).scalars().all()
    out = []
    for u in unites:
        imm = await db.get(Immeuble, u.immeuble_id)
        out.append({**ser_unite(u), "immeuble_nom": imm.nom if imm else "",
                    "bail_actif": await _bail_actif(db, u.id)})
    return {"unites": out}


@router.post("/immeubles")
async def creer_immeuble(body: ImmeubleIn, request: Request,
                         user: User = Depends(staff_or_responsable), db: AsyncSession = Depends(get_db)):
    _check(db, user)
    prop = await db.get(Proprietaire, body.proprietaire_id)
    if not prop or prop.agence_id != user.agence_id:
        raise HTTPException(404, "Propriétaire introuvable.")
    imm = Immeuble(agence_id=user.agence_id, proprietaire_id=prop.id, nom=body.nom.strip(),
                   adresse=body.adresse.strip(), quartier=body.quartier.strip())
    db.add(imm)
    await log_action(db, user, "immeuble.cree", "immeuble", imm.id, imm.nom, {}, device_id_from(request))
    await db.commit()
    return {"immeuble": await _immeuble_detail(db, imm)}


@router.patch("/immeubles/{iid}")
async def modifier_immeuble(iid: str, body: ImmeubleIn, request: Request,
                            user: User = Depends(staff_or_responsable), db: AsyncSession = Depends(get_db)):
    _check(db, user)
    imm = await db.get(Immeuble, iid)
    if not imm or imm.agence_id != user.agence_id:
        raise HTTPException(404, "Immeuble introuvable.")
    modifs = {}
    for champ in ("nom", "adresse", "quartier"):
        v = getattr(body, champ)
        if v is not None:
            setattr(imm, champ, v.strip())
            modifs[champ] = v
    await log_action(db, user, "immeuble.modifie", "immeuble", imm.id, imm.nom, modifs, device_id_from(request))
    await db.commit()
    return {"immeuble": await _immeuble_detail(db, imm)}


@router.delete("/immeubles/{iid}")
async def supprimer_immeuble(iid: str, request: Request,
                             user: User = Depends(staff_or_responsable), db: AsyncSession = Depends(get_db)):
    _check(db, user)
    imm = await db.get(Immeuble, iid)
    if not imm or imm.agence_id != user.agence_id:
        raise HTTPException(404, "Immeuble introuvable.")
    unites = (await db.execute(select(Unite).where(Unite.immeuble_id == iid))).scalars().all()
    for u in unites:
        if u.statut == "occupe":
            raise HTTPException(422, "Impossible de supprimer : des unités sont encore occupées (terminez les baux).")
    for u in unites:
        await db.delete(u)
    await log_action(db, user, "immeuble.supprime", "immeuble", imm.id, imm.nom)
    await db.delete(imm)
    await db.commit()
    return {"ok": True}


@router.post("/unites")
async def creer_unite(body: UniteIn, request: Request,
                      user: User = Depends(staff_or_responsable), db: AsyncSession = Depends(get_db)):
    _check(db, user)
    if body.type not in TYPES_UNITE:
        raise HTTPException(422, f"Type inconnu. Choix : {', '.join(sorted(TYPES_UNITE))}.")
    imm = await db.get(Immeuble, body.immeuble_id)
    if not imm or imm.agence_id != user.agence_id:
        raise HTTPException(404, "Immeuble introuvable.")
    u = Unite(agence_id=user.agence_id, immeuble_id=imm.id, nom=body.nom.strip(), type=body.type,
              loyer=body.loyer, charges=body.charges, notes=body.notes[:2000])
    db.add(u)
    await log_action(db, user, "unite.creee", "unite", u.id, f"{u.nom} ({imm.nom})",
                     {"loyer": u.loyer}, device_id_from(request))
    await db.commit()
    return {"unite": ser_unite(u)}


@router.patch("/unites/{uid}")
async def modifier_unite(uid: str, body: UniteIn, request: Request,
                         user: User = Depends(staff_or_responsable), db: AsyncSession = Depends(get_db)):
    _check(db, user)
    u = await db.get(Unite, uid)
    if not u or u.agence_id != user.agence_id:
        raise HTTPException(404, "Unité introuvable.")
    modifs = {}
    for champ in ("nom", "loyer", "charges", "notes"):
        v = getattr(body, champ)
        if v is not None:
            setattr(u, champ, v)
            modifs[champ] = v
    if body.type in TYPES_UNITE:
        u.type = body.type
        modifs["type"] = u.type
    await log_action(db, user, "unite.modifiee", "unite", u.id, u.nom, modifs, device_id_from(request))
    await db.commit()
    return {"unite": ser_unite(u)}


@router.delete("/unites/{uid}")
async def supprimer_unite(uid: str, request: Request,
                          user: User = Depends(staff_or_responsable), db: AsyncSession = Depends(get_db)):
    _check(db, user)
    u = await db.get(Unite, uid)
    if not u or u.agence_id != user.agence_id:
        raise HTTPException(404, "Unité introuvable.")
    if u.statut == "occupe":
        raise HTTPException(422, "Unité occupée : terminez d'abord le bail.")
    await log_action(db, user, "unite.supprimee", "unite", u.id, u.nom)
    await db.delete(u)
    await db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- Locataires (F4)

class LocataireIn(BaseModel):
    nom: str = Field(min_length=2, max_length=200)
    telephone: str = ""
    telephone_whatsapp: str = ""
    notes: str = ""


@router.get("/locataires")
async def liste_locataires(q: str = "", user: User = Depends(current_user),
                           db: AsyncSession = Depends(get_db)):
    query = select(Locataire).where(Locataire.agence_id == user.agence_id)
    if q:
        query = query.where(Locataire.nom.contains(q))
    locs = (await db.execute(query.order_by(Locataire.nom))).scalars().all()
    out = []
    for l in locs:
        baux = (await db.execute(select(Bail).where(Bail.locataire_id == l.id))).scalars().all()
        actifs = [b for b in baux if b.statut == "actif"]
        out.append({**ser_locataire(l), "nb_baux": len(baux), "nb_baux_actifs": len(actifs)})
    return {"locataires": out}


@router.get("/locataires/{lid}")
async def fiche_locataire(lid: str, user: User = Depends(current_user),
                          db: AsyncSession = Depends(get_db)):
    l = await db.get(Locataire, lid)
    if not l or l.agence_id != user.agence_id:
        raise HTTPException(404, "Locataire introuvable.")
    baux = (await db.execute(select(Bail).where(Bail.locataire_id == lid))).scalars().all()
    out_baux = []
    for b in baux:
        u = await db.get(Unite, b.unite_id)
        imm = await db.get(Immeuble, u.immeuble_id)
        ech = await echeances_detail(db, user.agence_id, bail_id=b.id)
        out_baux.append({**ser_bail(b), "unite_nom": u.nom, "immeuble_nom": imm.nom,
                         "echeances": ech})
    # historique paiements (tous baux confondus)
    from ..models import Paiement
    pmts = (await db.execute(select(Paiement).where(Paiement.bail_id.in_([b.id for b in baux]))
                             .order_by(Paiement.date_paiement.desc()))).scalars().all()
    return {**ser_locataire(l), "baux": out_baux,
            "paiements": [{
                "id": p.id, "date": p.date_paiement.isoformat(), "montant": p.montant, "mode": p.mode,
                "type": p.type, "annule": p.annule, "reference": p.reference,
            } for p in pmts]}


@router.post("/locataires")
async def creer_locataire(body: LocataireIn, request: Request,
                          user: User = Depends(staff_or_responsable), db: AsyncSession = Depends(get_db)):
    _check(db, user)
    l = Locataire(agence_id=user.agence_id, nom=body.nom.strip(),
                  telephone=normalize_phone(body.telephone),
                  telephone_whatsapp=normalize_phone(body.telephone_whatsapp or body.telephone),
                  notes=body.notes[:2000])
    db.add(l)
    await log_action(db, user, "locataire.cree", "locataire", l.id, l.nom, {}, device_id_from(request))
    await db.commit()
    return {"locataire": ser_locataire(l)}


@router.patch("/locataires/{lid}")
async def modifier_locataire(lid: str, body: LocataireIn, request: Request,
                             user: User = Depends(staff_or_responsable), db: AsyncSession = Depends(get_db)):
    _check(db, user)
    l = await db.get(Locataire, lid)
    if not l or l.agence_id != user.agence_id:
        raise HTTPException(404, "Locataire introuvable.")
    modifs = {}
    if body.nom is not None:
        l.nom = body.nom.strip()
        modifs["nom"] = l.nom
    if body.telephone is not None and body.telephone != "":
        l.telephone = normalize_phone(body.telephone)
        modifs["telephone"] = l.telephone
    if body.telephone_whatsapp is not None and body.telephone_whatsapp != "":
        l.telephone_whatsapp = normalize_phone(body.telephone_whatsapp)
        modifs["whatsapp"] = l.telephone_whatsapp
    if body.notes is not None:
        l.notes = body.notes[:2000]
        modifs["notes"] = True
    await log_action(db, user, "locataire.modifie", "locataire", l.id, l.nom, modifs, device_id_from(request))
    await db.commit()
    return {"locataire": ser_locataire(l)}


@router.delete("/locataires/{lid}")
async def supprimer_locataire(lid: str, request: Request,
                              user: User = Depends(staff_or_responsable), db: AsyncSession = Depends(get_db)):
    _check(db, user)
    l = await db.get(Locataire, lid)
    if not l or l.agence_id != user.agence_id:
        raise HTTPException(404, "Locataire introuvable.")
    nb = (await db.execute(select(Bail.id).where(Bail.locataire_id == lid))).scalars().all()
    if nb:
        raise HTTPException(422, "Ce locataire a des baux : les données financières doivent être conservées.")
    await log_action(db, user, "locataire.supprime", "locataire", l.id, l.nom)
    await db.delete(l)
    await db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- Baux (F4, F13)

class BailIn(BaseModel):
    unite_id: str
    locataire_id: str
    date_debut: date
    loyer: int = Field(ge=0)
    charges: int = Field(default=0, ge=0)
    jour_echeance: int = Field(default=5, ge=1, le=28)
    caution: int = Field(default=0, ge=0)
    duree_type: str = "triennale"


class BailPatch(BaseModel):
    loyer: int | None = Field(default=None, ge=0)
    charges: int | None = Field(default=None, ge=0)
    jour_echeance: int | None = Field(default=None, ge=1, le=28)
    caution: int | None = Field(default=None, ge=0)
    duree_type: str | None = None
    date_fin: date | None = None
    motif_loyer: str = ""
    enregistre_statut: str | None = None
    caution_rembourse_le: date | None = None
    caution_retenue: int | None = Field(default=None, ge=0)
    caution_retenue_motif: str | None = None


@router.post("/baux")
async def creer_bail(body: BailIn, request: Request,
                     user: User = Depends(staff_or_responsable), db: AsyncSession = Depends(get_db)):
    _check(db, user)
    u = await db.get(Unite, body.unite_id)
    if not u or u.agence_id != user.agence_id:
        raise HTTPException(404, "Unité introuvable.")
    l = await db.get(Locataire, body.locataire_id)
    if not l or l.agence_id != user.agence_id:
        raise HTTPException(404, "Locataire introuvable.")
    if u.statut == "occupe":
        raise HTTPException(422, "Cette unité est déjà louée (terminez le bail en cours).")
    regles = await regles_agence(db, user.agence_id)
    b = Bail(agence_id=user.agence_id, unite_id=u.id, locataire_id=l.id,
             date_debut=body.date_debut, loyer=body.loyer, charges=body.charges,
             jour_echeance=body.jour_echeance, caution=body.caution, duree_type=body.duree_type)
    db.add(b)
    await db.flush()  # attribue l'UUID du bail avant les lignes liées
    db.add(LoyerHistorique(agence_id=user.agence_id, bail_id=b.id, loyer=body.loyer,
                           date_effet=body.date_debut, motif="Bail initial"))
    u.statut = "occupe"
    alertes = []
    if regles.caution_max_mois and body.caution > body.loyer * regles.caution_max_mois:
        alertes.append(f"Caution ({body.caution:,} FCFA) supérieure à "
                       f"{regles.caution_max_mois} mois de loyer (règle paramétrée). "
                       f"Rappel décret 2023-382 : 2 mois max, 1 mois à l'entrée puis 1/12e par mois.")
    await log_action(db, user, "bail.cree", "bail", b.id,
                     f"{l.nom} — {u.nom}", {"loyer": body.loyer, "caution": body.caution},
                     device_id_from(request))
    await db.commit()
    await ensure_echeances_agence(db, user.agence_id)
    return {"bail": ser_bail(b), "alertes": alertes}


@router.get("/baux")
async def liste_baux(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    query = select(Bail).where(Bail.agence_id == user.agence_id)
    if user.role == "proprietaire":
        query = query.join(Unite).join(Immeuble).where(Immeuble.proprietaire_id == user.proprietaire_id)
    baux = (await db.execute(query.order_by(Bail.date_debut.desc()))).scalars().all()
    out = []
    for b in baux:
        u = await db.get(Unite, b.unite_id)
        imm = await db.get(Immeuble, u.immeuble_id)
        l = await db.get(Locataire, b.locataire_id)
        out.append({**ser_bail(b), "unite_nom": u.nom, "immeuble_nom": imm.nom,
                    "locataire_nom": l.nom, "locataire_telephone": l.telephone_whatsapp or l.telephone})
    return {"baux": out}


@router.get("/baux/{bid}")
async def fiche_bail(bid: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    b = await db.get(Bail, bid)
    if not b or b.agence_id != user.agence_id:
        raise HTTPException(404, "Bail introuvable.")
    if user.role == "proprietaire":
        u = await db.get(Unite, b.unite_id)
        imm = await db.get(Immeuble, u.immeuble_id)
        if imm.proprietaire_id != user.proprietaire_id:
            raise HTTPException(403, "Accès refusé.")
    u = await db.get(Unite, b.unite_id)
    imm = await db.get(Immeuble, u.immeuble_id)
    l = await db.get(Locataire, b.locataire_id)
    hist = (await db.execute(select(LoyerHistorique).where(LoyerHistorique.bail_id == bid)
                             .order_by(LoyerHistorique.date_effet))).scalars().all()
    ech = await echeances_detail(db, user.agence_id, bail_id=bid)
    from ..logique import situation_caution
    regles = await regles_agence(db, user.agence_id)
    caution = await situation_caution(db, b, regles)
    return {**ser_bail(b), "caution_detail": caution,
            "unite_nom": u.nom, "immeuble_nom": imm.nom, "immeuble_id": imm.id,
            "locataire_nom": l.nom, "locataire_telephone": l.telephone_whatsapp or l.telephone,
            "historique_loyer": [{"loyer": h.loyer, "date_effet": h.date_effet.isoformat(),
                                  "motif": h.motif} for h in hist],
            "echeances": ech}


@router.patch("/baux/{bid}")
async def modifier_bail(bid: str, body: BailPatch, request: Request,
                        user: User = Depends(staff_or_responsable), db: AsyncSession = Depends(get_db)):
    _check(db, user)
    b = await db.get(Bail, bid)
    if not b or b.agence_id != user.agence_id:
        raise HTTPException(404, "Bail introuvable.")
    modifs = {}
    nouveau_du = None
    if body.loyer is not None and body.loyer != b.loyer:
        motif = (body.motif_loyer or "Modification").strip()[:300]
        db.add(LoyerHistorique(agence_id=user.agence_id, bail_id=b.id, loyer=body.loyer,
                               date_effet=date.today(), motif=motif))
        modifs["loyer"] = {"ancien": b.loyer, "nouveau": body.loyer, "motif": motif}
        b.loyer = body.loyer
        nouveau_du = b.loyer + (body.charges if body.charges is not None else b.charges)
    if body.charges is not None and body.charges != b.charges:
        b.charges = body.charges
        modifs["charges"] = body.charges
        nouveau_du = b.loyer + b.charges
    if nouveau_du is not None:
        # Seules les échéances à venir (période courante incluse) prennent le nouveau montant ;
        # les échéances passées conservent le montant historisé.
        echs = (await db.execute(select(Echeance).where(Echeance.bail_id == b.id))).scalars().all()
        pc = periode_courante()
        for e in echs:
            if e.periode >= pc:
                e.montant_du = nouveau_du
    for champ in ("jour_echeance", "caution", "duree_type", "enregistre_statut"):
        v = getattr(body, champ)
        if v is not None:
            setattr(b, champ, v)
            modifs[champ] = v
    if body.enregistre_statut == "fait":
        b.enregistre_date = date.today()
        modifs["enregistre_date"] = b.enregistre_date.isoformat()
    if body.date_fin is not None:
        b.date_fin = body.date_fin
        modifs["date_fin"] = body.date_fin.isoformat()
    if body.caution_rembourse_le is not None:
        b.caution_rembourse_le = body.caution_rembourse_le
        modifs["caution_rembourse_le"] = body.caution_rembourse_le.isoformat()
    if body.caution_retenue is not None:
        if body.caution_retenue > 0 and not (body.caution_retenue_motif or "").strip():
            raise HTTPException(422, "Une retenue sur caution exige un motif justificatif (décret 2023-382).")
        b.caution_retenue = body.caution_retenue
        modifs["caution_retenue"] = body.caution_retenue
    if body.caution_retenue_motif is not None:
        b.caution_retenue_motif = body.caution_retenue_motif[:500]
        modifs["caution_retenue_motif"] = True
    await log_action(db, user, "bail.modifie", "bail", b.id, b.id[:8], modifs, device_id_from(request))
    await db.commit()
    return {"bail": ser_bail(b)}


class FinBailIn(BaseModel):
    motif: str = ""


@router.post("/baux/{bid}/terminer")
async def terminer_bail(bid: str, body: FinBailIn, request: Request,
                        user: User = Depends(staff_or_responsable), db: AsyncSession = Depends(get_db)):
    _check(db, user)
    b = await db.get(Bail, bid)
    if not b or b.agence_id != user.agence_id:
        raise HTTPException(404, "Bail introuvable.")
    if b.statut != "actif":
        raise HTTPException(422, "Ce bail est déjà terminé.")
    b.statut = "termine"
    b.date_fin = date.today()
    b.motif_fin = body.motif[:500]
    u = await db.get(Unite, b.unite_id)
    u.statut = "libre"
    await log_action(db, user, "bail.termine", "bail", b.id,
                     f"{u.nom}", {"motif": body.motif}, device_id_from(request))
    await db.commit()
    return {"bail": ser_bail(b), "unite": ser_unite(u),
            "suggestion": "Générez la décharge de remise de clés et le reçu de restitution de caution si besoin."}
