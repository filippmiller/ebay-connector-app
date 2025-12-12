"""Find TEST inventory records and create comprehensive eBay listing report."""
import os
from sqlalchemy import create_engine, text

DATABASE_URL = "postgresql://postgres:2ma5C7qZHXFJJGOG@db.nrpfahjygulsfxmbmfzv.supabase.co:5432/postgres?sslmode=require"
engine = create_engine(DATABASE_URL)

with engine.connect() as conn:
    # Find records with "TEST" in StatusSKU column
    query = text("""
    SELECT *
    FROM tbl_parts_inventory
    WHERE "StatusSKU" ILIKE '%TEST%'
    OR "StatusSKU" = 'TEST'
    LIMIT 5
    """)
    
    result = conn.execute(query)
    rows = result.fetchall()
    
    print(f"\nFound {len(rows)} records with TEST status\n")
    
    if rows:
        columns = result.keys()
        
        for idx, row in enumerate(rows, 1):
            record = dict(zip(columns, row))
            print("="*100)
            print(f"RECORD #{idx} - ID: {record.get('ID')}")
            print("="*100)
            
            # Show only non-null values
            for key, value in sorted(record.items()):
                if value is not None and value != '':
                    print(f"{key:45s}: {value}")
            print()
    else:
        print("No TEST records found. Let me check what statuses exist...")
        status_query = text("SELECT DISTINCT \"StatusSKU\" FROM tbl_parts_inventory WHERE \"StatusSKU\" IS NOT NULL LIMIT 20")
        status_result = conn.execute(status_query)
        print("\nAvailable StatusSKU values:")
        for s_row in status_result:
            print(f"  - {s_row[0]}")

print("\n" + "="*100)
print("EBAY INVENTORY API - REQUIRED FIELDS FOR 'BUY IT NOW' LISTING")
print("="*100)

ebay_fields = """
Based on eBay Inventory API documentation, here are the REQUIRED fields:

** INVENTORY ITEM (createOrReplaceInventoryItem) **
1. SKU (string) - Unique seller identifier ✓
2. Product Details:
   - title (string, max 80 chars) - ✓ Available in OverrideTitle/TitleToChange
   - description (string) - ✓ Available in OverrideDescription/DescriptionToChange  
   - aspects (key-value pairs) - Brand, Model, MPN, UPC, Part Number
   
3. Condition:
   - condition (enum) - NEW, LIKE_NEW, VERY_GOOD, GOOD, ACCEPTABLE, FOR_PARTS_OR_NOT_WORKING
   - conditionDescription (string) - ✓ Available in ConditionDescriptionToChange

4. Product Identifiers (at least ONE required):
   - UPC/EAN/ISBN - Check SKU_catalog
   - ePID (eBay Product ID) - Check SKU_catalog.EPIDValue
   - Brand + MPN - Check SKU_catalog

5. Images:
   - imageUrls (array) - ✓ Available in OverridePicURL1-12
   
6. Availability:
   - quantity (integer) - ✓ Available in Quantity column
   - shipToLocationAvailability.quantity
   
7. PackageWeightAndSize (if using calculated shipping):
   - weight.value + weight.unit
   - dimensions (length/width/height)

** OFFER (createOffer or publishOffer) **
8. Pricing:
   - pricingS strategy (FIXED_PRICE for Buy It Now)
   - price.value - ✓ Available in OverridePrice/PriceToChange
   - price.currency (USD, EUR, etc.)

9. Listing Policies:
   - merchantLocationKey OR fulfillmentPolicyId ✓ Check ShippingGroupID mapping
   - paymentPolicyId  
   - returnPolicyId
   - categoryId - ✓ May be in SKU_catalog or separate category mapping
   
10. Listing Configuration:
    - listingDuration (GTC = Good 'Til Cancelled for Buy It Now)
    - marketplaceId (EBAY_US, EBAY_GB, etc.) - ✓ Check EbayID or default
    - format (FIXED_PRICE for Buy It Now)
    - includeCatalogProductDetails (true/false)
    
11. Tax (optional but recommended):
    - tax.applyTax, tax.vatPercentage (for VAT countries)
    
12. Best Offer (optional):
    - bestOfferEnabled - ✓ Check BestOfferEnabledFlag
    - bestOfferAutoAcceptPrice - ✓ Check BestOfferAutoAcceptPriceValue
    - minimumBestOfferPrice - ✓ Check BestOfferMinimumPriceValue
"""

print(ebay_fields)

print("\n" + "="*100)
print("DATA MAPPING ANALYSIS")
print("="*100)

mapping_analysis = """
AVAILABLE DATA IN tbl_parts_inventory:
✓ HAVE:
  - SKU (SKU column)
  - Title (OverrideTitle or TitleToChange)
  - Description (OverrideDescription or DescriptionToChange)
  - Price (OverridePrice or PriceToChange)
  - Quantity (Quantity column)
  - Images (OverridePicURL1-12)
  - Condition Description (ConditionDescriptionToChange)
  - Best Offer Settings (BestOfferEnabledFlag, Auto-accept values)
  - Shipping Group (ShippingGroupToChange → maps to shipping policy)
  - eBay Account (EbayID, UserName)

❓ NEED TO VERIFY / LOOKUP FROM RELATED TABLES:
  - Condition ID → Need mapping from OverrideConditionID
  - Category ID → Lookup from SKU_catalog or separate category table
  - Product Identifiers (UPC, MPN, Brand, ePID) → SKU_catalog
  - Shipping Policy ID → Map ShippingGroupToChange to eBay policy
  - Payment Policy ID → Need to check if stored or use account default
  - Return Policy ID → Need to check if stored or use account default
  - Package dimensions/weight → May be in SKU_catalog or shipping groups

🔍 NEXT STEPS:
1. Query SKU_catalog for actual TEST record's SKU to see product identifiers
2. Check tbl_shippinggroups structure for policy mappings
3. Verify if eBay policy IDs are stored somewhere or need to be created
4. Check if there's a category mapping table
"""

print(mapping_analysis)
