#!/usr/bin/env bash
# Planificateur des sauvegardes : chaque nuit (heure UTC paramétrable) sauvegarde logique ; le dimanche, sauvegarde de
# base ; le 1er du mois, test de restauration. Les WAL sont archivés en continu par PostgreSQL (RPO 15 min).
source "$(dirname "$0")/common.sh"

hour="${PME360_BACKUP_HOUR_UTC:-1}"
log "Planificateur démarré (sauvegarde quotidienne à ${hour} h UTC)."
while true; do
  now=$(date -u +%s)
  next=$(date -u -d "today ${hour}:00" +%s)
  [ "$next" -le "$now" ] && next=$(date -u -d "tomorrow ${hour}:00" +%s)
  sleep $(( next - now ))
  "$(dirname "$0")/backup.sh" || log "ÉCHEC de la sauvegarde quotidienne"
  [ "$(date -u +%u)" = 7 ] && { "$(dirname "$0")/basebackup.sh" || log "ÉCHEC de la sauvegarde de base"; }
  [ "$(date -u +%d)" = 01 ] && { "$(dirname "$0")/test-restore.sh" || log "ÉCHEC du test de restauration"; }
done
