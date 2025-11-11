# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

Project overview
- Monorepo with a Python FastAPI backend and a React + TypeScript (Vite) frontend
- Default local stack: backend on http://localhost:8000, frontend on http://localhost:5173
- Backend supports SQLite (default) and PostgreSQL (e.g., Supabase over Postgres) via DATABASE_URL
- eBay OAuth integration with token storage, multi-account support, structured connect logs, and background workers

Commands you will commonly use
Backend (FastAPI / Poetry)
- Install deps
  - cd backend
  - poetry install
- Run dev server (auto-reload)
  - poetry run fastapi dev app/main.py --port 8000
- Environment (backend/.env). Minimum for auth + eBay OAuth:
  - SECRET_KEY or JWT_SECRET, ALGORITHM (default HS256), ACCESS_TOKEN_EXPIRE_MINUTES
  - ALLOWED_ORIGINS (comma-separated), FRONTEND_URL
  - DATABASE_URL (sqlite:///./ebay_connector.db by default; set to postgresql://... for hosted Postgres)
  - eBay credentials depend on environment (settings.EBAY_ENVIRONMENT = sandbox|production)
    - Sandbox: EBAY_SANDBOX_CLIENT_ID, EBAY_SANDBOX_CERT_ID, EBAY_SANDBOX_RUNAME
    - Production: EBAY_PRODUCTION_CLIENT_ID, EBAY_PRODUCTION_CERT_ID, EBAY_PRODUCTION_RUNAME
- Database migrations (Alembic)
  - Upgrade to latest: poetry run alembic upgrade head  (startup scripts also attempt upgrade, with retry)
  - Show heads/current: poetry run alembic heads; poetry run alembic current
  - Create revision (autogenerate): poetry run alembic revision -m "msg" --autogenerate
  - Downgrade one step: poetry run alembic downgrade -1
- Health checks
  - API: GET http://localhost:8000/healthz
  - DB: GET http://localhost:8000/healthz/db

Frontend (Vite / Node)
- Install deps
  - cd frontend
  - npm install
- Run dev server
  - npm run dev
- Build
  - npm run build
  - Prebuild step generates src/config/build.generated.ts and public/version.json from git metadata
- Lint
  - npm run lint
- E2E tests (Playwright)
  - All: npx playwright test
  - Single: npx playwright test path/to/spec.spec.ts -g "test name pattern"

Operational architecture and environment
- Frontend
  - Vite + React (TypeScript), Tailwind CSS, shadcn/ui
  - Dev proxy: /api → http://127.0.0.1:8000 (path /api is stripped by proxy)
  - Cloudflare Pages proxy in production: functions/api/[[path]].ts forwards /api/* → API_PUBLIC_BASE_URL, preserving headers (incl. Set-Cookie, X-Request-ID)
- Backend
  - FastAPI app (backend/app/main.py)
    - Request ID middleware (+ X-Request-ID on responses)
    - CORS from settings.ALLOWED_ORIGINS plus FRONTEND_URL fallback
    - Routers: auth, ebay, ebay_accounts, offers/inventory/orders/messages/financials/etc.
    - Startup:
      - Logs DB URL (masked)
      - Runs Alembic migrations with retry (backend/start.sh); falls back to table creation if needed
      - Starts background workers (token refresh ~10m; health check ~15m)
  - Data layer
    - app/services/database.py selects SQLite vs Postgres implementation
    - SQLAlchemy models in app/models_sqlalchemy/models.py (users, inventory, listings, buying, warehouses, tokens/logs, etc.)
    - Alembic config wired to settings.DATABASE_URL (backend/alembic/env.py)
  - eBay integration
    - OAuth: app/services/ebay.py builds authorization URL per environment and exchanges codes for tokens
    - Identity endpoint: GET /identity/v1/oauth2/userinfo (Bearer token)
    - Many eBay endpoints require header: X-EBAY-C-MARKETPLACE-ID: EBAY_US
    - Required scopes (common): base api_scope + sell.account, sell.fulfillment, sell.finances, sell.inventory; add trading or commerce.message if Messages are needed
  - Logging
    - app/utils/logger.py sanitizes credentials in logs
    - Dedicated connect logger stores structured request/response previews for OAuth/token exchanges

Environments and CI/CD
- Local development
  - Backend: poetry run fastapi dev app/main.py; SQLite by default, or set DATABASE_URL for Postgres
  - Frontend: npm run dev; Vite proxies /api to backend
  - Quick smoke for login/proxy (Windows): scripts/test-login-config.ps1
- Production/staging
  - Backend on Railway (recommended by docs):
    - Startup script backend/start.sh auto-runs Alembic (RUN_MIGRATIONS=1 by default)
    - Configure env vars: DATABASE_URL, JWT_SECRET, ALLOWED_ORIGINS, FRONTEND_URL, eBay creds per env
  - Frontend on Cloudflare Pages:
    - Set API_PUBLIC_BASE_URL to point to the backend (e.g., Railway URL)
    - Cloudflare Function functions/api/[[path]].ts proxies /api/* to backend
- GitHub Actions
  - .github/workflows/sync-secrets.yml (manual, workflow_dispatch) syncs env vars to:
    - Cloudflare Pages (frontend): API_PUBLIC_BASE_URL, BASE_URL, ALLOWED_ORIGINS, APP_ENV
    - Railway (backend): DATABASE_URL, JWT_SECRET, APP_ENV, API_PUBLIC_BASE_URL, BASE_URL, ALLOWED_ORIGINS, EBAY_* and others
  - After syncing, deploy frontend on Cloudflare Pages and backend on Railway
- Supabase
  - Used as hosted Postgres (DATABASE_URL); migrations are managed by Alembic in this repo (no Supabase migration CI present)

Key implementation notes from docs
- Inventory/Offers: fetch inventory items first, then get offers per SKU (docs/INVENTORY_OFFERS_SYNC.md)
- Identity API: use /identity/v1/oauth2/userinfo; verify scopes if username/user_id are None (docs/TOKEN_VALIDATION_GUIDE.md)
- Headers: include X-EBAY-C-MARKETPLACE-ID: EBAY_US where required
- Sandbox vs Production: tokens are stored per environment; ensure EBAY_* vars for the selected environment; UI may switch environments (see docs/SANDBOX_PRODUCTION_PLAN.md)
- Protected configs to avoid breaking login/proxy (see docs/PROTECTED_FILES.md):
  - Frontend API client should default to /api (proxied), not hardcode backend URLs
  - Cloudflare Function must preserve headers (Set-Cookie, X-Request-ID) and add CORS

File pointers
- Backend entrypoint: backend/app/main.py
- Settings: backend/app/config.py; Alembic: backend/alembic/env.py & backend/alembic/versions/*
- Startup scripts: backend/start.sh (prod), backend/entrypoint.sh (legacy)
- eBay service: backend/app/services/ebay.py; accounts: backend/app/routers/ebay_accounts.py
- Frontend config: frontend/vite.config.ts, frontend/eslint.config.js, frontend/tailwind.config.js
- Cloudflare proxy: functions/api/[[path]].ts (and frontend/functions/api/[[path]].ts)
- CI: .github/workflows/sync-secrets.yml
