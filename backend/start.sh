#!/usr/bin/env bash
set -euo pipefail

export PYTHONUNBUFFERED=1   # мгновенная запись логов в STDOUT
echo "[entry] Starting backend service..."
echo "[entry] PORT=${PORT:-8000}"
echo "[entry] Database configured: ${DATABASE_URL:+yes}"

# 1) Миграции (можно временно выключить RUN_MIGRATIONS=0 в Railway Variables)
if [[ "${RUN_MIGRATIONS:-1}" == "1" ]]; then
  echo "[entry] Checking Alembic state..."
  cd /app
  
  # Retry function for migrations with exponential backoff
  run_migrations_with_retry() {
    local max_attempts=3
    local attempt=1
    local delay=2
    
    while [ $attempt -le $max_attempts ]; do
      echo "[entry] Migration attempt $attempt/$max_attempts..."
      
      if poetry run alembic upgrade heads; then
        echo "[entry] ✅ Migrations completed successfully!"
        return 0
      else
        if [ $attempt -lt $max_attempts ]; then
          echo "[entry] ⚠️  Migration attempt $attempt failed, retrying in ${delay}s..."
          sleep $delay
          delay=$((delay * 2))  # Exponential backoff: 2s, 4s, 8s
        else
          echo "[entry] ❌ All migration attempts failed, continuing anyway..."
        fi
      fi
      
      attempt=$((attempt + 1))
    done
    
    return 1
  }
  
  echo "[entry] alembic current before:"
  poetry run alembic current || echo "[entry] No current revision found"
  echo "[entry] alembic heads:"
  poetry run alembic heads || echo "[entry] No heads found"
  echo "[entry] Running migrations with retry logic..."
  
  run_migrations_with_retry || {
    echo "[entry] WARNING: Migrations failed after retries, continuing anyway..."
  }
fi

# 2) Запуск приложения (exec — чтобы процесс не завершился после скрипта)
echo "[entry] Starting uvicorn server..."
exec poetry run uvicorn app.main:app \
  --host 0.0.0.0 --port "${PORT:-8000}" \
  --log-level debug --proxy-headers --forwarded-allow-ips="*"

