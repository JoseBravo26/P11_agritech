"""Captures d'écran de l'interface en ligne, pour le rapport métier.

Utilise Playwright avec le navigateur Edge installé sur la machine (aucun
navigateur à télécharger). Les deux modes de l'application sont joués comme
le ferait un utilisateur : réglages par défaut, clic sur le bouton, attente du
résultat, capture.

Sorties : reports/app/01_prediction.png et reports/app/02_recommandation.png
Lancement : python scripts/captures_interface.py [adresse de l'application]
"""

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ADRESSE = sys.argv[1] if len(sys.argv) > 1 else "https://p11-agritech-answers.streamlit.app"
SORTIE = Path(__file__).resolve().parents[1] / "reports" / "app"
ATTENTE_MS = 120_000   # l'API gratuite peut mettre une minute à se réveiller


def main() -> None:
    SORTIE.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        navigateur = p.chromium.launch(channel="msedge", headless=True)
        page = navigateur.new_page(viewport={"width": 1400, "height": 1250}, device_scale_factor=2,
                                   color_scheme="dark")
        # Sur Streamlit Community Cloud, l'application elle-même est servie sous /~/+/
        suffixe = "/~/+/" if "streamlit.app" in ADRESSE else "/"
        page.goto(ADRESSE.rstrip("/") + suffixe, wait_until="networkidle", timeout=ATTENTE_MS)
        page.get_by_text("API connectée").wait_for(timeout=ATTENTE_MS)

        # Le pays de l'exploitation est choisi dans la liste : on prend la France
        page.locator('[data-testid="stSelectbox"]').first.click()   # la liste des pays est la première
        page.keyboard.type("France")
        page.keyboard.press("Enter")
        page.get_by_text("Intensification agricole").wait_for(timeout=ATTENTE_MS)

        # 1. Mode prédiction (réglages par défaut : maïs, 25 °C, 600 mm, engrais)
        page.get_by_role("button", name="Lancer la prédiction").click()
        page.get_by_text("Résultat pour").wait_for(timeout=ATTENTE_MS)
        page.wait_for_timeout(1500)
        # Recadrée sur le contenu : le bas de la page est vide en mode prédiction
        page.screenshot(path=SORTIE / "01_prediction.png", clip={"x": 0, "y": 0, "width": 1400, "height": 970})

        # 2. Mode recommandation (mêmes conditions, tri par rendement)
        page.get_by_text("Recommandation", exact=True).click()
        page.get_by_role("button", name="Lancer la recommandation").click()
        # Le tableau est dessiné en canvas : on attend le message de recommandation qui le précède
        page.get_by_text("Culture recommandée").or_(page.get_by_text("Meilleure culture")).wait_for(timeout=ATTENTE_MS)
        page.wait_for_timeout(2500)   # laisse le graphique se dessiner
        page.screenshot(path=SORTIE / "02_recommandation.png")

        navigateur.close()
    print(f"Captures enregistrées dans {SORTIE}")


if __name__ == "__main__":
    main()
