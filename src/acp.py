"""Analyse en composantes principales (ACP) : identifier les variables clés du rendement.

Démarche demandée par la mission :
1. ACP sur « Agriculture Crop Yield » (DS1, 1 million de parcelles) pour repérer
   les variables qui vont avec le rendement et celles qui n'apportent rien ;
2. ACP de validation sur « Crop Yield Prediction » (FAO, données réelles) ;
3. synthèse : on compare ces résultats à l'importance des variables dans le
   modèle final (étape 2).

Principe de l'ACP, en bref : on résume beaucoup de variables liées entre elles en
quelques « axes ». Chaque axe est une combinaison de variables ; une variable
fortement corrélée à un axe « porte » cet axe. Si le rendement et la pluie sont
tous deux portés par le même axe, ils varient ensemble.

Les variables qualitatives (culture, région, sol, météo) ne servent pas à
construire les axes (variables « supplémentaires ») : on regarde ensuite si
leurs modalités se placent à des endroits différents sur ces axes.

Lancement : python -m src.acp   (figures et tableaux dans reports/acp/)
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Circle, FancyArrowPatch
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

from src.preparation_donnees import clean_ds2, load_ds1, load_ds2

ROOT = Path(__file__).resolve().parents[1]
SORTIE = ROOT / "reports" / "acp"

# --------------------------------------------------------------------------- libellés et style

# Noms lisibles pour les graphiques et le rapport
LIBELLES = {
    "Rainfall_mm": "Pluie", "Temperature_Celsius": "Température", "Days_to_Harvest": "Durée de culture",
    "Fertilizer_Used": "Engrais", "Irrigation_Used": "Irrigation", "Yield_tons_per_hectare": "Rendement",
    "rainfall_mm": "Pluie", "avg_temp": "Température", "log_pesticides": "Pesticides",
    "yield_t_ha": "Rendement", "Crop": "Culture", "Region": "Région", "Soil_Type": "Type de sol",
    "Weather_Condition": "Météo dominante",
}
MODALITES_FR = {"Maize": "Maïs", "Rice": "Riz", "Soybean": "Soja", "Wheat": "Blé", "Barley": "Orge",
                "Cotton": "Coton", "North": "Nord", "South": "Sud", "East": "Est", "West": "Ouest",
                "Sandy": "Sableux", "Clay": "Argileux", "Loam": "Limoneux", "Silt": "Silteux",
                "Peaty": "Tourbeux", "Chalky": "Calcaire", "Sunny": "Ensoleillé", "Rainy": "Pluvieux",
                "Cloudy": "Nuageux"}

# Palette sobre et moderne : un vert « agriculture » pour le rendement, des neutres ailleurs
VERT, VERT_CLAIR = "#15803d", "#bbf7d0"
ARDOISE, GRIS, GRIS_CLAIR = "#1e293b", "#64748b", "#e2e8f0"
AMBRE, BLEU, ROSE = "#d97706", "#2563eb", "#e11d48"
FOND = "#ffffff"


def appliquer_style() -> None:
    """Style commun à tous les graphiques : épuré, grille discrète, police lisible."""
    plt.rcParams.update({
        "figure.facecolor": FOND, "axes.facecolor": FOND, "savefig.facecolor": FOND,
        "font.family": ["Segoe UI", "DejaVu Sans"], "font.size": 11,
        "axes.edgecolor": GRIS_CLAIR, "axes.labelcolor": ARDOISE, "axes.titleweight": "bold",
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "grid.color": GRIS_CLAIR, "grid.linewidth": 0.8,
        "xtick.color": GRIS, "ytick.color": GRIS, "text.color": ARDOISE,
        "figure.dpi": 110, "savefig.dpi": 200, "savefig.bbox": "tight",
    })


def titrer(fig, titre: str, sous_titre: str = "", ax=None, marge_pts: float = 14) -> None:
    """Titre aligné à gauche, avec une ligne d'explication en gris, juste au-dessus du graphique.

    La position est donnée en points au-dessus du haut du graphique : l'écart reste
    le même quelle que soit la hauteur de la figure.
    """
    ax = ax or fig.axes[0]
    position = dict(xy=(0.01, 1), xycoords=("figure fraction", "axes fraction"), textcoords="offset points",
                    ha="left", va="bottom", annotation_clip=False)
    ax.annotate(titre, xytext=(0, marge_pts + 22), fontsize=15, fontweight="bold", color=ARDOISE, **position)
    if sous_titre:
        ax.annotate(sous_titre, xytext=(0, marge_pts + 4), fontsize=10.5, color=GRIS, **position)


# --------------------------------------------------------------------------- données

def preparer_ds1() -> pd.DataFrame:
    """DS1 complet (les 6 cultures), rendements négatifs retirés, oui/non -> 1/0."""
    ds1 = load_ds1()
    ds1 = ds1[ds1["Yield_tons_per_hectare"] > 0].copy()
    for col in ["Fertilizer_Used", "Irrigation_Used"]:
        ds1[col] = ds1[col].astype(int)
    return ds1.reset_index(drop=True)


def preparer_fao() -> pd.DataFrame:
    """FAO nettoyée à l'étape 1 (une ligne par pays, culture et année ; 4 cultures communes).

    Les pesticides sont très asymétriques (de 0 à 367 000 tonnes) : on prend leur
    logarithme, sinon quelques grands pays écraseraient l'analyse.
    """
    fao = clean_ds2(load_ds2())
    fao["log_pesticides"] = np.log1p(fao["pesticides_tonnes"])
    return fao


# --------------------------------------------------------------------------- calcul de l'ACP

@dataclass
class ResultatACP:
    """Tout ce qu'il faut pour lire une ACP."""
    valeurs_propres: pd.Series            # « quantité d'information » de chaque axe
    inertie_pct: pd.Series                # part de l'information totale (%)
    correlations: pd.DataFrame            # corrélation variable / axe (entre -1 et 1)
    contributions_pct: pd.DataFrame       # part de chaque variable dans la construction de l'axe
    barycentres: dict = field(default_factory=dict)   # position moyenne de chaque modalité qualitative
    eta2_pct: pd.DataFrame | None = None  # part de l'axe expliquée par chaque variable qualitative
    n_individus: int = 0


def faire_acp(df: pd.DataFrame, actives: list[str], qualitatives: tuple[str, ...] = ()) -> ResultatACP:
    """ACP normée (variables centrées-réduites) + variables qualitatives supplémentaires.

    Centrer-réduire met toutes les variables sur la même échelle : sans cela, la
    pluie (centaines de mm) écraserait l'engrais (0 ou 1).
    """
    X = StandardScaler().fit_transform(df[actives])
    acp = PCA().fit(X)
    axes = [f"F{i + 1}" for i in range(len(actives))]
    vp = pd.Series(acp.explained_variance_, index=axes)

    # Pour des données centrées-réduites, corrélation variable/axe = vecteur propre x racine(valeur propre)
    corr = pd.DataFrame(acp.components_.T * np.sqrt(acp.explained_variance_), index=actives, columns=axes)
    # Le signe d'un axe est arbitraire : on oriente chaque axe pour que sa variable principale soit positive
    signes = np.sign(corr.to_numpy()[np.abs(corr.to_numpy()).argmax(axis=0), range(len(axes))])
    corr = corr * signes
    contrib = pd.DataFrame(acp.components_.T ** 2 * 100, index=actives, columns=axes)

    # Coordonnées des individus, exprimées en écarts-types de chaque axe (comparables entre axes)
    coord = pd.DataFrame(acp.transform(X) / np.sqrt(acp.explained_variance_) * signes, columns=axes)
    barycentres, eta2 = {}, {}
    for var in qualitatives:
        groupes = coord.groupby(df[var].to_numpy())
        barycentres[var] = groupes.mean()
        # eta² = variance entre modalités / variance totale : 0 % = aucun lien, 100 % = lien parfait
        eta2[var] = (groupes.size().to_numpy()[:, None] * groupes.mean() ** 2).sum() / len(coord) * 100

    return ResultatACP(
        valeurs_propres=vp, inertie_pct=pd.Series(acp.explained_variance_ratio_ * 100, index=axes),
        correlations=corr, contributions_pct=contrib, barycentres=barycentres,
        eta2_pct=pd.DataFrame(eta2).T if eta2 else None, n_individus=len(df),
    )


def lien_avec_rendement(df: pd.DataFrame, cible: str, variables: list[str]) -> pd.Series:
    """Force du lien de chaque variable avec le rendement, sur une échelle de 0 à 1.

    - variable numérique ou oui/non : valeur absolue de la corrélation ;
    - variable qualitative : rapport de corrélation (racine de l'eta²), son équivalent.
    """
    liens = {}
    y = df[cible]
    for var in variables:
        if pd.api.types.is_numeric_dtype(df[var]):
            liens[var] = abs(df[var].corr(y))
        else:
            moyennes = y.groupby(df[var]).transform("mean")
            liens[var] = np.sqrt(((moyennes - y.mean()) ** 2).sum() / ((y - y.mean()) ** 2).sum())
    return pd.Series(liens)


def importance_modele() -> pd.Series | None:
    """Importance des variables du modèle final (étape 2), lue dans les artefacts MLflow."""
    fiche = json.loads((ROOT / "models" / "modele_rendement.json").read_text(encoding="utf-8"))
    chemin = ROOT / "mlruns" / fiche["mlflow_run_id"] / "artifacts" / "importance_variables.csv"
    if not chemin.exists():
        return None
    imp = pd.read_csv(chemin, index_col=0)["importance"]
    return imp / imp.max()   # ramenée à 1 pour la variable la plus importante


# --------------------------------------------------------------------------- graphiques

def fig_eboulis(res: ResultatACP, titre: str, chemin: Path) -> None:
    """Part d'information de chaque axe (barres) et cumul (ligne)."""
    fig, ax = plt.subplots(figsize=(8, 4.2))
    axes = [f"Axe {i + 1}" for i in range(len(res.inertie_pct))]
    seuil = 100 / len(axes)   # un axe « utile » doit résumer plus qu'une variable seule (règle de Kaiser)
    couleurs = [VERT if v > seuil * 1.2 else GRIS_CLAIR for v in res.inertie_pct]
    barres = ax.bar(axes, res.inertie_pct, color=couleurs, width=0.62, zorder=3)
    for b, v, c in zip(barres, res.inertie_pct, couleurs):
        # Valeur dans la barre (au-dessus si la barre est trop basse pour l'accueillir)
        dedans = v >= 6
        ax.text(b.get_x() + b.get_width() / 2, v / 2 if dedans else v + 1.5, f"{v:.0f} %", ha="center",
                va="center" if dedans else "bottom", fontsize=10, fontweight="bold",
                color=FOND if (dedans and c == VERT) else ARDOISE, zorder=5)
    ax.plot(axes, res.inertie_pct.cumsum(), color=ARDOISE, marker="o", lw=1.6, ms=5, zorder=4,
            label="Information cumulée")
    ax.axhline(seuil, color=AMBRE, ls="--", lw=1.2, zorder=2, label=f"Une variable seule ({seuil:.0f} %)")
    ax.set_ylim(0, 108)
    ax.set_ylabel("Part de l'information (%)")
    ax.grid(axis="x", visible=False)
    ax.legend(frameon=False, loc="upper left")
    titrer(fig, titre, "En vert : les axes qui résument plus d'information qu'une variable isolée")
    fig.savefig(chemin)
    plt.close(fig)


def fig_cercle(res: ResultatACP, titre: str, chemin: Path, sous_titre: str = "") -> None:
    """Cercle des corrélations sur les deux premiers axes.

    Une flèche longue = variable bien résumée par ces axes. Deux flèches dans la
    même direction = variables qui varient ensemble ; opposées = variables qui
    varient en sens inverse ; à angle droit = sans lien.
    """
    fig, ax = plt.subplots(figsize=(6.6, 6.6))
    ax.add_patch(Circle((0, 0), 1, fill=False, color=GRIS_CLAIR, lw=1.5))
    ax.add_patch(Circle((0, 0), 0.5, fill=False, color=GRIS_CLAIR, lw=0.8, ls=":"))
    ax.axhline(0, color=GRIS_CLAIR, lw=1)
    ax.axvline(0, color=GRIS_CLAIR, lw=1)
    for var, (x, y) in res.correlations[["F1", "F2"]].iterrows():
        nom = LIBELLES.get(var, var)
        est_cible = nom == "Rendement"
        longueur = np.hypot(x, y)
        couleur = VERT if est_cible else (BLEU if longueur >= 0.3 else GRIS)
        ax.add_patch(FancyArrowPatch((0, 0), (x, y), arrowstyle="-|>", mutation_scale=16,
                                     lw=3 if est_cible else 2, color=couleur, zorder=4))
        # Étiquette au bout de la flèche ; les flèches très courtes sont annotées à côté du centre
        if longueur > 0.2:
            tx, ty = x * 1.14, y * 1.14
        else:
            tx, ty = -0.42, -0.14
            nom = f"{nom} (≈ 0)"
        ax.text(tx, ty, nom, ha="center", va="center", fontsize=11, color=couleur,
                fontweight="bold" if est_cible else "normal",
                bbox=dict(boxstyle="round,pad=0.2", fc=FOND, ec="none", alpha=0.85), zorder=5)
    ax.set_xlim(-1.25, 1.25)
    ax.set_ylim(-1.25, 1.25)
    ax.set_aspect("equal")
    ax.grid(False)
    ax.set_xlabel(f"Axe 1 ({res.inertie_pct['F1']:.0f} % de l'information)")
    ax.set_ylabel(f"Axe 2 ({res.inertie_pct['F2']:.0f} % de l'information)")
    titrer(fig, titre, sous_titre or "Flèches proches = variables qui varient ensemble")
    fig.savefig(chemin)
    plt.close(fig)


def fig_correlations_axes(res: ResultatACP, titre: str, chemin: Path, n_axes: int = 3) -> None:
    """Carte de chaleur : corrélation de chaque variable avec les premiers axes."""
    corr = res.correlations.iloc[:, :n_axes].rename(index=LIBELLES)
    fig, ax = plt.subplots(figsize=(1.6 * n_axes + 2.8, 0.55 * len(corr) + 1.2))
    im = ax.imshow(corr.to_numpy(), cmap="RdBu_r", vmin=-1, vmax=1, aspect="auto")
    for i in range(corr.shape[0]):
        for j in range(corr.shape[1]):
            v = corr.iloc[i, j]
            ax.text(j, i, f"{v:+.2f}", ha="center", va="center", fontsize=10.5,
                    color=FOND if abs(v) > 0.55 else ARDOISE, fontweight="bold" if abs(v) >= 0.4 else "normal")
    ax.set_xticks(range(n_axes), [f"Axe {j + 1}\n({res.inertie_pct.iloc[j]:.0f} %)" for j in range(n_axes)])
    ax.set_yticks(range(len(corr)), corr.index)
    ax.grid(False)
    ax.tick_params(length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    barre = fig.colorbar(im, ax=ax, fraction=0.04, pad=0.03)
    barre.outline.set_visible(False)
    barre.set_label("corrélation", color=GRIS)
    titrer(fig, titre, "Rouge : varie dans le sens de l'axe · Bleu : en sens inverse")
    fig.savefig(chemin)
    plt.close(fig)


def fig_qualitatives(res: ResultatACP, titre: str, chemin: Path, sous_titre: str = "", axe: str = "F1") -> None:
    """Position moyenne des modalités qualitatives sur un axe (l'axe 1 par défaut).

    La bande verte représente la dispersion des individus (± 1 écart-type). Si toutes
    les modalités d'une variable sont collées au centre, cette variable ne distingue
    pas les individus sur cet axe.
    """
    positions, etiquettes, valeurs, titres_groupes = [], [], [], []
    y = 0.0
    for var, bary in res.barycentres.items():
        titres_groupes.append((y, LIBELLES.get(var, var)))
        y += 1.0                                   # ligne réservée au nom de la variable
        for modalite, f1 in bary[axe].sort_values().items():
            positions.append(y)
            etiquettes.append(MODALITES_FR.get(modalite, modalite))
            valeurs.append(f1)
            y += 1.0
        y += 0.6                                   # espace entre deux variables
    fig, ax = plt.subplots(figsize=(8.5, 0.34 * y + 1.2))
    ax.axvspan(-1, 1, color=VERT_CLAIR, alpha=0.45, zorder=0)
    ax.axvline(0, color=VERT, lw=1.2, zorder=1)
    for p, v in zip(positions, valeurs):
        ax.plot([0, v], [p, p], color=GRIS_CLAIR, lw=2, zorder=2)
        ax.scatter(v, p, s=70, zorder=3, color=ROSE if abs(v) > 0.1 else ARDOISE)
    for y0, nom in titres_groupes:
        ax.text(-1.33, y0, nom, fontsize=10.5, fontweight="bold", color=ARDOISE, ha="left", va="center")
    ax.set_yticks(positions, etiquettes, fontsize=9.5)
    ax.set_xlim(-1.35, 1.35)
    ax.set_ylim(y - 0.4, -0.8)
    ax.set_xlabel(f"Position moyenne sur l'axe {axe[1:]} (en écarts-types des individus)")
    ax.grid(axis="y", visible=False)
    titrer(fig, titre, sous_titre or "Bande verte : dispersion des individus · points au centre = aucun effet")
    fig.savefig(chemin)
    plt.close(fig)


def fig_synthese(synthese: pd.DataFrame, chemin: Path) -> None:
    """Matrice « variable x source » : force du lien avec le rendement (0 à 1)."""
    valeurs = synthese.to_numpy(dtype=float)
    fig, ax = plt.subplots(figsize=(8.8, 0.5 * len(synthese) + 1.6))
    carte = plt.get_cmap("Greens").copy()
    carte.set_bad("#f1f5f9")
    ax.imshow(np.ma.masked_invalid(valeurs), cmap=carte, vmin=0, vmax=1, aspect="auto")
    for i in range(valeurs.shape[0]):
        for j in range(valeurs.shape[1]):
            v = valeurs[i, j]
            if np.isnan(v):
                # Absente du modèle alors que DS1 la contient = retirée car elle n'apportait rien
                retiree = synthese.columns[j] == "Modèle final" and not np.isnan(valeurs[i, 0])
                ax.text(j, i, "retirée (aucun gain)" if retiree else "non mesurée", ha="center", va="center",
                        fontsize=9, color=GRIS, style="italic")
            else:
                ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=10.5,
                        color=FOND if v > 0.55 else ARDOISE, fontweight="bold" if v >= 0.3 else "normal")
    ax.set_xticks(range(synthese.shape[1]), synthese.columns, fontsize=10)
    ax.xaxis.tick_top()
    ax.set_yticks(range(len(synthese)), synthese.index, fontsize=10.5)
    ax.grid(False)
    ax.tick_params(length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    titrer(fig, "Variables clés : trois sources comparées",
           "Force du lien avec le rendement (0 = aucun, 1 = maximal) · modèle : importance ramenée à 1",
           marge_pts=34)   # laisse la place aux noms de colonnes, affichés en haut
    fig.savefig(chemin)
    plt.close(fig)


# --------------------------------------------------------------------------- programme principal

VARIABLES_DS1 = ["Rainfall_mm", "Temperature_Celsius", "Days_to_Harvest", "Fertilizer_Used",
                 "Irrigation_Used", "Yield_tons_per_hectare"]
QUALITATIVES_DS1 = ("Crop", "Region", "Soil_Type", "Weather_Condition")
VARIABLES_FAO = ["rainfall_mm", "avg_temp", "log_pesticides", "yield_t_ha"]


def tableau_synthese(ds1: pd.DataFrame, fao: pd.DataFrame) -> pd.DataFrame:
    """Rassemble, pour chaque variable, son lien avec le rendement dans chaque source."""
    lien_ds1 = lien_avec_rendement(ds1, "Yield_tons_per_hectare",
                                   [v for v in VARIABLES_DS1 if v != "Yield_tons_per_hectare"] + list(QUALITATIVES_DS1))
    lien_fao = lien_avec_rendement(fao, "yield_t_ha", ["rainfall_mm", "avg_temp", "log_pesticides", "Crop"])
    imp = importance_modele()

    noms = {  # libellé commun -> (nom DS1, nom FAO, nom modèle)
        "Culture": ("Crop", "Crop", "Crop"),
        "Température": ("Temperature_Celsius", "avg_temp", "Temperature_Celsius"),
        "Pluie": ("Rainfall_mm", "rainfall_mm", "Rainfall_mm"),
        "Pesticides (intensification)": (None, "log_pesticides", "Pesticides_tonnes"),
        "Engrais": ("Fertilizer_Used", None, "Fertilizer_Used"),
        "Irrigation": ("Irrigation_Used", None, "Irrigation_Used"),
        "Durée de culture": ("Days_to_Harvest", None, None),
        "Région": ("Region", None, None),
        "Type de sol": ("Soil_Type", None, None),
        "Météo dominante": ("Weather_Condition", None, None),
    }
    lignes = {}
    for libelle, (v1, v2, v3) in noms.items():
        lignes[libelle] = {
            "DS1 (1 M parcelles)": lien_ds1.get(v1, np.nan) if v1 else np.nan,
            "FAO (données réelles)": lien_fao.get(v2, np.nan) if v2 else np.nan,
            "Modèle final": (imp.get(v3, np.nan) if (imp is not None and v3) else np.nan),
        }
    return pd.DataFrame(lignes).T.astype(float).round(3)


def main() -> None:
    appliquer_style()
    SORTIE.mkdir(parents=True, exist_ok=True)

    # 1. ACP principale : Agriculture Crop Yield
    ds1 = preparer_ds1()
    res1 = faire_acp(ds1, VARIABLES_DS1, QUALITATIVES_DS1)
    fig_eboulis(res1, "ACP DS1 · Un seul axe résume vraiment l'information", SORTIE / "01_ds1_eboulis.png")
    fig_cercle(res1, "ACP DS1 · Cercle des corrélations", SORTIE / "02_ds1_cercle.png",
               "Le rendement suit la pluie, l'engrais et l'irrigation (axe 1)")
    fig_correlations_axes(res1, "ACP DS1 · Ce que porte chaque axe", SORTIE / "03_ds1_correlations_axes.png")
    fig_qualitatives(res1, "ACP DS1 · Culture, région, sol et météo n'ont aucun effet",
                     SORTIE / "04_ds1_qualitatives.png")

    # 2. ACP de validation : FAO (données réelles)
    fao = preparer_fao()
    res2 = faire_acp(fao, VARIABLES_FAO, ("Crop",))
    fig_eboulis(res2, f"ACP FAO · Deux axes résument {res2.inertie_pct.iloc[:2].sum():.0f} % de l'information",
                SORTIE / "05_fao_eboulis.png")
    fig_cercle(res2, "ACP FAO · Cercle des corrélations", SORTIE / "06_fao_cercle.png",
               "Le rendement baisse avec la chaleur et monte avec les pesticides (intensification)")
    # Les cultures se séparent surtout sur l'axe 3, celui que porte le rendement
    axe_cultures = res2.eta2_pct.loc["Crop"].idxmax()
    fig_qualitatives(res2, "ACP FAO · La culture compte dans les données réelles", SORTIE / "07_fao_cultures.png",
                     f"Axe {axe_cultures[1:]}, porté par le rendement : les cultures s'y séparent "
                     f"(la culture explique {res2.eta2_pct.loc['Crop', axe_cultures]:.0f} % de cet axe)",
                     axe=axe_cultures)

    # 3. Synthèse avec le modèle final
    synthese = tableau_synthese(ds1, fao)
    fig_synthese(synthese, SORTIE / "08_synthese_variables_cles.png")

    # Tableaux chiffrés, repris dans le rapport
    for nom, res in (("ds1", res1), ("fao", res2)):
        pd.DataFrame({"valeur_propre": res.valeurs_propres, "inertie_pct": res.inertie_pct,
                      "inertie_cumulee_pct": res.inertie_pct.cumsum()}).round(3).to_csv(SORTIE / f"{nom}_valeurs_propres.csv")
        res.correlations.round(3).to_csv(SORTIE / f"{nom}_correlations.csv")
        if res.eta2_pct is not None:
            res.eta2_pct.round(4).to_csv(SORTIE / f"{nom}_eta2_qualitatives.csv")
    synthese.to_csv(SORTIE / "synthese_variables_cles.csv")

    print(f"DS1 : {res1.n_individus:,} parcelles, inertie {res1.inertie_pct.round(1).tolist()}")
    print(f"FAO : {res2.n_individus:,} observations, inertie {res2.inertie_pct.round(1).tolist()}")
    print(res1.correlations.iloc[:, :3].round(2))
    print(res2.correlations.iloc[:, :3].round(2))
    print(res1.eta2_pct.round(4))
    print(res2.eta2_pct.round(2))
    print(synthese)
    print(f"Figures et tableaux : {SORTIE}")


if __name__ == "__main__":
    main()
