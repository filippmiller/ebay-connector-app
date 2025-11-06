# Protected Files - DO NOT MODIFY Without Explicit Approval

**Last Updated:** 2025-11-06  
**Status:** ✅ Login is working! These files are critical and must be protected.

## ⚠️ CRITICAL: These files are working correctly. Do NOT modify them without explicit user approval.

---

## What Fixed Login

### Root Cause
Login was broken because:
1. **`.env` files** contained Fly.dev URLs that were baked into the build
2. **`apiClient.ts`** had hardcoded Fly.dev URL check for `devinapps.com`
3. **Environment variables** in Cloudflare Pages were bypassing the Cloudflare proxy

### Solution Applied
1. ✅ **Deleted** `frontend/.env` (contained `VITE_API_URL=https://app-qngipkhc.fly.dev`)
2. ✅ **Removed** Fly.dev from `frontend/.env.production` (was `VITE_API_BASE_URL=https://app-vatxxrtj.fly.dev`)
3. ✅ **Fixed** `frontend/src/lib/apiClient.ts`:
   - Removed hardcoded Fly.dev URL check
   - Removed `devinapps.com` check
   - Added environment variable logging
   - Default to `/api` (Cloudflare proxy)
4. ✅ **Verified** Cloudflare proxy function is correct
5. ✅ **Verified** Backend CORS includes Cloudflare Pages URL

---

## Protected Files

### 🔴 CRITICAL - Frontend API Client

**File:** `frontend/src/lib/apiClient.ts`

**Why Protected:**
- This file determines where API requests go
- **MUST** default to `/api` (Cloudflare proxy)
- **MUST NOT** have hardcoded Fly.dev or devinapps.com URLs
- **MUST** log environment variables for debugging

**Current Working State:**
```typescript
// ✅ CORRECT: Default to /api
return "/api";

// ❌ WRONG: Never do this
if (window.location.hostname.includes('devinapps.com')) {
  return 'https://app-vatxxrtj.fly.dev'; // NEVER!
}
```

**Rules:**
- ✅ DO: Use `/api` as default
- ✅ DO: Log environment variables for debugging
- ✅ DO: Warn if `VITE_API_*` variables are set
- ❌ DON'T: Add hardcoded Fly.dev URLs
- ❌ DON'T: Add `devinapps.com` checks
- ❌ DON'T: Remove environment variable logging

---

### 🔴 CRITICAL - Environment Files

**Files:**
- `frontend/.env` - **DELETED** (was causing issues)
- `frontend/.env.production` - **MUST NOT** contain Fly.dev URLs

**Why Protected:**
- These files are baked into the build at compile time
- If they contain Fly.dev URLs, those URLs will be hardcoded in the JavaScript bundle
- This bypasses Cloudflare proxy and causes CORS errors

**Current Working State:**
```bash
# ✅ CORRECT: frontend/.env.production
# VITE_API_BASE_URL removed - using /api (Cloudflare proxy) instead

# ❌ WRONG: Never do this
VITE_API_BASE_URL=https://app-vatxxrtj.fly.dev
VITE_API_URL=https://app-qngipkhc.fly.dev
```

**Rules:**
- ✅ DO: Keep `frontend/.env` deleted (or empty)
- ✅ DO: Keep `frontend/.env.production` without `VITE_API_*` variables pointing to Fly.dev
- ❌ DON'T: Add Fly.dev URLs to `.env` files
- ❌ DON'T: Add `VITE_API_BASE_URL` or `VITE_API_URL` pointing to Railway directly (bypasses proxy)

---

### 🟡 IMPORTANT - Cloudflare Proxy Function

**File:** `functions/api/[[path]].ts`

**Why Protected:**
- This is the Cloudflare Pages Function that proxies `/api/*` requests to Railway
- Handles CORS headers correctly
- Routes requests from frontend to backend

**Current Working State:**
- ✅ Proxies `/api/*` to Railway backend
- ✅ Handles CORS preflight (OPTIONS)
- ✅ Adds CORS headers to responses
- ✅ Logs requests for debugging

**Rules:**
- ✅ DO: Keep CORS headers handling
- ✅ DO: Keep logging for debugging
- ✅ DO: Keep error handling
- ❌ DON'T: Remove CORS headers
- ❌ DON'T: Change proxy routing logic

---

### 🟡 IMPORTANT - Backend CORS Configuration

**File:** `backend/app/main.py` (lines 26-41)

**Why Protected:**
- Configures CORS for the FastAPI backend
- Must include Cloudflare Pages URL in allowed origins
- Required for frontend to make requests

**Current Working State:**
```python
# ✅ CORRECT: Includes Cloudflare Pages URL
cloudflare_url = os.getenv("FRONTEND_URL", "https://ebay-connector-frontend.pages.dev")
if cloudflare_url not in origins:
    origins.append(cloudflare_url)
```

**Rules:**
- ✅ DO: Keep Cloudflare Pages URL in allowed origins
- ✅ DO: Keep `allow_credentials=True`
- ❌ DON'T: Remove Cloudflare Pages URL from origins
- ❌ DON'T: Change CORS middleware configuration

---

### 🟡 IMPORTANT - Authentication Router

**File:** `backend/app/routers/auth.py`

**Why Protected:**
- Handles login/register endpoints
- Working correctly with proper error handling
- Includes request ID logging

**Current Working State:**
- ✅ Login endpoint works correctly
- ✅ Proper error handling
- ✅ Request ID logging for debugging

**Rules:**
- ✅ DO: Keep error handling
- ✅ DO: Keep request ID logging
- ❌ DON'T: Change authentication logic without testing

---

## Cloudflare Pages Environment Variables

### ✅ MUST HAVE:
- `API_PUBLIC_BASE_URL` = `https://ebay-connector-app-production.up.railway.app`

### ❌ MUST NOT HAVE (delete if present):
- `VITE_API_BASE_URL` - will bypass Cloudflare proxy
- `VITE_API_URL` - will bypass Cloudflare proxy
- `VITE_API_PREFIX` - might cause issues

---

## How to Verify Login is Working

1. **Check Console:**
   ```
   [API] ✅ Using /api (Cloudflare proxy -> Railway backend)
   [Auth] Login successful, token received
   ```

2. **Check Network Tab:**
   - Requests should go to `/api/auth/login`
   - NOT to `app-vatxxrtj.fly.dev`
   - Status should be 200 (success) or 401/422 (invalid credentials)

3. **Check for Errors:**
   - No CORS errors
   - No Fly.dev URLs in requests
   - No timeout errors

---

## Modification Protocol

**Before modifying any protected file:**

1. ✅ Get explicit user approval
2. ✅ Document what you're changing and why
3. ✅ Test thoroughly after changes
4. ✅ Verify login still works
5. ✅ Update this document if changes are approved

**If login breaks after modification:**
1. ⚠️ Immediately revert changes
2. ⚠️ Check this document for correct configuration
3. ⚠️ Verify environment variables
4. ⚠️ Check console for errors

---

## Summary

**Key Principle:** 
- Frontend → `/api` → Cloudflare Proxy → Railway Backend
- **NEVER** bypass Cloudflare proxy with direct Railway URLs
- **NEVER** use Fly.dev URLs anywhere

**Files to Protect:**
1. `frontend/src/lib/apiClient.ts` - API client configuration
2. `frontend/.env.production` - Environment variables
3. `functions/api/[[path]].ts` - Cloudflare proxy
4. `backend/app/main.py` - CORS configuration
5. `backend/app/routers/auth.py` - Authentication endpoints

**Status:** ✅ All files are in working state. Login is functional.
