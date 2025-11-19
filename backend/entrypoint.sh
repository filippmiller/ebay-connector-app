#!/bin/bash
set -e

# Prefer the app virtualenv Python if present so Alembic/uvicorn imports work
PYTHON_BIN="${PYTHON_BIN:-/app/.venv/bin/python}"

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
