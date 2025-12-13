import asyncio
import os
import sys

# Add backend to sys.path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

# Set env vars BEFORE importing app modules
os.environ["DATABASE_URL"] = "postgresql://postgres:2ma5C7qZHXFJJGOG@db.nrpfahjygulsfxmbmfzv.supabase.co:5432/postgres?sslmode=require"
os.environ["EBAY_ENVIRONMENT"] = "production"
os.environ["EBAY_PRODUCTION_CLIENT_ID"] = "filippmi-betterpl-PRD-0115bff8e-85d4f36a"
os.environ["EBAY_PRODUCTION_CERT_ID"] = "PRD-115bff8e0fbc-840b-4933-a9ce-4485"
os.environ["EBAY_PRODUCTION_DEV_ID"] = "c489fac8-41cb-4293-9a5d-e7c51df0646e"

try:
    from app.services.ebay import ebay_service
    from app.services.ebay_api_client import search_active_listings
    from app.utils.logger import logger
except Exception as e:
    print(f"Import failed: {e}")
    sys.exit(1)

async def test_search():
    print("Getting token...")
    try:
        token = await ebay_service.get_browse_app_token()
        print(f"Token obtained (len={len(token)})")
    except Exception as e:
        print(f"Failed to get token: {e}")
        return

    keyword = "Lenovo L500"
    
    print(f"\n--- Test 1: Sort by Price (Ascending) ---")
    try:
        results = await search_active_listings(token, keyword, limit=5, sort="price")
        print(f"Found {len(results)} results.")
        last_price = -1.0
        for item in results:
            total = (item.price or 0) + (item.shipping or 0)
            print(f"- {item.title} | Price: {item.price} | Shipping: {item.shipping} | Total: {total}")
            if last_price != -1.0 and total < last_price:
                 print("  WARNING: Price order violation?")
            last_price = total
    except Exception as e:
        print(f"Search failed: {e}")

    print(f"\n--- Test 2: Pagination (Offset) ---")
    try:
        page1 = await search_active_listings(token, keyword, limit=2, offset=0)
        print("Page 1:")
        for item in page1:
            print(f"- {item.item_id}: {item.title}")
            
        page2 = await search_active_listings(token, keyword, limit=2, offset=2)
        print("Page 2:")
        for item in page2:
            print(f"- {item.item_id}: {item.title}")
            
        # Verify no overlap
        ids1 = {i.item_id for i in page1}
        ids2 = {i.item_id for i in page2}
        if ids1.intersection(ids2):
             print("ERROR: Overlap between pages!")
        else:
             print("SUCCESS: No overlap between pages.")

    except Exception as e:
        print(f"Search failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_search())
