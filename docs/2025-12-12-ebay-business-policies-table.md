## eBay Business Policies table (defaults + UI wiring)

### Why this exists
Trading API BIN listing prefers **SellerProfiles (Business Policies)** to avoid building ShippingDetails/ReturnPolicy/PaymentMethods by hand.
We store policy IDs in DB so the BIN Debug UI can:

- show **dropdowns** per policy type
- auto-select per **account + marketplace**
- stay extensible (multiple policies, multiple accounts, multiple marketplaces)
- avoid hardcoding IDs in frontend

### Current default policy IDs (EBAY_US)
- **Shipping**: `206348665012`
- **Payment**: `179217199012`
- **Return**: `164486481012`

### DB schema
Migration: `supabase/migrations/20251212140000_ebay_business_policies.sql`

Table: `public.ebay_business_policies`
- `account_key` (e.g. `default`, later: `better_planet_llc`, `miller_sales_llc`)
- `marketplace_id` (e.g. `EBAY_US`)
- `policy_type` (`SHIPPING` | `PAYMENT` | `RETURN`)
- `policy_id` (eBay policy ID)
- `policy_name`, `policy_description`
- `is_default` (only one default per `(account_key, marketplace_id, policy_type)`)
- `is_active`, `sort_order`, `raw_source`

View: `public.ebay_business_policies_defaults`
- Returns `shipping_policy_id`, `payment_policy_id`, `return_policy_id` per `(account_key, marketplace_id)`

### Admin API (admin-only)
Router: `backend/app/routers/admin_ebay_business_policies.py`

- `GET /api/admin/ebay/business-policies?account_key=default&marketplace_id=EBAY_US`
  - Returns grouped lists by type: `shipping[]`, `payment[]`, `return[]`
- `GET /api/admin/ebay/business-policies/defaults?account_key=default&marketplace_id=EBAY_US`
  - Returns default IDs: `shipping_policy_id`, `payment_policy_id`, `return_policy_id`
- `POST /api/admin/ebay/business-policies`
  - Allows adding new policies later (supports setting default)

### UI wiring (BIN Listing Debug)
Page: `frontend/src/pages/AdminBinListingPage.tsx`

- On load, fetches policies + defaults from the admin API
- Shows **dropdowns** (Shipping/Payment/Return) in `SellerProfiles` mode
- Auto-selects defaults, then persists user override in `localStorage` per `(account_key, marketplace_id)`

### Verification steps
1. **Run migration** and confirm seed rows exist:
   - `SELECT * FROM public.ebay_business_policies WHERE account_key='default' AND marketplace_id='EBAY_US';`
2. Open **`/admin/bin-listing`**:
   - Dropdowns populate with 3 policies
   - Defaults auto-selected
3. Run **VERIFY**:
   - Confirm request XML contains `<SellerProfiles>` with selected `ShippingProfileID/PaymentProfileID/ReturnProfileID`
4. Change dropdown selections:
   - Confirm outgoing XML changes accordingly
5. Confirm frontend has **no hardcoded policy IDs** (only loaded from API).


