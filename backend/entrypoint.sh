#!/bin/bash
set -e

echo "🚀 Starting eBay Connector Backend..."

if [ -n "$DATABASE_URL" ]; then
    echo "📊 Running Alembic migrations..."
    cd /app && python -m alembic upgrade head
    echo "✅ Migrations completed!"
else
    echo "⚠️  DATABASE_URL not set, skipping migrations"
fi

echo "🎯 Starting FastAPI server..."
exec python -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
