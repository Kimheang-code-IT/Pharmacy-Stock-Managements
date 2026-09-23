#!/usr/bin/env bash
# Timestamped, verified backups of the PostgreSQL database and the media volume.
#
#   ./backup.sh [BACKUP_DIR] [RETENTION_DAYS] [--skip-media]
#
# Runs the one-shot `backup`/`media-backup` Compose services (profile "tools"),
# writes timestamped artifacts, verifies the newest dump with `pg_restore
# --list`, and prunes files older than the retention window. Secrets stay in
# infrastructure/.env and are never printed.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="$INFRA_DIR/docker-compose.yml"

BACKUP_DIR="${1:-$INFRA_DIR/backups}"
RETENTION_DAYS="${2:-14}"
SKIP_MEDIA="${3:-}"

mkdir -p "$BACKUP_DIR"

compose() { docker compose -f "$COMPOSE_FILE" --project-directory "$INFRA_DIR" "$@"; }

echo "==> Backing up PostgreSQL..."
compose --profile tools run --rm backup

if [[ "$SKIP_MEDIA" != "--skip-media" ]]; then
  echo "==> Backing up the media volume..."
  compose --profile tools run --rm media-backup
fi

DUMP="$(ls -1t "$BACKUP_DIR"/stock_pos_*.dump 2>/dev/null | head -n1 || true)"
if [[ -z "$DUMP" ]]; then
  echo "ERROR: no database dump was produced in $BACKUP_DIR" >&2
  exit 1
fi

echo "==> Verifying $(basename "$DUMP")..."
compose --profile tools run --rm backup \
  "pg_restore --list /backups/$(basename "$DUMP") > /dev/null && echo BACKUP_VERIFIED"
echo "Backup verified: $DUMP"

# Retention: delete artifacts older than the window.
find "$BACKUP_DIR" -type f -mtime "+${RETENTION_DAYS}" -print -delete || true
echo "Done. Backups in $BACKUP_DIR"
