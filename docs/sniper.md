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
- `has_bid` (boolean, NOT NULL, default `false`) – whether we have ever
  attempted to place a bid for this snipe (true even if eBay returned an
  error).
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
- `bidding` – a real proxy bid has been placed via the Buy Offer API and the
  auction is still running; we are waiting for the final result.
- `executed_stub` – **historical stub-only** state from the initial v2
  worker; the current production worker no longer writes this status, but
  older rows may still have it.
- `won` – auction is finished and the snipe won.
- `lost` – auction is finished and the snipe lost.
- `error` – an error occurred while processing the snipe (e.g. eBay API
  errors, invalid data, or safety guardrails). A human-readable explanation
  should be in `result_message`.
- `cancelled` – user cancelled the snipe before execution.

New snipes created via the v2 API enter the lifecycle in the `scheduled`
state. Typical automatic lifecycle today is:

- `scheduled` → `bidding` when the worker successfully places a proxy bid.
- `scheduled` → `error` if the worker decides it is unsafe/invalid to bid or
  cannot talk to eBay.
- `bidding` → `won` / `lost` / `error` once the auction has ended and the
  worker has checked the bidding status.

## Backend API

Router: `backend/app/routers/sniper.py`, prefix `/api/sniper`.

### OAuth scopes and tokens (Sniper-specific)

- Sniper использует **те же account-level user токены**, что и остальные
  eBay-модули, но для Browse/Buy Offer ему дополнительно требуются buy-скопы.
- Для корректной работы Sniper-воркера access token eBay-аккаунта должен
  включать как минимум:
  - `https://api.ebay.com/oauth/api_scope` – базовый browse/identity scope,
    используется в вызове `GET /buy/browse/v1/item/get_item_by_legacy_id` при
    создании снайпа и в воркере при разрешении REST `itemId`.
  - `https://api.ebay.com/oauth/api_scope/buy.offer.auction` – scope для
    Buy Offer Sniper:
    - `POST /buy/offer/v1_beta/bidding/{item_id}/place_proxy_bid`;
    - `GET /buy/offer/v1_beta/bidding/{item_id}`.
- Оба scope попадают в токен автоматически, если:
  - применены миграции Alembic для `ebay_scope_definitions`, включая
    `ensure_buy_offer_auction_scope_20251126`;
  - аккаунт был заново подключён через `/ebay/auth/start` после применения
    миграций.
- При диагностике проблем со Sniper важно:
  - проверить `ebay_authorizations.scopes` для соответствующего
    `ebay_account_id` и убедиться, что там есть `buy.offer.auction`;
  - при необходимости переподключить аккаунт, чтобы получить токен с
    обновлённым набором scope.

### POST /api/sniper/snipes

Create a new snipe using minimal client input and server-side metadata
lookup from eBay.

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

## Worker: sniper_executor (real bidding)

File: `backend/app/workers/sniper_executor.py`.

### Scheduling and polling

- Poll interval:
  - Configurable via env `SNIPER_POLL_INTERVAL_SECONDS`.
  - Defaults to 1s and is clamped to at least 1 second.
- Per-tick safety cap:
  - Env `SNIPER_MAX_SNIPES_PER_TICK` (default 50) limits how many due snipes
    are processed in one tick to avoid eBay API bursts.
- Due snipe selection (`_pick_due_snipes`):
  - `status == 'scheduled'`.
  - `fire_at <= now`.
  - `end_time > now`.
  - ordered by `fire_at ASC`.
  - limited by `SNIPER_MAX_SNIPES_PER_TICK`.

### Bidding flow (scheduled → bidding)

1. `run_sniper_once` loads all due snipes and iterates them.
2. For each snipe, `_place_bid_for_snipe` applies safety guardrails:
   - Skips bidding (sets `status='error'`, `has_bid=false`) if
     `max_bid_amount <= 0`.
   - Skips bidding (sets `status='error'`, `has_bid=false`) if
     `end_time - now < 1s` ("too late to bid").
   - In both cases, writes an `EbaySnipeLog` entry with `event_type`
     `skipped_invalid_max_bid` or `skipped_too_late` and a clear
     `result_message`.
3. If safety checks pass, the worker:
   - Resolves `EbayAccount` and the latest `EbayToken`.
   - Calls eBay Buy Browse
     `GET /buy/browse/v1/item/get_item_by_legacy_id?legacy_item_id={itemId}`
     to convert the legacy `item_id` to the REST `itemId`.
   - Calls eBay Buy Offer
     `POST /buy/offer/v1_beta/bidding/{itemId}/place_proxy_bid` with
     `max_bid_amount` and `currency`.
4. On success:
   - Marks the snipe as `status='bidding'`.
   - Sets `has_bid = true`.
   - Updates `result_message` with a short summary.
   - Records an `EbaySnipeLog` row with:
     - `event_type = 'place_bid'`,
     - `status = 'bidding'`,
     - `ebay_bid_id` (from `proxyBidId` or `bidId` if present),
     - `http_status = 200`,
     - `payload` = full JSON response.
5. On any error (missing account/token, Browse/Offer failure):
   - Marks `status='error'`, `has_bid = true`.
   - Sets `result_message` to the error detail.
   - Records an `EbaySnipeLog` with `event_type = 'place_bid_error'` and the
     HTTP status/body when known.

### Result checking (bidding → won/lost/error)

After bidding, the worker periodically checks auctions that have ended:

1. `_pick_ended_bidding_snipes` selects snipes where:
   - `status == 'bidding'`.
   - `end_time <= now`.
2. `_finalize_ended_snipes` iterates these snipes and for each one:
   - Resolves account and token as above.
   - Resolves the REST `itemId` via `get_item_by_legacy_id`.
   - Calls eBay Buy Offer
     `GET /buy/offer/v1_beta/bidding/{itemId}`.
3. It interprets the response:
   - Reads `auctionStatus`, `highBidder`, and `currentPrice.value`.
   - If `auctionStatus == 'ENDED'` and `highBidder` is present:
     - Sets `status='won'` and `result_message="Auction ended: WON"`.
   - If `auctionStatus == 'ENDED'` and no `highBidder` is present:
     - Sets `status='lost'` and `result_message="Auction ended: LOST"`.
   - Otherwise:
     - Keeps `status='bidding'` and sets `result_message` to a descriptive
       message like `"Auction status from getBidding: ..."`.
   - If `currentPrice.value` is present, stores it in `result_price`.
4. It writes an `EbaySnipeLog` row with:
   - `event_type = 'result_check'` on success, or
   - `event_type = 'result_check_error'` on failure.

### Worker loop

- `run_sniper_once` performs one combined tick:
  - Places proxy bids for all currently due `scheduled` snipes.
  - Finalizes any `bidding` snipes whose auctions have already ended.
- `run_sniper_loop` wraps this in an infinite loop with
  `await asyncio.sleep(POLL_INTERVAL_SECONDS)` between ticks, logging how many
  snipes were processed each time.
- The worker is designed to run as a separate long-running process, e.g. a
  dedicated Railway service with command:
  `poetry -C backend run python -m app.workers.sniper_executor`.

## Logging: ebay_snipe_logs

To provide an auditable trail of everything the worker does, each snipe has a
set of associated logs in `ebay_snipe_logs`.

Key columns:

- `id` (string, 36, PK) – log id.
- `snipe_id` (string, 36, FK `ebay_snipes.id`) – owning snipe.
- `created_at` (timestamptz) – log timestamp.
- `event_type` (string, 64) – short event kind, e.g.:
  - `place_bid`, `place_bid_error`.
  - `result_check`, `result_check_error`.
  - `skipped_invalid_max_bid`, `skipped_too_late`.
- `status` (string, 32) – snipe status at the time of the event.
- `ebay_bid_id` (string, nullable) – eBay bid/proxy id when available.
- `correlation_id` (string, nullable) – reserved for future tracing.
- `http_status` (int, nullable) – HTTP status from eBay when applicable.
- `payload` (text, nullable) – JSON-serialized eBay response or error body.
- `message` (text, nullable) – concise human-readable summary.

In addition, `ebay_snipes.has_bid` is set to `true` whenever the worker has
attempted to place a bid (even if eBay returned an error). For guardrail
skips (`skipped_*`), `has_bid` remains `false`.

The frontend exposes a per-snipe "View logs" modal that calls
`GET /api/sniper/snipes/{id}/logs` and lists all logs in chronological order.

## Testing and safe production usage

### Worker wiring (Railway/Fly or similar)

The sniper worker is intended to run as a dedicated background process in
production. A typical configuration looks like:

- Command: `poetry -C backend run python -m app.workers.sniper_executor`.
- Env vars:
  - `DATABASE_URL` – Supabase Postgres.
  - `SNIPER_POLL_INTERVAL_SECONDS` – usually `1`.
  - `SNIPER_MAX_SNIPES_PER_TICK` – e.g. `50`.
- Process manager / platform:
  - Configure the worker service to automatically restart on crash.
  - Point it at the same image/repo as the main API service.

### How to safely test in production

1. **Pick a safe real auction**
   - Choose a low-value test item (e.g. a cheap accessory) where you are
     comfortable placing and potentially winning a bid.
   - Verify that it is an actual auction (not Buy It Now only) and that the
     end time is at least several minutes in the future.

2. **Create a test snipe**
   - Go to the Sniper page and click "Add snipe".
   - Select a known-good eBay account.
   - Enter the ItemID of the chosen auction.
   - Set a low `max_bid_amount` (e.g. a few dollars) that you are comfortable
     with.
   - Set `seconds_before_end` to a small value (3–10 seconds).
   - Optionally add a comment like "TEST – DO NOT DELETE".
   - Save the snipe.

3. **Observe initial grid state**
   - The new row should appear with:
     - `status = scheduled`.
     - Correct `title`, `currency`, `end_time`, and `fire_at`.
     - `has_bid = false`.
   - Open the logs modal for the snipe; it should initially be empty.

4. **Watch the worker around `fire_at`**
   - Ensure the worker process is running and connected to the same DB.
   - Around `fire_at`, refresh the Sniper grid:
     - `status` should move from `scheduled` → `bidding` (if the bid was
       placed) or `scheduled` → `error` (if something failed or a guardrail
       triggered).
     - `has_bid` should become `true` if a bid was attempted (even on
       errors).
   - Open the logs modal:
     - Expect at least one `place_bid` or `place_bid_error` log with
       `created_at` close to `fire_at`.

5. **Observe final outcome after auction end**
   - After `end_time` has passed, wait 1–2 worker ticks and refresh the grid.
   - Expected transitions:
     - `bidding` → `won` **or** `lost`, with `result_price` set, and
       `result_message` summarizing the result.
     - In case of repeated eBay errors, `bidding` → `error` with an
       explanatory `result_message`.
   - Open the logs modal again:
     - Expect at least one `result_check` (or `result_check_error`) log with
       the final payload.

6. **Safety/guardrail verification (optional)**
   - Create a snipe with `max_bid_amount = 0` and a distant future end time:
     - It should transition to `status='error'`, `has_bid=false`.
     - Logs should show `skipped_invalid_max_bid`.
   - Create a snipe whose `fire_at` is so close to `end_time` that by the time
     the worker sees it, `end_time - now < 1s`:
     - It should transition to `status='error'`, `has_bid=false`.
     - Logs should show `skipped_too_late`.

Running through the above gives you high confidence that the production
sniper is correctly scheduling, bidding, and tracking results end-to-end.
