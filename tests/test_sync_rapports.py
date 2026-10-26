"""Tests F10 (synchronisation), F8 (rapports), F7 (relances), F9/F11 (audit, export), F12 (documents)."""
import io
from datetime import date

import pytest
from conftest import auth, creer_agence, pepiniere

pytestmark = pytest.mark.asyncio


def _jpeg() -> bytes:
    """Petite image JPEG de test."""
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (60, 40), (200, 30, 30)).save(buf, "JPEG")
    return buf.getvalue()


async def test_sync_rejeu_paiement_sans_doublon(client):
    """Le scénario critique F10 : paiement saisi hors ligne, synchronisé, puis re-synchronisé."""
    token = await creer_agence(client, nom="Agence Sync")
    d = await pepiniere(client, token)
    h = auth(token)
    r = await client.post("/api/baux", json={
        "unite_id": d["unite"]["id"], "locataire_id": d["loc"]["id"],
        "date_debut": date.today().isoformat(), "loyer": 180000, "charges": 20000}, headers=h)
    bail_id = r.json()["bail"]["id"]
    ech = (await client.get(f"/api/baux/{bail_id}", headers=h)).json()["echeances"][0]

    action = {"id": "act-1", "type": "paiement.create", "payload": {
        "echeance_id": ech["id"], "montant": 200000, "mode": "wave",
        "date_paiement": date.today().isoformat(), "reference": "offline-1",
        "client_uuid": "sync-uuid-001"}}
    r = await client.post("/api/sync", json={"device_id": "tel-A", "actions": [action]}, headers=h)
    assert r.status_code == 200, r.text
    res = r.json()["resultats"][0]
    assert res["status"] == "applied"
    numero1 = res["entity"]["recu"]["numero"]

    # rejeu immédiat (double envoi réseau) -> duplicate, même reçu
    r = await client.post("/api/sync", json={"device_id": "tel-A", "actions": [action]}, headers=h)
    res = r.json()["resultats"][0]
    assert res["status"] == "duplicate"
    assert res["entity"]["recu"]["numero"] == numero1

    r = await client.get(f"/api/echeances/{ech['id']}", headers=h)
    assert r.json()["montant_paye"] == 200000
    assert r.json()["statut"] == "paye"

    # un autre appareil paie la même échéance en trop : autorisé (append only) mais trace
    action2 = {"id": "act-2", "type": "paiement.create", "payload": {
        "echeance_id": ech["id"], "montant": 50000, "mode": "especes",
        "date_paiement": date.today().isoformat(), "client_uuid": "sync-uuid-002"}}
    r = await client.post("/api/sync", json={"device_id": "tel-B", "actions": [action2]}, headers=h)
    assert r.json()["resultats"][0]["status"] == "applied"
    r = await client.get(f"/api/echeances/{ech['id']}", headers=h)
    assert r.json()["montant_paye"] == 250000  # jamais écrasé : cumul


async def test_sync_creation_hors_ligne_idempotente(client):
    token = await creer_agence(client, nom="Agence SyncCreate")
    d = await pepiniere(client, token)
    h = auth(token)
    loc_uuid = "11111111-1111-4111-8111-111111111111"
    action = {"id": "a1", "type": "locataire.create", "payload": {
        "id": loc_uuid, "nom": "Créé Hors Ligne", "telephone": "770998877"}}
    r = await client.post("/api/sync", json={"device_id": "tel-C", "actions": [action]}, headers=h)
    assert r.json()["resultats"][0]["status"] == "applied"
    r = await client.post("/api/sync", json={"device_id": "tel-C", "actions": [action]}, headers=h)
    assert r.json()["resultats"][0]["status"] == "duplicate"

    # bail créé hors ligne : idempotent + échéances générées
    r = await client.post("/api/unites", json={"immeuble_id": d["immeuble"]["id"], "nom": "D1",
                                               "type": "chambre", "loyer": 80000, "charges": 0}, headers=h)
    unite_id = r.json()["unite"]["id"]
    bail_uuid = "22222222-2222-4222-8222-222222222222"
    action_bail = {"id": "a2", "type": "bail.create", "payload": {
        "id": bail_uuid, "unite_id": unite_id, "locataire_id": loc_uuid,
        "date_debut": date.today().isoformat(), "loyer": 80000, "charges": 0, "caution": 160000}}
    r = await client.post("/api/sync", json={"device_id": "tel-C", "actions": [action_bail]}, headers=h)
    assert r.json()["resultats"][0]["status"] == "applied"
    r = await client.post("/api/sync", json={"device_id": "tel-C", "actions": [action_bail]}, headers=h)
    assert r.json()["resultats"][0]["status"] == "duplicate"
    r = await client.get(f"/api/baux/{bail_uuid}", headers=h)
    assert r.status_code == 200
    assert len(r.json()["echeances"]) >= 1
    # alerte caution = 2 mois -> aucune
    # (80000*2 = 160000 = caution -> conforme)


async def test_sync_derniere_version_gagne(client):
    """Deux appareils modifient la même fiche : la plus récente gagne, l'autre reçoit conflict (F10)."""
    token = await creer_agence(client, nom="Agence LWW")
    d = await pepiniere(client, token)
    h = auth(token)
    from datetime import datetime, timedelta, timezone

    def ts(secondes: str) -> str:
        return (datetime.now(timezone.utc) + timedelta(seconds=int(secondes))).isoformat()

    # modification postérieure à la création de la fiche -> appliquée
    r = await client.post("/api/sync", json={"device_id": "tel-D", "actions": [
        {"id": "m1", "type": "locataire.update", "payload": {
            "id": d["loc"]["id"], "updated_at": ts(60), "nom": "Premier Changement"}}]}, headers=h)
    assert r.json()["resultats"][0]["status"] == "applied"

    # une version encore plus récente gagne
    r = await client.post("/api/sync", json={"device_id": "tel-E", "actions": [
        {"id": "m2", "type": "locataire.update", "payload": {
            "id": d["loc"]["id"], "updated_at": ts(120), "nom": "Nom Récent"}}]}, headers=h)
    assert r.json()["resultats"][0]["status"] == "applied"

    # une version plus ancienne -> conflit, la version serveur est renvoyée
    r = await client.post("/api/sync", json={"device_id": "tel-D", "actions": [
        {"id": "m3", "type": "locataire.update", "payload": {
            "id": d["loc"]["id"], "updated_at": ts(30), "nom": "Trop Vieux"}}]}, headers=h)
    res = r.json()["resultats"][0]
    assert res["status"] == "conflict"
    assert res["entity"]["nom"] == "Nom Récent"

    r = await client.get(f"/api/locataires/{d['loc']['id']}", headers=h)
    assert r.json()["nom"] == "Nom Récent"


async def test_relances(client):
    """F7 : liste des retards triée par ancienneté + message pré-rédigé + trace."""
    token = await creer_agence(client, nom="Agence Relance")
    d = await pepiniere(client, token)
    h = auth(token)
    vieux = date.fromordinal(date.today().toordinal() - 120)
    r = await client.post("/api/baux", json={
        "unite_id": d["unite"]["id"], "locataire_id": d["loc"]["id"],
        "date_debut": vieux.isoformat(), "loyer": 150000, "charges": 0}, headers=h)
    bail_id = r.json()["bail"]["id"]

    r = await client.get("/api/relances/retards", headers=h)
    retards = r.json()["retards"]
    assert len(retards) >= 2
    # tri par ancienneté : la première échéance est la plus vieille
    dates = [x["date_echeance"] for x in retards]
    assert dates == sorted(dates)
    msg = retards[0]["message"]
    assert "Aïssatou Ndiaye" in msg
    assert "FCFA" in msg or "150 000" in msg
    assert retards[0]["whatsapp"].isdigit()

    # trace de relance
    r = await client.post("/api/relances", json={
        "echeance_id": retards[0]["id"], "message": msg, "canal": "whatsapp"}, headers=h)
    assert r.status_code == 200


async def test_rapport_proprietaire(client):
    """F8 : encaissé, commission, à reverser + PDF partageable."""
    token = await creer_agence(client, nom="Agence Rapport")
    d = await pepiniere(client, token)
    h = auth(token)
    r = await client.post("/api/baux", json={
        "unite_id": d["unite"]["id"], "locataire_id": d["loc"]["id"],
        "date_debut": date.today().isoformat(), "loyer": 300000, "charges": 20000}, headers=h)
    ech = (await client.get(f"/api/baux/{r.json()['bail']['id']}", headers=h)).json()["echeances"][0]
    await client.post("/api/paiements", json={"echeance_id": ech["id"], "montant": 320000, "mode": "wave"}, headers=h)

    r = await client.get(f"/api/rapports/proprietaire/{d['prop']['id']}", headers=h)
    rap = r.json()
    assert rap["encaisse"] == 320000
    assert rap["proprietaire"]["commission_pct"] == 5
    assert rap["commission"] == 16000
    assert rap["a_reverser"] == 304000
    assert rap["biens"][0]["immeuble"] == "Immeuble Mermoz"

    r = await client.post(f"/api/rapports/proprietaire/{d['prop']['id']}/pdf", headers=h, json={})
    assert r.status_code == 200, r.text
    lien_pdf = r.json()["lien_pdf"]
    r = await client.get(lien_pdf)
    assert r.status_code == 200
    assert r.content[:5] == b"%PDF-"

    # page de partage publique
    r2 = await client.post(f"/api/rapports/proprietaire/{d['prop']['id']}/pdf", headers=h, json={})
    token_pub = r2.json()["lien_public"].rsplit("/", 1)[-1]
    rp = await client.get(f"/p/{token_pub}")
    assert rp.status_code == 200
    assert "Rapport" in rp.text
    rp = await client.get(f"/api/public/partage/{token_pub}/pdf")
    assert rp.content[:5] == b"%PDF-"


async def test_documents(client):
    """F12 : upload de 3 photos -> un seul PDF 3 pages ; validation du rattachement."""
    token = await creer_agence(client, nom="Agence Docs")
    d = await pepiniere(client, token)
    h = auth(token)
    r = await client.post("/api/baux", json={
        "unite_id": d["unite"]["id"], "locataire_id": d["loc"]["id"],
        "date_debut": date.today().isoformat(), "loyer": 100000, "charges": 0}, headers=h)
    bail_id = r.json()["bail"]["id"]

    fichiers = [("fichiers", ("page1.jpg", io.BytesIO(_jpeg()), "image/jpeg")),
                ("fichiers", ("page2.jpg", io.BytesIO(_jpeg()), "image/jpeg")),
                ("fichiers", ("page3.jpg", io.BytesIO(_jpeg()), "image/jpeg"))]
    r = await client.post("/api/documents", headers=h, files=fichiers, data={
        "attache_type": "bail", "attache_id": bail_id, "type_document": "bail_signe"})
    assert r.status_code == 200, r.text
    doc = r.json()["document"]
    assert doc["pages"] == 3
    assert doc["mimetype"] == "application/pdf"

    # PDF accessible
    r = await client.get(f"/api/documents/{doc['id']}/fichier", headers=h)
    assert r.status_code == 200
    assert r.content[:5] == b"%PDF-"

    # rattachement inconnu refusé
    r = await client.post("/api/documents", headers=h,
                          files=[("fichiers", ("p.jpg", io.BytesIO(_jpeg()), "image/jpeg"))],
                          data={"attache_type": "bail", "attache_id": "inconnu", "type_document": "autre"})
    assert r.status_code == 404

    # listing par fiche
    r = await client.get(f"/api/documents?attache_type=bail&attache_id={bail_id}", headers=h)
    assert len(r.json()["documents"]) == 1


async def test_audit_et_export(client):
    """F11 : journal complet. F9 : export CSV."""
    token = await creer_agence(client, nom="Agence AuditExport")
    d = await pepiniere(client, token)
    h = auth(token)
    r = await client.post("/api/baux", json={
        "unite_id": d["unite"]["id"], "locataire_id": d["loc"]["id"],
        "date_debut": date.today().isoformat(), "loyer": 100000, "charges": 0}, headers=h)
    ech = (await client.get(f"/api/baux/{r.json()['bail']['id']}", headers=h)).json()["echeances"][0]
    await client.post("/api/paiements", json={"echeance_id": ech["id"], "montant": 100000, "mode": "wave"}, headers=h)

    r = await client.get("/api/audit?limit=50", headers=h)
    logs = r.json()["logs"]
    actions = [l["action"] for l in logs]
    assert "compte.cree" in actions
    assert "proprietaire.cree" in actions
    assert "bail.cree" in actions
    assert "paiement.cree" in actions
    assert "recu.quittance" not in actions  # la quittance est dans le détail du paiement
    paiement_log = [l for l in logs if l["action"] == "paiement.cree"][0]
    assert paiement_log["details"]["montant"] == 100000
    assert paiement_log["user"] == "Moussa Test"

    # filtre
    r = await client.get("/api/audit?q=paiement", headers=h)
    assert all("paiement" in l["action"] or "paiement" in l["objet_libelle"].lower() for l in r.json()["logs"])

    # export CSV avec BOM
    r = await client.get("/api/export/paiements.csv", headers=h)
    assert r.status_code == 200
    assert r.text.startswith("\ufeff")
    assert "montant" in r.text
    r = await client.get("/api/export/echeances.csv", headers=h)
    assert "montant_du" in r.text
    r = await client.get("/api/export/table_inconnue.csv", headers=h)
    assert r.status_code == 404


async def test_modeles_et_regles(client):
    """F9/F13 : modèles de messages et règles configurables."""
    token = await creer_agence(client, nom="Agence Modeles")
    h = auth(token)
    r = await client.get("/api/modeles", headers=h)
    relance = [m for m in r.json()["modeles"] if m["type"] == "relance"][0]
    assert "{nom}" in relance["contenu"]

    r = await client.put("/api/modeles", json={
        "type": "relance", "contenu": "Cher {nom}, merci de payer {reste} FCFA pour {bien} ({periode})."}, headers=h)
    assert r.status_code == 200

    r = await client.get("/api/regles", headers=h)
    assert r.json()["regles"]["caution_max_mois"] == 2  # décret 2023-382 par défaut
    assert r.json()["regles"]["terme_paiement"] == "debut"      # payable d'avance (règle terrain)
    assert r.json()["regles"]["jour_limite_paiement"] == 10     # retard après le 10

    r = await client.patch("/api/regles", json={
        "caution_max_mois": 3, "terme_paiement": "debut", "jour_limite_paiement": 12}, headers=h)
    assert r.status_code == 200
    assert r.json()["regles"]["caution_max_mois"] == 3
    assert r.json()["regles"]["jour_limite_paiement"] == 12
    r = await client.patch("/api/regles", json={"terme_paiement": "nimportequoi"}, headers=h)
    assert r.status_code == 422
    r = await client.patch("/api/regles", json={"jour_limite_paiement": 40}, headers=h)
    assert r.status_code == 422


async def test_profil_agence_et_images(client):
    """F9 : profil agence, logo/tampon/signature pour les quittances."""
    token = await creer_agence(client, nom="Agence Profil")
    h = auth(token)
    r = await client.patch("/api/agence", json={
        "nom": "Nouvelle Agence", "telephone": "338000000", "adresse": "Dakar Plateau"}, headers=h)
    assert r.status_code == 200
    assert r.json()["agence"]["nom"] == "Nouvelle Agence"

    for champ in ("logo", "tampon", "signature"):
        r = await client.post(f"/api/agence/{champ}", headers=h,
                              files={"fichier": ("img.png", io.BytesIO(_jpeg_png()), "image/png")})
        assert r.status_code == 200, r.text
        assert r.json()[f"{champ}_path"]

    # format refusé
    r = await client.post("/api/agence/logo", headers=h,
                          files={"fichier": ("doc.txt", io.BytesIO(b"bonjour"), "text/plain")})
    assert r.status_code == 422


def _jpeg_png() -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (30, 30), (10, 80, 160)).save(buf, "PNG")
    return buf.getvalue()


async def test_quittance_avec_tampon_et_signature(client):
    """La quittance porte logo, signature et tampon (F6)."""
    token = await creer_agence(client, nom="Agence Tamponnée")
    h = auth(token)
    await client.post("/api/agence/tampon", headers=h,
                      files={"fichier": ("t.png", io.BytesIO(_jpeg_png()), "image/png")})
    await client.post("/api/agence/signature", headers=h,
                      files={"fichier": ("s.png", io.BytesIO(_jpeg_png()), "image/png")})
    d = await pepiniere(client, token)
    r = await client.post("/api/baux", json={
        "unite_id": d["unite"]["id"], "locataire_id": d["loc"]["id"],
        "date_debut": date.today().isoformat(), "loyer": 120000, "charges": 0}, headers=h)
    ech = (await client.get(f"/api/baux/{r.json()['bail']['id']}", headers=h)).json()["echeances"][0]
    r = await client.post("/api/paiements", json={"echeance_id": ech["id"], "montant": 120000, "mode": "wave"}, headers=h)
    recu = r.json()["recu"]
    r = await client.get(recu["lien_pdf"], headers=h)
    assert r.status_code == 200
    assert len(r.content) > 8000  # PDF avec images embarquées
