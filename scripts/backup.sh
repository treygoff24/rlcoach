#!/bin/bash
# PostgreSQL backup script for rlcoach
# Runs daily via cron: 0 3 * * * /opt/rlcoach/scripts/backup.sh >> /var/log/rlcoach-backup.log 2>&1

set -euo pipefail

# Configuration
BACKUP_DIR="${BACKUP_DIR:-/opt/rlcoach/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-rlcoach-postgres}"
POSTGRES_USER="${POSTGRES_USER:-rlcoach}"
POSTGRES_DB="${POSTGRES_DB:-rlcoach}"

# Backblaze B2 configuration
B2_BUCKET="${BACKBLAZE_BUCKET_NAME:-}"
B2_KEY_ID="${BACKBLAZE_KEY_ID:-}"
B2_APP_KEY="${BACKBLAZE_APPLICATION_KEY:-}"

# Timestamp
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="rlcoach_backup_${TIMESTAMP}.sql.gz"
BACKUP_PATH="${BACKUP_DIR}/${BACKUP_FILE}"

echo "=== rlcoach Backup Script ==="
echo "Timestamp: $(date)"
echo ""

# Create backup directory if it doesn't exist
mkdir -p "$BACKUP_DIR"

# Perform backup
echo "Starting PostgreSQL backup..."
docker exec "$POSTGRES_CONTAINER" \
    pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
    --format=plain \
    --no-owner \
    --no-acl \
    | gzip > "$BACKUP_PATH"

# Verify backup
if [ ! -f "$BACKUP_PATH" ]; then
    echo "ERROR: Backup file not created"
    exit 1
fi

BACKUP_SIZE=$(du -h "$BACKUP_PATH" | cut -f1)
echo "Backup created: $BACKUP_FILE ($BACKUP_SIZE)"

# Encrypt backup (optional - uses GPG if available)
if command -v gpg &> /dev/null && [ -n "${BACKUP_GPG_KEY:-}" ]; then
    echo "Encrypting backup..."
    gpg --batch --yes --passphrase "$BACKUP_GPG_KEY" \
        -c "$BACKUP_PATH"
    rm "$BACKUP_PATH"
    BACKUP_PATH="${BACKUP_PATH}.gpg"
    BACKUP_FILE="${BACKUP_FILE}.gpg"
    echo "Backup encrypted"
fi

# Upload to Backblaze B2
if [ -n "$B2_BUCKET" ] && [ -n "$B2_KEY_ID" ] && [ -n "$B2_APP_KEY" ]; then
    echo "Uploading to Backblaze B2..."

    # Install b2 CLI if not present
    if ! command -v b2 &> /dev/null; then
        pip install --quiet b2
    fi

    # Authorize
    b2 authorize-account "$B2_KEY_ID" "$B2_APP_KEY" > /dev/null

    # Upload
    b2 upload-file "$B2_BUCKET" "$BACKUP_PATH" "backups/$BACKUP_FILE" > /dev/null

    echo "Backup uploaded to B2: $B2_BUCKET/backups/$BACKUP_FILE"
else
    echo "Backblaze B2 not configured, skipping cloud upload"
fi

# Clean up old local backups
echo "Cleaning up backups older than $RETENTION_DAYS days..."
find "$BACKUP_DIR" -name "rlcoach_backup_*.sql.gz*" -mtime +"$RETENTION_DAYS" -delete

# Count remaining backups
LOCAL_COUNT=$(find "$BACKUP_DIR" -name "rlcoach_backup_*.sql.gz*" | wc -l)
echo "Local backups remaining: $LOCAL_COUNT"

# Clean up old B2 backups
if [ -n "$B2_BUCKET" ] && [ -n "$B2_KEY_ID" ]; then
    echo "Cleaning up old B2 backups..."
    CUTOFF_DATE=$(date -d "$RETENTION_DAYS days ago" +%Y%m%d)

    # List and delete old files
    b2 ls "$B2_BUCKET" backups/ 2>/dev/null | while read -r file; do
        FILE_DATE=$(echo "$file" | grep -oP '\d{8}' | head -1)
        if [ -n "$FILE_DATE" ] && [ "$FILE_DATE" -lt "$CUTOFF_DATE" ]; then
            echo "Deleting old B2 backup: $file"
            b2 delete-file-version "$file" 2>/dev/null || true
        fi
    done
fi

echo ""
echo "=== Backup Complete ==="
echo "Local: $BACKUP_PATH"
echo "Size: $BACKUP_SIZE"
echo "Timestamp: $(date)"
