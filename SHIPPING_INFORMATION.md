# Shipping Information

This document describes the Phase 1 **SHIPPING** module in the eBay Connector App: data model, backend APIs, frontend UI, and extension points.

---

## 1. High-level overview

The SHIPPING module provides internal infrastructure for bulk shipping workflows inside the eBay Connector App. Phase 1 focuses on:

- Normalized shipping tables in Postgres (via SQLAlchemy + Alembic).
- FastAPI endpoints under `/api/shipping` for managing shipping jobs, packages, labels, and status logs.
- A stubbed provider abstraction for shipping rates and labels (no real carrier integration yet).
- A new frontend `ShippingPage` with four tabs:
  - **Awaiting shipment** – NEW/PICKING jobs, bulk actions.
  - **Shipping (scanner)** – warehouse scanner view for status updates.
  - **Status table** – monitoring of non-SHIPPED jobs.
  - **Labels** – list and manage shipping labels.

Phase 1 intentionally does **not** integrate with eBay Logistics, Shippo, or other label providers. Labels can be entered manually; the provider layer is ready for future integration.

---

## 2. Data model (Postgres + SQLAlchemy)

All SHIPPING-related models live in:

- `backend/app/models_sqlalchemy/models.py`

The corresponding migration is:

- `backend/alembic/versions/20251121_shipping_tables.py`

### 2.1 Enums

Defined in SQLAlchemy and mapped to Postgres enums:

- **`ShippingJobStatus`** (`shipping_job_status`)
  - `NEW` – job created, not yet in the warehouse flow.
  - `PICKING` – warehouse is picking / staging items.
  - `PACKED` – job is packed ("boxed").
  - `SHIPPED` – shipment handed off to carrier.
  - `CANCELLED` – job cancelled.
  - `ERROR` – error state (e.g. provider or data failure).

- **`ShippingLabelProvider`** (`shipping_label_provider`)
  - `EBAY_LOGISTICS` – reserved for future direct eBay Logistics integration.
  - `EXTERNAL` – generic external provider (e.g. Shippo, EasyPost, etc.).
  - `MANUAL` – manually entered labels (Phase 1).

- **`ShippingStatusSource`** (`shipping_status_source`)
  - `WAREHOUSE_SCAN` – changes from the scanner UI / warehouse devices.
  - `API` – programmatic / system-driven changes.
  - `MANUAL` – manual changes via UI or ad-hoc tools.

### 2.2 `ShippingJob` → table `shipping_jobs`

Represents a logical shipping job (what we show in “Awaiting shipment” and “Status”):

- `id: String(36)` – UUID primary key (string form).
- `ebay_account_id: String(36)` – FK to `ebay_accounts.id`, nullable, on delete `SET NULL`.
- `ebay_order_id: Text` – eBay order ID.
- `ebay_order_line_item_ids: JSONB` – list of line item IDs associated with this job.
- `buyer_user_id: Text` – buyer username (e.g. eBay login).
- `buyer_name: Text` – buyer full name.
- `ship_to_address: JSONB` – raw structured shipping address from eBay.
- `warehouse_id: Text` – warehouse identifier (string, not FK yet).
- `storage_ids: JSONB` – list of storage locations used for picking (bins, shelves, etc.).
- `status: Enum(ShippingJobStatus)` – current status; **indexed**; server default `NEW`.
- `label_id: String(36)` – optional pointer to primary label for this job. **Not** a DB FK to avoid circular constraints with `shipping_labels`; application-level only.
- `paid_time: DateTime(timezone=True)` – paid/creation time for the order (used for sorting/aging).
- `created_at: DateTime(timezone=True)` – server default `now()`.
- `updated_at: DateTime(timezone=True)` – server default `now()`; updated on changes.
- `created_by: String(36)` – FK to `users.id`, nullable, on delete `SET NULL`.

Indexes:

- `idx_shipping_jobs_status_warehouse` on `(status, warehouse_id)` – fast filtering by status + warehouse.
- `idx_shipping_jobs_ebay_order_id` on `ebay_order_id` – de-duplication / lookup by order.

Relationships (SQLAlchemy-level):

- `packages: List[ShippingPackage]` – all packages for this job.
- `label: ShippingLabel | None` – primary label (via `ShippingLabel.shipping_job_id` and/or `label_id`).
- `status_logs: List[ShippingStatusLog]` – ordered status history.

### 2.3 `ShippingPackage` → table `shipping_packages`

Represents a physical package (box, envelope, pallet) attached to a job.

- `id: String(36)` – UUID primary key.
- `shipping_job_id: String(36)` – FK to `shipping_jobs.id`, on delete `CASCADE`; **indexed** (`ix_shipping_packages_job_id`).
- `combined_for_buyer: Boolean` – `True` if it combines multiple orders for a buyer; default `false`.
- `weight_oz: Numeric(10, 2)` – weight in ounces.
- `length_in`, `width_in`, `height_in: Numeric(10, 2)` – package dimensions in inches.
- `package_type: Text` – free-form type (`BOX`, `ENVELOPE`, etc.).
- `carrier_preference: Text` – free-form hint (`USPS`, `UPS`, etc.).
- `notes: Text` – additional internal notes.
- `created_at`, `updated_at: DateTime(timezone=True)` – timestamps (default `now()`).

Currently we use **at most one package per job** in Phase 1 (the first one). Schema allows multiple for future complex packaging.

### 2.4 `ShippingLabel` → table `shipping_labels`

Metadata for a purchased (or manually entered) label.

- `id: String(36)` – UUID primary key.
- `shipping_job_id: String(36)` – FK to `shipping_jobs.id`, on delete `CASCADE`; indexed.
- `provider: Enum(ShippingLabelProvider)` – `EBAY_LOGISTICS`, `EXTERNAL`, or `MANUAL`.
- `provider_shipment_id: Text` – provider-specific shipment ID, if any.
- `tracking_number: Text` – tracking number; **indexed** (`ix_shipping_labels_tracking_number`).
- `carrier: Text` – e.g. `USPS`, `UPS`, `FedEx`.
- `service_name: Text` – e.g. `Priority Mail`, `Ground Advantage`.
- `label_url: Text` – URL to the label PDF/PNG/etc.
- `label_file_type: Text` – file type (e.g. `pdf`, `zpl`).
- `label_cost_amount: Numeric(12, 2)` – cost.
- `label_cost_currency: CHAR(3)` – ISO currency, default `USD`.
- `purchased_at: DateTime(timezone=True)` – when label was purchased (or entered).
- `voided: Boolean` – logical void flag; default `false`; **indexed**.
- `created_at`, `updated_at: DateTime(timezone=True)` – timestamps.

Indexes:

- `ix_shipping_labels_tracking_number` on `tracking_number`.
- `idx_shipping_labels_provider_shipment` on `(provider, provider_shipment_id)` – fast lookup by provider ID.

### 2.5 `ShippingStatusLog` → table `shipping_status_log`

Audit log of job status transitions.

- `id: String(36)` – UUID primary key.
- `shipping_job_id: String(36)` – FK to `shipping_jobs.id`, on delete `CASCADE`.
- `status_before: Enum(ShippingJobStatus)` – previous status, nullable (e.g. first transition from `None` → `NEW`).
- `status_after: Enum(ShippingJobStatus)` – new status, non-null.
- `source: Enum(ShippingStatusSource)` – `WAREHOUSE_SCAN`, `API`, or `MANUAL`; default `MANUAL`.
- `reason: Text` – optional human-readable reason.
- `user_id: String(36)` – FK to `users.id`, nullable.
- `created_at: DateTime(timezone=True)` – timestamp (default `now()`).

Index:

- `idx_shipping_status_log_job_created` on `(shipping_job_id, created_at)` – for quickly loading history per job.

---

## 3. Alembic migration: `20251121_shipping_tables`

File: `backend/alembic/versions/20251121_shipping_tables.py`

- **Revision ID**: `shipping_tables_20251121`
- **Down revision**: `ebay_events_processing_20251121`

`upgrade()` does:

1. Obtain a DB connection and inspector.
2. Create three Postgres enums unconditionally but with `checkfirst=True`, so it is idempotent:
   - `shipping_job_status`
   - `shipping_label_provider`
   - `shipping_status_source`
3. Create tables `shipping_jobs`, `shipping_labels`, `shipping_packages`, and `shipping_status_log` if they don’t already exist, with all columns and FKs described above.
4. Create indexes for these tables (only if missing).

`downgrade()`:

1. Drops `shipping_status_log` (and its index), then `shipping_packages`, then `shipping_labels`, then `shipping_jobs`.
2. Attempts to drop the three enums using `sa.Enum(name=enum_name).drop(conn, checkfirst=True)` inside a `try/except` (best-effort).

This migration is designed to be **safe and re-runnable** in environments where some objects may already exist.

---

## 4. Backend API: FastAPI router `shipping`

File: `backend/app/routers/shipping.py`

Router base:

- Prefix: `/api/shipping`
- Tags: `["shipping"]`

Common dependencies:

- `get_db()` for a SQLAlchemy `Session` (Postgres).
- `get_current_user()` for auth and org scoping.

All queries are scoped to the authenticated user’s org using `EbayAccount.org_id == current_user.id`, consistent with other modules.

### 4.1 Helper serialization

Inside `shipping.py` there are small helpers to standardize responses:

- `_serialize_ship_to_summary(addr)` – builds a short one-line string from the `ship_to_address` JSON (e.g. `Name, City, State, Postal, Country`).
- `_job_to_row(job)` – converts a `ShippingJob` (and optional attached `ShippingLabel`) to a dict used by listing endpoints. Fields include job IDs, buyer info, storage IDs, ship-to summary, status, label tracking, timestamps, etc.

These helpers ensure consistent shapes across `/awaiting` and `/jobs`.

### 4.2 `GET /api/shipping/awaiting`

Lists jobs that are **awaiting shipment**.

- **Method**: `GET`
- **Path**: `/api/shipping/awaiting`
- **Query params** (subset):
  - `limit: int` – default 100.
  - `offset: int` – default 0.
  - `include_picking: bool` – include `PICKING` status along with `NEW`.
  - `warehouse_id: str | None` – optional filter.
  - `ebay_account_id: str | None` – optional filter.
  - `search: str | None` – text search across `ebay_order_id`, `buyer_user_id`, `buyer_name`, and stringified `storage_ids`.

- **Behavior**:
  - Filters `ShippingJob` by status (`NEW` and optionally `PICKING`).
  - Joins to `EbayAccount` to enforce org scoping.
  - Orders by `paid_time DESC`, then `created_at DESC`.
  - Returns `{ rows: [job_row...], limit, offset, total }`.

Used by the **Awaiting shipment** tab.

### 4.3 `POST /api/shipping/jobs/from-orders`

Upserts `ShippingJob` rows from order information.

- **Method**: `POST`
- **Path**: `/api/shipping/jobs/from-orders`
- **Body** (simplified):
  - `{ "orders": [ { "ebay_account_id?", "ebay_order_id", "ebay_order_line_item_ids"? } ] }`

- **Behavior**:
  - For each order DTO:
    - Queries the `ebay_orders` table via raw SQL to get normalized order data (JSON `order_data`, `creation_date`, `buyer_username`, etc.).
    - Extracts buyer info and `shipTo` address from the JSON if present.
    - Checks if a `ShippingJob` already exists for `(ebay_account_id, ebay_order_id)`.
      - If not, creates a new job with `status=NEW` and sets buyer, address, storage IDs (if any), and `paid_time`.
      - If yes, updates fields like line item IDs, buyer info, and `paid_time` if missing; does **not** regress the status.
  - Commits at the end.
  - Returns summary `{ created, updated, total }`.

This endpoint is used by worker processes / ingestion logic, not directly by the UI.

### 4.4 `POST /api/shipping/packages/bulk-update`

Bulk upserts package information for multiple jobs.

- **Method**: `POST`
- **Path**: `/api/shipping/packages/bulk-update`
- **Body**: list of items
  - Each `{ shippingJobId, weightOz?, lengthIn?, widthIn?, heightIn?, packageType?, carrierPreference? }`.

- **Behavior**:
  - For each item:
    - Loads `ShippingJob` by ID; if not found, skips.
    - Loads the first `ShippingPackage` for that job; if none exists, creates one.
    - Updates any provided fields (others left unchanged).
  - Commits once.
  - Returns `{ updated }` (number of jobs/packages modified).

Used by the **Edit package** modal in the Awaiting tab.

### 4.5 `POST /api/shipping/jobs/{job_id}/status`

Change a job’s status and write a status log entry.

- **Method**: `POST`
- **Path**: `/api/shipping/jobs/{job_id}/status`
- **Body**: e.g.
  - `{ "status": "PICKING", "reason"?: str, "source"?: "WAREHOUSE_SCAN" | "API" | "MANUAL" }`

- **Behavior**:
  - Loads `ShippingJob` by `job_id`; if missing, returns 404.
  - Stores `before = job.status`.
  - Sets `job.status = payload.status`, updates `updated_at`.
  - Inserts `ShippingStatusLog` with `status_before`, `status_after`, `source` (default `MANUAL`), `reason`, and `user_id` (current user).
  - Commits and returns the updated job row (`_job_to_row`).

Used by:

- **Awaiting** tab: `Send to Shipping` → `PICKING`.
- **Shipping (scanner)** tab: `PACKED` and `SHIPPED` transitions.
- **Manual label** flow (indirectly when label is created and status is SHIPPED).

### 4.6 `POST /api/shipping/labels/manual`

Create a label of provider `MANUAL` and mark the job as shipped.

- **Method**: `POST`
- **Path**: `/api/shipping/labels/manual`
- **Body** (simplified):
  - `{ "shippingJobId", "trackingNumber", "carrier", "serviceName", "labelUrl"?, "labelCostAmount"?, "labelCostCurrency"? }`

- **Behavior**:
  - Loads `ShippingJob`; 404 if missing.
  - Creates a `ShippingLabel` with `provider=MANUAL` and given fields.
    - `label_url` defaults to `"about:blank"` if not provided.
    - `label_cost_currency` defaults to `"USD"`.
  - Sets `job.label_id` to the new label’s ID and moves `job.status` to `SHIPPED`, updating `updated_at`.
  - Writes a `ShippingStatusLog` entry with `source=API` and a reason like “Manual label created”.
  - Commits and returns serialized label data.

This is the main label-creation surface for Phase 1.

### 4.7 `GET /api/shipping/jobs`

General-purpose job listing.

- **Method**: `GET`
- **Path**: `/api/shipping/jobs`
- **Query params** (subset):
  - `status: ShippingJobStatus | None` – filter by a specific status.
  - `exclude_status: ShippingJobStatus | None` – exclude a status (e.g. `SHIPPED`).
  - `warehouse_id`, `ebay_account_id`, `search` (same semantics as `/awaiting`).
  - `limit`, `offset`.

- **Behavior**:
  - Filters `ShippingJob` based on params.
  - Enforces org scoping.
  - Orders by `created_at DESC`.
  - Returns `{ rows, limit, offset, total }`, using `_job_to_row`.

Used by **Shipping (scanner)** and **Status** tabs.

### 4.8 `GET /api/shipping/labels`

List shipping labels.

- **Method**: `GET`
- **Path**: `/api/shipping/labels`
- **Query params** (subset):
  - `provider: ShippingLabelProvider | None`.
  - `carrier: str | None`.
  - `voided: bool | None`.
  - `limit`, `offset`.

- **Behavior**:
  - Joins `ShippingLabel` → `ShippingJob` → `EbayAccount` to enforce org scoping.
  - Applies filters.
  - Orders by `purchased_at DESC`, then `created_at DESC`.
  - Returns `{ rows, limit, offset, total }` with label info (including cost and voided flag).

Used by the **Labels** tab.

### 4.9 `POST /api/shipping/labels/{label_id}/void`

Toggle a label’s `voided` flag.

- **Method**: `POST`
- **Path**: `/api/shipping/labels/{label_id}/void`
- **Body**: `{ "voided": bool }`.

- **Behavior**:
  - Loads the label by ID, but only if its job’s account is in the current user’s org.
  - Sets `label.voided = payload.voided` and updates `updated_at`.
  - Commits and returns updated label.

Used by the **Void / Unvoid** button in the Labels tab.

---

## 5. Shipping provider abstraction

File: `backend/app/services/shipping_provider.py`

This module defines the interface for rate and label providers and a simple fake implementation used for future integration.

### 5.1 Data classes

(Actual implementation uses Python `dataclasses`, not Pydantic.)

- `RateRequest`
  - `shipping_job_id: str`
  - `from_address: dict`
  - `to_address: dict`
  - Optional package fields: `weight_oz`, `length_in`, `width_in`, `height_in`, `package_type`, `carrier_preference`.

- `Rate`
  - `service_code: str`
  - `service_name: str`
  - `carrier: str`
  - `amount: float`
  - `currency: str = "USD"`
  - `estimated_days: int | None`

- `RateSelection`
  - `shipping_job_id: str`
  - `package_id: str | None`
  - `rate: Rate`

- `LabelDetails`
  - Container for information used to fill a `ShippingLabel` (tracking number, service, cost, etc.).

### 5.2 Abstract `ShippingRateProvider`

Defines the interface to implement for real providers:

- `get_rates(self, request: RateRequest) -> list[Rate]`
- `buy_label(self, selection: RateSelection, db: Session) -> ShippingLabel`

### 5.3 `FakeShippingRateProvider`

A stub implementation used for testing / future wiring:

- `get_rates`:
  - Computes a base cost roughly proportional to weight.
  - Returns two fake `Rate` instances (e.g. USPS Priority Mail and USPS Ground Advantage) with different prices and ETAs.

- `buy_label`:
  - Generates a synthetic tracking number (e.g. `"FAKE" + uuid[:12]`).
  - Creates a `ShippingLabel` row in the database with:
    - `provider=ShippingLabelProvider.EXTERNAL`.
    - Placeholder `label_url="about:blank"`.
    - Cost from the selected `Rate`.
    - `purchased_at` set to current time.
  - Commits and returns the ORM label instance.

As of Phase 1, this provider is mostly a **hook for future integrations**; the public API uses `MANUAL` labels.

---

## 6. Frontend: Shipping UI

Main page file:

- `frontend/src/pages/ShippingPage.tsx`

This replaces the previous “coming soon” placeholder with a full tabbed UI built on the app’s design system.

### 6.1 Component structure

- Imports:
  - `FixedHeader` (layout).
  - `api` (`apiClient`) for HTTP requests to `/api/shipping/*`.
  - UI components: `Tabs`, `Card`, `Button`, `Input`, `Checkbox`, `Dialog`.

- Local TypeScript types mirror backend response shapes:
  - `ShippingJobRow` – fields exposed by `_job_to_row` (ID, order info, buyer, ship_to_summary, storage_ids, status, label snippet, timestamps).
  - `ShippingLabelRow` – subset of label info from `/api/shipping/labels`.

The page is a full-height flex column with a fixed header and `Tabs` content below.

### 6.2 Awaiting shipment tab

- Data:
  - Loads from `GET /api/shipping/awaiting` with `limit=100`, `offset=0`, `include_picking=true`, plus optional `search`.
  - Stores jobs, loading flag, error, and a `Set<string>` of selected job IDs.

- Toolbar:
  - Search input: filters by order ID, buyer, or storage ID.
  - `Reload` button.
  - Action buttons:
    - **Edit package** – opens Edit Package dialog; enabled when at least one row is selected.
    - **Create label (manual)** – opens Manual Label dialog; enabled only when **exactly one** row is selected.
    - **Send to Shipping** – moves selected jobs to `PICKING` via status endpoint.

- Table columns (simplified):
  - Checkbox selector.
  - Order (order ID + eBay account ID).
  - Buyer (name + username).
  - Ship to (one-line summary string from backend).
  - Storage (comma-separated `storage_ids`).
  - Status.
  - Tracking (from attached label, if any).
  - Paid time (localized).

- Edit Package dialog:
  - Fields: `weight_oz`, `length_in`, `width_in`, `height_in`, `package_type`, `carrier_preference`.
  - On save:
    - Builds an array of items `{ shippingJobId, ... }` for all selected jobs.
    - Calls `POST /api/shipping/packages/bulk-update`.

- Manual Label dialog:
  - Fields: `tracking_number`, `carrier`, `service`, `label_cost`.
  - On save:
    - Calls `POST /api/shipping/labels/manual` with the single selected job ID.
    - Clears modal state and selection.
    - Refreshes Awaiting jobs, Status jobs, and Labels.

- Send to Shipping:
  - For each selected job ID:
    - Calls `POST /api/shipping/jobs/{id}/status` with `{ status: 'PICKING', source: 'MANUAL', reason: 'Sent to Shipping from UI' }`.
  - Reloads the Awaiting list.

### 6.3 Shipping (scanner) tab

This tab is used by warehouse staff with scanners or keyboards.

- Inputs:
  - `Tracking number` – primary, auto-focused.
  - `Storage` – optional; can also be used to search jobs.

- Search behavior:
  - On Enter in the tracking input, or clicking `Find job`, it calls:
    - `GET /api/shipping/jobs?limit=10&offset=0&search=<tracking_or_storage>`.
  - If any rows are returned, the first job is displayed.
  - If no rows, a user-friendly “No matching job found” message is shown.

- Details view:
  - Displays key fields from `ShippingJobRow`: order ID, buyer name + username, ship-to summary, storage IDs, current status.

- Actions:
  - **Mark as PACKED (Box)** – `POST /api/shipping/jobs/{id}/status` with `{ status: 'PACKED', source: 'WAREHOUSE_SCAN' }`.
  - **Mark as SHIPPED** – same endpoint with `{ status: 'SHIPPED', source: 'WAREHOUSE_SCAN' }`.
  - After each update, the component refreshes Status jobs and Awaiting jobs to keep tabs in sync.

### 6.4 Status table tab

Monitoring view for all non-shipped jobs.

- Data source:
  - `GET /api/shipping/jobs?exclude_status=SHIPPED&limit=200&offset=0`.

- Table columns:
  - Job ID (UUID, monospaced).
  - Order ID.
  - Buyer (name or username).
  - Storage IDs.
  - Status.
  - Tracking (from attached label, if any).
  - Paid time.

- Provides a `Reload` button to refresh data.

### 6.5 Labels tab

History and control surface for labels.

- Data source:
  - `GET /api/shipping/labels?limit=200&offset=0`.

- Table columns:
  - Created (from `purchased_at`).
  - Provider.
  - Carrier.
  - Service.
  - Tracking number.
  - Cost (formatted as `CURRENCY amount`).
  - Status (`ACTIVE` or `VOIDED`).
  - Actions.

- Actions per label row:
  - **Download** – if `label_url` is non-empty, opens in a new tab.
  - **Void / Unvoid** – toggles `voided` by calling `POST /api/shipping/labels/{id}/void` with `{ voided: !current }`, then reloads the list.

---

## 7. Operational notes and future work

### 7.1 Migrations / deployment

- The SHIPPING migration depends on `ebay_events_processing_20251121` being present in the Alembic history.
- The enum creation in `20251121_shipping_tables` uses `checkfirst=True` and does **not** rely on dialect-specific helpers, making it safe across environments.
- On a fresh database, applying all migrations will create:
  - Enums: `shipping_job_status`, `shipping_label_provider`, `shipping_status_source`.
  - Tables: `shipping_jobs`, `shipping_packages`, `shipping_labels`, `shipping_status_log`.

### 7.2 Scope and limitations (Phase 1)

- No real carrier integration yet (no live rates, no automatic label purchase).
  - All labels are created via `/api/shipping/labels/manual`.
  - `FakeShippingRateProvider` exists as a stub but is not wired into public APIs.
- Grouping multiple orders per buyer into combined packages is not yet implemented in UI or router logic; schema (`combined_for_buyer`) allows this later.
- Scanner search currently uses the generic `search` parameter on `/jobs`; it does **not** yet search by tracking in `ShippingLabel` directly. That can be extended by joining labels and searching `tracking_number`.

### 7.3 Future integration points

- **Rates & labels**:
  - Implement real providers (`EbayLogisticsProvider`, `ShippoProvider`, etc.) that satisfy `ShippingRateProvider`.
  - Expose new endpoints such as `/api/shipping/rates` and `/api/shipping/labels/buy` that:
    - Call `get_rates` / `buy_label`.
    - Create labels and update jobs similarly to the manual flow.

- **Fulfillment + finances**:
  - When a label is created (especially via real providers), call eBay’s `createShippingFulfillment` and log shipping label costs into the finances tables as `SHIPPING_LABEL` transactions.

- **Warehouse UX**:
  - Add hotkeys, sound cues, and better error feedback in the Shipping (scanner) tab.
  - Add more robust search (tracking, storage, order, SKU) and conflict resolution when multiple jobs match.

---

This document should give future developers and agents enough detail to understand how the SHIPPING module works end-to-end (DB, backend, and frontend) and where to plug in further functionality.