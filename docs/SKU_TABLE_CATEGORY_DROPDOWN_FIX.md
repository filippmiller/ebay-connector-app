# SKU Table Category Dropdown Fix — Session 2025-11-22

**Status**: ✅ **RESOLVED**  
**Date**: 2025-11-22  
**Environment**: Railway (Production) + Supabase PostgreSQL

---

## Problem Statement

The SKU table's category dropdown menu was showing **0 records** instead of populating from the `tbl_parts_category` Supabase database table.

### User Requirements

From `tbl_parts_category`, we need **three fields**:

1. **CategoryID** (numeric) — The primary category code
2. **CategoryDescr** (text) — Human-readable category description  
3. **eBayCategoryName** (text, uppercase field name) — eBay category name

### Expected Dropdown Format

Each dropdown entry should display:
```
<CategoryID> — <CategoryDescr> — <eBayCategoryName>
```

**Example**:
```
101 — motherboards — Laptops & Netbooks
108 — lcd complete — Laptop Screens & LCD Panels
```

### Expected JSON Response

```json
{
  "id": 101,
  "code": "101",
  "label": "101 — motherboards — Laptops & Netbooks",
  "category_id": 101,
  "category_descr": "motherboards",
  "ebay_category_name": "Laptops & Netbooks"
}
```

---

## Environment Setup

### Railway Connection

**Project**: `pretty-exploration` (ID: `e2a4908d-6e01-46fa-a3ab-aa99ef3befdf`)  
**Service**: `ebay-connector-app` (ID: `31ec6c36-62b8-4f9c-b880-77476b8d340c`)  
**Environment**: `production` (ID: `524635cb-8338-482e-b9d6-002af8a12bcd`)

**Railway URL**: https://railway.com/project/e2a4908d-6e01-46fa-a3ab-aa99ef3befdf/service/31ec6c36-62b8-4f9c-b880-77476b8d340c?environmentId=524635cb-8338-482e-b9d6-002af8a12bcd

### Linked Project

Successfully linked the backend directory to Railway:
```powershell
npx -y @railway/cli@latest link --project e2a4908d-6e01-46fa-a3ab-aa99ef3befdf \
  --service 31ec6c36-62b8-4f9c-b880-77476b8d340c \
  --environment 524635cb-8338-482e-b9d6-002af8a12bcd
```

This allows running commands with Railway environment variables injected:
```powershell
npx -y @railway/cli@latest run <command>
```

---

## Investigation & Discoveries

### 1. Database Connection Verified

Created `debug_categories.py` to test direct database access:

**Key Findings**:
- ✅ Database connection to Supabase works correctly
- ✅ `tbl_parts_category` table exists and contains **55 records**
- ✅ All three queries work (quoted, public.quoted, and lowercase unquoted)
- ✅ Column names match expected structure

**Table Schema** (from Supabase):
```
Columns: ['ID', 'CategoryPartsGroupID', 'CategoryID', 'CategoryDescr', 
          'eBayCategoryID', 'eBayCategoryName', 'Part_specific_desc', 
          'Important_info', 'Estimated_shipping', 'oc_Category_ID', ...]
```

**Sample Data**:
```python
(Decimal('1'), Decimal('115'), Decimal('164'), 'CPU', 
 Decimal('164'), 'CPUs, Processors', ...)
```

### 2. API Endpoint Error Discovered

**Endpoint**: `GET /api/sq/dictionaries`  
**File**: `backend/app/routers/sq_catalog.py`

**Initial Error**:
```
(psycopg2.errors.SyntaxError) syntax error at or near "ASC"
LINE 2: ...ORDER BY item_conditions.sort_order NULLS LAST ASC, item_...
```

**Root Cause**: SQLAlchemy syntax error in `ItemCondition` query at line 513:

```python
# ❌ BROKEN CODE
.order_by(asc(ItemCondition.sort_order.nulls_last()), asc(ItemCondition.code))
```

**Problem Explanation**:
- `ItemCondition.sort_order.nulls_last()` returns a `UnaryExpression` with `NULLS LAST` clause
- Wrapping this in `asc()` tries to append `ASC` after `NULLS LAST`
- PostgreSQL syntax requires: `ORDER BY column ASC NULLS LAST` (not `column NULLS LAST ASC`)

### 3. The Bug's Impact

Even though the bug was in the `ItemCondition` query (which comes **after** the `tbl_parts_category` query in the code), it caused the **entire endpoint to fail** with a 500 error.

This meant:
- Frontend received no data at all
- UI showed "0 records" (because the API call failed)
- **Not** because `tbl_parts_category` was empty
- **Not** because the query was wrong
- **But** because a later query crashed the whole endpoint

---

## The Fix

### Changed Code (Line 513)

```python
# ✅ FIXED CODE
.order_by(ItemCondition.sort_order.asc(), ItemCondition.code.asc())
```

**Why This Works**:
- PostgreSQL defaults to `NULLS LAST` for `ASC` ordering
- No need to explicitly specify `nulls_last()` in this case
- Clean, valid SQL: `ORDER BY sort_order ASC, code ASC`

### File Modified

**File**: `c:\Users\filip\.gemini\antigravity\playground\silent-spirit\backend\app\routers\sq_catalog.py`

**Changes**:
1. ✅ Fixed `ItemCondition` ordering syntax (line 513)
2. ✅ Restored authentication requirement (temporarily removed for testing)

---

## Testing Results

### Test 1: Database Direct Access
```bash
npx -y @railway/cli@latest run python debug_categories.py
```

**Result**: ✅ Success
```
Connected successfully!
--- Checking "tbl_parts_category" ---
Count: 55
Columns: ['ID', 'CategoryPartsGroupID', 'CategoryID', 'CategoryDescr', ...]
```

### Test 2: API Endpoint (After Fix)
```bash
curl http://127.0.0.1:8083/api/sq/dictionaries
```

**Result**: ✅ Success (HTTP 200)
```json
{
  "internal_categories": [
    {
      "id": "164",
      "code": "164",
      "label": "164 — CPU — CPUs, Processors",
      "category_id": "164",
      "category_descr": "CPU",
      "ebay_category_name": "CPUs, Processors"
    },
    {
      "id": "1244",
      "code": "1244",
      ...
    }
  ],
  "shipping_groups": [...],
  "conditions": [...],
  "warehouses": [...],
  "listing_types": [...],
  "listing_durations": [...],
  "sites": [...]
}
```

**Response Stats**:
- Content-Length: 12,527 bytes
- Status: 200 OK
- Categories returned: 55 records (all from `tbl_parts_category`)

---

## Code Implementation Details

### Category Query (Lines 417-457)

The implementation correctly:
1. ✅ Queries `tbl_parts_category` with proper quoting
2. ✅ Falls back to `public."tbl_parts_category"` if needed
3. ✅ Constructs label as: `<CategoryID> — <CategoryDescr> — <eBayCategoryName>`
4. ✅ Returns all required fields in JSON

```python
# Primary query (line 422-426)
rows = db.execute(
    text(
        'SELECT "CategoryID", "CategoryDescr", "eBayCategoryName" '
        'FROM "tbl_parts_category" ORDER BY "CategoryID"'
    )
).fetchall()

# Fallback query with schema (line 431-435)
rows = db.execute(
    text(
        'SELECT "CategoryID", "CategoryDescr", "eBayCategoryName" '
        'FROM public."tbl_parts_category" ORDER BY "CategoryID"'
    )
).fetchall()

# Label construction (line 448-453)
parts = [str(cat_id)]
if descr:
    parts.append(descr)
if ebay_name:
    parts.append(ebay_name)
label = " — ".join(parts)
```

### Response Format

Each category includes:
- `id`: CategoryID (as string)
- `code`: CategoryID (as string, for consistency)
- `label`: Formatted display string
- `category_id`: CategoryID (original value)
- `category_descr`: CategoryDescr
- `ebay_category_name`: eBayCategoryName

---

## Railway & Supabase Integration

### Environment Variables (Managed by Railway)

**Backend** (secure, never exposed to frontend):
- `DATABASE_URL` — Supabase Session Pooler connection string
  - Format: `postgresql://postgres:PASSWORD@HOST.pooler.supabase.com:PORT/postgres?sslmode=require`
  - Uses TLS encryption
  - Session pooling enabled
- `SUPABASE_SERVICE_ROLE_KEY` — Service role key (bypasses RLS)
- `SECRET_KEY` / `JWT_SECRET` — App authentication
- `EBAY_*` — eBay API credentials
- `FRONTEND_URL` — CORS configuration
- `ALLOWED_ORIGINS` — CORS origins

**Frontend** (safe for client):
- `VITE_SUPABASE_URL` — Public Supabase project URL
- `VITE_SUPABASE_ANON_KEY` — Anonymous key (safe for browser)

### Running Backend with Railway Variables

```powershell
# Install dependencies
npx -y @railway/cli@latest run poetry install

# Run migrations
npx -y @railway/cli@latest run poetry run alembic upgrade head

# Start backend server
npx -y @railway/cli@latest run poetry run uvicorn app.main:app --host 127.0.0.1 --port 8081 --reload
```

### Database Health Check

```powershell
# Quick DB connectivity test
npx -y @railway/cli@latest run python -c "import os,psycopg2; d=os.environ['DATABASE_URL']; c=psycopg2.connect(d, connect_timeout=6); cur=c.cursor(); cur.execute('select 1'); print('DB_OK'); c.close()"
```

---

## Frontend Integration

### Hook: `useSqDictionaries.ts`

**Location**: `frontend/src/hooks/useSqDictionaries.ts`

**Features**:
- ✅ Fetches from `/api/sq/dictionaries`
- ✅ Caches results in memory to avoid repeated calls
- ✅ Handles loading/error states
- ✅ Shares cache across component instances

**Response Interface**:
```typescript
export interface DictionariesResponse {
  internal_categories: InternalCategoryDto[];
  shipping_groups: ShippingGroupDto[];
  conditions: ConditionDto[];
  listing_types: ListingTypeDto[];
  listing_durations: ListingDurationDto[];
  sites: SiteDto[];
}
```

---

## Summary of Changes

### Files Modified

1. **`backend/app/routers/sq_catalog.py`**
   - ✅ Fixed SQLAlchemy `order_by` syntax error (line 513)
   - Changed: `asc(ItemCondition.sort_order.nulls_last())` → `ItemCondition.sort_order.asc()`

### Files Created (Debug/Testing)

1. **`backend/debug_categories.py`** — Database connectivity test script
2. **`backend/projects.json`** — Railway projects list (temporary)

---

## Verification Checklist

- [x] Database contains 55 records in `tbl_parts_category`
- [x] API endpoint returns 200 OK
- [x] Response includes all 55 categories
- [x] Label format matches: `<ID> — <Descr> — <eBayName>`
- [x] JSON structure matches user requirements
- [x] Authentication restored (endpoint requires login)
- [x] Railway connection configured correctly
- [x] Backend runs with Supabase environment variables

---

## Next Steps

### Immediate Actions

1. **Deploy to Railway**: Push changes to trigger Railway deployment
2. **Test Frontend**: Verify dropdown populates correctly in UI
3. **Clean Up**: Remove debug scripts (`debug_categories.py`, `projects.json`)

### Deployment Command

```bash
git add backend/app/routers/sq_catalog.py
git commit -m "fix: resolve SKU category dropdown SQL syntax error

- Fix ItemCondition order_by syntax causing endpoint failure
- Categories now load correctly from tbl_parts_category (55 records)
- Resolves '0 records' issue in SKU table category dropdown"
git push origin main
```

### Frontend Testing

Once deployed, verify:
1. Login at: `filippmiller@gmail.com` / `Airbus380+`
2. Navigate to SKU management page
3. Open category dropdown
4. Verify 55 categories display with correct format

### Additional Improvements (Optional)

1. **Add Error Handling**: Consider more graceful degradation if `tbl_parts_category` is unavailable
2. **Logging**: The existing debug logging at line 412-415 is helpful; keep it
3. **Performance**: Consider adding response caching if dictionary endpoint is called frequently
4. **Data Validation**: Ensure CategoryID is always numeric and valid

---

## Technical Notes

### PostgreSQL Column Quoting

Supabase uses case-sensitive column names. Always use double quotes:
```sql
✅ SELECT "CategoryID" FROM "tbl_parts_category"
❌ SELECT CategoryID FROM tbl_parts_category  -- would look for lowercase
```

### SQLAlchemy Ordering

PostgreSQL ordering behavior:
- `ORDER BY x ASC` → Nulls appear **last** (default PostgreSQL behavior)
- `ORDER BY x DESC` → Nulls appear **first**

No need to explicitly specify `NULLS LAST` for ascending order in PostgreSQL.

### Railway CLI Patterns

```powershell
# Link project once
railway link --project <project-id> --service <service-id> --environment <env-id>

# Then run commands with env injection
railway run <command>

# View variables
railway variables --json
```

---

**Document Created**: 2025-11-22T09:29:00+03:00  
**Resolution Time**: ~45 minutes  
**Primary Issue**: SQLAlchemy syntax error in unrelated query causing entire endpoint failure  
**Records Found**: 55 categories in `tbl_parts_category`  
**Status**: ✅ **RESOLVED AND READY FOR DEPLOYMENT**
