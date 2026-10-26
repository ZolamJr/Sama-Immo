"""Tests F2-F4, F13 — fiches, baux, échéances automatiques, statuts, alertes de conformité."""
from datetime import date

import pytest
from conftest import auth, creer_agence, pepiniere

pytestmark = pytest.mark.asyncio

DEBUT_3_MOIS = (lambda: date.fromordinal(date.today().toordinal() - 90).isoformat())()


async def test_creer_parcours_complet(client):
    token = await creer_agence(client, nom="Agence Parcours")
    d = await pepiniere(client, token)
    h = auth(token)

    # bail : caution 2 mois -> pas d'alerte ; 500k caution / loyer 250k = 2 mois pile
    r = await client.post("/api/baux", json={
        "unite_id": d["unite"]["id"], "locataire_id": d["loc"]["id"],
        "date_debut": DEBUT_3_MOIS, "loyer": 250000, "charges": 10000,
        "jour_echeance": 5, "caution": 500000, "duree_type": "triennale"}, headers=h)
    assert r.status_code == 200, r.text
    bail = r.json()["bail"]
    assert bail["statut"] == "actif"
    assert r.json()["alertes"] == []  # 2 mois de loyer = conforme

    # l'unité passe en occupée
    r = await client.get("/api/unites", headers=h)
    unite = [u for u in r.json()["unites"] if u["id"] == d["unite"]["id"]][0]
    assert unite["statut"] == "occupe"
    assert unite["bail_actif"]["locataire_nom"] == "Aïssatou Ndiaye"

    # une seule échéance par période (génération idempotente), et rattrapage des mois passés
    r = await client.get("/api/dashboard", headers=h)
    assert r.status_code == 200
    r2 = await client.get("/api/dashboard", headers=h)
    assert r.json()["nb_echeances"] == r2.json()["nb_echeances"]  # pas de doublon au 2e appel
    assert r.json()["nb_echeances"] == 1  # le dashboard ne compte que le mois courant
    r = await client.get(f"/api/baux/{bail['id']}", headers=h)
    assert len(r.json()["echeances"]) >= 3  # mais le rattrapage des mois passés est fait


async def test_statuts_et_dashboard(client):
    token = await creer_agence(client, nom="Agence Statuts")
    d = await pepiniere(client, token)
    h = auth(token)

    r = await client.post("/api/baux", json={
        "unite_id": d["unite"]["id"], "locataire_id": d["loc"]["id"],
        "date_debut": DEBUT_3_MOIS, "loyer": 200000, "charges": 0,
        "jour_echeance": 5, "caution": 400000}, headers=h)
    bail_id = r.json()["bail"]["id"]

    r = await client.get(f"/api/baux/{bail_id}", headers=h)
    eches = r.json()["echeances"]
    assert len(eches) >= 3
    # toute échéance dont la date limite est passée et non soldée est en retard
    today = date.today().isoformat()
    for e in eches:
        if (e["date_limite"] or e["date_echeance"]) < today:
            assert e["statut"] == "en_retard"
        assert e["montant_du"] == 200000
        # payable d'avance : attendu le 5, retard après le 10
        assert e["date_echeance"].endswith("-05")
        assert e["date_limite"].endswith("-10")

    # un paiement partiel sur l'échéance courante
    from app.logique import periode_courante
    ech_courante = [e for e in eches if e["periode"] == periode_courante()][0]
    r = await client.post("/api/paiements", json={
        "echeance_id": ech_courante["id"], "montant": 50000, "mode": "wave"}, headers=h)
    assert r.status_code == 200, r.text

    # le dashboard reflète exactement la répartition calculée depuis les échéances (fraîches)
    from app.logique import statut_echeance
    eches = (await client.get(f"/api/baux/{bail_id}", headers=h)).json()["echeances"]
    r = await client.get("/api/dashboard", headers=h)
    dash = r.json()
    assert dash["encaisse"] == 50000
    assert dash["occupation"]["taux"] == 100
    attendu_attente, attendu_retard = 0, 0
    for e in eches:
        st = statut_echeance(e["montant_du"], e["montant_paye"],
                             date.fromisoformat(e["date_echeance"]), date.today(),
                             date.fromisoformat(e["date_limite"]) if e["date_limite"] else None)
        if st == "en_retard":
            attendu_retard += e["reste"]
        elif st in ("en_attente", "partiel"):
            attendu_attente += e["reste"]
    assert dash["en_attente"] == attendu_attente
    assert dash["en_retard"] == attendu_retard
    assert attendu_attente + attendu_retard == 200000 * len(eches) - 50000


async def test_statut_echeance_limites():
    """Frontières de la règle « payable d'avance, attendu le 5, retard après le 10 »."""
    from app.logique import statut_echeance as st
    assert st(100, 100, date(2026, 10, 5), date(2026, 10, 1), date(2026, 10, 10)) == "paye"
    assert st(100, 40, date(2026, 10, 5), date(2026, 10, 7), date(2026, 10, 10)) == "partiel"
    # le 10, dernier jour de tolérance : pas encore en retard
    assert st(100, 0, date(2026, 10, 5), date(2026, 10, 10), date(2026, 10, 10)) == "en_attente"
    # le 11 : en retard
    assert st(100, 0, date(2026, 10, 5), date(2026, 10, 11), date(2026, 10, 10)) == "en_retard"
    # le retard l'emporte sur le partiel
    assert st(100, 40, date(2026, 10, 5), date(2026, 10, 11), date(2026, 10, 10)) == "en_retard"


async def test_dates_echeance_avance(client):
    """Loyer payable d'avance : attendu le 5 du mois, retard après le 10.
    Premier loyer d'un bail signé le 20 : dû à la signature, retard le 10 du mois suivant."""
    token = await creer_agence(client, nom="Agence Avance")
    d = await pepiniere(client, token)
    h = auth(token)
    r = await client.post("/api/baux", json={
        "unite_id": d["unite"]["id"], "locataire_id": d["loc"]["id"],
        "date_debut": "2026-09-20", "loyer": 150000, "charges": 0,
        "jour_echeance": 5}, headers=h)
    assert r.status_code == 200
    bail_id = r.json()["bail"]["id"]
    eches = (await client.get(f"/api/baux/{bail_id}", headers=h)).json()["echeances"]
    par = {e["periode"]: e for e in eches}
    # premier mois (bail signé le 20, après le jour d'échéance) : loyer dû à la signature
    assert par["2026-09"]["date_echeance"] == "2026-09-20"
    assert par["2026-09"]["date_limite"] == "2026-10-10"
    # mois suivants : payable d'avance, attendu le 5, retard après le 10
    assert par["2026-10"]["date_echeance"] == "2026-10-05"
    assert par["2026-10"]["date_limite"] == "2026-10-10"


async def test_alerte_caution_superieure(client):
    """Alerte douce (jamais bloquante) si caution > règle paramétrée (F13)."""
    token = await creer_agence(client, nom="Agence Caution")
    d = await pepiniere(client, token)
    h = auth(token)
    r = await client.post("/api/baux", json={
        "unite_id": d["unite"]["id"], "locataire_id": d["loc"]["id"],
        "date_debut": date.today().isoformat(), "loyer": 150000, "charges": 0,
        "caution": 600000}, headers=h)  # 4 mois de loyer !
    assert r.status_code == 200  # jamais bloquant
    assert len(r.json()["alertes"]) == 1
    assert "caution" in r.json()["alertes"][0].lower() or "2 mois" in r.json()["alertes"][0]


async def test_unite_occree_refuse_double_bail(client):
    token = await creer_agence(client)
    d = await pepiniere(client, token)
    h = auth(token)
    r = await client.post("/api/baux", json={
        "unite_id": d["unite"]["id"], "locataire_id": d["loc"]["id"],
        "date_debut": date.today().isoformat(), "loyer": 100000, "charges": 0}, headers=h)
    assert r.status_code == 200
    r = await client.post("/api/locataires", json={"nom": "Second Loc", "telephone": "778889900"}, headers=h)
    loc2 = r.json()["locataire"]
    r = await client.post("/api/baux", json={
        "unite_id": d["unite"]["id"], "locataire_id": loc2["id"],
        "date_debut": date.today().isoformat(), "loyer": 100000, "charges": 0}, headers=h)
    assert r.status_code == 422


async def test_terminer_bail_libere_unite(client):
    token = await creer_agence(client)
    d = await pepiniere(client, token)
    h = auth(token)
    r = await client.post("/api/baux", json={
        "unite_id": d["unite"]["id"], "locataire_id": d["loc"]["id"],
        "date_debut": date.today().isoformat(), "loyer": 120000, "charges": 0}, headers=h)
    bail_id = r.json()["bail"]["id"]
    r = await client.post(f"/api/baux/{bail_id}/terminer", json={"motif": "Départ du locataire"}, headers=h)
    assert r.status_code == 200
    assert r.json()["bail"]["statut"] == "termine"
    r = await client.get("/api/unites", headers=h)
    unite = [u for u in r.json()["unites"] if u["id"] == d["unite"]["id"]][0]
    assert unite["statut"] == "libre"


async def test_historique_loyer(client):
    """Changement de loyer : historique conservé, échéances à jour, passées intactes (F13)."""
    from app.logique import periode_courante, periode_precedente
    token = await creer_agence(client)
    d = await pepiniere(client, token)
    h = auth(token)
    r = await client.post("/api/baux", json={
        "unite_id": d["unite"]["id"], "locataire_id": d["loc"]["id"],
        "date_debut": DEBUT_3_MOIS, "loyer": 100000, "charges": 0}, headers=h)
    bail_id = r.json()["bail"]["id"]

    r = await client.patch(f"/api/baux/{bail_id}", json={
        "loyer": 130000, "motif_loyer": "Révision annuelle"}, headers=h)
    assert r.status_code == 200
    r = await client.get(f"/api/baux/{bail_id}", headers=h)
    hist = r.json()["historique_loyer"]
    assert [x["loyer"] for x in hist] == [100000, 130000]
    eches = {e["periode"]: e for e in r.json()["echeances"]}
    assert eches[periode_courante()]["montant_du"] == 130000
    assert eches[periode_precedente(periode_courante())]["montant_du"] == 100000  # passée intacte


async def test_isolation_entre_agences(client):
    """Séparation stricte des données entre agences (§7)."""
    t1 = await creer_agence(client, nom="Agence A")
    t2 = await creer_agence(client, nom="Agence B")
    d = await pepiniere(client, t1)
    h2 = auth(t2)

    r = await client.get("/api/locataires", headers=h2)
    assert r.json()["locataires"] == []
    r = await client.get(f"/api/locataires/{d['loc']['id']}", headers=h2)
    assert r.status_code == 404
    r = await client.get(f"/api/proprietaires/{d['prop']['id']}", headers=h2)
    assert r.status_code == 404
    r = await client.delete(f"/api/locataires/{d['loc']['id']}", headers=h2)
    assert r.status_code == 404
