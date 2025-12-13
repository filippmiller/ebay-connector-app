import requests
import json

response = requests.get("http://127.0.0.1:8083/api/sq/dictionaries")
print(f"Status: {response.status_code}")

if response.status_code == 200:
    data = response.json()
    shipping_groups = data.get("shipping_groups", [])
    print(f"\nShipping groups count: {len(shipping_groups)}")
    print("\nShipping groups:")
    for group in shipping_groups:
        print(json.dumps(group, indent=2))
else:
    print(f"Error: {response.text}")
