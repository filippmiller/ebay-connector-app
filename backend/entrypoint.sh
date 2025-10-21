#!/bin/bash
set -e

echo "🚀 Starting eBay Connector Backend..."

if [ -n "$DATABASE_URL" ]; then
    echo "📊 Running Alembic migrations..."
    cd /app && poetry run alembic upgrade head
    echo "✅ Migrations completed!"
else
    echo "⚠️  DATABASE_URL not set, skipping migrations"
fi

echo "🎯 Starting FastAPI server..."
exec poetry run fastapi run app/main.py
