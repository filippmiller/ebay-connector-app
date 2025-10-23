import asyncio
import httpx
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://postgres:EVfiVxDuuwRa8hAx@db.nrpfahjygulsfxmbmfzv.supabase.co:5432/postgres?sslmode=require')

async def test_ebay_api():
    from app.database import SessionLocal
    from app.db_models import User
    
    db = SessionLocal()
    user = db.query(User).filter(User.email == "filippmiller@gmail.com").first()
    
    if not user or not user.ebay_access_token:
        print("ERROR: User not found or no eBay token")
        return
    
    print(f"User ID: {user.id}")
    print(f"eBay connected: {user.ebay_connected}")
    print(f"Token exists: {bool(user.ebay_access_token)}")
    
    api_url = "https://api.ebay.com/ws/api.dll"
    
    xml_request = f"""<?xml version="1.0" encoding="utf-8"?>
<GetMyMessagesRequest xmlns="urn:ebay:apis:eBLBaseComponents">
  <RequesterCredentials>
    <eBayAuthToken>{user.ebay_access_token}</eBayAuthToken>
  </RequesterCredentials>
  <DetailLevel>ReturnSummary</DetailLevel>
  <WarningLevel>High</WarningLevel>
</GetMyMessagesRequest>"""
    
    headers = {
        "X-EBAY-API-COMPATIBILITY-LEVEL": "1201",
        "X-EBAY-API-CALL-NAME": "GetMyMessages",
        "X-EBAY-API-SITEID": "0",
        "Content-Type": "text/xml",
        "Accept": "text/xml"
    }
    
    print("\n=== Making eBay API request ===")
    async with httpx.AsyncClient() as client:
        response = await client.post(
            api_url,
            content=xml_request,
            headers=headers,
            timeout=30.0
        )
        
        print(f"Status code: {response.status_code}")
        print(f"Response length: {len(response.text)}")
        print(f"\nFirst 1000 chars of response:")
        print(response.text[:1000])

asyncio.run(test_ebay_api())
