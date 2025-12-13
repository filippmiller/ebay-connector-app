# Debugging: Empty Dropdowns in SKU Form

This document contains the source code for the 3 key files involved in fetching and displaying the **Internal Category** and **Shipping Group** dropdowns.

If the dropdowns show **"No categories found (0 rows...)"**, it means either:
1.  The backend is connected to a database that *actually* has 0 rows in `tbl_parts_category`.
2.  The backend query is failing silently (though we added logging to catch this).
3.  The backend is returning data, but the frontend is receiving an empty list.

---

## 1. Backend Router (`backend/app/routers/sq_catalog.py`)

**Role**: This file defines the API endpoint `/api/sq/dictionaries`.
**Key Logic**:
*   Connects to the DB.
*   Runs a debug count query (`_debug_print_categories_and_shipping`) which prints to the server logs.
*   Tries to fetch data from `"tbl_parts_category"` (case-sensitive).
*   If that fails, tries `public."tbl_parts_category"`.
*   **Critical**: It now uses **index-based access** (`row[0]`, `row[1]`) instead of column names to avoid any issues with case sensitivity in column names (e.g. `CategoryID` vs `categoryid`).

```python path=backend/app/routers/sq_catalog.py
async def _debug_print_categories_and_shipping(db):
    try:
        # 1) simply count rows
        count_sql = text('SELECT COUNT(*) AS cnt FROM "tbl_parts_category"')
        count_row = db.execute(count_sql).fetchone()
        logger.info("DEBUG tbl_parts_category COUNT = %s", count_row[0] if count_row else 0)
    except Exception as exc:
        logger.exception("DEBUG ERROR counting tbl_parts_category", exc_info=exc)
    # ... (logging logic continues)

@router.get("/dictionaries")
async def get_sq_dictionaries(db: Session = Depends(get_db), ...):
    # ...
    # ---- INTERNAL CATEGORIES ----
    internal_categories = []
    try:
        # Try querying with explicit "tbl_parts_category" first
        rows = db.execute(
            text(
                'SELECT "CategoryID", "CategoryDescr", "eBayCategoryName" '
                'FROM "tbl_parts_category" ORDER BY "CategoryID"'
            )
        ).fetchall()
    except Exception as exc1:
        # Fallback to public schema
        try:
            rows = db.execute(
                text(
                    'SELECT "CategoryID", "CategoryDescr", "eBayCategoryName" '
                    'FROM public."tbl_parts_category" ORDER BY "CategoryID"'
                )
            ).fetchall()
        except Exception as exc2:
            logger.exception("Failed to load internal categories", exc_info=exc2)
            rows = []

    if rows:
        for row in rows:
            # INDEX-BASED ACCESS (Fix for column name ambiguity)
            cat_id = row[0]
            descr = str(row[1] or "").strip()
            ebay_name = str(row[2] or "").strip()
            
            parts = [str(cat_id)]
            if descr: parts.append(descr)
            if ebay_name: parts.append(ebay_name)
            label = " — ".join(parts)
            
            internal_categories.append({
                "id": cat_id, 
                "code": str(cat_id), 
                "label": label, 
                # ...
            })
    else:
        logger.warning("Internal categories: 0 rows loaded from tbl_parts_category")
    
    # ... (Shipping groups logic follows similar pattern)
    return { "internal_categories": internal_categories, ... }
```

---

## 2. Frontend Component (`frontend/src/components/SkuFormModal.tsx`)

**Role**: Fetches the JSON from the API and renders the dropdown.
**Key Logic**:
*   Uses the `useSqDictionaries` hook (which calls `/api/sq/dictionaries`).
*   Checks if `dictionaries.internal_categories` has items.
*   If it has items, it renders `<SelectItem>`.
*   **If it is empty**, it explicitly renders the "No categories found" message you are seeing.

```tsx path=frontend/src/components/SkuFormModal.tsx
// ... inside the render function ...
{dictionaries?.internal_categories && dictionaries.internal_categories.length > 0 ? (
  dictionaries.internal_categories.map((c) => (
    <SelectItem key={c.id} value={c.code}>
      {c.label}
    </SelectItem>
  ))
) : (
  <SelectItem value="__empty" disabled>
    No categories found (0 rows in tbl_parts_category)
  </SelectItem>
)}
```

---

## 3. Database Connection (`backend/app/models_sqlalchemy/__init__.py`)

**Role**: Establishes the connection to Postgres/Supabase.
**Key Logic**:
*   Reads `DATABASE_URL` from environment variables.
*   Forces `sslmode=require` (critical for Supabase).
*   Creates the SQLAlchemy engine.

If this file is misconfigured (e.g. connecting to a dev DB vs prod DB), the backend will query the wrong place.

```python path=backend/app/models_sqlalchemy/__init__.py
# ...
if "postgresql" in DATABASE_URL or "postgres" in DATABASE_URL:
    # ... logic to add sslmode=require ...
    
engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    echo=True,  # SQL logging enabled
    # ...
)
```
