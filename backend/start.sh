#!/usr/bin/env bash
set -euo pipefail

export PYTHONUNBUFFERED=1   # мгновенная запись логов в STDOUT
echo "[entry] Starting backend service..."
echo "[entry] PORT=${PORT:-8000}"
echo "[entry] Database configured: ${DATABASE_URL:+yes}"

# 0) Ensure Microsoft ODBC Driver 18 for SQL Server (msodbcsql18) is installed
#    This is idempotent and safe to run on each container start.
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ "${INSTALL_MSODBC18:-1}" == "1" ]]; then
  echo "[entry] Checking for ODBC Driver 18 for SQL Server..."
  if command -v odbcinst >/dev/null 2>&1 && odbcinst -q -d | grep -q "ODBC Driver 18 for SQL Server"; then
    echo "[entry] ODBC Driver 18 for SQL Server already installed."
  else
    echo "[entry] Installing Microsoft ODBC Driver 18 for SQL Server (msodbcsql18)..."
    if bash "${ROOT_DIR}/scripts/install_msodbc18.sh"; then
      echo "[entry] msodbcsql18 install script completed successfully."
    else
      echo "[entry] WARNING: msodbcsql18 install script failed; MSSQL connections may not work." >&2
    fi
  fi
fi

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

