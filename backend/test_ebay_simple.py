import asyncio
import httpx

# Use the token from the last login
TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJlMzk5ZWEyMy0xMmFjLTRiOTItOGMzMi1hZDI5YWNlNTM3YmQiLCJleHAiOjE3NjExMzU4MTd9.qxQYglqiXpkVy7Qm-RLJAP6Lq1IG1Jx1GILeR6R6Fsw"

async def test_ebay_api():
    # First get the eBay token from the backend
    print("=== Getting eBay token from backend ===")
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://app-vatxxrtj.fly.dev/admin/ebay/connection-status",
            headers={"Authorization": f"Bearer {TOKEN}"},
            timeout=30.0
        )
        print(f"Connection status response: {response.status_code}")
        if response.status_code != 200:
            print(f"Error: {response.text}")
            return
        
        data = response.json()
        print(f"Connected: {data.get('connected')}")
        
        if not data.get('connected'):
            print("Not connected to eBay")
            return
        
        # Get the eBay access token - we'll need to call a different endpoint
        # Let's try the diagnostics endpoint to see what error we get
        print("\n=== Testing diagnostics endpoint ===")
        response = await client.get(
            "https://app-vatxxrtj.fly.dev/messages/diagnostics?mode=folders",
            headers={"Authorization": f"Bearer {TOKEN}"},
            timeout=30.0
        )
        print(f"Diagnostics response status: {response.status_code}")
        print(f"Diagnostics response: {response.text[:500]}")

asyncio.run(test_ebay_api())
