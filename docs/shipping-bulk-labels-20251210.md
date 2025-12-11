# Bulk Shipping & Labels (2025-12-10)

## Data model

- `shipping_batches`: batches for bulk label purchases (`id`, `labels_count`, `total_cost`, `currency`, `status` = DRAFT/PURCHASING/PURCHASED/FAILED, `notes`, `created_at`, `updated_at`, `created_by`).
- `shipping_labels`: extended with batch + line-level metadata:
  - Linkage: `batch_id`, `order_id`, `order_line_item_id`, `legacy_transaction_id`, `inventory_id`, `item_id`, `sku`, `storage_id`, `quantity`.
  - Package: `weight_oz`, `length_in`, `width_in`, `height_in`.
  - Service: `carrier_code`, `service_code`, `label_status` (PENDING/RATED/PURCHASING/PURCHASED/FAILED), `label_pdf_url`, `label_zpl_url`.
  - Cost/track: `label_cost_amount`, `label_cost_currency`, `tracking_number`, `provider[_shipment_id]`, `label_url`, `label_file_type`.
- `inventory`: added `item_id` column + FIFO index `idx_inventory_item_id_created` for deterministic picks.

Indexes were added for batch, inventory, and order/line lookups on `shipping_labels`.

## Candidate selection (FIFO)

Endpoint: `GET /api/shipping/bulk/candidates`

Rules:
- Source: `order_line_items` joined to `ebay_orders`.
- Payment/fulfillment: `order_payment_status` in (`PAID`, `PAID_PENDING`, `PAID_PENDING_RELEASE`, `COMPLETED`) and `order_fulfillment_status` not `FULFILLED/CANCELLED`.
- Line not already labeled: no `shipping_labels` row for the order/line (non-voided).
- Inventory match: `inventory.item_id` = line `legacyItemId/itemId` (from `raw_payload`), quantity > 0, not already bound to an active label; FIFO by `rec_created`.
- Returns per-line inventory pick plus order + buyer + ship-to and inventory storage info. Supports pagination and search (order_id / sku / storage_id).

## Rates & purchase endpoints

- `POST /api/shipping/bulk/rates`
  - Input: array of lines `{ orderId, orderLineItemId, inventoryId, weightOz, lengthIn?, widthIn?, heightIn?, quantity? }`.
  - Output: rates per line (carrier/service/price/ETA) via provider abstraction (currently `FakeShippingRateProvider`; eBay Labels provider slot ready).

- `POST /api/shipping/bulk/purchase`
  - Input: `{ batchId?, selections: [{ orderId, orderLineItemId, inventoryId, carrierCode, serviceCode, serviceName, amount, currency, weightOz, lengthIn?, widthIn?, heightIn?, quantity? }] }`.
  - Behavior:
    - Creates/updates `shipping_batches` (status `PURCHASING` → `PURCHASED`).
    - Purchases labels via provider, writes `shipping_labels` with batch + inventory + cost + tracking, sets `label_status=PURCHASED`.
    - Decrements `inventory.quantity` (best-effort) and records total batch cost.

## UI: `/admin/shipping/bulk`

- Filters/search bar.
- Table of candidates with checkboxes, order/buyer/item/storage/ship-to columns.
- Per-line package inputs (weight/dims), rate tabs by carrier with radio select.
- Actions: “Get rates”, “Purchase labels”; summary shows selected count and estimated total.

## Verification checklist

- Migration: run Supabase SQL (`20251210120000_bulk_shipping.sql`) and confirm tables/columns/indexes created.
- Candidates: test with an order that has multiple inventory rows; verify FIFO pick and exclusion after label creation.
- Rates: request rates with weight/dims; ensure responses per line.
- Purchase: create batch, verify `shipping_labels` rows (with inventory_id, order_id, tracking_number, cost), batch totals, and inventory quantity decrement; candidate should disappear after purchase.

## Follow-ups / gaps

- Provider: swap `FakeShippingRateProvider` with real eBay Labels integration; wire real ship-from address and to-address mapping.
- Inventory reservations: consider explicit reservation flag to avoid concurrent picks.
- Tests: add DB-backed tests covering candidate selection, rate quoting, and purchase happy path/duplicate protection once test DB harness is available.




