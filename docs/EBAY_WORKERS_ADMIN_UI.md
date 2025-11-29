# Admin UI for eBay workers

This document explains how the **Admin → eBay Workers** page is structured and
how it reflects the workers behaviour implemented in the backend.

The goal of this UI is to give a clear, visual control panel for all eBay
workers for a given account, including:

- Enable/disable switches per worker and globally.
- One-click **Run now** and **Run ALL workers** actions.
- A readable summary of last runs, health state, primary keys and schedule.
- Direct access to detailed logs via the workers SyncTerminal.

---

## Page layout

- **Location:** Admin → “eBay Workers” tile.
- **Account selector:** at the top, you choose one eBay account. The rest of the
  page operates on that account only.
- **Workers command control:** main grid with one row per worker family:
  - API: `active_inventory`, `buyer`, `cases`, `finances`, `inquiries`,
    `messages`, `offers`, `orders`, `transactions`.
  - Status (enable/disable, coloured dot, last run summary, last error).
  - Last run (timestamps and status).
  - Cursor (type and current value from `EbaySyncState`).
  - Primary key (natural deduplication key string returned by backend).
  - Actions (Turn on/off, Run now, Details).
- **Schedule (next N hours):** simulated schedule grid based on
  `/ebay/workers/schedule`.
- **Workers terminal:** shared SyncTerminal at the bottom that can attach to any
  worker run and stream detailed HTTP and progress logs.

---

## Global controls

At the top-right of “Workers command control”:

- **Global toggle:**
  - Button text:
    - When workers are globally enabled: “BIG RED BUTTON: TURN OFF ALL JOBS”.
    - When global toggle is off: “Enable all workers”.
  - Backend: `/ebay/workers/global-toggle` and `EbayWorkerGlobalConfig`.
  - Effect: when OFF, `/run` and `/run-all` will skip real work and return
    `status="skipped", reason="workers_disabled"`.

- **Run ALL workers**:
  - Opens a confirmation modal. It shows:
    - Selected account (username / house name / eBay user id).
    - List of **enabled** workers that will be triggered.
    - Text (in Russian) explaining that all enabled workers will be started and
      that already-running workers will be marked as `already_running`.
  - On confirm, calls `POST /ebay/workers/run-all` with `account_id`.
  - The modal shows a **Run-all result** table with columns:
    - API
    - Status (`started`, `skipped`, `error`)
    - Run ID / Reason (e.g. `run_id: ...`, `disabled`, `workers_disabled`,
      `already_running`, `not_started`, or an error message).

### Run ALL stagger behaviour

Backend `/ebay/workers/run-all` starts workers **sequentially**. To avoid a
burst of simultaneous heavy API calls and potential 401/502 spikes, it now:

- Iterates workers with `enumerate(ensured_families)`.
- Before starting each worker after the first, awaits a small pause:
  - `RUN_ALL_STAGGER_SECONDS = 2` seconds.

This means a Run ALL call will take slightly longer overall, but each worker
starts a couple of seconds apart, which is friendlier to both eBay and our own
infrastructure.

### Run ALL and SyncTerminal dropdown

When the Run ALL request returns, the frontend immediately pulls out all
results with `status="started"` and a `run_id` and injects them into the
`recentRuns` list with synthetic entries:

- `id`: run_id returned by `/run-all`.
- `api_family`: worker name (orders, finances, etc.).
- `status`: `running`.
- `started_at`: current timestamp.
- `finished_at`: `null`.
- `summary`: `null` (real summary will be filled later by `/runs`).

Because of this, the **“Select worker run”** dropdown above the terminal shows
all newly-started worker runs immediately after Run ALL, without waiting for the
next `/ebay/workers/runs` refresh.

The existing logic that auto-attaches the terminal to the most recent run still
works on top of this behaviour.

---

## Per‑worker row: API and info tooltip

The API column now shows:

- The worker family name (e.g. `orders`, `transactions`, `messages`).
- A small circular **info icon** (`i`) to the right of the name.

Hovering the icon (no click needed) displays a tooltip with:

- **Source:** human-readable API name.
- **Endpoint:** main eBay API path used.
- **Destination:** main Postgres table(s) where data is written.
- **Key columns:** natural identifier(s) used for deduplication.

Examples (shortened):

- **orders**
  - Source: “Orders – Fulfillment API”
  - Endpoint: `GET /sell/fulfillment/v1/order`
  - Destination: `ebay_orders (+ ebay_order_line_items)`
  - Key columns: `(order_id, user_id)`; line items keyed by
    `(order_id, line_item_id)`.

- **transactions**
  - Source: “Transactions – Finances API”
  - Endpoint: `GET /sell/finances/v1/transaction`
  - Destination: `ebay_transactions`
  - Key columns: `(transaction_id, user_id)`.

- **finances**
  - Source: “Finances – Finances API”
  - Endpoint: `GET /sell/finances/v1/transaction`
  - Destination: `ebay_finances_transactions (+ ebay_finances_fees)`
  - Key columns: `(ebay_account_id, transaction_id)`.

- **messages**
  - Source: “Messages – Trading API”
  - Endpoint: `GetMyMessages`
  - Destination: `ebay_messages`
  - Key columns: `message_id (per ebay_account_id, user_id)`.

- **cases**
  - Source: “Post-Order – Case Management API”
  - Endpoint: `GET /post-order/v2/casemanagement/search`
  - Destination: `ebay_cases`
  - Key columns: `(case_id, user_id)`.

- **inquiries**
  - Source: “Post-Order – Inquiry API”
  - Endpoint: `GET /post-order/v2/inquiry/search`
  - Destination: `ebay_inquiries`
  - Key columns: `(inquiry_id, user_id)`.

- **offers**
  - Source: “Offers – Inventory API”
  - Endpoint: `GET /sell/inventory/v1/offer?sku=…`
  - Destination: `ebay_offers (+ inventory)`
  - Key columns: `(offer_id, user_id)`; inventory keyed by `sku_code`.

- **buyer**
  - Source: “Buying – Trading API”
  - Endpoint: `GetMyeBayBuying`
  - Destination: `ebay_buyer`
  - Key columns: `(ebay_account_id, item_id, transaction_id, order_line_item_id)`.

- **active_inventory**
  - Source: “Active inventory – Trading API”
  - Endpoint: `GetMyeBaySelling (ActiveList)`
  - Destination: `ebay_active_inventory`
  - Key columns: `(ebay_account_id, sku, item_id)`.

This replaces the previous behaviour where only Orders and Transactions had long
inline descriptions directly in the table.

---

## Status column: dot + tooltip + summary

Each worker row shows a **coloured dot** and an **Enabled / Disabled** pill.
The dot color is computed from the worker state and has a descriptive tooltip
(`title=` attribute) when you hover it:

- **Green**:
  - Condition: worker is enabled, no `last_error`, and `last_run_status` is
    `"completed"`.
  - Tooltip: “Healthy: last run completed without errors.”

- **Yellow**:
  - Condition: worker is enabled and `last_run_status === 'running'`.
  - Tooltip: “Running: worker is currently in progress.”

- **Red**:
  - Condition: `last_error` present or `last_run_status === 'error'`.
  - Tooltip: “Error: last run failed; see 'Last error' for details.”

- **Grey**:
  - Condition: worker is disabled or has never run.
  - Tooltip: if disabled: “Disabled: worker will not run on schedule.”; if
    enabled but never run: “Idle: worker is enabled but has not run yet.”

Below the dot and pill, if `last_run_summary` is present, a short text line
shows:

- `Last run: fetched X, stored Y` (values from `summary.total_fetched` and
  `summary.total_stored`).

If `last_error` is set, an extra line “Last error: …” is displayed in red.

---

## Last run and cursor columns

- **Last run** column shows:
  - Started: ISO string from `last_run_started_at`.
  - Finished: ISO string from `last_run_finished_at`.
  - Status: `last_run_status` (`completed`, `running`, `error`, `cancelled`, …).

- **Cursor** column shows:
  - Type: `cursor_type` (currently unused/null for most workers; reserved for
    future advanced cursors).
  - Value: `cursor_value` ISO string from `EbaySyncState`, which is always the
    **end** of the last successful window (in UTC).

Cursor values are updated by the backend via `mark_sync_run_result` when a
worker run completes successfully.

---

## Primary key column

The **Primary key** column surfaces the `primary_dedup_key` string provided by
`/ebay/workers/config`. It contains a short textual representation of the
natural key used for deduplication in the database, e.g.:

- Orders: `(order_id, user_id)`.
- Transactions: `(transaction_id, user_id)`.
- Finances: `(ebay_account_id, transaction_id)`.
- Messages: `message_id (per ebay_account_id, user_id)`.
- Buyer: `(ebay_account_id, item_id, transaction_id, order_line_item_id)`.

The cell shows:

- A monospace line with the key expression.
- A tiny description: “Natural key from eBay data used to avoid duplicates when
  windows overlap.”

If no key is defined for a worker (future extensions), the cell shows `n/a`.

See `EBAY_WORKERS_DEDUP_KEYS_AND_UPSERTS.md` for the authoritative mapping
between workers, tables, and keys.

---

## Actions: Turn on/off, Run now, Details

- **Turn on / Turn off**:
  - Calls `POST /ebay/workers/config` with `{ api_family, enabled }`.
  - Updates `EbaySyncState.enabled` for that worker.

- **Run now**:
  - Calls `POST /ebay/workers/run` with the selected `api` and `account_id`.
  - If `status="started"` and a `run_id` is returned:
    - Sets this run as selected in `recentRuns`.
    - Attaches the SyncTerminal to the corresponding `sync_run_id`
      (resolved from worker logs/summary where possible).
  - If `status="skipped"` with an existing `run_id` (already running):
    - Attaches the terminal to the existing run instead of starting a new one.
  - If `status="error"`, surfaces the error message in the page-level error
    area at the top.

- **Details**:
  - Fetches the most recent runs for this worker via `/ebay/workers/runs`.
  - Selects the last run and calls `/ebay/workers/logs/{run_id}`.
  - Opens a modal showing:
    - A small **summary header** with API, status, window, and fetched/stored
      counts (from `run.summary`).
    - A raw JSON dump of the run and logs for debugging.
  - Also wires the SyncTerminal to the `sync_run_id` contained in the summary
    (if present).

---

## Schedule (next N hours)

The Schedule section calls `GET /ebay/workers/schedule` and renders the
projected windows for each worker.

Key points:

- **Interval:** fixed 5 minutes between simulated runs.
- **Window computation:**
  - The backend simulates the same logic used by runtime workers:
    - If a `cursor_value` exists and parses, each future window is
      `[cursor - 30 minutes, run_at]`, and the cursor then advances to
      `window_to`.
    - If there is **no cursor yet**, the simulation treats the cursor as
      `run_at` and still uses a 30‑minute overlap-only window.
  - The old behaviour that showed a 90‑day backfill window has been removed for
    eBay workers.

- **Active inventory:**
  - This worker is snapshot-based (no true time window). In the schedule, each
    row now shows:
    - Run at: simulated run time.
    - Window from: same as run time.
    - Window to: same as run time.
  - This visually communicates when the next snapshots will happen without
    implying a time range.

The schedule table is purely informational; it does not affect real workers but
uses the same overlap/cursor logic so you can reason about incremental windows
before they run.

---

## Workers SyncTerminal

At the bottom of the page, the **eBay workers terminal** is a shared log viewer
powered by SyncEvent logs.

- The dropdown **“Select worker run”** is populated from `/ebay/workers/runs`.
- Each option label includes:
  - `api_family`.
  - ISO date and time of `started_at`.
  - `status`.
- Choosing an option fetches `/ebay/workers/logs/{run_id}` to resolve an
  appropriate `sync_run_id` (from `summary.sync_run_id` or `summary.run_id`) and
  attaches the terminal to that SSE stream.

When a worker is triggered via **Run now** or **Run ALL**, the panel:

- Optimistically creates/updates entries in `recentRuns` so that runs appear in
  the dropdown immediately.
- Attempts to auto‑attach the terminal to the freshest run when possible.

The terminal content itself is documented in more depth in
`EBAY_WORKERS_CURSOR_AND_WINDOWS.md` (window logs) and `EBAY_WORKER_NOTIFICATIONS.md`
(notification summaries).

---

## Notifications

Separately from the UI, each worker run now creates a Task + TaskNotification
summarising:

- Worker type (orders, transactions, etc.).
- Account/house name.
- Window (from/to) and fetched/stored counts.
- Error message (for failed runs).

These notifications appear in the existing notifications UI and are described in
`EBAY_WORKER_NOTIFICATIONS.md`. The Workers Admin UI does not manage
notifications directly; it only triggers worker runs and shows their status.