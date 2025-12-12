# eBay Test Listing — living document (append-only)

**Rule:** This file is **append-only**. Never delete or rewrite previous sections. Add a new dated “Iteration” section for each change.

---

## Iteration 1 — 2025-12-12

### Goal
Provide a strong **visual preview** in **Admin → eBay Test Listing** where the user manually inputs a **legacy inventory ID** (`public.tbl_parts_inventory."ID"`). The UI then pre-populates all available fields needed for eBay listing and groups them into:
- **Mandatory**
- **Optional**

Also include **field-level provenance**: source tables/columns and relationships.

---

### Tables involved (current understanding)

#### Legacy inventory (source of selected record)
- **Table**: `public.tbl_parts_inventory`
- **Primary key**: `"ID"`
- **Key columns used**:
  - `"SKU"` (numeric) — foreign key *by convention* into SKU payload tables
  - `"StatusSKU"` (numeric) — status code
  - `"OverrideTitle"`, `"OverridePrice"`, `"OverrideConditionID"`, `"OverrideDescription"`
  - `"OverridePicURL1" .. "OverridePicURL12"`
  - `"Quantity"`, `"Storage"`, `"WarehouseID"`, `"FilterValueWarehouseID"`
  - shipping hints: `"ShippingGroupToChange"` (nullable)

#### Inventory status dictionary (legacy)
- **Table**: `public.tbl_parts_inventorystatus`
- **Primary key**: `"InventoryStatus_ID"`
- **Key columns used**:
  - `"InventoryStatus_Name"` (example: `TEST`)
- **Relationship**:
  - `tbl_parts_inventory."StatusSKU" -> tbl_parts_inventorystatus."InventoryStatus_ID"`

#### SKU catalog / SKU payload (what the “Edit SKU” form edits)
- **Table**: `public."SKU_catalog"` (mixed-case table name; must be quoted)
- **Primary key**: `"ID"`
- **Key columns used**:
  - `"SKU"` (numeric) — joins to legacy inventory SKU
  - `"Part"` (logical Title)
  - `"Price"`, `"Weight"`, `"Unit"`
  - `"ShippingGroup"`, `"ShippingType"`
  - `"ConditionID"`
  - `"PicURL1" .. "PicURL12"`
  - `"Category"` (internal category id/code)
  - `"ExternalCategoryFlag"`, `"ExternalCategoryID"`, `"ExternalCategoryName"`
  - `"ListingType"` (e.g. `FixedPriceItem`)
  - `"ListingDuration"` (e.g. `GTC`)
  - `"SiteID"` (e.g. `0` for eBay US)
  - `"MPN"`, `"UPC"`, `"Part_Number"`
- **Relationship (by convention)**:
  - `tbl_parts_inventory."SKU" -> "SKU_catalog"."SKU"`

#### Legacy parts_detail payload
- **Table**: `public."tbl_parts_detail"`
- **Primary key**: `"ID"`
- **Key columns used**: similar to `"SKU_catalog"` (SKU/price/category/shipping/condition/pictures)
- **Relationship (by convention)**:
  - `tbl_parts_inventory."SKU" -> tbl_parts_detail."SKU"`

#### Canonical worker payload (modern)
- **Table**: `public.parts_detail`
- **Primary key**: `id`
- **Key columns used**:
  - `sku`, `override_sku`
  - `override_title`, `override_price`, `price_to_change`
  - `override_condition_id`
  - `override_pic_url_1 .. override_pic_url_12`
  - `status_sku` (string enum-like: `AwaitingModeration`, `Checked`, etc.)
- **Relationship**:
  - `inventory.parts_detail_id -> parts_detail.id` (modern inventory table)

#### Shipping group dictionaries (two sources exist)
- **Table**: `public.tbl_internalshippinggroups`
  - Columns: `"ID"`, `"Name"`, `"Description"`, `"Active"`
  - Relationship: `"SKU_catalog"."ShippingGroup" -> tbl_internalshippinggroups."ID"`
- **Table**: `public.sq_shipping_groups`
  - Columns: `id`, `code`, `label`, `sort_order`
  - Relationship: `"SKU_catalog"."ShippingGroup" -> sq_shipping_groups.id` (by numeric id)

#### Item condition dictionary
- **Table**: `public.item_conditions`
- **Primary key**: `id`
- **Columns**: `code`, `label`
- **Relationship**:
  - `"SKU_catalog"."ConditionID" -> item_conditions.id` (if IDs align in this environment)

#### Internal categories dictionary (legacy)
- **Table**: `public.tbl_parts_category`
- **Key columns**: `"CategoryID"`, `"CategoryDescr"`, `"eBayCategoryName"`
- **Relationship**:
  - `"SKU_catalog"."Category" -> tbl_parts_category."CategoryID"`

---

### Sample data points confirmed (from live DB)

#### Shipping group ID=4
- `tbl_internalshippinggroups` row:
  - `"ID" = 4`
  - `"Name" = "no international"`
  - `"Active" = true`

#### SKU 100000000095909
- `public."SKU_catalog"` row:
  - `"ShippingGroup" = 4`
  - `"ShippingType" = "Flat"`
  - `"Price" = 17.99`
  - `"Weight" = 32`
  - `"ListingType" = "FixedPriceItem"`
  - `"ListingDuration" = "GTC"`
  - `"ConditionID" = 7000`
  - `"PicURL1"` populated
- `public.parts_detail` row:
  - `id = 2`
  - `sku = 100000000095909`
  - `status_sku = "AwaitingModeration"`
  - `override_title` populated
  - `override_price = 17.99`
- `public.tbl_parts_inventory` row:
  - `"ID" = 501610`
  - `"StatusSKU" = 21` → maps to `tbl_parts_inventorystatus.InventoryStatus_Name = "TEST"`
  - `"SKU" = 100000000095909`

---

### Implementation notes (Iteration 1)

#### Backend
- Added admin endpoint:
  - `GET /api/admin/ebay/test-listing/payload?legacy_inventory_id=...`
- Implementation file:
  - `backend/app/routers/admin_ebay_listing_test.py`
- Response structure:
  - `mandatory_fields[]` + `optional_fields[]`
  - Each field includes `value`, `missing`, and `sources[]` (`table`, `column`).
- Prefill precedence (per-field):
  - `tbl_parts_inventory` overrides → `parts_detail` overrides → `"SKU_catalog"` → `"tbl_parts_detail"` → dictionaries

#### Frontend
- Added a new card on Admin → eBay Test Listing:
  - “Payload preview (by legacy Inventory ID)”
  - Input: numeric `tbl_parts_inventory.ID`
  - Renders **Mandatory** and **Optional** fields with OK/MISSING badges and source trails.
- Files:
  - `frontend/src/pages/AdminTestListingPage.tsx`
  - `frontend/src/api/ebay.ts` (added DTOs + `getTestListingPayloadPreview`)

---

## Iteration 2 — 2025-12-12

### Change request
- **Do not use `SKU_catalog` at all** in test-listing payload preview.
- **Use only `tbl_parts_detail`** as the SKU payload table (plus `tbl_parts_inventory` overrides, `parts_detail` overrides, and dictionaries).
- In the UI, add an **info (“i”) hover** on every field (mandatory + optional) describing:
  - what **eBay expects** for that field
  - how to interpret our internal codes (e.g., `ShippingGroup=4` → “no international”).

### Data flow (updated)
Prefill precedence (per-field) is now:
1) `tbl_parts_inventory` override columns (OverrideTitle/OverridePrice/OverrideConditionID/OverridePicURL*)
2) `parts_detail` override columns (override_title/override_price/override_condition_id/override_pic_url_*)
3) `tbl_parts_detail` columns (SKU payload for shipping/category/condition/pictures/listing settings/etc.)
4) dictionaries for labels (shipping group name, condition label, category label, status name)

### Implementation notes (Iteration 2)

#### Backend
- Updated `GET /api/admin/ebay/test-listing/payload` to **remove all `SKU_catalog` reads**.
- Primary payload source for SKU-level listing fields is now: `public."tbl_parts_detail"`.

#### Frontend
- Added an **Info icon** next to each field label in the payload preview.
- Hovering the icon shows:
  - a short, human-readable explanation of **what eBay expects**
  - dynamic interpretation for internal codes when available (e.g. `Shipping group` shows “4: no international”).

---

## Iteration 3 — 2025-12-12

### Change request
Add **full semantics / metadata** per field so the tooltip can show:
- What **eBay expects** for the field
- Our **internal meaning**
- The **full lookup row(s)** from dictionary tables (when applicable)

### API contract update
`TestListingPayloadField` now includes an optional `help` object:
- `help.ebay_expected`: string
- `help.internal_semantics`: string | null
- `help.lookup_rows`: object | null (raw rows as JSON; may include arrays)

### Examples of lookup metadata included
- **Shipping group** (`ShippingGroup`):
  - `tbl_internalshippinggroups` rows where `ID=<value>` (full row JSON; duplicates may exist)
  - `sq_shipping_groups` row for `id=<value>` when available
- **Category** (`Category`):
  - `tbl_parts_category` row for `CategoryID=<value>`
- **Condition** (`ConditionID`):
  - `item_conditions` row for `id=<value>` when available
- **Pictures**:
  - `lookup_rows.pic_urls`: list of `{index, url}` for all non-empty image URLs

### Desired UI behavior (Admin → eBay Test Listing)

#### Input
- User enters: **Legacy Inventory ID** = `tbl_parts_inventory."ID"` (example: `501610`)

#### Output (visual payload preview)
- **Top summary**: SKU, InventoryStatus, Titles/Prices chosen, where data came from.
- **Mandatory fields** section:
  - Each field shows:
    - current value
    - **source** (table.column)
    - status badge: **OK** / **MISSING**
- **Optional fields** section:
  - same style, but not blocking.

#### Data precedence (prefill rules)
For each field, choose the first non-empty value in this precedence order:
1) `tbl_parts_inventory` override columns (OverrideTitle/OverridePrice/OverrideConditionID/OverridePicURL*)
2) `parts_detail` override columns (override_title/override_price/override_condition_id/override_pic_url_*)
3) `SKU_catalog` columns (Part/Price/ConditionID/PicURL*/ShippingGroup/ShippingType/ListingType/ListingDuration/SiteID/Weight/Unit/Category/etc.)
4) `tbl_parts_detail` columns (fallback if SKU_catalog missing)
5) dictionaries for labels (shipping group name, condition label, category label)

---

### Mandatory vs Optional (initial version)

**Mandatory (BIN / our system)**:
- SKU
- Title (<=80 chars)
- Price (>0)
- Quantity (>0)
- ConditionID
- At least 1 picture URL
- ShippingGroup
- ShippingType
- ListingType (must be `FixedPriceItem` for our test)
- ListingDuration (e.g. `GTC`)
- SiteID (e.g. `0` = eBay US)
- Category (internal or external eBay category)

**Optional (nice-to-have / ebay specifics vary by category)**:
- MPN
- Part_Number
- UPC (or “Does not apply”)
- Condition description
- Description HTML
- Additional pictures (PicURL2..12)
- DomesticOnlyFlag / policy restrictions
- ExternalCategory fields (if using eBay category mode)

---

### API to support UI

Add endpoint (admin-only):
- `GET /api/admin/ebay/test-listing/payload?legacy_inventory_id=...`

Response should include:
- resolved identifiers: legacy inventory id, sku, status, parts_detail_id (if any)
- `mandatory_fields[]` and `optional_fields[]` arrays
- each field item includes: `key`, `label`, `value`, `required`, `missing`, `sources[]`


