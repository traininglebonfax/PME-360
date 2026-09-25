#!/bin/bash
# Création du rôle applicatif et de la base PME360.
# Le rôle applicatif n'est ni superutilisateur ni BYPASSRLS : les politiques RLS s'appliquent à lui.
# CREATEDB est nécessaire pour la base de test de Django.
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<-EOSQL
  CREATE ROLE ${PME360_DB_USER} LOGIN PASSWORD '${PME360_DB_PASSWORD}' NOSUPERUSER NOBYPASSRLS CREATEDB;
  CREATE DATABASE ${PME360_DB_NAME} OWNER ${PME360_DB_USER};
EOSQL

# Extensions installées dans template1 (héritées par la base de test) et dans la base applicative.
for db in template1 "${PME360_DB_NAME}"; do
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$db" <<-EOSQL
    CREATE EXTENSION IF NOT EXISTS pg_trgm;
    CREATE EXTENSION IF NOT EXISTS vector;
    CREATE EXTENSION IF NOT EXISTS citext;
EOSQL
done
