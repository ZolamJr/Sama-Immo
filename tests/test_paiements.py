"""Tests F5, F6 — paiements, quittances PDF numérotées, QR, annulation par écriture, idempotence."""
from datetime import date
from pathlib import Path

import pytest
from conftest import auth, creer_agence, pepiniere

pytestmark = pytest.mark.asyncio


async def _bail_avec_echeance(client, token, loyer=200000):
    d = await pepiniere(client, token)
    r = await client.post("/api/baux", json={
        "unite_id": d["unite"]["id"], "locataire_id": d["loc"]["id"],
        "date_debut": date.today().isoformat(), "loyer": loyer, "charges": 0}, headers=auth(token))
    assert r.status_code == 200
    bail_id = r.json()["bail"]["id"]
    r = await client.get(f"/api/baux/{bail_id}", headers=auth(token))
    ech = r.json()["echeances"][0]
    return d, bail_id, ech


async def test_paiement_quittance_pdf(client):
    token = await creer_agence(client, nom="Agence Quittance")
    d, bail_id, ech = await _bail_avec_echeance(client, token)

    r = await client.post("/api/paiements", json={
        "echeance_id": ech["id"], "montant": 200000, "mode": "wave",
        "reference": "TX-123"}, headers=auth(token))
    assert r.status_code == 200, r.text
    corps = r.json()
    assert corps["paiement"]["montant"] == 200000
    recu = corps["recu"]
    assert recu["numero"].startswith("Q-")
    assert "/r/" in recu["lien_verif"]

    # le PDF existe et fait quelques Ko
    r = await client.get(recu["lien_pdf"], headers=auth(token))
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert len(r.content) > 2000
    assert r.content[:5] == b"%PDF-"

    # l'échéance est soldée
    r = await client.get(f"/api/echeances/{ech['id']}", headers=auth(token))
    assert r.json()["statut"] == "paye"

    # numéro séquentiel : un deuxième paiement (autre bail) incrémente
    r = await client.post("/api/locataires", json={"nom": "Autre Loc", "telephone": "773332211"}, headers=auth(token))
    loc2 = r.json()["locataire"]
    r = await client.post("/api/unites", json={"immeuble_id": d["immeuble"]["id"], "nom": "C1",
                                               "type": "chambre", "loyer": 90000, "charges": 0}, headers=auth(token))
    unite2 = r.json()["unite"]
    r = await client.post("/api/baux", json={"unite_id": unite2["id"], "locataire_id": loc2["id"],
                                             "date_debut": date.today().isoformat(), "loyer": 90000, "charges": 0},
                          headers=auth(token))
    ech2 = (await client.get(f"/api/baux/{r.json()['bail']['id']}", headers=auth(token))).json()["echeances"][0]
    r = await client.post("/api/paiements", json={"echeance_id": ech2["id"], "montant": 90000, "mode": "especes"},
                          headers=auth(token))
    num2 = r.json()["recu"]["numero"]
    assert int(num2.split("-")[-1]) == int(recu["numero"].split("-")[-1]) + 1


async def test_paiement_partiel_puis_solde(client):
    token = await creer_agence(client, nom="Agence Partiel")
    _, _, ech = await _bail_avec_echeance(client, token, loyer=300000)
    h = auth(token)

    r = await client.post("/api/paiements", json={"echeance_id": ech["id"], "montant": 100000, "mode": "orange_money"}, headers=h)
    assert r.status_code == 200
    r = await client.get(f"/api/echeances/{ech['id']}", headers=h)
    e = r.json()
    assert e["statut"] == "partiel"
    assert e["reste"] == 200000

    r = await client.post("/api/paiements", json={"echeance_id": ech["id"], "montant": 200000, "mode": "especes"}, headers=h)
    assert r.status_code == 200
    r = await client.get(f"/api/echeances/{ech['id']}", headers=h)
    assert r.json()["statut"] == "paye"
    assert r.json()["montant_paye"] == 300000


async def test_idempotence_client_uuid(client):
    """Le même paiement renvoyé deux fois (rejeu hors ligne) ne crée pas de doublon (F10)."""
    token = await creer_agence(client, nom="Agence Idem")
    _, _, ech = await _bail_avec_echeance(client, token)
    h = auth(token)
    corps = {"echeance_id": ech["id"], "montant": 150000, "mode": "wave",
             "client_uuid": "uuid-test-12345"}
    r1 = await client.post("/api/paiements", json=corps, headers=h)
    r2 = await client.post("/api/paiements", json=corps, headers=h)
    assert r1.status_code == r2.status_code == 200
    assert r2.json()["deja_existant"] is True
    assert r2.json()["paiement"]["id"] == r1.json()["paiement"]["id"]

    r = await client.get(f"/api/echeances/{ech['id']}", headers=h)
    assert r.json()["montant_paye"] == 150000  # pas de doublon
    assert r.json()["statut"] == "partiel"


async def test_annulation_par_ecriture(client):
    """Annulation motivée : écriture négative visible, quittance marquée annulée, échéance recalculée (F5)."""
    token = await creer_agence(client, nom="Agence Annul")
    _, _, ech = await _bail_avec_echeance(client, token)
    h = auth(token)
    r = await client.post("/api/paiements", json={"echeance_id": ech["id"], "montant": 200000, "mode": "cheque"}, headers=h)
    paiement = r.json()["paiement"]
    recu_numero = r.json()["recu"]["numero"]
    recu_id = r.json()["recu"]["id"]

    # motif obligatoire
    r = await client.post(f"/api/paiements/{paiement['id']}/annuler", json={"motif": "ab"}, headers=h)
    assert r.status_code == 422

    r = await client.post(f"/api/paiements/{paiement['id']}/annuler", json={"motif": "Chèque sans provision"}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["paiement"]["annule"] is True

    # l'échéance redevient en attente/partiel
    r = await client.get(f"/api/echeances/{ech['id']}", headers=h)
    assert r.json()["montant_paye"] == 0

    # la quittance est marquée annulée et son PDF régénéré avec la mention
    r = await client.get("/api/recus", headers=h)
    recus = r.json()["recus"]
    cible = [x for x in recus if x["numero"] == recu_numero][0]
    assert cible["annule"] is True

    # page publique : statut annulé
    token_url = cible["lien_verif"].rsplit("/", 1)[-1]
    r = await client.get(f"/api/public/recu/{token_url}")
    assert r.status_code == 200
    assert r.json()["statut"] == "annule"
    # intégrité du fichier vérifiée
    assert r.json()["integrite_fichier"] is True

    # double annulation refusée
    r = await client.post(f"/api/paiements/{paiement['id']}/annuler", json={"motif": "encore"}, headers=h)
    assert r.status_code == 422


async def test_verification_publique(client):
    """Page de contrôle publique par QR (F6) : valide, introuvable, intégrité."""
    token = await creer_agence(client, nom="Agence Verif")
    _, _, ech = await _bail_avec_echeance(client, token)
    h = auth(token)
    r = await client.post("/api/paiements", json={"echeance_id": ech["id"], "montant": 50000, "mode": "wave"}, headers=h)
    lien = r.json()["recu"]["lien_verif"]
    tok = lien.rsplit("/", 1)[-1]

    r = await client.get(f"/r/{tok}")
    assert r.status_code == 200
    assert "REÇU AUTHENTIQUE" in r.text
    assert "50 000 FCFA" in r.text

    r = await client.get(f"/api/public/recu/{tok}")
    assert r.status_code == 200
    assert r.json()["statut"] == "valide"
    assert r.json()["integrite_fichier"] is True

    r = await client.get("/r/inexistant-xyz")
    assert r.status_code == 200
    assert "introuvable" in r.text.lower()

    r = await client.get(f"/api/public/recu/{tok}/pdf")
    assert r.status_code == 200
    assert r.content[:5] == b"%PDF-"


async def test_recus_autres_types(client):
    """Reçu de caution, frais d'agence (alerte si > ½ mois), décharge (F6, §13)."""
    from conftest import pepiniere
    token = await creer_agence(client, nom="Agence Reçus")
    d = await pepiniere(client, token)
    h = auth(token)
    r = await client.post("/api/baux", json={
        "unite_id": d["unite"]["id"], "locataire_id": d["loc"]["id"],
        "date_debut": date.today().isoformat(), "loyer": 200000, "charges": 0,
        "caution": 400000}, headers=h)
    bail_id = r.json()["bail"]["id"]

    r = await client.post("/api/recus", json={"type": "caution", "bail_id": bail_id, "montant": 200000}, headers=h)
    assert r.status_code == 200
    assert r.json()["recu"]["numero"].startswith("C-")
    assert r.json()["alertes"] == []

    # frais > ½ mois -> alerte douce
    r = await client.post("/api/recus", json={"type": "frais_agence", "bail_id": bail_id, "montant": 150000}, headers=h)
    assert r.status_code == 200
    assert len(r.json()["alertes"]) == 1

    r = await client.post("/api/recus", json={"type": "decharge", "bail_id": bail_id, "montant": 0}, headers=h)
    assert r.status_code == 200
    assert r.json()["recu"]["numero"].startswith("D-")

    # les PDFs sont téléchargeables
    for t in ("C", "F", "D"):
        r = await client.get("/api/recus", headers=h)
        cible = [x for x in r.json()["recus"] if x["numero"].startswith(t + "-")][0]
        r = await client.get(cible["lien_pdf"], headers=h)
        assert r.status_code == 200
        assert r.content[:5] == b"%PDF-"


async def test_montants_invalides(client):
    token = await creer_agence(client)
    _, _, ech = await _bail_avec_echeance(client, token)
    h = auth(token)
    r = await client.post("/api/paiements", json={"echeance_id": ech["id"], "montant": -5, "mode": "wave"}, headers=h)
    assert r.status_code == 422
    r = await client.post("/api/paiements", json={"echeance_id": ech["id"], "montant": 100, "mode": "inconnu"}, headers=h)
    assert r.status_code == 422
    r = await client.post("/api/paiements", json={"echeance_id": "id-inconnu", "montant": 100, "mode": "wave"}, headers=h)
    assert r.status_code == 404
