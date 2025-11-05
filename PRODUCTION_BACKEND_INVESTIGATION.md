# Production Backend URL Investigation Report

## Executive Summary

**Production Backend URL:** `https://app-vatxxrtj.fly.dev`

**Frontend Currently Points To:** Dynamic detection in `frontend/src/lib/apiClient.ts:8-9` - when running on devinapps.com, frontend points to `https://app-vatxxrtj.fly.dev`

**Status:** ✅ Frontend correctly points to production backend when running on devinapps.com

**Issues Found:**
1. Backend CORS configuration has hard-coded domains that don't include canonical production frontend
2. No environment variable for API base URL - logic is hard-coded in apiClient.ts
3. Build metadata script has hard-coded domain instead of reading from environment

---

## Investigation Results

### 1. Repository Status

```
Current Branch: main
Current Commit: 20824c1
Remote: https://git-manager.devin.ai/proxy/github.com/filippmiller/ebay-connector-app
```

### 2. API Base URL Configuration

**Search Results:**
- No `VITE_API_BASE_URL` or `VITE_API_URL` environment variables found in codebase
- Only `VITE_API_PREFIX` is documented in `frontend/.env.example`
- `API_PUBLIC_BASE_URL` is referenced in Cloudflare Pages Functions proxy (`frontend/functions/api/[[path]].ts`)

**Frontend API Client Logic** (`frontend/src/lib/apiClient.ts:3-13`):
```typescript
const getBaseURL = () => {
  if (import.meta.env.VITE_API_PREFIX) {
    return import.meta.env.VITE_API_PREFIX;
  }
  
  if (typeof window !== 'undefined' && window.location.hostname.includes('devinapps.com')) {
    return 'https://app-vatxxrtj.fly.dev';  // HARD-CODED FLY.DEV URL
  }
  
  return "/api";
};
```

**Issue:** The fly.dev backend URL is hard-coded in the apiClient logic instead of being configurable via environment variable.

### 3. Environment Files

**backend/.env.example:**
- `DATABASE_URL`
- `SECRET_KEY`
- `EBAY_ENVIRONMENT`
- `EBAY_SANDBOX_CLIENT_ID`, `EBAY_SANDBOX_CERT_ID`, `EBAY_SANDBOX_DEV_ID`
- `EBAY_PRODUCTION_CLIENT_ID`, `EBAY_PRODUCTION_CERT_ID`, `EBAY_PRODUCTION_DEV_ID`, `EBAY_PRODUCTION_RUNAME`

**Missing:** `ALLOWED_ORIGINS`, `FRONTEND_URL`

**frontend/.env.example:**
- `VITE_API_PREFIX=/api`

**Missing:** `VITE_API_BASE_URL`, `VITE_API_URL`, `DEPLOY_DOMAIN`

### 4. Deployment Configuration

**No deployment config files found:**
- ❌ fly.toml
- ❌ railway.json
- ❌ railway.yaml
- ❌ wrangler.toml

**GitHub Workflows:**
- `.github/workflows/sync-secrets.yml` - Secrets synchronization workflow (no deployment commands)

**Conclusion:** Deployments are manual, not automated via CI/CD.

### 5. Built Frontend Analysis

**Build Output:**
```
✓ Generated build.generated.ts
✓ Generated version.json
Build metadata: #6 main@20824c1 2025-11-05T08:25:50.965Z
✓ built in 4.97s
```

**Embedded URLs in dist/assets/index-Bo2PUXVr.js:**
- `app-vatxxrtj.fly.dev` - Backend URL embedded in compiled JavaScript

**version.json:**
```json
{
  "number": 6,
  "branch": "main",
  "commit": "20824c1",
  "ts": "2025-11-05T08:25:50.965Z",
  "domain": "ebay-connector-app-0uyvn1o1.devinapps.com"
}
```

### 6. Backend Runtime Check

**Testing https://app-vatxxrtj.fly.dev/healthz:**
```
GET https://app-vatxxrtj.fly.dev/healthz
Response: {"status":"ok"}
Status: ✅ 200 OK
```

**Testing https://app-vatxxrtj.fly.dev/api/healthz:**
```
GET https://app-vatxxrtj.fly.dev/api/healthz
Response: {"detail":"Not Found"}
Status: ❌ 404 Not Found
```

**Conclusion:** Production backend is at `https://app-vatxxrtj.fly.dev` with `/healthz` endpoint (no `/api` prefix).

---

## Single Source of Truth

### Production Backend URL

**✅ Production Backend:** `https://app-vatxxrtj.fly.dev`

**Evidence:**
1. Hard-coded in `frontend/src/lib/apiClient.ts:9`
2. Embedded in compiled `dist/assets/index-Bo2PUXVr.js`
3. Responds 200 OK to `/healthz` endpoint
4. Referenced in previous deployment documentation

### Frontend API Configuration

**Current Behavior:**
- **File:** `frontend/src/lib/apiClient.ts:8-9`
- **Logic:** When `window.location.hostname.includes('devinapps.com')`, return `'https://app-vatxxrtj.fly.dev'`
- **Fallback:** Returns `"/api"` for other environments

**Issue:** Backend URL is hard-coded instead of being configurable via environment variable.

**Recommended Fix:** Add environment variable fallback order:
1. `VITE_API_BASE_URL` (explicit full backend URL)
2. `VITE_API_URL` (compatibility alias)
3. `VITE_API_PREFIX` (relative path for proxied environments)
4. `"/api"` (default fallback)

---

## Issues Found

### Issue 1: Hard-coded Backend URL in Frontend

**File:** `frontend/src/lib/apiClient.ts:9`
**Line:** `return 'https://app-vatxxrtj.fly.dev';`

**Problem:** Backend URL is hard-coded, making it difficult to:
- Switch backends for staging/preview environments
- Test with different backend instances
- Configure via environment variables

**Impact:** Medium - Works for production but not flexible for other environments

### Issue 2: Backend CORS Missing Canonical Domain

**File:** `backend/app/main.py:13-19`
**Lines:**
```python
allow_origins=[
    "https://ebay-ui-app-b6oqapk8.devinapps.com",
    "https://ebay-connection-app-k0ge3h93.devinapps.com",
    "http://localhost:5173",
    "http://localhost:3000",
    "*"
],
```

**Problem:** 
- Canonical production domain `https://ebay-connector-app-0uyvn1o1.devinapps.com` is NOT in CORS whitelist
- Two deprecated devinapps domains are present
- Wildcard `*` is insecure for production

**Impact:** High - CORS failures from canonical production frontend (mitigated by wildcard `*`)

### Issue 3: Hard-coded Domain in Build Script

**File:** `frontend/scripts/write-build-meta.mjs:20`
**Line:** `const domain = 'ebay-connector-app-0uyvn1o1.devinapps.com';`

**Problem:** Domain is hard-coded instead of reading from `process.env.DEPLOY_DOMAIN`

**Impact:** Low - Only affects build metadata, not runtime behavior

### Issue 4: Missing Environment Variables

**Missing in backend/.env.example:**
- `ALLOWED_ORIGINS` - For CORS configuration
- `FRONTEND_URL` - For frontend URL reference

**Missing in frontend/.env.example:**
- `VITE_API_BASE_URL` - For explicit backend URL
- `VITE_API_URL` - For compatibility
- `DEPLOY_DOMAIN` - For build metadata

**Impact:** Medium - Makes configuration unclear for new deployments

---

## Bonus: Mis-typed URL Search

**Search for mis-typed domain (0uvyn1o1 vs 0uyvn1o1):**

```bash
rg -nS '0uvyn1o1' -g '!node_modules' -g '!.git'
```

**Result:** No mis-typed URLs found in current main branch.

**Note:** The user mentioned a wrong domain `ebay-connector-app-0uvyn1o1.devinapps.com` (letters "vy") that should be archived, but this domain is not hard-coded in the codebase. It likely exists as a separate deployment session that needs to be archived via app.devin.ai.

---

## Recommended Fix

### Phase 1: Make Backend URL Configurable

**File:** `frontend/src/lib/apiClient.ts`

**Current (lines 3-13):**
```typescript
const getBaseURL = () => {
  if (import.meta.env.VITE_API_PREFIX) {
    return import.meta.env.VITE_API_PREFIX;
  }
  
  if (typeof window !== 'undefined' && window.location.hostname.includes('devinapps.com')) {
    return 'https://app-vatxxrtj.fly.dev';
  }
  
  return "/api";
};
```

**Proposed (with environment variable fallback):**
```typescript
const getBaseURL = () => {
  // Prefer explicit base URL from environment
  if (import.meta.env.VITE_API_BASE_URL) {
    return import.meta.env.VITE_API_BASE_URL;
  }
  
  // Compatibility alias
  if (import.meta.env.VITE_API_URL) {
    return import.meta.env.VITE_API_URL;
  }
  
  // Relative prefix for proxied environments
  if (import.meta.env.VITE_API_PREFIX) {
    return import.meta.env.VITE_API_PREFIX;
  }
  
  // Legacy fallback for devinapps (can be removed after env vars are set)
  if (typeof window !== 'undefined' && window.location.hostname.includes('devinapps.com')) {
    return 'https://app-vatxxrtj.fly.dev';
  }
  
  return "/api";
};
```

### Phase 2: Fix Backend CORS Configuration

**File:** `backend/app/main.py`

**Current (lines 11-25):**
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://ebay-ui-app-b6oqapk8.devinapps.com",
        "https://ebay-connection-app-k0ge3h93.devinapps.com",
        "http://localhost:5173",
        "http://localhost:3000",
        "*"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600,
)
```

**Proposed (environment-based):**
```python
from app.config import settings

# Parse ALLOWED_ORIGINS from comma-separated string
origins = [o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600,
)
```

**File:** `backend/app/config.py` (add these settings)

```python
ALLOWED_ORIGINS: str = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:5173,http://localhost:3000"
)

FRONTEND_URL: str = os.getenv(
    "FRONTEND_URL",
    "http://localhost:5173"
)
```

### Phase 3: Fix Build Metadata Script

**File:** `frontend/scripts/write-build-meta.mjs`

**Current (line 20):**
```javascript
const domain = 'ebay-connector-app-0uyvn1o1.devinapps.com';
```

**Proposed:**
```javascript
const domain = process.env.DEPLOY_DOMAIN || '';
```

### Phase 4: Update Environment Examples

**File:** `backend/.env.example` (add)

```bash
# CORS Configuration
ALLOWED_ORIGINS=https://ebay-connector-app-0uyvn1o1.devinapps.com,http://localhost:5173,http://localhost:3000

# Frontend URL
FRONTEND_URL=https://ebay-connector-app-0uyvn1o1.devinapps.com
```

**File:** `frontend/.env.example` (add)

```bash
# API Base URL (full backend URL for devinapps deployment)
VITE_API_BASE_URL=https://app-vatxxrtj.fly.dev

# API URL (compatibility alias)
VITE_API_URL=https://app-vatxxrtj.fly.dev

# API Prefix (relative path for proxied environments)
VITE_API_PREFIX=/api

# Deploy Domain (for build metadata)
DEPLOY_DOMAIN=ebay-connector-app-0uyvn1o1.devinapps.com
```

**File:** `frontend/.env.production` (create)

```bash
# Production environment variables
DEPLOY_DOMAIN=ebay-connector-app-0uyvn1o1.devinapps.com
VITE_API_BASE_URL=https://app-vatxxrtj.fly.dev
```

---

## Production Environment Variables

### Backend (Fly.io)

```bash
ALLOWED_ORIGINS=https://ebay-connector-app-0uyvn1o1.devinapps.com
FRONTEND_URL=https://ebay-connector-app-0uyvn1o1.devinapps.com
DATABASE_URL=<postgres-connection-string>
SECRET_KEY=<secret>
JWT_SECRET=<secret>
EBAY_ENVIRONMENT=production
EBAY_PRODUCTION_CLIENT_ID=<secret>
EBAY_PRODUCTION_CERT_ID=<secret>
EBAY_PRODUCTION_DEV_ID=<secret>
EBAY_PRODUCTION_RUNAME=<secret>
```

### Frontend (Build Environment)

```bash
DEPLOY_DOMAIN=ebay-connector-app-0uyvn1o1.devinapps.com
VITE_API_BASE_URL=https://app-vatxxrtj.fly.dev
```

---

## Next Steps

1. **Create PR branch** with the fixes above
2. **Test locally** with environment variables set
3. **Deploy to production** with new environment variables configured
4. **Verify CORS** works from canonical domain
5. **Archive wrong deployment** (0uvyn1o1) via app.devin.ai

---

## Summary

**Production Backend URL:** `https://app-vatxxrtj.fly.dev`

**Frontend Points To:** Same URL (hard-coded in `frontend/src/lib/apiClient.ts:9`)

**Status:** ✅ Frontend correctly points to production backend

**Critical Issues:**
1. Backend CORS missing canonical production domain (mitigated by wildcard)
2. Backend URL hard-coded instead of configurable via environment
3. Build metadata domain hard-coded

**Recommended Action:** Apply the 4-phase fix to make configuration environment-based and remove hard-coded values.
