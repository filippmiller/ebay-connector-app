# Admin Workers: Inventory MV Refresh

This document describes how the **Workers** admin page manages background workers, starting with the **Inventory MV Refresh** worker used by the Inventory V3 grid.

## 1. Purpose of the Workers Page

The Admin → **Workers** page is a small command center for long-running background processes. It currently exposes:

- eBay workers and token refresh loops (existing functionality), and
- a new **Inventory MV Refresh** worker card for refreshing inventory materialized views.

The goal is to:

- See whether key workers are running and healthy.
- Toggle automatic loops on/off when doing maintenance.
- Adjust worker intervals without redeploying code.
- Trigger "run once now" actions on demand for debugging.

The page is designed so additional workers (e.g. eBay token refresh, log cleanup) can be added later using the same patterns.

## 2. Inventory MV Refresh Worker

### 2.1. What It Does

The Inventory MV Refresh worker updates the materialized views that power the Inventory V3 grid SKU/ItemID counters:

- `public.mv_tbl_parts_inventory_sku_counts`
- `public.mv_tbl_parts_inventory_itemid_counts`

Each cycle runs the following SQL statements against the Supabase/Postgres database:

- `REFRESH MATERIALIZED VIEW CONCURRENTLY public.mv_tbl_parts_inventory_sku_counts`
- `REFRESH MATERIALIZED VIEW CONCURRENTLY public.mv_tbl_parts_inventory_itemid_counts`

The worker runs as a dedicated process (see `backend/Procfile`):

- `worker_inventory_mv_refresh: python -m app.workers.inventory_mv_refresh_worker`

### 2.2. Configuration Storage

Configuration and runtime status for this worker are stored in the existing `background_workers` table via the `BackgroundWorker` SQLAlchemy model (`app.models_sqlalchemy.ebay_workers.BackgroundWorker`).

For the Inventory MV Refresh worker, the row uses:

- `worker_name = 'inventory_mv_refresh'`

The following fields are relevant to this worker:

- `worker_name` (text, unique)
  - Stable key used by code, migrations, and the admin API.
- `display_name` (text, nullable)
  - Human-friendly name shown in the Workers UI (e.g. "Inventory MV Refresh").
- `description` (text, nullable)
  - Short description rendered in the UI.
- `enabled` (boolean, default `true`)
  - Whether the automatic loop should run refresh cycles.
- `interval_seconds` (integer, nullable, default 600 for this worker)
  - Sleep interval between cycles. If null or non-positive, the worker falls back to a default of 600 seconds (10 minutes).
- `last_started_at` (timestamptz, nullable)
  - Timestamp when the last cycle started.
- `last_finished_at` (timestamptz, nullable)
  - Timestamp when the last cycle finished.
- `last_status` (text, nullable)
  - High-level status for the last cycle (e.g. `running`, `success`, `error`).
- `last_error_message` (text, nullable)
  - Short error string from the last failed cycle (truncated to ~2000 chars).
- `runs_ok_in_row` / `runs_error_in_row` (integer, defaults 0)
  - Counters for consecutive successful/error cycles.

An Alembic migration (`backend/alembic/versions/20251209_add_inventory_mv_worker_settings.py`) adds the additional configuration fields to `background_workers` (`display_name`, `description`, `enabled`) and seeds a default row for `worker_name = 'inventory_mv_refresh'` with:

- `display_name = 'Inventory MV Refresh'`
- `description = 'Refreshes inventory materialized views used by the Inventory V3 grid (SKU/ItemID Active/Sold counters).'`
- `enabled = true`
- `interval_seconds = 600`

## 3. How the Worker Loop Uses the Configuration

The worker implementation lives in `backend/app/workers/inventory_mv_refresh_worker.py`.

### 3.1. Single-Cycle Helper

The function:

- `run_inventory_mv_refresh_once() -> tuple[bool, str | None]`

performs a **single refresh cycle** and updates the `BackgroundWorker` row:

1. Loads or creates the `BackgroundWorker` row for `worker_name = 'inventory_mv_refresh'`.
2. Sets `last_started_at` to now, `last_status = 'running'`, and clears `last_error_message`.
3. Executes both `REFRESH MATERIALIZED VIEW` statements inside a transaction.
4. On success:
   - Sets `last_finished_at` to now.
   - Sets `last_status = 'success'`.
   - Clears `last_error_message`.
   - Increments `runs_ok_in_row` and resets `runs_error_in_row`.
5. On failure:
   - Sets `last_finished_at` to now.
   - Sets `last_status = 'error'`.
   - Writes a short error string to `last_error_message`.
   - Increments `runs_error_in_row`.

The helper always attempts a refresh regardless of the `enabled` flag; it is used by both the automatic loop and the admin "Run now" endpoint.

### 3.2. Long-Running Loop

The main loop function is:

- `async def run_inventory_mv_refresh_loop() -> None`

Behavior on each iteration:

1. Opens a DB session and loads the `BackgroundWorker` row for `worker_name = 'inventory_mv_refresh'`.
   - If the row does not exist, it is created with sensible defaults (display name, description, `enabled = true`, `interval_seconds = 600`).
2. Reads `enabled` and `interval_seconds` from the row:
   - If `interval_seconds` is `NULL` or <= 0, falls back to `DEFAULT_INTERVAL_SECONDS = 600`.
3. If `enabled = false`:
   - Logs a message like:
     - `"[inventory-mv-refresh] Worker disabled in DB; sleeping <interval>s without running"`.
   - Sleeps for `interval` seconds and **skips** the refresh logic.
4. If `enabled = true`:
   - Calls `run_inventory_mv_refresh_once()`.
   - Logs whether the cycle completed successfully or with an error.
   - Sleeps for `interval` seconds before the next cycle.

There are no hardcoded time-of-day rules anymore; scheduling is controlled entirely by `interval_seconds` in the DB.

## 4. Admin API Endpoints

A dedicated router `backend/app/routers/admin_workers.py` exposes admin-only endpoints under `/api/admin/workers`.

### 4.1. GET /api/admin/workers/inventory-mv-refresh

Returns the current configuration and last-run info for the worker.

Response shape:

```json
{
  "worker_key": "inventory_mv_refresh",
  "display_name": "Inventory MV Refresh",
  "description": "Refreshes inventory materialized views used by the Inventory V3 grid (SKU/ItemID Active/Sold counters).",
  "enabled": true,
  "interval_seconds": 600,
  "last_run_at": "2025-12-09T10:00:00Z",
  "last_run_status": "success",
  "last_run_error": null
}
```

Notes:

- `last_run_at` is derived from `last_finished_at` (or `last_started_at` if `last_finished_at` is null).
- All timestamps are returned in ISO8601 UTC.

### 4.2. PUT /api/admin/workers/inventory-mv-refresh

Updates configuration for the worker.

Request body (all fields optional):

```json
{
  "enabled": true,
  "interval_seconds": 600
}
```

Rules:

- If `interval_seconds` is provided, it must be a positive integer.
- If `enabled` is provided, it toggles the automatic loop.
- The endpoint always returns the updated worker DTO (same shape as GET).

### 4.3. POST /api/admin/workers/inventory-mv-refresh/run-once

Triggers a **single** refresh cycle by calling `run_inventory_mv_refresh_once()`.

Response on success:

```json
{ "status": "success" }
```

Response on failure:

```json
{ "status": "error", "message": "short error message" }
```

If an unexpected exception occurs in the endpoint itself, it returns HTTP 500 with `detail = "run_once_failed"`.

All endpoints are protected by the existing `admin_required` dependency and share the `/api/admin` namespace.

## 5. Admin Workers Page (Frontend)

The UI lives in `frontend/src/pages/AdminWorkersPage.tsx` and is accessible via:

- Route: `/admin/workers`
- Navigation: Admin → **eBay Workers** card (existing) and more generally the Admin dashboard card labeled **eBay Workers**.

### 5.1. Inventory MV Worker Card

The page now includes a **Global Background Workers** section with an **Inventory MV Refresh** card that shows:

- Name and description from the backend (`display_name`, `description`).
- A toggle (Radix `Switch`) bound to `enabled`.
- A numeric `interval_seconds` input (rendered in seconds, with an approximate minutes hint).
- Read-only fields for:
  - `Last run` (formatted local time from `last_run_at`).
  - `status` (from `last_run_status`).
  - `Last error` (from `last_run_error`, truncated in the UI).
- A **Run now** button that calls the `/run-once` endpoint.

Data is loaded with a new API client in `frontend/src/api/ebay.ts`:

- `ebayApi.getInventoryMvWorker()` → GET.
- `ebayApi.updateInventoryMvWorker({ enabled?, interval_seconds? })` → PUT.
- `ebayApi.runInventoryMvWorkerOnce()` → POST /run-once.

The UI is structured so additional workers can be added later by expanding the `AdminWorkerDto` list and rendering more cards.

## 6. How to Add New Workers Later

To add another background worker (e.g. eBay token refresh V2, log cleanup), follow this pattern:

1. **Model / DB**
   - Reuse the existing `BackgroundWorker` model and `background_workers` table.
   - Choose a stable `worker_name` key (e.g. `"log_cleanup"`).
   - Optionally create a migration that seeds a row with default values for the new worker (display name, description, enabled, interval_seconds).

2. **Worker Implementation**
   - Implement the worker loop in `backend/app/workers/<your_worker>.py`.
   - Introduce a helper like `run_<your_worker>_once()` that performs one cycle and updates `BackgroundWorker` fields (`last_started_at`, `last_finished_at`, `last_status`, `last_error_message`, counters).
   - In the main loop, on each iteration:
     - Load the `BackgroundWorker` row by `worker_name`.
     - If missing, create it with defaults.
     - Read `enabled` and `interval_seconds`.
     - If disabled → log and sleep.
     - If enabled → call the run-once helper and sleep for `interval_seconds`.

3. **Admin API**
   - Extend `backend/app/routers/admin_workers.py` with new endpoints, e.g.:
     - `GET /api/admin/workers/<your-worker>`
     - `PUT /api/admin/workers/<your-worker>`
     - `POST /api/admin/workers/<your-worker>/run-once`
   - Reuse the same DTO shape (`worker_key`, `display_name`, `enabled`, `interval_seconds`, last-run fields).

4. **Frontend**
   - Add corresponding client functions in `frontend/src/api/ebay.ts` (or a dedicated admin workers API module).
   - Update `AdminWorkersPage` to render an additional card in the **Global Background Workers** section using the new API.

By following this pattern, all long-running workers share a single, minimal configuration and status table and a consistent admin experience.

## 7. Verification Checklist

Before considering changes complete, verify the following:

### 7.1. DB Schema

- Run Alembic migrations (or start the backend so it runs migrations on startup).
- Confirm that `background_workers` has the columns:
  - `display_name`, `description`, `enabled`, `interval_seconds`, `last_started_at`, `last_finished_at`, `last_status`, `last_error_message`, `runs_ok_in_row`, `runs_error_in_row`.
- Confirm there is a row with `worker_name = 'inventory_mv_refresh'` and sensible defaults (enabled=true, interval_seconds=600).

### 7.2. Worker Loop

- Start the dedicated worker process locally or in staging:
  - `cd backend`
  - `python -m app.workers.inventory_mv_refresh_worker`
- In the DB, set `enabled = true` and `interval_seconds = 30` for `inventory_mv_refresh`.
- Observe logs:
  - The worker runs refresh logic approximately every 30 seconds.
  - `last_finished_at`, `last_status`, `last_error_message` are updated appropriately.
- Set `enabled = false` and confirm:
  - Logs show that the worker is disabled and only sleeps.
  - No `REFRESH MATERIALIZED VIEW` statements are executed while disabled.

### 7.3. Admin API

- Call `GET /api/admin/workers/inventory-mv-refresh` as an admin user and verify:
  - JSON reflects the DB row (worker_key, enabled, interval_seconds, last_run_* fields).
- Call `PUT /api/admin/workers/inventory-mv-refresh` with different `enabled` and `interval_seconds` values and confirm the DB row is updated.
- Call `POST /api/admin/workers/inventory-mv-refresh/run-once` and verify:
  - The materialized views are refreshed.
  - `last_run_at` / `last_run_status` / `last_run_error` are updated.

### 7.4. Frontend

- Open `/admin/workers` in the browser as an admin.
- Confirm:
  - The **Global Background Workers** section shows an **Inventory MV Refresh** card.
  - The card loads current values from the backend.
  - Toggling the switch and changing the interval updates the backend (confirmed via subsequent GET or by inspecting the DB row).
  - Clicking **Run now** triggers a single refresh cycle and the last-run info is updated.

### 7.5. Docs

- Open this file (`docs/admin-workers-inventory-mv-refresh-20251209.md`) and confirm it accurately reflects:
  - The Workers page behavior.
  - How the Inventory MV worker uses `background_workers` configuration.
  - How to add new workers in the future.
