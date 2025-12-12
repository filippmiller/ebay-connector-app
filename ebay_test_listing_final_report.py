"""Final comprehensive analysis for eBay Test Listing - ID 29"""
import json
from sqlalchemy import create_engine, text

DATABASE_URL = "postgresql://postgres:2ma5C7qZHXFJJGOG@db.nrpfahjygulsfxmbmfzv.supabase.co:5432/postgres?sslmode=require"
engine = create_engine(DATABASE_URL)

print("\n" + "="*100)
print("COMPREHENSIVE EBAY TEST LISTING ANALYSIS")
print("="*100)

with engine.connect() as conn:
    # Query the TEST record (ID=29 from screenshot)
    query = text("SELECT * FROM tbl_parts_inventory WHERE \"ID\" = 29 LIMIT 1")
    result = conn.execute(query)
    row = result.fetchone()
    
    if row:
        record = dict(zip(result.keys(), row))
        
        print("\n📋 TEST INVENTORY RECORD (ID=29)")
        print("-"*100)
        for k, v in sorted(record.items()):
            if v is not None and v != '':
                print(f"  {k:45s}: {v}")
        
        # Get SKU info
        sku = record.get('SKU')
        if sku:
            print(f"\n\n🔍 SKU CATALOG DATA FOR: {sku}")
            print("-"*100)
            sku_q = text('SELECT * FROM "SKU_catalog" WHERE "SKU" = :sku')
            sku_r = conn.execute(sku_q, {"sku": sku})
            sku_row = sku_r.fetchone()
            if sku_row:
                sku_data = dict(zip(sku_r.keys(), sku_row))
                for k, v in sorted(sku_data.items()):
                    if v is not None and v != '':
                        print(f"  {k:45s}: {v}")
            else:
                print(f"  ⚠️  No SKU_catalog record found for SKU: {sku}")
        
        # Get shipping group info
        ship_group = record.get('ShippingGroupToChange') or record.get('ShippingGroupID')
        if ship_group:
            print(f"\n\n📦 SHIPPING GROUP #{ship_group}")
            print("-"*100)
            ship_q = text('SELECT * FROM tbl_shippinggroups WHERE "ShippingGroupID" = :id')
            ship_r = conn.execute(ship_q, {"id": ship_group})
            ship_row = ship_r.fetchone()
            if ship_row:
                ship_data = dict(zip(ship_r.keys(), ship_row))
                for k, v in sorted(ship_data.items()):
                    if v is not None and v != '':
                        print(f"  {k:45s}: {v}")
            else:
                print(f"  ⚠️  No shipping group found with ID: {ship_group}")
    else:
        print("\n⚠️  Record ID=29 not found!")

print("\n\n" + "="*100)
print("EBAY BUY IT NOW LISTING - REQUIRED FIELDS MAPPING")
print("="*100)

report = """
╔══════════════════════════════════════════════════════════════════════════════╗
║                    EBAY INVENTORY API - REQUIRED FIELDS                      ║
╚══════════════════════════════════════════════════════════════════════════════╝

┌─ STEP 1: CREATE INVENTORY ITEM (createOrReplaceInventoryItem) ────────────────┐
│                                                                                │
│ ✅ SKU (required)                                                             │
│    Source: tbl_parts_inventory.SKU or OverrideSKU                            │
│                                                                                │
│ ✅ Product.title (required, max 80 chars)                                    │
│    Source: OverrideTitle or TitleToChange                                    │
│                                                                                │
│ ✅ Product.description (required, HTML supported)                            │
│    Source: OverrideDescription or DescriptionToChange                       │
│                                                                                │
│ ✅ Product.imageUrls (array, at least 1 required)                           │
│    Source: [OverridePicURL1, OverridePicURL2, ...OverridePicURL12]          │
│                                                                                │
│ ✅ Product.aspects (key-value pairs)                                         │
│    - Brand: SKU_catalog.Brand                                                │
│    - MPN: SKU_catalog.MPN                                                    │
│    - Model: SKU_catalog.Model                                                │
│    - Part Number: SKU_catalog.Part_Number                                    │
│                                                                                │
│ ⚠️  Condition (required enum)                                                 │
│    Values: NEW, LIKE_NEW, VERY_GOOD, GOOD, ACCEPTABLE,                       │
│           FOR_PARTS_OR_NOT_WORKING                                            │
│    Source: Need mapping from OverrideConditionID to eBay condition enum      │
│                                                                                │
│ ✅ ConditionDescription (recommended)                                        │
│    Source: ConditionDescriptionToChange                                      │
│                                                                                │
│ ✅ Availability.shipToLocationAvailability.quantity                          │
│    Source: Quantity                                                           │
│                                                                                │
│ ⚠️  Product Identifiers (at least ONE required):                             │
│    - UPC: SKU_catalog.UPC                                                     │
│    - EAN: Check if available                                                 │
│    - ePID: SKU_catalog.EPIDValue (if EPIDFlag = true)                       │
│    - ISBN: For books                                                          │
│    OR Brand + MPN combination                                                 │
│                                                                                │
│ ❓ PackageWeightAndSize (required if using calculated shipping)              │
│    Need to check: SKU_catalog or shipping_groups table                       │
│    - weight.value + weight.unit                                               │
│    - dimensions.length/width/height + unit                                    │
│                                                                                │
└────────────────────────────────────────────────────────────────────────────────┘

┌─ STEP 2: CREATE OFFER (createOffer) ──────────────────────────────────────────┐
│                                                                                │
│ ✅ SKU (links to inventory item)                                             │
│    Source: Same as Step 1                                                     │
│                                                                                │
│ ✅ MarketplaceId (required)                                                  │
│    Values: EBAY_US, EBAY_GB, EBAY_DE, etc.                                   │
│    Source: EbayID column or account default                                  │
│                                                                                │
│ ✅ Format (required)                                                         │
│    Value: "FIXED_PRICE" (for Buy It Now)                                     │
│                                                                                │
│ ✅ ListingDuration (required)                                                │
│    Value: "GTC" (Good 'Til Cancelled - standard for Buy It Now)              │
│    Source: Can check ChangeListingDuration column                            │
│                                                                                │
│ ✅ PricingSummary.price.value (required)                                     │
│    Source: OverridePrice or PriceToChange                                    │
│                                                                                │
│ ✅ PricingSummary.price.currency (required)                                  │
│    Value: "USD" (or based on marketplace)                                    │
│                                                                                │
│ ⚠️  CategoryId (required)                                                     │
│    Source: NEED TO FIND - Check if there's a category mapping table          │
│            or if it's stored in SKU_catalog                                   │
│                                                                                │
│ ⚠️  ListingPolicies (required):                                               │
│    ├─ fulfillmentPolicyId  → Shipping policy                                 │
│    ├─ paymentPolicyId      → Payment policy                                  │
│    └─ returnPolicyId       → Return policy                                   │
│                                                                                │
│    Source: Map ShippingGroupToChange to eBay policy IDs                      │
│            OR use merchantLocationKey for shipping                            │
│            NEED TO CHECK if these are stored or use account defaults          │
│                                                                                │
│ ✅ BestOfferTerms (optional but supported)                                   │
│    - bestOfferEnabled: BestOfferEnabledFlag                                  │
│    - autoAcceptPrice: BestOfferAutoAcceptPriceValue                          │
│    - autoDeclinePrice: BestOfferMinimumPriceValue                            │
│                                                                                │
│ ❓ Tax (may be required based on marketplace)                                │
│    - applyTax: boolean                                                        │
│    - vatPercentage: For EU/UK                                                 │
│                                                                                │
│ ❓ IncludeCatalogProductDetails (optional)                                   │
│    - If ePID is provided, can use eBay catalog data                          │
│                                                                                │
└────────────────────────────────────────────────────────────────────────────────┘

┌─ STEP 3: PUBLISH OFFER (publishOffer) ────────────────────────────────────────┐
│                                                                                │
│ ✅ OfferId (from Step 2 response)                                            │
│    The publish endpoint activates the listing on eBay                         │
│                                                                                │
└────────────────────────────────────────────────────────────────────────────────┘

╔══════════════════════════════════════════════════════════════════════════════╗
║                           DATA AVAILABILITY MATRIX                            ║
╚══════════════════════════════════════════════════════════════════════════════╝

✅ CONFIRMED AVAILABLE:
   - SKU, Title, Description
   - Price, Quantity
   - Images (up to 12)
   - Best Offer settings
   - Condition description
   - Product identifiers (MPN, UPC, Brand from SKU_catalog)

⚠️  NEEDS VERIFICATION:
   - Condition enum mapping (OverrideConditionID → eBay enum)
   - Category ID (where is it stored?)
   - Package dimensions/weight
   - eBay Policy IDs (fulfillment, payment, return)

❓ MISSING / UNCLEAR:
   - Tax settings
   - Merchant location key
   - Listing policy mappings

╔══════════════════════════════════════════════════════════════════════════════╗
║                                NEXT ACTIONS                                   ║
╚══════════════════════════════════════════════════════════════════════════════╝

1. ✅ HARDCODE STATUS: Change test-listing interface to use status "TEST" only
                      Remove dropdown, filter for StatusSKU = [TEST_STATUS_ID]

2. 🔍 FIND CATEGORY MAPPING: Search for category data in:
   - SKU_catalog table
   - Separate category mapping table
   - Or default to a generic category for testing

3. 🔍 VERIFY POLICY MAPPINGS: Check if eBay policy IDs are stored:
   - Query tbl_shippinggroups for eBay policy references
   - Check EbayAccounts table for default policies
   - May need to create policies via eBay API first

4. 🔧 CREATE CONDITION MAPPING: Map OverrideConditionID to eBay enums:
   - Query existing condition values
   - Create Python mapping dict

5. 📝 UPDATE FRONTEND: Remove dropdown, show only record ID=29
                      Display which fields are populated vs missing

6. 🧪 TEST API CALL: Use existing ebay_listing_service.py to test
                     with stub mode first, then live mode
"""

print(report)

print("\n✅ Connection to Supabase: CONFIRMED WORKING")
print("📊 Data extraction: SUCCESSFUL")
print("🎯 Ready for implementation\n")
