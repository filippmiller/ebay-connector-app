# Transactions Worker Audit & Refactor - 2025-12-04

## Executive Summary

This document summarizes the audit and refactoring of the Transactions worker to ensure consistent behavior between manual "Run Now" and automatic Railway worker loop executions. The primary issue was that automatic runs were experiencing 401 Unauthorized errors, indicating different token handling paths.

**Status:** ✅ Completed

**Key Changes:**
1. Enhanced logging in `fetch_transactions()` to include mode, correlation_id, account_id
2. Unified code path: both manual and automatic use the same `run_transactions_worker_for_account()` function
3. Internal endpoint `/api/admin/internal/workers/transactions/run-once` already exists and is properly configured
4. Railway worker should use proxy mode (`run_transactions_worker_proxy_loop()`) when running as a separate service

---

## Architecture Overview

### Manual "Run Now" Path

```
Frontend (Admin UI)
  ↓
POST /ebay/workers/run?api=transactions&account_id=...
  ↓
ebay_workers.py::run_worker_once()
  ↓
run_transactions_worker_for_account(account_id, triggered_by="manual")
  ↓
TransactionsWorker.run_for_account()
  ↓
BaseWorker.run_for_account()
  ├─→ get_valid_access_token() [unified token provider]
  └─→ TransactionsWorker.execute_sync()
      └─→ EbayService.sync_all_transactions()
          └─→ EbayService.fetch_transactions() [with mode="manual", correlation_id]
```

### Automatic Worker Loop Path (Main App)

```
Main App Startup (main.py)
  ↓
asyncio.create_task(run_ebay_workers_loop())
  ↓
run_ebay_workers_loop() [every 5 minutes]
  ↓
run_ebay_workers_once()
  ├─→ run_token_refresh_job()
  └─→ For each account:
      └─→ run_transactions_worker_for_account(account_id, triggered_by="manual")
          [Same path as manual Run Now]
```

### Automatic Worker Loop Path (Railway Separate Service - RECOMMENDED)

```
Railway Worker Service
  ↓
run_transactions_worker_proxy_loop() [every 5 minutes]
  ↓
run_transactions_worker_proxy_once()
  ↓
HTTP POST /api/admin/internal/workers/transactions/run-once
  ├─→ INTERNAL_API_KEY authentication
  └─→ run_transactions_sync_for_all_accounts(triggered_by="internal_scheduler")
      └─→ For each account:
          └─→ run_transactions_worker_for_account(account_id, triggered_by="internal_scheduler")
              [Same path as manual Run Now, but with mode="automatic"]
```

**Why Proxy Mode?**
- Railway worker service may not have access to the same encryption keys/environment variables
- Web App has the correct token decryption logic
- Ensures 100% identical code path between manual and automatic runs

---

## Key Components

### 1. Unified Token Provider

**Location:** `backend/app/services/ebay_token_provider.py`

**Function:** `get_valid_access_token()`

This is the **single source of truth** for token retrieval. All workers (manual and automatic) use this function, ensuring:
- Consistent token decryption
- Automatic refresh when near expiry
- Proper error handling
- Structured logging

### 2. Transactions Worker

**Location:** `backend/app/services/ebay_workers/transactions_worker.py`

**Key Functions:**
- `run_transactions_worker_for_account()` - Entry point for single account sync
- `run_transactions_sync_for_all_accounts()` - Entry point for all accounts (used by internal endpoint)
- `TransactionsWorker.execute_sync()` - Core sync logic

**Token Handling:**
- Uses `BaseWorker.run_for_account()` which calls `get_valid_access_token()`
- Passes `mode` and `correlation_id` to `EbayService.sync_all_transactions()`

### 3. EbayService.fetch_transactions()

**Location:** `backend/app/services/ebay.py`

**Enhanced Logging:**
- `mode`: "manual", "automatic", or "unknown"
- `correlation_id`: Unique ID for tracking sync batch
- `account_id`: eBay account ID
- `ebay_user_id`: eBay user ID
- `token_hash`: SHA256 hash of token (never raw token)

**Request Logging:**
- HTTP method and URL (without secrets)
- Headers (with Authorization redacted)
- Query parameters
- Mode, correlation_id, account identifiers

**Response Logging:**
- HTTP status code
- Error details on non-2xx
- Total transactions fetched on success
- Mode, correlation_id, account identifiers

### 4. Internal Endpoint

**Location:** `backend/app/routers/admin.py`

**Endpoint:** `POST /api/admin/internal/workers/transactions/run-once`

**Authentication:** `INTERNAL_API_KEY` (from environment variable)

**Request Body:**
```json
{
  "internal_api_key": "...",
  "account_id": "optional-uuid"  // If provided, runs for single account; otherwise all accounts
}
```

**Response:**
```json
{
  "status": "ok",
  "correlation_id": "...",
  "started_at": "2025-12-04T...",
  "triggered_by": "internal_scheduler",
  "accounts_processed": 2,
  "accounts_succeeded": 2,
  "accounts_failed": 0,
  "accounts_skipped": 0,
  "details": [...]
}
```

### 5. Railway Worker Proxy Functions

**Location:** `backend/app/workers/ebay_workers_loop.py`

**Functions:**
- `run_transactions_worker_proxy_once()` - Single proxy call
- `run_transactions_worker_proxy_loop()` - Loop that calls proxy every 5 minutes
- `run_ebay_workers_proxy_loop()` - Proxy loop for all workers

**Usage:**
```python
# In Railway worker service, use:
asyncio.run(run_transactions_worker_proxy_loop())
# OR for all workers:
asyncio.run(run_ebay_workers_proxy_loop())
```

---

## Logging Structure

### Example Log Entry for Manual Run

```
[fetch_transactions] mode=manual correlation_id=worker_transactions_abc123 account_id=uuid-123 ebay_user_id=testuser_123 target_env=sandbox base_url=https://apiz.sandbox.ebay.com api_url=https://apiz.sandbox.ebay.com/sell/finances/v1/transaction token_hash=a1b2c3d4e5f6g7h8
```

### Example Log Entry for Automatic Run

```
[fetch_transactions] mode=automatic correlation_id=worker_transactions_def456 account_id=uuid-123 ebay_user_id=testuser_123 target_env=sandbox base_url=https://apiz.sandbox.ebay.com api_url=https://apiz.sandbox.ebay.com/sell/finances/v1/transaction token_hash=a1b2c3d4e5f6g7h8
```

### Structured Event Log (via ebay_logger)

```json
{
  "event_type": "fetch_transactions_request",
  "description": "Fetching transactions from eBay (sandbox)",
  "request_data": {
    "environment": "sandbox",
    "api_url": "https://apiz.sandbox.ebay.com/sell/finances/v1/transaction",
    "method": "GET",
    "headers": {
      "Authorization": "Bearer ***REDACTED*** (hash=a1b2c3d4e5f6g7h8)",
      "Accept": "application/json",
      "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"
    },
    "params": {
      "filter": "transactionDate:[2025-12-01T00:00:00.000Z..2025-12-04T12:00:00.000Z]",
      "limit": 200,
      "offset": 0
    },
    "mode": "manual",
    "correlation_id": "worker_transactions_abc123",
    "account_id": "uuid-123",
    "ebay_user_id": "testuser_123"
  },
  "response_data": {
    "status_code": 200,
    "total_transactions": 42,
    "mode": "manual",
    "correlation_id": "worker_transactions_abc123",
    "account_id": "uuid-123"
  },
  "status": "success"
}
```

---

## Debugging 401 Errors

### Step 1: Check Logs for Mode and Correlation ID

Search logs for:
```
[fetch_transactions] mode=automatic correlation_id=...
```

This tells you:
- Whether it's manual or automatic
- The correlation_id to track the full sync batch

### Step 2: Check Token Hash

Look for:
```
token_hash=a1b2c3d4e5f6g7h8
```

Compare token hashes between successful manual runs and failing automatic runs. If different, the automatic run is using a different token.

### Step 3: Check Token Provider Logs

Search for:
```
[token_provider] Token retrieved successfully: account_id=... source=... token_hash=...
```

This shows:
- Which token was retrieved
- Whether it was refreshed or used existing
- The token hash for comparison

### Step 4: Check Internal Endpoint Logs

If using proxy mode, check:
```
[transactions_proxy] Triggering transactions sync via ...
[internal_transactions] Running for all accounts...
```

### Step 5: Verify Environment Variables

Ensure Railway worker service has:
- `WEB_APP_URL` - URL of the main web app
- `INTERNAL_API_KEY` - Shared secret for internal endpoints

### Step 6: Check Response Logs

On 401 error, logs will show:
```json
{
  "event_type": "fetch_transactions_failed",
  "response_data": {
    "status_code": 401,
    "error": "...",
    "mode": "automatic",
    "correlation_id": "...",
    "account_id": "..."
  }
}
```

---

## Configuration Checklist

### Main Web App (ebay-connector-app service)

- ✅ Has `INTERNAL_API_KEY` environment variable
- ✅ Internal endpoint `/api/admin/internal/workers/transactions/run-once` is accessible
- ✅ Token decryption keys are configured
- ✅ Database access for token retrieval

### Railway Worker Service (if separate)

- ✅ Has `WEB_APP_URL` environment variable (points to main app)
- ✅ Has `INTERNAL_API_KEY` environment variable (same as main app)
- ✅ Uses `run_transactions_worker_proxy_loop()` or `run_ebay_workers_proxy_loop()`
- ❌ **DO NOT** use `run_ebay_workers_loop()` directly (may have token decryption issues)

### Main App Background Loop (if running in main app)

- ✅ Uses `run_ebay_workers_loop()` (runs in same process, has access to all keys)
- ✅ Calls `run_ebay_workers_once()` which uses same code path as manual Run Now

---

## Testing

### Manual Run Now Test

1. Go to Admin → eBay Workers
2. Select an account
3. Click "Run now" for Transactions worker
4. Check logs for:
   - `mode=manual`
   - Successful API calls
   - Token hash logged

### Automatic Run Test (Main App Loop)

1. Wait for next 5-minute cycle (or trigger manually if possible)
2. Check logs for:
   - `mode=automatic` (if triggered_by="internal_scheduler")
   - Or `mode=manual` (if triggered_by="manual" in loop)
   - Successful API calls
   - Same token hash as manual runs

### Automatic Run Test (Railway Proxy)

1. Ensure Railway worker service is running `run_transactions_worker_proxy_loop()`
2. Check logs for:
   - `[transactions_proxy] Triggering transactions sync via ...`
   - `[internal_transactions] Running for all accounts...`
   - `mode=automatic` in fetch_transactions logs
   - Successful API calls

---

## Migration Guide

### If Railway Worker is Currently Using Direct Calls

1. Update Railway worker service to use proxy mode:
   ```python
   # OLD (may have token issues):
   asyncio.run(run_ebay_workers_loop())
   
   # NEW (uses internal endpoint):
   asyncio.run(run_transactions_worker_proxy_loop())
   # OR for all workers:
   asyncio.run(run_ebay_workers_proxy_loop())
   ```

2. Ensure environment variables are set:
   - `WEB_APP_URL=https://your-app.railway.app`
   - `INTERNAL_API_KEY=your-shared-secret`

3. Verify internal endpoint is accessible:
   ```bash
   curl -X POST https://your-app.railway.app/api/admin/internal/workers/transactions/run-once \
     -H "Content-Type: application/json" \
     -d '{"internal_api_key": "your-shared-secret"}'
   ```

---

## Summary

✅ **Unified Code Path:** Both manual and automatic runs use the same `run_transactions_worker_for_account()` function

✅ **Enhanced Logging:** All eBay API calls log mode, correlation_id, account_id, token_hash

✅ **Internal Endpoint:** Already exists and properly configured

✅ **Proxy Mode:** Railway worker should use proxy mode to avoid token decryption issues

✅ **Token Provider:** Single source of truth for all token retrieval

**Next Steps:**
1. Verify Railway worker service is using proxy mode
2. Monitor logs for 401 errors
3. Compare token hashes between manual and automatic runs
4. If 401s persist, check token refresh logic and environment configuration

---

## Files Modified

1. `backend/app/services/ebay.py`
   - Enhanced `fetch_transactions()` with mode, correlation_id, account_id logging
   - Updated `sync_all_transactions()` to accept and pass through these parameters

2. `backend/app/services/ebay_workers/transactions_worker.py`
   - Updated `execute_sync()` to determine mode from `triggered_by` and pass to `sync_all_transactions()`

3. `backend/app/workers/ebay_workers_loop.py`
   - Added documentation comment about proxy mode usage

4. `docs/worker-transactions-audit-20251204.md` (this file)
   - Comprehensive audit documentation

---

## Related Documentation

- `docs/EBAY_WORKERS_OVERVIEW.md` - General workers architecture
- `docs/EBAY_WORKERS_LOOP_STATUS.md` - Worker loop status and configuration
- `docs/worker-token-endpoint-20251204.md` - Token refresh endpoint pattern
- `docs/EBAY_TOKEN_REFRESH_LOGIC.md` - Token refresh logic

