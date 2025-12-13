# SQ Catalog (SKU) Module

This document summarizes the new SQ catalog implementation that replaces the
legacy `tbl_parts_detail` ("SQ catalog") UI and table.

## 1. Database & Models

### 1.1. Core table: `sq_items`

New Postgres table that can store **all** fields from legacy
`[DB_A28F26_parts].[dbo].[tbl_parts_detail]` plus a few extra columns used by
the modern app.

SQLAlchemy model: `app.models_sqlalchemy.models.SqItem`.

Key points:

- `id` (`BIGINT`, PK, autoincrement) – maps legacy `[ID]`.
- `part_id` (`BIGINT`) – `[Part_ID]`.
- `sku` (`String(100)`) – `[SKU]`.
- `sku2` (`String(100)`) – `[SKU2]`.
- `model_id` (`BIGINT`) – `[Model_ID]`.
- `model` (`Text`) – new display field for model code/name.
- `part` (`Text`) – `[Part]`.
- `price`, `previous_price`, `brutto` (`Numeric(12,2)`) – `[Price]`,
  `[PreviousPrice]`, `[Brutto]`.
- `price_updated` (`DateTime(timezone=True)`) – `[Price_updated]`.
- `market`, `use_ebay_id`, `category`, `description` – `[Market]`,
  `[UseEbayID]`, `[Category]`, `[Description]`.
- Shipping fields: `shipping_type`, `shipping_group`,
  `shipping_group_previous`, `shipping_group_change_state`,
  `shipping_group_change_state_updated`, `shipping_group_change_state_updated_by`.
- Condition: `condition_id` (`INT`) maps to `item_conditions.id`, plus
  `manual_condition_value_flag`.
- Images: `pic_url1` … `pic_url12` (`Text`) for `[PicURL1]`…`[PicURL12]`.
- Physical: `weight`, `weight_major`, `weight_minor` (`Numeric(12,3)`),
  `package_depth`, `package_length`, `package_width` (`Numeric(12,2)`),
  `size`, `unit` – `[Weight]`, `[WeightMajor]`, `[WeightMinor]`,
  `[PackageDepth]`, `[PackageLength]`, `[PackageWidth]`, `[Size]`, `[Unit]`.
- Identification: `part_number`, `mpn`, `upc`, `color_flag`, `color_value`,
  `epid_flag`, `epid_value` – `[Part_Number]`, `[MPN]`, `[UPC]`, etc.
- Grades/packaging: `item_grade_id`, `basic_package_id` – `[ItemGradeID]`,
  `[BasicPackageID]`.
- Alerts & status: `alert_flag`, `alert_message`, `record_status`,
  `record_status_flag`, `checked_status`, `checked`, `checked_by`,
  `one_time_auction` – `[AlertFlag]`, `[AlertMessage]`, `[RecordStatus]`, etc.
- Audit: `record_created_by`, `record_created`, `record_updated_by`,
  `record_updated`, `oc_export_date`, `oc_market_export_date` –
  `[record_created_by]`, `[record_created]`, etc.
- Template/listing metadata: `custom_template_flag`,
  `custom_template_description`, `condition_description`, `domestic_only_flag`,
  `external_category_flag`, `external_category_id`, `external_category_name`,
  `listing_type`, `listing_duration`, `listing_duration_in_days`,
  `use_standard_template_for_external_category_flag`, `use_ebay_motors_site_flag`,
  `site_id`.
- Clone metadata: `clone_sku_flag`, `clone_sku_updated`, `clone_sku_updated_by`.
- **New app-only fields** (not present in MSSQL):
  - `title` (`Text`) – short human title (<= 80 chars in UI).
  - `brand` (`String(100)`).
  - `warehouse_id` (`INT`, FK → `warehouses.id`).
  - `storage_alias` (`String(100)`) – storage / alias field visible in UI.

Indexes:

- `idx_sq_items_sku` (sku)
- `idx_sq_items_category` (category)
- `idx_sq_items_part_number` (part_number)
- `idx_sq_items_model` (model)
- `idx_sq_items_condition_id` (condition_id)
- `idx_sq_items_shipping_group` (shipping_group)
- `idx_sq_items_site_id` (site_id)

### 1.2. Dictionary tables

All created by Alembic revision `dae483e3dc8c_add_sq_items_and_sq_dictionaries`.

Models live in `app.models_sqlalchemy.models`:

- `SqInternalCategory` → table `sq_internal_categories`
  - `id`, `code`, `label`, `sort_order`.
  - Seeded with sample categories (`motherboards`, `LCD complete`, etc.).
- `SqShippingGroup` → table `sq_shipping_groups`
  - `id`, `code`, `label`, `sort_order`.
  - Seeded with legacy-like values (`1group<80`, `LCD Complete`, `BIG items`, …).
- `ItemCondition` → table `item_conditions`
  - `id`, `code`, `label`, `sort_order`.
  - Seeded with `NEW`, `USED`, `REFURBISHED`, `FOR_PARTS`.

Existing `warehouses` table is reused for the Warehouse dropdown.

## 2. Alembic Migration

Migration file: `backend/alembic/versions/dae483e3dc8c_add_sq_items_and_sq_dictionaries.py`.

It:

1. Creates `sq_internal_categories` and seeds base categories.
2. Creates `sq_shipping_groups` and seeds base groups.
3. Creates `item_conditions` and seeds base conditions.
4. Creates `sq_items` with all columns listed above plus indexes.

Down migration drops `sq_items` first (FK to `warehouses`), then the three
dictionary tables.

## 3. Backend API

### 3.1. Router

Router module: `app.routers.sq_catalog`.

Registered in `app.main` with:

- `app.include_router(sq_catalog.router)`

Prefix: `/api/sq`.

### 3.2. Endpoints

#### `GET /api/sq/items`

Paginated list for the SQ catalog grid.

Query params:

- `page` (int, default 1)
- `page_size` (int, default 50, max 200)
- `sku` (optional, substring match on `SqItem.sku`)
- `model_id` (optional, exact match)
- `category` (optional, exact match)
- `shipping_group` (optional, exact match)
- `condition_id` (optional, exact match)
- `has_alert` (optional bool; `true` → `alert_flag = true`, `false` → no alert)
- `search` (optional full-textish search across `sku`, `title`, `description`,
  `part_number`, `mpn`, `upc`, `part`).

Response model: `SqItemListResponse` (`app.models.sq_item`):

```json
{
  "items": [
    {
      "id": 123,
      "sku": "T410-LCD-01",
      "model": "T410",
      "category": "103", // internal category code
      "condition_id": 2,
      "part_number": "FRU 12345",
      "price": 79.99,
      "title": "Lenovo T410 LCD complete",
      "brand": "Lenovo",
      "alert_flag": true,
      "shipping_group": "5",
      "pic_url1": "https://...",
      "record_created": "...",
      "record_updated": "...",
      "record_status": "OK"
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 50
}
```

#### `GET /api/sq/items/{id}`

Returns full `SqItemRead` (detail view + edit form). Includes virtually all
legacy fields and the new app-specific ones.

#### `POST /api/sq/items`

Creates a new SQ item. Payload: `SqItemCreate`.

- Required: `model`, `category`, `condition_id`, `price`, `shipping_group`.
- Optional: all other fields (SKU, title, description, part numbers, images,
  warehouse, storage_alias, alerts, etc.).
- If `sku` is omitted or empty and `autoSku` is used on the frontend, the
  backend auto-generates a simple SKU of the form `SQ-{unix_timestamp}`.
- `record_created` and `record_created_by` are auto-populated using the
  authenticated user (username/email or `"system"`).

Returns: `SqItemRead` for the created record.

#### `PUT /api/sq/items/{id}`

Partial update using `SqItemUpdate` (all fields optional; only provided fields
are patched).

- `record_updated` and `record_updated_by` are auto-populated.
- Returns the updated `SqItemRead`.

#### `GET /api/sq/dictionaries`

Returns all dictionaries needed for the Create/Edit SKU form in one call.

Shape:

```json
{
  "internal_categories": [
    { "id": 1, "code": "101", "label": "motherboards" },
    ...
  ],
  "shipping_groups": [
    { "id": 1, "code": "1", "label": "1group<80" },
    ...
  ],
  "conditions": [
    { "id": 1, "code": "NEW", "label": "New" },
    ...
  ],
  "warehouses": [
    { "id": 1, "name": "Main", "location": "", "warehouse_type": null },
    ...
  ],
  "listing_types": [
    { "code": "FixedPriceItem", "label": "Fixed price" },
    { "code": "Auction", "label": "Auction" }
  ],
  "listing_durations": [
    { "code": "GTC", "label": "Good 'Til Cancelled", "days": null },
    { "code": "30", "label": "30 days", "days": 30 },
    { "code": "7", "label": "7 days", "days": 7 }
  ],
  "sites": [
    { "code": "EBAY-US", "label": "eBay US", "site_id": 0 }
  ]
}
```

## 4. Grid backend (`/api/grids/sku_catalog/data`)

The generic grids infrastructure is reused for the SKU grid via `gridKey`
`"sku_catalog"`.

Implementation: `_get_sku_catalog_data` in
`app.routers.grids_data`.

Changes:

- Previously backed by the simplified `SKU` table; now backed by `SqItem` +
  left-joined `ItemCondition`.
- Still returns the same logical columns so existing LISTING workflows keep
  working:
  - `id`
  - `sku_code` (mapped from `SqItem.sku`)
  - `model`
  - `category`
  - `condition` (friendly label from `item_conditions.label`)
  - `part_number`
  - `price`
  - `title`
  - `description`
  - `brand`
  - `rec_created` / `rec_updated`
- Sorting uses `SqItem` columns with the same column names used in
  `GRID_DEFAULTS` / `SKU_CATALOG_COLUMNS_META`.

## 5. Frontend: SKU tab

Page file: `frontend/src/pages/SKUPage.tsx`.

### 5.1. Layout

- Uses the existing `FixedHeader` and `DataGridPage` abstractions.
- Top: header + "New SKU" button.
- Middle: `DataGridPage` with `gridKey="sku_catalog"` powered by
  `/api/grids/sku_catalog/data`.
- Bottom: detail panel for the selected SQ item.

The grid uses `extraParams={ { _refresh: refreshKey } }` so that after create/
edit operations the grid can be forced to reload by bumping `refreshKey`.

### 5.2. Detail panel

- Shows a larger image (first non-empty of `pic_url1..12`) with simple
  previous/next controls to cycle through images.
- Right side shows a read-only summary:
  - Title / Part
  - Price
  - SKU
  - Model
  - Internal Category (resolved via `sq_internal_categories`)
  - Condition (resolved via `item_conditions`)
  - Shipping Group (resolved via `sq_shipping_groups`)
  - Part Number, UPC, MPN
  - Warehouse (resolved via `warehouses`)
  - Storage / Alias
  - Description
  - Created by / Updated by + timestamps
  - Alert flag and message (if enabled).

Clicking a grid row loads detail via `GET /api/sq/items/{id}`.

### 5.3. Create/Edit SKU form

Implemented as a `Dialog` (modal) in `SKUPage`:

- Opens in **create** mode via the top "New SKU" button.
- Opens in **edit** mode from the detail panel "Edit SKU" button.

Form fields (current subset):

- Header block:
  - `Title` (max 80 chars with live countdown).
  - `Model` (free text; `model_id` will be wired when/if a models table is
    introduced).
  - `SKU` + `Auto generated` checkbox.
- Category & condition:
  - `Internal Category` dropdown backed by `sq_internal_categories`.
  - `Condition` dropdown backed by `item_conditions`.
  - `Price` numeric field.
  - `Shipping Group` dropdown backed by `sq_shipping_groups`.
- Images:
  - 12 URL fields mapped to `pic_url1..pic_url12` with simple inputs.
- Storage & warehouse:
  - `Warehouse` dropdown backed by `warehouses`.
  - `Storage / Alias` text field mapped to `storage_alias`.
- Codes & identifiers:
  - `Part Number`, `MPN`, `UPC`, `Brand` text fields.
- Description:
  - Multiline `Description` textarea.
- Alerts:
  - `Enable Alert` checkbox + `Alert message` textarea mapped to
    `alert_flag` / `alert_message`.

Validation (frontend only, mirrored by backend types):

- Required: `model`, `category`, `condition_id`, `price` (numeric),
  `shipping_group`.

On submit:

- `POST /api/sq/items` for create; `PUT /api/sq/items/{id}` for edit.
- On success:
  - Close modal.
  - Bump `refreshKey` so `DataGridPage` reloads.
  - Set `selectedId` to the new/updated item id and refresh detail panel.

## 6. Assumptions & TODOs

- **Models table**: there is currently no dedicated `models` dictionary/table in
  Postgres; the SQ form uses a free-text `model` field. Once a models table is
  introduced (or mapped from MSSQL), `SqItem.model_id` can be wired and the
  frontend adapted to use a searchable dropdown.
- **External category picker**: fields for external eBay category
  (`external_category_id`, `external_category_name`) exist in the schema but are
  not yet surfaced in the UI; they will be integrated with a real eBay category
  picker later.
- **Listing settings**: `listing_type`, `listing_duration`,
  `listing_duration_in_days`, `site_id` are exposed via the dictionaries
  endpoint, but only a basic subset is wired into the frontend form right now.
- **Conditions vs `ConditionType` enum**: the new `item_conditions` table is
  separate from the existing `ConditionType` enum used by `inventory` / `sku`.
  Mapping between them can be added later if needed.
- **Filters in the SKU grid**: the generic grid backend currently provides
  sorting and column configuration for `sku_catalog`. Additional server-side
  filters (e.g., by category/condition) can be added to
  `_get_sku_catalog_data` and plumbed through `DataGridPage.extraParams` when
  needed.
