# GitHub Environments Deployment Guide

**Goal:** Secrets live in GitHub Environments, automatically sync to Cloudflare Pages (frontend) and Railway (backend). Site opens online, login works.

## Architecture

**Single Source of Truth:** GitHub Environments (staging/production)

**Platforms:**
- **Cloudflare Pages** - Frontend with public env vars (BASE_URL, API_PUBLIC_BASE_URL, ALLOWED_ORIGINS)
- **Railway** - Backend API with private env vars (DATABASE_URL, JWT_SECRET, EBAY_*, CRON_SECRET)

**Request Flow:**
```
Browser → Cloudflare Pages → /api/* → Pages Function (proxy) → Railway API
```

## Step 0: Verify PR #4 Files

Ensure these files exist in the repository:
- ✅ `frontend/CONFIG.md` - Frontend configuration documentation
- ✅ `frontend/.env.example` - Example environment variables
- ✅ `frontend/functions/api/[[path]].ts` - Cloudflare Pages Function proxy
- ✅ `frontend/src/lib/apiClient.ts` - Axios client with storage-based tokens
- ✅ `frontend/src/auth/AuthContext.tsx` - Robust auth context
- ✅ `frontend/vite.config.ts` - Vite dev proxy configuration
- ✅ `.github/workflows/sync-secrets.yml` - GitHub Actions workflow for secret sync

## Step 1: Create GitHub Environments

1. Go to GitHub repository → **Settings** → **Environments**
2. Click **New environment**
3. Create environment: `staging`
4. Click **New environment**
5. Create environment: `production`

## Step 2: Add Secrets to GitHub Staging Environment

Go to **Settings** → **Environments** → **staging** → **Add Secret**

### Frontend/Public Variables

| Secret Name | Example Value | Description |
|------------|---------------|-------------|
| `APP_ENV` | `staging` | Environment name |
| `BASE_URL` | `https://ebay-connector-staging.pages.dev` | Frontend URL |
| `API_PUBLIC_BASE_URL` | `https://ebay-api-staging.up.railway.app` | Backend API URL |
| `ALLOWED_ORIGINS` | `https://ebay-connector-staging.pages.dev,https://*.pages.dev` | CORS allowed origins |

### Backend/Private Variables

| Secret Name | Example Value | Description |
|------------|---------------|-------------|
| `DATABASE_URL` | `postgresql://user:pass@host:5432/db` | PostgreSQL connection string |
| `JWT_SECRET` | `<openssl rand -hex 32>` | JWT signing secret (32+ chars) |
| `EBAY_ENV` | `PRODUCTION` | eBay environment (SANDBOX or PRODUCTION) |
| `EBAY_CLIENT_ID` | `YourApp-YourApp-PRD-...` | eBay Production App ID |
| `EBAY_CLIENT_SECRET` | `PRD-...` | eBay Production Cert ID |
| `EBAY_RUNAME` | `Your_Company-YourApp-Produc-...` | eBay Production RU Name |
| `OAUTH_STATE_TTL_SEC` | `600` | OAuth state expiration (seconds) |
| `OAUTH_REDIRECT_PATH` | `/connections/callback` | OAuth callback path |
| `WEBHOOK_VERIFY` | `true` | Enable webhook verification |
| `CRON_SECRET` | `<openssl rand -hex 32>` | Cron job authentication secret |
| `CRON_EBAY_REFRESH` | `*/10 * * * *` | Cron schedule for token refresh |

### Platform Access Tokens (for GitHub Actions)

| Secret Name | How to Get | Description |
|------------|------------|-------------|
| `CF_API_TOKEN` | Cloudflare → My Profile → API Tokens → Create Token | Cloudflare API token with Pages:Edit permission |
| `CF_ACCOUNT_ID` | Cloudflare Dashboard → Copy from sidebar | Cloudflare Account ID |
| `CF_PAGES_PROJECT` | Cloudflare Pages → Project name | Pages project name (e.g., `ebay-connector-frontend`) |
| `RAILWAY_TOKEN` | Railway → Account Settings → Tokens → Create | Railway API token |
| `RAILWAY_PROJECT_ID` | Railway → Project Settings → Copy ID | Railway project ID |
| `RAILWAY_ENV_ID` | Railway → Environment → Copy ID | Railway environment ID for staging |

### How to Generate Secrets

```bash
# JWT_SECRET (32 characters)
openssl rand -hex 32

# CRON_SECRET (32 characters)
openssl rand -hex 32
```

### How to Get Platform IDs

**Cloudflare Account ID:**
1. Go to Cloudflare Dashboard
2. Account ID is in the right sidebar

**Cloudflare API Token:**
1. My Profile → API Tokens → Create Token
2. Use template: "Edit Cloudflare Workers"
3. Add permission: Account.Cloudflare Pages:Edit
4. Copy token immediately (shown only once)

**Railway Project ID & Environment ID:**
```bash
# Install Railway CLI
npm install -g @railway/cli

# Login
railway login

# Link to project
railway link

# List environments and get IDs
railway environment

# Or get from Railway dashboard URL:
# https://railway.app/project/<PROJECT_ID>/service/<SERVICE_ID>?environment=<ENV_ID>
```

## Step 3: Run GitHub Action to Sync Secrets

1. Go to GitHub → **Actions** tab
2. Select workflow: **"Sync Secrets to Platforms"**
3. Click **"Run workflow"** button
4. Select environment: `staging`
5. Click **"Run workflow"**
6. Wait for completion (check logs for errors)

**What this does:**
- Pushes frontend env vars to Cloudflare Pages staging environment
- Pushes backend env vars to Railway staging environment

## Step 4: Deploy Frontend to Cloudflare Pages

### Initial Setup (One-time)

1. Go to Cloudflare Dashboard → **Pages**
2. Click **"Create a project"**
3. Connect to GitHub repository: `filippmiller/ebay-connector-app`
4. Configure build settings:
   - **Framework preset:** Vite
   - **Build command:** `cd frontend && npm ci && npm run build`
   - **Build output directory:** `frontend/dist`
   - **Root directory:** `/` (leave empty or set to root)
5. Click **"Save and Deploy"**

### Verify Environment Variables

1. Go to Cloudflare Pages → Your Project → **Settings** → **Environment Variables**
2. Verify these are set for **Preview** and **Production**:
   - `API_PUBLIC_BASE_URL`
   - `BASE_URL`
   - `ALLOWED_ORIGINS`
   - `APP_ENV`

### Deploy

Cloudflare Pages auto-deploys on push to main branch. To manually trigger:
1. Go to Cloudflare Pages → Your Project → **Deployments**
2. Click **"Retry deployment"** or push to trigger new deployment

## Step 5: Deploy Backend to Railway

### Initial Setup (One-time)

1. Go to Railway Dashboard
2. Click **"New Project"**
3. Select **"Deploy from GitHub repo"**
4. Choose repository: `filippmiller/ebay-connector-app`
5. Configure service:
   - **Root directory:** `backend`
   - **Build command:** (Railway auto-detects from Dockerfile)
   - **Start command:** (Railway uses Dockerfile CMD)
6. Create **staging** environment if not exists

### Verify Environment Variables

1. Go to Railway → Your Project → **Variables** tab
2. Switch to **staging** environment
3. Verify all secrets are set (DATABASE_URL, JWT_SECRET, EBAY_*, etc.)

### Run Database Migrations

```bash
# Via Railway CLI
railway link
railway environment staging
railway run alembic upgrade head

# Or via Railway dashboard
# Add one-time deployment command: alembic upgrade head
```

### Deploy

Railway auto-deploys on push to main branch. To manually trigger:
1. Go to Railway → Your Project → **Deployments**
2. Click **"Deploy"** or push to trigger new deployment

## Step 6: Configure eBay Redirect URL

1. Go to **eBay Developer Portal**: https://developer.ebay.com/my/keys
2. Select your **Production** application
3. Click **"User Tokens"** → **"Get OAuth Redirect URI"**
4. Add redirect URI:
   ```
   https://ebay-connector-staging.pages.dev/connections/callback
   ```
   (Replace with your actual staging domain)
5. Click **"Save"**

**Important:** The redirect URI must exactly match: `BASE_URL + OAUTH_REDIRECT_PATH`

## Step 7: Smoke Tests (Staging)

### Test 1: Health Check via Pages Proxy

```bash
curl -I https://ebay-connector-staging.pages.dev/api/healthz
```

**Expected:** `HTTP/2 200`

**If 404:** Verify `API_PUBLIC_BASE_URL` is set in Cloudflare Pages env vars

### Test 2: Direct Backend Health Check

```bash
curl -I https://ebay-api-staging.up.railway.app/healthz
```

**Expected:** `HTTP/2 200`

**If error:** Check Railway logs for backend startup errors

### Test 3: Login Flow

1. Open browser: `https://ebay-connector-staging.pages.dev`
2. Navigate to `/login`
3. Enter admin credentials (create user first if needed)
4. Submit login form

**Verify:**
- ✅ Network tab shows `POST /api/auth/login` → 200
- ✅ `localStorage.auth_token` is set (check DevTools → Application → Local Storage)
- ✅ Automatic `GET /api/auth/me` → 200
- ✅ User redirected to dashboard
- ✅ User email displayed in header
- ✅ No "Loading..." hang or "Signing in..." stuck state

### Test 4: Session Persistence

1. Reload page (F5)

**Verify:**
- ✅ User stays logged in
- ✅ Dashboard loads without redirect to login
- ✅ Network tab shows `GET /api/auth/me` → 200

### Test 5: Logout

1. Click logout button

**Verify:**
- ✅ Redirected to login page
- ✅ `localStorage.auth_token` is cleared
- ✅ Cannot access dashboard without login

### Test 6: eBay OAuth Flow

1. Navigate to **Admin** → **eBay Connection**
2. Click **"Add Account"**

**Verify:**
- ✅ Redirected to eBay authorization page
- ✅ After authorization, redirected back to app
- ✅ Account appears in connection list
- ✅ Token saved in database

## Step 8: Production Deployment

Once staging tests pass, repeat for production:

1. **Create production secrets** in GitHub Environment: `production`
   - Use production domains (e.g., `app.yourdomain.com`, `api.yourdomain.com`)
   - Use production database
   - Use production eBay credentials (if different)

2. **Run sync workflow** with environment: `production`

3. **Configure custom domains:**
   - Cloudflare Pages: Add custom domain `app.yourdomain.com`
   - Railway: Add custom domain `api.yourdomain.com`

4. **Update eBay redirect URL** with production domain

5. **Run smoke tests** on production

### Production Environment Variables

```bash
APP_ENV=production
BASE_URL=https://app.yourdomain.com
API_PUBLIC_BASE_URL=https://api.yourdomain.com
ALLOWED_ORIGINS=https://app.yourdomain.com,https://yourdomain.com
```

## Troubleshooting

### Issue: `/api/healthz` returns 404

**Cause:** Cloudflare Pages Function not deployed or `API_PUBLIC_BASE_URL` not set

**Fix:**
1. Verify `functions/api/[[path]].ts` exists in repository
2. Verify `API_PUBLIC_BASE_URL` is set in Cloudflare Pages environment variables
3. Redeploy frontend to Cloudflare Pages

### Issue: Login hangs or returns 401

**Cause:** CORS misconfiguration or JWT_SECRET mismatch

**Fix:**
1. Verify `ALLOWED_ORIGINS` includes your frontend domain
2. Verify `JWT_SECRET` is set in Railway
3. Check Railway logs: `railway logs`
4. Check browser console for CORS errors

### Issue: eBay OAuth redirect fails

**Cause:** Redirect URL mismatch

**Fix:**
1. Verify eBay redirect URL exactly matches: `BASE_URL + /connections/callback`
2. No trailing slashes
3. Must use HTTPS
4. Verify `EBAY_RUNAME` matches eBay Developer Portal

### Issue: Database connection fails

**Cause:** `DATABASE_URL` not set or incorrect

**Fix:**
1. Verify `DATABASE_URL` is set in Railway environment variables
2. Test connection: `railway run python -c "from app.config import settings; print(settings.DATABASE_URL)"`
3. Check Railway logs for connection errors
4. Verify database is accessible from Railway (check firewall rules)

### Issue: Secrets not syncing

**Cause:** Platform API tokens expired or incorrect permissions

**Fix:**
1. Verify `CF_API_TOKEN` has "Cloudflare Pages:Edit" permission
2. Verify `RAILWAY_TOKEN` is valid (regenerate if needed)
3. Check GitHub Actions logs for specific error messages
4. Verify account IDs and project IDs are correct

## Monitoring & Maintenance

### Cron Jobs

Backend runs automated tasks:
- **Token Refresh:** Every 10 minutes (`CRON_EBAY_REFRESH`)
- **Health Check:** Every 15 minutes

Verify cron is running:
```bash
# Check Railway logs
railway logs --filter "Token refresh"
```

### Logs

**Railway Backend:**
```bash
railway logs
railway logs --filter "error"
```

**Cloudflare Pages:**
- Dashboard → Pages → Your Project → Logs

**GitHub Actions:**
- Repository → Actions → Workflow runs

### Updating Secrets

1. Update secret in GitHub Environment (Settings → Environments → staging/production)
2. Run "Sync Secrets to Platforms" workflow
3. Railway auto-restarts on env var change
4. Cloudflare Pages may need manual redeploy

## Security Checklist

- [ ] All secrets stored only in GitHub Environments (never committed)
- [ ] `.env` files in `.gitignore`
- [ ] `JWT_SECRET` is strong random string (32+ characters)
- [ ] `CRON_SECRET` is strong random string (32+ characters)
- [ ] `DATABASE_URL` uses SSL connection (`?sslmode=require`)
- [ ] `ALLOWED_ORIGINS` only includes your domains (no `*` in production)
- [ ] eBay redirect URL uses HTTPS
- [ ] Cloudflare API token has minimal permissions (Pages:Edit only)
- [ ] Railway API token is kept secure
- [ ] GitHub Environment protection rules enabled for production

## Quick Reference

### Where Secrets Live

| Secret Type | Storage Location | Synced To |
|------------|------------------|-----------|
| All secrets | GitHub Environments | Cloudflare Pages + Railway |
| Frontend public | Cloudflare Pages env vars | Browser (via import.meta.env) |
| Backend private | Railway env vars | Backend process only |

### eBay Redirect URL Format

```
BASE_URL + OAUTH_REDIRECT_PATH
```

Example:
- Staging: `https://ebay-connector-staging.pages.dev/connections/callback`
- Production: `https://app.yourdomain.com/connections/callback`

### Deployment Checklist

- [ ] GitHub Environments created (staging, production)
- [ ] All secrets added to GitHub Environment
- [ ] Platform access tokens configured (CF_API_TOKEN, RAILWAY_TOKEN, etc.)
- [ ] Sync secrets workflow run successfully
- [ ] Cloudflare Pages project created and connected to GitHub
- [ ] Railway project created and connected to GitHub
- [ ] Database migrations run on Railway
- [ ] eBay redirect URL updated in Developer Portal
- [ ] Smoke tests pass (healthz, login, reload, logout)
- [ ] CORS configured correctly
- [ ] Monitoring set up (logs, uptime checks)

## Support

For issues:
1. Check Railway logs: `railway logs`
2. Check Cloudflare Pages deployment logs
3. Check GitHub Actions workflow logs
4. Review `frontend/CONFIG.md` for frontend architecture
5. Review `PRODUCTION_DEPLOYMENT.md` for Railway/Cloudflare details
