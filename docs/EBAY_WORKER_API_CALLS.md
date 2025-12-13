# eBay Workers → API Call Mapping

This document summarizes which eBay API endpoints are called by each worker family exposed in the **Workers** UI.

## Orders worker (`orders`)

**Backend path:** `backend/app/services/ebay_workers/orders_worker.py` → `EbayService.sync_all_orders`

**Primary eBay API calls:**

- **Fulfillment API**
  - `GET /sell/fulfillment/v1/order`
    - Uses an RSQL filter on `lastModifiedDate:[window_from..window_to]`
    - Paged with `limit` / `offset` (up to 200 per page)

**Data covered:** sales orders.

---

## Transactions worker (`transactions`)

**Backend path:** `backend/app/services/ebay_workers/transactions_worker.py` → `EbayService.sync_all_transactions`

**Primary eBay API calls:**

- **Finances API**
  - `GET /sell/finances/v1/transaction`
    - Filtered with `transactionDate:[window_from..window_to]`
    - Paged with `limit` / `offset` (200 per page)

**Data covered:** general transactions stream (orders, refunds, etc.).

---

## Finances worker (`finances`)

**Backend path:** `backend/app/services/ebay_workers/finances_worker.py` → `EbayService.sync_finances_transactions`

**Primary eBay API calls:**

- **Finances API**
  - `GET /sell/finances/v1/transaction`
    - Same `transactionDate` time windowing as the `transactions` worker

**Data covered:** detailed finances / fees into `ebay_finances_*` tables.

---

## Offers worker (`offers`)

**Backend path:** `backend/app/services/ebay_workers/offers_worker.py` → `EbayService.sync_all_offers`

**Primary eBay API calls:**

- **Inventory API**
  1. `GET /sell/inventory/v1/inventory_item?limit=200&offset=…`
     - Enumerates all SKUs (inventory items).
  2. For each SKU:
     - `GET /sell/inventory/v1/offer?sku={sku}&limit=200&offset=…`

**Data covered:** listing offers and related inventory/offer metadata.

---

## Messages worker (`messages`)

**Backend path:** `backend/app/services/ebay_workers/messages_worker.py` → `EbayService.sync_all_messages`

**Primary eBay API calls (Trading API, XML via `https://api.ebay.com/ws/api.dll`):**

- `GetMyMessages` (ReturnSummary)
  - Folder/message count summary.
- `GetMyMessages` (ReturnHeaders)
  - Message headers, time-windowed via `StartTimeFrom` / `StartTimeTo`.
- `GetMyMessages` (ReturnMessages)
  - Message bodies for batches of up to 10 message IDs.

**Data covered:** inbox/sent/custom-folder messages normalized into `ebay_messages`.

---

## Cases worker (`cases`)

**Backend path:** `backend/app/services/ebay_workers/cases_worker.py` → `EbayService.sync_postorder_cases`

**Primary eBay API calls (Post-Order API):**

- `GET /post-order/v2/casemanagement/search`
  - Currently ignores the worker time window at HTTP level; `window_from`/`window_to` are metadata for logging and cursoring.

**Data covered:** INR/SNAD post-order cases, stored in `ebay_cases` and joined with `ebay_disputes` in the unified Cases grid.

---

## Inquiries worker (`inquiries`)

**Backend path:** `backend/app/services/ebay_workers/inquiries_worker.py` → `EbayService.sync_postorder_inquiries`

**Primary eBay API calls (Post-Order API):**

- `GET /post-order/v2/inquiry/search`
  - Main search for inquiries; worker window is currently metadata for logging/cursor.
- `GET /post-order/v2/inquiry/{inquiryId}`
  - Per-inquiry detail used to enrich records before upserting into `ebay_inquiries`.

**Data covered:** buyer inquiries (pre-case disputes), exposed as `kind = 'inquiry'` in the unified Cases grid.

---

## Active inventory worker (`active_inventory`)

**Backend path:** `backend/app/services/ebay_workers/active_inventory_worker.py` → `EbayService.sync_active_inventory_report`

**Primary eBay API calls (Trading API, XML via `https://api.ebay.com/ws/api.dll`):**

- `GetMyeBaySelling` with `<ActiveList>` block
  - Paginated via `<Pagination>` (EntriesPerPage/PageNumber).

**Data covered:** full snapshot of active listings into `ebay_active_inventory`.

---

## Buyer / purchases worker (`buyer`)

**Backend path:** `backend/app/services/ebay_workers/purchases_worker.py` → `EbayService.get_purchases`

**Primary eBay API calls (Trading API, XML via `https://api.ebay.com/ws/api.dll`):**

- `GetMyeBayBuying`
  - Paginated via `<Pagination>` (EntriesPerPage/PageNumber).

**Data covered:** BUYING-side purchases into `ebay_buyer`.

---

## Disputes sync (non-worker helper)

**Backend path:** `EbayService.sync_all_disputes` (not currently its own worker family)

**Primary eBay API calls (Fulfillment API):**

- `POST /sell/fulfillment/v1/payment_dispute_summary/search`

**Data covered:** payment disputes into `ebay_disputes`, included in the unified Cases & Disputes grid.
