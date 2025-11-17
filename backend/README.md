# Backend README

## MSSQL Data Migration – Driver & ODBC Requirements

The Admin → Data Migration → MSSQL workspace uses SQLAlchemy with the
`mssql+pyodbc` dialect, talking to an external SQL Server instance.

### Python driver

- Python dependency: `pyodbc` (declared in `pyproject.toml`).
- SQLAlchemy URL is built in `app/services/mssql_client.py` using the
  `mssql+pyodbc` dialect.

### ODBC driver on the server

The runtime container must have:

- `libodbc.so.2` and related libraries (from the `unixodbc` / `unixodbc-dev` packages).
- A SQL Server ODBC driver (for example `ODBC Driver 18 for SQL Server`).

By default, the backend will use the driver name from the environment
variable `MSSQL_ODBC_DRIVER` or fall back to:

```text
ODBC Driver 18 for SQL Server
```

If your system uses a different driver name (for example `ODBC Driver 17 for SQL Server`
or a FreeTDS-based driver), set:

```bash
export MSSQL_ODBC_DRIVER="<your-driver-name>"
```

### Railway / Nixpacks notes

When deploying to Railway with Nixpacks:

1. Ensure there is an `Aptfile` in the repository root containing at least:

   ```text
   unixodbc
   unixodbc-dev
   ```

   This makes `libodbc.so.2` available in the container so that `pyodbc`
   can import successfully.

2. Install an actual SQL Server ODBC driver (for example `msodbcsql18`).
   This typically requires adding Microsoft's apt repository. One common
   pattern is to add a prebuild script (via Railway's `NIXPACKS_PREBUILD`
   environment variable) which runs a shell script in the repo to install
   the driver. Example (pseudo-code):

   ```bash
   #!/usr/bin/env bash
   set -euo pipefail

   curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add -
   curl https://packages.microsoft.com/config/debian/12/prod.list \
     > /etc/apt/sources.list.d/mssql-release.list

   apt-get update
   ACCEPT_EULA=Y apt-get install -y msodbcsql18
   ```

   Adjust the distro identifier (`debian/12`) if your base image differs.

### Admin MSSQL test-connection endpoint

- Endpoint: `POST /api/admin/mssql/test-connection`
- Request body: `MssqlConnectionConfig` (host, port, database, username,
  password, encrypt).
- On success, returns:

  ```json
  {
    "ok": true,
    "message": "Connection successful",
    "details": {
      "server_version": "...",
      "driver": "ODBC Driver 18 for SQL Server"
    }
  }
  ```

- On failure, returns:

  ```json
  {
    "ok": false,
    "error": "Short human-readable message",
    "raw_error": "Full driver error string"
  }
  ```

Low-level driver errors such as missing `libodbc.so.2` are sanitized in
`error` but preserved in `raw_error` for easier debugging in logs.