#!/usr/bin/env bash
# Sauvegarde logique quotidienne chiffrée (pg_dump, format personnalisé) + manifeste de contrôle.
source "$(dirname "$0")/common.sh"

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
target="$BACKUP_ROOT/daily/pme360-$stamp.dump.enc"
manifest="$BACKUP_ROOT/daily/pme360-$stamp.manifest"

log "Sauvegarde logique de $DB_NAME → $target"
counts="$(table_counts "$DB_NAME")"
audit="$(last_audit_hash "$DB_NAME")"
pg_dump -d "$DB_NAME" -Fc | encrypt > "$target.part"
mv "$target.part" "$target"
{
  echo "file=$(basename "$target")"
  echo "created_at=$stamp"
  echo "database=$DB_NAME"
  echo "sha256=$(sha256sum "$target" | cut -d' ' -f1)"
  echo "size=$(stat -c %s "$target")"
  echo "counts=$counts"
  echo "last_audit_hash=$audit"
} > "$manifest"
log "Terminé : $(stat -c %s "$target") octets, empreinte enregistrée dans $(basename "$manifest")"

# Rétention : 30 jours (sauvegardes quotidiennes, sauvegardes de base et journaux WAL archivés).
find "$BACKUP_ROOT/daily" -type f -mtime +"$RETENTION_DAYS" -print -delete | sed 's/^/Suppression (rétention) : /' || true
find "$BACKUP_ROOT/base" -type f -mtime +"$RETENTION_DAYS" -print -delete | sed 's/^/Suppression (rétention) : /' || true
find "$BACKUP_ROOT/wal" -type f -mtime +"$RETENTION_DAYS" -delete || true
