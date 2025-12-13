#!/usr/bin/env python3
"""
Test all grid endpoints to verify they return data and column metadata.

This script tests:
1. Column metadata for each grid (via _columns_meta_for_grid)
2. Data endpoints (simulated - would need auth)
3. Preferences endpoints (simulated - would need auth)
"""

import os
import sys

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.routers.grid_layouts import _columns_meta_for_grid, _allowed_columns_for_grid, GRID_DEFAULTS

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
    """Test that all grids have column metadata."""
    print("="*80)
    print("TESTING COLUMN METADATA FOR ALL GRIDS")
    print("="*80)
    
    results = {}
    issues = []
    
    for grid_key in GRID_KEYS:
        try:
            cols_meta = _columns_meta_for_grid(grid_key)
            allowed_cols = _allowed_columns_for_grid(grid_key)
            defaults = GRID_DEFAULTS.get(grid_key, {})
            
            status = "OK" if len(cols_meta) > 0 else "EMPTY"
            
            results[grid_key] = {
                "status": status,
                "column_count": len(cols_meta),
                "allowed_columns_count": len(allowed_cols),
                "has_defaults": bool(defaults),
                "default_visible_count": len(defaults.get("visible_columns", [])),
            }
            
            if len(cols_meta) == 0:
                issues.append(f"{grid_key}: NO COLUMNS")
                print(f"❌ {grid_key}: NO COLUMNS (will show 'No columns configured')")
            elif len(cols_meta) < 5:
                issues.append(f"{grid_key}: Only {len(cols_meta)} columns")
                print(f"⚠️  {grid_key}: Only {len(cols_meta)} columns")
            else:
                print(f"✅ {grid_key}: {len(cols_meta)} columns, {len(defaults.get('visible_columns', []))} default visible")
                
        except Exception as e:
            results[grid_key] = {
                "status": "ERROR",
                "error": str(e),
            }
            issues.append(f"{grid_key}: ERROR - {e}")
            print(f"❌ {grid_key}: ERROR - {e}")
    
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    
    ok_count = sum(1 for r in results.values() if r.get("status") == "OK")
    empty_count = sum(1 for r in results.values() if r.get("status") == "EMPTY")
    error_count = sum(1 for r in results.values() if r.get("status") == "ERROR")
    
    print(f"✅ OK: {ok_count}/{len(GRID_KEYS)}")
    if empty_count > 0:
        print(f"⚠️  EMPTY: {empty_count}/{len(GRID_KEYS)}")
    if error_count > 0:
        print(f"❌ ERRORS: {error_count}/{len(GRID_KEYS)}")
    
    if issues:
        print("\nIssues found:")
        for issue in issues:
            print(f"  - {issue}")
    
    return results

def test_inventory_reflection():
    """Test inventory table reflection specifically."""
    print("\n" + "="*80)
    print("TESTING INVENTORY TABLE REFLECTION")
    print("="*80)
    
    try:
        from app.models_sqlalchemy.models import TblPartsInventory
        
        if TblPartsInventory.__table__ is None:
            print("❌ TblPartsInventory.__table__ is None - reflection failed")
            return False
        
        cols = list(TblPartsInventory.__table__.columns)
        if len(cols) == 0:
            print("❌ TblPartsInventory has no columns")
            return False
        
        print(f"✅ TblPartsInventory reflected: {len(cols)} columns")
        print(f"   First 5 columns: {[c.key for c in cols[:5]]}")
        return True
        
    except Exception as e:
        print(f"❌ Inventory reflection error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("Grid Endpoints Test - Column Metadata Check")
    print("="*80)
    
    # Test 1: Column metadata
    metadata_results = test_column_metadata()
    
    # Test 2: Inventory reflection
    inventory_ok = test_inventory_reflection()
    
    # Final status
    print("\n" + "="*80)
    print("FINAL STATUS")
    print("="*80)
    
    all_ok = all(r.get("status") == "OK" for r in metadata_results.values()) and inventory_ok
    
    if all_ok:
        print("✅ All grids have column metadata!")
    else:
        print("⚠️  Some grids need attention (see issues above)")
    
    sys.exit(0 if all_ok else 1)

