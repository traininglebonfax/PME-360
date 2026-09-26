#!/usr/bin/env bash
# Restauration d'une sauvegarde logique dans une base (par défaut : une NOUVELLE base, jamais écrasée en silence).
# Usage : restore.sh <fichier .dump.enc> <base cible>
source "$(dirname "$0")/common.sh"

dump="${1:?fichier de sauvegarde requis}"
target_db="${2:?base cible requise}"
manifest="${dump%.dump.enc}.manifest"

if [ -f "$manifest" ]; then
  expected="$(grep '^sha256=' "$manifest" | cut -d= -f2)"
  actual="$(sha256sum "$dump" | cut -d' ' -f1)"
  [ "$expected" = "$actual" ] || { echo "Empreinte différente : sauvegarde altérée ($dump)." >&2; exit 2; }
fi
if [ "$(psql -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = '$target_db'")" = "1" ]; then
  echo "La base $target_db existe déjà : choisissez une autre cible ou supprimez-la explicitement." >&2
  exit 3
fi
owner="${PME360_RESTORE_OWNER:-pme360}"
psql -d postgres -v ON_ERROR_STOP=1 -c "CREATE DATABASE \"$target_db\" OWNER \"$owner\" TEMPLATE template1"
# Propriétaires d'origine conservés (rôle applicatif propriétaire des tables : RLS forcée) ; restauration en superutilisateur.
# Les vues analytiques (RLS forcée sur leurs sources) sont recalculées ensuite en contexte système.
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
decrypt < "$dump" > "$work/dump"
pg_restore -l "$work/dump" | grep -v "MATERIALIZED VIEW DATA" > "$work/list"
pg_restore -d "$target_db" --no-comments --exit-on-error -L "$work/list" "$work/dump"
for view in $(psql -d "$target_db" -tAc "SELECT matviewname FROM pg_matviews WHERE schemaname = 'public'"); do
  psql -d "$target_db" -v ON_ERROR_STOP=1 -q     -c "SELECT set_config('app.bypass_rls', 'on', false)" -c "REFRESH MATERIALIZED VIEW $view" >/dev/null
done
log "Restauration de $(basename "$dump") dans $target_db terminée."
