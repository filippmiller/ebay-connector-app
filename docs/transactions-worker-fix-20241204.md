# Transactions Worker Fix — 2024-12-04

## Summary

Fixed 401 Unauthorized errors in the Transactions worker (and potentially other REST workers) that occurred during background scheduler runs but not during manual "Run now" triggers.

**Root Cause:** Token refresh service was using global `settings.EBAY_ENVIRONMENT` instead of the user-specific `User.ebay_environment`. This caused production eBay accounts to receive sandbox tokens (or vice versa), resulting in 401 errors when the worker tried to call the Finances API.

## Root Cause Analysis

### The Problem

```
┌────────────────────────────────────────────────────────────────────┐
│                    BEFORE FIX                                      │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  User connected to: PRODUCTION eBay                                │
│  User.ebay_environment: "production"                               │
│  settings.EBAY_ENVIRONMENT: "sandbox" (default)                    │
│                                                                    │
│  Background scheduler starts:                                      │
│  1. run_token_refresh_job()                                        │
│     └── Uses settings.EBAY_ENVIRONMENT = "sandbox" ❌              │
│     └── Refreshes token against sandbox.ebay.com                   │
│     └── Gets SANDBOX token (invalid for production!)               │
│                                                                    │
│  2. transactions_worker.execute_sync()                             │
│     └── Correctly uses User.ebay_environment = "production"        │
│     └── Calls apiz.ebay.com with SANDBOX token                     │
│     └── 401 Unauthorized! ❌                                       │
│                                                                    │
│  Manual "Run now" works because:                                   │
│  - Token might still be valid from a previous correct refresh      │
│  - Or environment happened to match                                │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

### The Fix

```
┌────────────────────────────────────────────────────────────────────┐
│                    AFTER FIX                                       │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  Background scheduler starts:                                      │
│  1. run_token_refresh_job()                                        │
│     └── Fetches User from DB via account.org_id                    │
│     └── Uses User.ebay_environment = "production" ✓                │
│     └── Refreshes token against api.ebay.com                       │
│     └── Gets PRODUCTION token (correct!)                           │
│                                                                    │
│  2. transactions_worker.execute_sync()                             │
│     └── Uses User.ebay_environment = "production" ✓                │
│     └── Calls apiz.ebay.com with PRODUCTION token                  │
│     └── Success! ✓                                                 │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

## Code Changes

### 1. `backend/app/services/ebay_token_refresh_service.py`

**Location:** `refresh_access_token_for_account()` function, after token decryption validation

**Before:**
```python
env = settings.EBAY_ENVIRONMENT or "sandbox"
```

**After:**
```python
# FIX: Get environment from the user who owns this account, not from
# global settings. This ensures production accounts refresh against
# production eBay API even if settings.EBAY_ENVIRONMENT defaults to sandbox.
from app.models_sqlalchemy.models import User
user = db.query(User).filter(User.id == account.org_id).first()
env = user.ebay_environment if user and user.ebay_environment else settings.EBAY_ENVIRONMENT or "sandbox"

logger.info(
    "[token_refresh] account=%s org_id=%s user_env=%s resolved_env=%s global_env=%s",
    account.id,
    account.org_id,
    user.ebay_environment if user else "<no_user>",
    env,
    settings.EBAY_ENVIRONMENT,
)
```

### 2. `backend/app/services/ebay.py` (Logging fix)

**Location:** `fetch_transactions()` method

**Before:**
```python
ebay_logger.log_ebay_event(
    "fetch_transactions_request",
    f"Fetching transactions from eBay ({settings.EBAY_ENVIRONMENT})",  # ← Wrong!
    request_data={
        "environment": settings.EBAY_ENVIRONMENT,  # ← Wrong!
        ...
    }
)
```

**After:**
```python
ebay_logger.log_ebay_event(
    "fetch_transactions_request",
    f"Fetching transactions from eBay ({target_env})",  # ← Correct!
    request_data={
        "environment": target_env,  # ← Correct!
        ...
    }
)
```

### 3. `backend/app/services/ebay_workers/transactions_worker.py` (Diagnostic logging)

Added optional diagnostic logging controlled by `EBAY_DEBUG_TRANSACTIONS=1` environment variable to capture environment resolution at runtime.

## Verification Steps

### 1. Check logs after next scheduler run

Look for the new log line:
```
[token_refresh] account=XXX org_id=YYY user_env=production resolved_env=production global_env=sandbox
```

Confirm `resolved_env` matches `user_env`, not `global_env`.

### 2. Check ebay_worker_run table

```sql
SELECT id, api_family, status, started_at, summary_json->'error_message' as error
FROM ebay_worker_run
WHERE api_family = 'transactions'
ORDER BY started_at DESC
LIMIT 10;
```

After the fix, `status` should be `completed` without 401 errors.

### 3. Check ebay_sync_state table

```sql
SELECT ebay_account_id, api_family, cursor_value, last_run_at, last_error
FROM ebay_sync_state
WHERE api_family = 'transactions';
```

- `cursor_value` should be recent (close to now)
- `last_error` should be NULL or not contain "401"

### 4. Run diagnostic script locally

```bash
cd backend
python scripts/check_transactions_worker_state.py
```

### 5. Run one-shot worker test

```bash
cd backend
EBAY_DEBUG_TRANSACTIONS=1 python scripts/run_transactions_worker_once.py
```

## Reusable Pattern for Other Workers

### Problem Detection Checklist

For any worker showing 401 errors in background but working manually:

1. **Check token refresh environment resolution**
   - Does the refresh service use account/user-specific environment?
   - Is `settings.EBAY_ENVIRONMENT` being used where it shouldn't be?

2. **Check worker's environment handling**
   - Does the worker fetch `User.ebay_environment`?
   - Is it passed correctly to the service layer?

3. **Check service layer logging**
   - Are logs showing the correct environment, or the global setting?
   - Fix any misleading logs.

### Fix Pattern

```python
# In any service that needs environment:
# DON'T do this:
env = settings.EBAY_ENVIRONMENT

# DO this:
from app.models_sqlalchemy.models import User
user = db.query(User).filter(User.id == account.org_id).first()
env = user.ebay_environment if user and user.ebay_environment else settings.EBAY_ENVIRONMENT or "sandbox"
```

## Files Changed

| File | Change Type | Description |
|------|-------------|-------------|
| `backend/app/services/ebay_token_refresh_service.py` | **FIX** | Use User.ebay_environment for token refresh |
| `backend/app/services/ebay.py` | **FIX** | Correct logging to show actual environment |
| `backend/app/services/ebay_workers/transactions_worker.py` | **DIAG** | Add optional diagnostic logging |
| `backend/scripts/check_transactions_worker_state.py` | **NEW** | Diagnostic script for DB state |
| `backend/scripts/run_transactions_worker_once.py` | **NEW** | One-shot worker test script |
| `docs/transactions-worker-fix-20241204.md` | **NEW** | This documentation |

## Impact

- **Transactions worker:** Should now work correctly in background scheduler
- **Other workers:** May also benefit if they use token refresh (to be verified)
- **Token refresh logs:** Will now show correct environment being used
- **Backward compatibility:** Maintained - falls back to global setting if user not found

## Next Steps

1. Deploy to production
2. Monitor next 2-3 scheduler cycles (10-15 minutes)
3. Verify transactions worker shows `status=completed`
4. Apply same pattern to Orders and Offers workers if needed









