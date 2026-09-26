# Sauvegardes et restauration — runbook

Mise en œuvre du Document 2, § « Sauvegardes » : archivage continu des WAL (restauration à un instant donné),
sauvegarde quotidienne chiffrée, rétention de 30 jours, réplication du stockage objet et **test de restauration
mensuel documenté**. Objectifs de départ : **RPO 15 minutes**, **RTO 4 heures**.

## Ce qui est sauvegardé

| Élément | Mécanisme | Fréquence | Emplacement (volume `pgbackups`) |
|---|---|---|---|
| Journaux PostgreSQL (WAL) | `archive_command` de PostgreSQL, compressés | Continu, au plus 15 min (`archive_timeout`) | `/backups/wal` |
| Base complète (logique) | `pg_dump` format personnalisé, **chiffré AES-256** + manifeste (empreinte SHA-256, volumes, dernier maillon d'audit) | Chaque nuit (1 h UTC par défaut) | `/backups/daily` |
| Base complète (physique) | `pg_basebackup`, **chiffré** : point de départ de la restauration à un instant donné | Chaque dimanche | `/backups/base` |
| Documents et rapports | Réplication continue du compartiment (`mc mirror --watch`) | Continu | `/backups/objects` |
| Test de restauration | Restauration de la dernière sauvegarde dans une base temporaire, contrôles, rapport | Le 1er de chaque mois | `/backups/restore-tests` |

Rétention : 30 jours (`PME360_BACKUP_RETENTION_DAYS`). Les fichiers chiffrés ne sont lisibles qu'avec
`PME360_BACKUP_PASSPHRASE`.

## Mise en service

```bash
# Phrase de chiffrement : à générer une fois, à conserver HORS du serveur (coffre de secrets, deux personnes).
export PME360_BACKUP_PASSPHRASE="$(openssl rand -base64 48)"
docker compose -f infra/docker-compose.yml --profile backup up -d      # postgres (WAL) + backup + backup-objects
```

En production : `PME360_ENV=prod` interdit la phrase de développement ; les volumes de la base et des sauvegardes
sont chiffrés au niveau du disque ; le stockage objet de production (S3) utilise le versionnement et la réplication
du fournisseur, et le compartiment de sauvegarde vit dans un autre site. **Copie hors site** : synchroniser chaque nuit
le volume `pgbackups` vers un stockage d'un autre fournisseur ou d'une autre région (par ex.
`mc mirror /backups offsite/pme360-backups`), les fichiers étant déjà chiffrés.

Sous Windows (Git Bash), préfixer les commandes suivantes par `MSYS_NO_PATHCONV=1` pour que les chemins `/scripts/…`
ne soient pas convertis.

## Opérations courantes

```bash
cd infra
# Sauvegarde immédiate (par ex. avant une mise à jour)
docker compose --profile backup run --rm --entrypoint bash backup /scripts/backup.sh
# Test de restauration à la demande (le rapport est écrit dans /backups/restore-tests)
docker compose --profile backup run --rm --entrypoint bash backup /scripts/test-restore.sh
# Lister les sauvegardes et les rapports de test
docker compose --profile backup run --rm --entrypoint bash backup -c "ls -lh /backups/daily /backups/restore-tests"
```

Le test de restauration échoue (et le signale dans son rapport) si : l'empreinte de la sauvegarde ne correspond pas,
la restauration échoue, les volumes des tables de référence ou le dernier maillon du journal d'audit diffèrent du
manifeste, les tables n'appartiennent plus au rôle applicatif ou la Row-Level Security forcée n'est plus en place.

**Test mensuel documenté** : chaque 1er du mois, relire le dernier rapport `restore-tests/test-*.log`, le joindre au
registre d'exploitation (date, résultat, durée, personne) et ouvrir un incident en cas d'échec.

## Restaurer après un incident

### A. Depuis la sauvegarde quotidienne (perte ≤ 24 h)

1. Arrêter l'application (API, worker, beat) pour éviter toute écriture.
2. Restaurer dans une **nouvelle** base (le script refuse d'écraser une base existante) :
   `docker compose --profile backup run --rm --entrypoint bash backup /scripts/restore.sh /backups/daily/<fichier>.dump.enc pme360_restauree`
3. Vérifier la chaîne d'audit sur la base restaurée : `POSTGRES_DB=pme360_restauree python manage.py verify_audit`
   (ou l'écran « Journal d'audit › Vérifier »).
4. Basculer l'application sur `pme360_restauree` (`POSTGRES_DB`), redémarrer, contrôler un parcours de connexion.
5. Conserver l'ancienne base jusqu'à la fin de l'analyse de l'incident.

### B. À un instant donné (perte ≤ 15 min)

1. Arrêter l'application, puis PostgreSQL.
2. Déchiffrer et extraire la dernière sauvegarde de base **antérieure** à l'instant visé dans un nouveau répertoire de
   données :
   ```bash
   openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass env:PME360_BACKUP_PASSPHRASE \
     < /backups/base/base-<date>.tar.gz.enc | gunzip > /tmp/base.tar
   tar -xf /tmp/base.tar -C "$PGDATA_NOUVEAU"
   ```
3. Dans `$PGDATA_NOUVEAU/postgresql.auto.conf` :
   ```
   restore_command = 'gunzip -c /backups/wal/%f.gz > %p'
   recovery_target_time = '2026-09-26 10:42:00+00'
   recovery_target_action = 'promote'
   ```
   puis créer le fichier vide `$PGDATA_NOUVEAU/recovery.signal`.
4. Démarrer PostgreSQL sur ce répertoire : il rejoue les WAL jusqu'à l'instant visé puis s'ouvre en écriture.
5. Recalculer les vues analytiques (`python manage.py shell -c "from pme360.analytics.services import refresh; refresh()"`),
   vérifier la chaîne d'audit, redémarrer l'application.

### C. Documents et rapports

Recopier `/backups/objects` vers le compartiment (`mc mirror /backups/objects local/pme360-documents`). Les rapports
PDF sont contrôlés à chaque téléchargement par leur empreinte SHA-256 : un fichier altéré est refusé.
