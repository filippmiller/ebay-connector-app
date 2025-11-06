#!/usr/bin/env bash
set -euo pipefail

export PYTHONUNBUFFERED=1   # мгновенная запись логов в STDOUT
echo "[entry] PORT=${PORT:-8000} DB=${DATABASE_URL:-unset}"

# 1) Миграции (можно временно выключить RUN_MIGRATIONS=0 в Railway Variables)
if [[ "${RUN_MIGRATIONS:-1}" == "1" ]]; then
  echo "[entry] alembic upgrade head..."
  cd /app && poetry run alembic upgrade head || {
    echo "[entry] WARNING: Migrations failed, continuing anyway..."
  }
fi

# 2) Запуск приложения (exec — чтобы процесс не завершился после скрипта)
echo "[entry] Starting uvicorn server..."
exec poetry run uvicorn app.main:app \
  --host 0.0.0.0 --port "${PORT:-8000}" \
  --log-level debug --proxy-headers --forwarded-allow-ips="*"

