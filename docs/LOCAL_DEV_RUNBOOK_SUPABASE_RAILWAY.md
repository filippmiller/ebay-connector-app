# eBay Connector App — Local Dev Runbook (Supabase + Railway)

This document systematizes how we understand the frontend and backend and where their environment comes from during testing. For TESTING ONLY we rely on Railway Variables as the single source of truth. Do NOT paste secrets into this file. In production, all values will be rotated and stored strictly as secrets.

Status
- Stack: FastAPI backend + React/Vite frontend
- Env source: Railway Variables (per Service + Environment)
- DB: Supabase Postgres (Session Pooler, TLS).

What lives where (variables by responsibility)
- Backend-only (never expose to frontend)
  - DATABASE_URL (Supabase pooled DSN; requires sslmode=require)
  - SUPABASE_SERVICE_ROLE_KEY
  - SECRET_KEY / JWT_SECRET (if used)
  - EBAY_* credentials (production/sandbox), FRONTEND_URL, ALLOWED_ORIGINS, etc.
- Frontend public (safe for client)
  - VITE_SUPABASE_URL
  - VITE_SUPABASE_ANON_KEY

Where to look up values (no secrets shown here)
- Railway CLI (service/env scoped):
  - List as JSON
    - `npx -y @railway/cli@latest variables --json --service $env:SVC --environment $env:ENV`
  - Write to file (local reference only; do not commit):
    - PowerShell: `npx -y @railway/cli@latest variables --json --service $env:SVC --environment $env:ENV | Out-File -FilePath _vars.json -Encoding utf8`

DB sanity (no secret output)
- Verify SELECT 1 using Railway env injection (backend dir):
  - `npx -y @railway/cli@latest run --service $env:SVC --environment $env:ENV -- python -c "import os,psycopg2; d=os.environ['DATABASE_URL']; c=psycopg2.connect(d, connect_timeout=6); cur=c.cursor(); cur.execute('select 1'); print('DB_OK'); c.close()"`
- If it fails with AUTH/OperationalError, ensure DATABASE_URL is the exact Supabase Session Pooler string (user=postgres, host=*.pooler.supabase.com, port 5432 or 6543, sslmode=require).

Backend — install, migrate, run (always via Railway env)
- From `backend/`:
  - Install: `npx -y @railway/cli@latest run --service $env:SVC --environment $env:ENV -- poetry install`
  - Migrate: `npx -y @railway/cli@latest run --service $env:SVC --environment $env:ENV -- poetry run alembic upgrade head`
  - Start API: `npx -y @railway/cli@latest run --service $env:SVC --environment $env:ENV -- poetry run uvicorn app.main:app --host 127.0.0.1 --port 8081 --reload`
- Health check: http://127.0.0.1:8081/healthz
- If port 8081 is busy (Windows):
  - `Get-NetTCPConnection -LocalPort 8081 -State Listen | Select OwningProcess`
  - `Stop-Process -Id <PID> -Force`

Frontend — run with public VITE_* only
- From `frontend/`:
  - Install: `npx -y @railway/cli@latest run --service $env:SVC --environment $env:ENV -- npm ci` (or `npm install`)
  - Dev server: `npx -y @railway/cli@latest run --service $env:SVC --environment $env:ENV -- npm run dev`
  - Vite will read VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY from the injected Railway env.
  - Open: usually http://127.0.0.1:5173

Troubleshooting quick refs
- DB auth failures: confirm DATABASE_URL user/host/port/sslmode. Try session pooler on 5432; if needed, 6543; hosts aws-0 / aws-1 for us-east-1.
- Alembic heads diverged: merge, then upgrade
  - `poetry run alembic merge heads -m "merge heads"`
  - `poetry run alembic upgrade head`
- Frontend auth loop: confirm VITE_* variables are present (Railway) and visible in the dev shell.

Runbook recap (Windows PowerShell)
1) Verify CLI: `npx -y @railway/cli@latest --version`
2) Backend/install: `cd backend; npx -y @railway/cli@latest run --service $env:SVC --environment $env:ENV -- poetry install`
3) DB sanity (SELECT 1) as above
4) Alembic: `npx -y @railway/cli@latest run --service $env:SVC --environment $env:ENV -- poetry run alembic upgrade head`
5) Start API: `npx -y @railway/cli@latest run --service $env:SVC --environment $env:ENV -- poetry run uvicorn app.main:app --host 127.0.0.1 --port 8081 --reload`
6) Frontend: `cd ../frontend; npx -y @railway/cli@latest run --service $env:SVC --environment $env:ENV -- npm ci; npx -y @railway/cli@latest run --service $env:SVC --environment $env:ENV -- npm run dev`

Notes
- This file intentionally contains no secret values; the authoritative values live in Railway Variables. During testing they can be used openly by authorized developers via the Railway CLI. On production cutover, rotate all credentials and store strictly as secrets.
