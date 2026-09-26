FROM python:3.14-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
# Bibliothèques natives de WeasyPrint (rendu des rapports PDF) et polices avec accents.
RUN apt-get update     && apt-get install -y --no-install-recommends libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b fonts-dejavu-core     && rm -rf /var/lib/apt/lists/*
RUN useradd --create-home --uid 10001 app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
USER app
EXPOSE 8000
# Migrations appliquées par une étape de déploiement dédiée (expand → migrate → contract), pas au démarrage.
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--access-logfile", "-"]
