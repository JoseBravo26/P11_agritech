"""Étape 3 : API de prédiction du rendement et de recommandation de cultures.

Le modèle entraîné à l'étape 2 (models/modele_rendement.joblib) est chargé une
seule fois au démarrage. Deux fonctions métier sont exposées :

- POST /predict   : rendement attendu (t/ha) d'une culture donnée sur une parcelle ;
- POST /recommend : toutes les cultures simulées sur la parcelle, classées par
                    rendement prédit décroissant (ou par marge, avec ?tri=marge).

La marge est calculée après la prédiction avec les hypothèses de src/economie.py
(prix Banque mondiale, coûts USDA ajustés) : les changer ne demande pas de
réentraîner le modèle.

Lancement local (depuis la racine du projet) :
    uvicorn api.main:app --reload
Documentation interactive : http://127.0.0.1:8000/docs
"""

import json
import os
from contextlib import asynccontextmanager
from enum import Enum
from pathlib import Path
from typing import Literal

import joblib
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, Field

from src import economie

ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = Path(os.environ.get("MODEL_PATH", ROOT / "models" / "modele_rendement.joblib"))
MODEL_CARD_PATH = MODEL_PATH.with_suffix(".json")


class Culture(str, Enum):
    """Cultures connues du modèle (communes aux deux jeux de données)."""

    maize = "Maize"
    rice = "Rice"
    soybean = "Soybean"
    wheat = "Wheat"


# --------------------------------------------------------------------------- schémas

class ContexteParcelle(BaseModel):
    """Conditions de la parcelle. Les bornes sont celles du jeu d'entraînement :
    hors de ces plages, le modèle extrapolerait sans garantie."""

    model_config = ConfigDict(json_schema_extra={"example": {
        "Rainfall_mm": 600, "Temperature_Celsius": 25, "Pesticides_tonnes": 3270,
        "Fertilizer_Used": True, "Irrigation_Used": False,
    }})

    Rainfall_mm: float = Field(..., ge=100, le=1000, description="Pluie sur la saison de culture (mm)")
    Temperature_Celsius: float = Field(..., ge=15, le=40, description="Température moyenne (°C)")
    Pesticides_tonnes: float = Field(
        ..., ge=0, le=400_000,
        description="Usage national de pesticides (tonnes), indicateur du niveau d'intensification "
                    "de l'agriculture du pays. Médiane du jeu de données : 3 270.")
    Fertilizer_Used: bool = Field(..., description="Engrais appliqué")
    Irrigation_Used: bool = Field(..., description="Parcelle irriguée")


class EntreePrediction(ContexteParcelle):
    model_config = ConfigDict(json_schema_extra={"example": {
        "Crop": "Rice", "Rainfall_mm": 600, "Temperature_Celsius": 25, "Pesticides_tonnes": 3270,
        "Fertilizer_Used": True, "Irrigation_Used": False,
    }})

    Crop: Culture = Field(..., description="Culture envisagée")


class ResultatCulture(BaseModel):
    culture: Culture
    rendement_t_ha: float = Field(..., description="Rendement prédit (tonnes par hectare)")
    marge_usd_ha: float = Field(..., description="Marge estimée sur coûts opérationnels (USD/ha)")
    seuil_rentabilite_t_ha: float = Field(..., description="Rendement minimal pour couvrir les coûts (t/ha)")
    rentable: bool


class ReponseRecommandation(BaseModel):
    tri: Literal["rendement", "marge"]
    meilleure_culture: Culture = Field(..., description="Première culture du classement")
    culture_la_plus_rentable: Culture = Field(..., description="Culture de marge maximale")
    classement: list[ResultatCulture]


# --------------------------------------------------------------------------- modèle

state: dict = {}


@asynccontextmanager
async def lifespan(_: FastAPI):
    if not MODEL_PATH.exists():
        raise RuntimeError(f"Modèle introuvable : {MODEL_PATH}. Lancez d'abord l'étape 2.")
    state["model"] = joblib.load(MODEL_PATH)
    card = json.loads(MODEL_CARD_PATH.read_text(encoding="utf-8")) if MODEL_CARD_PATH.exists() else {}
    state["features"] = card.get("features", ["Crop", "Rainfall_mm", "Temperature_Celsius",
                                              "Pesticides_tonnes", "Fertilizer_Used", "Irrigation_Used"])
    state["card"] = card
    yield
    state.clear()


app = FastAPI(
    title="Agritech Answers – API de recommandation de cultures",
    description="Prédit le rendement d'une culture et classe les cultures pour une parcelle donnée.",
    version="1.0.0",
    lifespan=lifespan,
)


def _evaluer(cultures: list[str], contexte: ContexteParcelle) -> pd.DataFrame:
    """Prédit rendement, marge et seuil de rentabilité pour chaque culture demandée."""
    conditions = contexte.model_dump()
    frame = pd.DataFrame([{**conditions, "Crop": c} for c in cultures])
    frame[["Fertilizer_Used", "Irrigation_Used"]] = frame[["Fertilizer_Used", "Irrigation_Used"]].astype(int)
    frame["rendement_t_ha"] = state["model"].predict(frame[state["features"]]).clip(min=0)
    frame["marge_usd_ha"] = economie.marge(frame["Crop"], frame["rendement_t_ha"],
                                           frame["Fertilizer_Used"], frame["Irrigation_Used"])
    frame["seuil_rentabilite_t_ha"] = [
        economie.seuil_rentabilite(c, int(f), int(i))
        for c, f, i in zip(frame["Crop"], frame["Fertilizer_Used"], frame["Irrigation_Used"])
    ]
    return frame


def _resultat(row) -> ResultatCulture:
    return ResultatCulture(
        culture=row["Crop"],
        rendement_t_ha=round(float(row["rendement_t_ha"]), 3),
        marge_usd_ha=round(float(row["marge_usd_ha"]), 1),
        seuil_rentabilite_t_ha=round(float(row["seuil_rentabilite_t_ha"]), 3),
        rentable=bool(row["marge_usd_ha"] > 0),
    )


# --------------------------------------------------------------------------- endpoints

@app.get("/", include_in_schema=False)
def accueil() -> RedirectResponse:
    """La racine renvoie vers la documentation interactive."""
    return RedirectResponse(url="/docs")


@app.get("/health", tags=["service"])
def health() -> dict:
    """État du service et performance du modèle chargé (jeu de test de l'étape 2)."""
    if "model" not in state:
        raise HTTPException(status_code=503, detail="Modèle non chargé")
    metrics = state["card"].get("metriques_test", {})
    return {
        "statut": "ok",
        "cultures": [c.value for c in Culture],
        "variables": state["features"],
        "mlflow_run_id": state["card"].get("mlflow_run_id"),
        "metriques_test": {k: metrics[k] for k in ("test_rmse", "test_mae", "test_r2",
                                                   "test_precision_rentabilite") if k in metrics},
    }


@app.get("/hypotheses", tags=["service"])
def hypotheses() -> dict:
    """Prix et coûts utilisés pour calculer les marges (voir src/economie.py)."""
    return {
        "prix_usd_t": economie.PRIX_USD_T,
        "cout_base_usd_ha": economie.COUT_BASE_USD_HA,
        "cout_engrais_usd_ha": economie.COUT_ENGRAIS_USD_HA,
        "cout_irrigation_usd_ha": economie.COUT_IRRIGATION_USD_HA,
        "sources": {"prix": "Banque mondiale, Pink Sheet, moyenne 2025",
                    "couts": "USDA ERS 2025, ajustés au rendement moyen du jeu de données",
                    "irrigation": "ordre de grandeur illustratif, non sourcé"},
    }


@app.post("/predict", response_model=ResultatCulture, tags=["prédiction"])
def predict(entree: EntreePrediction) -> ResultatCulture:
    """Rendement attendu d'une culture donnée sur la parcelle décrite."""
    contexte = ContexteParcelle(**entree.model_dump(exclude={"Crop"}))
    frame = _evaluer([entree.Crop.value], contexte)
    return _resultat(frame.iloc[0])


@app.post("/recommend", response_model=ReponseRecommandation, tags=["recommandation"])
def recommend(
    contexte: ContexteParcelle,
    tri: Literal["rendement", "marge"] = Query(
        "rendement", description="Critère de classement : rendement prédit (t/ha) ou marge estimée (USD/ha)"),
) -> ReponseRecommandation:
    """Simule toutes les cultures sur la parcelle et les classe par ordre décroissant."""
    frame = _evaluer([c.value for c in Culture], contexte)
    colonne = "rendement_t_ha" if tri == "rendement" else "marge_usd_ha"
    frame = frame.sort_values(colonne, ascending=False).reset_index(drop=True)
    return ReponseRecommandation(
        tri=tri,
        meilleure_culture=frame.loc[0, "Crop"],
        culture_la_plus_rentable=frame.loc[frame["marge_usd_ha"].idxmax(), "Crop"],
        classement=[_resultat(row) for _, row in frame.iterrows()],
    )
