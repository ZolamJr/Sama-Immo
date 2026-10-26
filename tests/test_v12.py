"""Tests v1.2 — mandat de gestion, cautions (décret 2023-382), notifications, exports PDF."""
from datetime import date

import pytest
from conftest import auth, creer_agence, pepiniere

pytestmark = pytest.mark.asyncio

DEBUT_3_MOIS = (lambda: date.fromordinal(date.today().toordinal() - 90).isoformat())()


def _texte_pdf(rep) -> str:
    """Extrait le texte d'un PDF reportlab sans dépendance externe.
    Reportlab encode ses flux en ASCII85 puis Flate : on décode les deux."""
    import base64
    import re
    import zlib

    morceaux = []
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", rep.content, re.S):
        data = m.group(1).strip()
        try:
            if data.endswith(b"~>"):
                data = base64.a85decode(data[:-2].strip(), adobe=False)
            data = zlib.decompress(data)
        except Exception:
            continue  # flux non texte (image, police…)
        for s in re.findall(rb"\((?:\\.|[^\\()])*\)", data):
            t = s[1:-1]
            t = re.sub(rb"\\([()\\])", rb"\1", t)
            t = re.sub(rb"\\([0-7]{1,3})", lambda x: bytes([int(x.group(1), 8) & 0xFF]), t)
            try:
                morceaux.append(t.decode("latin-1"))
            except UnicodeDecodeError:
                pass
    return " ".join(" ".join(morceaux).split())


async def _creer_bail(client, h, d, caution=500000):
    r = await client.post("/api/baux", json={
        "unite_id": d["unite"]["id"], "locataire_id": d["loc"]["id"],
        "date_debut": DEBUT_3_MOIS, "loyer": 250000, "charges": 10000,
        "jour_echeance": 5, "caution": caution, "duree_type": "triennale"}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()["bail"]


# ---------------------------------------------------------------- Mandat de gestion

async def test_mandat_gestion(client):
    token = await creer_agence(client, nom="Agence Mandat")
    h = auth(token)
    r = await client.post("/api/proprietaires", json={
        "nom": "Awa Ba", "telephone": "+221781112299", "commission_pct": 5,
        "mandat_debut": "2024-01-15", "mandat_fin": "2026-12-31"}, headers=h)
    assert r.status_code == 200, r.text
    prop = r.json()["proprietaire"]
    assert prop["mandat_debut"] == "2024-01-15" and prop["mandat_fin"] == "2026-12-31"

    # fin avant début -> refusé
    r = await client.patch(f"/api/proprietaires/{prop['id']}", json={
        "mandat_debut": "2026-01-01", "mandat_fin": "2025-01-01"}, headers=h)
    assert r.status_code == 422

    # patch valide + visible dans le rapport
    r = await client.patch(f"/api/proprietaires/{prop['id']}", json={
        "mandat_fin": "2027-06-30", "commission_pct": 7.5}, headers=h)
    assert r.status_code == 200
    r = await client.get(f"/api/rapports/proprietaire/{prop['id']}", headers=h)
    assert r.json()["proprietaire"]["mandat_fin"] == "2027-06-30"
    assert r.json()["proprietaire"]["commission_pct"] == 7.5


async def test_notification_mandat_bientot_echu(client):
    token = await creer_agence(client, nom="Agence Mandat Echu")
    h = auth(token)
    r = await client.post("/api/proprietaires", json={
        "nom": "Modou Sène", "telephone": "+221781112288", "commission_pct": 5,
        "mandat_debut": "2023-01-01", "mandat_fin": date.today().isoformat()}, headers=h)
    assert r.status_code == 200
    r = await client.get("/api/notifications", headers=h)
    cles = [n["cle"] for n in r.json()["notifications"]]
    assert "mandats" in cles


# ---------------------------------------------------------------- Caution (décret 2023-382)

async def test_caution_situation_et_restitution(client):
    token = await creer_agence(client, nom="Agence Caution")
    d = await pepiniere(client, token)
    h = auth(token)
    bail = await _creer_bail(client, h, d, caution=500000)  # 2 mois de loyer (250 000)

    # 1er versement : 1 mois à l'entrée (décret) -> reçu C-...
    r = await client.post("/api/recus", json={
        "type": "caution", "bail_id": bail["id"], "montant": 250000}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["recu"]["numero"].startswith("C-")

    r = await client.get(f"/api/baux/{bail['id']}", headers=h)
    c = r.json()["caution_detail"]
    assert c["prevue"] == 500000 and c["versee"] == 250000
    assert c["statut"] == "partielle"
    # échéancier légal : 1 mois à l'entrée + 12e étalées
    assert c["echeancier"][0]["libelle"].startswith("À l'entrée")
    assert len(c["echeancier"]) == 13
    assert sum(e["montant"] for e in c["echeancier"]) == 500000

    # 2e versement (solde) puis fin du bail -> à restituer
    await client.post("/api/recus", json={
        "type": "caution", "bail_id": bail["id"], "montant": 250000}, headers=h)
    r = await client.post(f"/api/baux/{bail['id']}/terminer", json={"motif": "départ"}, headers=h)
    assert r.status_code == 200
    r = await client.get(f"/api/baux/{bail['id']}", headers=h)
    c = r.json()["caution_detail"]
    assert c["statut"] == "a_restituer" and c["a_restituer"] == 500000
    assert c["date_limite_restitution"] is not None  # 1 mois après la remise des clés

    # retenue sans motif -> refusée (décret : retenues justifiées uniquement)
    r = await client.post(f"/api/baux/{bail['id']}/caution/restituer", json={
        "montant_retenu": 50000}, headers=h)
    assert r.status_code == 422

    # restitution avec retenue justifiée -> reçu R-...
    r = await client.post(f"/api/baux/{bail['id']}/caution/restituer", json={
        "montant_retenu": 50000, "motif_retenue": "dégradations état des lieux de sortie"}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["recu"]["numero"].startswith("R-")
    texte = _texte_pdf(await client.get(r.json()["recu"]["lien_pdf"], headers=h))
    assert "RESTITUTION DE CAUTION" in texte.upper() or "restitution de caution" in texte.lower()
    assert "50 000" in texte  # retenue

    r = await client.get(f"/api/baux/{bail['id']}", headers=h)
    c = r.json()["caution_detail"]
    assert c["statut"] == "restituee" and c["retenue"] == 50000


async def test_notification_cautions_a_restituer(client):
    token = await creer_agence(client, nom="Agence Notif Caution")
    d = await pepiniere(client, token)
    h = auth(token)
    bail = await _creer_bail(client, h, d, caution=250000)
    await client.post("/api/recus", json={
        "type": "caution", "bail_id": bail["id"], "montant": 250000}, headers=h)
    await client.post(f"/api/baux/{bail['id']}/terminer", json={"motif": "départ"}, headers=h)
    r = await client.get("/api/notifications", headers=h)
    notif = [n for n in r.json()["notifications"] if n["cle"] == "cautions"]
    assert notif and notif[0]["nombre"] == 1


async def test_notifications_retards_et_du_jour(client):
    token = await creer_agence(client, nom="Agence Notifs")
    d = await pepiniere(client, token)
    h = auth(token)
    await _creer_bail(client, h, d)  # aucun paiement -> en retard au-delà du 10
    r = await client.get("/api/notifications", headers=h)
    cles = [n["cle"] for n in r.json()["notifications"]]
    assert "retards" in cles


# ---------------------------------------------------------------- Exports PDF (v1.2)

async def test_pdf_etat_loyers_du_mois(client):
    token = await creer_agence(client, nom="Agence PDF Loyers")
    d = await pepiniere(client, token)
    h = auth(token)
    await _creer_bail(client, h, d)
    r = await client.get("/api/rapports/loyers-mois.pdf", headers=h)
    assert r.status_code == 200 and r.content[:4] == b"%PDF"
    texte = _texte_pdf(r)
    assert "TAT DES LOYERS" in texte.upper() or "ÉTAT DES LOYERS" in texte
    assert "Aïssatou Ndiaye" in texte and "260 000" in texte  # loyer+charges


async def test_pdf_arrieres(client):
    token = await creer_agence(client, nom="Agence PDF Arriérés")
    d = await pepiniere(client, token)
    h = auth(token)
    await _creer_bail(client, h, d)  # impayé -> retard
    r = await client.get("/api/rapports/arrieres.pdf", headers=h)
    assert r.status_code == 200 and r.content[:4] == b"%PDF"
    texte = _texte_pdf(r)
    assert "ARRI" in texte.upper()  # ÉTAT DES ARRIÉRÉS


async def test_pdf_recap_locataire(client):
    token = await creer_agence(client, nom="Agence PDF Récap")
    d = await pepiniere(client, token)
    h = auth(token)
    await _creer_bail(client, h, d)
    r = await client.get(f"/api/locataires/{d['loc']['id']}/recap.pdf", headers=h)
    assert r.status_code == 200 and r.content[:4] == b"%PDF"
    texte = _texte_pdf(r)
    assert "FICHE LOCATAIRE" in texte.upper() and "Aïssatou Ndiaye" in texte


async def test_pdf_journal_audit(client):
    token = await creer_agence(client, nom="Agence PDF Audit")
    h = auth(token)
    await pepiniere(client, token)
    r = await client.get("/api/audit/export.pdf", headers=h)
    assert r.status_code == 200 and r.content[:4] == b"%PDF"
    texte = _texte_pdf(r)
    assert "JOURNAL D" in texte.upper()  # JOURNAL D'ACTIVITÉ


# ---------------------------------------------------------------- Mentions gérant sur la quittance

async def test_quittance_mentionne_le_gerant(client):
    token = await creer_agence(client, nom="Agence Gérant Quittance", nom_kwargs=None) if False else await creer_agence(client, nom="Agence Gérant Quittance")
    d = await pepiniere(client, token)
    h = auth(token)
    bail = await _creer_bail(client, h, d)
    r = await client.get("/api/echeances", headers=h)
    ech = r.json()["echeances"][0]
    r = await client.post("/api/paiements", json={
        "echeance_id": ech["id"], "montant": 260000, "mode": "wave"}, headers=h)
    assert r.status_code == 200, r.text
    texte = _texte_pdf(await client.get(r.json()["recu"]["lien_pdf"], headers=h))
    # la quittance est signée par le gérant, pour l'agence (relation gérant-agence)
    assert "gérant(e) de" in texte and "Agence Gérant Quittance" in texte
