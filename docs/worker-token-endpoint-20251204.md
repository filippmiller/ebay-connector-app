# Unified eBay Token Provider & Internal Endpoint for Workers

**Date:** December 4, 2025  
**Type:** Architecture improvement  
**Repository:** `C:\dev\ebay-connector-app`

---

## 1. Problem Summary

### Original Issue
Background scheduler runs for eBay workers (especially Transactions) were failing with 401 "Invalid access token" errors, while manual "Run now" triggers from the Admin UI succeeded.

**Observed pattern:**
- Manual run at ~10:54 → 200 OK, narrow time window
- Scheduler run at ~11:00 → 401 Invalid access token, 90-day window

### Root Cause Analysis

After investigating the code flows, we identified several contributing factors:

1. **Token refresh timing mismatch:**
   - Background scheduler runs `run_token_refresh_job()` BEFORE workers
   - Token refresh only refreshes tokens expiring within 15 minutes
   - If refresh fails or produces a bad token, workers use that bad token
   
2. **Different code paths for token retrieval:**
   - Manual runs called workers directly, using whatever token was in DB
   - Scheduler runs went through refresh → then workers
   - No unified validation at point of use

3. **Environment mismatch (previously fixed):**
   - Token refresh was using `settings.EBAY_ENVIRONMENT` instead of `User.ebay_environment`
   - This was fixed in the previous iteration (see `transactions-worker-fix-20241204.md`)

4. **No token hash logging:**
   - Impossible to determine which exact token was being used in each path
   - Made debugging very difficult

---

## 2. Solution: Unified EbayTokenProvider

### Design Goals

1. **Single code path** for all token retrieval (manual, scheduler, external workers)
2. **Automatic refresh** when token is near expiry
3. **Optional validation** via eBay Identity API
4. **Clear error states** that can be logged and surfaced
5. **Token fingerprinting** for debugging (SHA256 hash, never raw token)

### New Components

#### 2.1 EbayTokenProvider (`backend/app/services/ebay_token_provider.py`)

Main entry point: `get_valid_access_token()`

```python
async def get_valid_access_token(
    db: Session,
    account_id: str,
    *,
    api_family: Optional[str] = None,
    force_refresh: bool = False,
    validate_with_identity_api: bool = False,
    triggered_by: str = "worker",
) -> EbayTokenResult
```

**Returns:** `EbayTokenResult` dataclass with:
- `success: bool`
- `access_token: Optional[str]` (only on success)
- `environment: str` ("production" or "sandbox")
- `expires_at: datetime`
- `source: Literal["existing", "refreshed", "none"]`
- `token_hash: str` (SHA256 prefix for debugging)
- `token_db_id: str`
- `account_id: str`
- `ebay_user_id: str`
- `error_code: Optional[str]` (only on failure)
- `error_message: Optional[str]` (only on failure)

**Behavior:**
1. Loads account from DB, validates it's active
2. Determines environment from `User.ebay_environment`
3. Gets current token from DB
4. Checks if token is near expiry (< 10 minutes by default)
5. If near expiry or `force_refresh=True`, calls `refresh_access_token_for_account()`
6. Optionally validates via Identity API
7. Returns structured result with token hash for debugging

#### 2.2 Internal HTTP Endpoint (`backend/app/routers/admin.py`)

```
POST /api/admin/internal/ebay/accounts/{account_id}/access-token
```

**Authentication:** `INTERNAL_API_KEY` header

**Request body:**
```json
{
  "internal_api_key": "...",
  "api_family": "transactions",  // optional, for logging
  "force_refresh": false,
  "validate_with_identity_api": false
}
```

**Response (success):**
```json
{
  "success": true,
  "access_token": "v^1.1#...",
  "environment": "production",
  "expires_at": "2025-12-04T12:00:00Z",
  "source": "existing",
  "token_hash": "a1b2c3d4e5f6",
  "token_db_id": "uuid-...",
  "account_id": "uuid-...",
  "ebay_user_id": "testuser",
  "api_family": "transactions"
}
```

**Response (failure):**
```json
{
  "success": false,
  "error_code": "refresh_failed",
  "error_message": "Token refresh failed: invalid_grant",
  "account_id": "uuid-...",
  "ebay_user_id": "testuser",
  "environment": "production"
}
```

---

## 3. Worker Refactoring

### BaseWorker Changes

All workers using `BaseWorker` now:

1. Accept `triggered_by` parameter (`"manual"`, `"scheduler"`, or `"unknown"`)
2. Call `get_valid_access_token()` from the token provider
3. Log token hash with each run for debugging

**Updated signature:**
```python
async def run_for_account(
    self,
    ebay_account_id: str,
    triggered_by: Literal["manual", "scheduler", "unknown"] = "unknown",
) -> Optional[str]
```

**Token retrieval in BaseWorker:**
```python
from app.services.ebay_token_provider import get_valid_access_token

token_result = await get_valid_access_token(
    db,
    ebay_account_id,
    api_family=self.api_family,
    force_refresh=False,
    validate_with_identity_api=False,
    triggered_by=f"worker_{triggered_by}",
)

if not token_result.success:
    logger.warning(f"{self.api_family} worker: token retrieval failed...")
    return None

logger.info(
    f"[{self.api_family}_worker] Token retrieved: account={ebay_account_id} "
    f"source={token_result.source} token_hash={token_result.token_hash} "
    f"environment={token_result.environment} triggered_by={triggered_by}"
)
```

### Updated Workers

All 10 workers now use the unified token provider:

| Worker | File | Uses BaseWorker |
|--------|------|-----------------|
| Orders | `orders_worker.py` | ✅ Yes |
| Transactions | `transactions_worker.py` | ✅ Yes |
| Offers | `offers_worker.py` | ✅ Yes |
| Messages | `messages_worker.py` | ✅ Yes |
| Active Inventory | `active_inventory_worker.py` | ✅ Yes |
| Buyer | `purchases_worker.py` | ✅ Yes |
| Cases | `cases_worker.py` | ✅ Yes |
| Finances | `finances_worker.py` | ✅ Yes |
| Inquiries | `inquiries_worker.py` | ❌ Manual (updated) |
| Returns | `returns_worker.py` | ❌ Manual (updated) |

### Scheduler Changes

The scheduler now passes `triggered_by="scheduler"` to all workers:

```python
# scheduler.py
triggered_by = "scheduler"

_add_if_enabled("orders", lambda aid: run_orders_worker_for_account(aid, triggered_by=triggered_by))
_add_if_enabled("transactions", lambda aid: run_transactions_worker_for_account(aid, triggered_by=triggered_by))
# ... etc
```

### Manual Run Changes

The manual run endpoint (`POST /ebay/workers/run`) now passes `triggered_by="manual"`:

```python
# ebay_workers.py router
if api == "transactions":
    run_id = await run_transactions_worker_for_account(account_id, triggered_by="manual")
```

---

## 4. Verification

### Expected Log Output

After deployment, logs should show token retrieval for every worker run:

```
[token_provider] Token retrieved successfully: account=uuid-123 environment=production 
    source=existing token_hash=a1b2c3d4 expires_at=2025-12-04T12:00:00Z 
    triggered_by=worker_scheduler api_family=transactions

[transactions_worker] Token retrieved: account=uuid-123 source=existing 
    token_hash=a1b2c3d4 environment=production triggered_by=scheduler
```

### Verification Steps

1. **Check logs after scheduler run:**
   - Look for `[token_provider]` logs
   - Verify `source=existing` or `source=refreshed`
   - Compare `token_hash` between manual and scheduler runs

2. **Run manual "Run now" for Transactions:**
   - Should show `triggered_by=manual`
   - Should succeed with 200 OK

3. **Wait for scheduler run:**
   - Should show `triggered_by=scheduler`
   - Should succeed with 200 OK
   - Token hash should match (if same token) or show `source=refreshed`

4. **Check DB:**
   ```sql
   SELECT id, api_family, status, started_at, summary_json
   FROM ebay_worker_run
   WHERE api_family = 'transactions'
   ORDER BY started_at DESC
   LIMIT 10;
   ```
   - Both manual and scheduler runs should show `status='completed'`

---

## 5. Pattern for Migrating Other Workers

### Step-by-step for any worker:

1. **Add `triggered_by` parameter:**
   ```python
   async def run_my_worker_for_account(
       ebay_account_id: str,
       triggered_by: str = "unknown",
   ) -> Optional[str]:
   ```

2. **Replace direct token fetch with provider:**
   ```python
   # OLD:
   token = ebay_account_service.get_token(db, ebay_account_id)
   if not token or not token.access_token:
       return None
   
   # NEW:
   from app.services.ebay_token_provider import get_valid_access_token
   
   token_result = await get_valid_access_token(
       db,
       ebay_account_id,
       api_family="my_family",
       triggered_by=f"worker_{triggered_by}",
   )
   
   if not token_result.success:
       logger.warning(f"Token retrieval failed: {token_result.error_message}")
       return None
   
   # Still get the ORM object if needed for execute_sync signature
   token = ebay_account_service.get_token(db, ebay_account_id)
   ```

3. **Add token hash logging:**
   ```python
   logger.info(
       f"[my_worker] Token retrieved: account={ebay_account_id} "
       f"source={token_result.source} token_hash={token_result.token_hash}"
   )
   ```

4. **Update scheduler call:**
   ```python
   _add_if_enabled("my_family", lambda aid: run_my_worker_for_account(aid, triggered_by="scheduler"))
   ```

5. **Update manual run endpoint:**
   ```python
   run_id = await run_my_worker_for_account(account_id, triggered_by="manual")
   ```

---

## 6. Files Changed

| File | Change Type | Description |
|------|-------------|-------------|
| `backend/app/services/ebay_token_provider.py` | **NEW** | Unified token provider |
| `backend/app/routers/admin.py` | **UPDATED** | Added internal token endpoint |
| `backend/app/services/ebay_workers/base_worker.py` | **UPDATED** | Use token provider, add triggered_by |
| `backend/app/services/ebay_workers/scheduler.py` | **UPDATED** | Pass triggered_by=scheduler |
| `backend/app/services/ebay_workers/orders_worker.py` | **UPDATED** | Add triggered_by param |
| `backend/app/services/ebay_workers/transactions_worker.py` | **UPDATED** | Add triggered_by param |
| `backend/app/services/ebay_workers/offers_worker.py` | **UPDATED** | Add triggered_by param |
| `backend/app/services/ebay_workers/messages_worker.py` | **UPDATED** | Add triggered_by param |
| `backend/app/services/ebay_workers/active_inventory_worker.py` | **UPDATED** | Add triggered_by param |
| `backend/app/services/ebay_workers/purchases_worker.py` | **UPDATED** | Add triggered_by param |
| `backend/app/services/ebay_workers/cases_worker.py` | **UPDATED** | Add triggered_by param |
| `backend/app/services/ebay_workers/finances_worker.py` | **UPDATED** | Add triggered_by param |
| `backend/app/services/ebay_workers/inquiries_worker.py` | **UPDATED** | Add triggered_by, use token provider |
| `backend/app/services/ebay_workers/returns_worker.py` | **UPDATED** | Add triggered_by, use token provider |
| `backend/app/routers/ebay_workers.py` | **UPDATED** | Pass triggered_by=manual |
| `docs/worker-token-endpoint-20251204.md` | **NEW** | This documentation |

---

## 7. Security Notes

1. **No raw tokens in logs:** Only SHA256 hash prefix is logged
2. **Internal endpoint protected:** Requires `INTERNAL_API_KEY`
3. **Token never in API response logs:** Only metadata is returned in logs
4. **Environment isolation:** Each account uses its user's `ebay_environment`

---

## 8. Future Improvements

1. **Token caching:** Consider in-memory caching with TTL to reduce DB queries
2. **Identity API validation:** Enable by default for first use after refresh
3. **Metrics:** Add Prometheus metrics for token refresh success/failure rates
4. **Alerting:** Alert on consecutive token refresh failures

---

*End of documentation.*

