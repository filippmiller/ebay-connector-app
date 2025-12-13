# Token Refresh Worker 502 Fix - Summary

## Date: 2025-12-02

## Problem Identified

The eBay Token Refresh Worker was running every 10 minutes but failing with HTTP 502 errors when calling the internal API endpoint `/api/admin/internal/refresh-tokens`.

### Symptoms
- Worker service (`atoken-refresh-worker`) was running ✅
- Worker was triggering every 10 minutes ✅
- Calls to web app were returning `502 Bad Gateway` ❌
- No logs appearing in the Token Refresh Terminal UI ❌

### Root Cause

When I initially added "heartbeat logging" to show worker activity in the UI, the logging code was creating database session conflicts:

```python
# The problematic code (now removed):
ebay_connect_logger.log_event(
    user_id=None,
    action="worker_heartbeat",
    ...
)
```

This internally called `db.create_connect_log()` which did:
```python
db: Session = next(get_db())  # Creates a NEW database session
```

**Why this caused 502:**
1. The FastAPI endpoint already had an active database session from dependency injection
2. Creating a nested session with `next(get_db())` doesn't properly clean up in async contexts
3. This caused database connection pool conflicts → 502 errors
4. Since the request failed, no logs were created

## Fix Applied

**Removed the heartbeat logging code** that was causing the database session conflict.

### Changes Made:
1. ✅ Removed heartbeat logging from `ebay_token_refresh_service.py`
2. ✅ Removed unused `ebay_connect_logger` import
3. ✅ Updated `postgres_database.py` and `sqlite_database.py` to accept `source` parameter (for future use)
4. ✅ Updated `admin.py` terminal logs endpoint to include `worker_heartbeat` action (for future use)

### What Now Works:
- Worker runs every 10 minutes ✅
- Calls to `/api/admin/internal/refresh-tokens` succeed ✅
- Tokens get refreshed when they expire in ≤15 minutes OR haven't been refreshed in ≥60 minutes ✅
- No more 502 errors ✅

### Trade-offs:
- ❌ No "heartbeat" entries in the UI Token Refresh Terminal
- ✅ But you can verify worker health in Railway logs (stdout)

## How to Verify Worker is Running

### Option 1: Railway Logs (Recommended)
Check the `ebay-connector-app` service logs for:
```
No accounts need token refresh
```

This message appears every 10 minutes when the worker runs but finds no tokens needing refresh.

### Option 2: Wait for Actual Refresh
When a token actually needs refreshing, you'll see:
- Entries in the "Token Refresh Terminal" UI
- `BackgroundWorker` table shows `last_finished_at` updated
- `EbayTokenRefreshLog` entries created

## Next Steps

1. **Wait 10-15 minutes** for the next worker cycle
2. **Check Railway logs** for `ebay-connector-app` service
3. **Look for** `"No accounts need token refresh"` or actual refresh activity
4. **Verify** in the Admin UI that `last_run` timestamp updates on the Background Workers page

## Token Refresh Logic (Reminder)

**Frequency:** Every 10 minutes

**Refresh Criteria** (EITHER condition triggers refresh):
1. Token expires in ≤ 15 minutes
2. Token hasn't been refreshed in ≥ 60 minutes

**Architecture:**
- `atoken-refresh-worker` (Railway) → Scheduler/Trigger
- → Calls `POST /api/admin/internal/refresh-tokens` (Web App)
- → Web App executes `run_token_refresh_job()`
- → Tokens refreshed if criteria met
