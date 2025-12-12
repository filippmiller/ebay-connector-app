#!/usr/bin/env python3
"""
Test grid endpoints via HTTP (if backend is running).

This script tests the actual HTTP endpoints to see if they return data.
"""

import requests
import json
import sys

# Base URL - adjust if backend is running on different port
BASE_URL = "http://127.0.0.1:8081"

GRID_KEYS = [
    "orders",
    "transactions",
    "finances",
    "finances_fees",
    "buying",
    "sku_catalog",
    "active_inventory",
    "inventory",
    "cases",
    "offers",
]

def test_preferences_endpoint(grid_key, token=None):
    """Test GET /api/grid/preferences endpoint."""
    url = f"{BASE_URL}/api/grid/preferences"
    params = {"grid_key": grid_key}
    headers = {}
    
    if token:
        headers["Authorization"] = f"Bearer {token}"
    
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            available_cols = data.get("available_columns", [])
            columns_cfg = data.get("columns", {})
            
            return {
                "status": "OK",
                "available_columns_count": len(available_cols),
                "visible_columns_count": len(columns_cfg.get("visible", [])),
                "has_columns_config": bool(columns_cfg),
            }
        elif resp.status_code == 401:
            return {"status": "AUTH_REQUIRED", "error": "Authentication required"}
        else:
            return {"status": "ERROR", "status_code": resp.status_code, "error": resp.text[:100]}
    except requests.exceptions.ConnectionError:
        return {"status": "NOT_RUNNING", "error": "Backend not running on " + BASE_URL}
    except Exception as e:
        return {"status": "ERROR", "error": str(e)}

def test_data_endpoint(grid_key, token=None):
    """Test GET /api/grids/{grid_key}/data endpoint."""
    url = f"{BASE_URL}/api/grids/{grid_key}/data"
    params = {"limit": 1, "offset": 0}
    headers = {}
    
    if token:
        headers["Authorization"] = f"Bearer {token}"
    
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            rows = data.get("rows", [])
            total = data.get("total", 0)
            
            return {
                "status": "OK",
                "rows_returned": len(rows),
                "total": total,
                "has_data": len(rows) > 0,
            }
        elif resp.status_code == 401:
            return {"status": "AUTH_REQUIRED", "error": "Authentication required"}
        else:
            return {"status": "ERROR", "status_code": resp.status_code, "error": resp.text[:100]}
    except requests.exceptions.ConnectionError:
        return {"status": "NOT_RUNNING", "error": "Backend not running on " + BASE_URL}
    except Exception as e:
        return {"status": "ERROR", "error": str(e)}

def main():
    print("="*80)
    print("GRID ENDPOINTS HTTP TEST")
    print("="*80)
    print(f"Testing backend at: {BASE_URL}")
    print("Note: This requires backend to be running and may require authentication")
    print()
    
    # Test if backend is running
    try:
        resp = requests.get(f"{BASE_URL}/healthz", timeout=2)
        if resp.status_code == 200:
            print("✅ Backend is running")
        else:
            print(f"⚠️  Backend responded with {resp.status_code}")
    except:
        print("❌ Backend is not running or not accessible")
        print("   Start backend with: npx -y @railway/cli@latest run --service 31ec6c36-62b8-4f9c-b880-77476b8d340c --environment 524635cb-8338-482e-b9d6-002af8a12bcd -- poetry run uvicorn app.main:app --host 127.0.0.1 --port 8081 --reload")
        return
    
    print("\n" + "="*80)
    print("TESTING PREFERENCES ENDPOINTS")
    print("="*80)
    
    prefs_results = {}
    for grid_key in GRID_KEYS:
        result = test_preferences_endpoint(grid_key)
        prefs_results[grid_key] = result
        
        if result["status"] == "OK":
            cols_count = result.get("available_columns_count", 0)
            if cols_count > 0:
                print(f"✅ {grid_key}: {cols_count} available columns")
            else:
                print(f"❌ {grid_key}: NO COLUMNS in response")
        elif result["status"] == "AUTH_REQUIRED":
            print(f"⚠️  {grid_key}: Requires authentication")
        else:
            print(f"❌ {grid_key}: {result.get('error', 'Unknown error')}")
    
    print("\n" + "="*80)
    print("TESTING DATA ENDPOINTS")
    print("="*80)
    
    data_results = {}
    for grid_key in GRID_KEYS:
        result = test_data_endpoint(grid_key)
        data_results[grid_key] = result
        
        if result["status"] == "OK":
            total = result.get("total", 0)
            rows = result.get("rows_returned", 0)
            if total > 0:
                print(f"✅ {grid_key}: {total:,} total rows, {rows} returned")
            else:
                print(f"⚠️  {grid_key}: Table is empty (0 rows)")
        elif result["status"] == "AUTH_REQUIRED":
            print(f"⚠️  {grid_key}: Requires authentication")
        else:
            print(f"❌ {grid_key}: {result.get('error', 'Unknown error')}")
    
    # Summary
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    
    prefs_ok = sum(1 for r in prefs_results.values() if r.get("status") == "OK" and r.get("available_columns_count", 0) > 0)
    data_ok = sum(1 for r in data_results.values() if r.get("status") == "OK" and r.get("total", 0) > 0)
    
    print(f"Preferences endpoints: {prefs_ok}/{len(GRID_KEYS)} with columns")
    print(f"Data endpoints: {data_ok}/{len(GRID_KEYS)} with data")
    
    if prefs_ok < len(GRID_KEYS) or data_ok < len(GRID_KEYS):
        print("\n⚠️  Some grids need attention - check results above")

if __name__ == "__main__":
    main()

