# Étape 3 — API de prédiction et de recommandation

L'API charge le modèle de l'étape 2 (`models/modele_rendement.joblib`, forêt aléatoire, R² 0,76 sur le jeu de test) et l'expose avec FastAPI.

## Points d'accès

| Méthode | URL | Rôle |
|---|---|---|
| `POST` | `/predict` | Rendement prédit (t/ha) d'**une** culture sur la parcelle, avec la marge estimée et le seuil de rentabilité |
| `POST` | `/recommend` | **Toutes** les cultures simulées sur la parcelle, triées par rendement prédit décroissant. Avec `?tri=marge`, triées par marge décroissante |
| `GET` | `/health` | État du service, variables attendues et métriques de test du modèle |
| `GET` | `/hypotheses` | Prix et coûts utilisés pour la marge, avec leurs sources |
| `GET` | `/docs` | Documentation interactive (Swagger), générée automatiquement |

### Entrées

| Champ | Type | Plage acceptée | Sens |
|---|---|---|---|
| `Crop` (`/predict` seulement) | `Maize`, `Rice`, `Soybean`, `Wheat` | — | Culture envisagée |
| `Rainfall_mm` | nombre | 100 – 1 000 | Pluie sur la saison (mm) |
| `Temperature_Celsius` | nombre | 15 – 40 | Température moyenne (°C) |
| `Pesticides_tonnes` | nombre | 0 – 400 000 | Usage national de pesticides : niveau d'intensification du pays (médiane 3 270) |
| `Fertilizer_Used` | booléen | — | Engrais appliqué |
| `Irrigation_Used` | booléen | — | Parcelle irriguée |

Les plages sont celles du jeu d'entraînement. Une valeur hors plage, un champ manquant ou une culture inconnue renvoie une erreur **422** avec le détail du problème, plutôt qu'une prédiction extrapolée.

### Exemple

```bash
curl -X POST http://127.0.0.1:8000/recommend -H "Content-Type: application/json" \
  -d '{"Rainfall_mm": 600, "Temperature_Celsius": 25, "Pesticides_tonnes": 3270, "Fertilizer_Used": true, "Irrigation_Used": false}'
```

Réponse (extrait) :

```json
{"tri": "rendement", "meilleure_culture": "Rice", "culture_la_plus_rentable": "Rice",
 "classement": [
   {"culture": "Rice",    "rendement_t_ha": 5.287, "marge_usd_ha": 654.9, "seuil_rentabilite_t_ha": 2.89,  "rentable": true},
   {"culture": "Wheat",   "rendement_t_ha": 2.356, "marge_usd_ha": 263.3, "seuil_rentabilite_t_ha": 1.274, "rentable": true},
   {"culture": "Maize",   "rendement_t_ha": 2.266, "marge_usd_ha": 130.3, "seuil_rentabilite_t_ha": 1.625, "rentable": true},
   {"culture": "Soybean", "rendement_t_ha": 1.649, "marge_usd_ha": 426.3, "seuil_rentabilite_t_ha": 0.62,  "rentable": true}]}
```

Le soja arrive dernier en rendement mais deuxième en marge : c'est pourquoi la réponse donne aussi `culture_la_plus_rentable` et accepte `?tri=marge`.

## Choix de conception

- **Tri par rendement par défaut**, comme demandé dans la consigne. La marge est ajoutée à chaque culture, car l'objectif métier est la culture **la plus rentable**.
- **Modèle chargé une seule fois** au démarrage, pas à chaque requête.
- **`/predict` et `/recommend` partagent le même calcul** : une culture a exactement le même résultat dans les deux réponses (vérifié par les tests).
- **Hypothèses économiques séparées** (`src/economie.py`) : on peut les remplacer par les chiffres du client sans réentraîner le modèle.
- **Versions figées** dans `api/requirements.txt` : le modèle sérialisé doit être rechargé avec la version de scikit-learn qui l'a entraîné (1.9.1).

## Lancer l'API

En local, depuis la racine du projet :

```bash
.venv/Scripts/python -m uvicorn api.main:app --reload
```

Avec Docker, depuis la racine du projet :

```bash
docker build -t agritech-api .
```

```bash
docker run -p 8000:8000 agritech-api
```

Puis ouvrir http://localhost:8000 (redirigé vers `/docs`). L'adresse `0.0.0.0` affichée par Uvicorn est l'adresse d'écoute du serveur, pas une adresse à ouvrir dans le navigateur.

## Consulter les expériences MLflow

Les entraînements de l'étape 2 sont tracés dans MLflow : base `mlflow.db` et artefacts dans `mlruns/`, à la racine du projet. Le modèle servi par l'API correspond au run `C_modele_final`, enregistré dans le registre sous `rendement_cultures` version 1.

Depuis la racine du projet :

```bash
.venv/Scripts/mlflow ui --backend-store-uri sqlite:///mlflow.db --host 127.0.0.1 --port 5000
```

Puis ouvrir http://localhost:5000 et choisir l'expérience `P11_rendement_cultures`. On y trouve trois runs parents :
- `A_comparaison_modeles` : les 5 modèles comparés en validation croisée ;
- `B_optimisation_RandomForestRegressor` : les 20 essais d'hyperparamètres ;
- `C_modele_final` : les métriques de test, les figures et le modèle enregistré.

Arrêter le serveur avec Ctrl+C. Deux interfaces MLflow ne peuvent pas tourner en même temps sur le port 5000.

## Tests

```bash
.venv/Scripts/python -m pytest tests -q
```

14 tests couvrent : redirection de la racine vers la documentation, état du service, prédiction plausible, calcul de la marge, cohérence entre `/predict` et `/recommend`, ordre des deux tris, effet de l'engrais, et rejet des entrées invalides (culture inconnue, valeur hors plage, mauvais type, champ manquant, tri inconnu).
