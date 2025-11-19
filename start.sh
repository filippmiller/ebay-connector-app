#!/usr/bin/env bash
# Root start script. In Railway this is used as the service start command.
# Delegate to backend/start.sh using bash explicitly.
set -Eeuo pipefail

SCRIPT_PATH="${BASH_SOURCE[0]:-$0}"
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
ROOT_DIR="$SCRIPT_DIR"

echo "[entry-root] SCRIPT_PATH=${SCRIPT_PATH}"
echo "[entry-root] ROOT_DIR=${ROOT_DIR}"
echo "[entry-root] Delegating to backend/start.sh via bash..."

exec /usr/bin/env bash "${ROOT_DIR}/backend/start.sh"
