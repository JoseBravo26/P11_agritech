"""Tests de l'interface Streamlit (étape 4) : python -m pytest tests -q

L'API est simulée : on vérifie ce que l'interface envoie et ce qu'elle affiche,
sans lancer de serveur.
"""

import json
from pathlib import Path

import pytest
import requests
import streamlit as st
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / "frontend" / "app.py")

SANTE = {"statut": "ok", "metriques_test": {"test_r2": 0.76, "test_mae": 0.68}}
PREDICTION = {"culture": "Maize", "rendement_t_ha": 2.266, "marge_usd_ha": 130.3,
              "seuil_rentabilite_t_ha": 1.625, "rentable": True}
RECOMMANDATION = {
    "tri": "rendement", "meilleure_culture": "Rice", "culture_la_plus_rentable": "Rice",
    "classement": [
        {"culture": "Rice", "rendement_t_ha": 5.287, "marge_usd_ha": 654.9, "seuil_rentabilite_t_ha": 2.89, "rentable": True},
        {"culture": "Wheat", "rendement_t_ha": 2.356, "marge_usd_ha": 263.3, "seuil_rentabilite_t_ha": 1.274, "rentable": True},
        {"culture": "Maize", "rendement_t_ha": 2.266, "marge_usd_ha": 130.3, "seuil_rentabilite_t_ha": 1.625, "rentable": True},
        {"culture": "Soybean", "rendement_t_ha": 1.649, "marge_usd_ha": 426.3, "seuil_rentabilite_t_ha": 0.62, "rentable": True},
    ],
}


class FausseReponse:
    def __init__(self, status_code, data):
        self.status_code, self._data = status_code, data
        self.ok = status_code < 400
        self.text = str(data)

    def json(self):
        return self._data


@pytest.fixture
def api(monkeypatch):
    """Remplace requests.request ; enregistre les appels reçus."""
    appels, reponses = [], {"/health": FausseReponse(200, SANTE),
                            "/predict": FausseReponse(200, PREDICTION),
                            "/recommend": FausseReponse(200, RECOMMANDATION)}

    def fausse_requete(methode, url, **kwargs):
        chemin = "/" + url.split("/", 3)[-1]
        appels.append({"methode": methode, "chemin": chemin, **kwargs})
        rep = reponses[chemin]
        if isinstance(rep, Exception):
            raise rep
        return rep

    monkeypatch.setattr(requests, "request", fausse_requete)
    st.cache_data.clear()  # l'état de l'API est mis en cache : chaque test repart de zéro
    return {"appels": appels, "reponses": reponses}


def lancer() -> AppTest:
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    assert not at.exception
    return at


def bouton_envoi(at):
    return next(b for b in at.button if b.label.startswith("Lancer"))


def envoi_vers(api, chemin):
    return next(a for a in api["appels"] if a["chemin"] == chemin)


def test_page_initiale_sans_appel_de_prediction(api):
    at = lancer()
    assert any("API connectée" in s.value for s in at.sidebar.success)
    assert [a["chemin"] for a in api["appels"]] == ["/health"]
    assert at.info  # invite à cliquer sur le bouton


def test_mode_prediction_affiche_un_chiffre_clair(api):
    at = lancer()
    bouton_envoi(at).click().run()
    envoi = envoi_vers(api, "/predict")
    assert envoi["methode"] == "POST"
    assert envoi["json"] == {"Rainfall_mm": 600, "Temperature_Celsius": 25.0, "Pesticides_tonnes": 3270,
                             "Fertilizer_Used": True, "Irrigation_Used": False, "Crop": "Maize"}
    assert [m.value for m in at.metric] == ["2.27 t/ha", "130 USD/ha", "1.62 t/ha"]
    assert at.success


def test_mode_recommandation_affiche_graphique_et_tableau(api):
    at = lancer()
    at.sidebar.radio[0].set_value("Recommandation").run()
    bouton_envoi(at).click().run()
    envoi = envoi_vers(api, "/recommend")
    assert envoi["params"] == {"tri": "rendement"}
    assert "Crop" not in envoi["json"]
    tableau = at.dataframe[0].value
    assert list(tableau["Culture"]) == ["Riz", "Blé", "Maïs", "Soja"]
    assert list(tableau["Rang"]) == [1, 2, 3, 4]
    assert at.get("vega_lite_chart")  # graphique à barres (Altair)
    assert "Riz" in at.success[0].value


def test_tri_par_marge_transmis_a_l_api(api):
    at = lancer()
    at.sidebar.radio[0].set_value("Recommandation").run()
    next(r for r in at.main.radio if r.label.startswith("Classer")).set_value("marge")
    bouton_envoi(at).click().run()
    assert envoi_vers(api, "/recommend")["params"] == {"tri": "marge"}


def liste(at, debut_libelle):
    return next(s for s in at.selectbox if s.label.startswith(debut_libelle))


def test_niveau_de_pesticides_personnalise(api):
    at = lancer()
    liste(at, "Niveau d'intensification").set_value("Valeur personnalisée")
    at.number_input[0].set_value(50_000)
    bouton_envoi(at).click().run()
    assert envoi_vers(api, "/predict")["json"]["Pesticides_tonnes"] == 50_000


def test_choix_du_pays_fixe_les_pesticides(api):
    # L'agriculteur choisit son pays : la valeur nationale de pesticides (FAO) est retrouvée seule
    table = json.loads((Path(APP).with_name("pays_pesticides.json")).read_text(encoding="utf-8"))
    at = lancer()
    liste(at, "Pays de l'exploitation").set_value("France").run()
    assert not any(s.label.startswith("Niveau d'intensification") for s in at.selectbox)  # menu des niveaux masqué
    assert any("France" in i.value for i in at.info)
    bouton_envoi(at).click().run()
    assert envoi_vers(api, "/predict")["json"]["Pesticides_tonnes"] == table["France"]["pesticides_tonnes"]


def test_erreur_422_affichee_lisiblement(api):
    api["reponses"]["/predict"] = FausseReponse(422, {"detail": [
        {"loc": ["body", "Temperature_Celsius"], "msg": "Input should be less than or equal to 40"}]})
    at = lancer()
    bouton_envoi(at).click().run()
    assert not at.exception
    assert "Temperature_Celsius" in at.main.error[0].value
    assert not at.metric


def test_api_injoignable(api):
    for chemin in ("/health", "/predict"):
        api["reponses"][chemin] = requests.ConnectionError()
    at = lancer()
    assert "Impossible de joindre l'API" in at.sidebar.error[0].value
    bouton_envoi(at).click().run()
    assert not at.exception
    assert any("Impossible de joindre l'API" in e.value for e in at.main.error)
