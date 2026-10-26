"""Envoi des codes OTP : SMS (console ou passerelle HTTP générique) — branchement clé API sans toucher au code.

Pour brancher un vrai agrégateur (Orange SN API, TerangaSms, Twilio…) :
  SMS_PROVIDER=http  SMS_HTTP_URL=https://api.exemple.com/v1/send  SMS_HTTP_KEY=xxx
La passerelle doit accepter un POST JSON {phone, message, sender}.
"""
from __future__ import annotations

import httpx
from fastapi import HTTPException

from .config import settings


async def send_otp_sms(telephone: str, code: str) -> None:
    message = f"{settings.app_name} : votre code de connexion est {code}. Valable {settings.otp_ttl_min} minutes."
    provider = settings.sms_provider.lower()
    if provider == "http":
        if not settings.sms_http_url:
            raise HTTPException(500, "SMS_PROVIDER=http mais SMS_HTTP_URL absente.")
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                await client.post(
                    settings.sms_http_url,
                    json={"phone": telephone, "message": message, "sender": settings.sms_sender_name},
                    headers={"Authorization": f"Bearer {settings.sms_http_key}"},
                )
        except httpx.HTTPError as e:  # pragma: no cover
            raise HTTPException(502, f"Échec d'envoi SMS : {e}")
    else:  # console
        print(f"[OTP] {telephone} -> code {code}", flush=True)
