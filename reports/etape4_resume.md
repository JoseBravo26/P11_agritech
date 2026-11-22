# Étape 4 — Résumé de l'interface Streamlit

*Document destiné à alimenter le rapport métier final. Code : `frontend/app.py`. Mode d'emploi : `frontend/README.md`. Tests : `tests/test_front.py`. Lancement complet : `docker-compose.yml` à la racine.*

## 1. Ce que fait l'interface

C'est la partie visible du projet pour l'utilisateur final. Une page web où l'agriculteur décrit sa parcelle et obtient, en un clic :
- en mode **Prédiction**, le rendement attendu d'une culture choisie ;
- en mode **Recommandation**, la comparaison des quatre cultures (maïs, riz, soja, blé).

L'interface **ne contient aucune logique de Machine Learning** : elle interroge l'API de l'étape 3 (`/predict`, `/recommend`, `/health`) et met ses réponses en forme. Le modèle peut donc être mis à jour sans toucher à l'interface.

## 2. Ce qui est demandé dans la consigne, et où le trouver

| Demande | Réalisation |
|---|---|
| Choisir entre « Prédiction » et « Recommandation » | Choix dans la barre latérale |
| Sliders et champs de saisie pour le contexte | Curseurs température et pluie, liste de niveaux de pesticides et champ de valeur personnalisée, interrupteurs engrais et irrigation, choix de la culture |
| Un bouton pour interroger l'API | Bouton « Lancer la prédiction / la recommandation » |
| Un chiffre clair pour la prédiction | Rendement (t/ha), marge estimée (USD/ha) et seuil de rentabilité, avec un message rentable ou non |
| Un graphique à barres et un tableau pour la recommandation | Barres horizontales colorées selon la rentabilité, et tableau classé avec rang, rendement, marge, seuil |
| `requirements.txt` | `frontend/requirements.txt` (Streamlit, Requests, pandas, Altair, versions figées) |

## 3. Choix de conception

- **Les curseurs sont bornés aux plages d'entraînement** (15 – 40 °C, 100 – 1 000 mm), les mêmes que celles contrôlées par l'API. L'utilisateur ne peut pas demander une extrapolation.
- **Pesticides présentés comme un niveau d'intensification du pays.** Le modèle utilise un total national de pesticides, un chiffre qu'aucun agriculteur ne connaît. L'interface propose quatre niveaux tirés du jeu de données : faible, médian, élevé, très élevé (25 %, 50 %, 75 % et 90 % des pays-années). Une valeur personnalisée reste possible.
- **Formulaire** : les réglages n'appellent pas l'API à chaque mouvement de curseur, seulement au clic.
- **Tri au choix** en recommandation : par rendement (consigne) ou par marge (objectif métier). Un message signale quand la meilleure culture en rendement n'est pas la plus rentable.
- **Noms de cultures en français** et explication des chiffres (« Comment lire ces chiffres ? »). Elle rappelle que prix et coûts sont des hypothèses, à remplacer par ceux de l'exploitation.
- **Robustesse** :
  - l'état de l'API est affiché en permanence ;
  - une API injoignable, une réponse trop lente ou une entrée refusée donnent un message clair, jamais une erreur technique.

## 4. Exemple

À 25 °C, 600 mm de pluie, intensification médiane, avec engrais et sans irrigation, l'interface affiche les mêmes chiffres que l'API (voir étape 3).
- **Prédiction pour le maïs** : 2,27 t/ha, marge de 130 USD/ha, seuil de 1,62 t/ha, culture rentable.
- **Recommandation** : riz en tête.
  - Classement par rendement : riz, blé, maïs, soja.
  - Classement par marge : riz, soja, blé, maïs.

## 5. Déploiement

- **Une commande lance tout** : `docker compose up --build`. Deux conteneurs démarrent :
  - l'API, image de l'étape 3 ;
  - l'interface, nouvelle image `agritech-front` d'environ 800 Mo, sans bibliothèque de ML, avec un utilisateur non administrateur et un contrôle de santé.
- L'interface **attend que l'API soit prête** (modèle chargé) avant de démarrer. Elle la joint par le réseau interne de Docker (`http://api:8000`).
- Les ports publiés sont réglables (`API_PORT`, `FRONT_PORT`), utile quand un autre service occupe déjà le port 8000.
- Interface : http://localhost:8501. API : http://localhost:8000/docs.

## 6. Tests

- **7 tests automatisés de l'interface**, avec le module de test de Streamlit. L'API y est simulée : on vérifie ce qui est envoyé et ce qui est affiché.
  - ce qui est envoyé : contenu de la requête, tri par marge, valeur personnalisée de pesticides ;
  - ce qui est affiché : chiffres, graphique, tableau, messages d'erreur.
- **Avec les 14 tests de l'API : 21 tests, tous réussis.**
- **Vérification manuelle dans le navigateur** :
  - en local, les deux modes et les deux tris ;
  - avec Docker Compose, les deux conteneurs sont déclarés en bonne santé et l'interface affiche « API connectée ».

## 7. Limites

- **Une parcelle à la fois** : pas d'import de fichier pour simuler plusieurs parcelles.
- **Pas de carte ni de données météo automatiques** : l'utilisateur saisit lui-même température et pluie.
- **Pas d'authentification** : adapté à une démonstration ou à un réseau interne.
- **Prix et coûts non modifiables dans l'interface** : ils se changent dans `src/economie.py`. Une évolution utile serait de les saisir directement dans l'interface.
