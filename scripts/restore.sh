#!/bin/bash
# PostgreSQL restore script for rlcoach
# Usage: ./restore.sh [backup_file]
#        ./restore.sh                    # Lists available backups
#        ./restore.sh latest             # Restores most recent backup
#        ./restore.sh backup_file.sql.gz # Restores specific backup

set -euo pipefail

# Configuration
BACKUP_DIR="${BACKUP_DIR:-/opt/rlcoach/backups}"
POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-rlcoach-postgres}"
POSTGRES_USER="${POSTGRES_USER:-rlcoach}"
POSTGRES_DB="${POSTGRES_DB:-rlcoach}"

# Backblaze B2 configuration
B2_BUCKET="${BACKBLAZE_BUCKET_NAME:-}"
B2_KEY_ID="${BACKBLAZE_KEY_ID:-}"
B2_APP_KEY="${BACKBLAZE_APPLICATION_KEY:-}"

echo "=== rlcoach Restore Script ==="
echo ""

# List available backups
list_backups() {
    echo "Local backups in $BACKUP_DIR:"
    echo "-----------------------------"
    ls -lh "$BACKUP_DIR"/rlcoach_backup_*.sql.gz* 2>/dev/null | \
        awk '{print $NF, "(" $5 ")"}' | \
        sort -r | \
        head -20

    if [ -n "$B2_BUCKET" ] && [ -n "$B2_KEY_ID" ]; then
        echo ""
        echo "Remote backups in B2 (recent 20):"
        echo "---------------------------------"
        b2 authorize-account "$B2_KEY_ID" "$B2_APP_KEY" > /dev/null 2>&1
        b2 ls "$B2_BUCKET" backups/ 2>/dev/null | sort -r | head -20
    fi
}

# Download from B2 if not local
download_from_b2() {
    local file=$1
    local local_path="$BACKUP_DIR/$file"

    if [ -f "$local_path" ]; then
        echo "Backup exists locally: $local_path"
        return 0
    fi

    if [ -z "$B2_BUCKET" ] || [ -z "$B2_KEY_ID" ]; then
        echo "ERROR: Backup not found locally and B2 not configured"
        return 1
    fi

    echo "Downloading from B2..."
    b2 authorize-account "$B2_KEY_ID" "$B2_APP_KEY" > /dev/null
    b2 download-file-by-name "$B2_BUCKET" "backups/$file" "$local_path"
    echo "Downloaded: $local_path"
}

# Restore backup
restore_backup() {
    local backup_file=$1
    local backup_path

    # Handle 'latest' keyword
    if [ "$backup_file" = "latest" ]; then
        backup_path=$(ls -t "$BACKUP_DIR"/rlcoach_backup_*.sql.gz* 2>/dev/null | head -1)
        if [ -z "$backup_path" ]; then
            echo "ERROR: No local backups found"
            exit 1
        fi
        backup_file=$(basename "$backup_path")
        echo "Using latest backup: $backup_file"
    else
        backup_path="$BACKUP_DIR/$backup_file"
    fi

    # Download from B2 if needed
    if [ ! -f "$backup_path" ]; then
        download_from_b2 "$backup_file"
        backup_path="$BACKUP_DIR/$backup_file"
    fi

    # Verify file exists
    if [ ! -f "$backup_path" ]; then
        echo "ERROR: Backup file not found: $backup_path"
        exit 1
    fi

    echo ""
    echo "WARNING: This will DROP and recreate the database!"
    echo "Backup: $backup_file"
    echo ""
    read -p "Are you sure you want to continue? (yes/no): " confirm
    if [ "$confirm" != "yes" ]; then
        echo "Restore cancelled"
        exit 0
    fi

    echo ""
    echo "Stopping application services..."
    docker compose -f docker-compose.prod.yml stop backend worker frontend 2>/dev/null || true

    echo "Creating pre-restore backup..."
    PRE_RESTORE_BACKUP="$BACKUP_DIR/pre_restore_$(date +%Y%m%d_%H%M%S).sql.gz"
    docker exec "$POSTGRES_CONTAINER" \
        pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
        --format=plain --no-owner --no-acl \
        | gzip > "$PRE_RESTORE_BACKUP"
    echo "Pre-restore backup saved: $PRE_RESTORE_BACKUP"

    echo ""
    echo "Dropping and recreating database..."
    docker exec "$POSTGRES_CONTAINER" psql -U "$POSTGRES_USER" -c \
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$POSTGRES_DB' AND pid <> pg_backend_pid();" \
        2>/dev/null || true
    docker exec "$POSTGRES_CONTAINER" dropdb -U "$POSTGRES_USER" "$POSTGRES_DB" --if-exists
    docker exec "$POSTGRES_CONTAINER" createdb -U "$POSTGRES_USER" "$POSTGRES_DB"

    echo "Restoring from backup..."

    # Handle encrypted backups
    if [[ "$backup_path" == *.gpg ]]; then
        if [ -z "${BACKUP_GPG_KEY:-}" ]; then
            echo "ERROR: Encrypted backup requires BACKUP_GPG_KEY"
            exit 1
        fi
        gpg --batch --passphrase "$BACKUP_GPG_KEY" -d "$backup_path" | \
            gunzip | \
            docker exec -i "$POSTGRES_CONTAINER" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"
    else
        gunzip -c "$backup_path" | \
            docker exec -i "$POSTGRES_CONTAINER" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"
    fi

    echo ""
    echo "Running migrations..."
    docker compose -f docker-compose.prod.yml run --rm backend \
        alembic upgrade head

    echo ""
    echo "Starting application services..."
    docker compose -f docker-compose.prod.yml up -d backend worker frontend

    echo ""
    echo "=== Restore Complete ==="
    echo "Restored from: $backup_file"
    echo "Pre-restore backup: $PRE_RESTORE_BACKUP"
    echo ""
    echo "Verify the application is working correctly."
    echo "If issues occur, restore from: $PRE_RESTORE_BACKUP"
}

# Main
if [ $# -eq 0 ]; then
    list_backups
    echo ""
    echo "Usage: $0 [backup_file|latest]"
    exit 0
fi

restore_backup "$1"
