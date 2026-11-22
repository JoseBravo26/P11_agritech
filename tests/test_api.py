"""Tests de l'API (étape 3) : python -m pytest tests -q"""

import pytest
from fastapi.testclient import TestClient

from api.main import app
from src import economie

PARCELLE = {"Rainfall_mm": 600, "Temperature_Celsius": 25, "Pesticides_tonnes": 3270,
            "Fertilizer_Used": True, "Irrigation_Used": False}
CULTURES = {"Maize", "Rice", "Soybean", "Wheat"}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:  # déclenche le chargement du modèle
        yield c


def test_racine_redirige_vers_docs(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert r.headers["location"] == "/docs"


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["statut"] == "ok"
    assert set(body["cultures"]) == CULTURES
    assert 0.7 < body["metriques_test"]["test_r2"] < 0.8


def test_predict_renvoie_un_rendement_plausible(client):
    r = client.post("/predict", json={**PARCELLE, "Crop": "Rice"})
    assert r.status_code == 200
    body = r.json()
    assert body["culture"] == "Rice"
    assert 0 < body["rendement_t_ha"] < 25
    attendu = body["rendement_t_ha"] * economie.PRIX_USD_T["Rice"] - economie.COUT_BASE_USD_HA["Rice"] \
        - economie.COUT_ENGRAIS_USD_HA["Rice"]
    assert body["marge_usd_ha"] == pytest.approx(attendu, abs=1)
    assert body["rentable"] == (body["marge_usd_ha"] > 0)


def test_predict_coherent_avec_recommend(client):
    reco = {c["culture"]: c for c in client.post("/recommend", json=PARCELLE).json()["classement"]}
    for culture in CULTURES:
        pred = client.post("/predict", json={**PARCELLE, "Crop": culture}).json()
        assert pred == reco[culture]


def test_recommend_trie_par_rendement_par_defaut(client):
    r = client.post("/recommend", json=PARCELLE)
    assert r.status_code == 200
    body = r.json()
    assert body["tri"] == "rendement"
    rendements = [c["rendement_t_ha"] for c in body["classement"]]
    assert {c["culture"] for c in body["classement"]} == CULTURES
    assert rendements == sorted(rendements, reverse=True)
    assert body["meilleure_culture"] == body["classement"][0]["culture"]


def test_recommend_tri_par_marge(client):
    body = client.post("/recommend?tri=marge", json=PARCELLE).json()
    marges = [c["marge_usd_ha"] for c in body["classement"]]
    assert marges == sorted(marges, reverse=True)
    assert body["meilleure_culture"] == body["culture_la_plus_rentable"]


def test_l_engrais_augmente_le_rendement(client):
    sans = client.post("/predict", json={**PARCELLE, "Crop": "Wheat", "Fertilizer_Used": False}).json()
    avec = client.post("/predict", json={**PARCELLE, "Crop": "Wheat", "Fertilizer_Used": True}).json()
    assert avec["rendement_t_ha"] > sans["rendement_t_ha"]


@pytest.mark.parametrize("modif", [
    {"Crop": "Banana"},                 # culture inconnue
    {"Temperature_Celsius": 60},        # hors de la plage d'entraînement
    {"Rainfall_mm": -5},
    {"Pesticides_tonnes": "beaucoup"},  # mauvais type
])
def test_predict_refuse_les_entrees_invalides(client, modif):
    r = client.post("/predict", json={**PARCELLE, "Crop": "Rice", **modif})
    assert r.status_code == 422


def test_champ_manquant(client):
    incomplet = {k: v for k, v in PARCELLE.items() if k != "Temperature_Celsius"}
    assert client.post("/recommend", json=incomplet).status_code == 422


def test_tri_invalide(client):
    assert client.post("/recommend?tri=prix", json=PARCELLE).status_code == 422


def test_hypotheses(client):
    body = client.get("/hypotheses").json()
    assert set(body["prix_usd_t"]) == CULTURES
