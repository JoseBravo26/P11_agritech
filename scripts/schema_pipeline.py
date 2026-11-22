"""Dessine le schéma du pipeline CI/CD pour le rapport métier (étape 5).

Sortie : reports/cicd/pipeline_cicd.png
Lancement : python scripts/schema_pipeline.py
"""

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

SORTIE = Path(__file__).resolve().parents[1] / "reports" / "cicd" / "pipeline_cicd.png"

# Palette sobre : un fond clair, une couleur par grande étape
FOND, TEXTE, GRIS = "#f7f8fa", "#1f2937", "#6b7280"
COULEURS = {"declencheur": "#475569", "tests": "#2563eb", "build": "#7c3aed",
            "deploy": "#059669", "alerte": "#dc2626", "cible": "#0f766e"}

# Chaque bloc : (x, y, largeur, hauteur, couleur, titre, détail)
BLOCS = {
    "push":   (0.3, 3.0, 2.2, 1.5, "declencheur", "Déclencheur",
               "push sur main\npull request\nlancement manuel"),
    "tests":  (3.3, 3.0, 2.6, 1.5, "tests", "1. Tests",
               "48 tests pytest\néconomie · modèle\nAPI · interface"),
    "build":  (6.7, 3.0, 2.8, 1.5, "build", "2. Build",
               "images Docker API + interface\ntest d'intégration\nsur les conteneurs"),
    "deploy": (10.3, 3.0, 2.6, 1.5, "deploy", "3. Déploiement",
               "publication sur\nDocker Hub\n(main seulement)"),
    "hub":    (10.3, 0.6, 2.6, 1.3, "cible", "Docker Hub",
               "agritech-api\nagritech-front"),
    "cloud":  (0.3, 0.6, 2.2, 1.3, "cible", "Streamlit Cloud",
               "redéploie l'interface\nà chaque push"),
    "alerte": (5.15, 0.6, 2.9, 1.3, "alerte", "Alerte",
               "ticket GitHub + e-mail\nsi une étape échoue"),
}


def bloc(ax, x, y, l, h, couleur, titre, detail):
    """Carte arrondie avec un bandeau de couleur et deux niveaux de texte."""
    ax.add_patch(FancyBboxPatch((x + 0.04, y - 0.06), l, h, boxstyle="round,pad=0.02,rounding_size=0.18",
                                fc="#000000", alpha=0.06, lw=0))                      # ombre douce
    ax.add_patch(FancyBboxPatch((x, y), l, h, boxstyle="round,pad=0.02,rounding_size=0.18",
                                fc="white", ec="#e5e7eb", lw=1.2))
    ax.add_patch(FancyBboxPatch((x, y + h - 0.42), l, 0.42, boxstyle="round,pad=0.02,rounding_size=0.18",
                                fc=couleur, ec=couleur, lw=0))                         # bandeau titre
    ax.text(x + l / 2, y + h - 0.21, titre, ha="center", va="center", color="white",
            fontsize=12, fontweight="bold")
    ax.text(x + l / 2, y + (h - 0.42) / 2, detail, ha="center", va="center", color=TEXTE,
            fontsize=9.5, linespacing=1.45)


def fleche(ax, depart, arrivee, couleur=GRIS, style="-", texte=None, courbe=0.0):
    ax.add_patch(FancyArrowPatch(depart, arrivee, arrowstyle="-|>", mutation_scale=16, lw=1.8,
                                 color=couleur, linestyle=style, connectionstyle=f"arc3,rad={courbe}"))
    if texte:
        ax.text((depart[0] + arrivee[0]) / 2, (depart[1] + arrivee[1]) / 2 + 0.18, texte,
                ha="center", fontsize=8.5, color=couleur, style="italic")


def main():
    fig, ax = plt.subplots(figsize=(13.5, 5.6), dpi=200)
    fig.patch.set_facecolor(FOND)
    ax.set_facecolor(FOND)
    ax.set_xlim(0, 13.2)
    ax.set_ylim(0, 5.4)
    ax.axis("off")

    for x, y, l, h, cle, titre, detail in BLOCS.values():
        bloc(ax, x, y, l, h, COULEURS[cle], titre, detail)

    # Enchaînement principal : chaque étape ne démarre que si la précédente réussit
    fleche(ax, (2.55, 3.75), (3.25, 3.75))
    fleche(ax, (5.95, 3.75), (6.65, 3.75), COULEURS["tests"], texte="si OK")
    fleche(ax, (9.55, 3.75), (10.25, 3.75), COULEURS["build"], texte="si OK")
    fleche(ax, (11.6, 2.95), (11.6, 1.95), COULEURS["deploy"])
    # Streamlit Cloud suit le dépôt GitHub, indépendamment des Actions
    fleche(ax, (1.4, 2.95), (1.4, 1.95), COULEURS["cible"], style="--")
    # Toute étape en échec déclenche l'alerte
    fleche(ax, (4.6, 2.95), (6.0, 1.95), COULEURS["alerte"], style="--", texte="échec")
    fleche(ax, (8.1, 2.95), (7.2, 1.95), COULEURS["alerte"], style="--")

    ax.text(0.3, 5.15, "Pipeline CI/CD — Agritech Answers", fontsize=17, fontweight="bold", color=TEXTE)
    ax.text(0.3, 4.78, "GitHub Actions · .github/workflows/ci-cd.yml · un échec arrête la chaîne et déclenche une alerte",
            fontsize=10, color=GRIS)

    SORTIE.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(SORTIE, bbox_inches="tight", facecolor=FOND)
    print(f"Schéma enregistré : {SORTIE}")


if __name__ == "__main__":
    main()
