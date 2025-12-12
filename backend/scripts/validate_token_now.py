#!/usr/bin/env python3
"""
Validate current tokens against eBay Identity API.
"""

import sys
import os
import asyncio
import hashlib
import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone
from app.models_sqlalchemy import SessionLocal
from app.models_sqlalchemy.models import EbayAccount, EbayToken, User
from app.config import settings


def compute_token_hash(token: str) -> str:
    """Compute SHA256 hash prefix for logging."""
    if not token:
        return "empty"
    return hashlib.sha256(token.encode()).hexdigest()[:16]


async def validate_token_with_identity_api(access_token: str, environment: str) -> dict:
    """Call eBay Identity API to validate token."""
    if environment == "production":
        identity_url = "https://apiz.ebay.com/commerce/identity/v1/user"
    else:
        identity_url = "https://apiz.sandbox.ebay.com/commerce/identity/v1/user"
    
    print(f"   Calling Identity API: {identity_url}")
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                identity_url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
            )
            
            print(f"   Response status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                return {"valid": True, "user_id": data.get("userId"), "username": data.get("username")}
            else:
                error_data = response.json() if response.content else {}
                return {"valid": False, "status": response.status_code, "error": error_data}
    except Exception as e:
        return {"valid": False, "error": str(e)}


async def main():
    print("=" * 80)
    print("TOKEN VALIDATION DIAGNOSTIC")
    print("=" * 80)
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print(f"settings.EBAY_ENVIRONMENT: {settings.EBAY_ENVIRONMENT}")
    print()

    db = SessionLocal()
    try:
        accounts = db.query(EbayAccount).filter(EbayAccount.is_active == True).all()
        
        for acc in accounts:
            print("-" * 60)
            print(f"Account: {acc.house_name} ({acc.ebay_user_id})")
            print(f"Account ID: {acc.id}")
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
            
            print(f"Token ID: {token.id}")
            print(f"Token hash: {compute_token_hash(token.access_token)}")
            print(f"Token length: {len(token.access_token) if token.access_token else 0}")
            print(f"Token prefix: {token.access_token[:30] if token.access_token else 'N/A'}...")
            print(f"Expires at: {token.expires_at}")
            print(f"Last refreshed: {token.last_refreshed_at}")
            print(f"Refresh error: {token.refresh_error}")
            
            # Validate with Identity API using PRODUCTION
            print()
            print("Validating with PRODUCTION Identity API:")
            prod_result = await validate_token_with_identity_api(token.access_token, "production")
            print(f"   Result: {prod_result}")
            
            # Also try sandbox to see if token is for wrong environment
            print()
            print("Validating with SANDBOX Identity API:")
            sandbox_result = await validate_token_with_identity_api(token.access_token, "sandbox")
            print(f"   Result: {sandbox_result}")
            
            # Conclusion
            print()
            if prod_result.get("valid"):
                print("✅ Token is VALID for PRODUCTION")
            elif sandbox_result.get("valid"):
                print("⚠️ Token is VALID for SANDBOX but NOT production!")
                print("   This means token refresh is using wrong environment!")
            else:
                print("❌ Token is INVALID for both environments")
            
            print()

    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())

