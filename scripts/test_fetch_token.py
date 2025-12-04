#!/usr/bin/env python3
"""
Test script for /api/admin/internal/test-fetch-token endpoint.

Usage:
    python scripts/test_fetch_token.py <ebay_account_id> [api_url] [internal_api_key]
    
Example:
    python scripts/test_fetch_token.py e524cb1f-87c2-4eda-9518-721fc66bd0c0
"""

import sys
import os
import requests
import json
from typing import Optional

def test_fetch_token(
    ebay_account_id: str,
    api_url: Optional[str] = None,
    internal_api_key: Optional[str] = None,
) -> dict:
    """Test the fetch_active_ebay_token endpoint."""
    
    # Get API URL from environment or use default
    if not api_url:
        api_url = os.getenv("WEB_APP_URL") or os.getenv("API_URL") or "http://localhost:8000"
    
    # Get INTERNAL_API_KEY from environment
    if not internal_api_key:
        internal_api_key = os.getenv("INTERNAL_API_KEY")
    
    if not internal_api_key:
        print("ERROR: INTERNAL_API_KEY not found in environment variables")
        print("Please set INTERNAL_API_KEY environment variable or pass it as argument")
        return {"error": "INTERNAL_API_KEY missing"}
    
    endpoint = f"{api_url.rstrip('/')}/api/admin/internal/test-fetch-token"
    
    payload = {
        "internal_api_key": internal_api_key,
        "ebay_account_id": ebay_account_id,
        "triggered_by": "test_script",
        "api_family": "transactions",
    }
    
    print(f"Testing endpoint: {endpoint}")
    print(f"Account ID: {ebay_account_id}")
    print(f"Payload: {json.dumps({**payload, 'internal_api_key': '***'}, indent=2)}")
    print("-" * 60)
    
    try:
        response = requests.post(
            endpoint,
            json=payload,
            timeout=30,
        )
        
        print(f"Status Code: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")
        print("-" * 60)
        
        if response.status_code == 200:
            result = response.json()
            print("Response:")
            print(json.dumps(result, indent=2))
            print("-" * 60)
            
            # Analyze result
            if result.get("success"):
                if result.get("token_is_decrypted"):
                    print("✅ SUCCESS: Token is decrypted!")
                    print(f"   Token prefix: {result.get('token_prefix')}")
                    print(f"   Token hash: {result.get('token_hash')}")
                    print(f"   Build number: {result.get('build_number')}")
                else:
                    print("⚠️  WARNING: Token is still encrypted!")
                    print(f"   Token prefix: {result.get('token_prefix')}")
                    print("   This indicates SECRET_KEY mismatch or decryption failure")
            else:
                print("❌ FAILED: Token retrieval failed")
                print(f"   Error: {result.get('error')}")
            
            return result
        else:
            print(f"ERROR: HTTP {response.status_code}")
            print(f"Response: {response.text}")
            return {"error": f"HTTP {response.status_code}", "response": response.text}
            
    except requests.exceptions.RequestException as e:
        print(f"ERROR: Request failed: {e}")
        return {"error": str(e)}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    ebay_account_id = sys.argv[1]
    api_url = sys.argv[2] if len(sys.argv) > 2 else None
    internal_api_key = sys.argv[3] if len(sys.argv) > 3 else None
    
    result = test_fetch_token(ebay_account_id, api_url, internal_api_key)
    
    # Exit with error code if failed
    if result.get("error") or not result.get("success") or not result.get("token_is_decrypted"):
        sys.exit(1)
    else:
        sys.exit(0)

