# Shipping Groups Dropdown Fix — Session 2025-11-22

**Status**: ✅ **RESOLVED**  
**Date**: 2025-11-22  
**Related Issue**: Duplicate records in shipping groups dropdown

---

## Problem Statement

The SKU form's **shipping groups dropdown** was showing **duplicate records** instead of unique entries. Each shipping group appeared **twice** in the dropdown.

### User Requirements

From `tbl_internalshippinggroups`, we need:
1. **ID** (numeric) — Shipping group ID
2. **Name** (text) — Shipping group name
3. **Active** (boolean) — Only show active groups

### Expected Dropdown Format

Each dropdown entry should display:
```
<ID>: <Name>
```

**Example**:
```
1: 1group<80
2: 2group<80
4: no international
5: LCD Complete
6: BIG items
```

### Expected JSON Response

```json
{
  "id": 1,
  "code": "1",
  "name": "1group<80",
  "label": "1: 1group<80",
  "active": true
}
```

---

## Root Cause

**Database Issue**: The `tbl_internalshippinggroups` table contains **duplicate rows**:
- Total records: 12
- Unique records: 6
- Each record appears exactly **twice**
- **No primary key** defined on the table

### Evidence

From `check_duplicates.py`:
```
Found duplicates:
  ID=5, Name=LCD Complete, Count=2
  ID=3, Name=3group<80, Count=2
  ID=4, Name=no international, Count=2
  ID=1, Name=1group<80, Count=2
  ID=6, Name=BIG items, Count=2
  ID=2, Name=2group<80, Count=2

No primary key found!

DISTINCT records:
  ID=1, Name=1group<80, Active=True
  ID=2, Name=2group<80, Active=True
  ID=3, Name=3group<80, Active=True
  ID=4, Name=no international, Active=True
  ID=5, Name=LCD Complete, Active=True
  ID=6, Name=BIG items, Active=True
```

---

## The Fix

**Solution**: Add `DISTINCT` keyword to the SQL query to filter out duplicate rows.

### Code Changes

**File**: `backend/app/routers/sq_catalog.py`

**Lines 469-476** (Primary query):
```python
# BEFORE (returned duplicates)
rows = db.execute(
    text(
        'SELECT "ID", "Name", "Active" '
        'FROM "tbl_internalshippinggroups" '
        'WHERE "Active" = true '
        'ORDER BY "ID"'
    )
).fetchall()

# AFTER (returns unique records)
rows = db.execute(
    text(
        'SELECT DISTINCT "ID", "Name", "Active" '
        'FROM "tbl_internalshippinggroups" '
        'WHERE "Active" = true '
        'ORDER BY "ID"'
    )
).fetchall()
```

**Lines 480-487** (Fallback query):
```python
# BEFORE
rows = db.execute(
    text(
        'SELECT "ID", "Name", "Active" '
        'FROM public."tbl_internalshippinggroups" '
        'WHERE "Active" = true '
        'ORDER BY "ID"'
    )
).fetchall()

# AFTER
rows = db.execute(
    text(
        'SELECT DISTINCT "ID", "Name", "Active" '
        'FROM public."tbl_internalshippinggroups" '
        'WHERE "Active" = true '
        'ORDER BY "ID"'
    )
).fetchall()
```

---

## Results

### Before Fix
- **API returned**: 12 shipping groups (with duplicates)
- **User sees**: Each group listed twice
- **Example**: "1: 1group<80" appeared twice

### After Fix
- **API returns**: 6 unique shipping groups
- **User sees**: Each group listed once
- **Clean dropdown** with no duplicates

### Test Results

From `debug_shipping.py`:
```
Connected successfully!

--- Checking "tbl_internalshippinggroups" ---
Total count: 12
Active records (Active=true): 12

All records:
  ID=1, Name=1group<80, Active=True
  ID=1, Name=1group<80, Active=True  ← Duplicate
  ID=2, Name=2group<80, Active=True
  ID=2, Name=2group<80, Active=True  ← Duplicate
  ...
```

With `DISTINCT`, API returns:
```json
[
  {"id": "1", "code": "1", "name": "1group<80", "label": "1: 1group<80", "active": true},
  {"id": "2", "code": "2", "name": "2group<80", "label": "2: 2group<80", "active": true},
  {"id": "3", "code": "3", "name": "3group<80", "label": "3: 3group<80", "active": true},
  {"id": "4", "code": "4", "name": "no international", "label": "4: no international", "active": true},
  {"id": "5", "code": "5", "name": "LCD Complete", "label": "5: LCD Complete", "active": true},
  {"id": "6", "code": "6", "name": "BIG items", "label": "6: BIG items", "active": true}
]
```

---

## Additional Fixes in Same Commit

Along with the shipping groups fix, also resolved:
1. **ItemCondition sort order** SQL syntax error (same as categories fix)
   - Changed: `asc(ItemCondition.sort_order.nulls_last())` → `ItemCondition.sort_order.asc()`

---

## Recommended Database Cleanup (Optional)

While the `DISTINCT` query fixes the API response, the underlying database still contains duplicates. Consider:

### Option 1: Add Primary Key (Recommended)
```sql
-- Remove duplicates first
DELETE FROM tbl_internalshippinggroups a
USING tbl_internalshippinggroups b
WHERE a."ID" = b."ID"
  AND a.ctid < b.ctid;

-- Then add primary key
ALTER TABLE tbl_internalshippinggroups 
ADD PRIMARY KEY ("ID");
```

### Option 2: Keep DISTINCT (Current Solution)
- ✅ Works immediately
- ✅ No database schema changes
- ✅ Safe for production
- ⚠️ Underlying duplicates remain

---

## Files Modified

1. **`backend/app/routers/sq_catalog.py`**
   - Added `DISTINCT` to shipping groups queries (lines 471, 482)
   - Fixed `ItemCondition` ordering syntax (line 513)

## Files Created (Debug/Testing)

1. **`backend/debug_shipping.py`** — Shipping groups connectivity test
2. **`backend/check_duplicates.py`** — Duplicate detection script
3. **`backend/test_shipping_api.py`** — API response test
4. **`backend/test_shipping_fixed.py`** — Fixed API test

---

## Summary

**Problem**: Shipping groups dropdown showed duplicates  
**Root Cause**: Database table contains duplicate rows + no primary key  
**Fix**: Added `DISTINCT` to SQL queries  
**Result**: ✅ API now returns 6 unique shipping groups instead of 12 duplicates

---

**Document Created**: 2025-11-22T09:48:00+03:00  
**Resolution**: ✅ **COMPLETE**  
**Deployment**: Ready (same fix as categories)
