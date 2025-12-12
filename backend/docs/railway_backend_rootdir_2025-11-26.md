# Railway backend rootDir mismatch (2025-11-26)

## Context

The eBay Connector App backend is deployed to Railway using Railpack. The
backend lives in a monorepo with the following structure (simplified):

- `backend/` – FastAPI + PostgreSQL backend (this service)
- `frontend/` – React frontend (Cloudflare Pages)
- other project files and tooling

The Railway service for the backend is configured with `rootDir = /backend`.
This means Railpack expects the deployed project to contain a `/backend`
subdirectory and will `cd /backend` before running `bash start.sh` and
backend commands.

## Symptom

Recent deployments started failing immediately with the following message in
Railway **Build Logs**:

> `Could not find root directory: /backend`

The build stopped before installing dependencies or starting Uvicorn.

## Root cause

`railway up` was being executed from **inside** the `backend/` directory
instead of from the monorepo root.

When running `railway up` from the monorepo root (`silent-spirit`), the
uploaded project seen by Railway looks like:

```text
/              ← project root inside Railway
  backend/     ← Python backend (FastAPI)
  frontend/    ← React frontend
  ...
```

In this layout the `/backend` directory exists, so Railpack's `rootDir =
/backend` works.

When `railway up` is run from `silent-spirit/backend`, the uploaded project
looks like:

```text
/              ← this is already the backend dir
  app/
  start.sh
  pyproject.toml
  ...
```

There is **no** `/backend` folder inside that tree. Railpack still tries to
`cd /backend` (per its configuration), fails to find it, and aborts the build
with:

> `Could not find root directory: /backend`

This was a **rootDir vs. CLI working-directory mismatch**, not a Python
application bug.

## Fix

1. **Restore correct deploy working directory**

   - Always run `railway up` from the monorepo root directory (the one that
     contains the `backend/` folder), e.g.:

     ```powershell
     cd C:\Users\filip\.gemini\antigravity\playground\silent-spirit
     railway status      # confirms project/env/service
     railway up --service ebay-connector-app --environment production
     ```

   - With this layout, the deployed project again contains `/backend`, so the
     existing Railpack `rootDir = /backend` configuration works without
     changes.

2. **Runtime import/syntax fixes (minimal)**

   While restoring a clean deploy we also fixed a few minimal issues exposed
   once the service started again:

   - Removed references to a non-existent `admin_profitability` router from:
     - `backend/app/routers/__init__.py`
     - `backend/app/main.py`
   - Re-pointed AI worker configuration imports away from
     `app.config.worker_settings` and into a dedicated module
     `app.config_worker_settings`, avoiding conflicts with the existing
     `app.config` settings module.
   - Fixed small syntax/indentation errors introduced during earlier edits in:
     - `backend/app/services/ebay.py` (app token helper and browse token
       helper)
     - `backend/app/routers/integrations.py` (stray characters before
       `@router` decorators).

   These changes were deliberately minimal and only addressed import/syntax
   problems that prevented the app from starting; no business logic was
   refactored.

3. **Verification**

   - Deploy from monorepo root (`railway up --service ebay-connector-app
     --environment production`) now completes **without** the
     `Could not find root directory: /backend` error.
   - Inside Railway, the following check succeeds:

     ```bash
     railway run poetry -C backend run python -c "import app.main; print('app_import_ok')"
     ```

     Output includes `app_import_ok` and only non-fatal Pydantic warnings.

## Rule for future deployments

For this backend service on Railway:

- **Do NOT** run `railway up` from inside `backend/` unless the Railway
  `rootDir` is explicitly changed to `/`.
- **DO** run deployments from the monorepo root (directory that contains
  `backend/`):

  ```powershell
  cd C:\Users\filip\.gemini\antigravity\playground\silent-spirit
  railway up --service ebay-connector-app --environment production
  ```

This keeps the deployed project layout consistent with `rootDir = /backend`
 and avoids future "Could not find root directory: /backend" failures.
