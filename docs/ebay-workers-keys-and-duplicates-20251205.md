# eBay Worker Table Analysis & Deduplication Report
**Date:** 2025-12-05

This document provides a detailed analysis of the Supabase/Postgres tables used by the 10 eBay API workers. It covers table coverage, schema introspection, recommended business keys based on eBay Developer documentation, and a read-only diagnostic of current duplicates.

## Summary of Critical Findings

> [!IMPORTANT]
> **CRITICAL BUG: Missing `ebay_orders` Table**
> The `OrdersWorker` attempts to write to a table named `ebay_orders`, but this table **does not exist** in the database. This means order data is currently **not being persisted**.

> [!WARNING]
> **Duplicates Detected**
> - **`ebay_finances_fees`**: 22 duplicate groups found (44 rows).
> - **`ebay_active_inventory`**: 8 duplicate groups found (16 rows).

---

## 1. ebay_orders

### 1. Worker & API Source
- **Owner Worker:** `OrdersWorker` (via `EbayService.sync_all_orders` -> `PostgresEbayDatabase.batch_upsert_orders`)
- **eBay API:** Fulfillment API (Orders)
- **Main External IDs:** `orderId`

### 2. Structure Snapshot
- **Status:** **MISSING**
- **Row Count:** 0
- **Issue:** The code explicitly attempts `INSERT INTO ebay_orders ...`, but the table is missing from the schema.

### 3. Recommended Business Keys
- **Primary Business Key:**
  - Columns: `(order_id, user_id)`
  - Rationale: `orderId` is unique globally on eBay. We scope by `user_id` (organization) to support multi-tenant data, although `orderId` should theoretically be unique across users too. The code currently uses this pair for `ON CONFLICT`.

### 4. Duplicate Diagnostics
- **Status:** N/A (Table missing)

### 5. Notes / Next Steps
- **Action Required:** Create the `ebay_orders` table immediately using the schema defined in `PostgresEbayDatabase.upsert_order`.

---

## 2. order_line_items

### 1. Worker & API Source
- **Owner Worker:** `OrdersWorker`
- **eBay API:** Fulfillment API (Order Line Items)
- **Main External IDs:** `lineItemId`, `orderId`

### 2. Structure Snapshot
- **Row Count:** 7,896
- **PK:** `id` (BIGINT)
- **Unique Constraints:** `(order_id, line_item_id)`

### 3. Recommended Business Keys
- **Primary Business Key:**
  - Columns: `(order_id, line_item_id)`
  - Rationale: A `lineItemId` is unique within an `orderId`. Together they uniquely identify a purchased item line.

### 4. Duplicate Diagnostics
- **Key Used:** `(order_id, line_item_id)`
- **Duplicate Groups:** 0
- **Rows in Duplicates:** 0

---

## 3. ebay_transactions

### 1. Worker & API Source
- **Owner Worker:** `TransactionsWorker`
- **eBay API:** Trading API (`GetMyeBaySelling` / `GetOrders`) or legacy Transaction calls.
- **Main External IDs:** `transactionId`, `orderId`

### 2. Structure Snapshot
- **Row Count:** 11,913
- **PK:** `(transaction_id, user_id)`

### 3. Recommended Business Keys
- **Primary Business Key:**
  - Columns: `(transaction_id, user_id)`
  - Rationale: `transactionId` is unique for a sale (order line item) in the Trading API. Scoped by `user_id`.

### 4. Duplicate Diagnostics
- **Key Used:** `(transaction_id, user_id)`
- **Duplicate Groups:** 0
- **Rows in Duplicates:** 0

---

## 4. ebay_finances_transactions

### 1. Worker & API Source
- **Owner Worker:** `FinancesWorker`
- **eBay API:** Finances API
- **Main External IDs:** `transactionId`, `transactionType`

### 2. Structure Snapshot
- **Row Count:** 11,645
- **PK:** `id` (BIGINT)
- **Unique Constraints:** None visible in introspection, but code likely relies on logic.

### 3. Recommended Business Keys
- **Primary Business Key:**
  - Columns: `(transaction_id, transaction_type, ebay_account_id)`
  - Rationale: In Finances API, a `transactionId` can appear multiple times with different `transactionType` (e.g., `SALE`, `REFUND`). Scoping by `ebay_account_id` ensures separation between linked accounts.

### 4. Duplicate Diagnostics
- **Key Used:** `(transaction_id, transaction_type, ebay_account_id)`
- **Duplicate Groups:** 0
- **Rows in Duplicates:** 0

---

## 5. ebay_finances_fees

### 1. Worker & API Source
- **Owner Worker:** `FinancesWorker` (side-loaded with transactions)
- **eBay API:** Finances API
- **Main External IDs:** `transactionId` (parent), `feeType`

### 2. Structure Snapshot
- **Row Count:** 19,559
- **PK:** `id` (BIGINT)

### 3. Recommended Business Keys
- **Primary Business Key:**
  - Columns: `(transaction_id, fee_type, amount_value, ebay_account_id)`
  - Rationale: Fees don't always have a unique ID in the API response. They are often nested under a transaction. The combination of the parent transaction, the fee type (e.g., `FINAL_VALUE_FEE`), and the amount is the strongest available proxy for uniqueness.

### 4. Duplicate Diagnostics
- **Key Used:** `(transaction_id, fee_type, amount_value, ebay_account_id)`
- **Duplicate Groups:** 22
- **Rows in Duplicates:** 44
- **Example:**
  - **Key:** `transaction_id=25-13747-95262`, `fee_type=FINAL_VALUE_FEE`, `amount=1.92`
  - **Rows:**
    - ID: 138347, Created: 2025-11-30T17:40:15
    - ID: 138348, Created: 2025-11-30T17:40:15
  - **Note:** Timestamps are identical, suggesting a double-insert during a single sync run.

---

## 6. ebay_disputes

### 1. Worker & API Source
- **Owner Worker:** `DisputesWorker`
- **eBay API:** Fulfillment API (Payment Disputes)
- **Main External IDs:** `paymentDisputeId`

### 2. Structure Snapshot
- **Row Count:** 0
- **PK:** `(dispute_id, user_id)`

### 3. Recommended Business Keys
- **Primary Business Key:**
  - Columns: `(dispute_id, user_id)`
  - Rationale: `paymentDisputeId` is the unique identifier for a payment dispute.

### 4. Duplicate Diagnostics
- **Key Used:** `(dispute_id, user_id)`
- **Duplicate Groups:** 0

---

## 7. ebay_cases

### 1. Worker & API Source
- **Owner Worker:** `CasesWorker`
- **eBay API:** Post-Order API (Case Management)
- **Main External IDs:** `caseId`

### 2. Structure Snapshot
- **Row Count:** 37
- **PK:** `(case_id, user_id)`

### 3. Recommended Business Keys
- **Primary Business Key:**
  - Columns: `(case_id, user_id)`
  - Rationale: `caseId` is unique for Post-Order cases.

### 4. Duplicate Diagnostics
- **Key Used:** `(case_id, user_id)`
- **Duplicate Groups:** 0

---

## 8. ebay_inquiries

### 1. Worker & API Source
- **Owner Worker:** `InquiriesWorker`
- **eBay API:** Post-Order API (Inquiries)
- **Main External IDs:** `inquiryId`

### 2. Structure Snapshot
- **Row Count:** 47
- **PK:** `(inquiry_id, user_id)`

### 3. Recommended Business Keys
- **Primary Business Key:**
  - Columns: `(inquiry_id, user_id)`
  - Rationale: `inquiryId` is unique for Post-Order inquiries.

### 4. Duplicate Diagnostics
- **Key Used:** `(inquiry_id, user_id)`
- **Duplicate Groups:** 0

---

## 9. ebay_returns

### 1. Worker & API Source
- **Owner Worker:** `ReturnsWorker`
- **eBay API:** Post-Order API (Returns)
- **Main External IDs:** `returnId`

### 2. Structure Snapshot
- **Row Count:** 78
- **PK:** `(return_id, user_id)`

### 3. Recommended Business Keys
- **Primary Business Key:**
  - Columns: `(return_id, user_id)`
  - Rationale: `returnId` is unique for Post-Order returns.

### 4. Duplicate Diagnostics
- **Key Used:** `(return_id, user_id)`
- **Duplicate Groups:** 0

---

## 10. ebay_offers

### 1. Worker & API Source
- **Owner Worker:** `OffersWorker`
- **eBay API:** Negotiation API
- **Main External IDs:** `offerId`

### 2. Structure Snapshot
- **Row Count:** 0
- **PK:** `(offer_id, user_id)`

### 3. Recommended Business Keys
- **Primary Business Key:**
  - Columns: `(offer_id, user_id)`
  - Rationale: `offerId` is unique for an offer.

### 4. Duplicate Diagnostics
- **Key Used:** `(offer_id, user_id)`
- **Duplicate Groups:** 0

---

## 11. ebay_active_inventory

### 1. Worker & API Source
- **Owner Worker:** `ActiveInventoryWorker`
- **eBay API:** Trading API (`GetMyeBaySelling`) or Inventory API
- **Main External IDs:** `SKU`, `ItemID`

### 2. Structure Snapshot
- **Row Count:** 20,683
- **PK:** `id` (INTEGER)

### 3. Recommended Business Keys
- **Primary Business Key:**
  - Columns: `(sku, ebay_account_id)`
  - Rationale: We manage inventory primarily by SKU. Each eBay account should have unique SKUs.
- **Alternative Key:**
  - Columns: `(item_id, ebay_account_id)`
  - Rationale: `ItemID` is eBay's internal unique ID for a listing.

### 4. Duplicate Diagnostics
- **Key Used:** `(sku, ebay_account_id)`
- **Duplicate Groups:** 8
- **Rows in Duplicates:** 16
- **Example:**
  - **Key:** `sku=100000000064584`, `ebay_account_id=...`
  - **Rows:**
    - ID: 20331, ItemID: 397336018311, Last Seen: 2025-12-05
    - ID: 4329, ItemID: 396534305484, Last Seen: 2025-11-25
  - **Note:** These appear to be different ItemIDs for the same SKU, likely due to relisting or multiple active listings for the same product. This might be valid on eBay but violates our "one SKU per account" assumption if we enforce it strictly.

---

## 12. ebay_messages

### 1. Worker & API Source
- **Owner Worker:** `MessagesWorker`
- **eBay API:** Messaging API
- **Main External IDs:** `messageId`

### 2. Structure Snapshot
- **Row Count:** 2,734
- **PK:** `id` (VARCHAR) - *Note: This seems to be an internal UUID, not the eBay message ID.*

### 3. Recommended Business Keys
- **Primary Business Key:**
  - Columns: `(message_id, user_id)`
  - Rationale: `messageId` is the unique eBay identifier.

### 4. Duplicate Diagnostics
- **Key Used:** `(message_id, user_id)`
- **Duplicate Groups:** 0

---

## Conclusion & Next Steps

1.  **Fix `ebay_orders`**: The missing table is a critical blocker for the Orders worker. A migration must be created to define this table matching the code's expectations.
2.  **Cleanup `ebay_finances_fees`**: The 44 duplicate rows should be deduplicated, likely by keeping the most recent one or adding a unique constraint to prevent future occurrences.
3.  **Investigate `ebay_active_inventory`**: The duplicates here (same SKU, different ItemID) suggest multiple listings for the same product. We need to decide if this is allowed or if we should enforce uniqueness by SKU.
