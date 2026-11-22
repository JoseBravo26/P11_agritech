"""Étape 2 : entraînement, optimisation et sélection du modèle de rendement.

Pipeline (détaillé dans notebooks/02_modelisation.ipynb) :
1. Préparation : encodage one-hot des catégorielles, log des pesticides,
   standardisation, ajustés à l'intérieur de chaque pli (pas de fuite de données).
2. Comparaison de modèles en validation croisée sur le jeu d'entraînement.
3. Optimisation des hyperparamètres du meilleur modèle (recherche aléatoire).
4. Évaluation unique sur un jeu de test séparé, puis enregistrement du modèle.
Chaque étape est tracée dans MLflow : paramètres, métriques, figures, notes.

Usage : python -m src.entrainement
Interface MLflow : mlflow ui --backend-store-uri sqlite:///mlflow.db
"""

import json
import pickle
import time
from pathlib import Path

import joblib
import matplotlib.pyplot as plt
import mlflow
import numpy as np
import pandas as pd
from scipy.stats import loguniform
from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.inspection import permutation_importance
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GroupKFold, GroupShuffleSplit, ParameterSampler
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder, StandardScaler

from src import economie
from src import preparation_donnees as prep

ROOT = prep.ROOT
DATA_PATH = prep.OUTPUT_PATH
TARGET = prep.TARGET
CROPS = prep.COMMON_CROPS
MODEL_DIR = ROOT / "models"

SEED = 42
TEST_SIZE = 0.2
CV_FOLDS = 3
CV_SAMPLE = 150_000  # parcelles tirées du jeu d'entraînement pour la validation croisée
N_ITER = 20  # configurations testées lors de l'optimisation
# Perte de RMSE relative acceptée pour retenir le modèle à variables réduites
PARSIMONY_TOLERANCE = 0.01

EXPERIMENT = "P11_rendement_cultures"
TRACKING_URI = "sqlite:///" + (ROOT / "mlflow.db").as_posix()
ARTIFACT_ROOT = ROOT / "mlruns"
REGISTERED_MODEL = "rendement_cultures"
TRUSTED_TREE_TYPES = [
    "sklearn.tree._tree.Tree",
    "sklearn.ensemble._hist_gradient_boosting.predictor.TreePredictor",
]

CATEGORICAL = ["Crop", "Region", "Soil_Type", "Weather_Condition"]
NUMERIC = ["Rainfall_mm", "Temperature_Celsius", "Days_to_Harvest"]
LOG_NUMERIC = ["Pesticides_tonnes"]  # s'étale sur 7 ordres de grandeur
BINARY = ["Fertilizer_Used", "Irrigation_Used"]
FEATURES_ALL = CATEGORICAL + NUMERIC + LOG_NUMERIC + BINARY
# Variables ayant un effet à l'étape 1 ; les autres (région, sol, météo, durée) n'en montraient aucun
FEATURES_CLES = ["Crop", "Rainfall_mm", "Temperature_Celsius", "Pesticides_tonnes", "Fertilizer_Used", "Irrigation_Used"]

# Espaces de recherche des hyperparamètres, par famille de modèle
TUNING_SPACES = {
    "HistGradientBoostingRegressor": {
        "model__learning_rate": loguniform(0.02, 0.3),
        "model__max_iter": [200, 400, 800],
        "model__max_leaf_nodes": [15, 31, 63, 127],
        "model__min_samples_leaf": [20, 50, 100, 200],
        "model__l2_regularization": loguniform(1e-3, 10),
        "model__max_features": [0.5, 0.8, 1.0],
    },
    # Bornée pour que le modèle reste déployable (taille en mémoire de l'API)
    "RandomForestRegressor": {
        "model__max_depth": [None, 12, 20],
        "model__min_samples_leaf": [20, 50, 100],
        "model__max_features": [0.3, 0.6, 1.0],
        "model__max_samples": [0.3, 0.5],
    },
}


# --------------------------------------------------------------------------- données

def load_data(path: Path = DATA_PATH) -> pd.DataFrame:
    return pd.read_csv(path)


def donor_groups(df: pd.DataFrame) -> pd.Series:
    """Identifiant approché du donneur FAO (pays x année) de chaque parcelle.

    Les pesticides sont un total national propre à chaque pays-année : avec la culture,
    leur valeur exacte désigne presque le donneur. Sans regroupement, des parcelles d'un
    même donneur se retrouvent à la fois en entraînement et en test, et le modèle peut
    « reconnaître » le donneur au lieu d'apprendre l'effet des conditions : la
    performance mesurée serait trop optimiste. On sépare donc par donneur.
    """
    return df["Crop"] + "_" + df["Pesticides_tonnes"].astype(str)


def split(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Jeu de test mis de côté une fois pour toutes : des donneurs (pays-années) jamais vus."""
    train_idx, test_idx = next(GroupShuffleSplit(n_splits=1, test_size=TEST_SIZE, random_state=SEED)
                               .split(df, groups=donor_groups(df)))
    return df.iloc[train_idx].reset_index(drop=True), df.iloc[test_idx].reset_index(drop=True)


def build_pipeline(estimator, features: list[str]) -> Pipeline:
    """Préparation + modèle dans un seul objet : la préparation est ajustée sur
    les seules données d'entraînement et le modèle s'utilise sur des données brutes."""
    prep_steps = ColumnTransformer(
        [
            ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), [c for c in CATEGORICAL if c in features]),
            ("log", make_pipeline(FunctionTransformer(np.log1p, feature_names_out="one-to-one"), StandardScaler()),
             [c for c in LOG_NUMERIC if c in features]),
            ("num", StandardScaler(), [c for c in NUMERIC if c in features]),
            ("bin", "passthrough", [c for c in BINARY if c in features]),
        ],
        verbose_feature_names_out=False,
    )
    return Pipeline([("prep", prep_steps), ("model", estimator)])


def candidate_models() -> dict:
    return {
        "Baseline (moyenne)": DummyRegressor(),
        "Regression Ridge": Ridge(alpha=1.0),
        # Feuilles d'au moins 20 parcelles : avec des feuilles de 1, la forêt pèserait ~5 Go,
        # inutilisable dans l'API ; ici ~100 Mo
        "Foret aleatoire": RandomForestRegressor(
            n_estimators=100, min_samples_leaf=20, max_samples=0.5, n_jobs=-1, random_state=SEED
        ),
        "Gradient boosting (HGB)": HistGradientBoostingRegressor(random_state=SEED),
    }


# --------------------------------------------------------------------------- métriques

def evaluate(frame: pd.DataFrame, y_true, y_pred) -> dict:
    """Métriques statistiques (t/ha) et économiques (USD/ha)."""
    y_true, y_pred = np.asarray(y_true), np.asarray(y_pred)
    crop, fert, irr = frame["Crop"], frame["Fertilizer_Used"], frame["Irrigation_Used"]
    marge_true = economie.marge(crop, y_true, fert, irr)
    marge_pred = economie.marge(crop, y_pred, fert, irr)
    return {
        "rmse": float(np.sqrt(mean_squared_error(y_true, y_pred))),
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "r2": float(r2_score(y_true, y_pred)),
        # Erreur sur la marge : une erreur sur le soja (420 USD/t) coûte plus qu'une erreur sur le maïs
        "rmse_marge_usd_ha": float(np.sqrt(mean_squared_error(marge_true, marge_pred))),
        # Part des parcelles correctement classées rentables / non rentables
        "precision_rentabilite": float(np.mean((marge_true > 0) == (marge_pred > 0))),
    }


def cross_validate(pipeline: Pipeline, frame: pd.DataFrame, features: list[str]) -> dict:
    folds = GroupKFold(CV_FOLDS, shuffle=True, random_state=SEED).split(frame, groups=donor_groups(frame))
    scores, start = [], time.perf_counter()
    for train_idx, valid_idx in folds:
        fitted = clone(pipeline).fit(frame.iloc[train_idx][features], frame.iloc[train_idx][TARGET])
        valid = frame.iloc[valid_idx]
        scores.append(evaluate(valid, valid[TARGET], fitted.predict(valid[features])))
    scores = pd.DataFrame(scores)
    out = {f"cv_{k}": float(v) for k, v in scores.mean().items()}
    out |= {f"cv_{k}_std": float(v) for k, v in scores.std().items()}
    out["duree_cv_s"] = time.perf_counter() - start
    return out


# --------------------------------------------------------------------------- MLflow

def setup_mlflow() -> None:
    mlflow.set_tracking_uri(TRACKING_URI)
    if mlflow.get_experiment_by_name(EXPERIMENT) is None:
        mlflow.create_experiment(
            EXPERIMENT,
            artifact_location=ARTIFACT_ROOT.as_uri(),
            tags={"projet": "P11 Agritech Answers", "mlflow.note.content":
                  "Prédiction du rendement (t/ha) de 4 cultures à partir du dataset consolidé de l'étape 1."},
        )
    mlflow.set_experiment(EXPERIMENT)


def _simple_params(estimator) -> dict:
    return {k: v for k, v in estimator.get_params().items() if isinstance(v, (int, float, str, bool, type(None)))}


def _log_common(features: list[str], n_rows: int) -> None:
    mlflow.log_params({"seed": SEED, "jeu_variables": ",".join(features), "n_variables": len(features), "n_lignes": n_rows})


# --------------------------------------------------------------------------- étapes

def compare_models(train: pd.DataFrame) -> pd.DataFrame:
    """Étape A : modèles candidats en validation croisée, puis variante à variables réduites du meilleur."""
    sample = train.sample(min(CV_SAMPLE, len(train)), random_state=SEED)
    results = {}

    def run(name, estimator, features, note):
        with mlflow.start_run(run_name=name, nested=True):
            _log_common(features, len(sample))
            mlflow.log_params({"modele": type(estimator).__name__, "cv_folds": CV_FOLDS} | _simple_params(estimator))
            metrics = cross_validate(build_pipeline(estimator, features), sample, features)
            mlflow.log_metrics(metrics)
            mlflow.set_tag("mlflow.note.content", note.format(**metrics))
        results[name] = {"modele": type(estimator).__name__, "features": features} | metrics

    with mlflow.start_run(run_name="A_comparaison_modeles"):
        mlflow.set_tag("etape", "comparaison")
        mlflow.log_params(economie.hypotheses())
        for name, estimator in candidate_models().items():
            run(name, estimator, FEATURES_ALL,
                f"{name}, toutes les variables. RMSE CV = {{cv_rmse:.3f}} t/ha, R² = {{cv_r2:.3f}}.")

        best = min(results, key=lambda n: results[n]["cv_rmse"])
        run(f"{best} - variables cles", candidate_models()[best], FEATURES_CLES,
            f"{best} limité aux 6 variables clés de l'étape 1. RMSE CV = {{cv_rmse:.3f}} t/ha, R² = {{cv_r2:.3f}}.")

        table = pd.DataFrame(results).T.sort_values("cv_rmse")
        mlflow.log_text(table.drop(columns="features").to_csv(), "comparaison_modeles.csv")
        mlflow.log_metric("meilleur_cv_rmse", table["cv_rmse"].iloc[0])
        mlflow.set_tag("mlflow.note.content",
                       f"Meilleur modèle en validation croisée : {table.index[0]} (RMSE {table['cv_rmse'].iloc[0]:.3f} t/ha).")
    return table


def best_family(table: pd.DataFrame):
    """Estimateur (non entraîné) du meilleur modèle sur toutes les variables."""
    return candidate_models()[table[~table.index.str.endswith("variables cles")].index[0]]


def choose_features(table: pd.DataFrame) -> list[str]:
    """Garde le jeu réduit si sa RMSE ne dépasse pas celle du jeu complet de plus de PARSIMONY_TOLERANCE :
    un agriculteur renseigne alors 6 champs au lieu de 10 dans l'application."""
    reduced = table[table.index.str.endswith("variables cles")].iloc[0]
    full = table[(table["modele"] == reduced["modele"]) & ~table.index.str.endswith("variables cles")].iloc[0]
    return FEATURES_CLES if reduced["cv_rmse"] <= full["cv_rmse"] * (1 + PARSIMONY_TOLERANCE) else FEATURES_ALL


def tune(train: pd.DataFrame, estimator, features: list[str]) -> tuple[dict, pd.DataFrame]:
    """Étape B : recherche aléatoire des hyperparamètres, un run MLflow par configuration."""
    sample = train.sample(min(CV_SAMPLE, len(train)), random_state=SEED)
    space = TUNING_SPACES[type(estimator).__name__]
    configs, trials = [], []
    with mlflow.start_run(run_name=f"B_optimisation_{type(estimator).__name__}"):
        mlflow.set_tag("etape", "optimisation")
        _log_common(features, len(sample))
        mlflow.log_params({"n_iter": N_ITER, "cv_folds": CV_FOLDS})
        for i, params in enumerate(ParameterSampler(space, n_iter=N_ITER, random_state=SEED), start=1):
            with mlflow.start_run(run_name=f"essai_{i:02d}", nested=True):
                mlflow.log_params({k.removeprefix("model__"): v for k, v in params.items()})
                metrics = cross_validate(build_pipeline(clone(estimator), features).set_params(**params), sample, features)
                mlflow.log_metrics(metrics)
            configs.append(params)
            trials.append({**params, **metrics})

        # Configuration lue dans la liste d'origine : un tableau pandas transformerait None en NaN
        best = configs[int(np.argmin([t["cv_rmse"] for t in trials]))]
        trials = pd.DataFrame(trials).sort_values("cv_rmse").reset_index(drop=True)
        mlflow.log_params({f"meilleur_{k.removeprefix('model__')}": v for k, v in best.items()})
        mlflow.log_metrics({"meilleur_cv_rmse": trials["cv_rmse"].iloc[0], "meilleur_cv_r2": trials["cv_r2"].iloc[0]})
        mlflow.log_text(trials.to_csv(index=False), "essais.csv")
        mlflow.set_tag("mlflow.note.content",
                       f"{N_ITER} configurations testées. Meilleure RMSE CV : {trials['cv_rmse'].iloc[0]:.3f} t/ha "
                       f"(pire : {trials['cv_rmse'].iloc[-1]:.3f}).")
    return best, trials


def _figures(test: pd.DataFrame, pred: np.ndarray, importance: pd.Series) -> dict:
    figs = {}
    fig, ax = plt.subplots(figsize=(6, 6))
    s = np.random.default_rng(SEED).choice(len(test), size=min(20_000, len(test)), replace=False)
    real, guess, crops = test[TARGET].to_numpy()[s], pred[s], test["Crop"].to_numpy()[s]
    for crop in CROPS:
        ax.scatter(real[crops == crop], guess[crops == crop], s=3, alpha=0.3, label=crop)
    lim = [0, float(np.percentile(test[TARGET], 99.5))]
    ax.plot(lim, lim, "k--", lw=1)
    ax.set(xlim=lim, ylim=lim, xlabel="Rendement réel (t/ha)", ylabel="Rendement prédit (t/ha)",
           title="Jeu de test : prédit vs réel")
    ax.legend(markerscale=4)
    figs["predit_vs_reel.png"] = fig

    fig, ax = plt.subplots(figsize=(7, 4))
    importance.sort_values().plot.barh(ax=ax, color="tab:green")
    ax.set(xlabel="Hausse de la RMSE quand la variable est brouillée (t/ha)", title="Importance des variables")
    figs["importance_variables.png"] = fig
    # Fermées pour ne pas s'afficher d'office dans un notebook ; restent utilisables (log, display).
    # tight_layout : sans lui, les noms de variables sont rognés dans les images enregistrées par MLflow
    for fig in figs.values():
        fig.tight_layout()
        plt.close(fig)
    return figs


def train_final(train: pd.DataFrame, test: pd.DataFrame, estimator, best_params: dict, features: list[str]):
    """Étape C : réentraînement sur tout le jeu d'entraînement, évaluation unique sur le test."""
    with mlflow.start_run(run_name="C_modele_final") as run:
        mlflow.set_tag("etape", "modele_final")
        _log_common(features, len(train))
        mlflow.log_params({"modele": type(estimator).__name__} | {k.removeprefix("model__"): v for k, v in best_params.items()})
        mlflow.log_params(economie.hypotheses())

        pipeline = build_pipeline(clone(estimator), features).set_params(**best_params)
        start = time.perf_counter()
        pipeline.fit(train[features], train[TARGET])
        mlflow.log_metric("duree_entrainement_s", time.perf_counter() - start)

        pred_test = pipeline.predict(test[features])
        metrics = {"taille_modele_mo": len(pickle.dumps(pipeline)) / 1e6}
        metrics |= {f"test_{k}": v for k, v in evaluate(test, test[TARGET], pred_test).items()}
        metrics |= {f"train_{k}": v for k, v in evaluate(train, train[TARGET], pipeline.predict(train[features])).items()}
        metrics["ecart_rmse_test_train"] = metrics["test_rmse"] - metrics["train_rmse"]
        for crop in CROPS:
            m = (test["Crop"] == crop).to_numpy()
            crop_metrics = evaluate(test[m], test[TARGET][m], pred_test[m])
            metrics |= {f"test_rmse_{crop}": crop_metrics["rmse"], f"test_r2_{crop}": crop_metrics["r2"]}
        mlflow.log_metrics(metrics)

        sample = test.sample(min(20_000, len(test)), random_state=SEED)
        perm = permutation_importance(pipeline, sample[features], sample[TARGET], n_repeats=5,
                                      random_state=SEED, scoring="neg_root_mean_squared_error", n_jobs=-1)
        importance = pd.Series(perm.importances_mean, index=features, name="importance").sort_values(ascending=False)
        mlflow.log_text(importance.to_csv(), "importance_variables.csv")

        figs = _figures(test, pred_test, importance)
        for name, fig in figs.items():
            mlflow.log_figure(fig, name)

        # Modèle produit ici même : on autorise explicitement les types d'arbres internes de scikit-learn
        mlflow.sklearn.log_model(pipeline, name="modele", input_example=test[features].head(5),
                                 registered_model_name=REGISTERED_MODEL, skops_trusted_types=TRUSTED_TREE_TYPES)
        mlflow.set_tag("mlflow.note.content",
                       f"Modèle retenu, évalué une seule fois sur {len(test):,} parcelles jamais vues. "
                       f"RMSE {metrics['test_rmse']:.3f} t/ha, R² {metrics['test_r2']:.3f}, "
                       f"rentabilité bien classée pour {metrics['test_precision_rentabilite']:.1%} des parcelles. "
                       f"Écart test - entraînement : {metrics['ecart_rmse_test_train']:+.3f} t/ha.")
        run_id = run.info.run_id
    return pipeline, metrics, importance, figs, run_id


def save_model(pipeline: Pipeline, features: list[str], metrics: dict, run_id: str) -> Path:
    """Copie locale du modèle et de sa fiche, pour l'API de l'étape suivante."""
    MODEL_DIR.mkdir(exist_ok=True)
    path = MODEL_DIR / "modele_rendement.joblib"
    # Compression zlib niveau 3 : environ 40 Mo au lieu de 104 Mo, mêmes prédictions.
    # Le fichier reste ainsi sous la limite de 100 Mo par fichier de GitHub (pipeline CI/CD, étape 5).
    joblib.dump(pipeline, path, compress=("zlib", 3))
    (MODEL_DIR / "modele_rendement.json").write_text(json.dumps(
        {"features": features, "cultures": CROPS, "mlflow_run_id": run_id,
         "metriques_test": {k: round(v, 4) for k, v in metrics.items() if k.startswith("test_")}},
        indent=2, ensure_ascii=False), encoding="utf-8")
    return path


# --------------------------------------------------------------------------- recommandation

def recommend(model: Pipeline, conditions: dict, features: list[str]) -> pd.DataFrame:
    """Simule le rendement et la marge de chaque culture pour une parcelle, classées par marge."""
    frame = pd.DataFrame([{**conditions, "Crop": crop} for crop in CROPS])[features]
    frame["rendement_t_ha"] = model.predict(frame)
    frame["marge_usd_ha"] = economie.marge(frame["Crop"], frame["rendement_t_ha"],
                                           frame["Fertilizer_Used"], frame["Irrigation_Used"])
    frame["seuil_rentabilite_t_ha"] = [economie.seuil_rentabilite(c, int(f), int(i)) for c, f, i in
                                       zip(frame["Crop"], frame["Fertilizer_Used"], frame["Irrigation_Used"])]
    out = frame.sort_values("marge_usd_ha", ascending=False).reset_index(drop=True)
    out.index = out.index + 1
    return out[["Crop", "rendement_t_ha", "marge_usd_ha", "seuil_rentabilite_t_ha"]]


def recommendation_grid(model: Pipeline, features: list[str], base: dict,
                        temperatures: np.ndarray, rainfalls: np.ndarray) -> pd.DataFrame:
    """Rendement et marge de chaque culture sur une grille température x pluie (autres conditions fixées)."""
    t, r, c = np.meshgrid(temperatures, rainfalls, CROPS, indexing="ij")
    frame = pd.DataFrame({"Temperature_Celsius": t.ravel(), "Rainfall_mm": r.ravel(), "Crop": c.ravel()})
    for k, v in base.items():
        frame[k] = v
    frame["rendement_t_ha"] = model.predict(frame[features])
    frame["marge_usd_ha"] = economie.marge(frame["Crop"], frame["rendement_t_ha"],
                                           frame["Fertilizer_Used"], frame["Irrigation_Used"])
    return frame


# --------------------------------------------------------------------------- script

def main() -> None:
    plt.switch_backend("Agg")
    setup_mlflow()
    train, test = split(load_data())
    print(f"Entraînement : {len(train):,} | test : {len(test):,}")

    table = compare_models(train)
    print(table[["modele", "cv_rmse", "cv_r2", "cv_rmse_marge_usd_ha", "cv_precision_rentabilite"]])
    features = choose_features(table)
    estimator = best_family(table)
    print("Variables retenues :", features)

    best_params, _ = tune(train, estimator, features)
    print("Meilleurs hyperparamètres :", best_params)

    pipeline, metrics, importance, _, run_id = train_final(train, test, estimator, best_params, features)
    print(json.dumps({k: round(v, 4) for k, v in metrics.items() if k.startswith("test_")}, indent=2))
    print(importance)
    print("Modèle sauvegardé :", save_model(pipeline, features, metrics, run_id))


if __name__ == "__main__":
    main()
