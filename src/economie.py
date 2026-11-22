"""Hypothèses économiques : du rendement (t/ha) à la marge (USD/ha).

Aucun des deux jeux de données ne contient de prix ni de coûts. Ils sont donc
tirés de sources publiques (ci-dessous) pour traduire les rendements en marge,
objectif métier exprimé par Gabriel (« modéliser la relation entre les espèces
cultivées, les coûts de production et les profits »). Tout est centralisé ici
pour pouvoir être remplacé par les prix et coûts réels d'Agritech Answers sans
toucher au modèle : le modèle prédit un rendement, la marge est calculée après.

marge (USD/ha) = rendement (t/ha) x prix (USD/t)
                 - coût de base de la culture (USD/ha)
                 - coût de l'engrais de la culture (si utilisé)
                 - coût de l'irrigation (si utilisée)

Sources
-------
Prix : Banque mondiale, « Commodity Price Data (The Pink Sheet) », édition de
novembre 2026, moyenne annuelle Jan-Dec 2025 (USD/tonne métrique) :
  - Maize (US), no. 2 yellow, f.o.b. US Gulf ........ 203,2
  - Soybeans (US), c.i.f. Rotterdam ................. 414,0
  - Wheat (US), no. 1 HRW, f.o.b. US Gulf ........... 243,3
  - Rice (Thailand), 5 % broken, milled, f.o.b. ..... 407,8
  Les rendements FAO du riz sont exprimés en paddy (non décortiqué) : le prix
  du riz blanchi est converti en équivalent paddy avec le taux d'usinage
  standard de la FAO (0,67 t de riz blanchi par t de paddy).
  https://www.worldbank.org/en/research/commodity-markets

Coûts : USDA Economic Research Service, « Commodity Costs and Returns »,
U.S. total, année 2025, USD par acre semé (fichiers corn/soybeans/wheat/rice).
  - coût de base = coûts opérationnels totaux - engrais - eau d'irrigation
    achetée (semences, phytosanitaires, prestations, carburant, réparations,
    intérêts). Les charges de structure (terre, matériel, main-d'œuvre
    familiale) sont exclues : il s'agit d'une marge sur coûts opérationnels.
  - coût de l'engrais = poste « Fertilizer ».
  https://www.ers.usda.gov/data-products/commodity-costs-and-returns

Ajustement à l'intensité des parcelles : les rendements américains sont 1,3 à
3,4 fois ceux du jeu consolidé (maïs 12,4 t/ha contre 3,6 en moyenne).
Appliqués tels quels, les coûts américains rendraient le riz et le maïs
presque jamais rentables, un artefact du décalage d'intensité. Les coûts
par hectare sont donc multipliés par (rendement moyen du jeu consolidé /
rendement américain), ce qui revient à conserver le coût par tonne produite
américain. C'est une hypothèse de modélisation, pas une donnée observée.

Irrigation : aucune source publique comparable ne donne un coût d'irrigation
par hectare (l'USDA ne compte que l'eau achetée, le pompage étant noyé dans
« carburant et électricité »). La valeur de 200 USD/ha reste un ORDRE DE
GRANDEUR ILLUSTRATIF, à remplacer en priorité par un chiffre du client.
"""

import numpy as np
import pandas as pd

ACRE_PAR_HA = 2.4711
TAUX_USINAGE_RIZ = 0.67  # t de riz blanchi par t de paddy (FAO)

# --- Prix : Banque mondiale, Pink Sheet, moyenne 2025 (USD/t) ---
PRIX_USD_T = {
    "Maize": 203.2,
    "Rice": round(407.8 * TAUX_USINAGE_RIZ, 1),  # équivalent paddy
    "Soybean": 414.0,
    "Wheat": 243.3,
}

# --- Coûts : USDA ERS, U.S. total 2025 (USD par acre semé) ---
_USDA_2025 = {
    #           coûts opérationnels, engrais, eau achetée, rendement (t/ha)
    "Maize":   (455.80, 171.89, 0.29, 198 * 0.0254012 * ACRE_PAR_HA),    # 198 bu/acre
    "Rice":    (792.12, 190.13, 21.45, 81 * 0.0453592 * ACRE_PAR_HA),    # 81 cwt/acre
    "Soybean": (250.88, 59.18, 0.18, 58 * 0.0272155 * ACRE_PAR_HA),      # 58 bu/acre
    "Wheat":   (162.96, 63.93, 0.00, 54 * 0.0272155 * ACRE_PAR_HA),      # 54 bu/acre
}

# Rendement moyen par culture dans data/processed/dataset_consolide.csv (t/ha)
RENDEMENT_MOYEN_T_HA = {"Maize": 3.6457, "Rice": 3.7637, "Soybean": 1.6153, "Wheat": 2.7951}


def _ajuste(usd_par_acre: float, crop: str) -> float:
    """USD/acre américain -> USD/ha ramené à l'intensité du jeu consolidé."""
    rendement_us = _USDA_2025[crop][3]
    return round(usd_par_acre * ACRE_PAR_HA * RENDEMENT_MOYEN_T_HA[crop] / rendement_us, 1)


# Coûts de production de base hors engrais et irrigation (USD/ha)
COUT_BASE_USD_HA = {c: _ajuste(op - engrais - eau, c) for c, (op, engrais, eau, _) in _USDA_2025.items()}

# Coût de l'engrais par culture (USD/ha)
COUT_ENGRAIS_USD_HA = {c: _ajuste(engrais, c) for c, (_, engrais, _, _) in _USDA_2025.items()}

# Illustratif, non sourcé (voir docstring)
COUT_IRRIGATION_USD_HA = 200.0


def hypotheses() -> dict:
    """Hypothèses à plat, pour journalisation dans MLflow."""
    params = {f"prix_usd_t_{c}": p for c, p in PRIX_USD_T.items()}
    params |= {f"cout_base_usd_ha_{c}": v for c, v in COUT_BASE_USD_HA.items()}
    params |= {f"cout_engrais_usd_ha_{c}": v for c, v in COUT_ENGRAIS_USD_HA.items()}
    params |= {"cout_irrigation_usd_ha": COUT_IRRIGATION_USD_HA,
               "source_prix": "Banque mondiale Pink Sheet, moyenne 2025",
               "source_couts": "USDA ERS 2025, ajusté au rendement moyen du jeu"}
    return params


def marge(crop: pd.Series, rendement, fertilizer: pd.Series, irrigation: pd.Series) -> np.ndarray:
    """Marge par hectare sur coûts opérationnels (USD/ha) pour des vecteurs alignés."""
    prix = crop.map(PRIX_USD_T).to_numpy()
    cout = (
        crop.map(COUT_BASE_USD_HA).to_numpy()
        + crop.map(COUT_ENGRAIS_USD_HA).to_numpy() * np.asarray(fertilizer)
        + COUT_IRRIGATION_USD_HA * np.asarray(irrigation)
    )
    return np.asarray(rendement) * prix - cout


def seuil_rentabilite(crop: str, fertilizer: int, irrigation: int) -> float:
    """Rendement minimal (t/ha) pour que la marge soit positive."""
    cout = COUT_BASE_USD_HA[crop] + COUT_ENGRAIS_USD_HA[crop] * fertilizer + COUT_IRRIGATION_USD_HA * irrigation
    return cout / PRIX_USD_T[crop]
