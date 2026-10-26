"""Tests F1 — Authentification par OTP, inscription, rôles, propriétaire lecture seule."""
import pytest
from conftest import auth, creer_agence, tel_unique

pytestmark = pytest.mark.asyncio


async def test_parcours_otp_complet(client):
    tel = tel_unique()
    r = await client.post("/api/auth/otp/request", json={"telephone": tel})
    assert r.status_code == 200
    corps = r.json()
    assert corps["ok"] is True
    assert "dev_code" in corps  # mode démo

    # mauvais code
    r = await client.post("/api/auth/otp/verify", json={"telephone": tel, "code": "000000"})
    assert r.status_code == 401

    # bon code -> inscription demandée
    code = corps["dev_code"]
    r = await client.post("/api/auth/otp/verify", json={"telephone": tel, "code": code})
    assert r.status_code == 200
    data = r.json()
    assert data["inscription_requise"] is True
    assert "jeton" in data

    # inscription
    r = await client.post("/api/auth/inscription", json={
        "jeton": data["jeton"], "nom_agence": "Immo Dakar", "nom": "Fatou Ba"})
    assert r.status_code == 200
    token = r.json()["token"]
    assert r.json()["user"]["role"] == "responsable"

    # /me
    r = await client.get("/api/auth/me", headers=auth(token))
    assert r.status_code == 200
    assert r.json()["agence"]["nom"] == "Immo Dakar"


async def test_telephone_invalide(client):
    r = await client.post("/api/auth/otp/request", json={"telephone": "abc"})
    assert r.status_code == 422


async def test_reconnexion_sans_inscription(client):
    tel = tel_unique()
    r = await client.post("/api/auth/otp/request", json={"telephone": tel})
    code = r.json()["dev_code"]
    r = await client.post("/api/auth/otp/verify", json={"telephone": tel, "code": code})
    jeton = r.json()["jeton"]
    await client.post("/api/auth/inscription", json={"jeton": jeton, "nom_agence": "A1", "nom": "X Y"})
    # deuxième connexion : direct, sans inscription
    r = await client.post("/api/auth/otp/request", json={"telephone": tel})
    code = r.json()["dev_code"]
    r = await client.post("/api/auth/otp/verify", json={"telephone": tel, "code": code})
    assert r.status_code == 200
    assert r.json().get("token")
    assert not r.json().get("inscription_requise")


async def test_code_expire(client):
    from app.security import create_otp, check_otp
    from app.db import SessionLocal
    from datetime import datetime, timezone, timedelta
    async with SessionLocal() as db:
        otp, code = await create_otp(db, "+221999000111")
        otp.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=1)
        await db.commit()
        assert await check_otp(db, "+221999000111", code) is None


async def test_proprietaire_lecture_seule(client):
    """Un propriétaire dont le téléphone est enregistré obtient un compte lecture seule (F2)."""
    token = await creer_agence(client, nom="Agence Prop")
    h = auth(token)
    tel_prop = "+221785556677"
    r = await client.post("/api/proprietaires", json={
        "nom": "Mame Diop", "telephone": tel_prop, "commission_pct": 10}, headers=h)
    assert r.status_code == 200

    # le propriétaire se connecte : compte lecture seule automatique
    r = await client.post("/api/auth/otp/request", json={"telephone": tel_prop})
    code = r.json()["dev_code"]
    r = await client.post("/api/auth/otp/verify", json={"telephone": tel_prop, "code": code})
    assert r.status_code == 200
    data = r.json()
    assert data["user"]["role"] == "proprietaire"

    # il peut lire le dashboard mais pas écrire
    r = await client.get("/api/dashboard", headers=auth(data["token"]))
    assert r.status_code == 200
    r = await client.post("/api/locataires", json={"nom": "Quelqu'un"}, headers=auth(data["token"]))
    assert r.status_code == 403
    r = await client.get("/api/audit", headers=auth(data["token"]))
    assert r.status_code == 403


async def test_roles_employe(client):
    token = await creer_agence(client)
    h = auth(token)
    tel_emp = "+221771112233"
    r = await client.post("/api/users", json={
        "nom": "Employé Test", "telephone": tel_emp, "role": "employe"}, headers=h)
    assert r.status_code == 200

    r = await client.post("/api/auth/otp/request", json={"telephone": tel_emp})
    code = r.json()["dev_code"]
    r = await client.post("/api/auth/otp/verify", json={"telephone": tel_emp, "code": code})
    token_emp = r.json()["token"]

    # l'employé peut gérer le métier…
    r = await client.post("/api/locataires", json={"nom": "Client Un", "telephone": "770001122"}, headers=auth(token_emp))
    assert r.status_code == 200
    # …mais pas les paramètres ni l'audit ni les users
    r = await client.get("/api/audit", headers=auth(token_emp))
    assert r.status_code == 403
    r = await client.post("/api/users", json={"nom": "Z", "telephone": "+221770000999"}, headers=auth(token_emp))
    assert r.status_code == 403
    r = await client.patch("/api/regles", json={"caution_max_mois": 3}, headers=auth(token_emp))
    assert r.status_code == 403
