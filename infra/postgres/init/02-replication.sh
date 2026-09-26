#!/bin/bash
# Première initialisation : autorise pg_basebackup (sauvegarde de base) depuis le réseau, par mot de passe.
set -euo pipefail
echo "host replication postgres all scram-sha-256" >> "$PGDATA/pg_hba.conf"
