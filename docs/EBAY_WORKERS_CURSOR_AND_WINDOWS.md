# eBay Workers: Cursor, Windows, and Overlap

This document explains how all eBay workers share the same incremental, cursor-based sync model:

- First run: backfill a fixed number of days (90 by default, 30 for Buyer/Purchases).
- Subsequent runs: use the last cursor **minus 30 minutes** as the start of the next window.
- All runs advance the cursor to the **end** of the window on success.
- Overlap (30 minutes) plus **upsert-by-natural-key** makes all workers idempotent.

The goal is that **every API family follows the same behavior** so schedules and logs in the Admin Workers UI are predictable.

---

## Global helper: `compute_sync_window`

**File:** `backend/app/services/ebay_workers/state.py`

The core logic lives in `compute_sync_window(state, overlap_minutes=..., initial_backfill_days=...)`.

Key points:

- Reads `state.cursor_value` (ISO8601 string).
- If the cursor is present and parses:
  - `window_to = now` (current UTC time).
  - `window_from = cursor - overlap_minutes`.
- If the cursor is missing or invalid:
  - `window_to = now`.
  - `window_from = now - initial_backfill_days`.
- Returns a tuple of **timezone-aware** datetimes `(window_from, window_to)`.

There is also `get_or_create_global_config`, which seeds `EbayWorkerGlobalConfig` with JSON defaults:

- `overlap_minutes = 30` (global default overlap for future uses).
- `initial_backfill_days = 90`.

> Note: individual workers explicitly pass their own overlap and backfill values, but the global config now reflects the 30‑minute policy as well.

---

## Shared worker pattern

Every time-windowed worker follows the same high-level flow:

1. **Resolve account** and token for a given `ebay_account_id`.
2. **Get or create** `EbaySyncState` row for that account + API family.
3. **Skip** if `state.enabled` is `False`.
4. Acquire a per-account+API **run lock** via `start_run(...)`.
5. Use `compute_sync_window` to get `(window_from, window_to)` with a 30‑minute overlap.
6. Convert to ISO strings `from_iso`, `to_iso` for logging and downstream APIs.
7. Log `log_start(...)` into `EbayApiWorkerLog`.
8. Call the appropriate `EbayService.sync_*` method, passing:
   - `user_id` (org id),
   - `access_token`,
   - `run_id` for the SyncTerminal,
   - `ebay_account_id`, `ebay_user_id`,
   - `window_from=from_iso`, `window_to=to_iso`.
9. Read back `total_fetched`, `total_stored`, and a more specific `run_id` (if provided).
10. Log a synthetic `log_page(...)` and `log_done(...)` per worker run.
11. Call `mark_sync_run_result(db, state, cursor_value=to_iso, error=None)`
    - This advances the cursor to `window_to` on success.
12. Call `complete_run(...)` with a summary JSON:
    - `total_fetched`, `total_stored`, `duration_ms`, `window_from`, `window_to`, `sync_run_id`, etc.

On error, the workers call `log_error(...)`, **do not advance the cursor**, and call `fail_run(...)` with an error summary. `mark_sync_run_result` records `last_error` while leaving `cursor_value` unchanged.

---

## Per-worker configuration and overlap

### Orders (`orders` API family)

**Worker:** `backend/app/services/ebay_workers/orders_worker.py`

- Constants:
  - `OVERLAP_MINUTES_DEFAULT = 30`
  - `INITIAL_BACKFILL_DAYS_DEFAULT = 90`
- Uses `compute_sync_window(state, overlap_minutes=30, initial_backfill_days=90)`.
- Delegates heavy lifting to `EbayService.sync_all_orders(...)`.

**Service:** `EbayService.sync_all_orders`

- Accepts `window_from` / `window_to` ISO strings from the worker.
- Parses them to `start_dt` and `end_dt`:
  - If missing/invalid, falls back to `end_dt = now_utc`, `start_dt = end_dt - 90 days`.
- Derives `start_iso` and `end_iso` in `YYYY-MM-DDTHH:MM:SS.000Z` format.
- Builds Fulfillment search filter:
  - `filter = "lastModifiedDate:[{start_iso}..{end_iso}]"`.
- Paginates with `limit=ORDERS_PAGE_LIMIT` and `offset` while staying inside this **fixed** time window.
- For each page:
  - Inserts/updates via `PostgresEbayDatabase.batch_upsert_orders(...)`, keyed by `(order_id, user_id, ebay_account_id)`.
- Returns a summary dict with `total_fetched`, `total_stored`, and `run_id`.

### Transactions (`transactions` API family)

**Worker:** `backend/app/services/ebay_workers/transactions_worker.py`

- Constants:
  - `OVERLAP_MINUTES_DEFAULT = 30`
  - `INITIAL_BACKFILL_DAYS_DEFAULT = 90`
- Uses `compute_sync_window` and passes `window_from`/`window_to` into `EbayService.sync_all_transactions`.

**Service:** `EbayService.sync_all_transactions`

- Parses `window_from` and `window_to` into `start_date` / `end_date`.
- Defaults to a 90‑day window ending at `now` if missing or invalid.
- Builds an RSQL Finances filter:
  - `filter = "transactionDate:[start_iso..end_iso]"`.
- Calls `fetch_transactions(access_token, filter_params)` which:
  - Uses `sell/finances/v1/transaction` endpoint.
  - Honors the `transactionDate:[...]` filter.
- For each page:
  - Upserts via `ebay_db.upsert_transaction(...)`, keyed by `(transaction_id, user_id, ebay_account_id)`.
- Returns summary with `total_fetched`, `total_stored`, `run_id`.

### Finances (`finances` API family)

**Worker:** `backend/app/services/ebay_workers/finances_worker.py`

- Constants:
  - `OVERLAP_MINUTES_DEFAULT = 30`
  - `INITIAL_BACKFILL_DAYS_DEFAULT = 90`
- Same pattern as Transactions worker but using the finances tables and service.

**Service:** `EbayService.sync_finances_transactions`

- Parses `window_from`/`window_to` into `start_date` / `end_date`.
- Builds an RSQL filter:
  - `filter = "transactionDate:[start_iso..end_iso]"`.
- Calls `fetch_transactions` (same Finances API helper) with this filter.
- For each page:
  - Upserts via `PostgresEbayDatabase.upsert_finances_transaction(...)`, keyed by the external Finances `transactionId`.

### Messages (`messages` API family)

**Worker:** `backend/app/services/ebay_workers/messages_worker.py`

- Constants:
  - `OVERLAP_MINUTES_DEFAULT = 30`
  - `INITIAL_BACKFILL_DAYS_DEFAULT = 90`
- Uses `compute_sync_window` with 30‑minute overlap.
- Delegates to `EbayService.sync_all_messages`, passing `window_from`/`window_to`.

**Service:** `EbayService.sync_all_messages` (not shown here in full):

- Uses Trading API `GetMyMessages` with:
  - `StartTimeFrom = window_from` (ISO, truncated to seconds).
  - `StartTimeTo = window_to`.
- Two-phase approach:
  1. Fetch **message headers** page-by-page (IDs only) within the time window.
  2. Fetch message **bodies** in small batches (up to 10 IDs) via `GetMyMessages` with `ReturnMessages`.
- Normalizes and upserts into `ebay_messages` using external message IDs as keys.

### Cases (`cases` API family)

**Worker:** `backend/app/services/ebay_workers/cases_worker.py`

- Constants:
  - `CASES_OVERLAP_MINUTES_DEFAULT = 30`
  - `CASES_INITIAL_BACKFILL_DAYS_DEFAULT = 90`
- Uses `compute_sync_window` with 30‑minute overlap for its window.
- Calls `EbayService.sync_postorder_cases(..., window_from, window_to)`.

**Service:** `EbayService.sync_postorder_cases`

- Currently, Post-Order `casemanagement/search` does **not** support a clean time filter that matches our cursor model.
- `window_from`/`window_to` are accepted and logged, but the API call:
  - Fetches the latest cases via `GET /post-order/v2/casemanagement/search`.
- Upserts each case into `ebay_cases` via `ebay_db.upsert_case(...)`, keyed on external `caseId`.
- Worker cursor still advances to `window_to` on success, and dedup is enforced by the database constraints.

> Future enhancement: if eBay exposes a reliable created/lastUpdated date filter for cases, we can project the same window `[cursor - 30min, now]` onto that query param.

### Inquiries (`inquiries` API family)

**Worker:** `backend/app/services/ebay_workers/inquiries_worker.py`

- Constants:
  - `INQUIRIES_OVERLAP_MINUTES_DEFAULT = 30`
  - `INQUIRIES_INITIAL_BACKFILL_DAYS_DEFAULT = 90`
- Uses `compute_sync_window` with 30‑minute overlap.
- Calls `EbayService.sync_postorder_inquiries(..., window_from, window_to)`.

**Service:** `EbayService.sync_postorder_inquiries`

- Similar to cases: `window_from`/`window_to` are logged, but the current call to
  `GET /post-order/v2/inquiry/search` does not yet pass a time filter.
- Normalizes inquiries and detailed inquiry payloads, then upserts via
  `ebay_db.upsert_inquiry(...)`, keyed by external `inquiryId`.

### Offers (`offers` API family)

**Worker:** `backend/app/services/ebay_workers/offers_worker.py`

- Constants:
  - `OVERLAP_MINUTES_DEFAULT = 30` (was 360 before; now aligned to the global policy).
  - `INITIAL_BACKFILL_DAYS_DEFAULT = 90`.
- Uses `compute_sync_window` but **Offers APIs themselves do not accept a date filter**.
- Passes `window_from`/`window_to` to `EbayService.sync_all_offers` for logging only.

**Service:** `EbayService.sync_all_offers`

- Two-step workflow:
  1. Fetch **all inventory items** via `GET /sell/inventory/v1/inventory_item` (paginated) to collect SKUs.
  2. For each SKU, call `GET /sell/inventory/v1/offer?sku=...` to fetch offers.
- Upserts via `ebay_db.upsert_offer(...)`, keyed by external offer identifiers.
- Time window is informational/diagnostic only; dedup + overlap keep things safe.

### Buyer / Purchases (`buyer` API family)

**Worker:** `backend/app/services/ebay_workers/purchases_worker.py`

- Constants:
  - `OVERLAP_MINUTES_DEFAULT = 30`.
  - `INITIAL_BACKFILL_DAYS_DEFAULT = 30` (shorter backfill for Buying history).
- Uses `compute_sync_window` to compute `[window_from, window_to]` but currently passes:
  - `since = window_from` into `EbayService.get_purchases`.

**Service:** `EbayService.get_purchases`

- Wrapper around Trading `GetMyeBayBuying`.
- For now, it **does not** send date filters to eBay (Trading request uses the default window), but the signature accepts `since` so we can later:
  - Add a true date range filter once confirmed in Trading docs.
- Normalizes XML into `EbayBuyer`-compatible rows and the worker:
  - Uses `EbayBuyer` unique key (`ebay_account_id`, `item_id`, `transaction_id`, `order_line_item_id`).
  - Updates only API-owned fields on existing rows.

### Active Inventory (`active_inventory` API family)

**Worker:** `backend/app/services/ebay_workers/active_inventory_worker.py`

- Snapshot worker:
  - `ACTIVE_INV_LIMIT_DEFAULT = 0`.
  - `INITIAL_BACKFILL_DAYS_DEFAULT = 0` (window concept not used).
- Instead of `compute_sync_window`, it logs a synthetic single-point window:
  - `window_from = now`, `window_to = now` (for observability only).
- Calls `EbayService.sync_active_inventory_report`, which:
  - Uses Trading `GetMyeBaySelling` ActiveList.
  - Produces a **full snapshot** of active listings into `ebay_active_inventory`.
- Cursor is treated as "last successful snapshot timestamp".

---

## Schedule simulation (`/ebay/workers/schedule`)

**File:** `backend/app/routers/ebay_workers.py`

The `GET /ebay/workers/schedule` endpoint shows a **simulated future schedule** using the same overlap/backfill values as the workers.

Important pieces:

- `ensured_families`: includes `orders`, `transactions`, `offers`, `messages`, `active_inventory`, `cases`, `inquiries`, `finances`, `buyer`.
- For each family, the router ensures there is an `EbaySyncState` row.
- Two config maps mirror the worker constants:
  - `overlap_by_api`: now sets **30** minutes for all time-windowed workers
    (`orders`, `transactions`, `finances`, `cases`, `inquiries`, `offers`, `messages`).
  - `backfill_by_api`: 90 days for most, 90 for offers/messages as well.
- For `active_inventory`:
  - The schedule shows run times but no windows (`window_from = None`, `window_to = None`).

The schedule simulation uses a local helper:

- `compute_window_from_cursor(cursor_value, now_dt, overlap_min, backfill_days)`:
  - Pure, inlined version of `compute_sync_window` for projection only.
- It repeatedly advances a local `cursor_value` with the same rule as the real workers:
  - Next cursor becomes the **previous `window_to`**.

This ensures the Admin Workers UI shows **exactly the same 30‑minute overlap** that runtime workers use.

---

## Summary of behavior

- All incremental workers (Orders, Transactions, Finances, Messages, Cases, Inquiries, Offers, Buyer) share the same cursor policy:
  - First run: backfill (90 days, or 30 days for Buyer).
  - Subsequent runs: `[cursor - 30 minutes, now]`.
  - Cursor is moved to `window_to` only on successful runs.
- Where eBay APIs expose a reliable time filter (`lastModifiedDate`, `transactionDate`, Trading `StartTimeFrom/To`), the workers project the window directly onto those parameters.
- Where the external API does **not** support such a filter (Post-Order, Offers, current Trading Buying flow):
  - `window_from`/`window_to` are logged and used only for cursor semantics.
  - Safety is guaranteed via **upserts on natural keys** and the 30‑minute overlap.
- `/ebay/workers/schedule` is fully aligned with runtime behavior, using the same overlap/backfill settings to simulate future windows.

This unified model means that **every worker run** has:

- A clearly defined time window.
- A well-defined cursor advancement rule.
- A consistent overlap of 30 minutes across all time-based workers.
