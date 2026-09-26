#!/usr/bin/env bash
# Démarrage de PostgreSQL avec l'archivage des WAL (restauration à un instant donné, RPO 15 min).
set -euo pipefail
mkdir -p /backups/wal
chown postgres:postgres /backups /backups/wal
# Connexions de réplication (pg_basebackup) depuis le réseau Docker, authentifiées par mot de passe.
if [ -f "$PGDATA/pg_hba.conf" ] && ! grep -q "^host replication postgres all scram-sha-256" "$PGDATA/pg_hba.conf"; then
  echo "host replication postgres all scram-sha-256" >> "$PGDATA/pg_hba.conf"
fi
exec docker-entrypoint.sh postgres \
  -c archive_mode=on \
  -c "archive_command=test ! -f /backups/wal/%f.gz && gzip -c %p > /backups/wal/%f.gz" \
  -c archive_timeout=900 \
  "$@"
