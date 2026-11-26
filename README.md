# Agritech Answers — Recommandation de cultures

[![CI/CD](https://github.com/JoseBravo26/P11_agritech/actions/workflows/ci-cd.yml/badge.svg?branch=main)](https://github.com/JoseBravo26/P11_agritech/actions/workflows/ci-cd.yml)
[![Docker Hub](https://img.shields.io/docker/v/josibra/agritech-api?label=Docker%20Hub&logo=docker&sort=date)](https://hub.docker.com/r/josibra/agritech-api)
![Python](https://img.shields.io/badge/python-3.13-blue?logo=python&logoColor=white)
![Tests](https://img.shields.io/badge/tests-48-brightgreen)

Application web qui aide un agriculteur à choisir sa culture :
- **Prédiction** : rendement attendu d'une culture sur sa parcelle ;
- **Recommandation** : les quatre cultures (maïs, riz, soja, blé) simulées et classées par rendement ou par marge.

## Application en ligne

| Service | Adresse | Hébergement |
|---|---|---|
| Interface | https://p11-agritech-answers.streamlit.app | Streamlit Community Cloud, redéployée à chaque push sur `main` |
| API | https://agritech-api-usx2.onrender.com/docs | Render, offre gratuite, image `josibra/agritech-api:latest` |

L'API gratuite se met en veille après une période sans visite : la première requête peut alors prendre environ une minute.

## Architecture

| Brique | Dossier | Rôle |
|---|---|---|
| Préparation et entraînement | `src/`, `notebooks/` | Fusion des deux jeux de données, modèle de forêt aléatoire, suivi MLflow |
| API (back-end) | `api/` | FastAPI : `/predict`, `/recommend`, `/health`, `/hypotheses` |
| Interface (front-end) | `frontend/` | Streamlit, sans logique de Machine Learning, interroge l'API |
| Pipeline CI/CD | `.github/workflows/` | Tests, build Docker, déploiement sur Docker Hub |
| Rapports | `reports/` | Résumés métier de chaque étape, captures MLflow, schéma du pipeline |

## Démarrage rapide

```bash
docker compose up --build
```

Puis ouvrir l'interface sur http://localhost:8501. La documentation de l'API est sur http://localhost:8000/docs.

## Documentation

- API : [api/README.md](api/README.md)
- Interface : [frontend/README.md](frontend/README.md)
- Pipeline CI/CD (workflows, déclencheurs, secrets, badges) : [docs/CI_CD.md](docs/CI_CD.md)
- Résumés métier : [reports/](reports/)

## Données

Les jeux de données ne sont pas dans le dépôt (taille). Ils sont à télécharger sur Kaggle (« Agriculture Crop Yield » et « Crop Yield Prediction Dataset ») et à placer dans les dossiers de même nom à la racine, pour relancer les notebooks. L'API et le pipeline CI/CD n'en ont pas besoin : ils utilisent le modèle déjà entraîné (`models/`).

## Tests

```bash
python -m pytest tests -v
```
