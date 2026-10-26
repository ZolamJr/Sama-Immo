"""Authentification : téléphone + OTP (pas de mot de passe), sessions JWT, rôles."""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import JWT_SECRET, settings
from .db import SessionLocal
from .models import OtpCode, User


def utc_naif() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _hash_code(code: str) -> str:
    return hashlib.sha256(("sama-immo-otp:" + code).encode()).hexdigest()


def normalize_phone(tel: str) -> str:
    """Normalise un numéro sénégalais/international : espaces retirés, + conservé."""
    tel = (tel or "").strip().replace(" ", "").replace("-", "").replace(".", "")
    if not tel:
        return ""
    if tel.startswith("00"):
        tel = "+" + tel[2:]
    if tel.startswith("+"):
        return tel
    # local 9 chiffres (ex : 77 123 45 67) -> +221
    if tel.isdigit() and len(tel) == 9:
        return "+221" + tel
    return tel


def phone_valid(tel: str) -> bool:
    tel = normalize_phone(tel)
    if tel.startswith("+"):
        return tel[1:].isdigit() and 8 <= len(tel) - 1 <= 15
    return tel.isdigit() and 8 <= len(tel) <= 15


# ---------------------------------------------------------------- OTP

async def create_otp(db: AsyncSession, telephone: str, scope: str = "login") -> tuple[OtpCode, bool]:
    """Crée un code. Renvoie (code, ok) ; ok=False si demande trop récente (anti-spam)."""
    recent = await db.execute(
        select(OtpCode).where(
            OtpCode.telephone == telephone,
            OtpCode.created_at > utc_naif() - timedelta(seconds=settings.otp_resend_sec),
        )
    )
    if recent.scalars().first():
        return None, False
    code = "".join(secrets.choice("0123456789") for _ in range(settings.otp_len))
    otp = OtpCode(
        telephone=telephone,
        code_hash=_hash_code(code),
        scope=scope,
        expires_at=utc_naif() + timedelta(minutes=settings.otp_ttl_min),
    )
    db.add(otp)
    await db.commit()
    return otp, code


async def check_otp(db: AsyncSession, telephone: str, code: str) -> OtpCode | None:
    res = await db.execute(
        select(OtpCode)
        .where(OtpCode.telephone == telephone, OtpCode.consumed_at.is_(None))
        .order_by(OtpCode.created_at.desc())
        .limit(1)
    )
    otp = res.scalars().first()
    if not otp:
        return None
    if otp.expires_at < utc_naif():
        return None
    if otp.attempts >= settings.otp_max_attempts:
        return None
    if not hmac.compare_digest(otp.code_hash, _hash_code(code.strip())):
        otp.attempts += 1
        await db.commit()
        return None
    otp.consumed_at = utc_naif()
    await db.commit()
    return otp


# ---------------------------------------------------------------- JWT

def make_token(user: User, scope: str = "session") -> str:
    payload = {
        "sub": user.id,
        "tel": user.telephone,
        "role": user.role,
        "agence": user.agence_id,
        "prop": user.proprietaire_id,
        "scope": scope,
        "exp": datetime.now(timezone.utc)
        + (timedelta(days=settings.jwt_ttl_days) if scope == "session" else timedelta(minutes=30)),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def make_inscription_token(telephone: str) -> str:
    payload = {
        "tel": telephone,
        "scope": "inscription",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=30),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def decode_token(token: str, expected_scope: str = "session") -> dict:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Session expirée, reconnectez-vous.")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Jeton invalide.")
    if payload.get("scope") != expected_scope:
        raise HTTPException(401, "Jeton invalide.")
    return payload


# ---------------------------------------------------------------- Dépendances FastAPI

async def get_db(request: Request):
    async with SessionLocal() as session:
        request.state.db = session
        yield session


async def current_user(
    request: Request,
    authorization: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None, alias="X-Device-Id"),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Non connecté.")
    payload = decode_token(authorization.split(" ", 1)[1].strip())
    user = await db.get(User, payload["sub"])
    if not user or not user.actif:
        raise HTTPException(401, "Compte désactivé.")
    request.state.device_id = (x_device_id or "")[:100]
    return user


def require_roles(*roles: str):
    async def dep(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(403, "Action non autorisée pour votre rôle.")
        return user

    return dep


responsable_only = require_roles("responsable")
staff_or_responsable = require_roles("responsable", "employe")
any_role = require_roles("responsable", "employe", "proprietaire")
