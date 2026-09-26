#!/usr/bin/env bash
# Test de restauration (mensuel, Document 2) : restaure la dernière sauvegarde dans une base temporaire, compare les
# volumes et le dernier maillon du journal d'audit au manifeste, puis supprime la base temporaire. Rapport archivé.
source "$(dirname "$0")/common.sh"

latest="$(ls -1t "$BACKUP_ROOT"/daily/*.dump.enc 2>/dev/null | head -1 || true)"
[ -n "$latest" ] || { echo "Aucune sauvegarde à tester." >&2; exit 1; }
manifest="${latest%.dump.enc}.manifest"
report="$BACKUP_ROOT/restore-tests/test-$(date -u +%Y%m%dT%H%M%SZ).log"
test_db="pme360_restore_test"
started=$(date +%s)

{
  log "Test de restauration de $(basename "$latest")"
  psql -d postgres -c "DROP DATABASE IF EXISTS $test_db WITH (FORCE)" >/dev/null
  "$(dirname "$0")/restore.sh" "$latest" "$test_db"
  expected_counts="$(grep '^counts=' "$manifest" | cut -d= -f2-)"
  restored_counts="$(table_counts "$test_db")"
  expected_audit="$(grep '^last_audit_hash=' "$manifest" | cut -d= -f2-)"
  restored_audit="$(last_audit_hash "$test_db")"
  status=OK
  if [ "$expected_counts" != "$restored_counts" ]; then
    status=ECHEC; log "Volumes différents : attendu [$expected_counts] ; restauré [$restored_counts]"
  else
    log "Volumes identiques : $restored_counts"
  fi
  if [ "$expected_audit" != "$restored_audit" ]; then
    status=ECHEC; log "Dernier maillon du journal d'audit différent."
  else
    log "Dernier maillon du journal d'audit identique."
  fi
  # Sécurité de la base restaurée : tables du rôle applicatif (sinon la RLS forcée ne s'appliquerait plus).
  foreign="$(psql -d "$test_db" -tAc "SELECT count(*) FROM pg_tables WHERE schemaname = 'public' AND tableowner <> '${PME360_RESTORE_OWNER:-pme360}'")"
  source_rls="$(psql -d "$DB_NAME" -tAc "SELECT count(*) FROM pg_class WHERE relrowsecurity AND relforcerowsecurity")"
  restored_rls="$(psql -d "$test_db" -tAc "SELECT count(*) FROM pg_class WHERE relrowsecurity AND relforcerowsecurity")"
  if [ "$foreign" != "0" ] || [ "$source_rls" != "$restored_rls" ]; then
    status=ECHEC; log "Sécurité : $foreign table(s) d'un autre propriétaire ; RLS forcée sur $restored_rls table(s) au lieu de $source_rls."
  else
    log "Sécurité : propriétaire applicatif et RLS forcée conservés ($restored_rls tables)."
  fi
  psql -d postgres -c "DROP DATABASE IF EXISTS $test_db WITH (FORCE)" >/dev/null
  log "Durée de restauration : $(( $(date +%s) - started )) s (objectif RTO : 4 h)"
  log "RÉSULTAT : $status"
  [ "$status" = OK ]
} 2>&1 | tee "$report"
exit "${PIPESTATUS[0]}"
