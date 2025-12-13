#!/usr/bin/env bash
set -euo pipefail

# Install Microsoft ODBC Driver 18 for SQL Server inside a Debian-based
# Railway / Nixpacks build image.
#
# Usage with Railway + Nixpacks (recommended):
#   - Add an environment variable in Railway:
#       NIXPACKS_PREBUILD="bash scripts/install_msodbc18.sh"
#   - Trigger a new deploy.
#
# This script:
#   1. Adds Microsoft's package signing key.
#   2. Adds the Microsoft package feed for Debian 11 (bullseye) by default.
#   3. Installs the msodbcsql18 package.
#
# You can override the distro config path via MSODBCSQL_DISTRO, e.g.:
#   MSODBCSQL_DISTRO="debian/12".

DISTRO_CONFIG_PATH="${MSODBCSQL_DISTRO:-debian/11}"

echo "[msodbc18] Using Microsoft feed config for: ${DISTRO_CONFIG_PATH}" >&2

echo "[msodbc18] Adding Microsoft GPG key..." >&2
curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | apt-key add - >/dev/null

echo "[msodbc18] Adding Microsoft package feed..." >&2
curl -fsSL "https://packages.microsoft.com/config/${DISTRO_CONFIG_PATH}/prod.list" \
  > /etc/apt/sources.list.d/mssql-release.list

echo "[msodbc18] Updating apt package index..." >&2
apt-get update -y >/dev/null

echo "[msodbc18] Installing msodbcsql18 (accepting EULA)..." >&2
ACCEPT_EULA=Y apt-get install -y msodbcsql18 >/dev/null

echo "[msodbc18] Installed drivers:" >&2
if command -v odbcinst >/dev/null 2>&1; then
  odbcinst -q -d || true
else
  echo "[msodbc18] odbcinst not found; skipping driver listing" >&2
fi

echo "[msodbc18] Microsoft ODBC Driver 18 installation complete." >&2
