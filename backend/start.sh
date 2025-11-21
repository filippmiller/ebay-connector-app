#!/usr/bin/env bash
# Backend startup script for Railway
# Notes:
# - Pure LF line endings so bash inside the container does not see stray CR characters
# - Use bash-safe strict mode with pipefail now that we ensure bash is used
set -Eeuo pipefail

# Resolve ROOT_DIR based on this script's location.
# In the container this should typically resolve to /app/backend.
SCRIPT_PATH="${BASH_SOURCE[0]:-$0}"
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
ROOT_DIR="$SCRIPT_DIR"

echo "[entry] Backend SCRIPT_PATH=${SCRIPT_PATH}"
echo "[entry] Backend ROOT_DIR resolved to: ${ROOT_DIR}"

# Detect Alembic CLI if available
ALEMBIC_BIN=""
if command -v alembic >/dev/null 2>&1; then
  ALEMBIC_BIN="$(command -v alembic)"
  echo "[entry] Found Alembic CLI at: ${ALEMBIC_BIN}"
else
  echo "[entry] Alembic CLI not found on PATH; will try python -m alembic"
fi

# Resolve Python binary:
# 1) Respect $PYTHON_BIN if already set.
# 2) Prefer project virtualenvs if they exist.
# 3) Fall back to python3/python on PATH.
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

if [ ! -x "$PYTHON_BIN" ]; then
  echo "[entry] ERROR: PYTHON_BIN '$PYTHON_BIN' is not executable" >&2
  exit 1
fi

echo "[entry] Using PYTHON_BIN=${PYTHON_BIN}"

# Log which Python is actually running
"$PYTHON_BIN" - << 'EOF'
import sys
print("[entry] Python executable:", sys.executable)
EOF

# Ensure pip is available
if ! "$PYTHON_BIN" -m pip --version >/dev/null 2>&1; then
  echo "[entry] FATAL: pip is not available for PYTHON_BIN=${PYTHON_BIN}" >&2
  exit 1
fi

# Helper to ensure a Python package is importable; installs via pip if missing
ensure_python_package() {
  local module_name="$1"
  local pip_spec="$2"

  if "$PYTHON_BIN" -c "import ${module_name}" 2>/dev/null; then
    echo "[entry] Python module '${module_name}' import OK"
    return 0
  fi

  echo "[entry] Python module '${module_name}' missing; installing via pip (${pip_spec})..."
  if ! "$PYTHON_BIN" -m pip install --no-cache-dir "${pip_spec}"; then
    echo "[entry] FATAL: pip install failed for ${pip_spec}" >&2
    return 1
  fi

  if "$PYTHON_BIN" -c "import ${module_name}" 2>/dev/null; then
    echo "[entry] Python module '${module_name}' import OK after pip install"
    return 0
  else
    echo "[entry] FATAL: Python module '${module_name}' still not importable after pip install" >&2
    return 1
  fi
}

# Ensure critical Python modules (FastAPI + uvicorn) are present
# Force-install Alembic to ensure `python -m alembic` works even if a system
# package without __main__ is present.
echo "[entry] Ensuring Alembic is installed via pip (alembic==1.17.0)..."
if ! "$PYTHON_BIN" -m pip install --no-cache-dir "alembic==1.17.0"; then
  echo "[entry] WARNING: pip install for alembic failed; migrations may fail" >&2
else
echo "[entry] Alembic pip install completed"
fi

# Ensure pydantic-settings (import name: pydantic_settings) is available for config and Alembic env
if ! ensure_python_package "pydantic_settings" "pydantic-settings==2.11.0"; then
  echo "[entry] FATAL: pydantic_settings is required for application config" >&2
  exit 1
fi

# Ensure PostgreSQL driver (psycopg2 via psycopg2-binary) is available for SQLAlchemy
if ! ensure_python_package "psycopg2" "psycopg2-binary==2.9.11"; then
  echo "[entry] FATAL: psycopg2 is required for PostgreSQL connections" >&2
  exit 1
fi

# Ensure python-jose (import name: jose) for JWT/auth
if ! ensure_python_package "jose" "python-jose==3.5.0"; then
  echo "[entry] FATAL: python-jose is required for JWT authentication" >&2
  exit 1
fi

if ! ensure_python_package "fastapi" "fastapi[standard]==0.119.0"; then
  echo "[entry] FATAL: fastapi is required to start the API server" >&2
  exit 1
fi

if ! ensure_python_package "uvicorn" "uvicorn==0.32.0"; then
  echo "[entry] FATAL: uvicorn is required to start the API server" >&2
  exit 1
fi

# Ensure cryptography is available for eBay webhook signature verification
# (app.services.ebay_signature imports from cryptography.exceptions).
if ! ensure_python_package "cryptography" "cryptography"; then
  echo "[entry] FATAL: cryptography is required for eBay notification signature verification" >&2
  exit 1
fi

# Ensure MSSQL SQLAlchemy dialect for pytds is available for admin tools
# (DB Explorer MSSQL tab and Dual-DB Migration Studio). This installs the
# pure-Python driver that provides the `mssql+pytds` dialect.
if ! ensure_python_package "sqlalchemy_pytds" "sqlalchemy-pytds==1.0.2"; then
  echo "[entry] FATAL: sqlalchemy-pytds is required for MSSQL connections" >&2
  exit 1
fi

export PYTHONUNBUFFERED=1
echo "[entry] Starting backend service..."
echo "[entry] PORT=${PORT:-8000}"
echo "[entry] Database configured: ${DATABASE_URL:+yes}"

# 1) Alembic migrations (can be disabled with RUN_MIGRATIONS=0 in Railway Variables).
if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
  echo "[entry] Checking Alembic state..."
  cd /app

  # Helper to run Alembic either via CLI or python -m
  run_alembic() {
    if [ -n "$ALEMBIC_BIN" ]; then
      "$ALEMBIC_BIN" "$@"
    else
      "$PYTHON_BIN" -m alembic "$@"
    fi
  }

  # Retry function for migrations with exponential backoff
  run_migrations_with_retry() {
    max_attempts=3
    attempt=1
    delay=2

    while [ "$attempt" -le "$max_attempts" ]; do
      echo "[entry] Migration attempt $attempt/$max_attempts (upgrade heads)..."

      if run_alembic upgrade heads; then
        echo "[entry] Migrations completed successfully!"
        return 0
      else
        if [ "$attempt" -lt "$max_attempts" ]; then
          echo "[entry] Migration attempt $attempt failed, retrying in ${delay}s..."
          sleep "$delay"
          delay=$((delay * 2))  # Exponential backoff: 2s, 4s, 8s
        else
          echo "[entry] All migration attempts failed, continuing anyway..."
        fi
      fi

      attempt=$((attempt + 1))
    done

    return 1
  }

  echo "[entry] alembic current before:"
  run_alembic current -v || echo "[entry] No current revision found"
  echo "[entry] alembic heads:"
  run_alembic heads || echo "[entry] Unable to list Alembic heads"
  echo "[entry] Running migrations with retry logic (upgrade heads)..."
  run_migrations_with_retry || {
    echo "[entry] WARNING: Migrations failed after retries, continuing anyway..."
  }
fi

# 2) Start the application (exec so the process stays attached to container lifecycle).
echo "[entry] Starting uvicorn server..."
exec "$PYTHON_BIN" -m uvicorn app.main:app \
  --host 0.0.0.0 --port "${PORT:-8000}" \
  --log-level debug --proxy-headers --forwarded-allow-ips="*"
