# TODO – Finances Feature

Status legend: `[ ]` pending, `[x]` done

## Design & docs

- [x] Read Finances API docs and design DB schema
- [x] Add docs/FINANCES_SYNC.md with high-level design
- [ ] Keep docs updated as implementation evolves

## Backend – DB & sync

- [ ] Add Postgres tables: ebay_finances_transactions, ebay_finances_fees (Alembic migration)
- [ ] Extend PostgresEbayDatabase with upsert helpers for finances transactions and fees
- [ ] Ensure EbaySyncState supports api_family="finances" (reuse existing table)
- [ ] Implement Finances API client (getTransactions) in EbayService
- [ ] Implement finances sync method that:
  - [ ] Pages through getTransactions by transactionDate
  - [ ] Upserts into ebay_finances_transactions
  - [ ] Replaces fees in ebay_finances_fees
  - [ ] Updates sync job + SyncEventLogger
- [ ] Implement finances worker run_finances_worker_for_account(ebay_account_id)
- [ ] Wire finances worker into /ebay/workers/config and /ebay/workers/run

## Backend – API for grid

- [ ] Add /api/finances/transactions endpoint
  - [ ] Supports limit/offset, sort_by/sort_dir
  - [ ] Filters: date_from/date_to, transaction_type, ebay_account_id, order_id/search
  - [ ] Returns fee aggregates per transaction

## Frontend – UI

- [ ] Add Finances tab to FixedHeader nav
- [ ] Wire /financials route in App.tsx
- [ ] Implement FinancesPage using DataGridPage (gridKey="finances")
- [ ] Add filters (date range, type, account, search) to the page
- [ ] Show per-transaction fee breakdown columns

## Validation & tests

- [ ] Run Alembic migration against dev DB
- [ ] Run finances worker for at least one real eBay account
- [ ] Confirm rows in ebay_finances_transactions and ebay_finances_fees
- [ ] Manually hit /api/finances/transactions with different filters
- [ ] Compare a few transactions against Seller Hub > Payments
- [ ] Open Finances tab in UI and confirm data + interactions
- [ ] Add/adjust tests where it makes sense (e.g., DB helpers, API filters)
