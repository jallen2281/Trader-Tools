#!/bin/bash
# Dump the tradertools PostgreSQL database to /data/backups.
# Expects standard PG* env vars: PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE.
# Retains the last 30 daily dumps; older files are pruned automatically.

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/data/backups}"
DB_NAME="${PGDATABASE:-tradertools}"
TIMESTAMP="$(date -u +%Y%m%d_%H%M%S)"
OUTFILE="${BACKUP_DIR}/${DB_NAME}_${TIMESTAMP}.dump"
RETENTION_DAYS="${RETENTION_DAYS:-30}"

mkdir -p "$BACKUP_DIR"

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Starting pg_dump for database '${DB_NAME}'"
pg_dump \
    --format=custom \
    --compress=9 \
    --no-password \
    "$DB_NAME" \
    > "$OUTFILE"

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Backup written to ${OUTFILE} ($(du -h "$OUTFILE" | cut -f1))"

# Prune backups older than RETENTION_DAYS
find "$BACKUP_DIR" -name "${DB_NAME}_*.dump" -mtime "+${RETENTION_DAYS}" -delete
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Pruned backups older than ${RETENTION_DAYS} days"
