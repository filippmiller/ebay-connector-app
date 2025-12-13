# Debugging Token Encryption Issue in Railway Worker

## Problem
Railway transactions worker is still using encrypted tokens (`ENC:v1:...`) instead of decrypted tokens (`v^1.1#...`), causing 401 errors.

## Diagnostic Steps

### 1. Check Railway Worker Logs

Go to Railway Dashboard → `aebay-workers-loop` service → Logs

**Look for these log messages:**

#### ✅ GOOD (Token is decrypted):
```
[fetch_active_ebay_token] ✅ Token retrieved successfully: account_id=... token_prefix=v^1.1#... token_is_decrypted=YES
[fetch_transactions] Token validation: ... token_prefix=v^1.1#... token_is_decrypted=YES
```

#### ❌ BAD (Token is still encrypted):
```
[fetch_active_ebay_token] ⚠️ TOKEN STILL ENCRYPTED! account_id=... token_prefix=ENC:v1:...
[fetch_transactions] ⚠️⚠️⚠️ CRITICAL: ENCRYPTED TOKEN RECEIVED! token_prefix=ENC:v1:...
[token_provider] ⚠️ Token property returned ENC:v1:... attempting explicit decryption
```

### 2. Check Which Code Path is Used

**Look for these log messages to understand the flow:**

```
[transactions_proxy] Triggering transactions sync via .../api/admin/internal/workers/transactions/run-once...
```
→ This means Railway worker is using **proxy mode** (GOOD)

OR

```
Running workers cycle (manual code path)...
```
→ This means Railway worker is calling `run_ebay_workers_once()` directly (may have issues)

### 3. Check Token Provider Logs

**Look for:**
```
[token_provider] Token property returned: account_id=... token_prefix=... is_encrypted=YES/NO
```

If `is_encrypted=YES`, it means `token.access_token` property returned `ENC:v1:...`, which indicates:
- `SECRET_KEY` / `JWT_SECRET` is missing or wrong in Railway worker environment
- Decryption failed

### 4. Check Railway Worker Configuration

#### A. Start Command
Railway Dashboard → `aebay-workers-loop` → Settings → Deploy → Start Command

**Should be:**
```bash
python -m app.workers.ebay_workers_loop transactions
```
or
```bash
python -m app.workers.ebay_workers_loop
```

**NOT:**
```bash
python -m app.workers.ebay_workers_loop --direct
```

#### B. Environment Variables
Railway Dashboard → `aebay-workers-loop` → Variables

**Required for proxy mode:**
- `WEB_APP_URL` - URL of main web app (e.g., `https://your-app.railway.app`)
- `INTERNAL_API_KEY` - Shared secret for internal API calls

**Required for direct mode (NOT recommended):**
- `SECRET_KEY` - Must match main web app's `SECRET_KEY`
- `JWT_SECRET` - Must match main web app's `JWT_SECRET`

### 5. Check if Code is Deployed

**Look for in logs:**
```
Starting Transactions-only worker proxy loop...
```
or
```
Starting ALL workers proxy loop...
```

If you see old log messages without our new diagnostic logging, the code hasn't deployed yet.

### 6. Check Token Hash Matching

Compare token hashes between manual and automatic runs:

**Manual Run Now:**
```
[fetch_active_ebay_token] ✅ Token retrieved successfully: ... token_hash=abc123def456 ...
```

**Automatic Worker:**
```
[fetch_active_ebay_token] ✅ Token retrieved successfully: ... token_hash=abc123def456 ...
```

If hashes match → Same token is used (GOOD)
If hashes differ → Different tokens or different accounts

## Common Issues & Fixes

### Issue 1: Railway Worker Not Using Proxy Mode

**Symptom:**
- Logs show `Running workers cycle (manual code path)...`
- No `[transactions_proxy]` messages

**Fix:**
1. Check Start Command in Railway
2. Ensure it's `python -m app.workers.ebay_workers_loop transactions`
3. Ensure `WEB_APP_URL` and `INTERNAL_API_KEY` are set

### Issue 2: Token Property Returns ENC:v1:...

**Symptom:**
```
[token_provider] Token property returned: ... is_encrypted=YES
[token_provider] ⚠️ Token property returned ENC:v1:... attempting explicit decryption
```

**Fix:**
1. Check `SECRET_KEY` / `JWT_SECRET` in Railway worker environment
2. Must match main web app's values
3. Or switch to proxy mode (recommended)

### Issue 3: Code Not Deployed

**Symptom:**
- No new diagnostic log messages
- Still seeing old error messages

**Fix:**
1. Check Railway deployment status
2. Wait for deployment to complete
3. Check git commit is pushed to main branch

### Issue 4: Explicit Decryption Also Fails

**Symptom:**
```
[token_provider] ⚠️ TOKEN STILL ENCRYPTED AFTER ALL ATTEMPTS!
```

**Fix:**
1. `SECRET_KEY` / `JWT_SECRET` is definitely wrong or missing
2. Check Railway worker environment variables
3. Compare with main web app's environment variables

## What to Report

If the issue persists, please provide:

1. **Railway Logs Excerpt:**
   - Last 50-100 lines from `aebay-workers-loop` service
   - Look for `[fetch_active_ebay_token]`, `[token_provider]`, `[fetch_transactions]` messages

2. **Railway Configuration:**
   - Start Command
   - Environment Variables (masked): `WEB_APP_URL`, `INTERNAL_API_KEY`, `SECRET_KEY` (if set)

3. **Error Messages:**
   - Exact error text from logs
   - Token prefix (first 20 chars, e.g., `ENC:v1:qev...` or `v^1.1#i^1#...`)

4. **Manual vs Automatic:**
   - Does manual "Run Now" work?
   - What token prefix does manual show in logs?

