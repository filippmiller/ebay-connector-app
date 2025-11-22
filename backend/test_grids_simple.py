#!/usr/bin/env python3
"""
Simple test for grid column metadata - minimal imports.
"""

import sys
import os

# Minimal test - just check if we can import and call the functions
try:
    # Add to path
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    
    # Import only what we need
    from app.routers.grid_layouts import (
        _columns_meta_for_grid,
        _allowed_columns_for_grid,
        GRID_DEFAULTS,
    )
    
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
    
    print("="*80)
    print("GRID COLUMN METADATA TEST")
    print("="*80)
    
    issues = []
    ok_count = 0
    
    for grid_key in GRID_KEYS:
        try:
            cols_meta = _columns_meta_for_grid(grid_key)
            allowed_cols = _allowed_columns_for_grid(grid_key)
            defaults = GRID_DEFAULTS.get(grid_key, {})
            
            if len(cols_meta) == 0:
                issues.append(f"{grid_key}: NO COLUMNS")
                print(f"❌ {grid_key}: NO COLUMNS")
            else:
                ok_count += 1
                default_visible = len(defaults.get("visible_columns", []))
                print(f"✅ {grid_key}: {len(cols_meta)} cols, {default_visible} default visible")
                
        except Exception as e:
            issues.append(f"{grid_key}: ERROR - {str(e)[:60]}")
            print(f"❌ {grid_key}: ERROR - {e}")
    
    # Test inventory reflection
    print("\n" + "="*80)
    print("INVENTORY REFLECTION TEST")
    print("="*80)
    
    try:
        from app.models_sqlalchemy.models import TblPartsInventory
        
        if TblPartsInventory.__table__ is None:
            print("❌ TblPartsInventory.__table__ is None")
            issues.append("inventory: Table reflection failed")
        else:
            cols = list(TblPartsInventory.__table__.columns)
            if len(cols) == 0:
                print("❌ TblPartsInventory has no columns")
                issues.append("inventory: No columns in reflected table")
            else:
                print(f"✅ TblPartsInventory: {len(cols)} columns reflected")
                ok_count += 1
    except Exception as e:
        print(f"❌ Inventory reflection error: {e}")
        issues.append(f"inventory: Reflection error - {str(e)[:60]}")
    
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print(f"✅ OK: {ok_count}/{len(GRID_KEYS) + 1}")  # +1 for inventory
    if issues:
        print(f"⚠️  Issues: {len(issues)}")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print("✅ All grids have column metadata!")
    
    sys.exit(0 if len(issues) == 0 else 1)
    
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("This script needs to run in Railway environment with all dependencies")
    sys.exit(1)

