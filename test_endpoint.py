#!/usr/bin/env python3
"""Test POST to parts-models endpoint to see full error"""

import requests
import json

# Test creating a model with minimal data
url = "https://ebay-connector-app-production.up.railway.app/api/sq/parts-models"

payload = {
    "model": "Test Model 123"
}

headers = {
    "Content-Type": "application/json",
    # Add auth token if needed - for now testing without
}

print("Testing POST to:", url)
print("Payload:", json.dumps(payload, indent=2))
print("\nSending request...")

try:
    response = requests.post(url, json=payload, headers=headers)
    print(f"\nStatus Code: {response.status_code}")
    print(f"Response Headers: {dict(response.headers)}")
    print(f"\nResponse Body:")
    print(response.text)
    
    if response.status_code != 200:
        print("\n❌ Error occurred!")
        try:
            error_data = response.json()
            print("Error details:", json.dumps(error_data, indent=2))
        except:
            pass
    else:
        print("\n✅ Success!")
        
except Exception as e:
    print(f"\n❌ Exception: {e}")
    import traceback
    traceback.print_exc()
