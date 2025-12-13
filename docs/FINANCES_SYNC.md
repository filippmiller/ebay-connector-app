# Finances Sync Design (Draft)

> Status: draft / in progress

This document describes the new **Finances** feature for the eBay Connector App:

- A background worker that pulls monetary transactions from the **Sell Finances getTransactions** API.
- Postgres tables to store the raw ledger and per-fee breakdown.
- Backend APIs to expose this data to the frontend.
- A Finances tab in the UI that shows a grid of transactions and fees.

The implementation follows the same patterns as existing workers (orders, transactions, inventory, messages).

## High-level architecture

- **Data source**: `GET https://apiz.ebay.com/sell/finances/v1/transaction`
  - OAuth scope: `https://api.ebay.com/oauth/api_scope/sell.finances` (authorization code grant).
  - Headers: `Authorization: Bearer <access_token>`, `Accept: application/json`, `Content-Type: application/json`, `X-EBAY-C-MARKETPLACE-ID: EBAY_US`.
- **DB layer**:
  - `public.ebay_finances_transactions` – one row per Finances transaction (SALE, REFUND, FEE, SHIPPING_LABEL, etc.).
  - `public.ebay_finances_fees` – one row per fee line (FINAL_VALUE_FEE, PROMOTED_LISTING_FEE, SHIPPING_LABEL_FEE, etc.).
  - Reuse `ebay_sync_state` (`EbaySyncState`) as the per-account cursor store (`api_family='finances'`).
- **Worker**:
  - `run_finances_worker_for_account(ebay_account_id)` uses `EbayService` to call Finances `getTransactions` with a **transactionDate** window.
  - Incremental sync based on `booking_date` (transactions.transactionDate) with a small overlap window.
  - Writes rows into `ebay_finances_transactions` and `ebay_finances_fees` via `PostgresEbayDatabase` helpers.
- **Backend API**:
  - Read-only endpoints (e.g. `/api/finances/transactions`) to support a grid with pagination, filters, and fee aggregates.
- **Frontend**:
  - New **Finances** tab in the main nav.
  - `FinancesPage` using `DataGridPage` (same grid infra as Orders/Transactions) to display transactions + fee breakdown.

## Data model (summary)

### ebay_finances_transactions

One row per Finances `Transaction` object.

Key fields (simplified):

- `id` – PK.
- `ebay_account_id` – FK to `ebay_accounts.id`.
- `ebay_user_id` – cached seller ID.
- `transaction_id` – Finances `transactionId` (unique per account).
- `transaction_type` – `transactionType` (SALE, REFUND, SHIPPING_LABEL, NON_SALE_CHARGE, CREDIT, TRANSFER, ...).
- `transaction_status` – `transactionStatus` (FUNDS_ON_HOLD, FUNDS_PROCESSING, PAYOUT, ...).
- `booking_date` – `transactionDate` (timestamptz); used as sync cursor.
- `transaction_amount_value` – signed amount (CREDIT = +, DEBIT = −).
- `transaction_amount_currency` – currency code.
- `order_id` – `orderId` if present.
- `order_line_item_id` – first `orderLineItems[].lineItemId` (if any).
- `payout_id` – `payoutId` if present.
- `seller_reference` – `salesRecordReference` (and/or payout reference as needed).
- `transaction_memo` – `transactionMemo` (shipping label notes, holds, non-sale charges).
- `raw_payload` – jsonb `Transaction` object.
- `created_at` / `updated_at` – audit.

Constraints and indexes:

- Unique `(ebay_account_id, transaction_id)`.
- Index on `(ebay_account_id, booking_date DESC)`.
- Indexes on `(order_id)`, `(order_line_item_id)`, `(transaction_type)`.

### ebay_finances_fees

One row per fee line (typically from `orderLineItems[].marketplaceFees[]` or top-level fee-only transactions).

Key fields:

- `id` – PK.
- `ebay_account_id` – FK.
- `transaction_id` – FK to `ebay_finances_transactions(transaction_id)` (and account).
- `fee_type` – `FeeTypeEnum` value (FINAL_VALUE_FEE, FINAL_VALUE_FEE_FIXED_PER_ORDER, PROMOTED_LISTING_FEE, SHIPPING_LABEL_FEE, CHARITY_DONATION, ...).
- `amount_value` / `amount_currency` – magnitude of the fee (always positive; direction inferred from parent transaction).
- `raw_payload` – jsonb `Fee` object.

Indexes:

- `(ebay_account_id, transaction_id)`.
- `(fee_type)`.

## Worker algorithm (outline)

Per account (ebay_account_id):

1. Look up or create `EbaySyncState` row with `api_family='finances'`.
2. Determine date window:
   - `window_to = now()`.
   - If cursor exists: `window_from = last_cursor - overlap` (e.g. 1 hour).
   - Else: `window_from = now() - 30 days`.
3. Call Finances `getTransactions` in pages using filters:
   - `transactionDate:[window_from..window_to]`.
   - `transactionStatus:{SUCCESS,FUNDS_AVAILABLE_FOR_PAYOUT,FUNDS_PROCESSING,FUNDS_ON_HOLD,PAYOUT}` (exact set TBD).
   - Optionally `transactionType` to narrow down (SALE, REFUND, SHIPPING_LABEL, NON_SALE_CHARGE, CREDIT, ...).
4. For each transaction in each page:
   - Normalize and upsert into `ebay_finances_transactions` (using signed amount based on `bookingEntry`).
   - Extract fee lines and replace rows in `ebay_finances_fees` for that transaction.
   - Track max `booking_date` seen.
5. After all pages:
   - Update sync state cursor (`cursor_type='transactionDate'`, `cursor_value=max_booking_date`).
   - Mark worker run as completed with counts.
6. On error:
   - Log HTTP status, errorId, and message from eBay.
   - Set `last_error` on sync state and mark worker run as failed.

## Backend API (outline)

- `GET /api/finances/transactions`
  - Query params: `limit`, `offset`, `sort_by`, `sort_dir`, `date_from`, `date_to`, `transaction_type`, `ebay_account_id`, `order_id`, `search`.
  - Returns paginated list of transactions with:
    - Core fields (booking_date, transaction_type, status, order_id, amount, currency, bookingEntry sign baked into amount).
    - Aggregated fee columns: `final_value_fee`, `promoted_listing_fee`, `shipping_label_fee`, `other_fees`, `total_fees`.
  - Backed by joins between `ebay_finances_transactions` and `ebay_finances_fees`.

## Frontend Finances grid (outline)

- New **Finances** tab in `FixedHeader` pointing to `/financials`.
- `FinancialsPage` updated to host a full-width `DataGridPage` using a new `gridKey="finances"`.
- Grid columns (initial):
  - Date, Account, Type, Status, Order ID, Transaction ID.
  - Gross amount (signed).
  - Final value fee, insertion/listing fees, promoted listing fee, shipping label cost, total fees.
- Filters: date range, transaction type, account, order ID / search.

## OAuth and scopes

- Finances API requires `https://api.ebay.com/oauth/api_scope/sell.finances`.
- Our OAuth URL generation already includes this scope by default; accounts that predate this feature may need to be re-authorized.

## Implementation checklist

See `docs/TODO-FINANCES.md` for the concrete task list and status.
