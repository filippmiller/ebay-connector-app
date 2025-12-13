# eBay Workers System Audit Report

**Date:** December 4, 2025  
**Type:** Read-only audit  
**Repository:** `C:\dev\ebay-connector-app`

---

## 1. Summary

This document provides a comprehensive audit of the eBay worker system that powers the "Workers command control" admin page. The system consists of **10 workers** that synchronize data from various eBay APIs into the application's PostgreSQL database.

### Current State (as observed)

| Category | Workers | Cursor Status |
|----------|---------|---------------|
| **Healthy (fresh cursor ~Dec 4, 12:09)** | Active_inventory, Buyer, Messages | Running every 5 minutes, cursors advancing |
| **Stuck (cursor ~Dec 2-3)** | Cases, Finances, Inquiries, Returns | Cursors frozen 1-2 days behind |
| **401 Errors in background** | Orders, Offers, Transactions | Fail with 401 in background, work with manual "Run now" |

### Key Questions This Audit Answers

1. How is the worker system architected?
2. Why do only 3 workers have fresh cursors?
3. Why do Transactions/Offers/Orders fail with 401 in background but succeed when triggered manually?

---

## 2. High-Level Architecture Overview

### 2.1 Pipeline Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           ADMIN UI (Frontend)                                │
│  frontend/src/components/workers/EbayWorkersPanel.tsx                       │
│  - Shows 10 workers with status, cursor, last run                           │
│  - "Run now" button → POST /ebay/workers/run                                │
│  - "BIG RED BUTTON" → global toggle                                         │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         BACKEND API ROUTER                                   │
│  backend/app/routers/ebay_workers.py                                        │
│  - GET /ebay/workers/config     → Worker config + status for account        │
│  - POST /ebay/workers/run       → Manual trigger for single worker          │
│  - POST /ebay/workers/run-all   → Run all enabled workers                   │
│  - GET /ebay/workers/runs       → Run history                               │
│  - GET /ebay/workers/schedule   → Projected future schedule                 │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    ▼                               ▼
┌──────────────────────────────┐   ┌──────────────────────────────────────────┐
│     MANUAL RUN PATH          │   │        BACKGROUND SCHEDULER              │
│  (Run now button)            │   │  backend/app/workers/ebay_workers_loop.py│
│                              │   │  - Runs every 300 seconds (5 min)        │
│  Direct call to worker       │   │  - First: run_token_refresh_job()        │
│  function in web app         │   │  - Then: run_cycle_for_all_accounts()    │
│  context                     │   │                                          │
└──────────────────────────────┘   └──────────────────────────────────────────┘
                    │                               │
                    └───────────────┬───────────────┘
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           SCHEDULER                                          │
│  backend/app/services/ebay_workers/scheduler.py                             │
│  - run_cycle_for_all_accounts() → iterates active eBay accounts             │
│  - run_cycle_for_account(id) → runs all enabled workers for 1 account       │
│  - Parallel execution with asyncio.gather()                                 │
│  - Max 5 concurrent accounts (semaphore)                                    │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      INDIVIDUAL WORKERS                                      │
│  backend/app/services/ebay_workers/*.py                                     │
│                                                                             │
│  BaseWorker (base_worker.py):                                               │
│  - run_for_account(ebay_account_id) → main entry point                      │
│  - Gets EbayAccount + EbayToken from DB                                     │
│  - Computes sync window via compute_sync_window()                           │
│  - Calls execute_sync() (implemented by each worker)                        │
│  - Updates cursor on success, logs error on failure                         │
│                                                                             │
│  10 Workers:                                                                │
│  ├── orders_worker.py        → EbayService.sync_all_orders()               │
│  ├── transactions_worker.py  → EbayService.sync_all_transactions()         │
│  ├── offers_worker.py        → ebay_offers_service.sync_offers_for_account()│
│  ├── messages_worker.py      → EbayService.sync_all_messages()             │
│  ├── active_inventory_worker.py → EbayService.sync_active_inventory_report()│
│  ├── purchases_worker.py     → EbayService.get_purchases() (buyer)         │
│  ├── cases_worker.py         → EbayService.sync_postorder_cases()          │
│  ├── inquiries_worker.py     → EbayService.sync_postorder_inquiries()      │
│  ├── finances_worker.py      → EbayService.sync_finances_transactions()    │
│  └── returns_worker.py       → EbayService.sync_postorder_returns()        │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           eBay APIs                                          │
│  - Fulfillment API (Orders)        → api.ebay.com/sell/fulfillment/v1      │
│  - Finances API (Transactions)     → apiz.ebay.com/sell/finances/v1        │
│  - Inventory API (Offers)          → api.ebay.com/sell/inventory/v1        │
│  - Trading API (Messages, Buyer, Active Inventory) → api.ebay.com/ws/api.dll│
│  - Post-Order API (Cases, Inquiries, Returns) → api.ebay.com/post-order/v2 │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                       PostgreSQL (Supabase)                                  │
│  Tables:                                                                    │
│  - ebay_sync_state      → cursor, enabled flag, last_error per worker      │
│  - ebay_worker_run      → individual run history                           │
│  - ebay_api_worker_log  → detailed logs per run                            │
│  - ebay_orders, ebay_transactions, ebay_messages, etc. → domain data       │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Key Components

| Component | File | Purpose |
|-----------|------|---------|
| Background loop | `backend/app/workers/ebay_workers_loop.py` | Runs every 5 min, triggers all workers |
| Scheduler | `backend/app/services/ebay_workers/scheduler.py` | Orchestrates workers per account |
| Base worker | `backend/app/services/ebay_workers/base_worker.py` | Shared logic for token/cursor/logging |
| State management | `backend/app/services/ebay_workers/state.py` | Cursor computation, global toggle |
| Run locking | `backend/app/services/ebay_workers/runs.py` | Prevents concurrent runs |
| API router | `backend/app/routers/ebay_workers.py` | REST endpoints for UI |
| DB models | `backend/app/models_sqlalchemy/ebay_workers.py` | EbaySyncState, EbayWorkerRun |

---

## 3. Worker Inventory

### 3.1 Complete Worker Table

| # | Worker Name | API Family | eBay API | Destination Table | Cursor Type | Overlap | File |
|---|-------------|------------|----------|-------------------|-------------|---------|------|
| 1 | **Active_inventory** | `active_inventory` | Trading API (GetMyeBaySelling) | `ebay_active_inventory` | Snapshot (no window) | N/A | `active_inventory_worker.py` |
| 2 | **Buyer** | `buyer` | Trading API (GetMyeBayBuying) | `ebay_buyer` | Time-based | 30 min | `purchases_worker.py` |
| 3 | **Cases** | `cases` | Post-Order API | `ebay_cases` | Time-based | 30 min | `cases_worker.py` |
| 4 | **Finances** | `finances` | Finances API | `ebay_finances_transactions` | Time-based | 30 min | `finances_worker.py` |
| 5 | **Inquiries** | `inquiries` | Post-Order API | `ebay_inquiries` | Time-based | 30 min | `inquiries_worker.py` |
| 6 | **Messages** | `messages` | Trading API (GetMyMessages) | `ebay_messages` | Time-based | 30 min | `messages_worker.py` |
| 7 | **Offers** | `offers` | Inventory API | `ebay_inventory_offers` | Snapshot (no window) | N/A | `offers_worker.py` |
| 8 | **Orders** | `orders` | Fulfillment API | `ebay_orders` | Time-based | 30 min | `orders_worker.py` |
| 9 | **Returns** | `returns` | Post-Order API | `ebay_returns` | Time-based | 30 min | `returns_worker.py` |
| 10 | **Transactions** | `transactions` | Finances API | `ebay_transactions` | Time-based | 30 min | `transactions_worker.py` |

### 3.2 API Family Registration

The `API_FAMILIES` list in `scheduler.py` defines which workers are automatically scheduled:

```python
API_FAMILIES = [
    "orders",
    "transactions",
    "offers",
    "messages",
    "active_inventory",
    "buyer",
    "cases",
    "inquiries",
    "finances",
    "returns",
]
```

All 10 workers are registered for automatic scheduling.

---

## 4. Scheduling & Cursor Logic

### 4.1 Background Loop

**File:** `backend/app/workers/ebay_workers_loop.py`

The main background loop runs every 5 minutes:

```python
async def run_ebay_workers_loop(interval_seconds: int = 300) -> None:
    while True:
        # 1. First refresh tokens
        await run_token_refresh_job(db)
        
        # 2. Then run all workers
        await run_cycle_for_all_accounts()
        
        # 3. Sleep 5 minutes
        await asyncio.sleep(interval_seconds)
```

**Key observation:** Token refresh happens **before** workers run, ensuring fresh tokens are available.

### 4.2 Sync Window Computation

**File:** `backend/app/services/ebay_workers/state.py`

The `compute_sync_window()` function determines the time window for each run:

```python
def compute_sync_window(
    state: EbaySyncState,
    *,
    now: Optional[datetime] = None,
    overlap_minutes: int = 60,
    initial_backfill_days: int = 90,
) -> Tuple[datetime, datetime]:
    """
    - If cursor exists: window_from = cursor - overlap_minutes
    - If cursor missing: window_from = now - overlap_minutes (NOT backfill)
    - window_to = now (always)
    """
```

**Important:** The current implementation does **not** use `initial_backfill_days` for new cursors. This means new accounts only look back by the overlap window (30 minutes), not 90 days.

### 4.3 Cursor Update Policy

| Event | Cursor Behavior |
|-------|-----------------|
| Run succeeds | Cursor advances to `window_to` |
| Run fails | Cursor unchanged, `last_error` populated |
| No data fetched | Cursor still advances (success case) |

### 4.4 Run Locking

**File:** `backend/app/services/ebay_workers/runs.py`

Workers use row-level locking to prevent concurrent runs:

```python
def start_run(...) -> Optional[EbayWorkerRun]:
    # 1. Acquire lock on EbaySyncState row
    db.query(EbaySyncState)
       .filter(...)
       .with_for_update()  # ← Row-level lock
       .first()
    
    # 2. Check if another run is active (heartbeat within 10 min)
    active = get_active_run(...)
    if active:
        return None  # Skip, already running
    
    # 3. Create new run
    run = EbayWorkerRun(status="running", ...)
```

---

## 5. Per-Worker Analysis

### 5.1 Active_inventory (HEALTHY ✅)

**Status:** Fresh cursor, running successfully every 5 minutes

**Implementation:**
- File: `backend/app/services/ebay_workers/active_inventory_worker.py`
- Uses `BaseWorker` with `overlap_minutes=None` (snapshot mode)
- Calls `EbayService.sync_active_inventory_report()`
- Uses Trading API `GetMyeBaySelling`

**Why it works:**
- Snapshot worker - fetches all active listings, no time filter needed
- Trading API is less strict about token scopes
- No environment parameter needed (uses global settings)

```python
class ActiveInventoryWorker(BaseWorker):
    def __init__(self):
        super().__init__(
            api_family="active_inventory",
            overlap_minutes=None,  # No window, full snapshot
            initial_backfill_days=0,
            limit=0,
        )
```

### 5.2 Buyer (HEALTHY ✅)

**Status:** Fresh cursor, running successfully

**Implementation:**
- File: `backend/app/services/ebay_workers/purchases_worker.py`
- Uses `BaseWorker` with 30-min overlap
- Calls `EbayService.get_purchases(access_token, since=window_from)`
- Uses Trading API `GetMyeBayBuying`

**Why it works:**
- Trading API is more permissive
- Direct token usage from `EbayToken` model
- No environment mismatch issues

```python
class PurchasesWorker(BaseWorker):
    def __init__(self):
        super().__init__(
            api_family="buyer",
            overlap_minutes=30,
            initial_backfill_days=30,
            limit=500,
        )
```

### 5.3 Messages (HEALTHY ✅)

**Status:** Fresh cursor, running successfully

**Implementation:**
- File: `backend/app/services/ebay_workers/messages_worker.py`
- Uses `BaseWorker` with 30-min overlap
- Calls `EbayService.sync_all_messages()`
- Uses Trading API `GetMyMessages`

**Why it works:**
- Same as Buyer/Active_inventory - Trading API
- Proper time window support in API

```python
class MessagesWorker(BaseWorker):
    def __init__(self):
        super().__init__(
            api_family="messages",
            overlap_minutes=30,
            initial_backfill_days=90,
            limit=200,
        )
```

### 5.4 Cases (STUCK ⚠️)

**Status:** Cursor stuck at ~Dec 4, 08:15 (several hours behind)

**Implementation:**
- File: `backend/app/services/ebay_workers/cases_worker.py`
- Uses `BaseWorker` with 30-min overlap
- Calls `EbayService.sync_postorder_cases()`
- Uses Post-Order API `/post-order/v2/casemanagement/search`

**Possible reasons for stuck cursor:**
1. Post-Order API returns empty results (no new cases)
2. API rate limiting or throttling
3. Token scope issues for Post-Order API

```python
class CasesWorker(BaseWorker):
    def __init__(self):
        super().__init__(
            api_family="cases",
            overlap_minutes=30,
            initial_backfill_days=90,
            limit=None,
        )
```

### 5.5 Finances (STUCK ⚠️)

**Status:** Cursor stuck at ~Dec 2, 12:15 (2 days behind)

**Implementation:**
- File: `backend/app/services/ebay_workers/finances_worker.py`
- Uses `BaseWorker` with 30-min overlap
- Calls `EbayService.sync_finances_transactions()`
- Uses Finances API at `apiz.ebay.com` (different host!)

**Key observation:** Does NOT pass `environment` parameter (unlike Transactions worker)

```python
async def execute_sync(...) -> Dict[str, Any]:
    ebay_service = EbayService()
    # No environment parameter!
    result = await ebay_service.sync_finances_transactions(
        user_id=user_id,
        access_token=token.access_token,
        ...
    )
```

**Possible reasons for stuck cursor:**
1. API endpoint mismatch (`apiz.` vs `api.`)
2. Token scope mismatch
3. Silent errors not propagating

### 5.6 Inquiries (STUCK ⚠️)

**Status:** Cursor stuck at ~Dec 2, 12:15

**Implementation:**
- File: `backend/app/services/ebay_workers/inquiries_worker.py`
- Does NOT use `BaseWorker` class
- Manual implementation of the worker pattern
- Calls `EbayService.sync_postorder_inquiries()`

**Notable:** This worker has its own implementation of the run/cursor logic, not using BaseWorker:

```python
async def run_inquiries_worker_for_account(ebay_account_id: str) -> Optional[str]:
    db: Session = SessionLocal()
    # ... manual implementation of all BaseWorker logic
```

**Possible reasons for stuck cursor:**
- Similar to Cases - Post-Order API issues
- Different implementation might have subtle bugs

### 5.7 Returns (STUCK ⚠️)

**Status:** Cursor stuck at ~Dec 2, 12:15

**Implementation:**
- File: `backend/app/services/ebay_workers/returns_worker.py`
- Does NOT use `BaseWorker` class (manual implementation)
- Calls `EbayService.sync_postorder_returns()`

**Same pattern as Inquiries:** Manual implementation rather than BaseWorker inheritance.

### 5.8 Orders (401 ERRORS ❌)

**Status:** Cursor stuck at ~Dec 4, 07:03, fails with 401 in background

**Implementation:**
- File: `backend/app/services/ebay_workers/orders_worker.py`
- Uses `BaseWorker` with 30-min overlap
- Calls `EbayService.sync_all_orders()`
- Uses Fulfillment API at `api.ebay.com/sell/fulfillment/v1`

**Critical observation:** Does NOT pass `environment` parameter:

```python
async def execute_sync(...) -> Dict[str, Any]:
    ebay_service = EbayService()
    # No environment parameter!
    result = await ebay_service.sync_all_orders(
        user_id=user_id,
        access_token=token.access_token,
        run_id=sync_run_id,
        ...
    )
```

**But sync_all_orders uses global settings for base URL:**

```python
# In EbayService.sync_all_orders():
api_url = f"{settings.ebay_api_base_url}/sell/fulfillment/v1/order"
```

### 5.9 Offers (401 ERRORS ❌)

**Status:** Cursor stuck at ~Dec 3, 14:53, fails with 401 in background

**Implementation:**
- File: `backend/app/services/ebay_workers/offers_worker.py`
- Uses `BaseWorker` with `overlap_minutes=None` (snapshot)
- Uses **different service:** `ebay_offers_service` instead of `EbayService`

```python
async def execute_sync(...) -> Dict[str, Any]:
    # Uses ebay_offers_service, NOT EbayService!
    stats = await ebay_offers_service.sync_offers_for_account(db, account)
```

**EbayOffersService implementation:**

```python
class EbayOffersService:
    def __init__(self):
        self.base_url = settings.ebay_api_base_url.rstrip("/")  # Uses global setting
```

### 5.10 Transactions (401 ERRORS ❌)

**Status:** Cursor stuck at ~Dec 3, 14:52, fails with 401 in background

**Implementation:**
- File: `backend/app/services/ebay_workers/transactions_worker.py`
- Uses `BaseWorker` with 30-min overlap
- Calls `EbayService.sync_all_transactions()`

**UNIQUE: This is the ONLY worker that passes `environment` parameter:**

```python
async def execute_sync(...) -> Dict[str, Any]:
    ebay_service = EbayService()
    user_id = account.org_id

    # Fetch user to get environment
    user = db.query(User).filter(User.id == user_id).first()
    environment = user.ebay_environment if user else "sandbox"

    result = await ebay_service.sync_all_transactions(
        ...
        environment=environment,  # ← ONLY worker that does this!
    )
```

---

## 6. Run Now vs Background Worker Comparison

### 6.1 Execution Paths

Both paths ultimately call the **same worker functions**, but in different contexts:

| Aspect | Run Now (Manual) | Background Loop |
|--------|-----------------|-----------------|
| **Trigger** | User clicks "Run now" in UI | `run_ebay_workers_loop()` timer |
| **Entry point** | `POST /ebay/workers/run` | `run_cycle_for_all_accounts()` |
| **Function called** | e.g., `run_orders_worker_for_account()` | Same function |
| **Process context** | Web app (FastAPI) | Same process (asyncio task) |
| **Token source** | `EbayToken` from DB | Same |
| **Token refresh** | Not explicitly called | `run_token_refresh_job()` called first |

### 6.2 Key Difference: Token Refresh Timing

**Background loop flow:**
```python
async def run_ebay_workers_loop():
    while True:
        # 1. FIRST refresh tokens
        await run_token_refresh_job(db)  # ← This happens first
        
        # 2. THEN run workers
        await run_cycle_for_all_accounts()  # ← Uses freshly refreshed tokens
        
        await asyncio.sleep(300)
```

**Manual Run now flow:**
```python
@router.post("/run")
async def run_worker_once(...):
    # No token refresh here!
    # Directly calls worker, which uses whatever token is in DB
    run_id = await run_orders_worker_for_account(account_id)
```

### 6.3 Token Acquisition in Workers

All workers (via BaseWorker) get tokens the same way:

```python
# In BaseWorker.run_for_account():
token: Optional[EbayToken] = ebay_account_service.get_token(db, ebay_account_id)
if not token or not token.access_token:
    logger.warning(f"{self.api_family} worker: no token for account {ebay_account_id}")
    return None
```

The `access_token` property of `EbayToken` returns the raw access token string from the database.

### 6.4 Why Manual Works but Background Fails?

**Hypothesis 1: Token Refresh Failure**
- `run_token_refresh_job()` silently fails to refresh some tokens
- Workers then use stale/expired tokens
- Manual runs might coincidentally happen when token is still valid

**Hypothesis 2: Token Caching**
- There might be some in-memory caching of tokens
- Web app context has different cache state than background loop

**Hypothesis 3: Database Session Differences**
- Background loop creates new `SessionLocal()` per cycle
- Manual runs use request-scoped `Depends(get_db)`
- Token retrieval might behave differently

---

## 7. Findings & Hypotheses

### 7.1 Why Only 3 Workers Have Fresh Cursors

**Pattern observed:**
- Healthy workers: Active_inventory, Buyer, Messages - all use **Trading API**
- Stuck/Failing workers: Use REST APIs (Fulfillment, Finances, Inventory, Post-Order)

**Hypothesis:** Trading API has more permissive authentication requirements. The OAuth token may have:
- All Trading API scopes properly configured
- Missing or misconfigured REST API scopes

### 7.2 Why Orders/Offers/Transactions Fail with 401

**Root Cause Analysis:**

| Factor | Evidence | Impact |
|--------|----------|--------|
| **Token refresh issues** | Background loop calls `run_token_refresh_job()` but errors may be swallowed | Stale tokens used |
| **Environment parameter** | Only `transactions_worker` passes `environment` to service | Other workers may hit wrong endpoint |
| **Different API hosts** | Finances uses `apiz.ebay.com`, others use `api.ebay.com` | Possible token scope mismatch |
| **Offers uses different service** | `EbayOffersService` vs `EbayService` | Different base URL resolution |

**Most Likely Cause:**

The token refresh service (`run_token_refresh_job()`) may be:
1. Failing to decrypt refresh tokens properly (JWT_SECRET mismatch historical issue)
2. Skipping accounts that don't "need" refresh (within 15-minute threshold)
3. Silently failing and not updating `access_token`

When manual "Run now" succeeds, it's likely because:
- The user recently performed another action that triggered a token refresh
- The token happens to still be valid at that moment
- The web app context has a fresher token in session

### 7.3 Why Post-Order Workers (Cases, Inquiries, Returns) Are Stuck

**Pattern:** These workers have cursors stuck at ~Dec 2, 12:15 - all at the same time.

**Hypotheses:**
1. Post-Order API requires specific scopes not present on the token
2. All three failed at the same moment and haven't recovered
3. Post-Order API may have rate limits or quota issues

**Note:** Inquiries and Returns don't use `BaseWorker` - they have manual implementations which may have subtle differences in error handling.

### 7.4 Inconsistency: Environment Parameter

**Critical finding:**

```python
# transactions_worker.py - DOES pass environment
user = db.query(User).filter(User.id == user_id).first()
environment = user.ebay_environment if user else "sandbox"
result = await ebay_service.sync_all_transactions(..., environment=environment)

# orders_worker.py - does NOT pass environment
result = await ebay_service.sync_all_orders(...)  # Uses global settings.EBAY_ENVIRONMENT
```

If `user.ebay_environment` differs from `settings.EBAY_ENVIRONMENT`, this causes:
- Orders worker → uses global setting (may be wrong)
- Transactions worker → uses user-specific setting (correct)

---

## 8. Questions / Unknowns

The following questions require access to production logs or live debugging:

1. **What does the token refresh log show?** Check `ebay_token_refresh_log` table for failed refreshes.

2. **What is the actual 401 error message?** The `last_error` field in `ebay_sync_state` should contain details.

3. **Is `settings.EBAY_ENVIRONMENT` set correctly in Railway?** Check if it's "production" or "sandbox".

4. **What scopes are on the tokens?** The `EbayAuthorization` table contains scope arrays.

5. **When did the stuck workers last succeed?** Check `ebay_worker_run` table for historical success/failure patterns.

---

## 9. Code References

### 9.1 Key Files

| File | Purpose |
|------|---------|
| `backend/app/workers/ebay_workers_loop.py` | Background loop entry point |
| `backend/app/services/ebay_workers/scheduler.py` | Orchestrates workers per account |
| `backend/app/services/ebay_workers/base_worker.py` | BaseWorker class - shared logic |
| `backend/app/services/ebay_workers/state.py` | `compute_sync_window()`, cursor management |
| `backend/app/services/ebay_workers/runs.py` | Run locking with `SELECT FOR UPDATE` |
| `backend/app/routers/ebay_workers.py` | REST API for UI |
| `backend/app/models_sqlalchemy/ebay_workers.py` | DB models |
| `backend/app/services/ebay_token_refresh_service.py` | Token refresh logic |
| `backend/app/config.py` | `EBAY_ENVIRONMENT`, base URLs |

### 9.2 Individual Worker Files

| Worker | File | Special Notes |
|--------|------|---------------|
| Active Inventory | `active_inventory_worker.py` | Snapshot, no window |
| Buyer | `purchases_worker.py` | Trading API |
| Messages | `messages_worker.py` | Trading API |
| Cases | `cases_worker.py` | Post-Order API |
| Finances | `finances_worker.py` | Uses `apiz.` host |
| Inquiries | `inquiries_worker.py` | Manual implementation (no BaseWorker) |
| Returns | `returns_worker.py` | Manual implementation (no BaseWorker) |
| Orders | `orders_worker.py` | Fulfillment API, 401 issues |
| Offers | `offers_worker.py` | Uses `EbayOffersService` |
| Transactions | `transactions_worker.py` | Only one with `environment` param |

### 9.3 Key Functions

```python
# Token refresh before workers
async def run_token_refresh_job(db, force_all=False, capture_http=False, triggered_by="scheduled"):
    # Refreshes tokens for accounts expiring within 15 minutes
    pass

# Main scheduler entry
async def run_cycle_for_all_accounts():
    # 1. Refresh tokens first
    await run_token_refresh_job(db)
    # 2. Run workers for all active accounts
    for account in accounts:
        await run_cycle_for_account(account.id)

# Sync window computation
def compute_sync_window(state, overlap_minutes=60, initial_backfill_days=90):
    # Returns (window_from, window_to) based on cursor
    pass

# BaseWorker main method
async def run_for_account(self, ebay_account_id: str):
    # Get account, token, state
    # Compute window
    # Call execute_sync()
    # Update cursor on success
    pass
```

---

## 10. Recommendations (for future work)

> **Note:** This audit is read-only. These are observations, not implemented changes.

### High Priority

1. **Standardize environment handling:** All workers should pass `environment` parameter like `transactions_worker.py` does.

2. **Investigate token refresh failures:** Add more detailed logging to `run_token_refresh_job()` to surface silent failures.

3. **Unify worker implementations:** `inquiries_worker.py` and `returns_worker.py` should use `BaseWorker` for consistency.

### Medium Priority

4. **Add token refresh logging to UI:** Show recent refresh attempts/failures in Workers panel.

5. **Implement per-worker retry logic:** Currently, if a worker fails, it just waits for the next 5-minute cycle.

### Low Priority

6. **Consider separate token refresh for REST vs Trading APIs:** Different APIs may need different token handling.

---

## Appendix A: Database Schema

### ebay_sync_state

```sql
CREATE TABLE ebay_sync_state (
    id VARCHAR(36) PRIMARY KEY,
    ebay_account_id VARCHAR(36) NOT NULL,
    ebay_user_id VARCHAR(64) NOT NULL,
    api_family VARCHAR(64) NOT NULL,        -- "orders", "transactions", etc.
    enabled BOOLEAN DEFAULT TRUE,
    cursor_type VARCHAR(64),                -- e.g., "lastModifiedDate"
    cursor_value VARCHAR(64),               -- ISO8601 timestamp
    last_run_at TIMESTAMP WITH TIME ZONE,
    last_error TEXT,
    created_at TIMESTAMP WITH TIME ZONE,
    updated_at TIMESTAMP WITH TIME ZONE
);
```

### ebay_worker_run

```sql
CREATE TABLE ebay_worker_run (
    id VARCHAR(36) PRIMARY KEY,
    ebay_account_id VARCHAR(36) NOT NULL,
    ebay_user_id VARCHAR(64) NOT NULL,
    api_family VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL,            -- "running", "completed", "error"
    started_at TIMESTAMP WITH TIME ZONE,
    finished_at TIMESTAMP WITH TIME ZONE,
    heartbeat_at TIMESTAMP WITH TIME ZONE,
    summary_json JSONB
);
```

---

*End of audit report.*

