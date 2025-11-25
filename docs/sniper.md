# Sniper module (internal Bidnapper) – v2 overview

## Purpose

The Sniper module lets users schedule last-second bids on eBay auction listings
(similar to Bidnapper). Each snipe is stored as a row in the `ebay_snipes`
Postgres table and executed by a background worker shortly before the auction
ends.

This document describes:
- the `ebay_snipes` schema and status lifecycle,
- backend API endpoints used by the Sniper UI,
- the sniper executor worker and its `fire_at`-based scheduling,
- the frontend SNIPER page and grid.

## Database: ebay_snipes

Core columns (relevant to Sniper v2):

- `id` (string, 36) – primary key (UUID).
- `user_id` (string, 36, FK `users.id`) – owner of the snipe.
- `ebay_account_id` (string, 36, FK `ebay_accounts.id`, ondelete CASCADE) –
  eBay account used to place the bid.
- `item_id` (string, 100) – eBay legacy ItemID.
- `title` (text, nullable) – cached item title at creation time.
- `image_url` (text, nullable) – cached primary image URL.
- `end_time` (timestamptz, NOT NULL, indexed) – auction end time (UTC).
- `fire_at` (timestamptz, NOT NULL, indexed) – exact moment when the worker
  should attempt to place the bid, computed as
  `end_time - seconds_before_end`.
- `max_bid_amount` (numeric(14,2), NOT NULL) – user’s max bid.
- `currency` (char(3), NOT NULL, default `USD`) – currency of the auction.
- `seconds_before_end` (int, NOT NULL, default 5) – how many seconds before
  `end_time` to fire.
- `status` (string, 32, NOT NULL, indexed) – logical state of the snipe.
- `current_bid_at_creation` (numeric(14,2), nullable) – current auction bid
  at the time the snipe was created.
- `result_price` (numeric(14,2), nullable) – final auction price when known.
- `result_message` (text, nullable) – human-readable outcome/err message.
- `comment` (text, nullable) – free-form user note.
- `contingency_group_id` (string, 100, nullable) – reserved for future
  strategy features (one-of-many, groups, etc.).
- `created_at`, `updated_at` (timestamptz, NOT NULL) – audit timestamps.

Indexes:

- `idx_ebay_snipes_user_id` on `user_id`.
- `idx_ebay_snipes_account_id` on `ebay_account_id`.
- `idx_ebay_snipes_status` on `status`.
- `idx_ebay_snipes_end_time` on `end_time`.
- `idx_ebay_snipes_fire_at` on `fire_at`.

### Status lifecycle (EbaySnipeStatus)

Enum `EbaySnipeStatus` (Python str Enum):

- `pending` – legacy state; created but not fully scheduled. In v2 we
  generally create new snipes directly as `scheduled` once `fire_at` is
  computed.
- `scheduled` – auction metadata has been fetched, `fire_at` is set and the
  worker is waiting for that moment.
- `bidding` – reserved for future real PlaceOffer integration when a worker
  is actively placing a bid for the snipe.
- `executed_stub` – **stub-only** state used by the current worker
  implementation to mark that a snipe has been processed without placing a
  real bid.
- `won` – auction is finished and the snipe won.
- `lost` – auction is finished and the snipe lost.
- `error` – an error occurred while processing the snipe (e.g. eBay API
  errors). A human-readable explanation should be in `result_message`.
- `cancelled` – user cancelled the snipe before execution.

New snipes created via the v2 API enter the lifecycle in the `scheduled`
state. Older rows may still carry `pending`.

## Backend API

Router: `backend/app/routers/sniper.py`, prefix `/api/sniper`.

### POST /api/sniper/snipes

Create a new snipe using minimal client input and server-side metadata
lookup from eBay.

Request body (JSON):

- `ebay_account_id` (string, required) – must reference an `ebay_accounts`
  row owned by the current user/org with a valid token.
- `item_id` (string, required) – eBay ItemID.
- `max_bid_amount` (number, required) – max bid.
- `seconds_before_end` (number, optional, default 5) – when to fire.
- `comment` (string, optional) – note.

Server behaviour:

1. Validates account ownership via `EbayAccount.org_id == current_user.id`.
2. Loads the latest `EbayToken` for the account and calls eBay Buy Browse
   `get_item_by_legacy_id` using that token.
3. Validates that the item exists, is an auction and has not yet ended.
4. Extracts `end_time` (itemEndDate), `title`, `currency`, `price.value` and
   image URL (from `image.imageUrl` or first `images[].imageUrl`).
5. Computes `fire_at = end_time - seconds_before_end` (normalized to UTC).
6. Inserts an `EbaySnipe` row with:
   - status = `scheduled`,
   - `current_bid_at_creation` set from the current price,
   - `comment` from the request.

Response:

- Returns a serialized snipe row including `fire_at`, `comment` and all
  other grid fields.

Error cases:

- 400 if the account has no active token, the item doesn’t exist, is not an
  auction, or is already ended.
- 502 if the eBay Browse API is unreachable or returns invalid JSON.

### PATCH /api/sniper/snipes/{id}

Editable fields while status is `pending` or `scheduled`:

- `max_bid_amount` (number, optional).
- `seconds_before_end` (number, optional).
- `comment` (string, optional).
- `status` (enum, optional) – only transition allowed is to `cancelled`.

When `seconds_before_end` changes while the snipe is still mutable,
`fire_at` is recomputed as `end_time - seconds_before_end`.

Core fields (`ebay_account_id`, `item_id`, `end_time`) are immutable once
created.

If the snipe is in a terminal state (`executed_stub`, `won`, `lost`,
`error`, `cancelled`), any attempt to modify fields results in 400.

### DELETE /api/sniper/snipes/{id}

Logical cancellation:

- Allowed only when status is `pending` or `scheduled`.
- Sets status to `cancelled` and updates `updated_at`.

No physical delete is performed; history remains visible in the grid.

### GET /api/sniper/snipes

Utility list endpoint (not used by the main grid, but kept for API
completeness).

Query params:

- `limit`, `offset` – pagination.
- `status` – optional single status or comma-separated list.
- `ebay_account_id` – optional filter.
- `search` – case-insensitive search over `item_id` and `title`.

Returns `rows`, `limit`, `offset`, `total`.

## Grid: sniper_snipes

Backend:

- Column metadata is defined in `backend/app/routers/grid_layouts.py` as
  `SNIPER_SNIPES_COLUMNS_META`. It now includes:
  - `status`, `ebay_account_id`, `item_id`, `title`,
  - `max_bid_amount`, `currency`, `end_time`, `seconds_before_end`,
  - `comment`,
  - `current_bid_at_creation`, `result_price`, `result_message`,
  - `created_at`, `updated_at`.
- Grid defaults (`GRID_DEFAULTS['sniper_snipes']`) show a subset by default
  including `comment`.

Data endpoint:

- Implemented in `backend/app/routers/grids_data.py` as part of
  `/api/grids/{grid_key}/data`.
- When `grid_key == "sniper_snipes"`, the router calls
  `_get_sniper_snipes_data`, which:
  - uses the SQLAlchemy session from `app.models_sqlalchemy.get_db_sqla`,
  - scopes rows to `user_id == current_user.id`,
  - supports filters:
    - `state` – reused as a status filter, allowing a single value or
      comma-separated list,
    - `ebay_account_id`,
    - `search` – `item_id`/`title` ILIKE match,
  - sorts by a safe subset of columns (`created_at`, `end_time`, `fire_at`,
    `status`, `max_bid_amount`), defaulting to `created_at desc`,
  - serializes datetimes as ISO strings and numerics as floats,
  - returns `{ rows, limit, offset, total, sort }`.

Frontend:

- The Sniper page `frontend/src/pages/SniperPage.tsx` uses
  `<DataGridPage gridKey="sniper_snipes" />` with an extra `state` filter
  bound to the status dropdown.
- Columns, layouts and theme are managed via the shared
  `DataGridPage + AppDataGrid` infrastructure and stored in
  `user_grid_layouts`.
- In `AppDataGrid` the `item_id` column for `gridKey === 'sniper_snipes'`
  is rendered as a clickable link to `https://www.ebay.com/itm/{item_id}`
  (opening in a new tab, without triggering row-click handlers).

## Frontend form: Add/Edit snipe

File: `frontend/src/pages/SniperPage.tsx`.

Form fields (v2):

- `eBay account` – required dropdown populated via
  `/ebay-accounts?active_only=true`, filtered to accounts that:
  - are active, and
  - have a non-broken token (`token` present and no `refresh_error`).
- `Item ID` – required text input.
- `Max bid amount` – required numeric input.
- `Seconds before end` – optional number, default 5.
- `Comment` – optional textarea.

On save:

- For “Add” mode, the page calls `createSnipe` with the v2 payload
  (`ebay_account_id`, `item_id`, `max_bid_amount`, optional
  `seconds_before_end`, optional `comment`).
- For “Edit” mode, the page calls `updateSnipe` with any changed
  `max_bid_amount`, `seconds_before_end`, and `comment`.
- The ItemID and eBay account are immutable when editing; the account
  dropdown is disabled in edit mode.

Status dropdown on the page controls a simple filter by passing
`state={statusFilter}` to the grid data endpoint.

## Worker: sniper_executor (stub phase)

File: `backend/app/workers/sniper_executor.py`.

Key behaviour in v2 stub:

- Poll interval:
  - Configurable via env `SNIPER_POLL_INTERVAL_SECONDS`.
  - Defaults to 1s and is clamped to at least 1 second.
- Due snipe selection:
  - `_pick_due_snipes` queries `EbaySnipe` for rows where:
    - `status IN ('pending', 'scheduled')`,
    - `fire_at <= now`,
    - `end_time > now`,
    - ordered by `fire_at ASC`.
- Execution:
  - `run_sniper_once` marks each due snipe as
    `EbaySnipeStatus.executed_stub` and sets a clear
    `result_message = "SNIPER_STUB_EXECUTED — real eBay bid is not implemented yet"`.
  - This is a **stub only** implementation and does not call eBay to place
    real bids yet.
- Loop:
  - `run_sniper_loop` runs `run_sniper_once` in a `while True` loop with
    `await asyncio.sleep(interval_seconds)` between ticks, logging how many
    snipes were processed per tick.

Planned future extension (not implemented yet but prepared for):

- Replace the stub status change with:
  - `scheduled -> bidding` while calling the real PlaceOffer/Browse API.
  - After auction end, a separate result loop that sets `won` / `lost` /
    `error` and fills `result_price` and `result_message`.

## Testing notes

Because production Supabase connectivity is currently failing, Alembic
migrations (including `ebay_snipes_fire_at_comment_20251125`) must **not** be
run yet. Once `DATABASE_URL` and Alembic heads are healthy, the expected
sequence is:

1. `poetry -C backend run alembic upgrade head` (or targeted revision).
2. Basic smoke test:
   - Create a snipe via the SNIPER UI with a realistic ItemID.
   - Confirm that the grid shows the new row with the expected metadata
     (title, currency, end_time, fire_at, comment).
   - Watch worker logs to ensure due snipes transition into
     `executed_stub` at approximately the right time.

This concludes the Sniper v2 `fire_at` + `comment` foundation and wiring for
backend, worker and frontend.
