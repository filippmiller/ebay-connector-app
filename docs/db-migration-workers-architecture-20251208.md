# DB migration workers – behaviour, observability, and controls (2025-12-08)

This document describes the behaviour and UI of the MSSQL → Supabase migration
workers after the 2025-12-08 refactor.

The goals of the changes were:

- Fix confusing timestamps where `Last run` looked like a single run lasting
  many days.
- Make it clear that counts in the worker grid are **snapshots** from the last
  successful run, and also expose **live** counts for the source and target
  tables.
- Persist worker error state so the UI reflects the last failed attempt.
- Add edit/delete controls for workers and clarify what it means to pause a
  worker vs. delete it.
- Document the background loop that actually runs workers every N seconds.

---

## Data model recap

Workers are stored in the `db_migration_workers` Postgres table. Relevant
columns used by the UI:

- Identity and configuration
  - `id` – numeric worker id.
  - `source_database` – MSSQL database name.
  - `source_schema` – MSSQL schema (typically `dbo`).
  - `source_table` – MSSQL table name.
  - `target_schema` – Supabase/Postgres schema (typically `public`).
  - `target_table` – Supabase/Postgres table name.
  - `pk_column` – numeric, monotonically increasing primary key used for
    incremental sync (e.g. `ID`, `FeeID`).
  - `worker_enabled` – boolean flag; when `false`, the background loop skips
    this worker.
  - `interval_seconds` – minimum time between background runs for this worker.
  - `owner_user_id` – admin user who owns this worker configuration.
  - `notify_on_success` / `notify_on_error` – whether to create popup
    notifications for success/failure.

- Last run snapshot
  - `last_run_started_at` – timestamp when the **last successful run** started.
  - `last_run_finished_at` – timestamp when the **last successful run**
    finished, or when the last failed run finished if we could persist the
    error.
  - `last_run_status` – `'ok'` or `'error'` for the last attempt that actually
    wrote state into this row.
  - `last_error` – error message for the last failed run (if any).
  - `last_source_row_count` – `COUNT(*)` on MSSQL at the time of the last
    successful run.
  - `last_target_row_count` – `COUNT(*)` on Supabase at the time of the last
    successful run.
  - `last_inserted_count` – how many rows were inserted in the last successful
    run.
  - `last_max_pk_source` – maximum PK observed on MSSQL during the last
    successful run.
  - `last_max_pk_target` – maximum PK observed on Supabase after the last
    successful run.

These snapshot fields are **not live**; they are updated only after a successful
incremental run (or, in the case of errors, as part of the failure handling).

---

## Incremental worker algorithm

Both the admin API (`/worker/run-once`) and the background loop share the same
core helper: `run_worker_incremental_sync`.

For a given worker (one MSSQL table and one Supabase table with compatible
schema, plus a numeric PK):

1. Resolve the PK column name on Supabase side case-insensitively.
2. In Supabase, compute `target_max_pk = MAX(pk_column)` (or `0` if table is
   empty).
3. In MSSQL, select rows from the source table where `pk_column > target_max_pk`
   using batched paging with `ORDER BY pk_column OFFSET :offset FETCH NEXT
   :limit`.
4. Insert those rows into the Supabase target table, mapping columns by
   case-insensitive name and using `ON CONFLICT(pk) DO NOTHING` when the PK is
   backed by a UNIQUE/PRIMARY KEY constraint. This makes the process idempotent.
5. After all batches:
   - Recompute `MAX(pk)` on the target.
   - Compute `COUNT(*)` on source and target.
   - If a `worker_id` was supplied, update the corresponding
     `db_migration_workers` row with a fresh snapshot.

### Timestamp semantics (fixed)

Previously `last_run_started_at` was only set the first time a worker ran and
was never updated again. This made the UI look like the worker had been running
for many days, and the background loop used it for interval calculations.

Now:

- At the beginning of each incremental run, `run_worker_incremental_sync`
  records a `started_at` timestamp.
- When the run finishes successfully and a `worker_id` is provided, the helper
  executes a single `UPDATE db_migration_workers` that sets:
  - `last_run_started_at = :started_at` (per-run value),
  - `last_run_finished_at = NOW()`,
  - `last_run_status = 'ok'`,
  - clears `last_error`, and updates snapshot counts and PKs.

This means in the UI we can reliably compute:

- `Last run finished`: `last_run_finished_at`.
- `duration`: `last_run_finished_at - last_run_started_at` in seconds.

### Error handling semantics (fixed)

Previously, when an incremental run failed:

- The background loop logged the error but did not update
  `db_migration_workers`.
- The admin `/worker/run-once` endpoint simply propagated the exception.
- As a result, `last_run_status` and `last_error` could still show the previous
  successful run even though the last attempt actually failed.

Now:

- The background loop wraps each worker run in `try/except`. On failure it:
  - logs the error; and
  - **best-effort** updates the worker row with:
    - `last_run_finished_at = NOW()`,
    - `last_run_status = 'error'`,
    - `last_error = <truncated message>`,
    - `updated_at = NOW()`.
- The admin `/worker/run-once` endpoint does the same in its own `try/except`.

If the error-update itself fails (e.g. transient DB problem), we log that but do
not crash the process.

The UI now reads `last_run_status` and `last_error` directly and always reflects
**the last attempt we know about**, whether it succeeded or failed.

---

## Background loop and interval gating

A separate process runs `backend/app/workers/db_migration_worker.py`:

- `run_db_migration_workers_loop(interval_seconds: int = 60)` is an infinite
  loop that:
  1. Calls `run_db_migration_workers_once()`.
  2. Sleeps `interval_seconds` seconds.

- `run_db_migration_workers_once(max_workers: int = 20)` loads up to
  `max_workers` rows from `db_migration_workers` where `worker_enabled = TRUE`.

### Per-worker interval (fixed)

Previously the loop used `last_run_started_at` for interval gating, but because
that field was never updated after the first run, the gating effectively
stopped working.

Now the loop fetches both `last_run_started_at` and `last_run_finished_at` and
uses:

- `anchor = last_run_finished_at or last_run_started_at`.
- If `anchor` is not `NULL` and `now - anchor < interval_seconds`, the worker
  is skipped for this cycle.

This means:

- If the loop heartbeat is every 60 seconds and `interval_seconds` for a worker
  is 300, that worker will run roughly every 5 minutes.
- If a run fails and we manage to persist the error, `last_run_finished_at` is
  still set and interval gating works the same way.

### Enabling / pausing a worker

- `worker_enabled = TRUE` means the background loop **is allowed** to run this
  worker according to `interval_seconds`.
- `worker_enabled = FALSE` means the background loop will completely skip this
  worker.
- Manual runs via the admin UI (`Run once now`) do **not** depend on
  `worker_enabled`.

In the UI, this is surfaced as a checkbox labelled **Enabled** with a note
explaining that disabling pauses the background loop but manual runs still work.

### Infrastructure note

To get continuous incremental syncing in production you must ensure the
background loop process is actually running, for example:

- As a separate Railway worker process:
  - Command: `python -m app.workers.db_migration_worker`.
  - Environment: same DB and MSSQL settings as the main app.
- Or via a process manager (e.g. systemd, PM2, etc.) running the same module.

If the loop is not running, the Admin → Data Migration → Worker page still lets
admins run manual incremental passes, but nothing will happen automatically
"каждые 5 минут".

---

## Worker admin API

All endpoints live under the FastAPI router prefix `/api/admin/db-migration`.

### List workers

- `GET /worker/state`
- Returns the raw `db_migration_workers` rows mapped to the
  `MigrationWorkerState` model.
- Used by the Worker tab to populate the main grid.

### Create / update a worker

- `POST /worker/upsert`
- Request model: `MigrationWorkerConfig`.
- Behaviour:
  - If `id` is provided and exists, updates the row.
  - Otherwise inserts a new row.
  - Validates that the target Supabase table exists.
  - If `pk_column` is omitted, attempts to auto-detect a single-column MSSQL PK.
  - Defaults `owner_user_id` to the current admin if not provided.

The UI uses this endpoint for both:

- Creating new workers ("Create worker" dialog).
- Editing existing workers ("Edit" flow described below).

### Delete a worker (new)

- `DELETE /worker/{worker_id}`
- Behaviour:
  - Deletes the corresponding row from `db_migration_workers`.
  - If no row was deleted, returns 404.
- Does **not** change or delete any data in MSSQL or Supabase; it only removes
  the configuration.

The Worker grid exposes a **Delete** action that calls this endpoint after a
confirmation dialog.

### Preview (live stats for a single worker)

- `POST /worker/preview`
- Request model: `MigrationWorkerRunOnceRequest` (either `id` or full identity).
- Response model: `MigrationWorkerPreview`.

This endpoint:

1. Loads the worker row.
2. Computes current MSSQL `COUNT(*)` and `MAX(pk)`.
3. Computes current Supabase `COUNT(*)` and `MAX(pk)`.
4. Computes `rows_to_copy` = number of rows in MSSQL where
   `pk > target_max_pk`.

The Worker UI uses this endpoint in a confirmation modal before starting a
manual `Run once` for a worker.

### Live stats for all workers (new)

- `GET /worker/live-stats`
- Response model: `List[MigrationWorkerLiveStats]`.
- Each entry is the same shape as `MigrationWorkerPreview` plus an `id` field.

For each row in `db_migration_workers` the endpoint:

1. Resolves the PK column on Supabase side.
2. Computes current Supabase `COUNT(*)` and `MAX(pk)`.
3. Computes current MSSQL `COUNT(*)`, `MAX(pk)`, and `rows_to_copy` from the
   current target `MAX(pk)`.

This endpoint is **heavier** than `/worker/state` and is intended for occasional
refreshes in the UI (e.g. once per minute), not tight polling.

### Run once (manual incremental pass with error persistence)

- `POST /worker/run-once`
- Request model: `MigrationWorkerRunOnceRequest`.
- Behaviour:
  1. Loads the worker row (by `id` or composite identity).
  2. Calls `run_worker_incremental_sync` with a `worker_id` so that on success
     the helper updates the snapshot fields.
  3. If `run_worker_incremental_sync` raises, it:
     - runs a best-effort `UPDATE` with `last_run_status='error'`,
       `last_error=<message>`, and `last_run_finished_at = NOW()`;
     - re-raises the exception so the caller sees an HTTP error.

The Worker grid uses this endpoint indirectly via the "Run once now" button and
its confirmation modal.

---

## Worker UI (Admin → Data Migration → Worker tab)

### Overview

The Worker tab is the main console for configuring and monitoring
`db_migration_workers`.

Columns in the grid (after the refactor):

- **ID** – worker id.
- **Source** – `source_database` on the first line, `schema.table` below.
- **Target** – `target_schema.target_table`.
- **PK column** – `pk_column` used for incremental sync.
- **Enabled** – checkbox bound to `worker_enabled`.
- **Interval (sec)** – editable `interval_seconds`.
- **Notify OK / Notify errors** – checkboxes bound to notification flags.
- **Last status** – `last_run_status` and optional `last_error`.
- **Last run** – derived from timestamps (see below).
- **Last run snapshot** – debug counts from the last successful run.
- **Actions** – `Run once now`, `Edit`, and `Delete` actions.

At the top of the tab there is a short description explaining that automatic
runs depend on the background `db_migration_worker` loop, while this page only
configures workers and triggers manual runs.

### Last run column (fixed)

The **Last run** column now focuses on the last **finished** run:

- Primary line:
  - `finish: 2025-12-08 16:35:05` – formatted `last_run_finished_at`.
- Secondary line (when both timestamps are present):
  - `duration: 12s` – difference between `last_run_finished_at` and
    `last_run_started_at` converted to seconds.

We intentionally no longer show the stale `start` timestamp by itself to avoid
any impression of "worker работал 10 дней подряд".

### Last run snapshot column (renamed, clarified)

The former **Last counts** column has been renamed to **Last run snapshot**.

The cell renders:

- A small label: `as of last run:` if any snapshot fields are present.
- `src: <last_source_row_count>` if available.
- `tgt: <last_target_row_count>` if available.
- `+<last_inserted_count> rows` if available.

This makes it explicit that these numbers reflect **how things looked right
after the last successful incremental run**, not the current live state.

### Live stats overlay (new)

Below the snapshot, if live stats are available for a worker (from
`/worker/live-stats`), the UI shows:

- `now src: <live source_row_count>, tgt: <live target_row_count>`.
- A delta line with semantics:
  - `Δ: 0 (up to date)` – when source and target counts match.
  - `Δ: N rows behind` – when source has more rows than target.
  - `Δ: -N (target ahead)` – if for some reason target has more rows than
    source.

Live stats are fetched:

- Once on mount of the Worker tab.
- Every 60 seconds thereafter.

If the live-stats request fails, the grid keeps working with the snapshot data
and logs a warning in the browser console; no error banner is shown to the
user.

### Enabled, interval, and notifications

The Enabled, Interval, and Notify columns continue to use `POST
/worker/upsert` under the hood:

- Toggling **Enabled** updates `worker_enabled`. The tooltip/text clarifies that
  this only affects the background loop; manual runs are still allowed.
- **Interval (sec)** is an editable numeric input; changing it sends an upsert
  with the updated `interval_seconds`.
- **Notify OK/Notify errors** map to `notify_on_success` and `notify_on_error`.

### Actions: Run once, Edit, Delete (new)

Each row exposes three actions:

1. **Run once now**
   - Opens a confirmation dialog that calls `/worker/preview` to show how many
     rows would be copied and current PK bounds.
   - On confirmation, the UI repeatedly calls `/worker/run-once` until a pass
     inserts `0` rows or a safety iteration limit is reached, updating the
     worker list between passes.

2. **Edit** (new)
   - Opens the existing Create Worker dialog in **edit mode** with fields
     pre-filled from the selected worker:
     - MSSQL database, schema, table.
     - Supabase schema and target table.
     - PK column.
     - Interval seconds.
   - On submit, sends `POST /worker/upsert` with `id` set to the worker id.
   - When editing, the "Run initial catch-up immediately" checkbox is ignored;
     we only use that for **new** workers.

3. **Delete** (new)
   - Shows a confirmation prompt clarifying that only the configuration will be
     deleted (no data changes in MSSQL or Supabase).
   - On confirm, sends `DELETE /worker/{id}` and then reloads the worker list.

### In-page terminal log

At the bottom of the tab there is a simple terminal-style log that aggregates
per-worker changes over time since the page was loaded.

- The log is derived from snapshots: when a worker’s
  `(last_run_finished_at, last_inserted_count, last_run_status)` triple changes,
  a new line is appended summarising the run:
  - Timestamp (from `last_run_finished_at` or `last_run_started_at`).
  - Worker id and source → target.
  - Inserted rows and source/target counts.
  - `max_pk` values on source and target.
- The log is truncated to the last ~200 lines to avoid unbounded growth.

This gives a quick at-a-glance history of recent runs without having to inspect
raw logs.

---

## Operator checklist

### To configure continuous incremental sync for a table

1. Ensure the Supabase target table exists and is structurally compatible.
   Often this is created by a prior 1:1 migration.
2. Open **Admin → Data Migration → Worker**.
3. Click **New worker**.
4. In the dialog:
   - MSSQL database: e.g. `DB_A28F26_parts`.
   - MSSQL schema: typically `dbo`.
   - MSSQL table: select the source table (e.g. `tbl_ebay_fees`).
   - Supabase target table: select the corresponding table
     (e.g. `public.tbl_ebay_fees`).
   - Supabase schema: usually `public`.
   - Primary key column: specify a numeric PK (e.g. `FeeID`) or leave blank to
     auto-detect.
   - Run every (seconds): e.g. `300` for every 5 minutes.
   - Optionally check **Run initial catch-up immediately**.
5. Submit the dialog.
6. Ensure the background `db_migration_worker` loop is running in the
   environment so that `Enabled` and `interval_seconds` actually have effect.

### To pause a worker without deleting it

1. In the Worker grid, uncheck **Enabled** for that worker.
2. The background loop will skip it until you re-enable it.
3. You can still run manual `Run once now` operations while it is disabled.

### To delete a worker configuration

1. In the Worker grid, click **Delete** on the row.
2. Confirm the prompt.
3. The `db_migration_workers` row is removed; no data is changed in MSSQL or
   Supabase.

If you later need a similar worker, you can recreate it via the **New worker**
flow or by editing another worker.

---

## Summary of key behavioural fixes

- `last_run_started_at` is now updated **for every successful run**, and the
  background loop uses `last_run_finished_at` (or `last_run_started_at` as
  fallback) for interval gating.
- Worker error state (`last_run_status`, `last_error`, `last_run_finished_at`)
  is persisted on both manual and background failures.
- The Worker grid clearly separates **Last run snapshot** (snapshot at the time
  of the last run) from **live stats** (current MSSQL/Supabase counts and
  deltas).
- Edit/Delete actions for workers are available directly in the UI, with the
  create dialog reused as an edit form.
- The relationship between the Worker UI and the background
  `db_migration_worker` loop is explicitly documented, so it is clear how
  "каждые 5 минут" is actually achieved in production.
