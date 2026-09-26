#!/usr/bin/env bash
# Réglages communs des sauvegardes PME360 (Document 2, § « Sauvegardes »).
set -euo pipefail

BACKUP_ROOT="${PME360_BACKUP_ROOT:-/backups}"
DB_HOST="${PME360_BACKUP_DB_HOST:-postgres}"
DB_NAME="${PME360_BACKUP_DB_NAME:-pme360}"
DB_USER="${PME360_BACKUP_DB_USER:-postgres}"
RETENTION_DAYS="${PME360_BACKUP_RETENTION_DAYS:-30}"
export PGPASSWORD="${PME360_BACKUP_DB_PASSWORD:?mot de passe PostgreSQL requis}"
export PGHOST="$DB_HOST" PGUSER="$DB_USER"

if [ -z "${PME360_BACKUP_PASSPHRASE:-}" ]; then
  echo "PME360_BACKUP_PASSPHRASE manquante : aucune sauvegarde non chiffrée n'est produite." >&2
  exit 1
fi
if [ "${PME360_ENV:-dev}" = "prod" ] && [ "${PME360_BACKUP_PASSPHRASE}" = "backup-dev-only" ]; then
  echo "Phrase de chiffrement de développement interdite en production." >&2
  exit 1
fi

mkdir -p "$BACKUP_ROOT/daily" "$BACKUP_ROOT/base" "$BACKUP_ROOT/wal" "$BACKUP_ROOT/restore-tests"

log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

encrypt() { openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt -pass env:PME360_BACKUP_PASSPHRASE; }
decrypt() { openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass env:PME360_BACKUP_PASSPHRASE; }

# Volumes de référence (comptés en superutilisateur : la RLS ne limite pas le comptage).
KEY_TABLES="organization pme diagnostic score_snapshot document document_version action_plan action report audit_log"

table_counts() {
  local db="$1" out="" n
  for t in $KEY_TABLES; do
    n=$(psql -d "$db" -tAc "SELECT count(*) FROM $t")
    out="$out$t=$n "
  done
  echo "${out% }"
}

last_audit_hash() { psql -d "$1" -tAc "SELECT coalesce(max(hash), '') FROM audit_log WHERE id = (SELECT max(id) FROM audit_log)"; }
