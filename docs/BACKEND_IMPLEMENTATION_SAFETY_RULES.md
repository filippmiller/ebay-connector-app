# Backend implementation safety rules

This document captures concrete rules and checks to avoid breaking the backend
with mistakes similar to the `NameError: name 'get_db' is not defined` incident
that caused the login and API routes to fail after deployment.

## 1. Dependency imports for FastAPI routes

- **Rule 1.1 – Always import dependencies used in `Depends(...)` at module import time.**
  - Any dependency referenced in a route signature (e.g. `db: Session = Depends(get_db)`) must be available **as a name in the module scope** when the router module is imported.
  - Missing imports will cause **import-time NameError** and prevent the entire app from starting, not just that endpoint.

- **Rule 1.2 – Prefer a single canonical `get_db` for SQLAlchemy.**
  - For SQLAlchemy Postgres access, always import from `app.models_sqlalchemy`:
    - `from app.models_sqlalchemy import get_db`
  - Avoid mixing different `get_db` sources in the same module unless there is a very clear reason (e.g. legacy SQLite path that is fully isolated).

- **Rule 1.3 – Do not rely on relative imports for shared infrastructure.**
  - Use absolute imports for core infrastructure pieces like DB sessions:
    - ✅ `from app.models_sqlalchemy import get_db`
    - 🚫 `from ..models_sqlalchemy import get_db` in top-level routers (makes refactoring and grepping harder).

- **Rule 1.4 – When adding a new router endpoint, always run a quick import check.**
  - At least run `python -m py_compile backend/app/routers/<router>.py` locally after editing to catch missing names.
  - Optionally run a one-shot app import: `python -c "import app.main"` to prove all routers load.

## 2. SQLAlchemy Session usage

- **Rule 2.1 – Always import `Session` when using typed DB deps.**
  - If a route uses `db: Session = Depends(get_db)`, ensure:
    - `from sqlalchemy.orm import Session` is imported.
  - Missing `Session` imports can surface as typing/runtime confusion; explicit import keeps code consistent and self-documenting.

- **Rule 2.2 – Use SQLAlchemy `Session` for ORM access, legacy `db` service only for legacy models.**
  - New functionality that reads/writes ORM tables should use `Session` from `app.models_sqlalchemy.get_db`.
  - Legacy `app.database.db` should be restricted to older, non-SQLAlchemy paths and not mixed into new endpoints without a clear rationale.

## 3. Router consistency for DB access

- **Rule 3.1 – For each router, pick ONE DB access style per concern (ORM vs legacy).**
  - If a router file already uses `from app.models_sqlalchemy import get_db` and SQLAlchemy models, keep new endpoints on the same stack.
  - If a router uses `from app.database import get_db` and legacy tables, do not introduce mixed patterns unless explicitly needed.

- **Rule 3.2 – Avoid inline imports of `get_db` unless absolutely necessary.**
  - Importing `get_db` inside a function (`from app.database import get_db`) makes it harder to statically check for NameError issues.
  - Prefer top-level imports; inline imports should be reserved for heavy or optional dependencies.

## 4. Post-change verification checklist

Any time a backend change is made (especially adding routes, workers, or
refactoring imports), execute the following minimal checklist **before
pushing**:

1. **Static import check**
   - `python -m py_compile backend/app/routers/*.py` (or at least the files you touched).
   - `python -c "import app.main"` to ensure FastAPI app imports all routers without errors.

2. **Local smoke test (if possible)**
   - Start the API locally (e.g. `uvicorn app.main:app --reload`) and hit at least:
     - `/auth/login` (login flow)
     - Any newly added endpoints (e.g. `/ebay/returns`).

3. **CI / Railway logs quick scan pattern**
   - After deploying to Railway, run:
     - `railway logs --service <service> --environment production --lines 100 --filter "NameError OR ImportError OR ModuleNotFoundError"`
   - Ensure there are **zero** hits before concluding the deployment is healthy.

## 5. Patterns to watch for in future implementations

When adding new functionality (routes, workers, background tasks), explicitly
check for the following anti-patterns and fix them before commit:

- **Missing imports**:
  - Using `Depends(get_db)` or any other dependency without a matching import.
  - Using `Session` type annotations without importing it from `sqlalchemy.orm`.

- **Inconsistent DB helpers**:
  - Mixing `app.database.get_db` and `app.models_sqlalchemy.get_db` in the same
    module without a clear boundary.

- **Silent inline imports**:
  - Inline `from app.database import get_db` or similar inside functions that
    hide dependency structure from static analysis.

- **Unverified router changes**:
  - Adding new endpoints or changing import paths in `backend/app/routers/*` and
    skipping the import/smoke tests.

By following these rules and checklists, we reduce the risk of introducing
import-time errors that take down the entire backend (such as the
`NameError: name 'get_db' is not defined` incident) and keep future
implementations safer and more predictable.
