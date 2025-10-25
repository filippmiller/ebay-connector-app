# Production Deployment Guide - Railway + Cloudflare Pages

This guide covers deploying the eBay Connector application to production using Railway (backend) and Cloudflare Pages (frontend).

## Overview

- **Backend**: FastAPI on Railway (https://api.PROD_DOMAIN)
- **Frontend**: Vite/React on Cloudflare Pages (https://app.PROD_DOMAIN)
- **Database**: Supabase PostgreSQL (existing)

---

## Part 1: Railway Backend Deployment

### 1.1 Prerequisites

- Railway account with GitHub connected
- Access to filippmiller/ebay-connector-app repository
- Production eBay API credentials

### 1.2 Create Railway Service

1. Go to Railway dashboard (https://railway.app)
2. Click "New Project" → "Deploy from GitHub repo"
3. Select `filippmiller/ebay-connector-app`
4. Select branch: `main` (or your production branch)
5. Set service name: `ebay-connector-api`
6. Railway will auto-detect the Dockerfile in `/backend` directory

### 1.3 Configure Environment Variables

In Railway project settings → Variables, add the following:

#### Required Environment Variables:

```
EBAY_ENV=PRODUCTION
EBAY_ENVIRONMENT=production

# eBay Production Credentials
EBAY_PRODUCTION_CLIENT_ID=<your-production-client-id>
EBAY_PRODUCTION_CERT_ID=<your-production-cert-id>
EBAY_PRODUCTION_DEV_ID=<your-production-dev-id>
EBAY_PRODUCTION_RUNAME=<your-production-runame>

# Database (Supabase)
SUPABASE_URL=<your-supabase-url>
SUPABASE_SERVICE_ROLE_KEY=<your-supabase-service-role-key>
DATABASE_URL=postgresql://postgres:<password>@db.nrpfahjygulsfxmbmfzv.supabase.co:5432/postgres?sslmode=require

# Application URLs
APP_URL=https://api.PROD_DOMAIN
FRONTEND_URL=https://app.PROD_DOMAIN

# Security
JWT_SECRET=<generate-strong-random-secret>
SECRET_KEY=<generate-strong-random-secret>

# MADN Verification (if applicable)
MADN_VERIFICATION_TOKEN=<your-madn-token>
```

**Note**: Replace `PROD_DOMAIN` with your actual production domain (e.g., `ebayconnector.com`)

#### Optional Environment Variables:

```
# If using external Postgres besides Supabase RPC
DATABASE_URL=<external-postgres-url>

# Port (Railway sets this automatically)
PORT=8000
```

### 1.4 Configure Service Settings

In Railway service settings:

**Health Check**:
- Path: `/healthz`
- Expected status: 200

**Scaling**:
- Memory: 512MB
- Workers: 2 (configured in Dockerfile via gunicorn)
- Auto-scaling: Enable if needed

**Deployment**:
- Auto-deploy: Enable for `main` branch
- Build command: Uses Dockerfile automatically
- Start command: Defined in Dockerfile (gunicorn with uvicorn workers)

### 1.5 Custom Domain Setup

1. In Railway service → Settings → Networking
2. Click "Generate Domain" to get Railway domain (e.g., `ebay-connector-api.up.railway.app`)
3. Add custom domain: `api.PROD_DOMAIN`
4. Railway will provide DNS configuration (see DNS section below)

---

## Part 2: Cloudflare Pages Frontend Deployment

### 2.1 Prerequisites

- Cloudflare account
- GitHub repository access
- Domain managed in Cloudflare DNS

### 2.2 Create Cloudflare Pages Project

1. Go to Cloudflare dashboard → Pages
2. Click "Create a project" → "Connect to Git"
3. Select GitHub → `filippmiller/ebay-connector-app`
4. Configure build settings:
   - **Project name**: `ebay-connector-frontend`
   - **Production branch**: `main`
   - **Framework preset**: Vite
   - **Build command**: `cd frontend && npm ci && npm run build`
   - **Build output directory**: `frontend/dist`
   - **Root directory**: `/` (leave empty or set to root)

### 2.3 Configure Environment Variables

In Cloudflare Pages → Settings → Environment variables → Production:

```
# Vite environment variables (primary)
VITE_API_URL=https://api.PROD_DOMAIN
VITE_APP_URL=https://app.PROD_DOMAIN
VITE_SUPABASE_URL=<your-supabase-url>
VITE_EBAY_ENV=PRODUCTION

# Next.js compatibility variables (for future migration)
NEXT_PUBLIC_API_URL=https://api.PROD_DOMAIN
NEXT_PUBLIC_APP_URL=https://app.PROD_DOMAIN
NEXT_PUBLIC_SUPABASE_URL=<your-supabase-url>
NEXT_PUBLIC_EBAY_ENV=PRODUCTION
```

**Note**: Replace `PROD_DOMAIN` with your actual production domain

### 2.4 Enable Auto-Deploy

In Cloudflare Pages → Settings → Builds & deployments:
- Enable "Automatic deployments" for `main` branch
- Enable "Preview deployments" for pull requests (optional)

### 2.5 Custom Domain Setup

1. In Cloudflare Pages → Custom domains
2. Click "Set up a custom domain"
3. Enter: `app.PROD_DOMAIN`
4. Cloudflare will automatically configure DNS if domain is in same account

---

## Part 3: DNS Configuration (Cloudflare)

### 3.1 Backend API Domain (api.PROD_DOMAIN)

If using Railway:

1. Go to Cloudflare → DNS → Records
2. Add CNAME record:
   - **Type**: CNAME
   - **Name**: `api`
   - **Target**: `<your-railway-domain>.up.railway.app` (from Railway)
   - **Proxy status**: DNS only (grey cloud) initially, then enable proxy after SSL works
   - **TTL**: Auto

### 3.2 Frontend App Domain (app.PROD_DOMAIN)

If domain is in Cloudflare (same account as Pages):
- DNS is configured automatically when adding custom domain to Pages project

If domain is external:
1. Add CNAME record:
   - **Type**: CNAME
   - **Name**: `app`
   - **Target**: `<pages-project>.pages.dev`
   - **TTL**: Auto

### 3.3 Enable HTTPS

1. In Cloudflare → SSL/TLS → Overview
2. Set SSL/TLS encryption mode: "Full (strict)"
3. Wait for SSL certificates to provision (usually 5-15 minutes)
4. Verify HTTPS works for both domains

---

## Part 4: eBay App Configuration (Production)

### 4.1 Update eBay Developer Portal

1. Go to eBay Developer Portal: https://developer.ebay.com
2. Navigate to your **Production** application (not sandbox)
3. Update Application Settings:

**Redirect URI (OAuth)**:
- Add: `https://api.PROD_DOMAIN/ebay/auth/callback`
- Ensure this matches exactly (including `/ebay/auth/callback` path)

**RU Name (Redirect URL Name)**:
- Verify the Production RUName matches the one in your Railway environment variables
- Format typically: `Your_Company_Name-YourAppN-Produc-xxxxx`

**Grant Application Access**:
- Ensure all required scopes are enabled:
  - `https://api.ebay.com/oauth/api_scope/sell.fulfillment`
  - `https://api.ebay.com/oauth/api_scope/sell.finances`
  - `https://api.ebay.com/oauth/api_scope/sell.inventory`
  - `https://api.ebay.com/oauth/api_scope/sell.marketing`
  - Any other scopes your app requires

### 4.2 Verify Credentials

Ensure the following Production credentials are set in Railway:
- `EBAY_PRODUCTION_CLIENT_ID` (App ID)
- `EBAY_PRODUCTION_CERT_ID` (Cert ID)
- `EBAY_PRODUCTION_DEV_ID` (Dev ID)
- `EBAY_PRODUCTION_RUNAME` (RU Name)

---

## Part 5: Post-Deployment Verification

### 5.1 Backend Health Check

```bash
curl https://api.PROD_DOMAIN/healthz
# Expected: {"status":"ok"}

curl https://api.PROD_DOMAIN/
# Expected: {"message":"eBay Connector API","version":"1.0.0","docs":"/docs"}
```

### 5.2 API Documentation

Visit: `https://api.PROD_DOMAIN/docs`
- Should show FastAPI Swagger UI
- Verify all endpoints are listed

### 5.3 Frontend Access

1. Open: `https://app.PROD_DOMAIN`
2. Verify the app loads without errors
3. Check browser console for any API connection errors

### 5.4 OAuth Flow Test

1. Log in to the frontend app
2. Navigate to "Add eBay Account" or similar
3. Click to connect eBay account
4. Should redirect to eBay OAuth page
5. After authorization, should redirect back to `https://api.PROD_DOMAIN/ebay/auth/callback`
6. Should then redirect to frontend with success message
7. Verify in database that:
   - User's `ebay_connected` = true
   - Access token and refresh token are stored
   - Token expiration is set correctly

### 5.5 Data Sync Test

1. In the app, trigger "Sync Orders" (or similar)
2. Monitor Railway logs:
   ```bash
   # In Railway dashboard → Deployments → View logs
   # Look for:
   # - "Starting order sync for user: <email>"
   # - "Fetched X orders from eBay"
   # - "Stored X orders in database"
   ```
3. Verify orders appear in the app UI
4. Check database to confirm data is stored

### 5.6 Scheduler/Cron Jobs (if applicable)

If you have background jobs for token refresh and health pings:

**Token Refresh** (every 10 minutes):
- Check Railway logs for token refresh activity
- Verify tokens are being refreshed before expiration

**Health Ping** (every 15 minutes):
- Verify Railway service stays active
- Check for any timeout or connection errors

---

## Part 6: Monitoring & Maintenance

### 6.1 Railway Monitoring

- **Logs**: Railway dashboard → Deployments → View logs
- **Metrics**: Monitor CPU, memory, and request metrics
- **Alerts**: Set up alerts for service downtime

### 6.2 Cloudflare Analytics

- **Traffic**: Cloudflare Pages → Analytics
- **Performance**: Monitor page load times
- **Errors**: Check for 4xx/5xx errors

### 6.3 Database Monitoring

- **Supabase Dashboard**: Monitor database size, connections, queries
- **Backups**: Ensure automatic backups are enabled
- **Performance**: Monitor slow queries

### 6.4 eBay API Rate Limits

- Monitor eBay API usage in Railway logs
- eBay Production limits are higher than sandbox
- Implement rate limiting if needed

---

## Part 7: Rollback Procedure

If deployment fails or issues arise:

### 7.1 Railway Rollback

1. Go to Railway → Deployments
2. Find previous working deployment
3. Click "Redeploy" on that version

### 7.2 Cloudflare Pages Rollback

1. Go to Cloudflare Pages → Deployments
2. Find previous working deployment
3. Click "Rollback to this deployment"

### 7.3 Database Rollback

If database migrations cause issues:
```bash
# Connect to database
# Run Alembic downgrade
alembic downgrade -1  # or specific revision
```

---

## Environment Variables Summary

### Railway Backend Variables (Required):

| Variable | Description | Example |
|----------|-------------|---------|
| `EBAY_ENV` | eBay environment | `PRODUCTION` |
| `EBAY_ENVIRONMENT` | eBay environment (alt) | `production` |
| `EBAY_PRODUCTION_CLIENT_ID` | eBay App ID | `YourAppId-...` |
| `EBAY_PRODUCTION_CERT_ID` | eBay Cert ID | `PRD-...` |
| `EBAY_PRODUCTION_DEV_ID` | eBay Dev ID | `abc123...` |
| `EBAY_PRODUCTION_RUNAME` | eBay RU Name | `Your_Company-...` |
| `SUPABASE_URL` | Supabase project URL | `https://xxx.supabase.co` |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service key | `eyJ...` |
| `DATABASE_URL` | PostgreSQL connection | `postgresql://...` |
| `APP_URL` | Backend URL | `https://api.PROD_DOMAIN` |
| `FRONTEND_URL` | Frontend URL | `https://app.PROD_DOMAIN` |
| `JWT_SECRET` | JWT signing secret | Random 32+ char string |
| `SECRET_KEY` | App secret key | Random 32+ char string |

### Cloudflare Pages Variables (Required):

| Variable | Description | Example |
|----------|-------------|---------|
| `VITE_API_URL` | Backend API URL | `https://api.PROD_DOMAIN` |
| `VITE_APP_URL` | Frontend URL | `https://app.PROD_DOMAIN` |
| `VITE_SUPABASE_URL` | Supabase URL | `https://xxx.supabase.co` |
| `VITE_EBAY_ENV` | eBay environment | `PRODUCTION` |
| `NEXT_PUBLIC_API_URL` | Backend API URL (compat) | `https://api.PROD_DOMAIN` |
| `NEXT_PUBLIC_APP_URL` | Frontend URL (compat) | `https://app.PROD_DOMAIN` |
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase URL (compat) | `https://xxx.supabase.co` |
| `NEXT_PUBLIC_EBAY_ENV` | eBay environment (compat) | `PRODUCTION` |

---

## Manual Steps Required

### Before Deployment:

1. ✅ Generate strong random secrets for `JWT_SECRET` and `SECRET_KEY`
2. ✅ Obtain Production eBay API credentials from eBay Developer Portal
3. ✅ Verify Supabase database is accessible and has latest schema

### During Deployment:

1. ✅ Set all environment variables in Railway
2. ✅ Set all environment variables in Cloudflare Pages
3. ✅ Configure DNS records in Cloudflare
4. ✅ Update eBay App Redirect URI to production URL

### After Deployment:

1. ✅ Test health endpoints
2. ✅ Test OAuth flow end-to-end
3. ✅ Test data synchronization
4. ✅ Verify CORS is working (frontend can call backend)
5. ✅ Monitor logs for errors
6. ✅ Set up monitoring/alerts

---

## Troubleshooting

### Issue: CORS errors in browser console

**Solution**: 
- Verify `FRONTEND_URL` is set correctly in Railway
- Check that frontend URL matches exactly (including https://)
- Clear browser cache and try again

### Issue: OAuth redirect fails

**Solution**:
- Verify eBay Redirect URI matches exactly: `https://api.PROD_DOMAIN/ebay/auth/callback`
- Check that `EBAY_PRODUCTION_RUNAME` matches eBay Developer Portal
- Ensure `EBAY_ENVIRONMENT=production` is set

### Issue: Database connection errors

**Solution**:
- Verify `DATABASE_URL` is correct and includes `?sslmode=require`
- Check Supabase dashboard for connection limits
- Verify Railway can reach Supabase (check firewall rules)

### Issue: Frontend shows "API connection failed"

**Solution**:
- Verify `VITE_API_URL` is set correctly in Cloudflare Pages
- Check that backend is running: `curl https://api.PROD_DOMAIN/healthz`
- Check browser console for specific error messages
- Verify CORS configuration

### Issue: Railway deployment fails

**Solution**:
- Check Railway build logs for specific errors
- Verify Dockerfile syntax is correct
- Ensure all dependencies are in `pyproject.toml`
- Check that `poetry.lock` is committed to repository

### Issue: Cloudflare Pages build fails

**Solution**:
- Check build logs in Cloudflare Pages dashboard
- Verify build command is correct: `cd frontend && npm ci && npm run build`
- Verify output directory is correct: `frontend/dist`
- Check that all npm dependencies are in `package.json`

---

## Production URLs

After deployment, your application will be accessible at:

- **Frontend**: https://app.PROD_DOMAIN
- **Backend API**: https://api.PROD_DOMAIN
- **API Docs**: https://api.PROD_DOMAIN/docs
- **Health Check**: https://api.PROD_DOMAIN/healthz

Replace `PROD_DOMAIN` with your actual production domain.

---

## Security Checklist

- [ ] All secrets are stored in Railway/Cloudflare (not in code)
- [ ] `.env` files are in `.gitignore`
- [ ] HTTPS is enabled for both domains
- [ ] CORS is configured to allow only production frontend
- [ ] JWT secrets are strong random strings (32+ characters)
- [ ] Database uses SSL connection (`?sslmode=require`)
- [ ] eBay Production credentials are kept secure
- [ ] Supabase service role key is not exposed to frontend
- [ ] Rate limiting is configured (if needed)
- [ ] Monitoring and alerts are set up

---

## Next Steps

1. Complete Railway service setup with all environment variables
2. Complete Cloudflare Pages setup with all environment variables
3. Configure DNS records for both domains
4. Update eBay App Redirect URI in Developer Portal
5. Deploy and verify all smoke tests pass
6. Set up monitoring and alerts
7. Document any production-specific configurations
8. Create runbook for common operations

---

## Support

For issues or questions:
- Check Railway logs: Railway dashboard → Deployments → Logs
- Check Cloudflare Pages logs: Cloudflare dashboard → Pages → Deployments
- Review this deployment guide
- Check application logs in Railway for backend errors
