# Image de l'API de prédiction (étape 3)
# Construction : docker build -t agritech-api .
# Lancement    : docker run -p 8000:8000 agritech-api
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dépendances d'abord : cette couche reste en cache tant que requirements.txt ne change pas
COPY api/requirements.txt api/requirements.txt
RUN pip install -r api/requirements.txt

# Code de l'API, hypothèses économiques et modèle entraîné
COPY src/__init__.py src/economie.py src/
COPY api/ api/
COPY models/modele_rendement.joblib models/modele_rendement.json models/

# Utilisateur sans privilèges
RUN useradd --create-home appuser
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
