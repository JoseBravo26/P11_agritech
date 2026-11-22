"""Test d'intégration de bout en bout sur les conteneurs Docker (étape 5).

Il interroge l'API et l'interface réellement lancées (docker compose up) et
s'arrête avec un code d'erreur au premier problème, ce qui fait échouer le
pipeline CI/CD.

Utilisation (les conteneurs tournant déjà) :
    python scripts/smoke_test.py --api http://localhost:8000 --front http://localhost:8501

Seule la bibliothèque standard est utilisée : aucun paquet à installer.
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

PARCELLE = {"Rainfall_mm": 600, "Temperature_Celsius": 25, "Pesticides_tonnes": 3270,
            "Fertilizer_Used": True, "Irrigation_Used": False}


def appeler(url: str, donnees: dict | None = None) -> tuple[int, str]:
    """Envoie une requête GET (ou POST si des données sont fournies) et renvoie (code, texte)."""
    corps = json.dumps(donnees).encode() if donnees is not None else None
    requete = urllib.request.Request(url, data=corps, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(requete, timeout=15) as reponse:
            return reponse.status, reponse.read().decode()
    except urllib.error.HTTPError as erreur:
        return erreur.code, erreur.read().decode()


def attendre(url: str, delai_max_s: int = 90) -> None:
    """Attend qu'un service réponde, le temps que le modèle soit chargé."""
    debut = time.time()
    while time.time() - debut < delai_max_s:
        try:
            if appeler(url)[0] == 200:
                return
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            pass
        time.sleep(2)
    sys.exit(f"ÉCHEC : {url} ne répond pas après {delai_max_s} s")


def verifier(condition: bool, message: str) -> None:
    print(("OK     " if condition else "ÉCHEC  ") + message)
    if not condition:
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--front", default="http://localhost:8501")
    args = parser.parse_args()

    # 1. L'API démarre et a chargé son modèle
    attendre(f"{args.api}/health")
    code, texte = appeler(f"{args.api}/health")
    verifier(code == 200 and json.loads(texte)["statut"] == "ok", "API : /health répond, modèle chargé")

    # 2. Une recommandation complète et cohérente
    code, texte = appeler(f"{args.api}/recommend", PARCELLE)
    reponse = json.loads(texte) if code == 200 else {}
    cultures = [c["culture"] for c in reponse.get("classement", [])]
    verifier(code == 200 and sorted(cultures) == ["Maize", "Rice", "Soybean", "Wheat"],
             f"API : /recommend classe les 4 cultures ({', '.join(cultures)})")

    # 3. Une entrée hors plage est refusée (le contrôle des données fonctionne)
    code, _ = appeler(f"{args.api}/predict", {**PARCELLE, "Crop": "Rice", "Temperature_Celsius": 60})
    verifier(code == 422, "API : une température de 60 °C est refusée (422)")

    # 4. L'interface Streamlit est en ligne
    attendre(f"{args.front}/_stcore/health")
    verifier(appeler(f"{args.front}/_stcore/health")[0] == 200, "Interface : Streamlit répond")

    print("Test d'intégration réussi.")


if __name__ == "__main__":
    main()
