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
| Sliders et champs de saisie pour le contexte | Choix du pays de l'exploitation, curseurs température et pluie, interrupteurs engrais et irrigation, choix de la culture. Si le pays n'est pas dans la liste : niveau de pesticides ou valeur personnalisée |
| Un bouton pour interroger l'API | Bouton « Lancer la prédiction / la recommandation » |
| Un chiffre clair pour la prédiction | Rendement (t/ha), marge estimée (USD/ha) et seuil de rentabilité, avec un message rentable ou non |
| Un graphique à barres et un tableau pour la recommandation | Barres horizontales colorées selon la rentabilité, et tableau classé avec rang, rendement, marge, seuil |
| `requirements.txt` | `frontend/requirements.txt` (Streamlit, Requests, pandas, Altair, versions figées) |

## 3. Choix de conception

- **Les curseurs sont bornés aux plages d'entraînement** (15 – 40 °C, 100 – 1 000 mm), les mêmes que celles contrôlées par l'API. L'utilisateur ne peut pas demander une extrapolation.
- **Pesticides : l'agriculteur choisit simplement son pays.** Le modèle utilise un total national de pesticides, un chiffre qu'aucun agriculteur ne connaît.
  - L'interface demande donc le **pays de l'exploitation** (101 pays, noms en français). Elle retrouve seule la valeur FAO la plus récente (2013) et l'affiche comme information, avec le niveau d'intensification correspondant (par exemple France : 66 497 t, parmi les plus élevés).
  - Les valeurs viennent de `frontend/pays_pesticides.json`, produit par `scripts/generer_pays_pesticides.py` à partir du jeu FAO.
  - Pour un pays absent de la liste (« Autre pays »), l'interface propose quatre niveaux tirés du jeu de données : faible, médian, élevé, très élevé (25 %, 50 %, 75 % et 90 % des pays-années). Une valeur personnalisée reste possible.
- **Formulaire** : les réglages n'appellent pas l'API à chaque mouvement de curseur, seulement au clic.
- **Tri au choix** en recommandation : par rendement (consigne) ou par marge (objectif métier). Un message signale quand la meilleure culture en rendement n'est pas la plus rentable.
- **Noms de cultures en français** et explication des chiffres (« Comment lire ces chiffres ? »). Elle rappelle que prix et coûts sont des hypothèses, à remplacer par ceux de l'exploitation.
- **Robustesse** :
  - l'état de l'API est affiché en permanence ;
  - une API injoignable, une réponse trop lente ou une entrée refusée donnent un message clair, jamais une erreur technique ;
  - l'interface attend jusqu'à 60 secondes la réponse de l'API, le temps que l'API hébergée gratuitement sur Render sorte de veille.

## 4. Exemple

À 25 °C, 600 mm de pluie, « Autre pays » avec intensification médiane, avec engrais et sans irrigation, l'interface affiche les mêmes chiffres que l'API (voir étape 3).
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
- **En ligne** (mis en place à l'étape 5) :

| Service | Adresse |
|---|---|
| Interface (Streamlit Community Cloud) | https://p11-agritech-answers.streamlit.app |
| API (Render, offre gratuite) | https://agritech-api-usx2.onrender.com/docs |

## 6. Tests

- **8 tests automatisés de l'interface**, avec le module de test de Streamlit. L'API y est simulée : on vérifie ce qui est envoyé et ce qui est affiché.
  - ce qui est envoyé : contenu de la requête, tri par marge, valeur personnalisée de pesticides, valeur FAO du pays choisi (France) ;
  - ce qui est affiché : chiffres, graphique, tableau, information sur le pays, messages d'erreur.
- **Avec les 14 tests de l'API : 22 tests.** Le projet en compte 49 au total (calcul économique et modèle compris), tous réussis et relancés à chaque modification par le pipeline de l'étape 5.
- **Vérification manuelle dans le navigateur** :
  - en local, les deux modes et les deux tris ;
  - avec Docker Compose, les deux conteneurs sont déclarés en bonne santé et l'interface affiche « API connectée » ;
  - en ligne, l'application affiche « API connectée » et le choix « Pays de l'exploitation ».

## 7. Limites

- **Une parcelle à la fois** : pas d'import de fichier pour simuler plusieurs parcelles.
- **Pas de carte ni de données météo automatiques** : l'utilisateur saisit lui-même température et pluie.
- **Pesticides figés en 2013** : dernière année du jeu FAO. Une mise à jour avec des données FAO plus récentes demanderait de régénérer `pays_pesticides.json`.
- **Pas d'authentification** : adapté à une démonstration ou à un réseau interne.
- **Lenteur au premier appel en ligne** : l'API gratuite se met en veille, le réveil prend environ une minute.
- **Prix et coûts non modifiables dans l'interface** : ils se changent dans `src/economie.py`. Une évolution utile serait de les saisir directement dans l'interface.
