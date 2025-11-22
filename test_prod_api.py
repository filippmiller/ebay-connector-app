import requests
import sys

BASE_URL = "https://ebay-connector-app-production.up.railway.app"
EMAIL = "filippmiller@gmail.com"
PASSWORD = "Airbus380+"

def test_prod_grid():
    print(f"Testing connection to {BASE_URL}...")
    
    # 1. Login
    login_url = f"{BASE_URL}/auth/login"
    try:
        print(f"Logging in to {login_url}...")
        resp = requests.post(login_url, json={"email": EMAIL, "password": PASSWORD}, timeout=10)
        if resp.status_code != 200:
            print(f"Login failed: {resp.status_code} {resp.text}")
            return
        
        data = resp.json()
        token = data.get("access_token")
        if not token:
            print("No access token returned")
            return
            
        print("Login successful. Token received.")
        
        # 2. Fetch Grid Preferences
        headers = {"Authorization": f"Bearer {token}"}
        grid_key = "orders"
        prefs_url = f"{BASE_URL}/api/grid/preferences"
        
        print(f"Fetching grid preferences for '{grid_key}' from {prefs_url}...")
        resp = requests.get(prefs_url, params={"grid_key": grid_key}, headers=headers, timeout=30)
        
        print(f"Response Status: {resp.status_code}")
        if resp.status_code == 200:
            print("Response Data:")
            print(resp.json())
        else:
            print(f"Error: {resp.text}")

        # 3. Fetch Legacy Layout (Fallback)
        legacy_url = f"{BASE_URL}/api/grids/{grid_key}/layout"
        print(f"Fetching legacy layout for '{grid_key}' from {legacy_url}...")
        resp = requests.get(legacy_url, headers=headers, timeout=30)
        print(f"Legacy Response Status: {resp.status_code}")
        if resp.status_code == 200:
             print("Legacy Data found")
        else:
             print(f"Legacy Error: {resp.status_code}")

    except Exception as e:
        print(f"Exception occurred: {e}")

if __name__ == "__main__":
    test_prod_grid()
