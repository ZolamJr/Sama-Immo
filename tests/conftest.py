"""Configuration des tests : base temporaire, client HTTP async, helpers d'authentification."""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

# Doit être fait AVANT tout import de app.config
_TMP = tempfile.mkdtemp(prefix="samaimmo-test-")
os.environ["DB_PATH"] = str(Path(_TMP) / "test.db")
os.environ["DATA_DIR"] = _TMP
os.environ["OTP_DEV_MODE"] = "true"
os.environ["OTP_RESEND_SEC"] = "0"
os.environ["BASE_URL"] = "http://testserver"

import pytest  # noqa: E402
import httpx  # noqa: E402

from app.db import init_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="session", autouse=True)
async def _base_prete():
    await init_db()
    yield


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


_numero = [0]


def tel_unique() -> str:
    """Un numéro distinct par test (évite le anti-spam OTP et les collisions de comptes)."""
    _numero[0] += 1
    return f"+22177000{_numero[0]:04d}"


async def creer_agence(client: httpx.AsyncClient, nom="Agence Test", tel=None) -> str:
    """Passe le parcours complet : OTP -> inscription -> token."""
    tel = tel or tel_unique()
    r = await client.post("/api/auth/otp/request", json={"telephone": tel})
    assert r.status_code == 200, r.text
    code = r.json().get("dev_code")
    assert code, "OTP_DEV_MODE doit être actif dans les tests"
    r = await client.post("/api/auth/otp/verify", json={"telephone": tel, "code": code})
    assert r.status_code == 200, r.text
    jeton = r.json()["jeton"]
    r = await client.post("/api/auth/inscription", json={"jeton": jeton, "nom_agence": nom, "nom": "Moussa Test"})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def pepiniere(client: httpx.AsyncClient, token: str) -> dict:
    """Crée un jeu de données complet : propriétaire, immeuble, 2 unités, locataire, bail."""
    h = auth(token)
    r = await client.post("/api/proprietaires", json={
        "nom": "Ousmane Sow", "telephone": "+22178111000", "commission_pct": 5}, headers=h)
    prop = r.json()["proprietaire"]
    r = await client.post("/api/immeubles", json={
        "nom": "Immeuble Mermoz", "proprietaire_id": prop["id"], "quartier": "Mermoz",
        "adresse": "Rue 10 x Corniche"}, headers=h)
    imm = r.json()["immeuble"]
    r = await client.post("/api/unites", json={
        "immeuble_id": imm["id"], "nom": "Appartement B2", "type": "appartement",
        "loyer": 250000, "charges": 10000}, headers=h)
    unite = r.json()["unite"]
    r = await client.post("/api/locataires", json={
        "nom": "Aïssatou Ndiaye", "telephone": "772223344"}, headers=h)
    loc = r.json()["locataire"]
    return {"prop": prop, "immeuble": imm, "unite": unite, "loc": loc}
