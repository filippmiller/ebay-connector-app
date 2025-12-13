# eBay cases normalization (ebay_cases)

This document describes how eBay Post-Order cases are stored and normalized in
Postgres, and how to run the worker that keeps `ebay_cases` up to date.

## Table: `public.ebay_cases`

Key columns (before normalization):

- `case_id` – eBay case identifier (PK together with `user_id`).
- `user_id` – org-level user id for the owning account.
- `order_id` – eBay order id when available.
- `case_type` – human-readable type/reason from the Post-Order API.
- `case_status` – coarse status used in legacy grids.
- `open_date`, `close_date` – original string timestamps as returned by early
  implementations.
- `case_data` – **raw JSON payload** from the Post-Order Case Management API
  (archival copy of the full response for this case).
- `created_at`, `updated_at` – audit timestamps.
- `ebay_account_id`, `ebay_user_id` – normalized eBay identity for joins.

### New normalized columns

The migration `ebay_cases_normalization_20251124` adds the following nullable
columns so that grids and services no longer need to parse `case_data` on the
fly:

- `item_id` (`varchar(100)`) – from `case_data.itemId`.
- `transaction_id` (`varchar(100)`) – from `case_data.transactionId`.
- `buyer_username` (`text`) – from `case_data.buyer` (string username).
- `seller_username` (`text`) – from `case_data.seller`.
- `case_status_enum` (`text`) – original enum from Post-Order API
  (`caseStatusEnum`, e.g. `CS_OPEN`, `CS_CLOSED`).
- `claim_amount_value` (`numeric(12,2)`) – from `case_data.claimAmount.value`.
- `claim_amount_currency` (`varchar(10)`) – from
  `case_data.claimAmount.currency`.
- `respond_by` (`timestamptz`) – from `case_data.respondByDate.value`.
- `creation_date_api` (`timestamptz`) – from `case_data.creationDate.value`
  (the actual case creation moment from eBay).
- `last_modified_date_api` (`timestamptz`) – from
  `case_data.lastModifiedDate.value`.

Indexes added for matching and filtering:

- `idx_ebay_cases_transaction_id` on `transaction_id`.
- `idx_ebay_cases_item_id` on `item_id`.
- `idx_ebay_cases_buyer_username` on `buyer_username`.
- `idx_ebay_cases_respond_by` on `respond_by`.

> Issue type: current Post-Order payloads in this project do not expose a
> stable, single field like `issueType` or `caseReason` that can be used as a
> canonical case category (INR/SNAD/etc.). The unified Cases grid continues to
> infer `issue_type` from existing `case_type` / `dispute_reason` strings and
> does not introduce a dedicated `issue_type` column in `ebay_cases` yet.

## Backfill migration

The Alembic migration performs a best-effort backfill for existing rows:

- Iterates all rows from `ebay_cases`, parses `case_data` JSON via Python,
  and extracts the fields listed above.
- Populates the new columns using the following mappings (per row):
  - `item_id` ← `case_data["itemId"]` (stringified if numeric).
  - `transaction_id` ← `case_data["transactionId"]`.
  - `buyer_username` ← `case_data["buyer"]`.
  - `seller_username` ← `case_data["seller"]`.
  - `case_status_enum` ← `case_data["caseStatusEnum"]`.
  - `claim_amount_value`, `claim_amount_currency` ←
    `case_data["claimAmount"]` (`{"value","currency"}`).
  - `respond_by` ← `case_data["respondByDate"]["value"]` (ISO8601 string).
  - `creation_date_api` ← `case_data["creationDate"]["value"]`.
  - `last_modified_date_api` ← `case_data["lastModifiedDate"]["value"]`.
- All timestamps are parsed into timezone-aware `timestamptz` values using the
  same helpers as other ingestion paths.
- If a row’s `case_data` cannot be parsed as JSON, the migration logs a
  warning with `case_id` and leaves the new columns as `NULL` for that row
  (the migration continues for the rest of the table).

The backfill is idempotent in practice: running the same logic again would
recompute the same deterministic values and overwrite existing ones with
identical data.

## Ingestion pipeline

The Post-Order cases ingestion path is:

1. **Worker** – `run_cases_worker_for_account` in
   `backend/app/services/ebay_workers/cases_worker.py`:
   - Resolves the eBay account and sync window.
   - Calls `EbayService.sync_postorder_cases` with `user_id`, access token,
     and window metadata.
2. **Service** – `EbayService.sync_postorder_cases` in
   `backend/app/services/ebay.py`:
   - Calls `GET /post-order/v2/casemanagement/search`.
   - Logs request/response details via `SyncEventLogger`.
   - Iterates each case payload and delegates persistence to
     `PostgresEbayDatabase.upsert_case`.
   - Tracks counters:
     - `total_fetched` – cases returned by the API.
     - `total_stored` – successfully written rows.
     - `normalized_full` – rows where both `itemId` and `transactionId` were
       present and written to `ebay_cases`.
     - `normalized_partial` – rows written but missing one of the key IDs.
     - `normalization_errors` – rows that failed to upsert due to
       normalization issues.
3. **Storage** – `PostgresEbayDatabase.upsert_case` in
   `backend/app/services/postgres_ebay_database.py`:
   - Validates `caseId` and extracts core fields (`orderId`, `caseType`,
     `status`, open/close dates).
   - Normalizes and writes identifiers, usernames, amounts and timestamps into
     the new columns described above.
   - Always stores the full raw payload in `case_data`.
   - Upserts by `(case_id,user_id)` so repeated runs are idempotent.

The unified Cases grid in `backend/app/routers/grids_data.py` now uses these
normalized columns for Post-Order cases and falls back to parsing
`case_data` only when necessary for legacy disputes.

## Manual worker run for verification

You can trigger a single Post-Order cases sync for a specific eBay account via
the existing workers API:

- Endpoint: `POST /api/ebay-workers/run`.
- Query parameters:
  - `account_id` – eBay account id (UUID from `ebay_accounts.id`).
  - `api=cases` – select the cases worker family.

Example (pseudo-HTTP):

- `POST /api/ebay-workers/run?account_id={ACCOUNT_ID}&api=cases`

The response includes:

- `status` – `started`, `skipped`, or `error`.
- `run_id` – worker run identifier when started.
- `api_family` – should be `"cases"`.

For each run you can inspect detailed stats via the workers runs endpoint
and logs:

- `GET /api/ebay-workers/runs?account_id={ACCOUNT_ID}&api=cases`
  - The `summary` JSON for the most recent run includes
    `total_fetched`, `total_stored`, `normalized_full`,
    `normalized_partial`, and `normalization_errors`, plus the sync window
    used for that run.
- Railway/Cloud logs for the backend service will show INFO/WARN lines from
  `sync_postorder_cases` and `upsert_case`, including warnings about cases
  missing `itemId`/`transactionId` or any normalization errors.

After running the worker, you can query `public.ebay_cases` (or use the
Admin → Cases grid) to confirm that:

- New rows have `item_id`, `transaction_id`, `buyer_username`,
  `claim_amount_value`/`claim_amount_currency`, and `respond_by` populated.
- Existing rows created before this migration have been backfilled where their
  `case_data` JSON was valid.
