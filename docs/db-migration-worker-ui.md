# DB Migration Worker UI

This document describes the graphical interface for configuring and monitoring
MSSQL → Supabase migration workers.

Workers are admin-only tools designed for **append-only** tables. They
periodically fetch new rows from MSSQL based on a numeric primary key and append
those rows to a Supabase/Postgres table.

---

## Where to find it

1. Open **Admin → Data Migration**.
2. At the top you will see three tabs:
   - **MSSQL Explorer (legacy)** – browse legacy MSSQL tables.
   - **Dual-DB Migration Studio** – plan and run full 1:1 migrations
     (structure + data).
   - **Worker** – configure incremental workers that keep selected tables
     in sync.

Click the **Worker** tab to see all existing workers and create new ones.

---

## Worker list view

The Worker tab shows a table of all `db_migration_workers` rows.

Columns:

- **ID** – numeric worker ID.
- **Source** – MSSQL database + `schema.table`, e.g.
  `DB_A28F26_parts` and `dbo.tbl_ebay_fees`.
- **Target** – Supabase `schema.table`, e.g. `public.tbl_ebay_fees`.
- **PK column** – the numeric primary key used to detect new rows (e.g. `FeeID`).
- **Enabled** – checkbox that turns the worker on or off.
- **Interval (sec)** – how often the worker is allowed to run.
- **Notify OK** – whether to create a popup notification when a run succeeds.
- **Notify errors** – whether to create a popup notification when a run fails.
- **Last status** – last run status (`ok` / `error` / `null`), plus any error
  message.
- **Last run** – timestamps of the last run (start / finish).
- **Last counts** – last known source/target counts and how many rows were
  inserted in the last run.
- **Actions** – **Run once now** button to trigger an immediate incremental
  run.

At the top right there is a **New worker** button that opens a dialog to create
a new worker.

---

## Creating a new worker

Click **New worker** to open the **Create migration worker** dialog.

Fields:

- **MSSQL database** – database name, e.g. `DB_A28F26_parts`.
- **MSSQL schema** – typically `dbo`.
- **MSSQL table** – source table name, e.g. `tbl_ebay_fees`.
- **Supabase target table** – name of the target Postgres table,
  e.g. `tbl_ebay_fees`.
- **Supabase schema** – typically `public`.
- **Primary key column (optional)** – name of the numeric, monotonically
  increasing column used to detect new rows (e.g. `FeeID`). If left blank,
  the backend attempts to auto-detect a **single-column primary key** in the
  MSSQL table.
- **Run every (seconds)** – global interval between worker cycles
  (e.g. `300` for every 5 minutes).
- **Notify OK** – if enabled, create a popup task/notification for each
  successful run.
- **Notify errors** – if enabled, create a popup task/notification when a run
  fails.
- **Run initial catch-up immediately** – if checked, the UI will trigger a
  `run-once` call for the new worker right after it is created to catch up any
  existing "tail" of data.

Behavior on submit:

1. The UI calls `POST /api/admin/db-migration/worker/upsert` with the data.
2. The backend:
   - Validates that the Supabase target table exists.
   - Auto-detects a single-column MSSQL PK if `pk_column` is omitted.
   - Inserts or updates the `db_migration_workers` row.
3. If **Run initial catch-up immediately** is checked, the UI then calls
   `POST /api/admin/db-migration/worker/run-once` for the new worker.
4. The worker list is refreshed so you can see the new worker and its
   last-run status.

---

## What the worker actually does

For each enabled worker, the background `db_migration_workers` loop and the
manual **Run once now** action share the same logic:

1. In Supabase, read the current `MAX(pk_column)` from the target table.
2. In MSSQL, select rows from the source table where
   `pk_column > MAX(pk_column)` using batched paging.
3. Insert those rows into the Supabase target table using
   `INSERT ... ON CONFLICT(pk_column) DO NOTHING`.
4. Update the worker row with:
   - `last_run_started_at` / `last_run_finished_at`
   - `last_run_status`
   - `last_source_row_count`, `last_target_row_count`
   - `last_inserted_count`
   - `last_max_pk_source`, `last_max_pk_target`.

This makes each run **idempotent**:

- If a run fails halfway through, already-inserted rows stay in Supabase.
- The next run recomputes `MAX(pk_column)` in Supabase and continues from
  there, skipping duplicates thanks to the `ON CONFLICT` clause.

> Note: workers treat tables as **append-only**. Updates or deletes of old
> rows are not propagated. If your source table can mutate older rows,
> consider using a different migration strategy.

---

## Typical flow for a large table

Example: `dbo.tbl_ebay_fees → public.tbl_ebay_fees`.

1. Use **Dual-DB Migration Studio** to perform an initial full 1:1 migration.
2. Switch to the **Worker** tab.
3. Click **New worker** and fill in:
   - MSSQL database: `DB_A28F26_parts`
   - MSSQL schema: `dbo`
   - MSSQL table: `tbl_ebay_fees`
   - Supabase schema: `public`
   - Supabase target table: `tbl_ebay_fees`
   - PK column: `FeeID` (or leave blank to auto-detect)
   - Run every: `300` seconds
   - Enable **Run initial catch-up immediately**.
4. After saving, the initial run will add any rows that were inserted into
   MSSQL after the first migration but before the worker was created.
5. From that point on, the background loop will keep pulling new `tbl_ebay_fees`
   rows into Supabase every few minutes.

---

## Error handling and limitations

- If the backend cannot auto-detect a single-column primary key, worker
  creation fails with a clear error; you need to provide `pk_column`
  explicitly.
- If the target Supabase table does not exist, the worker cannot be created.
  Run a full migration first (1:1 or via the JSON console).
- Workers do not handle UPDATE/DELETE operations in MSSQL; they only insert
  new rows.
- MSSQL always remains read-only; all writes are done in Supabase.

You can always disable a worker via the **Enabled** checkbox in the list if you
want to pause incremental syncing without deleting the configuration.