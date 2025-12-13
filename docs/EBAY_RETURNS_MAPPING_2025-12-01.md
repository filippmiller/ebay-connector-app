# eBay Post-Order Returns → `public.ebay_returns` mapping

Date: 2025-12-01

## 1. Source APIs

* **Search:** `GET /post-order/v2/return/search`
* **Detail:** `GET /post-order/v2/return/{returnId}`

For each return, we build a merged payload:

```json
{
  "summary": { /* row from /post-order/v2/return/search */ },
  "detail": { /* payload from /post-order/v2/return/{id} */ }
}
```

This merged object is stored (compact) in `ebay_returns.raw_json` and is the
only source for normalized columns.

## 2. Target table

* **Table:** `public.ebay_returns`
* **Primary key:** `(return_id, user_id)`
* **Per-account uniqueness:** unique index on `(ebay_account_id, return_id)`

Important linkage columns:

* `user_id` – owner/org id in our system.
* `ebay_account_id` – local eBay account PK; distinguishes multiple seller
  accounts in the same org.
* `ebay_user_id` – seller login (e.g. `mil_243`).

## 3. Column → JSON mapping

### Identity & linkage

* **`return_id`**
  * JSON path: `summary.returnId`
  * Notes: logical id of the Post-Order return; unique per account.

* **`order_id`**
  * JSON path: `summary.orderId`
  * Notes: eBay order id (e.g. `26-13721-98548`).

* **`item_id`**
  * JSON path (preferred):
    * `summary.creationInfo.item.itemId`
  * Fallbacks:
    * `detail.itemDetail.itemId`
  * Notes: stored as string even if numeric in JSON.

* **`transaction_id`**
  * JSON path (preferred):
    * `summary.creationInfo.item.transactionId`
  * Fallbacks:
    * `detail.itemDetail.transactionId`
  * Notes: stored as string.

* **`buyer_username`**
  * JSON paths (first non-null):
    * `summary.buyerLoginName`
    * `detail.buyerLoginName`

* **`seller_username`**
  * JSON paths (first non-null):
    * `summary.sellerLoginName`
    * `detail.sellerLoginName`

* **`ebay_user_id`**
  * Value: same as `seller_username` when present, otherwise the
    worker-provided account `ebay_user_id`.
  * Notes: identifies the eBay seller login for joins and display.

* **`ebay_account_id`**
  * Value: local EbayAccount primary key passed in from the worker.

* **`user_id`**
  * Value: owning org/user id (e.g. `account.org_id`) passed into the sync.

### Return type & state

* **`return_type`**
  * JSON paths (first non-null):
    * `summary.currentType` (e.g. `MONEY_BACK`, `REPLACEMENT`)
    * `summary.creationInfo.type`

* **`return_state`**
  * JSON paths (first non-null):
    * `summary.state`
    * `summary.returnState`

### Dates / timestamps

* **`creation_date`**
  * JSON path: `summary.creationInfo.creationDate.value`
  * Parsing: ISO 8601 → timestamptz (UTC).

* **`last_modified_date`**
  * JSON source: `detail.responseHistory[*].creationDate.value`.
  * Mapping: take the **maximum** parsed timestamp across all history entries.
  * Fallback: if `responseHistory` is missing/empty, use `creation_date`.

* **`closed_date`**
  * JSON paths (first non-null):
    * `detail.closeDate.value`
    * `detail.closeDate`
    * `detail.closeInfo.closeDate.value`
    * `detail.closeInfo.closeDate`
  * Notes: if no explicit close timestamp is present, remains `NULL`.

### Reason / comments

* **`reason`**
  * JSON paths:
    * `summary.creationInfo.reasonType`
    * `summary.creationInfo.reason`
  * Mapping logic:
    * Let `r_type = summary.creationInfo.reasonType`.
    * Let `r_code = summary.creationInfo.reason`.
    * If both present: `reason = "{r_type}:{r_code}"` (e.g. `"SNAD:DEFECTIVE_ITEM"`).
    * If only `r_type`: `reason = r_type`.
    * If only `r_code`: `reason = r_code`.
    * If both missing: `reason = NULL`.

### Money / amounts

* **`total_amount_value`**, **`total_amount_currency`**
  * Preferred source:
    * `summary.sellerTotalRefund.estimatedRefundAmount`
  * First fallback:
    * `summary.buyerTotalRefund.estimatedRefundAmount`
  * Second fallback:
    * `detail.refundInfo.estimatedRefundDetail.itemizedRefundDetails[0].estimatedAmount`
  * Each amount object is expected to have:
    * `value` – parsed as `Numeric(12, 2)`.
    * `currency` – stored as `VARCHAR(10)`.
  * Notes: this is the main seller refund amount used for analytics.

### Raw JSON

* **`raw_json`**
  * Value: `json.dumps({"summary": summary, "detail": detail}, separators=(",", ":"))`
  * Notes: always stores the full merged payload; used for debugging,
    backfills, and future schema extensions.

### Audit columns

* **`created_at`**
  * On insert: set to current UTC timestamp from the worker process.
  * On conflict: left unchanged (only `updated_at` is updated).

* **`updated_at`**
  * On insert: set to current UTC timestamp.
  * On update: always overwritten with the latest UTC timestamp.

## 4. Upsert behaviour

Uniqueness:

* **Primary key:** `(return_id, user_id)` – ensures per-tenant isolation.
* **Unique index:** `(ebay_account_id, return_id)` – ensures a single row per
  return id and eBay account.

Upsert key and behaviour:

* Upsert uses `ON CONFLICT (return_id, user_id)`.
* On conflict, the following columns are updated:
  * `ebay_account_id`, `ebay_user_id`
  * `order_id`, `item_id`, `transaction_id`
  * `return_state`, `return_type`, `reason`
  * `buyer_username`, `seller_username`
  * `total_amount_value`, `total_amount_currency`
  * `creation_date`, `last_modified_date`, `closed_date`
  * `raw_json`, `updated_at`
* `created_at` is **not** updated on conflict (insert-only).

## 5. Worker integration (summary)

* The Post-Order Returns worker calls `EbayService.sync_postorder_returns` with
  `user_id`, `ebay_account_id`, and `ebay_user_id` for the account.
* `sync_postorder_returns`:
  * Calls `GET /post-order/v2/return/search` to obtain summary rows.
  * For each summary, calls `GET /post-order/v2/return/{id}` for detail
    (best-effort; falls back to summary-only on error).
  * Builds `payload = {"summary": summary, "detail": detail}`.
  * Calls `PostgresEbayDatabase.upsert_return(user_id, payload, ebay_account_id, ebay_user_id, return_id)`.
* The worker window (`window_from` / `window_to`) is used for logging and
  cursor advancement; deduplication is handled by the upsert and overlap.

## 6. Testing notes

The unit test `backend/tests/test_ebay_returns_mapping.py` uses the example
payload from this document to assert that:

* Identifiers and usernames are mapped as expected.
* `return_type` and `return_state` reflect `summary.currentType` and
  `summary.state`.
* `reason` contains both `reasonType` and `reason` (e.g. `"SNAD:DEFECTIVE_ITEM"`).
* `total_amount_value` / `total_amount_currency` come from
  `summary.sellerTotalRefund.estimatedRefundAmount`.
* Timestamps are parsed into datetimes.
* `raw_json` contains the full merged payload, including nested blocks like
  `returnShipmentInfo`.
