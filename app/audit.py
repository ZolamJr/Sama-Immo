"""Journal d'audit (F11) : chaque action sensible laisse une trace."""
from __future__ import annotations

import json

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from .models import AuditLog, User


async def log_action(
    db: AsyncSession,
    user: User | None,
    action: str,
    objet_type: str = "",
    objet_id: str = "",
    objet_libelle: str = "",
    details: dict | None = None,
    device_id: str = "",
) -> None:
    entry = AuditLog(
        agence_id=(user.agence_id if user else None),
        user_id=(user.id if user else None),
        user_nom=(user.nom if user else ""),
        action=action,
        objet_type=objet_type,
        objet_id=str(objet_id),
        objet_libelle=str(objet_libelle)[:300],
        details=json.dumps(details or {}, ensure_ascii=False, default=str),
        device_id=(device_id or "")[:100],
    )
    db.add(entry)


def device_id_from(request: Request) -> str:
    return (getattr(request.state, "device_id", "") or "")[:100]
