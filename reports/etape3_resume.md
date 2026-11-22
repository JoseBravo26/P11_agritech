# Étape 3 — Résumé de l'API de prédiction et de recommandation

*Document destiné à alimenter le rapport métier final. Code : `api/main.py`. Mode d'emploi détaillé : `api/README.md`. Tests : `tests/test_api.py`. Conteneur : `Dockerfile` à la racine.*

## 1. Ce que fait l'API

L'API rend le modèle de l'étape 2 utilisable par une autre application (l'interface Streamlit de l'étape 4, ou tout outil du client). Elle répond à deux questions métier :

- **« Quel rendement puis-je attendre pour cette culture sur ma parcelle ? »** → `POST /predict`
- **« Quelle culture choisir sur ma parcelle ? »** → `POST /recommend`, qui simule les quatre cultures (maïs, riz, soja, blé) et les classe.

Pour chaque culture, la réponse donne le **rendement prédit (t/ha)**, la **marge estimée (USD/ha)**, le **seuil de rentabilité (t/ha)** et un indicateur **rentable oui/non**.

## 2. Points d'accès

| Méthode | URL | Rôle |
|---|---|---|
| `POST` | `/predict` | Rendement, marge et seuil de rentabilité d'**une** culture |
| `POST` | `/recommend` | **Toutes** les cultures, triées par rendement décroissant (par défaut) ou par marge (`?tri=marge`) |
| `GET` | `/health` | État du service, variables attendues, identifiant du run MLflow et métriques de test du modèle |
| `GET` | `/hypotheses` | Prix et coûts utilisés pour la marge, avec leurs sources |
| `GET` | `/docs` | Documentation interactive (Swagger), générée automatiquement. La racine `/` y redirige |

## 3. Entrées et contrôle des données

| Champ | Plage acceptée | Sens |
|---|---|---|
| `Crop` (`/predict` seulement) | Maize, Rice, Soybean, Wheat | Culture envisagée |
| `Rainfall_mm` | 100 – 1 000 | Pluie sur la saison (mm) |
| `Temperature_Celsius` | 15 – 40 | Température moyenne (°C) |
| `Pesticides_tonnes` | 0 – 400 000 | Usage national de pesticides, indicateur du niveau d'intensification du pays (médiane 3 270) |
| `Fertilizer_Used` | oui / non | Engrais appliqué |
| `Irrigation_Used` | oui / non | Parcelle irriguée |

- **Les plages sont celles du jeu d'entraînement.** Hors de ces plages, le modèle extrapolerait sans garantie : l'API refuse donc la requête (erreur **422** avec un message explicite) plutôt que de renvoyer un chiffre trompeur.
- Une culture inconnue, un champ manquant ou une valeur du mauvais type sont aussi refusés.

## 4. Exemple

Parcelle à 25 °C, 600 mm de pluie, intensification médiane, avec engrais, sans irrigation :

| Culture | Rendement (t/ha) | Marge (USD/ha) | Seuil de rentabilité (t/ha) |
|---|---|---|---|
| **Riz** | **5,29** | **655** | 2,89 |
| Blé | 2,36 | 263 | 1,27 |
| Maïs | 2,27 | 130 | 1,63 |
| Soja | 1,65 | 426 | 0,62 |

- **Classement par rendement (par défaut, comme demandé dans la consigne) :** riz, blé, maïs, soja.
- **Classement par marge :** riz, soja, blé, maïs. Le soja, dernier en tonnes, est deuxième en revenu, car il se vend environ deux fois plus cher à la tonne.
- C'est pourquoi la réponse indique toujours, en plus de la première culture du classement, la **culture la plus rentable**.

## 5. Choix de conception

- **Tri par rendement par défaut, marge toujours affichée.** La consigne demande un classement par rendement ; l'objectif métier du client est la culture la plus rentable. L'API fournit les deux sans obliger à choisir.
- **Modèle chargé une seule fois au démarrage**, pas à chaque requête : réponse rapide.
- **`/predict` et `/recommend` utilisent le même calcul** : une culture obtient exactement le même résultat dans les deux réponses (vérifié par les tests).
- **Hypothèses économiques séparées du modèle** (`src/economie.py`) : prix Banque mondiale 2025 et coûts USDA 2025 ajustés (voir étape 2). Le client peut les remplacer par ses propres chiffres **sans réentraîner** le modèle. `/hypotheses` les rend visibles, sources comprises.
- **Image légère en dépendances** : l'API n'importe que la partie économique du projet, pas le code d'entraînement. MLflow n'est donc pas embarqué dans le conteneur.
- **Versions figées** (`api/requirements.txt`) : le modèle sérialisé doit être rechargé avec la version de scikit-learn qui l'a entraîné (1.9.1), sinon il peut être illisible ou donner d'autres résultats.
- **Traçabilité** : `/health` renvoie l'identifiant du run MLflow du modèle servi (`C_modele_final`, modèle enregistré `rendement_cultures` version 1) et ses métriques de test (R² 0,76, rentabilité bien classée 84 %).

## 6. Déploiement avec Docker

- **Image** `agritech-api` : Python 3.13 allégé, environ 750 Mo, dont 37 Mo pour le modèle (compressé à l'étape 5 ; 104 Mo auparavant, mêmes prédictions).
- **Bonnes pratiques appliquées :**
  - l'application tourne avec un **utilisateur non administrateur** ;
  - un **contrôle de santé** interroge `/health` régulièrement ;
  - un fichier `.dockerignore` exclut données brutes, notebooks, rapports, base MLflow et environnement virtuel.
- **Lancement :** `docker build -t agritech-api .` puis `docker run -p 8000:8000 agritech-api`, puis ouvrir http://localhost:8000.
- **Point d'attention rencontré :** l'adresse `0.0.0.0:8000` affichée au démarrage est l'adresse d'**écoute** du serveur, pas une adresse à ouvrir dans le navigateur. Il faut utiliser `localhost:8000`. Pour éviter une page vide, la racine redirige désormais vers la documentation `/docs`. C'est documenté dans `api/README.md`.

## 7. Tests

**14 tests automatisés** (`python -m pytest tests -q`), tous réussis. Ils vérifient :

- la redirection de la racine vers la documentation et l'état du service ;
- qu'une prédiction est plausible et que la marge correspond au calcul attendu ;
- la cohérence entre `/predict` et `/recommend` ;
- l'ordre des deux tris (rendement et marge) ;
- un comportement agronomique attendu : **l'engrais augmente le rendement** ;
- le rejet des entrées invalides : culture inconnue, valeur hors plage, mauvais type, champ manquant, tri inconnu.

L'image Docker a aussi été construite et testée : conteneur déclaré en bonne santé, réponses identiques à celles du lancement local.

## 8. Suivi des expériences (MLflow)

Le README de l'API explique aussi comment ouvrir l'interface MLflow (`mlflow ui` sur `sqlite:///mlflow.db`, port 5000) pour retrouver les 28 runs de l'étape 2 et le modèle enregistré que sert l'API.

## 9. Limites et suites

- **`Pesticides_tonnes` est un total national**, pas une quantité épandue sur la parcelle. Il mesure le niveau d'intensification du pays. L'interface de l'étape 4 devra l'expliquer ou proposer des niveaux prédéfinis (faible, médian, élevé).
- **Les prix et coûts restent des hypothèses** : sourcées, mais à remplacer par les chiffres réels du client. Le coût d'irrigation (200 USD/ha) n'est pas sourcé.
- **Pas d'authentification ni de limitation de débit** : adapté à une démonstration ou à un réseau interne, à ajouter avant une mise en ligne publique.
- **Étape suivante :** interface Streamlit qui appelle cette API (les deux services pouvant être lancés ensemble avec docker-compose).
