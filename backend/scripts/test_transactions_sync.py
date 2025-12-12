#!/usr/bin/env python3
"""
Test transactions sync by calling eBay API directly.
"""

import sys
import os
import asyncio
import hashlib
import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone, timedelta
from app.models_sqlalchemy import SessionLocal
from app.models_sqlalchemy.models import EbayAccount, EbayToken, User
from app.config import settings


def compute_token_hash(token: str) -> str:
    if not token:
        return "empty"
    return hashlib.sha256(token.encode()).hexdigest()[:16]


async def test_transactions_api(access_token: str, environment: str) -> dict:
    """Call eBay Finances API directly to test transactions."""
    
    if environment == "production":
        base_url = "https://apiz.ebay.com"
    else:
        base_url = "https://apiz.sandbox.ebay.com"
    
    # Use a simple window
    now = datetime.now(timezone.utc)
    window_from = (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    window_to = now.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    
    url = f"{base_url}/sell/finances/v1/transaction"
    params = {
        "filter": f"transactionDate:[{window_from}..{window_to}]",
        "limit": "5",
    }
    
    print(f"   Calling: {url}")
    print(f"   Filter: transactionDate:[{window_from}..{window_to}]")
    print(f"   Token hash: {compute_token_hash(access_token)}")
    print(f"   Token prefix: {access_token[:30] if access_token else 'N/A'}...")
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                url,
                params=params,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )
            
            print(f"   Response status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                total = data.get("total", 0)
                return {"success": True, "total": total}
            else:
                error_data = response.json() if response.content else {}
                return {"success": False, "status": response.status_code, "error": error_data}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def main():
    print("=" * 80)
    print("TRANSACTIONS API DIRECT TEST")
    print("=" * 80)
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print(f"settings.EBAY_ENVIRONMENT: {settings.EBAY_ENVIRONMENT}")
    print()

    db = SessionLocal()
    try:
        # Get mil_243 account (the one from the user's logs)
        accounts = db.query(EbayAccount).filter(
            EbayAccount.is_active == True,
            EbayAccount.ebay_user_id == "mil_243"
        ).all()
        
        if not accounts:
            print("mil_243 account not found, getting first active account")
            accounts = db.query(EbayAccount).filter(EbayAccount.is_active == True).limit(1).all()
        
        for acc in accounts:
            print("-" * 60)
            print(f"Account: {acc.house_name} ({acc.ebay_user_id})")
            print("-" * 60)
            
            # Get user
            user = db.query(User).filter(User.id == acc.org_id).first()
            user_env = user.ebay_environment if user else None
            print(f"User.ebay_environment: {user_env}")
            
            # Get token
            token = db.query(EbayToken).filter(EbayToken.ebay_account_id == acc.id).first()
            if not token:
                print("   ERROR: No token found!")
                continue
            
            print(f"Token expires_at: {token.expires_at}")
            print(f"Token last_refreshed: {token.last_refreshed_at}")
            
            # Check the raw encrypted value vs decrypted
            print()
            print("Checking token decryption:")
            raw_token = token._access_token  # Get raw encrypted value
            decrypted_token = token.access_token  # Get via property (should decrypt)
            
            print(f"   Raw (encrypted) starts with: {raw_token[:30] if raw_token else 'N/A'}...")
            print(f"   Decrypted starts with: {decrypted_token[:30] if decrypted_token else 'N/A'}...")
            
            is_encrypted = raw_token and raw_token.startswith("ENC:v1:")
            decryption_worked = decrypted_token and not decrypted_token.startswith("ENC:v1:")
            
            print(f"   Token is encrypted in DB: {is_encrypted}")
            print(f"   Decryption worked: {decryption_worked}")
            
            if not decryption_worked:
                print("   ⚠️ DECRYPTION FAILED! Token is still encrypted!")
                # Show what the crypto error was
                from app.utils import crypto
                test_decrypt = crypto.decrypt(raw_token)
                print(f"   After manual decrypt: {test_decrypt[:30] if test_decrypt else 'N/A'}...")
                continue
            
            # Test the API
            print()
            print("Testing Transactions API (production):")
            result = await test_transactions_api(decrypted_token, "production")
            print(f"   Result: {result}")
            
            if result.get("success"):
                print("✅ Transactions API works!")
            else:
                print("❌ Transactions API failed!")

    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())

