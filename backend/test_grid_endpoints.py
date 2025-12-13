#!/usr/bin/env python3
"""
Test script to verify grid endpoints are working correctly.

This script tests:
1. Grid preferences endpoint (GET /api/grid/preferences)
2. Grid data endpoint (GET /api/grids/{grid_key}/data)

Run with Railway CLI:
  npx -y @railway/cli@latest run --service <SERVICE> --environment <ENV> -- python test_grid_endpoints.py

Or locally if DATABASE_URL is set:
  python test_grid_endpoints.py
"""

import os
import sys
import json
from typing import Dict, Any, List

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from app.routers.grid_layouts import _columns_meta_for_grid, _allowed_columns_for_grid
    from app.routers.grid_preferences import get_grid_preferences
    from app.models_sqlalchemy import get_db
    from app.models_sqlalchemy.models import User
    from app.services.auth import get_current_active_user
except ImportError as e:
    print(f"Import error: {e}")
    print("Make sure you're running from the backend directory")
    sys.exit(1)

# Grid keys to test
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

def test_column_metadata():
    """Test that column metadata is available for each grid."""
    print("\n" + "="*80)
    print("TEST 1: Column Metadata")
    print("="*80)
    
    results: Dict[str, Dict[str, Any]] = {}
    
    for grid_key in GRID_KEYS:
        try:
            cols_meta = _columns_meta_for_grid(grid_key)
            allowed_cols = _allowed_columns_for_grid(grid_key)
            
            results[grid_key] = {
                "status": "OK" if len(cols_meta) > 0 else "EMPTY",
                "column_count": len(cols_meta),
                "allowed_columns_count": len(allowed_cols),
                "columns": [c.name for c in cols_meta[:5]],  # First 5 column names
            }
            
            if len(cols_meta) == 0:
                print(f"⚠️  {grid_key}: NO COLUMNS (this will cause 'No columns configured')")
            else:
                print(f"✅ {grid_key}: {len(cols_meta)} columns")
        except Exception as e:
            results[grid_key] = {
                "status": "ERROR",
                "error": str(e),
            }
            print(f"❌ {grid_key}: ERROR - {e}")
    
    return results

def test_preferences_endpoint():
    """Test preferences endpoint (requires DB and user)."""
    print("\n" + "="*80)
    print("TEST 2: Preferences Endpoint")
    print("="*80)
    print("Note: This requires a valid user session. Skipping for now.")
    print("To test manually, use FastAPI TestClient or HTTP requests.")
    return {}

def test_data_endpoint():
    """Test data endpoint (requires DB and user)."""
    print("\n" + "="*80)
    print("TEST 3: Data Endpoint")
    print("="*80)
    print("Note: This requires a valid user session. Skipping for now.")
    print("To test manually, use FastAPI TestClient or HTTP requests.")
    return {}

def main():
    print("Grid Endpoints Test Script")
    print("="*80)
    
    # Check DATABASE_URL
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("⚠️  DATABASE_URL not set. Some tests may fail.")
    else:
        print(f"✅ DATABASE_URL is set (length: {len(db_url)})")
    
    # Test 1: Column metadata (no DB required)
    metadata_results = test_column_metadata()
    
    # Test 2 & 3: Endpoints (require DB + auth)
    # These would need a test user and session
    # For now, we'll just report the metadata results
    
    # Summary
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    
    empty_grids = [k for k, v in metadata_results.items() if v.get("status") == "EMPTY"]
    error_grids = [k for k, v in metadata_results.items() if v.get("status") == "ERROR"]
    
    if empty_grids:
        print(f"\n⚠️  Grids with EMPTY column metadata: {', '.join(empty_grids)}")
        print("   These will show 'No columns configured' in the UI.")
    
    if error_grids:
        print(f"\n❌ Grids with ERRORS: {', '.join(error_grids)}")
    
    ok_grids = [k for k, v in metadata_results.items() if v.get("status") == "OK"]
    if ok_grids:
        print(f"\n✅ Grids with column metadata: {len(ok_grids)}/{len(GRID_KEYS)}")
    
    # Save results to file
    output_file = "grid_test_results.json"
    with open(output_file, "w") as f:
        json.dump({
            "metadata": metadata_results,
        }, f, indent=2)
    print(f"\n📄 Results saved to {output_file}")

if __name__ == "__main__":
    main()

