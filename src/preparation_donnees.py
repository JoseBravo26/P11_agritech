"""Étape 1 : nettoyage et fusion des deux jeux de données.

Stratégie (détaillée dans notebooks/01_exploration_fusion.ipynb) :
- DS1 (Agriculture Crop Yield) fournit les parcelles et l'effet des pratiques
  culturales (engrais, irrigation), mais son rendement ne dépend pas de la culture.
- DS2 (FAO, Crop Yield Prediction) fournit des rendements réels par culture et
  par climat, ainsi que l'usage de pesticides.
- Fusion par appariement statistique (distance hot-deck) : chaque parcelle DS1
  reçoit un « donneur » FAO de la même culture, au climat le plus proche.
- Rendement cible = rendement FAO du donneur x coefficient de conduite DS1.

Usage : python -m src.preparation_donnees
"""

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.neighbors import NearestNeighbors

ROOT = Path(__file__).resolve().parents[1]
DS1_PATH = ROOT / "Agriculture Crop Yield" / "crop_yield.csv"
DS2_PATH = ROOT / "Crop Yield Prediction Dataset" / "yield_df.csv"
OUTPUT_PATH = ROOT / "data" / "processed" / "dataset_consolide.csv"

TARGET = "Yield_tons_per_hectare"
# Noms FAO -> noms DS1, pour les seules cultures présentes dans les deux sources
CROP_MAPPING = {"Maize": "Maize", "Rice, paddy": "Rice", "Soybeans": "Soybean", "Wheat": "Wheat"}
COMMON_CROPS = sorted(CROP_MAPPING.values())
HG_PER_TONNE = 10_000
YIELD_CAP_QUANTILE = 0.99
N_DONORS = 10
SEED = 42

OUTPUT_COLUMNS = [
    "Region", "Soil_Type", "Crop", "Rainfall_mm", "Temperature_Celsius",
    "Pesticides_tonnes", "Fertilizer_Used", "Irrigation_Used",
    "Weather_Condition", "Days_to_Harvest", TARGET,
]


def load_ds1(path: Path = DS1_PATH) -> pd.DataFrame:
    return pd.read_csv(path)


def load_ds2(path: Path = DS2_PATH) -> pd.DataFrame:
    return pd.read_csv(path, index_col=0)


def clean_ds1(df: pd.DataFrame) -> pd.DataFrame:
    """Garde les cultures communes, retire les rendements <= 0, booléens -> 0/1."""
    out = df[df["Crop"].isin(COMMON_CROPS) & (df[TARGET] > 0)].copy()
    for col in ["Fertilizer_Used", "Irrigation_Used"]:
        out[col] = out[col].astype(int)
    return out.reset_index(drop=True)


def clean_ds2(df: pd.DataFrame) -> pd.DataFrame:
    """Une ligne par (pays, culture, année), rendement en t/ha plafonné, noms harmonisés.

    yield_df.csv répète chaque rendement autant de fois que temp.csv contient de
    stations pour le pays : on moyenne ces températures. Pluie, pesticides et
    rendement sont constants au sein d'un (pays, culture, année).
    """
    out = (
        df.drop_duplicates()
        .groupby(["Area", "Item", "Year"], as_index=False)
        .agg(
            yield_hg_ha=("hg/ha_yield", "first"),
            rainfall_mm=("average_rain_fall_mm_per_year", "first"),
            pesticides_tonnes=("pesticides_tonnes", "first"),
            avg_temp=("avg_temp", "mean"),
        )
    )
    out = out[out["Item"].isin(CROP_MAPPING)].copy()
    out["Crop"] = out["Item"].map(CROP_MAPPING)
    out["yield_t_ha"] = out["yield_hg_ha"] / HG_PER_TONNE
    # Plafonne les valeurs extrêmes (ex. maïs du Qatar ~20 t/ha sur des micro-surfaces)
    # sans supprimer d'observations
    cap = out.groupby("Crop")["yield_t_ha"].transform(lambda s: s.quantile(YIELD_CAP_QUANTILE))
    out["yield_t_ha"] = out["yield_t_ha"].clip(upper=cap)
    return out.drop(columns=["Item", "yield_hg_ha"]).reset_index(drop=True)


def to_fao_scale(values: np.ndarray, ds1_ref: np.ndarray, fao_ref: np.ndarray) -> np.ndarray:
    """Aligne une variable DS1 sur l'échelle FAO par correspondance de quantiles.

    DS1 décrit le climat de la parcelle (saison), DS2 des moyennes annuelles par
    pays : on compare donc des positions relatives (rangs), pas des valeurs brutes.
    """
    ranks = np.searchsorted(np.sort(ds1_ref), values, side="right") / len(ds1_ref)
    return np.quantile(fao_ref, np.clip(ranks, 0.0, 1.0))


def management_factor(ds1: pd.DataFrame) -> pd.Series:
    """Coefficient de conduite = rendement observé / rendement attendu au même climat.

    Le climat est déjà porté par le donneur FAO : on ne garde de DS1 que l'effet
    des pratiques (engrais, irrigation) et l'aléa, pour ne pas compter la pluie deux fois.
    """
    climate = ds1[["Rainfall_mm", "Temperature_Celsius"]]
    expected = LinearRegression().fit(climate, ds1[TARGET]).predict(climate)
    if (expected <= 0).any():
        raise ValueError("Rendement attendu non positif : coefficient de conduite indéfini")
    return ds1[TARGET] / expected


def match_donors(
    ds1: pd.DataFrame, ds2: pd.DataFrame, k: int = N_DONORS, seed: int = SEED
) -> tuple[np.ndarray, np.ndarray]:
    """Pour chaque parcelle DS1, tire un donneur FAO parmi les k plus proches
    voisins climatiques (température, pluie) de la même culture.

    Le tirage aléatoire parmi k voisins conserve la variabilité réelle des
    rendements et des pesticides au lieu de la lisser par une moyenne.
    """
    rng = np.random.default_rng(seed)
    receiver = np.column_stack([
        to_fao_scale(ds1["Temperature_Celsius"].to_numpy(), ds1["Temperature_Celsius"].to_numpy(), ds2["avg_temp"].to_numpy()),
        to_fao_scale(ds1["Rainfall_mm"].to_numpy(), ds1["Rainfall_mm"].to_numpy(), ds2["rainfall_mm"].to_numpy()),
    ])
    donor = ds2[["avg_temp", "rainfall_mm"]].to_numpy()
    mean, std = donor.mean(axis=0), donor.std(axis=0)
    receiver, donor = (receiver - mean) / std, (donor - mean) / std

    donor_idx = np.empty(len(ds1), dtype=int)
    donor_dist = np.empty(len(ds1))
    for crop in COMMON_CROPS:
        recv_rows = np.flatnonzero(ds1["Crop"].to_numpy() == crop)
        crop_donors = np.flatnonzero(ds2["Crop"].to_numpy() == crop)
        dist, idx = NearestNeighbors(n_neighbors=k).fit(donor[crop_donors]).kneighbors(receiver[recv_rows])
        pick = rng.integers(0, k, size=len(recv_rows))
        rows = np.arange(len(recv_rows))
        donor_idx[recv_rows] = crop_donors[idx[rows, pick]]
        donor_dist[recv_rows] = dist[rows, pick]
    return donor_idx, donor_dist


def fuse(ds1_raw: pd.DataFrame, ds2_raw: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Retourne (dataset consolidé, table d'audit de la fusion)."""
    ds1, ds2 = clean_ds1(ds1_raw), clean_ds2(ds2_raw)
    factor = management_factor(ds1)
    donor_idx, donor_dist = match_donors(ds1, ds2)
    donors = ds2.iloc[donor_idx].reset_index(drop=True)

    dataset = ds1.drop(columns=[TARGET])
    dataset["Pesticides_tonnes"] = donors["pesticides_tonnes"].to_numpy()
    dataset[TARGET] = donors["yield_t_ha"].to_numpy() * factor.to_numpy()
    dataset = dataset[OUTPUT_COLUMNS].round(
        {"Rainfall_mm": 2, "Temperature_Celsius": 2, "Pesticides_tonnes": 2, TARGET: 4}
    )

    audit = pd.DataFrame({
        "Crop": ds1["Crop"],
        "ds1_yield": ds1[TARGET],
        "management_factor": factor,
        "donor_area": donors["Area"],
        "donor_year": donors["Year"],
        "donor_yield_t_ha": donors["yield_t_ha"],
        "donor_temp": donors["avg_temp"],
        "donor_rainfall": donors["rainfall_mm"],
        "donor_distance": donor_dist,
    })
    return dataset, audit


def main() -> None:
    dataset, audit = fuse(load_ds1(), load_ds2())
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    dataset.to_csv(OUTPUT_PATH, index=False)
    print(f"{len(dataset):,} lignes, {dataset.shape[1]} colonnes -> {OUTPUT_PATH}")
    print(f"Donneurs FAO distincts : {audit.groupby(['donor_area', 'donor_year', 'Crop']).ngroups:,}")


if __name__ == "__main__":
    main()
