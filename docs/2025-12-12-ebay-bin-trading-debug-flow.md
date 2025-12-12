# eBay BIN (Fixed Price) Trading API — Debug Flow (Verify + List)

## Why `bulk_publish_offer` is NOT enough
The previous flow (`offer lookup → bulkPublishOffer`) only **publishes an already-created offer** on eBay. It does **not** create a listing from our database payload. For listing from DB, we need Trading API calls that create the listing and return `ItemID`.

## Target flow (Trading API, XML)
- **VERIFY (safe preflight)**: `VerifyAddFixedPriceItem`
- **LIST (real)**: `AddFixedPriceItem` → returns **`ItemID`**

## OAuth rule (Trading API)
For Trading API with OAuth:
- Token must be provided in **`X-EBAY-API-IAF-TOKEN`** header.
- Do **NOT** include `<RequesterCredentials>` in the XML body.

## Endpoints implemented (Admin-only)
- `POST /api/admin/ebay/bin/verify`
  - Builds canonical XML payload from DB + config
  - Sends to `VerifyAddFixedPriceItem`
  - Logs request/response
  - Returns raw XML + parsed summary
- `POST /api/admin/ebay/bin/list`
  - Same payload builder
  - Sends to `AddFixedPriceItem`
  - Returns `ItemID` on success
  - Persists `ItemID` into `parts_detail.item_id` (best-effort)
- `GET /api/admin/ebay/bin/source?legacy_inventory_id=...`
  - No eBay calls; returns DB-derived fields used for mapping + missing DB fields

## Trading API endpoints
Derived from `settings.EBAY_ENVIRONMENT`:
- Sandbox: `https://api.sandbox.ebay.com/ws/api.dll`
- Production: `https://api.ebay.com/ws/api.dll`

## Required headers (always)
For each request:
- `X-EBAY-API-CALL-NAME`: `VerifyAddFixedPriceItem` or `AddFixedPriceItem`
- `X-EBAY-API-SITEID`: `0` for eBay US (configurable)
- `X-EBAY-API-COMPATIBILITY-LEVEL`: fixed integer (default 1311)
- `X-EBAY-API-IAF-TOKEN`: OAuth user access token (masked in logs/UI)
- `Content-Type`: `text/xml; charset=utf-8`
- `Accept`: `text/xml`

## Canonical “minimal working” BIN XML (schema + namespace)
All requests are built with:
- `xmlns="urn:ebay:apis:eBLBaseComponents"`

The debug tool builds:
- `<VerifyAddFixedPriceItemRequest ...><Item>...</Item></VerifyAddFixedPriceItemRequest>`
- `<AddFixedPriceItemRequest ...><Item>...</Item></AddFixedPriceItemRequest>`

## Mandatory pre-check (our side)
Before calling eBay, we block VERIFY/LIST if any are missing:
- `Item.Title` (<=80)
- `Item.Description` (HTML)
- `Item.PrimaryCategory.CategoryID`
- `Item.ListingType = FixedPriceItem`
- `Item.ListingDuration` (e.g. `GTC`)
- `Item.StartPrice` (currencyID=USD)
- `Item.Quantity`
- `Item.Currency`
- `Item.Country`
- `Item.Location`
- `Item.PostalCode`
- `Item.DispatchTimeMax`
- `Item.PictureDetails.PictureURL[]` (>=1)
- `Item.ConditionID`
- `Item.Site` (must match `X-EBAY-API-SITEID`)
- `ItemSpecifics.Brand` (default: `Unbranded`)
- `ItemSpecifics.MPN` (default: `tbl_parts_detail.MPN`/`Part_Number` or `Does Not Apply`)
- `SellerProfiles` IDs:
  - `SellerShippingProfile.ShippingProfileID`
  - `SellerPaymentProfile.PaymentProfileID`
  - `SellerReturnProfile.ReturnProfileID`

If `Item.Description` is empty in DB, the debug tool auto-generates a minimal HTML template to avoid immediate hard failures and let Verify surface category-specific requirements (item specifics, policy compliance, etc.).

## Policies strategy (fixed)
Canonical: **SellerProfiles (Business Policies)** only.

Fallback: **Manual shipping/returns** mode is available for troubleshooting when policy IDs are invalid / not applicable.
The UI forces you to choose one mode per run to avoid “mixed-mode mystery failures”.

## DB → eBay mapping (source of truth)
**Source of truth for listing fields**: `public."tbl_parts_detail"` plus `public."tbl_parts_inventory"` overrides.

Mapping (simplified):
- `Item.Title` ← `tbl_parts_inventory.OverrideTitle` → fallback `tbl_parts_detail.Part`
- `Item.Description` ← `tbl_parts_inventory.OverrideDescription` → fallback `tbl_parts_detail.Description`
- `Item.PrimaryCategory.CategoryID` ← `tbl_parts_detail.Category`
- `Item.StartPrice` ← `tbl_parts_inventory.OverridePrice` → fallback `tbl_parts_detail.Price`
- `Item.Quantity` ← `tbl_parts_inventory.Quantity`
- `Item.ConditionID` ← `tbl_parts_inventory.OverrideConditionID` → fallback `tbl_parts_detail.ConditionID`
- `Item.PictureDetails.PictureURL[]` ← `tbl_parts_inventory.OverridePicURL1..12` → fallback `tbl_parts_detail.PicURL1..12`

## Logging (required)
Table: `public.ebay_bin_test_runs`
- Stores: full request URL, masked headers, raw request XML, response status/headers/body, parsed Ack/errors/warnings, ItemID.

Migration: `supabase/migrations/20251212130000_ebay_bin_test_runs.sql`

## ItemID persistence (must not be lossy)
Even if updating `parts_detail.item_id` fails, we always write a hard mapping row:
- Table: `public.ebay_bin_listings_map`
- Migration: `supabase/migrations/20251212131500_ebay_bin_listings_map.sql`

## UI behavior
Admin page: **eBay BIN Listing Debug (Trading API)**
- Loads DB fields by legacy inventory id
- Shows mandatory checklist (checkboxes)
- Buttons:
  - **VERIFY** (safe)
  - **LIST** (real)
- Result modal shows:
  - XML payload (request)
  - HTTP headers (masked) + URL
  - Raw XML response
  - Parsed summary (Ack, errors, warnings, ItemID)


