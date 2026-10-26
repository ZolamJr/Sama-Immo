"""F10 — Synchronisation hors ligne.

Principes garantis :
- Identifiants UUID générés côté appareil => un rejeu ne crée jamais de doublon.
- Les paiements sont en ajout uniquement : jamais écrasés entre appareils.
- Pour les fiches modifiées sur deux appareils : la version la plus récente (updated_at) gagne,
  et chaque écrasement est consigné dans le journal d'audit.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit import device_id_from, log_action
from ..security import get_db
from ..logique import ensure_echeances_agence, regles_agence
from ..models import Bail, Echeance, Immeuble, Locataire, Proprietaire, Unite, User
from ..security import current_user, staff_or_responsable
from ..serializers import ser_bail, ser_locataire
from ..services import enregistrer_paiement, contexte_agence

router = APIRouter(prefix="/api/sync", tags=["sync"])

MAX_ACTIONS = 50


class Action(BaseModel):
    id: str = Field(max_length=64)
    type: str
    payload: dict


class SyncIn(BaseModel):
    actions: list[Action]
    device_id: str = ""


def _dt(v) -> datetime | None:
    """Horodatage client -> UTC naïf (comparable avec les colonnes SQLite)."""
    if not v:
        return None
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        if d.tzinfo:
            d = d.astimezone(timezone.utc).replace(tzinfo=None)
        return d
    except ValueError:
        return None


@router.post("")
async def synchroniser(body: SyncIn, request: Request,
                       user: User = Depends(staff_or_responsable), db: AsyncSession = Depends(get_db)):
    if user.role == "proprietaire":
        raise HTTPException(403, "Lecture seule.")
    if len(body.actions) > MAX_ACTIONS:
        raise HTTPException(422, f"Trop d'actions d'un coup (max {MAX_ACTIONS}).")
    device = (body.device_id or device_id_from(request))[:100]
    resultats = []
    for action in body.actions:
        try:
            resultats.append(await _traiter(db, user, action, device))
        except HTTPException as e:
            resultats.append({"id": action.id, "status": "error", "message": e.detail})
        except Exception as e:  # noqa: BLE001 — une action ne bloque jamais les autres
            resultats.append({"id": action.id, "status": "error",
                              "message": f"Erreur inattendue : {e}"})
    return {"resultats": resultats}


async def _traiter(db: AsyncSession, user: User, action: Action, device: str) -> dict:
    t = action.type
    p = action.payload
    agence_id = user.agence_id

    # ------------------------------------------------ paiements : ajout uniquement, idempotents
    if t == "paiement.create":
        ech = await db.get(Echeance, p.get("echeance_id", ""))
        if not ech or ech.agence_id != agence_id:
            raise HTTPException(404, "Échéance introuvable (peut-être obsolète).")
        paiement, recu, existant = await enregistrer_paiement(
            db, user,
            echeance_id=ech.id,
            montant=int(p.get("montant", 0)),
            mode=p.get("mode", "especes"),
            date_paiement=p.get("date_paiement") or date.today().isoformat(),
            reference=p.get("reference", ""),
            client_uuid=p.get("client_uuid") or p.get("id", ""),
            device_id=device,
        )
        from ..serializers import ser_paiement
        return {"id": action.id, "status": "duplicate" if existant else "applied",
                "entity": {"paiement": ser_paiement(paiement),
                           "recu": {"numero": recu.numero if recu else "",
                                    "token": recu.token if recu else "",
                                    "lien_verif": f"/r/{recu.token}" if recu else ""}}}

    # ------------------------------------------------ créations idempotentes (UUID côté appareil)
    if t == "locataire.create":
        existant = await db.get(Locataire, p.get("id", ""))
        if existant and existant.agence_id == agence_id:
            return {"id": action.id, "status": "duplicate", "entity": ser_locataire(existant)}
        from ..security import normalize_phone
        loc = Locataire(
            id=p.get("id") or None,
            agence_id=agence_id, nom=str(p.get("nom", ""))[:200].strip(),
            telephone=normalize_phone(str(p.get("telephone", ""))),
            telephone_whatsapp=normalize_phone(str(p.get("telephone_whatsapp") or p.get("telephone", ""))),
            notes=str(p.get("notes", ""))[:2000],
        )
        if not loc.nom:
            raise HTTPException(422, "Nom du locataire manquant.")
        db.add(loc)
        await log_action(db, user, "locataire.cree", "locataire", loc.id, loc.nom,
                         {"source": "sync", "device": device}, device)
        await db.commit()
        return {"id": action.id, "status": "applied", "entity": ser_locataire(loc)}

    if t == "bail.create":
        existant = await db.get(Bail, p.get("id", ""))
        if existant and existant.agence_id == agence_id:
            return {"id": action.id, "status": "duplicate", "entity": ser_bail(existant)}
        u = await db.get(Unite, p.get("unite_id", ""))
        if not u or u.agence_id != agence_id:
            raise HTTPException(404, "Unité introuvable.")
        if u.statut == "occupe":
            bail_actif = (await db.execute(select(Bail).where(
                Bail.unite_id == u.id, Bail.statut == "actif"))).scalars().first()
            if bail_actif and bail_actif.id != p.get("id"):
                raise HTTPException(409, "Cette unité est déjà louée (créée sur un autre appareil).")
        loc = await db.get(Locataire, p.get("locataire_id", ""))
        if not loc or loc.agence_id != agence_id:
            raise HTTPException(404, "Locataire introuvable.")
        try:
            debut = date.fromisoformat(str(p.get("date_debut")))
        except ValueError:
            raise HTTPException(422, "date_debut invalide.")
        b = Bail(
            id=p.get("id") or None,
            agence_id=agence_id, unite_id=u.id, locataire_id=loc.id, date_debut=debut,
            loyer=int(p.get("loyer", 0)), charges=int(p.get("charges", 0)),
            jour_echeance=int(p.get("jour_echeance", 5)), caution=int(p.get("caution", 0)),
            duree_type=p.get("duree_type", "triennale"),
        )
        db.add(b)
        await db.flush()  # UUID du bail avant l'historique de loyer
        u.statut = "occupe"
        from ..models import LoyerHistorique
        db.add(LoyerHistorique(agence_id=agence_id, bail_id=b.id, loyer=b.loyer,
                               date_effet=debut, motif="Bail initial (hors ligne)"))
        await log_action(db, user, "bail.cree", "bail", b.id, f"{loc.nom} — {u.nom}",
                         {"source": "sync", "loyer": b.loyer, "caution": b.caution}, device)
        await db.commit()
        await ensure_echeances_agence(db, agence_id)
        alertes = []
        regles = await regles_agence(db, agence_id)
        if regles.caution_max_mois and b.caution > b.loyer * regles.caution_max_mois:
            alertes.append(f"Caution supérieure à {regles.caution_max_mois} mois de loyer (règle paramétrée).")
        return {"id": action.id, "status": "applied", "entity": dict(ser_bail(b), alertes=alertes)}

    # ------------------------------------------------ mises à jour : la plus récente gagne (LWW)
    LWW = {
        "locataire.update": (Locataire, ser_locataire,
                             ("nom", "telephone", "telephone_whatsapp", "notes")),
        "bail.update": (Bail, ser_bail,
                        ("loyer", "charges", "jour_echeance", "caution", "duree_type", "enregistre_statut")),
        "unite.update": (Unite, None, ("nom", "loyer", "charges", "notes")),
        "immeuble.update": (Immeuble, None, ("nom", "adresse", "quartier")),
        "proprietaire.update": (Proprietaire, None, ("nom", "email", "mode_reversement", "commission_pct")),
    }
    if t in LWW:
        modele, ser, champs = LWW[t]
        obj = await db.get(modele, p.get("id", ""))
        nom_type = modele.__tablename__
        if not obj or obj.agence_id != agence_id:
            raise HTTPException(404, f"{nom_type} introuvable.")
        incoming_ts = _dt(p.get("updated_at"))
        if incoming_ts is None:
            raise HTTPException(422, "updated_at manquant.")
        serveur_ts = obj.updated_at  # déjà en UTC naïf
        if incoming_ts <= serveur_ts:
            # Le serveur a une version plus récente : conflit, le client doit reprendre la version serveur.
            entite = ser(obj) if ser else {"id": obj.id, "updated_at": obj.updated_at.isoformat(),
                                           **{c: getattr(obj, c) for c in champs}}
            return {"id": action.id, "status": "conflict", "entity": entite,
                    "message": "Une version plus récente existe : la version du serveur est conservée."}
        modifs = {}
        for c in champs:
            if c in p:
                ancien = getattr(obj, c)
                nouveau = p[c]
                if ancien != nouveau:
                    modifs[c] = {"ancien": str(ancien), "nouveau": str(nouveau)}
                    setattr(obj, c, nouveau)
        if t == "bail.update" and "loyer" in modifs:
            from ..models import LoyerHistorique
            db.add(LoyerHistorique(agence_id=agence_id, bail_id=obj.id, loyer=int(p["loyer"]),
                                   date_effet=date.today(),
                                   motif=str(p.get("motif_loyer") or "Modification (hors ligne)")[:300]))
        obj.updated_at = incoming_ts
        await log_action(db, user, f"{nom_type}.modifie", nom_type, obj.id, str(getattr(obj, 'nom', obj.id))[:100],
                         {"source": "sync", "modifs": modifs}, device)
        await db.commit()
        entite = ser(obj) if ser else {"id": obj.id, "updated_at": obj.updated_at.isoformat(),
                                       **{c: getattr(obj, c) for c in champs}}
        return {"id": action.id, "status": "applied", "entity": entite}

    raise HTTPException(422, f"Type d'action inconnu : {t}")
