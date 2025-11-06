# Login Fix Checklist - Starting Fresh

## Problem
Login requests are going to `app-vatxxrtj.fly.dev` instead of Railway backend via Cloudflare proxy.

## Root Cause
- `apiClient.ts` had hardcoded Fly.dev URL check for `devinapps.com`
- Environment variables in Cloudflare Pages might be overriding `/api` default

## Fixes Applied

### ✅ 1. Frontend: apiClient.ts
- **REMOVED** all Fly.dev and devinapps.com references
- **ADDED** logging to show which URL is being used
- **ADDED** warnings if environment variables bypass Cloudflare proxy
- **DEFAULT** is now always `/api` (Cloudflare proxy)

### ✅ 2. Cloudflare Proxy Function
- Located at: `functions/api/[[path]].ts`
- Routes `/api/*` requests to Railway backend
- Handles CORS headers correctly
- Status: ✅ Already correct

### ✅ 3. Backend CORS Configuration
- Located at: `backend/app/main.py`
- Includes Cloudflare Pages URL in allowed origins
- Status: ✅ Already correct

## Required Cloudflare Pages Environment Variables

### ✅ MUST HAVE:
- `API_PUBLIC_BASE_URL` = `https://ebay-connector-app-production.up.railway.app`

### ❌ MUST NOT HAVE (delete if present):
- `VITE_API_BASE_URL` - will bypass Cloudflare proxy
- `VITE_API_URL` - will bypass Cloudflare proxy  
- `VITE_API_PREFIX` - might cause issues

## Testing Steps

1. **Verify Cloudflare Pages Variables:**
   - Go to Cloudflare Pages → Your Project → Settings → Environment Variables
   - Ensure `API_PUBLIC_BASE_URL` is set to Railway URL
   - Delete any `VITE_API_*` variables

2. **Wait for Deployment:**
   - Cloudflare Pages should auto-deploy after git push
   - Wait 1-2 minutes for deployment to complete

3. **Clear Browser Cache:**
   - Press Ctrl+Shift+Delete (or Cmd+Shift+Delete on Mac)
   - Or use Incognito/Private window

4. **Test Login:**
   - Open browser console (F12)
   - Look for `[API] Using /api (Cloudflare proxy -> Railway backend)` message
   - Try to login
   - Check console for:
     - ✅ Requests going to `/api/auth/login` (NOT Fly.dev)
     - ✅ `[CF Proxy]` logs (if viewing Cloudflare logs)
     - ✅ No CORS errors
     - ✅ Login successful

## Expected Console Output

**On page load:**
```
[API] Using /api (Cloudflare proxy -> Railway backend)
```

**On login attempt:**
```
[Auth] Attempting login for: your@email.com
[API] Request to: /api/auth/login
[Auth] Login successful
```

**If environment variable is set (WARNING):**
```
[API] VITE_API_BASE_URL is set: https://some-url.com
[API] This will bypass Cloudflare proxy! Consider removing this variable.
```

## Troubleshooting

### If requests still go to Fly.dev:
1. Check browser console for `[API]` messages
2. Verify no `VITE_API_*` variables in Cloudflare Pages
3. Clear browser cache completely
4. Check Network tab - what URL is actually being called?

### If CORS errors:
1. Verify `API_PUBLIC_BASE_URL` is set correctly in Cloudflare Pages
2. Check Railway backend is running and accessible
3. Verify backend CORS includes Cloudflare Pages URL

### If 500 errors:
1. Check Railway logs for backend errors
2. Verify backend is running and healthy
3. Check `/healthz` endpoint on Railway

## Files Changed
- `frontend/src/lib/apiClient.ts` - Removed Fly.dev, added logging

