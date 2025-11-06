# Testing Guide for Login Fix

## Quick Test Script

Run this PowerShell script to verify backend configuration:

```powershell
.\scripts\test-login-config.ps1
```

This will check:
- ✅ Railway backend accessibility
- ✅ Login endpoint exists
- ✅ CORS configuration
- ✅ Cloudflare proxy (if accessible)

## Manual Browser Testing

### Step 1: Open Browser Console
1. Open `https://ebay-connector-frontend.pages.dev`
2. Press `F12` to open Developer Tools
3. Go to **Console** tab
4. Clear console (right-click → Clear console)

### Step 2: Check Initial Load
Look for this message when page loads:
```
[API] Using /api (Cloudflare proxy -> Railway backend)
```

**If you see a warning instead:**
```
[API] VITE_API_BASE_URL is set: https://...
[API] This will bypass Cloudflare proxy!
```
→ **PROBLEM**: Delete `VITE_API_BASE_URL` from Cloudflare Pages environment variables

### Step 3: Try Login
1. Enter email and password
2. Click "Sign In"
3. Watch console for:

**✅ GOOD - Should see:**
```
[Auth] Attempting login for: your@email.com
[API] Request to: /api/auth/login
[Auth] Login successful
```

**❌ BAD - If you see:**
```
Access to XMLHttpRequest at 'https://app-vatxxrtj.fly.dev/auth/login'...
```
→ **PROBLEM**: Still using Fly.dev! Check environment variables.

### Step 4: Check Network Tab
1. Go to **Network** tab in Developer Tools
2. Try login again
3. Look for request to `/auth/login`
4. Click on it and check:
   - **Request URL**: Should be `https://ebay-connector-frontend.pages.dev/api/auth/login`
   - **NOT**: `https://app-vatxxrtj.fly.dev/auth/login`
   - **Status**: Should be `200` (success) or `401`/`422` (invalid credentials), NOT `500` or CORS error

## Common Issues & Solutions

### Issue: Requests still go to Fly.dev
**Solution:**
1. Check Cloudflare Pages → Environment Variables
2. Delete ALL `VITE_API_*` variables
3. Clear browser cache completely
4. Hard refresh (Ctrl+Shift+R)

### Issue: CORS errors
**Solution:**
1. Verify `API_PUBLIC_BASE_URL` is set in Cloudflare Pages
2. Check Railway backend is running
3. Verify backend CORS includes Cloudflare Pages URL

### Issue: 500 Internal Server Error
**Solution:**
1. Check Railway logs for backend errors
2. Verify backend is healthy: `https://ebay-connector-app-production.up.railway.app/healthz`
3. Check Railway deployment status

### Issue: Timeout errors
**Solution:**
1. Check Railway backend is running
2. Verify network connectivity
3. Check Cloudflare proxy is working

## What to Report

If login still doesn't work, please provide:

1. **Console output** (screenshot or copy-paste)
2. **Network tab** - the `/auth/login` request details
3. **Cloudflare Pages environment variables** (screenshot)
4. **Railway backend status** (is it running?)

This will help diagnose the issue quickly!

