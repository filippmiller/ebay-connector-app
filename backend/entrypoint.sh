#!/bin/bash
set -e

# Resolve Python binary similarly to start.sh
if [ -z "${PYTHON_BIN:-}" ]; then
  if [ -x "/app/.venv/bin/python" ]; then
    PYTHON_BIN="/app/.venv/bin/python"
  elif [ -x "/app/backend/.venv/bin/python" ]; then
    PYTHON_BIN="/app/backend/.venv/bin/python"
  else
    PYTHON_BIN="$(command -v python3 || command -v python)"
  fi
fi

echo "[entry] Using PYTHON_BIN=${PYTHON_BIN}"

echo "🚀 Starting eBay Connector Backend..."

if [ -n "$DATABASE_URL" ]; then
    echo "📊 Running Alembic migrations..."
    cd /app && "${PYTHON_BIN}" -m alembic upgrade head
    echo "✅ Migrations completed!"
else
    echo "⚠️  DATABASE_URL not set, skipping migrations"
fi

echo "🎯 Starting FastAPI server..."
exec "${PYTHON_BIN}" -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
