"""Tests du modèle enregistré (models/modele_rendement.joblib).

Ils vérifient que le fichier livré avec l'API est lisible, cohérent avec sa
fiche et qu'il donne des prédictions plausibles et stables.
"""

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest

MODELS = Path(__file__).resolve().parents[1] / "models"
CULTURES = ["Maize", "Rice", "Soybean", "Wheat"]


@pytest.fixture(scope="module")
def modele():
    return joblib.load(MODELS / "modele_rendement.joblib")


@pytest.fixture(scope="module")
def fiche():
    return json.loads((MODELS / "modele_rendement.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def grille(fiche):
    # Toutes les combinaisons de conditions aux bornes et au centre des plages d'entraînement
    lignes = [{"Crop": c, "Rainfall_mm": r, "Temperature_Celsius": t, "Pesticides_tonnes": p,
               "Fertilizer_Used": f, "Irrigation_Used": i}
              for c in CULTURES for r in (100, 600, 1000) for t in (15, 25, 40)
              for p in (0, 3270, 400_000) for f in (0, 1) for i in (0, 1)]
    return pd.DataFrame(lignes)[fiche["features"]]


def test_fichier_sous_la_limite_github():
    # GitHub refuse les fichiers de plus de 100 Mo : le pipeline CI/CD en dépend
    assert (MODELS / "modele_rendement.joblib").stat().st_size < 100 * 1024 ** 2


def test_fiche_coherente(fiche):
    assert set(fiche["features"]) == {"Crop", "Rainfall_mm", "Temperature_Celsius", "Pesticides_tonnes",
                                      "Fertilizer_Used", "Irrigation_Used"}
    assert 0.7 < fiche["metriques_test"]["test_r2"] < 0.8
    assert fiche["mlflow_run_id"]


def test_predictions_plausibles(modele, grille):
    pred = modele.predict(grille)
    assert np.isfinite(pred).all()
    assert pred.min() >= 0          # un rendement n'est jamais négatif
    assert pred.max() < 25          # aucune valeur aberrante (t/ha)


def test_predictions_deterministes(modele, grille):
    # Les arbres sont calculés en parallèle : l'ordre des additions peut varier,
    # d'où des écarts d'arrondi de l'ordre de 1e-15. On tolère 1e-9 t/ha.
    np.testing.assert_allclose(modele.predict(grille), modele.predict(grille), rtol=0, atol=1e-9)


def test_engrais_augmente_le_rendement_en_moyenne(modele, grille):
    sans = modele.predict(grille[grille["Fertilizer_Used"] == 0])
    avec = modele.predict(grille[grille["Fertilizer_Used"] == 1])
    assert avec.mean() > sans.mean()
