"""F5, F6, F7, F8 — Loyers, paiements, reçus, relances WhatsApp, rapports."""
from __future__ import annotations

import json
import secrets
from datetime import date
from pathlib import Path

from fastapi import (APIRouter, Depends, File, Form, HTTPException, Request,
                     Response, UploadFile)
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit import device_id_from, log_action
from ..config import FILES_DIR, settings
from ..security import get_db
from ..logique import (LIBELLES_STATUT, MODES_PAIEMENT, calculer_notifications,
                       dashboard, echeances_detail, periode_courante, periode_libelle,
                       periode_precedente, rapport_proprietaire, regles_agence,
                       situation_caution)
from ..models import (Bail, Echeance, Immeuble, Locataire, ModeleMessage,
                      Paiement, Partage, Proprietaire, Recu, Relance, Unite, User)
from ..pdf import (generer_arrieres_pdf, generer_audit_pdf, generer_etat_loyers_pdf,
                   generer_rapport_pdf, generer_recap_locataire_pdf)
from ..security import current_user, normalize_phone, staff_or_responsable
from ..serializers import ser_paiement
from ..services import (annuler_paiement, contexte_agence, creer_recu_autre,
                        enregistrer_paiement)

router = APIRouter(prefix="/api", tags=["loyers"])


def _peut_ecrire(user: User) -> None:
    if user.role == "proprietaire" or not user.agence_id:
        raise HTTPException(403, "Compte propriétaire : lecture seule.")


# ---------------------------------------------------------------- Dashboard (F8)

@router.get("/dashboard")
async def tableau_de_bord(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    prop_id = user.proprietaire_id if user.role == "proprietaire" else None
    data = await dashboard(db, user.agence_id, prop_id)
    # activité récente : 8 derniers événements de l'agence
    from ..models import AuditLog
    logs = (await db.execute(
        select(AuditLog).where(AuditLog.agence_id == user.agence_id)
        .order_by(AuditLog.created_at.desc()).limit(8))).scalars().all()
    data["activite"] = [{
        "date": l.created_at.isoformat(), "user": l.user_nom, "action": l.action,
        "libelle": l.objet_libelle,
    } for l in logs]
    # alertes enregistrement de bail (§13.1 : délai configurable, défaut 30 jours)
    regles = await regles_agence(db, user.agence_id)
    baux = (await db.execute(select(Bail).where(Bail.agence_id == user.agence_id, Bail.statut == "actif"))).scalars().all()
    limite = date.fromordinal(date.today().toordinal() - regles.rappel_enregistrement_jours)
    a_enregistrer = []
    for b in baux:
        if b.enregistre_statut != "fait" and b.date_debut < limite:
            u = await db.get(Unite, b.unite_id)
            a_enregistrer.append({"bail_id": b.id, "unite": u.nom, "depuis": b.date_debut.isoformat()})
    data["baux_a_enregistrer"] = a_enregistrer
    return data


# ---------------------------------------------------------------- Notifications (cloche, v1.2)

@router.get("/notifications")
async def notifications(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    prop_id = user.proprietaire_id if user.role == "proprietaire" else None
    if prop_id:
        # compte propriétaire : limité à ses propres retards
        retards = await echeances_detail(db, user.agence_id, statut="en_retard", proprietaire_id=prop_id)
        out = []
        if retards:
            out.append({"cle": "retards", "gravite": "alerte", "nombre": len(retards),
                        "titre": "Loyers en retard",
                        "detail": f"{len(retards)} échéance(s) · {sum(e['reste'] for e in retards):,} FCFA".replace(",", " "),
                        "lien": "#/relances"})
        return {"notifications": out}
    return {"notifications": await calculer_notifications(db, user.agence_id)}


# ---------------------------------------------------------------- Exports PDF (v1.2)

def _pdf_response(chemin: str, nom: str) -> FileResponse:
    return FileResponse(chemin, media_type="application/pdf", filename=nom)


@router.get("/rapports/loyers-mois.pdf")
async def export_loyers_mois(periode: str | None = None, user: User = Depends(current_user),
                             db: AsyncSession = Depends(get_db)):
    periode = periode or periode_courante()
    prop_id = user.proprietaire_id if user.role == "proprietaire" else None
    ech = await echeances_detail(db, user.agence_id, periode=periode, proprietaire_id=prop_id)
    totaux = {"du": sum(e["montant_du"] for e in ech), "paye": sum(e["montant_paye"] for e in ech),
              "reste": sum(e["reste"] for e in ech)}
    agence = await contexte_agence(db, user.agence_id)
    chemin = str(FILES_DIR / "recus" / f"etat-loyers-{user.agence_id[:8]}-{periode}.pdf")
    generer_etat_loyers_pdf(chemin, periode_libelle=periode_libelle(periode), echeances=ech,
                            totaux=totaux, agence=agence)
    return _pdf_response(chemin, f"etat-loyers-{periode}.pdf")


@router.get("/rapports/arrieres.pdf")
async def export_arrieres(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    prop_id = user.proprietaire_id if user.role == "proprietaire" else None
    retards = await echeances_detail(db, user.agence_id, statut="en_retard", proprietaire_id=prop_id)
    retards.sort(key=lambda e: e["date_echeance"])
    agence = await contexte_agence(db, user.agence_id)
    chemin = str(FILES_DIR / "recus" / f"arrieres-{user.agence_id[:8]}.pdf")
    generer_arrieres_pdf(chemin, retards=retards, totaux=sum(e["reste"] for e in retards), agence=agence)
    return _pdf_response(chemin, "etat-arrieres.pdf")


@router.get("/locataires/{lid}/recap.pdf")
async def export_recap_locataire(lid: str, user: User = Depends(current_user),
                                 db: AsyncSession = Depends(get_db)):
    l = await db.get(Locataire, lid)
    if not l or l.agence_id != user.agence_id:
        raise HTTPException(404, "Locataire introuvable.")
    from ..models import Bail, Unite, Immeuble
    baux = (await db.execute(select(Bail).where(Bail.locataire_id == lid)
                             .order_by(Bail.date_debut.desc()))).scalars().all()
    out_baux, unite_ids = [], []
    for b in baux:
        u = await db.get(Unite, b.unite_id)
        imm = await db.get(Immeuble, u.immeuble_id)
        out_baux.append({"unite_nom": u.nom, "immeuble_nom": imm.nom,
                         "date_debut": b.date_debut.isoformat(),
                         "date_fin": b.date_fin.isoformat() if b.date_fin else None,
                         "loyer": b.loyer, "charges": b.charges, "caution": b.caution,
                         "statut": b.statut, "statut_libelle": {"actif": "en cours", "termine": "terminé"}.get(b.statut, b.statut)})
        unite_ids.append(b.id)
    pmts = (await db.execute(select(Paiement).where(Paiement.bail_id.in_(unite_ids))
                             .order_by(Paiement.date_paiement.desc()).limit(18))).scalars().all()
    out_pmts = [{"date": p.date_paiement.isoformat(), "type": p.type,
                 "type_libelle": {"loyer": "Loyer", "caution": "Caution", "frais_agence": "Frais d'agence",
                                  "annulation": "Annulation"}.get(p.type, p.type),
                 "mode": p.mode, "mode_libelle": MODES_PAIEMENT.get(p.mode, p.mode), "montant": p.montant}
                for p in pmts]
    agence = await contexte_agence(db, user.agence_id)
    chemin = str(FILES_DIR / "recus" / f"recap-{l.id[:8]}.pdf")
    generer_recap_locataire_pdf(chemin, loc={"nom": l.nom, "telephone": l.telephone,
                                             "telephone_whatsapp": l.telephone_whatsapp},
                                baux=out_baux, paiements=out_pmts, agence=agence)
    return _pdf_response(chemin, f"fiche-{l.nom.replace(' ', '-')}.pdf")


class RestitutionCautionIn(BaseModel):
    montant_retenu: int = Field(default=0, ge=0)
    motif_retenue: str = ""
    date_remboursement: str | None = None


@router.post("/baux/{bid}/caution/restituer")
async def restituer_caution(bid: str, body: RestitutionCautionIn, request: Request,
                            user: User = Depends(staff_or_responsable), db: AsyncSession = Depends(get_db)):
    """Restitution de la caution : trace la retenue justifiée + génère le reçu PDF (v1.2)."""
    _peut_ecrire(user)
    b = await db.get(Bail, bid)
    if not b or b.agence_id != user.agence_id:
        raise HTTPException(404, "Bail introuvable.")
    regles = await regles_agence(db, user.agence_id)
    sc = await situation_caution(db, b, regles)
    if sc["versee"] <= 0:
        raise HTTPException(422, "Aucune caution versée sur ce bail.")
    if body.montant_retenu > 0 and not (body.motif_retenue or "").strip():
        raise HTTPException(422, "Une retenue exige un motif justificatif (état des lieux, devis — décret 2023-382).")
    if body.montant_retenu > sc["versee"]:
        raise HTTPException(422, "La retenue ne peut pas dépasser la caution versée.")
    try:
        date_remb = date.fromisoformat(body.date_remboursement) if body.date_remboursement else date.today()
    except ValueError:
        raise HTTPException(422, "Date invalide (AAAA-MM-JJ).")
    b.caution_retenue = body.montant_retenu
    b.caution_retenue_motif = (body.motif_retenue or "").strip()[:500]
    b.caution_rembourse_le = date_remb
    await db.flush()
    recu = await creer_recu_autre(db, user, recu_type="restitution_caution", bail_id=bid,
                                  montant=sc["versee"] - body.montant_retenu,
                                  reference=(body.motif_retenue or "")[:200],
                                  device_id=device_id_from(request))
    await log_action(db, user, "caution.restituee", "bail", bid, "",
                     {"montant": sc["versee"] - body.montant_retenu, "retenue": body.montant_retenu},
                     device_id_from(request))
    await db.commit()
    return {"recu": _ser_recu(recu, user),
            "message": "Caution restituée — reçu généré."}


# ---------------------------------------------------------------- Échéances (F5)

@router.get("/echeances")
async def liste_echeances(periode: str | None = None, statut: str | None = None,
                          locataire_id: str | None = None, bail_id: str | None = None,
                          user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    prop_id = user.proprietaire_id if user.role == "proprietaire" else None
    ech = await echeances_detail(db, user.agence_id, periode=periode or periode_courante(),
                                 statut=statut, locataire_id=locataire_id, bail_id=bail_id,
                                 proprietaire_id=prop_id)
    return {"periode": periode or periode_courante(), "echeances": ech}


@router.get("/echeances/{eid}")
async def fiche_echeance(eid: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    from ..models import Echeance as E
    e = await db.get(E, eid)
    if not e or e.agence_id != user.agence_id:
        raise HTTPException(404, "Échéance introuvable.")
    if user.role == "proprietaire":
        b = await db.get(Bail, e.bail_id)
        u = await db.get(Unite, b.unite_id)
        imm = await db.get(Immeuble, u.immeuble_id)
        if imm.proprietaire_id != user.proprietaire_id:
            raise HTTPException(403, "Accès refusé.")
    tous = await echeances_detail(db, user.agence_id, bail_id=e.bail_id)
    for d in tous:
        if d["id"] == eid:
            return d
    raise HTTPException(404, "Échéance introuvable.")


# ---------------------------------------------------------------- Paiements (F5)

class PaiementIn(BaseModel):
    echeance_id: str
    montant: int = Field(gt=0)
    mode: str
    date_paiement: str | None = None  # défaut : aujourd'hui
    reference: str = ""
    client_uuid: str = Field(default="", max_length=64)


@router.post("/paiements")
async def creer_paiement(body: PaiementIn, request: Request,
                         user: User = Depends(staff_or_responsable), db: AsyncSession = Depends(get_db)):
    _peut_ecrire(user)
    paiement, recu, existant = await enregistrer_paiement(
        db, user,
        echeance_id=body.echeance_id, montant=body.montant, mode=body.mode,
        date_paiement=body.date_paiement or date.today().isoformat(),
        reference=body.reference, client_uuid=body.client_uuid,
        device_id=device_id_from(request),
    )
    return {
        "paiement": ser_paiement(paiement),
        "recu": _ser_recu(recu, user),
        "deja_existant": existant,
        "message": "Paiement enregistré." if not existant else "Ce paiement était déjà enregistré (synchronisation).",
    }


class AnnulationIn(BaseModel):
    motif: str = Field(min_length=3, max_length=500)


@router.post("/paiements/{pid}/annuler")
async def annuler(pid: str, body: AnnulationIn, request: Request,
                  user: User = Depends(staff_or_responsable), db: AsyncSession = Depends(get_db)):
    _peut_ecrire(user)
    paiement, ecriture = await annuler_paiement(db, user, pid, body.motif, device_id_from(request))
    return {"paiement": ser_paiement(paiement), "ecriture_annulation": ser_paiement(ecriture),
            "message": "Paiement annulé par écriture motivée. La quittance est marquée annulée."}


@router.get("/paiements/{pid}/preuve")
async def obtenir_preuve(pid: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    p = await db.get(Paiement, pid)
    if not p or p.agence_id != user.agence_id:
        raise HTTPException(404, "Paiement introuvable.")
    if not p.preuve_path or not Path(p.preuve_path).exists():
        raise HTTPException(404, "Aucune preuve jointe.")
    return FileResponse(p.preuve_path, filename=Path(p.preuve_path).name)


@router.post("/paiements/{pid}/preuve")
async def joindre_preuve(pid: str, request: Request, fichier: UploadFile = File(...),
                         user: User = Depends(staff_or_responsable), db: AsyncSession = Depends(get_db)):
    _peut_ecrire(user)
    p = await db.get(Paiement, pid)
    if not p or p.agence_id != user.agence_id:
        raise HTTPException(404, "Paiement introuvable.")
    if fichier.content_type not in ("image/png", "image/jpeg", "image/jpg", "image/webp", "application/pdf"):
        raise HTTPException(422, "Preuve : image ou PDF uniquement.")
    donnees = await fichier.read()
    if len(donnees) > 4 * 1024 * 1024:
        raise HTTPException(413, "Fichier trop lourd (max 4 Mo).")
    ext = {"image/png": "png", "image/jpeg": "jpg", "image/jpg": "jpg",
           "image/webp": "webp", "application/pdf": "pdf"}[fichier.content_type]
    chemin = FILES_DIR / "uploads" / f"preuve-{p.id[:8]}-{secrets.token_hex(4)}.{ext}"
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_bytes(donnees)
    p.preuve_path = str(chemin)
    await log_action(db, user, "paiement.preuve", "paiement", p.id, "", {"fichier": chemin.name},
                     device_id_from(request))
    await db.commit()
    return {"ok": True, "preuve_path": p.preuve_path}


@router.get("/paiements")
async def liste_paiements(echeance_id: str | None = None, bail_id: str | None = None,
                          locataire_id: str | None = None, limit: int = 100,
                          user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    query = select(Paiement).where(Paiement.agence_id == user.agence_id)
    if user.role == "proprietaire":
        query = query.join(Bail).join(Unite).join(Immeuble).where(
            Immeuble.proprietaire_id == user.proprietaire_id)
    if echeance_id:
        query = query.where(Paiement.echeance_id == echeance_id)
    if bail_id:
        query = query.where(Paiement.bail_id == bail_id)
    if locataire_id:
        if user.role != "proprietaire":
            query = query.join(Bail)
        query = query.where(Bail.locataire_id == locataire_id)
    pmts = (await db.execute(query.order_by(Paiement.created_at.desc()).limit(min(limit, 500)))).scalars().all()
    out = []
    for p in pmts:
        ech = await db.get(Echeance, p.echeance_id) if p.echeance_id else None
        b = await db.get(Bail, p.bail_id)
        loc = await db.get(Locataire, b.locataire_id) if b else None
        out.append({**ser_paiement(p),
                    "periode": ech.periode if ech else "",
                    "locataire_nom": loc.nom if loc else ""})
    return {"paiements": out}


# ---------------------------------------------------------------- Reçus (F6)

def _ser_recu(recu: Recu | None, user: User) -> dict | None:
    if not recu:
        return None
    return {
        "id": recu.id, "numero": recu.numero, "type": recu.type, "annule": recu.annule,
        "empreinte": recu.empreinte[:16],
        "lien_verif": f"{settings.base_url}/r/{recu.token}",
        "lien_pdf": f"/api/recus/{recu.id}/pdf",
        "contenu": json.loads(recu.contenu or "{}"),
    }


@router.get("/recus")
async def liste_recus(type: str | None = None, bail_id: str | None = None, limit: int = 100,
                      user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    query = select(Recu).where(Recu.agence_id == user.agence_id)
    if type:
        query = query.where(Recu.type == type)
    if bail_id:
        query = query.where(Recu.bail_id == bail_id)
    recus = (await db.execute(query.order_by(Recu.created_at.desc()).limit(min(limit, 500)))).scalars().all()
    return {"recus": [_ser_recu(r, user) for r in recus]}


@router.get("/recus/{rid}/pdf")
async def telecharger_recu(rid: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    r = await db.get(Recu, rid)
    if not r or r.agence_id != user.agence_id:
        raise HTTPException(404, "Reçu introuvable.")
    if not Path(r.fichier_path).exists():
        raise HTTPException(404, "Fichier PDF absent.")
    return FileResponse(r.fichier_path, media_type="application/pdf",
                        filename=f"{r.numero}.pdf")


class RecuAutreIn(BaseModel):
    type: str = Field(pattern="^(caution|frais_agence|decharge)$")
    bail_id: str
    montant: int = Field(default=0, ge=0)
    reference: str = ""


@router.post("/recus")
async def creer_recu(body: RecuAutreIn, request: Request,
                     user: User = Depends(staff_or_responsable), db: AsyncSession = Depends(get_db)):
    _peut_ecrire(user)
    regles = await regles_agence(db, user.agence_id)
    alertes = []
    if body.type == "caution":
        b = await db.get(Bail, body.bail_id)
        if b and regles.caution_max_mois and body.montant > b.loyer * regles.caution_max_mois:
            alertes.append(f"Caution supérieure à {regles.caution_max_mois} mois de loyer (règle paramétrée, "
                           "décret 2023-382 : max 2 mois, 1 mois à l'entrée puis 1/12e par mois).")
    if body.type == "frais_agence":
        b = await db.get(Bail, body.bail_id)
        if b and regles.frais_agence_max_mois and body.montant > b.loyer * regles.frais_agence_max_mois:
            alertes.append(f"Frais supérieurs à {regles.frais_agence_max_mois} mois de loyer "
                           "(décret 2023-382 : ½ mois max pour les baux ≤ 500 000 FCFA).")
    recu = await creer_recu_autre(db, user, recu_type=body.type, bail_id=body.bail_id,
                                  montant=body.montant, reference=body.reference,
                                  device_id=device_id_from(request))
    return {"recu": _ser_recu(recu, user), "alertes": alertes}


# ---------------------------------------------------------------- Relances (F7)

@router.get("/relances/retards")
async def liste_retards(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    prop_id = user.proprietaire_id if user.role == "proprietaire" else None
    ech = await echeances_detail(db, user.agence_id, statut="en_retard", proprietaire_id=prop_id)
    ech.sort(key=lambda e: e["date_echeance"])  # tri par ancienneté
    modele = (await db.execute(select(ModeleMessage).where(
        ModeleMessage.agence_id == user.agence_id, ModeleMessage.type == "relance"))).scalars().first()
    agence = await contexte_agence(db, user.agence_id)
    for e in ech:
        tel = normalize_phone(e["locataire_telephone"])
        e["whatsapp"] = tel.replace("+", "")
        e["message"] = (modele.contenu if modele else
                        "Bonjour {nom}, le loyer de {bien} pour {periode} ({reste} FCFA) est en retard.").format(
            nom=e["locataire_nom"], bien=e["bien_libelle"], periode=e["periode_libelle"],
            reste=f"{e['reste']:,}".replace(",", " "),
            echeance=(e.get("date_limite") or e["date_echeance"]),
            agence=agence["nom"])
    return {"retards": ech}


class RelanceIn(BaseModel):
    echeance_id: str
    message: str = Field(default="", max_length=2000)
    canal: str = "whatsapp"


@router.post("/relances")
async def enregistrer_relance(body: RelanceIn, request: Request,
                              user: User = Depends(staff_or_responsable), db: AsyncSession = Depends(get_db)):
    _peut_ecrire(user)
    from ..models import Echeance
    ech = await db.get(Echeance, body.echeance_id)
    if not ech or ech.agence_id != user.agence_id:
        raise HTTPException(404, "Échéance introuvable.")
    r = Relance(agence_id=user.agence_id, echeance_id=ech.id, user_id=user.id,
                canal=body.canal, message=body.message[:2000])
    db.add(r)
    await log_action(db, user, "relance.envoyee", "echeance", ech.id,
                     f"{ech.periode}", {"canal": body.canal}, device_id_from(request))
    await db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- Rapports (F8)

@router.get("/rapports/proprietaires")
async def rapports_proprietaires(periode: str | None = None, user: User = Depends(current_user),
                                 db: AsyncSession = Depends(get_db)):
    periode = periode or periode_courante()
    if user.role == "proprietaire":
        props = (await db.execute(select(Proprietaire).where(
            Proprietaire.id == user.proprietaire_id))).scalars().all()
    else:
        props = (await db.execute(select(Proprietaire).where(
            Proprietaire.agence_id == user.agence_id).order_by(Proprietaire.nom))).scalars().all()
    out = []
    for p in props:
        r = await rapport_proprietaire(db, user.agence_id, p.id, periode)
        out.append({"proprietaire_id": p.id, "nom": p.nom, "encaisse": r["encaisse"],
                    "a_reverser": r["a_reverser"], "commission": r["commission"],
                    "remuneration_gerant_pct": r["remuneration_gerant_pct"],
                    "remuneration_gerant": r["remuneration_gerant"],
                    "nb_en_retard": r["nb_en_retard"], "telephone": p.telephone})
    return {"periode": periode, "periode_libelle": periode_libelle(periode), "rapports": out}


@router.get("/rapports/proprietaire/{pid}")
async def rapport_detail(pid: str, periode: str | None = None, user: User = Depends(current_user),
                         db: AsyncSession = Depends(get_db)):
    if user.role == "proprietaire" and user.proprietaire_id != pid:
        raise HTTPException(403, "Accès refusé.")
    periode = periode or periode_courante()
    r = await rapport_proprietaire(db, user.agence_id, pid, periode)
    return r


@router.post("/rapports/proprietaire/{pid}/pdf")
async def generer_rapport(pid: str, request: Request, periode: str | None = None,
                          user: User = Depends(staff_or_responsable), db: AsyncSession = Depends(get_db)):
    _peut_ecrire(user)
    periode = periode or periode_courante()
    r = await rapport_proprietaire(db, user.agence_id, pid, periode)
    agence = await contexte_agence(db, user.agence_id)
    token = secrets.token_urlsafe(18)
    chemin = FILES_DIR / "recus" / f"rapport-{token}.pdf"
    url_verif = f"{settings.base_url}/p/{token}"
    generer_rapport_pdf(str(chemin), rapport=r, agence=agence, url_verif=url_verif)
    db.add(Partage(token=token, agence_id=user.agence_id, chemin=str(chemin),
                   filename=f"rapport-{r['periode']}-{r['proprietaire']['nom'].replace(' ', '-')}.pdf"))
    await log_action(db, user, "rapport.genere", "proprietaire", pid,
                     r["proprietaire"]["nom"], {"periode": periode}, device_id_from(request))
    await db.commit()
    return {"lien_pdf": f"/api/public/partage/{token}/pdf",
            "lien_public": f"{settings.base_url}/p/{token}",
            "rapport": r}
