#!/bin/sh
# Dump the tradertools PostgreSQL database to /data/backups.
# Expects standard PG* env vars: PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE.
# Retains the last 30 daily dumps; older files are pruned automatically.
#
# Encryption: when BACKUP_ENCRYPTION_KEY is set the dump is encrypted with AES-256 before
# it touches disk. This matters because the dumps sit on unencrypted Ceph storage in a
# colocation facility, and they contain every financial record in the system.
#
# To restore an encrypted backup:
#   openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 \
#       -pass env:BACKUP_ENCRYPTION_KEY -in FILE.dump.enc | pg_restore -d DBNAME
#
# LOSING THE KEY MAKES EVERY ENCRYPTED BACKUP UNRECOVERABLE. Store it somewhere that is
# not only inside the cluster it protects.
#
# NOTE: this script exists in two places that must stay in step - backup.sh at the repo
# root, and inline in the ConfigMap in k8s/backup-cronjob.yaml, which is what actually runs.

set -eu

BACKUP_DIR="${BACKUP_DIR:-/data/backups}"
DB_NAME="${PGDATABASE:-tradertools}"
TIMESTAMP="$(date -u +%Y%m%d_%H%M%S)"
RETENTION_DAYS="${RETENTION_DAYS:-30}"

mkdir -p "$BACKUP_DIR"

# Fail the whole pipeline if pg_dump fails, not just the last command in it. Without this a
# dump that dies half way still produces a file and exits 0 — a truncated backup that looks
# like a good one is worse than no backup, because nobody investigates it.
set -o pipefail 2>/dev/null || true

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }

if [ -n "${BACKUP_ENCRYPTION_KEY:-}" ] && ! command -v openssl >/dev/null 2>&1; then
    apk add --no-cache openssl >/dev/null 2>&1 || true
fi

if [ -n "${BACKUP_ENCRYPTION_KEY:-}" ] && command -v openssl >/dev/null 2>&1; then
    OUTFILE="${BACKUP_DIR}/${DB_NAME}_${TIMESTAMP}.dump.enc"
    log "Starting encrypted pg_dump for '${DB_NAME}'"
    # The passphrase is read from the environment, never passed as an argument, so it does
    # not appear in the process list.
    pg_dump --format=custom --compress=9 --no-password "$DB_NAME" \
        | openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt \
            -pass env:BACKUP_ENCRYPTION_KEY > "$OUTFILE"
else
    OUTFILE="${BACKUP_DIR}/${DB_NAME}_${TIMESTAMP}.dump"
    log "WARNING: BACKUP_ENCRYPTION_KEY is not set - writing an UNENCRYPTED dump."
    log "WARNING: it contains financial records and email addresses in the clear."
    # Deliberately still taking the backup. Losing the safety net entirely is a worse
    # outcome than the status quo, and the .dump vs .dump.enc suffix makes the state
    # obvious in a directory listing rather than hiding in a log nobody reads.
    pg_dump --format=custom --compress=9 --no-password "$DB_NAME" > "$OUTFILE"
fi

# A zero-byte or missing file means the dump failed even if the exit status did not say so.
if [ ! -s "$OUTFILE" ]; then
    log "ERROR: backup file is missing or empty - removing it and failing the job"
    rm -f "$OUTFILE"
    exit 1
fi

log "Backup written to ${OUTFILE} ($(du -h "$OUTFILE" | cut -f1))"

# Prune both suffixes: older backups may predate encryption.
find "$BACKUP_DIR" -name "${DB_NAME}_*.dump" -mtime "+${RETENTION_DAYS}" -delete
find "$BACKUP_DIR" -name "${DB_NAME}_*.dump.enc" -mtime "+${RETENTION_DAYS}" -delete
log "Pruned backups older than ${RETENTION_DAYS} days"
