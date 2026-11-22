"""Tests unitaires du calcul économique (src/economie.py).

Ces fonctions transforment un rendement prédit en marge et en seuil de
rentabilité : une erreur ici fausserait toutes les recommandations.
"""

import numpy as np
import pandas as pd
import pytest

from src import economie

CULTURES = ["Maize", "Rice", "Soybean", "Wheat"]


def marge_une(crop, rendement, engrais=0, irrigation=0):
    """Raccourci : marge d'une seule parcelle."""
    return float(economie.marge(pd.Series([crop]), [rendement], pd.Series([engrais]), pd.Series([irrigation]))[0])


def test_hypotheses_completes_et_positives():
    # Chaque culture a un prix, un coût de base et un coût d'engrais strictement positifs
    for table in (economie.PRIX_USD_T, economie.COUT_BASE_USD_HA, economie.COUT_ENGRAIS_USD_HA):
        assert set(table) == set(CULTURES)
        assert all(v > 0 for v in table.values())
    assert economie.COUT_IRRIGATION_USD_HA > 0


def test_marge_formule():
    # marge = rendement x prix - coût de base (sans engrais ni irrigation)
    attendu = 3 * economie.PRIX_USD_T["Wheat"] - economie.COUT_BASE_USD_HA["Wheat"]
    assert marge_une("Wheat", 3) == pytest.approx(attendu)


def test_marge_rendement_nul_egale_moins_les_couts():
    attendu = -(economie.COUT_BASE_USD_HA["Rice"] + economie.COUT_ENGRAIS_USD_HA["Rice"]
                + economie.COUT_IRRIGATION_USD_HA)
    assert marge_une("Rice", 0, engrais=1, irrigation=1) == pytest.approx(attendu)


def test_engrais_et_irrigation_ajoutent_leur_cout():
    base = marge_une("Maize", 4)
    assert base - marge_une("Maize", 4, engrais=1) == pytest.approx(economie.COUT_ENGRAIS_USD_HA["Maize"])
    assert base - marge_une("Maize", 4, irrigation=1) == pytest.approx(economie.COUT_IRRIGATION_USD_HA)


def test_marge_vectorielle_alignee():
    # Plusieurs parcelles en une fois : chaque ligne doit être calculée avec sa propre culture
    crops = pd.Series(CULTURES)
    rendements = np.array([1.0, 2.0, 3.0, 4.0])
    engrais = pd.Series([1, 0, 1, 0])
    irrigation = pd.Series([0, 1, 0, 1])
    vecteur = economie.marge(crops, rendements, engrais, irrigation)
    une_par_une = [marge_une(c, r, f, i) for c, r, f, i in zip(crops, rendements, engrais, irrigation)]
    assert vecteur == pytest.approx(une_par_une)


@pytest.mark.parametrize("crop", CULTURES)
@pytest.mark.parametrize("engrais,irrigation", [(0, 0), (1, 0), (0, 1), (1, 1)])
def test_seuil_rentabilite_annule_la_marge(crop, engrais, irrigation):
    # Au seuil de rentabilité, la marge vaut exactement zéro
    seuil = economie.seuil_rentabilite(crop, engrais, irrigation)
    assert seuil > 0
    assert marge_une(crop, seuil, engrais, irrigation) == pytest.approx(0, abs=1e-9)


def test_hypotheses_pour_mlflow():
    params = economie.hypotheses()
    assert params["prix_usd_t_Rice"] == economie.PRIX_USD_T["Rice"]
    assert "source_prix" in params and "source_couts" in params
