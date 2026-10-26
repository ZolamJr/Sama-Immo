"""Routes publiques : vérification des quittances par QR code / lien (F6) et partage de rapports."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..db import SessionLocal
from ..models import Partage, Recu

router = APIRouter(tags=["public"])


def _page(titre: str, corps: str, couleur: str = "#0b5394") -> HTMLResponse:
    html = f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{titre}</title>
<style>
 body{{font-family:-apple-system,'Segoe UI',Roboto,Arial,sans-serif;background:#f4f7fb;margin:0;
      display:flex;min-height:100vh;align-items:center;justify-content:center;padding:24px;color:#1a1a1a}}
 .carte{{background:#fff;max-width:430px;width:100%;border-radius:16px;padding:28px;
        box-shadow:0 4px 24px rgba(11,83,148,.12)}}
 h1{{font-size:20px;color:{couleur};margin:0 0 4px}}
 .num{{color:#666;font-size:13px;margin-bottom:18px}}
 .ligne{{display:flex;justify-content:space-between;padding:10px 0;border-bottom:1px solid #eef2f7;font-size:15px}}
 .ligne b{{text-align:right}}
 .badge{{display:inline-block;margin-top:18px;padding:8px 16px;border-radius:999px;font-weight:700;font-size:14px}}
 .ok{{background:#e6f7ee;color:#0a7d43}} .ko{{background:#fdeaea;color:#b3261e}}
 .pied{{margin-top:22px;font-size:11.5px;color:#8a97a6;text-align:center;line-height:1.5}}
 .lien{{display:block;margin-top:18px;background:{couleur};color:#fff;text-align:center;padding:14px;
       border-radius:12px;text-decoration:none;font-weight:700}}
</style></head><body><div class="carte">{corps}
<div class="pied">{settings.app_name} — les quittances électroniques sont horodatées et ne peuvent pas être
supprimées ni modifiées : une erreur est corrigée par une écriture d'annulation visible.</div></div>
</body></html>"""
    return HTMLResponse(html)


def _lignes_contenu(c: dict) -> str:
    out = ""
    for k, v in c.items():
        if k in ("numero", "type", "empreinte"):
            continue
        lib = {"agence": "Agence", "locataire": "Locataire", "bien": "Bien", "periode": "Période",
               "montant": "Montant", "mode": "Mode de paiement", "date_paiement": "Date",
               "date": "Date"}.get(k, k)
        if k == "montant":
            v = f"{v:,} FCFA".replace(",", " ")
        if k in ("date_paiement", "date") and v:
            try:
                v = datetime.fromisoformat(str(v)).strftime("%d/%m/%Y")
            except ValueError:
                pass
        out += f'<div class="ligne"><span>{lib}</span><b>{v}</b></div>'
    return out


@router.get("/r/{token}", response_class=HTMLResponse)
async def verifier_quittance(token: str):
    async with SessionLocal() as db:
        recu = (await db.execute(select(Recu).where(Recu.token == token))).scalars().first()
    if not recu:
        return _page("Reçu introuvable",
                     "<h1>Reçu introuvable</h1><div class='num'>—</div>"
                     "<p>Ce lien ne correspond à aucun reçu. Vérifiez le lien ou scannez à nouveau le QR code.</p>",
                     "#b3261e")
    c = json.loads(recu.contenu or "{}")
    integre = False
    if recu.fichier_path and Path(recu.fichier_path).exists():
        empreinte_actuelle = hashlib.sha256(Path(recu.fichier_path).read_bytes()).hexdigest()
        integre = empreinte_actuelle == recu.empreinte
    if recu.annule:
        corps = (f"<h1>Reçu annulé</h1><div class='num'>{recu.numero}</div>"
                 + _lignes_contenu(c)
                 + '<span class="badge ko">REÇU ANNULÉ</span>'
                 + "<p style='font-size:13px;color:#666;margin-top:12px'>Ce paiement a été annulé par une "
                   "écriture motivée, visible dans le journal de l'agence.</p>")
    else:
        corps = (f"<h1>Reçu vérifié</h1><div class='num'>{recu.numero}</div>"
                 + _lignes_contenu(c)
                 + '<span class="badge ok">✔ REÇU AUTHENTIQUE</span>')
    if recu.fichier_path and Path(recu.fichier_path).exists():
        corps += f'<a class="lien" href="/api/public/recu/{token}/pdf">Télécharger le PDF</a>'
        corps += ('<div class="pied" style="margin-top:10px">Intégrité du fichier : '
                  + ("conforme (SHA-256 vérifiée)" if integre else "⚠ fichier altéré, empreinte non conforme")
                  + "</div>")
    return _page(f"Reçu {recu.numero}", corps)


@router.get("/api/public/recu/{token}")
async def api_recu_public(token: str):
    async with SessionLocal() as db:
        recu = (await db.execute(select(Recu).where(Recu.token == token))).scalars().first()
    if not recu:
        raise HTTPException(404, "Reçu introuvable.")
    c = json.loads(recu.contenu or "{}")
    integre = None
    if recu.fichier_path and Path(recu.fichier_path).exists():
        integre = hashlib.sha256(Path(recu.fichier_path).read_bytes()).hexdigest() == recu.empreinte
    return {"numero": recu.numero, "statut": "annule" if recu.annule else "valide",
            "integrite_fichier": integre, "contenu": c,
            "date_emission": recu.created_at.isoformat()}


@router.get("/api/public/recu/{token}/pdf")
async def pdf_recu_public(token: str):
    async with SessionLocal() as db:
        recu = (await db.execute(select(Recu).where(Recu.token == token))).scalars().first()
    if not recu or not Path(recu.fichier_path).exists():
        raise HTTPException(404, "Reçu introuvable.")
    return FileResponse(recu.fichier_path, media_type="application/pdf",
                        filename=f"{recu.numero}.pdf")


@router.get("/p/{token}", response_class=HTMLResponse)
async def page_partage(token: str):
    async with SessionLocal() as db:
        p = await db.get(Partage, token)
    if not p or not Path(p.chemin).exists():
        return _page("Lien invalide", "<h1>Lien invalide ou expiré</h1>", "#b3261e")
    return _page("Rapport de gestion",
                 "<h1>Rapport de gestion</h1>"
                 "<p>Le rapport détaillé est disponible au format PDF.</p>"
                 f'<a class="lien" href="/api/public/partage/{token}/pdf">Télécharger le rapport (PDF)</a>')


@router.get("/api/public/partage/{token}/pdf")
async def pdf_partage(token: str):
    async with SessionLocal() as db:
        p = await db.get(Partage, token)
    if not p or not Path(p.chemin).exists():
        raise HTTPException(404, "Fichier introuvable.")
    return FileResponse(p.chemin, media_type="application/pdf", filename=p.filename)
