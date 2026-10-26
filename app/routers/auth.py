"""F1 — Compte et authentification : téléphone + code OTP, pas de mot de passe."""
from __future__ import annotations


from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit import log_action
from ..config import settings
from ..security import get_db
from ..models import Agence, ModeleMessage, Proprietaire, Regles, User
from ..notify import send_otp_sms
from ..security import (check_otp, create_otp, current_user, decode_token,
                        make_inscription_token, make_token, normalize_phone, phone_valid,
                        utc_naif)
from ..serializers import ser_agence, ser_user

router = APIRouter(prefix="/api/auth", tags=["auth"])

MODELE_RELANCE_DEFAUT = (
    "Bonjour {nom}, nous vous rappelons que le loyer de {bien} pour {periode} "
    "d'un montant de {reste} FCFA est en attente depuis le {echeance}. "
    "Merci de régulariser (Wave, Orange Money ou espèces). Cordialement, {agence}."
)

MODELE_QUITTANCE_DEFAUT = (
    "Bonjour {nom}, voici votre quittance de loyer n° {numero} pour {periode} "
    "({montant} FCFA) : {lien}. Merci de votre confiance, {agence}."
)


class TelIn(BaseModel):
    telephone: str = Field(min_length=6, max_length=25)


class VerifyIn(BaseModel):
    telephone: str = Field(min_length=6, max_length=25)
    code: str = Field(min_length=4, max_length=8)


class InscriptionIn(BaseModel):
    jeton: str
    nom_agence: str = Field(min_length=2, max_length=200)
    nom: str = Field(min_length=2, max_length=200)


def _tel(body_tel: str) -> str:
    tel = normalize_phone(body_tel)
    if not phone_valid(tel):
        raise HTTPException(422, "Numéro de téléphone invalide.")
    return tel


@router.post("/otp/request")
async def demander_otp(body: TelIn, db: AsyncSession = Depends(get_db)):
    tel = _tel(body.telephone)
    otp, code = await create_otp(db, tel)
    if otp is None:
        raise HTTPException(429, f"Un code vient d'être envoyé. Attendez {settings.otp_resend_sec} secondes.")
    await send_otp_sms(tel, code)
    reponse: dict = {"ok": True, "message": "Code envoyé par SMS."}
    if settings.otp_dev_mode:
        # Mode démo : le code s'affiche (désactiver via OTP_DEV_MODE=false en production)
        reponse["dev_code"] = code
    return reponse


@router.post("/otp/verify")
async def verifier_otp(body: VerifyIn, db: AsyncSession = Depends(get_db)):
    tel = _tel(body.telephone)
    otp = await check_otp(db, tel, body.code)
    if not otp:
        raise HTTPException(401, "Code incorrect ou expiré.")

    user = (await db.execute(select(User).where(User.telephone == tel))).scalars().first()
    if user:
        if not user.actif:
            raise HTTPException(403, "Ce compte est désactivé. Contactez votre agence.")
        user.last_login_at = utc_naif()
        await db.commit()
        agence = await db.get(Agence, user.agence_id) if user.agence_id else None
        return {"token": make_token(user), "user": ser_user(user), "agence": ser_agence(agence) if agence else None,
                "nouveau_compte": False}

    # Pas de compte : si ce numéro correspond à un propriétaire invité -> compte lecture seule (F2)
    prop = (await db.execute(select(Proprietaire).where(Proprietaire.telephone == tel))).scalars().first()
    if prop:
        user = User(telephone=tel, nom=prop.nom, role="proprietaire",
                    agence_id=prop.agence_id, proprietaire_id=prop.id)
        db.add(user)
        await db.commit()
        await log_action(db, user, "compte.proprietaire_cree", "user", user.id, prop.nom)
        await db.commit()
        agence = await db.get(Agence, prop.agence_id)
        return {"token": make_token(user), "user": ser_user(user), "agence": ser_agence(agence),
                "nouveau_compte": False, "role": "proprietaire"}

    # Sinon : inscription (création d'une nouvelle agence)
    return {"inscription_requise": True, "jeton": make_inscription_token(tel)}


@router.post("/inscription")
async def inscription(body: InscriptionIn, db: AsyncSession = Depends(get_db)):
    try:
        payload = decode_token(body.jeton, expected_scope="inscription")
    except HTTPException:
        raise HTTPException(401, "Session d'inscription expirée. Recommencez (code SMS).")
    tel = payload["tel"]
    existe = (await db.execute(select(User).where(User.telephone == tel))).scalars().first()
    if existe:
        raise HTTPException(409, "Un compte existe déjà avec ce numéro. Connectez-vous.")

    agence = Agence(nom=body.nom_agence.strip(), telephone=tel)
    db.add(agence)
    await db.flush()
    db.add(Regles(agence_id=agence.id))
    db.add(ModeleMessage(agence_id=agence.id, type="relance", contenu=MODELE_RELANCE_DEFAUT))
    db.add(ModeleMessage(agence_id=agence.id, type="quittance", contenu=MODELE_QUITTANCE_DEFAUT))
    user = User(telephone=tel, nom=body.nom.strip(), role="responsable", agence_id=agence.id)
    db.add(user)
    await db.commit()
    await log_action(db, user, "compte.cree", "agence", agence.id, agence.nom)
    await db.commit()
    return {"token": make_token(user), "user": ser_user(user), "agence": ser_agence(agence),
            "nouveau_compte": True}


@router.get("/me")
async def profil(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    agence = await db.get(Agence, user.agence_id) if user.agence_id else None
    return {"user": ser_user(user), "agence": ser_agence(agence) if agence else None}
