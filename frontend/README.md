# Étape 4 — Interface Streamlit

`app.py` est le front-end d'Agritech Answers. Il ne contient **aucune logique de Machine Learning** : il envoie le contexte de la parcelle à l'API FastAPI de l'étape 3 (`api/`) et affiche ses réponses.

## Ce que permet l'interface

- **Choisir le mode** dans la barre latérale :
  - **Prédiction** : rendement d'une culture choisie ;
  - **Recommandation** : comparaison des quatre cultures.
- **Décrire la parcelle** :
  - curseurs pour la température (15 – 40 °C) et la pluie (100 – 1 000 mm), limités aux plages d'entraînement du modèle ;
  - **pays de l'exploitation** (101 pays de la FAO) : l'interface en déduit l'usage national de pesticides, c'est-à-dire le niveau d'intensification agricole. L'agriculteur n'a pas à connaître ce chiffre ;
  - si le pays n'est pas dans la liste : niveau d'intensification prédéfini (tiré des quantiles du jeu de données) ou valeur personnalisée ;
  - interrupteurs pour l'engrais et l'irrigation.
- **Lancer la requête** avec un bouton. Les réglages sont regroupés dans un formulaire : l'API n'est appelée qu'au clic.
- **Lire les résultats** :
  - en prédiction, trois chiffres clairs (rendement, marge estimée, seuil de rentabilité) et un message rentable ou non ;
  - en recommandation, un graphique à barres (vert si rentable, rouge sinon) et un tableau classé. Le tri se fait par rendement ou par marge.
- **État de l'API** dans la barre latérale : connectée ou non, et performance du modèle. Une API injoignable ou une entrée refusée (erreur 422) donne un message lisible, pas une erreur Python.

### Pays et niveaux de pesticides

Le modèle utilise l'usage **national** de pesticides (tonnes par an), un indicateur du niveau d'intensification de l'agriculture du pays. Ce n'est pas la quantité épandue sur la parcelle : un agriculteur ne connaît pas ce chiffre.

**L'interface demande donc le pays.** La valeur vient de `pays_pesticides.json` (FAO, année 2013, 101 pays), produit par `scripts/generer_pays_pesticides.py` à partir du jeu *Crop Yield Prediction*. Le niveau correspondant est affiché en clair, par exemple « France : parmi les plus élevés ».

Si le pays n'est pas dans la liste, l'utilisateur choisit un niveau :

| Niveau | Tonnes | Repère dans le jeu de données |
|---|---|---|
| Faible | 470 | 25 % des pays-années en dessous |
| Médian | 3 270 | médiane |
| Élevé | 14 200 | 75 % en dessous |
| Très élevé | 40 700 | 90 % en dessous |

## Lancer l'interface

### Avec Docker Compose (API et interface ensemble)

Depuis la racine du projet :

```bash
docker compose up --build
```

Puis ouvrir http://localhost:8501 pour l'interface. La documentation de l'API reste sur http://localhost:8000/docs. L'interface attend que l'API ait chargé son modèle avant de démarrer.

Si le port 8000 est déjà utilisé sur la machine, changer seulement le port publié de l'API, l'interface continuant à la joindre en interne :

```bash
API_PORT=8002 docker compose up --build
```

Sous PowerShell : `$env:API_PORT='8002'; docker compose up --build`.

Arrêter avec `docker compose down`.

### En local, sans Docker

L'API doit tourner (voir `api/README.md`). Depuis la racine du projet :

```bash
.venv/Scripts/python -m pip install -r frontend/requirements.txt
```

```bash
.venv/Scripts/python -m streamlit run frontend/app.py
```

L'interface cherche l'API sur `http://localhost:8000`. Pour une autre adresse, définir la variable d'environnement `API_URL`, par exemple `API_URL=http://127.0.0.1:8001`.

## Tests

```bash
.venv/Scripts/python -m pytest tests/test_front.py -q
```

Les 8 tests simulent l'API, sans lancer de serveur. Ils vérifient :
- la page initiale, qui ne lance aucune prédiction ;
- les données envoyées à `/predict` et les trois chiffres affichés ;
- le graphique et le tableau de recommandation, avec les noms de cultures en français et le classement ;
- la transmission du tri par marge ;
- la valeur de pesticides personnalisée ;
- l'affichage lisible d'une erreur 422 et d'une API injoignable.
