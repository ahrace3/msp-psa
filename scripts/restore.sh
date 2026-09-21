#!/bin/sh
# Restore a dump. Run this once, on purpose, before you trust the backups.
#
#   sh /share/Container/psa/scripts/restore.sh /share/Container/psa/backups/psa-YYYYMMDD-HHMMSS.sql.gz

set -eu

FILE="${1:?usage: restore.sh <path-to-psa-*.sql.gz>}"
DB_CONTAINER="psa-postgres-1"

[ -f "$FILE" ] || { echo "No such file: $FILE"; exit 1; }

printf 'This overwrites the current database. Type RESTORE to continue: '
read -r CONFIRM
[ "$CONFIRM" = "RESTORE" ] || { echo "Cancelled."; exit 1; }

gunzip -c "$FILE" | docker exec -i "$DB_CONTAINER" psql -U psa -d psa
echo "Restore complete. Restart the web and worker containers."
