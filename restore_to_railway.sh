#!/usr/bin/env bash
# Turnkey script to restore local LCHA PostgreSQL database (with pgvector) into Railway
set -e

if [ -z "$1" ]; then
  echo "Usage: ./restore_to_railway.sh <RAILWAY_DATABASE_URL>"
  echo "Example: ./restore_to_railway.sh postgresql://postgres:password@roundhouse.proxy.rlwy.net:12345/railway"
  exit 1
fi

DEST_URL="$1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DUMP_FILE="$SCRIPT_DIR/lcha_db_dump.sql.gz"

if [ ! -f "$DUMP_FILE" ]; then
  echo "Error: $DUMP_FILE not found!"
  exit 1
fi

PSQL_BIN="psql"
if ! command -v psql &> /dev/null; then
  if [ -x "/Applications/Postgres.app/Contents/Versions/17/bin/psql" ]; then
    PSQL_BIN="/Applications/Postgres.app/Contents/Versions/17/bin/psql"
  else
    echo "Error: psql command not found. Please install PostgreSQL client tools."
    exit 1
  fi
fi

echo "======================================================="
echo " Restoring LCHA Database to Railway PostgreSQL"
echo "======================================================="
echo "Using: $PSQL_BIN"
echo "Restoring from: $DUMP_FILE"
echo "Target URL: ${DEST_URL:0:35}..."
echo ""

gunzip -c "$DUMP_FILE" | "$PSQL_BIN" "$DEST_URL"

echo ""
echo "✅ Database restore to Railway completed successfully!"
