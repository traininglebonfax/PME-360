#!/usr/bin/env bash
# Sauvegarde physique hebdomadaire (point de départ de la restauration à un instant donné avec les WAL archivés).
source "$(dirname "$0")/common.sh"

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
target="$BACKUP_ROOT/base/base-$stamp.tar.gz.enc"
log "Sauvegarde de base (pg_basebackup) → $target"
pg_basebackup -D - -Ft -X none --checkpoint=fast | gzip | encrypt > "$target.part"
mv "$target.part" "$target"
sha256sum "$target" | cut -d' ' -f1 > "$target.sha256"
log "Terminé : $(stat -c %s "$target") octets"
