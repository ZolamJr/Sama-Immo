"""F9, F11, F13 — Paramètres agence, utilisateurs (rôles), règles locales, modèles, export."""
from __future__ import annotations

import csv
import io
import json
import uuid as uuid_mod
from datetime import date, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit import device_id_from, log_action
from ..config import FILES_DIR, settings
from ..security import get_db
from ..logique import echeances_detail
from ..pdf import generer_audit_pdf
from ..services import contexte_agence
from ..models import (Agence, AuditLog, Bail, Immeuble, Locataire, ModeleMessage,
                      Paiement, Proprietaire, Regles, Unite, User)
from ..security import current_user, normalize_phone, phone_valid, responsable_only
from ..serializers import ser_user

router = APIRouter(prefix="/api", tags=["parametres"])

IMAGES = {"image/png", "image/jpeg", "image/webp", "image/jpg"}
TAILLE_MAX = 4 * 1024 * 1024  # 4 Mo


class AgenceIn(BaseModel):
    nom: str | None = Field(default=None, max_length=200)
    telephone: str | None = Field(default=None, max_length=30)
    email: str | None = Field(default=None, max_length=200)
    adresse: str | None = Field(default=None, max_length=300)


class UserIn(BaseModel):
    telephone: str = Field(min_length=6, max_length=25)
    nom: str = Field(min_length=1, max_length=200)
    role: str = "employe"


class UserPatch(BaseModel):
    nom: str | None = Field(default=None, max_length=200)
    role: str | None = None
    actif: bool | None = None


class ReglesIn(BaseModel):
    caution_max_mois: int | None = Field(default=None, ge=0, le=12)
    caution_etalee_mois: int | None = Field(default=None, ge=1, le=36)
    terme_paiement: str | None = None
    jour_limite_paiement: int | None = Field(default=None, ge=1, le=28)
    frais_agence_max_mois: float | None = Field(default=None, ge=0, le=6)
    revision_periodicite_mois: int | None = Field(default=None, ge=1, le=120)
    rappel_enregistrement_jours: int | None = Field(default=None, ge=1, le=365)


class ModeleIn(BaseModel):
    type: str = Field(pattern="^(relance|quittance|rapport)$")
    contenu: str = Field(min_length=5, max_length=2000)


async def get_agence(db: AsyncSession, user: User) -> Agence:
    if not user.agence_id or user.role == "proprietaire":
        raise HTTPException(403, "Compte propriétaire : lecture seule.")
    a = await db.get(Agence, user.agence_id)
    if not a:
        raise HTTPException(404, "Agence introuvable.")
    return a


async def get_regles(db: AsyncSession, agence_id: str) -> Regles:
    r = (await db.execute(select(Regles).where(Regles.agence_id == agence_id))).scalars().first()
    if not r:
        r = Regles(agence_id=agence_id)
        db.add(r)
        await db.commit()
    return r


def _ser_agence(a: Agence) -> dict:
    return {"id": a.id, "nom": a.nom, "telephone": a.telephone, "email": a.email,
            "adresse": a.adresse, "logo_path": a.logo_path, "tampon_path": a.tampon_path,
            "signature_path": a.signature_path}


def _ser_regles(r: Regles) -> dict:
    return {"caution_max_mois": r.caution_max_mois, "caution_etalee_mois": r.caution_etalee_mois,
            "terme_paiement": r.terme_paiement,
            "jour_limite_paiement": r.jour_limite_paiement if r.jour_limite_paiement is not None else 10,
            "frais_agence_max_mois": r.frais_agence_max_mois,
            "revision_periodicite_mois": r.revision_periodicite_mois,
            "rappel_enregistrement_jours": r.rappel_enregistrement_jours}


@router.get("/agence")
async def lire_agence(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    if user.role == "proprietaire":
        a = await db.get(Agence, user.agence_id)
        return {"agence": _ser_agence(a), "regles": None, "modeles": [], "lecture_seule": True}
    a = await get_agence(db, user)
    regles = await get_regles(db, a.id)
    modeles = (await db.execute(select(ModeleMessage).where(ModeleMessage.agence_id == a.id))).scalars().all()
    return {"agence": _ser_agence(a), "regles": _ser_regles(regles),
            "modeles": [{"id": m.id, "type": m.type, "contenu": m.contenu} for m in modeles],
            "lecture_seule": False}


@router.patch("/agence")
async def modifier_agence(body: AgenceIn, request: Request, user: User = Depends(current_user),
                          db: AsyncSession = Depends(get_db)):
    a = await get_agence(db, user)
    modifs = {}
    for champ in ("nom", "telephone", "email", "adresse"):
        v = getattr(body, champ)
        if v is not None:
            setattr(a, champ, v.strip())
            modifs[champ] = v
    await log_action(db, user, "agence.modifiee", "agence", a.id, a.nom, modifs, device_id_from(request))
    await db.commit()
    return {"agence": _ser_agence(a)}


async def _sauver_image(fichier: UploadFile, dossier: str) -> str:
    if fichier.content_type not in IMAGES:
        raise HTTPException(422, "Format d'image non supporté (PNG, JPG ou WebP).")
    donnees = await fichier.read()
    if len(donnees) > TAILLE_MAX:
        raise HTTPException(413, "Image trop lourde (max 4 Mo).")
    ext = {"image/png": "png", "image/jpeg": "jpg", "image/jpg": "jpg", "image/webp": "webp"}[fichier.content_type]
    chemin = FILES_DIR / "agence" / f"{dossier}-{uuid_mod.uuid4().hex}.{ext}"
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_bytes(donnees)
    return str(chemin)


@router.post("/agence/logo")
async def uploader_logo(fichier: UploadFile = File(...), user: User = Depends(current_user),
                        db: AsyncSession = Depends(get_db)):
    a = await get_agence(db, user)
    a.logo_path = await _sauver_image(fichier, "logo")
    await log_action(db, user, "agence.logo", "agence", a.id, a.nom)
    await db.commit()
    return {"ok": True, "logo_path": a.logo_path}


@router.post("/agence/tampon")
async def uploader_tampon(fichier: UploadFile = File(...), user: User = Depends(current_user),
                          db: AsyncSession = Depends(get_db)):
    a = await get_agence(db, user)
    a.tampon_path = await _sauver_image(fichier, "tampon")
    await log_action(db, user, "agence.tampon", "agence", a.id, a.nom)
    await db.commit()
    return {"ok": True, "tampon_path": a.tampon_path}


@router.post("/agence/signature")
async def uploader_signature(fichier: UploadFile = File(...), user: User = Depends(current_user),
                             db: AsyncSession = Depends(get_db)):
    a = await get_agence(db, user)
    a.signature_path = await _sauver_image(fichier, "signature")
    await log_action(db, user, "agence.signature", "agence", a.id, a.nom)
    await db.commit()
    return {"ok": True, "signature_path": a.signature_path}


@router.get("/agence/image/{kind}")
async def image_agence(kind: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    a = await get_agence(db, user) if user.role != "proprietaire" else await db.get(Agence, user.agence_id)
    chemin = {"logo": a.logo_path, "tampon": a.tampon_path, "signature": a.signature_path}.get(kind)
    if not chemin or not Path(chemin).exists():
        raise HTTPException(404, "Image absente.")
    return FileResponse(chemin)


@router.delete("/agence/image/{kind}")
async def retirer_image_agence(kind: str, request: Request, user: User = Depends(current_user),
                               db: AsyncSession = Depends(get_db)):
    if kind not in ("logo", "tampon", "signature"):
        raise HTTPException(422, "Type d'image inconnu.")
    a = await get_agence(db, user)
    setattr(a, f"{kind}_path", None)
    await log_action(db, user, f"agence.{kind}", "agence", a.id, a.nom, {"retire": True},
                     device_id_from(request))
    await db.commit()
    return {"ok": True}


# ------------------------------------------------------------- Utilisateurs (F11)

@router.get("/users")
async def liste_users(user: User = Depends(responsable_only), db: AsyncSession = Depends(get_db)):
    users = (await db.execute(select(User).where(User.agence_id == user.agence_id))).scalars().all()
    return {"users": [ser_user(u) for u in users]}


@router.post("/users")
async def ajouter_user(body: UserIn, request: Request,
                       user: User = Depends(responsable_only), db: AsyncSession = Depends(get_db)):
    if user.role != "responsable":
        raise HTTPException(403, "Seul le responsable peut ajouter des employés.")
    tel = normalize_phone(body.telephone)
    if not phone_valid(tel):
        raise HTTPException(422, "Numéro de téléphone invalide.")
    if body.role not in ("employe", "responsable"):
        raise HTTPException(422, "Rôle invalide.")
    existe = (await db.execute(select(User).where(User.telephone == tel))).scalars().first()
    if existe:
        raise HTTPException(409, "Ce numéro a déjà un compte.")
    u = User(telephone=tel, nom=body.nom.strip(), role=body.role, agence_id=user.agence_id)
    db.add(u)
    await log_action(db, user, "user.ajoute", "user", u.id, u.nom,
                     {"role": body.role, "telephone": tel}, device_id_from(request))
    await db.commit()
    return {"user": ser_user(u), "message": "L'employé se connectera avec ce numéro (code SMS)."}


@router.patch("/users/{user_id}")
async def modifier_user(user_id: str, body: UserPatch, request: Request,
                        user: User = Depends(responsable_only), db: AsyncSession = Depends(get_db)):
    cible = await db.get(User, user_id)
    if not cible or cible.agence_id != user.agence_id:
        raise HTTPException(404, "Utilisateur introuvable.")
    if cible.id == user.id and body.actif is False:
        raise HTTPException(422, "Impossible de se désactiver soi-même.")
    modifs = {}
    if body.nom is not None:
        cible.nom = body.nom.strip()
        modifs["nom"] = cible.nom
    if body.role is not None and body.role in ("employe", "responsable"):
        cible.role = body.role
        modifs["role"] = body.role
    if body.actif is not None:
        cible.actif = body.actif
        modifs["actif"] = body.actif
    await log_action(db, user, "user.modifie", "user", cible.id, cible.nom, modifs, device_id_from(request))
    await db.commit()
    return {"user": ser_user(cible)}


# ------------------------------------------------------------- Règles locales (F13)

@router.get("/regles")
async def lire_regles(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    if not user.agence_id:
        raise HTTPException(403, "Lecture seule.")
    r = await get_regles(db, user.agence_id)
    return {"regles": _ser_regles(r)}


@router.patch("/regles")
async def modifier_regles(body: ReglesIn, request: Request,
                          user: User = Depends(responsable_only), db: AsyncSession = Depends(get_db)):
    r = await get_regles(db, user.agence_id)
    modifs = {}
    for champ, v in body.model_dump(exclude_none=True).items():
        if champ == "terme_paiement" and v not in ("fin", "debut"):
            raise HTTPException(422, "terme_paiement doit valoir 'fin' ou 'debut'.")
        setattr(r, champ, v)
        modifs[champ] = v
    await log_action(db, user, "regles.modifiees", "regles", r.id, "", modifs, device_id_from(request))
    await db.commit()
    return {"regles": _ser_regles(r)}


# ------------------------------------------------------------- Modèles de messages (F9)

@router.get("/modeles")
async def lire_modeles(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    if not user.agence_id:
        raise HTTPException(403, "Lecture seule.")
    ms = (await db.execute(select(ModeleMessage).where(ModeleMessage.agence_id == user.agence_id))).scalars().all()
    return {"modeles": [{"id": m.id, "type": m.type, "contenu": m.contenu} for m in ms]}


@router.put("/modeles")
async def modifier_modele(body: ModeleIn, request: Request,
                          user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    if user.role == "proprietaire":
        raise HTTPException(403, "Lecture seule.")
    m = (await db.execute(select(ModeleMessage).where(
        ModeleMessage.agence_id == user.agence_id, ModeleMessage.type == body.type))).scalars().first()
    if m:
        m.contenu = body.contenu
    else:
        m = ModeleMessage(agence_id=user.agence_id, type=body.type, contenu=body.contenu)
        db.add(m)
    await log_action(db, user, "modele.modifie", "modele", m.id, body.type, {}, device_id_from(request))
    await db.commit()
    return {"modele": {"id": m.id, "type": m.type, "contenu": m.contenu}}


# ------------------------------------------------------------- Journal d'audit (F11)

@router.get("/audit")
async def journal_audit(request: Request, limit: int = 100, offset: int = 0, q: str = "",
                        user: User = Depends(responsable_only), db: AsyncSession = Depends(get_db)):
    query = select(AuditLog).where(AuditLog.agence_id == user.agence_id)
    if q:
        query = query.where(AuditLog.action.contains(q) | AuditLog.objet_libelle.contains(q)
                            | AuditLog.user_nom.contains(q))
    total = len((await db.execute(query)).scalars().all())
    logs = (await db.execute(query.order_by(AuditLog.created_at.desc()).limit(min(limit, 500)).offset(max(offset, 0)))).scalars().all()
    return {"total": total, "logs": [{
        "id": l.id, "date": l.created_at.isoformat(), "user": l.user_nom, "action": l.action,
        "objet_type": l.objet_type, "objet_id": l.objet_id, "objet_libelle": l.objet_libelle,
        "details": json.loads(l.details or "{}"), "device_id": l.device_id,
    } for l in logs]}


# ------------------------------------------------------------- Export PDF du journal (v1.2)

@router.get("/audit/export.pdf")
async def export_audit_pdf(limit: int = 150, q: str = "", user: User = Depends(responsable_only),
                           db: AsyncSession = Depends(get_db)):
    query = select(AuditLog).where(AuditLog.agence_id == user.agence_id)
    if q:
        query = query.where(AuditLog.action.contains(q) | AuditLog.objet_libelle.contains(q)
                            | AuditLog.user_nom.contains(q))
    logs = (await db.execute(query.order_by(AuditLog.created_at.desc())
                             .limit(min(limit, 500)))).scalars().all()
    agence = await contexte_agence(db, user.agence_id)
    chemin = str(FILES_DIR / "recus" / f"audit-{user.agence_id[:8]}.pdf")
    generer_audit_pdf(chemin, logs=[{
        "date": l.created_at.isoformat(), "user": l.user_nom, "action": l.action,
        "objet_libelle": l.objet_libelle} for l in logs], agence=agence)
    return FileResponse(chemin, media_type="application/pdf", filename="journal-activite.pdf")


# ------------------------------------------------------------- Export CSV (F9)

TABLES_EXPORT = {"proprietaires", "immeubles", "unites", "locataires", "baux", "echeances", "paiements"}


@router.get("/export/{table}.csv")
async def export_csv(table: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    if table not in TABLES_EXPORT:
        raise HTTPException(404, "Table inconnue.")
    if not user.agence_id:
        raise HTTPException(403, "Lecture seule.")
    agence_id = user.agence_id
    lignes: list[dict] = []

    if table == "proprietaires":
        objs = (await db.execute(select(Proprietaire).where(Proprietaire.agence_id == agence_id))).scalars().all()
        lignes = [{"id": o.id, "nom": o.nom, "telephone": o.telephone, "email": o.email,
                   "mode_reversement": o.mode_reversement, "commission_pct": o.commission_pct} for o in objs]
    elif table == "immeubles":
        objs = (await db.execute(select(Immeuble).where(Immeuble.agence_id == agence_id))).scalars().all()
        lignes = [{"id": o.id, "nom": o.nom, "quartier": o.quartier, "adresse": o.adresse,
                   "proprietaire_id": o.proprietaire_id} for o in objs]
    elif table == "unites":
        objs = (await db.execute(select(Unite).where(Unite.agence_id == agence_id))).scalars().all()
        lignes = [{"id": o.id, "nom": o.nom, "type": o.type, "loyer": o.loyer, "charges": o.charges,
                   "statut": o.statut, "immeuble_id": o.immeuble_id} for o in objs]
    elif table == "locataires":
        objs = (await db.execute(select(Locataire).where(Locataire.agence_id == agence_id))).scalars().all()
        lignes = [{"id": o.id, "nom": o.nom, "telephone": o.telephone,
                   "whatsapp": o.telephone_whatsapp} for o in objs]
    elif table == "baux":
        objs = (await db.execute(select(Bail).where(Bail.agence_id == agence_id))).scalars().all()
        lignes = [{"id": o.id, "unite_id": o.unite_id, "locataire_id": o.locataire_id,
                   "date_debut": o.date_debut, "date_fin": o.date_fin, "loyer": o.loyer,
                   "charges": o.charges, "caution": o.caution, "statut": o.statut} for o in objs]
    elif table == "echeances":
        lignes = await echeances_detail(db, agence_id)
    elif table == "paiements":
        objs = (await db.execute(select(Paiement).where(Paiement.agence_id == agence_id)
                                 .order_by(Paiement.date_paiement))).scalars().all()
        lignes = [{"id": o.id, "date": o.date_paiement, "type": o.type, "montant": o.montant,
                   "mode": o.mode, "reference": o.reference, "echeance_id": o.echeance_id,
                   "bail_id": o.bail_id, "annule": o.annule, "motif_annulation": o.motif_annulation,
                   "saisi_par": o.saisi_par} for o in objs]

    entetes = sorted({k for l in lignes for k in l}) if lignes else []
    buf = io.StringIO()
    buf.write("\ufeff")  # BOM pour Excel
    writer = csv.DictWriter(buf, fieldnames=entetes, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(lignes)
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f"attachment; filename={table}.csv"})
