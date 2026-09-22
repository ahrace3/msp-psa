#!/bin/sh
# Nightly backup: dump Postgres, keep 14 local copies, push one to Azure Blob.
#
# QNAP: Control Panel > Task Scheduler > Create > Scheduled Script, daily 02:15.
#   sh /share/Container/psa/scripts/backup.sh >> /share/Container/psa/backup.log 2>&1
#
# Azure side (one time, in Cloud Shell):
#   az storage account create -n psabackupYOURNAME -g YOURRG --sku Standard_LRS --access-tier Cool
#   az storage container create -n psa --account-name psabackupYOURNAME
#   az storage container generate-sas -n psa --account-name psabackupYOURNAME \
#       --permissions acw --expiry 2028-01-01 --https-only
# Paste the SAS token (no leading ?) below. Permissions are add/create/write
# only, so a compromised NAS cannot read or delete what is already stored.

set -eu

PSA_DIR="/share/Container/psa"
BACKUP_DIR="$PSA_DIR/backups"
KEEP_DAYS=14
COMPOSE_PROJECT="psa"           # Container Station application name
DB_CONTAINER="${COMPOSE_PROJECT}-postgres-1"

AZURE_ACCOUNT="psabackupYOURNAME"
AZURE_CONTAINER="psa"
AZURE_SAS="REPLACE_WITH_SAS_TOKEN"

STAMP=$(date +%Y%m%d-%H%M%S)
FILE="psa-$STAMP.sql.gz"
mkdir -p "$BACKUP_DIR"

echo "[$(date)] dumping database"
docker exec "$DB_CONTAINER" pg_dump -U psa -d psa --clean --if-exists \
  | gzip -9 > "$BACKUP_DIR/$FILE"

SIZE=$(wc -c < "$BACKUP_DIR/$FILE")
if [ "$SIZE" -lt 2000 ]; then
  echo "[$(date)] ERROR: dump is only ${SIZE} bytes, refusing to upload"
  exit 1
fi
echo "[$(date)] dump ok (${SIZE} bytes)"

echo "[$(date)] uploading to Azure"
curl -sS -f -X PUT \
  -H "x-ms-blob-type: BlockBlob" \
  -H "Content-Type: application/gzip" \
  --data-binary "@$BACKUP_DIR/$FILE" \
  "https://${AZURE_ACCOUNT}.blob.core.windows.net/${AZURE_CONTAINER}/${FILE}?${AZURE_SAS}"
echo "[$(date)] upload ok"

find "$BACKUP_DIR" -name 'psa-*.sql.gz' -mtime +$KEEP_DAYS -delete
echo "[$(date)] backup complete: $FILE"
