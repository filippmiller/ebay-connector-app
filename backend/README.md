# Backend README

## MSSQL Data Migration – Driver (no ODBC required)

The Admin → Data Migration → MSSQL workspace uses SQLAlchemy with the
`mssql+pytds` dialect (provided by `sqlalchemy-pytds`), talking to an
external SQL Server instance.

### Python driver

- Python dependency: `sqlalchemy-pytds` (and its dependency `python-tds`).
- SQLAlchemy URL is built in `app/services/mssql_client.py` using the
  `mssql+pytds` dialect.

### ODBC / system libraries

This implementation does **not** require any system-level ODBC libraries
(`libodbc.so.2`, `msodbcsql18`, etc.). All communication with SQL Server
happens via the pure-Python TDS implementation.

You may keep `unixodbc` packages in the `Aptfile` (they are harmless), but
MSSQL connectivity no longer depends on them.

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
   the driver.

   This repository already includes such a script:

   - Path: `scripts/install_msodbc18.sh`
   - Recommended Railway variable:

     ```text
     NIXPACKS_PREBUILD=bash scripts/install_msodbc18.sh
     ```

   The script defaults to the Microsoft repo config for Debian 11
   (`debian/11`). You can override this by setting `MSODBCSQL_DISTRO`,
   for example `debian/12`.

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