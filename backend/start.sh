#!/usr/bin/env bash
set -euo pipefail

export PYTHONUNBUFFERED=1   # мгновенная запись логов в STDOUT
echo "[entry] PORT=${PORT:-8000} DB=${DATABASE_URL:-unset}"

# 1) Миграции (можно временно выключить RUN_MIGRATIONS=0 в Railway Variables)
if [[ "${RUN_MIGRATIONS:-1}" == "1" ]]; then
  echo "[entry] Checking Alembic state..."
  cd /app
  echo "[entry] alembic current before:"
  poetry run alembic current || echo "[entry] No current revision found"
  echo "[entry] alembic heads:"
  poetry run alembic heads || echo "[entry] No heads found"
  echo "[entry] alembic upgrade heads..."
  poetry run alembic upgrade heads || {
    echo "[entry] WARNING: Migrations failed, continuing anyway..."
  }
fi

# 2) Запуск приложения (exec — чтобы процесс не завершился после скрипта)
echo "[entry] Starting uvicorn server..."
exec poetry run uvicorn app.main:app \
  --host 0.0.0.0 --port "${PORT:-8000}" \
  --log-level debug --proxy-headers --forwarded-allow-ips="*"

