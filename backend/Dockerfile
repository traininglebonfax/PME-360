FROM python:3.14-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN useradd --create-home --uid 10001 app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
USER app
EXPOSE 8000
# Migrations appliquées par une étape de déploiement dédiée (expand → migrate → contract), pas au démarrage.
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--access-logfile", "-"]
