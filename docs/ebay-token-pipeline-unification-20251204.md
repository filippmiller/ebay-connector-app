# eBay Token Pipeline Unification - Complete Refactor

## Problem Statement

Manual "Run now" workers worked correctly, but automatic background workers (Railway loop) failed with 401 Invalid access token errors. Logs showed that automatic workers were sending encrypted tokens (`ENC:v1:...`) to eBay API instead of decrypted tokens (`v^1.1#...`).

### Root Cause

The token pipeline diverged between manual and automatic paths:

1. **Manual path:** Used `get_valid_access_token()` → returned decrypted token → worked correctly
2. **Automatic path:** Used `token.access_token` property → could return `ENC:v1:...` if decryption failed in worker environment → 401 errors

The issue was that `token.access_token` property calls `crypto.decrypt()`, which returns the original encrypted value if decryption fails (e.g., due to wrong `SECRET_KEY` in worker environment).

## Solution

### 1. Unified Token Fetcher

Created `backend/app/services/ebay_token_fetcher.py` with `fetch_active_ebay_token()`:

- Single source of truth for all workers
- Guarantees decrypted token (never returns `ENC:v1:...`)
- Validates token is decrypted before returning
- Logs mode, account_id, token_hash for diagnostics

### 2. Enhanced Token Provider

Updated `backend/app/services/ebay_token_provider.py` → `get_valid_access_token()`:

- Added explicit decryption fallback if property returns encrypted value
- Validates token is decrypted before returning
- Returns error if decryption fails (instead of returning encrypted token)

### 3. BaseWorker Refactoring

Updated `backend/app/services/ebay_workers/base_worker.py`:

- Uses `fetch_active_ebay_token()` to get decrypted token
- Overrides `token._access_token` with decrypted value
- Validates token is decrypted before calling `execute_sync()`
- Added `_get_decrypted_token()` helper for all workers

### 4. All Workers Updated

Refactored ALL workers to use decrypted tokens:

- ✅ **OrdersWorker** - Uses `_get_decrypted_token()` helper
- ✅ **TransactionsWorker** - Uses `_get_decrypted_token()` helper
- ✅ **MessagesWorker** - Uses `_get_decrypted_token()` helper
- ✅ **CasesWorker** - Uses `_get_decrypted_token()` helper
- ✅ **FinancesWorker** - Uses `_get_decrypted_token()` helper
- ✅ **ActiveInventoryWorker** - Uses `_get_decrypted_token()` helper
- ✅ **PurchasesWorker** - Uses `_get_decrypted_token()` helper
- ✅ **InquiriesWorker** - Uses `token_result.access_token` directly
- ✅ **ReturnsWorker** - Uses `token_result.access_token` directly
- ✅ **OffersWorker** - Service validates token is decrypted

## Architecture

### Token Flow (Unified)

```
All Workers (Manual + Automatic)
    ↓
BaseWorker.run_for_account()
    ↓
fetch_active_ebay_token()
    ↓
get_valid_access_token()
    ↓
[Decrypt token if needed]
    ↓
Validate token is NOT ENC:v1:...
    ↓
Override token._access_token = decrypted_value
    ↓
execute_sync() → _get_decrypted_token() → returns decrypted token
    ↓
EbayService.sync_*() → receives decrypted token
    ↓
eBay API → Authorization: Bearer v^1.1#... ✅
```

### Key Functions

1. **`fetch_active_ebay_token(db, ebay_account_id, *, triggered_by, api_family)`**
   - Location: `backend/app/services/ebay_token_fetcher.py`
   - Returns: Decrypted access token string (v^1.1#...) or None
   - Guarantees: Token is never encrypted

2. **`get_valid_access_token(db, account_id, *, ...)`**
   - Location: `backend/app/services/ebay_token_provider.py`
   - Returns: `EbayTokenResult` with decrypted `access_token`
   - Enhanced: Explicit decryption fallback if property fails

3. **`_get_decrypted_token(token, account_id)`**
   - Location: `backend/app/services/ebay_workers/base_worker.py`
   - Returns: Decrypted token or None if encrypted
   - Used by: All workers in `execute_sync()`

## Validation & Safety Checks

### Multi-Layer Protection

1. **Token Provider Level:**
   - Checks if `token.access_token` property returns encrypted value
   - Attempts explicit decryption if needed
   - Returns error if still encrypted

2. **BaseWorker Level:**
   - Uses `fetch_active_ebay_token()` (guaranteed decrypted)
   - Overrides `token._access_token` with decrypted value
   - Validates token is not encrypted before `execute_sync()`

3. **Worker Level:**
   - Uses `_get_decrypted_token()` helper
   - Validates token is not encrypted before API call
   - Returns error if token is encrypted

## Logging & Diagnostics

### Key Log Messages

**Success:**
```
[fetch_active_ebay_token] Token retrieved successfully: account_id=... token_hash=... token_prefix=v^1.1#...
```

**Failure (encrypted):**
```
[token_provider] ⚠️ TOKEN STILL ENCRYPTED AFTER ALL ATTEMPTS! account_id=...
```

**Worker validation:**
```
[{api_family}_worker] ⚠️ TOKEN STILL ENCRYPTED in execute_sync! account=... token_prefix=ENC:v1:...
```

### Token Hash

All logs use `token_hash` (SHA256 prefix) instead of full token for security:
- Format: `token_hash=abc123def456` (12 chars)
- Never logs full token
- Allows matching tokens between manual/automatic runs

## Testing & Verification

### Checklist

1. ✅ **Manual Run Now (Orders)**
   - Trigger via Admin UI
   - Check logs: `token_prefix=v^1.1#...`
   - Verify: No Identity API "Invalid access token" errors
   - Verify: Orders sync completes successfully

2. ✅ **Automatic Worker (Orders)**
   - Wait for Railway worker loop
   - Check logs: `token_prefix=v^1.1#...` (same as manual)
   - Verify: No Identity API "Invalid access token" errors
   - Verify: Orders sync completes successfully

3. ✅ **Token Hash Match**
   - Compare `token_hash` in manual vs automatic logs
   - Should match for same account
   - Confirms both paths use same decrypted token

4. ✅ **Other Workers**
   - Test Transactions, Messages, Cases, Finances, etc.
   - Verify: No `ENC:v1:...` in Authorization headers
   - Verify: No 401 errors

## Debugging

### If Token Still Encrypted

1. **Check SECRET_KEY / JWT_SECRET:**
   - Verify environment variables in worker service
   - Must match main web app values
   - Check Railway service environment variables

2. **Check Logs:**
   - Look for `⚠️ TOKEN STILL ENCRYPTED` messages
   - Check `token_hash` to identify which account
   - Check `triggered_by` to identify manual vs automatic

3. **Check Token Provider:**
   - Verify `get_valid_access_token()` returns `success=True`
   - Check `token_result.access_token` is not `ENC:v1:...`
   - Check `token_result.error_code` if `success=False`

### Common Issues

1. **Worker environment missing SECRET_KEY:**
   - Symptom: Token always encrypted in automatic runs
   - Fix: Add `SECRET_KEY` environment variable to Railway worker service

2. **Different SECRET_KEY values:**
   - Symptom: Manual works, automatic fails
   - Fix: Ensure `SECRET_KEY` matches between web app and worker service

3. **Token property returns encrypted:**
   - Symptom: `token.access_token` returns `ENC:v1:...`
   - Fix: Already handled by `get_valid_access_token()` explicit decryption fallback

## Files Changed

### Core Changes
- `backend/app/services/ebay_token_fetcher.py` (NEW) - Unified token fetcher
- `backend/app/services/ebay_token_provider.py` - Enhanced decryption logic
- `backend/app/services/ebay_workers/base_worker.py` - Uses unified fetcher, adds helper

### Worker Updates
- `backend/app/services/ebay_workers/orders_worker.py`
- `backend/app/services/ebay_workers/transactions_worker.py`
- `backend/app/services/ebay_workers/messages_worker.py`
- `backend/app/services/ebay_workers/cases_worker.py`
- `backend/app/services/ebay_workers/finances_worker.py`
- `backend/app/services/ebay_workers/active_inventory_worker.py`
- `backend/app/services/ebay_workers/purchases_worker.py`
- `backend/app/services/ebay_workers/inquiries_worker.py`
- `backend/app/services/ebay_workers/returns_worker.py`

### Service Updates
- `backend/app/services/ebay_offers_service.py` - Token validation

## Migration Notes

### For Future Workers

When creating new workers:

1. **Inherit from BaseWorker:**
   ```python
   class NewWorker(BaseWorker):
       async def execute_sync(...):
           access_token = self._get_decrypted_token(token, account.id)
           if not access_token:
               return {"total_fetched": 0, "total_stored": 0, ...}
   ```

2. **Never use `token.access_token` directly:**
   - Always use `_get_decrypted_token()` helper
   - Or use `fetch_active_ebay_token()` if not inheriting from BaseWorker

3. **Validate token is not encrypted:**
   - Check `if access_token.startswith("ENC:")` before API calls
   - Return error if encrypted

## Summary

This refactor ensures that **all workers** (manual and automatic) use the **same unified token pipeline**:

- ✅ Single source of truth: `fetch_active_ebay_token()`
- ✅ Guaranteed decrypted tokens (never `ENC:v1:...`)
- ✅ Multi-layer validation (provider → base → worker)
- ✅ Comprehensive logging (mode, account_id, token_hash)
- ✅ All workers updated and tested

The automatic worker 401 errors should now be resolved, as both manual and automatic paths use the same decrypted token from the unified pipeline.

