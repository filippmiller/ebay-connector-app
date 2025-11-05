# Deployment Forensics Report

## Executive Summary

**Problem:** Frontend at https://ebay-connector-app-0uyvn1o1.devinapps.com shows old UI from main branch (commit 20824c1) without new features (terminal, build metadata). Multiple devinapps domains exist causing confusion.

**Root Cause:** Hard-coded devinapps domains in backend CORS configuration and lack of deployment domain pinning capability.

**Impact:** 
- Production site serves stale code without build metadata guardrail
- Backend CORS doesn't include canonical production domain
- No automated verification that deployed code matches intended commit
- Multiple deployment domains exist (0uyvn1o1 vs 0uvyn1o1) causing confusion

---

## Evidence

### 1. Live Site Status (Step 1)

**URL:** https://ebay-connector-app-0uyvn1o1.devinapps.com

**Finding:** Site does not have `/version.json` endpoint
- Request to `/version.json` returns `index.html` (404 fallback)
- This confirms the live site is running old deployment without build metadata guardrail
- Build metadata guardrail was added to main branch in latest commits but not deployed

**Proof:** `artifacts/live-version-A.json`

---

### 2. Hard-coded Domains in Codebase (Step 2)

**Search Results:** 1002 URL references found across codebase

**Critical Findings:**

#### Backend CORS Configuration (`backend/app/main.py` lines 13-18)
```python
allow_origins=[
    "https://ebay-ui-app-b6oqapk8.devinapps.com",      # Hard-coded domain A
    "https://ebay-connection-app-k0ge3h93.devinapps.com",  # Hard-coded domain B
    "http://localhost:5173",
    "http://localhost:3000",
    "*"  # Wildcard - INSECURE for production
],
```

**Issues:**
- Two hard-coded devinapps domains that don't match canonical domain (0uyvn1o1)
- Wildcard `*` allows any origin (security risk)
- Canonical domain `https://ebay-connector-app-0uyvn1o1.devinapps.com` is NOT in the list
- No environment variable configuration for ALLOWED_ORIGINS

#### Frontend Build Metadata (`frontend/scripts/write-build-meta.mjs` line 17)
```javascript
const domain = 'ebay-connector-app-0uyvn1o1.devinapps.com';
```

**Issue:** Domain is hard-coded in build script instead of reading from environment

#### Frontend Dist Artifacts
**Finding:** Built frontend/dist contains embedded devinapps.com URLs in JavaScript bundles
- This happens because some API calls or configuration embeds the domain at build time
- Proof: `artifacts/url-findings-dist.txt` shows devinapps.com in compiled assets

**Proof:** `artifacts/url-findings.csv` (1002 rows), `artifacts/url-findings-dist.txt`

---

### 3. Git History Analysis (Step 3)

**Search:** Commits introducing devinapps.com and ebay-connector-app- domains

**Key Findings from `artifacts/git-domain-history.diff`:**

The git history shows multiple commits adding different devinapps domains:
- `ebay-ui-app-b6oqapk8.devinapps.com` - Added to CORS early in development
- `ebay-connection-app-k0ge3h93.devinapps.com` - Added later
- `ebay-connector-app-0uyvn1o1.devinapps.com` - Canonical domain, added to build script

**Pattern:** Each deployment created a new devinapps subdomain, and domains were hard-coded into CORS configuration rather than using environment variables.

**Proof:** `artifacts/git-domain-history.diff` (2044 lines)

---

### 4. Deployment History (Step 4)

**Search:** Bash history and logs for deployment commands

**Findings from `artifacts/devin-deploy-urls.txt` (60 entries):**

Multiple deployment commands found in history:
- References to both frontend and backend deployments
- Multiple devinapps domains mentioned
- No consistent deployment target or domain pinning

**Key Issue:** The deploy tool does not support a `--domain` parameter to pin deployments to a specific URL. Each deployment may create or update different devinapps subdomains based on the active Devin session.

**Proof:** `artifacts/devin-deploy-urls.txt`

---

### 5. Backend CORS Configuration (Step 5)

**Current CORS Origins (Production):**
```
✅ https://ebay-ui-app-b6oqapk8.devinapps.com
✅ https://ebay-connection-app-k0ge3h93.devinapps.com
✅ http://localhost:5173 (dev)
✅ http://localhost:3000 (dev)
✅ * (wildcard - INSECURE)
```

**Missing:**
```
❌ https://ebay-connector-app-0uyvn1o1.devinapps.com (canonical production domain)
```

**Issues:**
1. Canonical production domain not in CORS whitelist
2. Old/deprecated domains still present
3. Wildcard `*` allows any origin (security vulnerability)
4. No environment variable for ALLOWED_ORIGINS
5. No distinction between staging/preview/production origins

**Proof:** `artifacts/cors-findings.txt`, `backend/app/main.py` lines 11-25

---

## Root Cause Analysis

### Primary Issues

1. **Hard-coded Domains in Backend CORS**
   - Backend CORS configuration has hard-coded devinapps domains
   - Canonical production domain (0uyvn1o1) is missing from CORS whitelist
   - No environment-based configuration for origins

2. **No Deployment Domain Pinning**
   - Deploy tool lacks `--domain` parameter to target specific URL
   - Each deployment may create/update different devinapps subdomains
   - No verification that deployment went to intended domain

3. **Missing Build Metadata Verification**
   - Live site doesn't have `/version.json` endpoint
   - No automated check that deployed code matches intended commit
   - No way to verify which branch/commit is running in production

4. **Hard-coded Domain in Build Script**
   - Build metadata script has hard-coded domain instead of reading from env
   - This embeds the domain into built artifacts

### Secondary Issues

1. **Wildcard CORS Origin**
   - Using `*` in CORS origins is insecure for production
   - Should be removed and replaced with explicit domain list

2. **Multiple Deprecated Domains**
   - Old devinapps domains still in CORS configuration
   - No cleanup of deprecated domains

3. **No Environment Separation**
   - Same CORS configuration for dev/staging/production
   - No way to configure different origins per environment

---

## Fix Plan

### Phase 1: Centralize Domain Configuration (Immediate)

#### Backend Changes

**File:** `backend/app/config.py`
```python
# Add new settings
ALLOWED_ORIGINS: str = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:5173,http://localhost:3000"
)
FRONTEND_URL: str = os.getenv(
    "FRONTEND_URL",
    "http://localhost:5173"
)
```

**File:** `backend/app/main.py`
```python
# Replace hard-coded origins with environment-based configuration
from app.config import settings

origins = settings.ALLOWED_ORIGINS.split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # Read from environment
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600,
)
```

#### Frontend Changes

**File:** `frontend/scripts/write-build-meta.mjs`
```javascript
// Read domain from environment instead of hard-coding
const domain = process.env.DEPLOY_DOMAIN || 'localhost:5173';
```

**File:** `frontend/.env.production` (create)
```bash
DEPLOY_DOMAIN=ebay-connector-app-0uyvn1o1.devinapps.com
VITE_API_URL=https://app-vatxxrtj.fly.dev
```

### Phase 2: Add Post-Deploy Verification (Immediate)

**File:** `scripts/verify-deployment.sh` (create)
```bash
#!/bin/bash
set -e

DEPLOY_URL=$1
EXPECTED_COMMIT=$(git rev-parse --short HEAD)

echo "Verifying deployment at $DEPLOY_URL"
echo "Expected commit: $EXPECTED_COMMIT"

# Fetch version.json from deployed site
DEPLOYED_VERSION=$(curl -sf "$DEPLOY_URL/version.json" || echo "{}")
DEPLOYED_COMMIT=$(echo "$DEPLOYED_VERSION" | jq -r '.commit // "unknown"')

echo "Deployed commit: $DEPLOYED_COMMIT"

if [ "$DEPLOYED_COMMIT" != "$EXPECTED_COMMIT" ]; then
    echo "❌ DEPLOYMENT VERIFICATION FAILED"
    echo "Expected: $EXPECTED_COMMIT"
    echo "Deployed: $DEPLOYED_COMMIT"
    exit 1
fi

echo "✅ Deployment verified successfully"
```

### Phase 3: Update Deployment Process (Immediate)

**Deployment Checklist:**

1. **Before Deploy:**
   - Ensure on correct branch (main for production)
   - Run `git status` to verify clean working directory
   - Run `npm run build` in frontend directory
   - Verify `dist/version.json` contains correct commit hash

2. **Deploy:**
   - Since deploy tool doesn't support `--domain`, deploy must be done from the Devin session that owns the canonical domain
   - Alternative: Use Cloudflare Pages or Railway with branch-based deployment

3. **After Deploy:**
   - Run verification script: `./scripts/verify-deployment.sh https://ebay-connector-app-0uyvn1o1.devinapps.com`
   - Check `/version.json` endpoint returns correct commit
   - Verify CORS allows requests from production domain
   - Test critical user flows (login, sync operations)

### Phase 4: Environment Variables Configuration

**Production Environment Variables:**

**Backend (Railway/Fly.io):**
```bash
ALLOWED_ORIGINS=https://ebay-connector-app-0uyvn1o1.devinapps.com,https://ebay-connector-app.pages.dev
FRONTEND_URL=https://ebay-connector-app-0uyvn1o1.devinapps.com
DATABASE_URL=<postgres-connection-string>
JWT_SECRET=<secret>
# ... other secrets
```

**Frontend (Build Environment):**
```bash
DEPLOY_DOMAIN=ebay-connector-app-0uyvn1o1.devinapps.com
VITE_API_URL=https://app-vatxxrtj.fly.dev
```

### Phase 5: Cleanup (After Verification)

1. **Remove deprecated domains from CORS:**
   - Remove `ebay-ui-app-b6oqapk8.devinapps.com`
   - Remove `ebay-connection-app-k0ge3h93.devinapps.com`
   - Remove wildcard `*`

2. **Archive wrong deployment:**
   - Archive/disable the `ebay-connector-app-0uvyn1o1.devinapps.com` session (letters "vy")
   - Keep only canonical `ebay-connector-app-0uyvn1o1.devinapps.com` (letters "uy")

3. **Update documentation:**
   - Document canonical production URL
   - Document deployment process with verification steps
   - Document environment variable requirements

---

## Recommended Patch

See `artifacts/deployment-fix.patch` for the complete diff to implement Phase 1 and Phase 2 changes.

**Summary of Changes:**
- Remove hard-coded domains from backend CORS
- Add ALLOWED_ORIGINS and FRONTEND_URL to backend config
- Update frontend build script to read domain from environment
- Create deployment verification script
- Add .env.production template for frontend

---

## Post-Deploy Smoke Tests

After applying the patch and deploying:

1. **Version Verification:**
   ```bash
   curl -s https://ebay-connector-app-0uyvn1o1.devinapps.com/version.json | jq .
   # Should return: {"number":6,"branch":"main","commit":"<current-commit>",...}
   ```

2. **CORS Verification:**
   ```bash
   curl -I -H "Origin: https://ebay-connector-app-0uyvn1o1.devinapps.com" \
     https://app-vatxxrtj.fly.dev/healthz
   # Should include: Access-Control-Allow-Origin: https://ebay-connector-app-0uyvn1o1.devinapps.com
   ```

3. **Frontend Verification:**
   - Open https://ebay-connector-app-0uyvn1o1.devinapps.com
   - Check browser console: `fetch('/version.json').then(r=>r.json()).then(console.log)`
   - Should show build metadata with correct commit

4. **Terminal Verification:**
   - Login to the app
   - Navigate to /ebay/test
   - Click "Sync Orders" button
   - Terminal should appear immediately with run_id
   - Terminal should stream live events from backend

---

## Conclusion

The deployment issue stems from hard-coded domains in backend CORS configuration and lack of deployment domain pinning. The fix requires:

1. Centralizing domain configuration in environment variables
2. Adding post-deploy verification with version.json checks
3. Updating deployment process to verify correct domain and commit
4. Cleaning up deprecated domains and removing wildcard CORS

**Next Steps:**
1. Apply the patch (see Phase 7)
2. Configure environment variables for production
3. Deploy with verification
4. Archive wrong deployment domain
5. Update documentation

**Estimated Time:** 2-3 hours for implementation and verification
