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

---

## Iteration 4 — 2025-12-12

### Issue observed
After adding “full semantics” lookup metadata, the admin UI started showing **Network Error** for:
- `GET /api/admin/ebay/test-listing/payload?legacy_inventory_id=501610`

Evidence (from user screenshots):
- Browser devtools shows **HTTP 500 Internal Server Error** for `/api/admin/ebay/test-listing/payload?...`
- Railway request logs show **httpStatus: 500** for path `/api/admin/ebay/test-listing/payload`.

### Root cause (most likely)
The new `help.lookup_rows` field included non-JSON-native objects (e.g., SQLAlchemy RowMapping / Decimal / datetime) which can trigger a **server-side JSON serialization failure**, returning HTTP 500.

### Fix
Backend now runs `fastapi.encoders.jsonable_encoder()` on `help.lookup_rows` so that:
- SQLAlchemy row mappings become plain dicts
- Decimals/datetimes are converted into JSON-friendly types

Implementation:
- `backend/app/routers/admin_ebay_listing_test.py`: `_make_help(..., lookup_rows=...)` now encodes the metadata before returning it.

---

## Iteration 5 — 2025-12-12

### Goal
Add a **Preview → LIST → Terminal** debug workflow to Admin → eBay Test Listing, wired to the selected **legacy inventory id**.

### UX flow
1) User loads payload preview by entering `tbl_parts_inventory.ID`.
2) User clicks **TEST LIST (preview)**.
3) A **Preview modal** opens with two sections:
   - **HTTP call preview (masked)**: planned eBay endpoint/method/headers/body. (Tokens masked. OfferId is shown as a placeholder because it is resolved at runtime.)
   - **Variables / payload fields**: all fields (mandatory + optional) the system will use for listing.
4) User clicks **LIST** in the modal:
   - Backend executes listing call and returns `trace + summary`.
5) A **Terminal window** opens automatically and shows:
   - **Raw trace**: all steps including masked HTTP requests/responses.
   - **Decoded response**: derived summaries from the last eBay response (including bulkPublishOffer response entries when present).

### Backend changes
- `backend/app/services/ebay_listing_service.py`
  - `run_listing_worker_debug(..., candidates_override=...)` added so admin can force-run a specific `parts_detail` row.
- `backend/app/routers/admin_ebay_listing_test.py`
  - `POST /api/admin/ebay/test-listing/list`
    - Input: `{ legacy_inventory_id, force=true }`
    - Resolves SKU → modern `inventory.parts_detail_id` → `parts_detail` row
    - Runs listing worker and returns full `EbayListingDebugResponse` (trace + summary)

### Frontend changes
- `frontend/src/pages/AdminTestListingPage.tsx`
  - Added **TEST LIST (preview)** button (enabled after payload is loaded)
  - Added preview modal + LIST confirm wiring to `/api/admin/ebay/test-listing/list`
  - Auto-opens terminal with returned trace
- `frontend/src/components/WorkerDebugTerminalModal.tsx`
  - Added **Raw trace** / **Decoded response** tabs
  - Decoded tab shows last eBay response JSON and a heuristic summary for `bulkPublishOffer`.

---

## Iteration 6 — 2025-12-12

### Change request
In the Preview modal, show the **full HTTP sequence** (not just publish):
1) **Offer lookup** by SKU (to resolve `offerId`)
2) **Publish** via `bulkPublishOffer`

### Implementation notes
- `frontend/src/pages/AdminTestListingPage.tsx`
  - Preview modal “Full HTTP call preview (masked)” now prints an object with `calls[]`:
    - Call 1: `GET /sell/inventory/v1/offer?sku=<SKU>` (masked Authorization)
    - Call 2: `POST /sell/inventory/v1/bulk_publish_offer` (masked Authorization)
  - `offerId` is shown as a placeholder because it is resolved from the step-1 response at runtime.

---

## Iteration 7 — 2025-12-12

### Change request
Make the Preview modal feel **real** by showing the **actual HTTP** for the offer lookup call *before* publishing:
- Step 1 must be a real request to eBay (with real response headers/body), with secrets masked.
- Step 2 remains a planned publish request, but now includes the **real resolved offerId** from step 1.

### Backend changes
- `backend/app/services/ebay.py`
  - Added `EbayService.fetch_offers_debug(...)` which calls eBay and returns:
    - `payload` (offers JSON)
    - `http` (request/response/duration metadata; Authorization masked)
- `backend/app/routers/admin_ebay_listing_test.py`
  - Added `POST /api/admin/ebay/test-listing/prepare`
    - Input: `{ legacy_inventory_id }`
    - Output includes:
      - `http_offer_lookup` (REAL HTTP request + response)
      - `offer_id` + `chosen_offer`
      - `http_publish_planned` (planned publish request using resolved `offer_id`)

### Frontend changes
- `frontend/src/pages/AdminTestListingPage.tsx`
  - When Preview modal opens, it now calls `/prepare` automatically.
  - The “Full HTTP call preview” pane renders:
    - Step 1: real offer lookup HTTP request/response
    - Step 2: planned publish HTTP request using the real `offerId`

---

## Iteration 8 — 2025-12-12

### Change request
- Preview modal must show **one single chunk** representing the **exact eBay HTTP traffic** executed when the user clicks LIST.
- Do **not** show “step 1 / step 2” in the UI.
- Ensure **Description** is treated as **Mandatory** in the payload preview so missing descriptions are caught early.

### What we can and cannot send in the publish call
- Current listing implementation **publishes existing eBay offers**:
  - The publish request (`bulk_publish_offer`) **only contains `offerId`**.
  - Title/price/quantity/description are not part of that publish request; they exist on eBay already in the offer/inventory item.
- To provide a “real feel”, the Preview now shows a single **HTTP transcript** containing:
  1) the real **offer lookup** request+response (includes those listing fields as returned by eBay)
  2) the exact **publish request** that will be sent on LIST (with resolved `offerId`)

### Implementation notes
- `backend/app/routers/admin_ebay_listing_test.py`
  - Fixed `no_parts_detail_id_for_sku` by adding fallback resolution via `parts_detail` (sku/override_sku) when `inventory.sku_code` is missing.
  - Moved `description` into **Mandatory** fields.
- `frontend/src/pages/AdminTestListingPage.tsx`
  - “Full HTTP call preview” now renders a **single text transcript** (no step labels) instead of a `{calls:[...]}` JSON object.

---

## Iteration 9 — 2025-12-12

### Pivot: BIN listing must be Trading API (XML), not offer publish
We split the tooling into two separate admin screens:
- **BIN Listing Debug (Trading API)**: `VerifyAddFixedPriceItem` + `AddFixedPriceItem`
- **Legacy Offer Publish Debug**: offer lookup + `bulkPublishOffer` (kept separate; not used for DB-driven listing)

### New backend endpoints
- `GET /api/admin/ebay/bin/source?legacy_inventory_id=...`
- `POST /api/admin/ebay/bin/verify`
- `POST /api/admin/ebay/bin/list`

### New documentation
- `docs/2025-12-12-ebay-bin-trading-debug-flow.md`

---

## Iteration 10 — 2025-12-12

### Hardening for real categories (P0)
- Added `tbl_parts_condition` integration into BIN source preview:
  - show `ConditionID + ConditionDisplayName` and expose full condition row metadata.
- Added **ItemSpecifics** minimums:
  - Brand (default `Unbranded`)
  - MPN (default `tbl_parts_detail.MPN/Part_Number` or `Does Not Apply`)
- Added **Description fallback template** when DB description is empty (prevents guaranteed early failure and lets Verify surface real category requirements).
- Added **Policies mode** to avoid mixed-mode mystery failures:
  - canonical: SellerProfiles IDs
  - fallback: manual ShippingDetails + ReturnPolicy (minimal)
- Made persistence non-lossy:
  - Added `ebay_bin_listings_map` mapping table to guarantee `ItemID` retention even if `parts_detail` update fails.
  - Added explicit `log_saved` / `item_id_saved_to_map` flags to responses + UI warnings when something fails to persist.

---

## Iteration 11 — 2025-12-12

### Business Policies: store in DB + dropdowns (no hardcoded IDs)
- Added `public.ebay_business_policies` (seeded defaults for `EBAY_US`) and `public.ebay_business_policies_defaults` view.
- Added admin-only endpoints:
  - `GET /api/admin/ebay/business-policies`
  - `GET /api/admin/ebay/business-policies/defaults`
- Updated BIN debug UI to load policies from API and show dropdowns with auto-selected defaults (persisted per user via `localStorage`).

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


