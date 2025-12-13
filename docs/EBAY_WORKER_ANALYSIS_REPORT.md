# eBay Worker Architecture Analysis & Critique

## 1. Overview
This report analyzes the current implementation of eBay background workers, focusing on security, efficiency, standardization, and reliability. The analysis covers the scheduler, state management, and specific worker implementations (Transactions, Active Inventory, Cases, etc.).

## 2. Critical Findings

### 2.1. Concurrency & Race Conditions
*   **Worker Locking (`runs.py`):** The `start_run` function checks for an active run and then inserts a new run row. This check-then-act sequence is not atomic. Two worker instances (e.g., one in the Web App and one in a separate service, or two Web App replicas) could race and both start a run for the same account/API combination.
    *   **Impact:** Duplicate processing, race conditions in data insertion, API rate limit exhaustion.
    *   **Recommendation:** Use a database-level lock (e.g., `SELECT ... FOR UPDATE` on the `EbaySyncState` row) or a unique constraint on `(ebay_account_id, api_family)` where `status='running'`.

*   **Active Inventory Upsert:** The `sync_active_inventory_report` function uses a read-then-write pattern:
    ```python
    existing = db_session.query(ActiveInventory).filter(...).one_or_none()
    if existing: update...
    else: insert...
    ```
    This is not atomic. If two runs occur simultaneously, both will see "no existing record" and attempt to insert, leading to `IntegrityError` or duplicate data.
    *   **Recommendation:** Use atomic `ON CONFLICT` (upsert) clauses via SQLAlchemy or the `ebay_db` wrapper.

### 2.2. Data Integrity & Backfilling
*   **Broken Backfill Logic (`state.py`):** The `compute_sync_window` function ignores the `initial_backfill_days` parameter when a cursor is missing.
    ```python
    # No cursor yet – behave as if the last successful run ended "now"
    cursor_dt = now
    ```
    *   **Impact:** New accounts will **NOT** import historical data. They will only start syncing data from the moment they are connected (minus the overlap window).
    *   **Recommendation:** Logic should be: `if not cursor: cursor_dt = now - timedelta(days=initial_backfill_days)`.

*   **Cursor Updates:** Cursors are updated to `window_to` (the start time of the run) only if the run succeeds. This is generally good ("at-least-once" delivery). However, if a run fails after processing 90% of pages, the next run re-processes everything.
    *   **Recommendation:** Consider checkpointing cursors for long-running jobs, or accept this trade-off for simplicity.

### 2.3. Efficiency & Performance
*   **Single-Row Upserts:** Most workers (e.g., `sync_postorder_cases`, `sync_all_transactions`) iterate through results and perform a database write for *every single item*.
    ```python
    for dispute in disputes:
        ebay_db.upsert_dispute(...)
    ```
    *   **Impact:** High database latency, connection pool exhaustion, and slow worker performance.
    *   **Recommendation:** Implement batch upserts (`bulk_insert_mappings` with `ON CONFLICT`) to insert/update hundreds of rows in a single query.

*   **Memory Usage:** Some workers (e.g., `sync_postorder_cases`) appear to fetch all data into memory before processing, or rely on helper methods (`fetch_postorder_cases`) whose pagination strategy is opaque. If these helpers fetch all pages into a list, it poses an OOM (Out of Memory) risk for large accounts.

### 2.4. Standardization
*   **Inconsistent Database Access:**
    *   `sync_all_transactions` uses `fin_db.upsert_finances_transaction` (good abstraction).
    *   `sync_active_inventory_report` uses raw `db_session` queries mixed with `ebay_db` calls (inconsistent).
*   **Pagination Logic:** Pagination logic is duplicated across workers (`sync_active_inventory_report` implements it manually, others delegate it).

## 3. Security Considerations
*   **Token Handling:** The recent fix (Proxy Mode) mitigates the risk of environment variable mismatches. However, ensure `INTERNAL_API_KEY` is rotated and high-entropy.
*   **Logging:** The `_mask_prefix` utility is used correctly for tokens. However, be cautious with `logger.error(str(e))` in `httpx` exceptions, as they might leak query parameters if sensitive data is ever passed there (currently seems safe as tokens are headers).

## 4. Recommendations Roadmap

### Immediate Fixes (High Priority)
1.  **Fix Backfill Logic:** Update `compute_sync_window` to respect `initial_backfill_days` for new accounts.
2.  **Fix Locking:** Implement `SELECT ... FOR UPDATE` in `start_run` or `get_or_create_sync_state` to prevent race conditions.

### Optimization (Medium Priority)
3.  **Batch Upserts:** Refactor `EbayDatabase` methods to accept lists of items and perform bulk upserts.
4.  **Atomic Inventory Sync:** Rewrite `sync_active_inventory_report` to use atomic upserts.

### Long Term (Low Priority)
5.  **Standardize Pagination:** Create a generic `fetch_all_pages` generator that yields batches of results, handling rate limits and pagination automatically.

