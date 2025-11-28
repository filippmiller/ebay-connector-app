# eBay Workers: Natural Keys and Deduplication Strategy

This document describes, for each eBay worker and its corresponding Postgres tables, **which natural keys from eBay data are used to avoid duplicates**, how they are enforced in the schema, and how the upsert procedures use them.

The guiding principles are:

- Never rely on internal surrogate IDs (`id` columns) for dedup.
- Prefer **eBay-origin identifiers** (orderId, transactionId, caseId, inquiryId, etc.), combined with account/user context where needed.
- Back the natural key with a **unique constraint or index**.
- Implement **`INSERT ... ON CONFLICT (...) DO UPDATE`** upserts on exactly these key columns.

This makes all workers safe to rerun with overlapping time windows and idempotent in the presence of retries.

---

## Overview: worker → table → dedup key

High-level mapping:

- **Orders worker (`orders`)**
  - Tables: `ebay_orders`, `order_line_items`.
  - Keys:
    - `ebay_orders`: `(order_id, user_id)`.
    - `order_line_items`: `(order_id, line_item_id)`.
- **Transactions worker (`transactions`)**
  - Table: `ebay_transactions`.
  - Key: `(transaction_id, user_id)`.
- **Finances worker (`finances`)**
  - Table: `ebay_finances_transactions`.
  - Key: `(ebay_account_id, transaction_id)`.
  - Fees table `ebay_finances_fees` is treated as **replace-all-per-(account,transaction)** rather than upsert-by-key.
- **Offers worker (`offers`)**
  - Table: `ebay_offers`.
  - Key: `(offer_id, user_id)`.
- **Inventory helper (called by offers)**
  - Table: `inventory` (SKU inventory).
  - Key: `sku_code` (per-org SKU; plus account_id/user_id tracked as fields).
- **Messages worker (`messages`)**
  - Table: `ebay_messages`.
  - Key: natural `message_id` per eBay message; enforced in schema and indexes.
- **Active Inventory snapshot (`active_inventory`)**
  - Table: `ebay_active_inventory`.
  - Key: `(ebay_account_id, sku, item_id)`.
- **Buyer / Purchases worker (`buyer`)**
  - Table: `ebay_buyer`.
  - Key: `(ebay_account_id, item_id, transaction_id, order_line_item_id)`.
- **Post-Order Inquiries worker (`inquiries`)**
  - Table: `ebay_inquiries`.
  - Key: `(inquiry_id, user_id)`.
- **Post-Order Cases worker (`cases`)**
  - Table: `ebay_cases`.
  - Key: `(case_id, user_id)`.
- **Payment Disputes helper (no dedicated worker yet)**
  - Table: `ebay_disputes`.
  - Key: `(dispute_id, user_id)`.

Each section below links these keys to:

- The **eBay field(s)** they come from.
- The **schema constraint** (unique index or table args) that enforces them.
- The **upsert function** in `PostgresEbayDatabase` (or ORM) that uses `ON CONFLICT` on those columns.

---

## Orders: `ebay_orders` and `order_line_items`

### Natural keys

- **Order header**:
  - eBay field: `orderId`.
  - Context: each logical org/user may have multiple eBay accounts; legacy path keys by `user_id` + eBay `orderId`.
- **Order line items**:
  - eBay fields: `orderId` + `lineItemId`.

### Schema enforcement

- `ebay_orders` (see `backend/app/db_models/order.py` and `DATABASE_SCHEMA.md`):
  - `order_id` is unique per user.
  - There is a unique constraint `(order_id, user_id)` used by upserts.
- `order_line_items`:
  - Unique constraint on `(order_id, line_item_id)`.

### Upsert procedures

- `PostgresEbayDatabase.upsert_order` and `batch_upsert_orders`:
  - Use `ON CONFLICT (order_id, user_id) DO UPDATE`.
  - On conflict, update status, totals, buyer info, payload, timestamps.
- `PostgresEbayDatabase.batch_upsert_line_items`:
  - Uses `ON CONFLICT (order_id, line_item_id) DO UPDATE`.
  - Updates SKU, title, quantity, value, currency, payload, account context.

**Implication:** any overlapping fetch (e.g. same order re-fetched because `lastModifiedDate` fell into an overlap window) will update the existing row instead of inserting a duplicate.

---

## Transactions: `ebay_transactions`

### Natural key

- eBay field: `transactionId` from Sell Finances API transaction payloads.
- Context: dedup per `(transactionId, user_id)`.

### Schema enforcement

- `ebay_transactions` table (see `DATABASE_SCHEMA.md` and migration scripts):
  - `transaction_id` is unique per user; implemented as a unique key / index.

### Upsert procedure

- `PostgresEbayDatabase.upsert_transaction`:
  - `INSERT ... ON CONFLICT (transaction_id, user_id) DO UPDATE`.
  - Updates order linkage, type, status, amounts, currency, payload, timestamps.

**Implication:** the Transactions worker can safely fetch the same Finances transaction multiple times across overlapping windows; each run will converge to a single row per `(user_id, transactionId)`.

---

## Finances: `ebay_finances_transactions` and `ebay_finances_fees`

### Natural keys

- **Finances transaction**:
  - eBay field: `transactionId` from Finances API.
  - Context: per-account uniqueness: `(ebay_account_id, transaction_id)`.
- **Fees**:
  - No strict per-fee natural key defined; fees are treated as **ephemeral detail rows** hanging off the transaction.

### Schema enforcement

- `ebay_finances_transactions`:
  - Unique constraint on `(ebay_account_id, transaction_id)`.
- `ebay_finances_fees`:
  - `id` is surrogate; dedup handled via delete+insert per transaction.

### Upsert procedure

- `PostgresEbayDatabase.upsert_finances_transaction`:
  - Inserts into `ebay_finances_transactions` with `ON CONFLICT (ebay_account_id, transaction_id) DO UPDATE`.
  - Updates type, status, booking date, signed amount, linkage to order/payout, memo, payload, account/user context.
- Fees:
  - For a given `(ebay_account_id, transaction_id)` the helper **deletes all existing `ebay_finances_fees` rows** and re-inserts the current `fee_rows`.
  - This treats the combination as **source-of-truth**; repeated syncs rebuild the fee set from scratch for that transaction.

**Implication:** overlapping windows re-upsert the same `transactionId` but never create duplicates, and the associated fees are always the latest full set from eBay.

---

## Offers: `ebay_offers`

### Natural key

- eBay field: `offerId` from Inventory Offers API.
- Context: unique per `(offerId, user_id)` in the legacy schema; in the multi-account world, `ebay_account_id` is also stored but the conflict key remains `(offerId, user_id)`.

### Schema enforcement

- `ebay_offers` table:
  - Unique `(offer_id, user_id)` (see `DATABASE_SCHEMA.md` and migrations).

### Upsert procedure

- `PostgresEbayDatabase.upsert_offer`:
  - `INSERT ... ON CONFLICT (offer_id, user_id) DO UPDATE`.
  - Updates listing id, buyer username, price, status, dates, raw payload, timestamps, and account context.

**Implication:** scanning all SKUs and their offers repeatedly will only update each distinct `offerId` per user, never insert duplicates.

---

## Inventory helper: `inventory` (SKU inventory)

### Natural key

- eBay field: SKU string from Inventory API: `inventory_item_data['sku']`.
- Context: table-level unique `sku_code`; `user_id` and `ebay_account_id` are descriptive and can change.

### Schema enforcement

- `inventory` table:
  - Unique key on `sku_code`.

### Upsert procedure

- `PostgresEbayDatabase.upsert_inventory_item`:
  - `INSERT ... ON CONFLICT (sku_code) DO UPDATE`.
  - Updates descriptive fields: title, condition, part_number, model, category, price, quantity, listing id, status, photo_count, payload, and account context.

**Implication:** different workers (Offers worker, potential dedicated inventory worker) can safely call `upsert_inventory_item` without creating duplicates for the same SKU.

---

## Messages: `ebay_messages`

### Natural key

- eBay fields from Trading `GetMyMessages`:
  - Primary: `MessageID`.
  - Context: stored alongside `ebay_account_id` and `user_id`, but the **message identity is `message_id`**.

### Schema enforcement

- `ebay_messages` SQLAlchemy model (`Message`):
  - `message_id` is indexed (`idx_ebay_messages_message_id`).
- Historical schema (`DATABASE_SCHEMA.md`) defined `message_id` as `UNIQUE`.
- Alembic migrations and normalization scripts enforce uniqueness per environment and fix prior duplicates.

### Upsert / dedup procedure

- Normalization and upsert path (see backend docs and normalisation scripts):
  - When ingesting messages, code first **looks up by `message_id`** (and account) to decide whether to insert or update.
  - Duplicate `MessageID` from eBay will always map back to the same DB row.
- Additional scripts (`fix_ebay_messages_id.py`, `ebay_messages_normalization_20251124.py`) clean and enforce the uniqueness of `message_id`.

**Implication:** overlapping message windows (via `StartTimeFrom`/`StartTimeTo`) re-process the same messages safely, keyed by `MessageID`.

---

## Active Inventory snapshot: `ebay_active_inventory`

### Natural key

- eBay fields from Trading `GetMyeBaySelling` ActiveList:
  - `ItemID` and `SKU` (if present).
- Context: unique per `(ebay_account_id, sku, item_id)`.

### Schema enforcement

- `ActiveInventory` model:
  - Composite unique index:
    - `idx_active_inv_account_sku_item (ebay_account_id, sku, item_id, unique=True)`.

### Upsert procedure

- `EbayService.sync_active_inventory_report`:
  - For each page of Trading results, it either:
    - Finds existing row by `(ebay_account_id, sku, item_id)` or
    - Creates a new one.
  - Fields like title, quantity, price, status, condition, raw_payload, last_seen_at are updated in-place.

**Implication:** rerunning the snapshot worker never creates duplicate rows for the same listing/SKU; it simply refreshes the current state.

---

## Buyer / Purchases: `ebay_buyer`

### Natural key

- eBay fields from Trading `GetMyeBayBuying` (and other Buying sources):
  - `item_id` (ItemID).
  - `transaction_id` (when available).
  - `order_line_item_id` (when available).
- Context: uniqueness is per eBay account:
  - `(ebay_account_id, item_id, transaction_id, order_line_item_id)`.

### Schema enforcement

- `EbayBuyer` model:
  - Unique index `uq_ebay_buyer_account_item_txn` on
    - `ebay_account_id`, `item_id`, `transaction_id`, `order_line_item_id`.

### Upsert procedure

- `purchases_worker` uses SQLAlchemy ORM instead of raw SQL:
  - For each normalized DTO, the worker does:
    - Query `EbayBuyer` by `(ebay_account_id, item_id, transaction_id, order_line_item_id)`.
    - If found: update **only external/API-owned fields** and keep warehouse-driven columns intact.
    - If not found: insert a new `EbayBuyer` row.

**Implication:** multiple runs over the same purchases (even without a strict Trading date filter yet) converge to a **single row per purchase line item per account**.

---

## Post-Order Inquiries: `ebay_inquiries`

### Natural key

- eBay fields:
  - `inquiryId` from Post-Order Inquiry API.
- Context: unique per `(inquiry_id, user_id)`.

### Schema enforcement

- `ebay_inquiries` table (see `ebay_inquiries_20251124` migration and schema):
  - Unique constraint on `(inquiry_id, user_id)`.

### Upsert procedure

- `PostgresEbayDatabase.upsert_inquiry`:
  - `INSERT ... ON CONFLICT (inquiry_id, user_id) DO UPDATE`.
  - Updates normalized identifiers (orderId/itemId/transactionId), buyer/seller usernames, status, issue type, amounts, timestamps, raw JSON, and account context.

**Implication:** the Inquiries worker can safely re-ingest the same inquiry (or updated versions) without creating duplicates.

---

## Post-Order Cases: `ebay_cases`

### Natural key

- eBay fields:
  - `caseId` from Post-Order Case Management API.
- Context: unique per `(case_id, user_id)`.

### Schema enforcement

- `ebay_cases` table (see `CASES_NORMALIZATION.md` and migrations):
  - Unique constraint on `(case_id, user_id)`.

### Upsert procedure

- `PostgresEbayDatabase.upsert_case`:
  - `INSERT ... ON CONFLICT (case_id, user_id) DO UPDATE`.
  - Updates orderId, caseType, status, timestamps, normalized item/transaction ids, buyer/seller usernames, claim amounts, and account context.

**Implication:** repeated Post-Order case syncs (with no strong API time filter yet) still maintain **one row per logical case** per user.

---

## Payment Disputes: `ebay_disputes`

### Natural key

- eBay field:
  - `paymentDisputeId`.
- Context: unique per `(dispute_id, user_id)`.

### Schema enforcement

- `ebay_disputes` table (see migrations):
  - Unique `(dispute_id, user_id)`.

### Upsert procedure

- `PostgresEbayDatabase.upsert_dispute`:
  - `INSERT ... ON CONFLICT (dispute_id, user_id) DO UPDATE`.
  - Updates orderId, reason, status, dates, payload, ebay_account_id, ebay_user_id.

**Implication:** once a dedicated Disputes worker is added, it will automatically inherit a safe dedup behavior on `(user_id, paymentDisputeId)`.

---

## Keys in the UI and grids

- **Workers Admin UI (Admin → Workers → eBay Workers):**
  - `/ebay/workers/config` now returns a `primary_dedup_key` string per worker.
  - `EbayWorkersPanel` renders this in the "Primary key" column as a small
    monospace label (for example, `(order_id, user_id)` for Orders, or
    `(ebay_account_id, item_id, transaction_id, order_line_item_id)` for Buyer).
  - This makes it explicit, per worker, *which* eBay-origin fields are used to
    avoid duplicates when windows overlap.

- **Domain grids** (Orders, Transactions, Buyer, Cases, etc.):
  - Orders grid exposes `order_id` as the primary visible identifier; that is
    the same field used in the `(order_id, user_id)` key for `ebay_orders`.
  - Transactions/Finances grids surface `transaction_id` and `transaction_type`;
    the dedup key is `(transaction_id, user_id)` for `ebay_transactions` and
    `(ebay_account_id, transaction_id)` for `ebay_finances_transactions`.
  - Messages grid shows `message_id`, thread, and direction; dedup is by
    `message_id` (plus account context) as documented above.
  - Buyer grid surfaces `item_id`, `transaction_id`, and `order_line_item_id`
    per row; these three plus `ebay_account_id` form the unique key.
  - Cases/Inquiries grids expose `case_id` / `inquiry_id` along with linked
    `order_id`/`item_id`/`transaction_id`; DB dedup uses `(case_id, user_id)` and
    `(inquiry_id, user_id)` respectively.

This alignment means the identifiers you see in the UI (IDs in the first
column of each grid) are the same ones the workers and upserts rely on as
natural keys.

## Summary

- Every eBay worker or ingestion helper uses **eBay-origin identifiers** as the primary dedup keys.
- These keys are consistently backed by **unique constraints or composite indexes**:
  - Orders: `(order_id, user_id)`; line items: `(order_id, line_item_id)`.
  - Transactions: `(transaction_id, user_id)`; Finances: `(ebay_account_id, transaction_id)`.
  - Offers: `(offer_id, user_id)`.
  - Messages: `message_id` (plus account/user context).
  - Active inventory: `(ebay_account_id, sku, item_id)`.
  - Buyer: `(ebay_account_id, item_id, transaction_id, order_line_item_id)`.
  - Inquiries: `(inquiry_id, user_id)`.
  - Cases: `(case_id, user_id)`.
  - Disputes: `(dispute_id, user_id)`.
- All upsert logic is implemented using `INSERT ... ON CONFLICT (natural_key...) DO UPDATE`, or the ORM equivalent for `ebay_buyer`.
- Combined with the **30-minute overlap window** for workers, this guarantees:
  - No duplicates when the same entities are re-fetched.
  - Existing rows are updated with the latest data from eBay.
  - Workers remain safe to rerun manually and on schedule with overlapping windows.
