#!/usr/bin/env bash
# Legacy-style entrypoint; kept for compatibility. Prefer start.sh.
set -eu

# Resolve Python binary similarly to start.sh
if [ -z "${PYTHON_BIN:-}" ]; then
  if [ -x "/app/backend/.venv/bin/python" ]; then
    PYTHON_BIN="/app/backend/.venv/bin/python"
  elif [ -x "/app/.venv/bin/python" ]; then
    PYTHON_BIN="/app/.venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
  elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python)"
  else
    echo "[entry] ERROR: Could not find a usable Python interpreter (python3/python)" >&2
    exit 1
  fi
fi

echo "[entry] Using PYTHON_BIN=${PYTHON_BIN}"

SCRIPT_PATH="${BASH_SOURCE[0]:-$0}"
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
ROOT_DIR="$SCRIPT_DIR"

echo "[entry] entrypoint SCRIPT_PATH=${SCRIPT_PATH}"
echo "[entry] entrypoint ROOT_DIR=${ROOT_DIR}"

echo "Starting eBay Connector Backend (entrypoint.sh)..."

if [ -n "${DATABASE_URL:-}" ]; then
    echo "Running Alembic migrations from /app/backend..."
    cd /app/backend && "${PYTHON_BIN}" -m alembic upgrade heads
    echo "Migrations completed!"
else
    echo "DATABASE_URL not set, skipping migrations"
fi

echo "Starting FastAPI server..."
exec "${PYTHON_BIN}" -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
