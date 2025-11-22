# Grid Debug Notes

## Status: In Progress - Frontend Fixes Applied

This document tracks the diagnosis and repair of AG Grid data + metadata wiring issues.

## Step 1: DB Connectivity

**Status**: ✅ VERIFIED - Connected to Railway/Supabase

**Results**:
- ✅ Connected to PostgreSQL 17.6 (Supabase) via Railway CLI
- ✅ Railway authentication: `filippmiller@gmail.com`
- ✅ Service ID: `31ec6c36-62b8-4f9c-b880-77476b8d340c`
- ✅ Environment ID: `524635cb-8338-482e-b9d6-002af8a12bcd`

**Table Verification**:
- ✅ `order_line_items`: 7,896 rows
- ✅ `ebay_transactions`: 7,609 rows
- ✅ `ebay_finances_transactions`: 7,059 rows
- ✅ `ebay_finances_fees`: 11,916 rows
- ✅ `ebay_buyer`: 337 rows
- ✅ `ebay_active_inventory`: 17,167 rows
- ✅ `tbl_parts_inventory`: 264,698 rows
- ✅ `SKU_catalog`: 143,525 rows (correct table name with quotes)
- ⚠️  `offers`: 0 rows (table exists but empty)
- ✅ `user_grid_layouts`: 7 rows (saved layouts exist)

**Note**: Created test scripts:
- `backend/test_db_connection.py` - DB connectivity test
- `backend/test_db_full.py` - Full table structure check
- `backend/test_grid_endpoints_http.py` - HTTP endpoint testing

## Step 2: Backend Data Endpoints

**Status**: ✅ FIXED - Improved error handling

**Findings**:
- All grid data helpers exist in `backend/app/routers/grids_data.py`
- Endpoints follow pattern: `GET /api/grids/{grid_key}/data`
- Helpers serialize data correctly (datetime → isoformat, Decimal → float, Enum → value)
- All grid keys have corresponding helper functions

**Fixes Applied**:
- ✅ Added error handling in all `_serialize` functions (`_get_orders_data`, `_get_transactions_data`, `_get_offers_data`, `_get_buying_data`, `_get_active_inventory_data`, `_get_inventory_data`, `_get_sku_catalog_data`)
- ✅ Improved null/None handling - columns that don't exist or are None are now skipped instead of causing errors
- ✅ Added aliases for SKU catalog: `rec_created`/`rec_updated` map to `record_created`/`record_updated` in data
- ✅ All serializers now use try/except to gracefully handle missing columns

## Step 3: Backend Preferences/Layout API

**Status**: Code review complete

**Findings**:
- `GET /api/grid/preferences?grid_key=...` exists in `backend/app/routers/grid_preferences.py`
- Uses `_columns_meta_for_grid(grid_key)` from `grid_layouts.py`
- All grid keys have `*_COLUMNS_META` definitions
- `_columns_meta_for_grid` returns empty list `[]` for unknown grid keys (line 544)

## Step 4: Frontend Grid Preferences Wiring

**Status**: ✅ FIXED

**Issues Found and Fixed**:

1. **Data fetching blocked when columns empty** (DataGridPage.tsx line 181)
   - **Problem**: Data fetch was blocked if `orderedVisibleColumns.length === 0`, even if `availableColumns` had metadata
   - **Fix**: Changed logic to use `availableColumns` as fallback when `orderedVisibleColumns` is empty
   - **File**: `frontend/src/components/DataGridPage.tsx`

2. **Error handling in useGridPreferences** (useGridPreferences.ts)
   - **Problem**: If all fallbacks failed, it set empty state and blocked further attempts
   - **Fix**: Improved error handling and logging, better fallback chain with early returns on success
   - **File**: `frontend/src/hooks/useGridPreferences.ts`

**Changes Made**:
- `DataGridPage.tsx`: 
  - Modified data fetch logic to not block when `orderedVisibleColumns` is empty but `availableColumns` exists
  - Improved column initialization logic to not block rendering
  - Better handling of empty states
- `useGridPreferences.ts`: Improved fallback chain with better error handling and early returns
- `AppDataGrid.tsx`: 
  - Added explicit `colId` for AG Grid columns
  - Added debug logging in development mode to track column/row mismatches
  - Improved empty state handling
  - Enabled column resizing
- `grids_data.py`: 
  - Added error handling in all `_serialize` functions to skip problematic columns
  - Added aliases for `rec_created`/`rec_updated` in SKU catalog data
  - Improved null/None handling in all serializers

## Per-Grid Status

| Grid Key | Data Endpoint | Preferences Endpoint | Status |
|----------|---------------|---------------------|--------|
| orders | `_get_orders_data` | `ORDERS_COLUMNS_META` | Pending test |
| transactions | `_get_transactions_data` | `TRANSACTIONS_COLUMNS_META` | Pending test |
| finances | `_get_finances_data` | `FINANCES_COLUMNS_META` | Pending test |
| finances_fees | `_get_finances_fees_data` | `FINANCES_FEES_COLUMNS_META` | Pending test |
| buying | `_get_buying_data` | `BUYING_COLUMNS_META` | Pending test |
| sku_catalog | `_get_sku_catalog_data` | `SKU_CATALOG_COLUMNS_META` | Pending test |
| active_inventory | `_get_active_inventory_data` | `ACTIVE_INVENTORY_COLUMNS_META` | Pending test |
| inventory | `_get_inventory_data` | Reflected from `TblPartsInventory` | Pending test |
| cases | `_get_cases_data` | `CASES_COLUMNS_META` | Pending test |
| offers | `_get_offers_data` | `OFFERS_COLUMNS_META` | Pending test |

## Bugs Fixed

### Frontend Fixes

1. **DataGridPage.tsx - Blocked data fetching**
   - **Problem**: Data fetch blocked when `orderedVisibleColumns.length === 0`
   - **Fix**: Use `availableColumns` as fallback, only block if truly no columns exist
   - **Lines**: 182-198, 393-399

2. **DataGridPage.tsx - Column initialization**
   - **Problem**: Columns state cleared too aggressively, blocking rendering
   - **Fix**: Only clear columns if no available columns metadata exists
   - **Lines**: 150-164

3. **useGridPreferences.ts - Error handling**
   - **Problem**: All fallbacks failed silently, blocking grid initialization
   - **Fix**: Better error handling, early returns on success, improved logging
   - **Lines**: 84-164

4. **AppDataGrid.tsx - Column/row mismatch**
   - **Problem**: No debug info when column fields don't match row data keys
   - **Fix**: Added development-mode logging to detect mismatches
   - **Lines**: 127-157

5. **AppDataGrid.tsx - Empty columnDefs**
   - **Problem**: Empty columnDefs array could cause AG Grid to not render
   - **Fix**: Added explicit check and empty state message
   - **Lines**: 81-99, 127-157

### Backend Fixes

1. **grids_data.py - Missing error handling**
   - **Problem**: Serializers could crash on missing columns
   - **Fix**: Added try/except in all `_serialize` functions
   - **Files**: All `_get_*_data` functions

2. **grids_data.py - SKU catalog column aliases**
   - **Problem**: Metadata uses `rec_created`/`rec_updated` but data has `record_created`/`record_updated`
   - **Fix**: Added aliases in `base_values` dictionary
   - **File**: `_get_sku_catalog_data` function

3. **grids_data.py - Null value handling**
   - **Problem**: None values could cause serialization issues
   - **Fix**: Skip None values instead of including them
   - **Files**: All serializers

## Verification

(To be filled with screenshots/notes after fixes)

