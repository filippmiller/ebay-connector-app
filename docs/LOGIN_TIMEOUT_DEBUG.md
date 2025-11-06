# Login Timeout Debug Guide

**Date:** 2025-11-06  
**Issue:** Login timeout - `timeout of 15000ms exceeded` for `/auth/Login`

---

## Symptoms

- Login request times out after 15 seconds
- Error: `timeout of 15000ms exceeded`
- URL in console shows `/auth/Login` (with capital L)
- No response from backend

---

## Possible Causes

### 1. Backend Not Running / Failed to Start
- **Check:** Railway logs for startup errors
- **Check:** Backend health endpoint: `https://ebay-connector-app-production.up.railway.app/healthz`
- **Possible issues:**
  - Import errors in recent changes
  - Syntax errors preventing startup
  - Database connection failures
  - Migration failures

### 2. Cloudflare Proxy Issue
- **Check:** Cloudflare Pages Function logs
- **Check:** `API_PUBLIC_BASE_URL` environment variable in Cloudflare Pages
- **Check:** Browser console for `[CF Proxy]` logs
- **Possible issues:**
  - Proxy function not deployed
  - Wrong `API_PUBLIC_BASE_URL` value
  - CORS issues

### 3. Network / DNS Issues
- **Check:** Can access backend directly: `https://ebay-connector-app-production.up.railway.app/healthz`
- **Check:** Railway service status

### 4. URL Case Sensitivity
- **Issue:** Console shows `/auth/Login` but code uses `/auth/login`
- **Check:** Frontend code for any URL transformations
- **Check:** Backend router registration

---

## Debugging Steps

### Step 1: Check Backend Health
```bash
curl https://ebay-connector-app-production.up.railway.app/healthz
```
**Expected:** `{"status": "ok"}`

### Step 2: Check Railway Logs
1. Go to Railway Dashboard
2. Select backend service
3. Check "Deployments" tab for latest deployment status
4. Check "Logs" tab for startup errors

**Look for:**
- Import errors
- Syntax errors
- Database connection errors
- Migration errors

### Step 3: Check Frontend Console
1. Open browser DevTools (F12)
2. Go to Console tab
3. Look for:
   - `[API] Environment check:` logs
   - `[CF Proxy]` logs (if proxy is working)
   - Any error messages

### Step 4: Check Network Tab
1. Open browser DevTools (F12)
2. Go to Network tab
3. Try to login
4. Check:
   - What URL is being called?
   - What's the response status?
   - Is request reaching backend?

### Step 5: Check Cloudflare Pages Settings
1. Go to Cloudflare Pages Dashboard
2. Select project
3. Go to Settings → Environment Variables
4. Verify:
   - `API_PUBLIC_BASE_URL` is set to `https://ebay-connector-app-production.up.railway.app`
   - No `VITE_API_BASE_URL` or `VITE_API_URL` variables (these bypass proxy)

---

## Recent Changes That Could Affect Login

### Files Modified (2025-11-06):
1. `backend/app/services/ebay.py` - Added inventory/offers sync methods
2. `backend/app/services/postgres_ebay_database.py` - Added `upsert_inventory_item()`
3. `backend/app/routers/ebay.py` - Added inventory sync endpoint

### Files NOT Modified (Should be safe):
- `backend/app/routers/auth.py` - Login endpoint unchanged
- `backend/app/main.py` - Router registration unchanged
- `frontend/src/lib/apiClient.ts` - API client unchanged
- `frontend/src/auth/AuthContext.tsx` - Auth logic unchanged

---

## Quick Fixes to Try

### 1. Check if Backend Started
```bash
# Check Railway logs for:
- "eBay Connector API starting up..."
- "✅ Migrations completed successfully!"
- "Starting uvicorn server..."
```

### 2. Verify Backend is Accessible
```bash
curl -v https://ebay-connector-app-production.up.railway.app/healthz
```

### 3. Check Frontend Environment Variables
In browser console, look for:
```
[API] Environment check: {
  VITE_API_BASE_URL: '(not set)',
  VITE_API_URL: '(not set)',
  VITE_API_PREFIX: '(not set)',
  ...
}
[API] ✅ Using /api (Cloudflare proxy -> Railway backend)
```

If you see `VITE_API_BASE_URL` or `VITE_API_URL` set, that's the problem - delete them from Cloudflare Pages.

### 4. Test Direct Backend Access
Try accessing backend directly (bypassing Cloudflare):
- If `VITE_API_BASE_URL` is set, temporarily set it to Railway URL
- Test login
- If it works, problem is in Cloudflare proxy
- If it doesn't work, problem is in backend

---

## Common Issues & Solutions

### Issue: Backend Not Starting
**Symptoms:** No logs in Railway, health endpoint returns 502/503

**Possible causes:**
- Import error in `ebay.py` or `postgres_ebay_database.py`
- Syntax error
- Database connection failure

**Solution:**
1. Check Railway logs for specific error
2. Fix import/syntax errors
3. Verify database connection

### Issue: Cloudflare Proxy Not Working
**Symptoms:** No `[CF Proxy]` logs in browser console, requests timeout

**Possible causes:**
- `API_PUBLIC_BASE_URL` not set in Cloudflare Pages
- Proxy function not deployed
- Wrong `API_PUBLIC_BASE_URL` value

**Solution:**
1. Verify `API_PUBLIC_BASE_URL` in Cloudflare Pages settings
2. Redeploy Cloudflare Pages
3. Check `functions/api/[[path]].ts` exists

### Issue: URL Case Mismatch
**Symptoms:** Console shows `/auth/Login` but code uses `/auth/login`

**Possible causes:**
- URL transformation somewhere
- Case-sensitive routing

**Solution:**
1. Check frontend code for URL transformations
2. Verify backend router uses lowercase `/login`

---

## Next Steps

1. **Check Railway logs** - Most important! This will show if backend started
2. **Check backend health** - Verify backend is accessible
3. **Check Cloudflare proxy** - Verify proxy is working
4. **Check frontend console** - Look for environment variable issues

---

## Files to Check

### Backend:
- `backend/app/main.py` - Router registration
- `backend/app/routers/auth.py` - Login endpoint
- `backend/app/services/ebay.py` - Recent changes (check for import errors)
- `backend/app/services/postgres_ebay_database.py` - Recent changes (check for import errors)

### Frontend:
- `frontend/src/lib/apiClient.ts` - API client configuration
- `frontend/src/auth/AuthContext.tsx` - Login logic
- `frontend/functions/api/[[path]].ts` - Cloudflare proxy function

### Configuration:
- Railway: Environment variables, service status
- Cloudflare Pages: Environment variables, deployment status

