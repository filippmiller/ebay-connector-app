# Audit: Wiring of Internal Category and Shipping Groups

## Overview
This document contains the exact code currently deployed to wire the **Internal Category** and **Shipping Group** dropdowns in the Create SKU form.

The implementation uses explicit SQL queries (not ORM reflection) to access:
1.  `tbl_parts_category` for Internal Categories.
2.  `tbl_internalshippinggroups` for Shipping Groups.

## Backend Code (`backend/app/routers/sq_catalog.py`)

### Debug Logging Function
This function runs before the data loading to output the current state of the tables to the logs. It verifies connectivity and row counts.

```python path=backend/app/routers/sq_catalog.py start=363
async def _debug_print_categories_and_shipping(db):
    try:
        # 1) simply count rows
        count_sql = text('SELECT COUNT(*) AS cnt FROM "tbl_parts_category"')
        count_row = db.execute(count_sql).fetchone()
        logger.info("DEBUG tbl_parts_category COUNT = %s", count_row[0] if count_row else 0)
    except Exception as exc:
        logger.exception("DEBUG ERROR counting tbl_parts_category", exc_info=exc)

    try:
        # 2) show first 3 rows
        sample_sql = text('''
            SELECT "CategoryID", "CategoryDescr", "eBayCategoryName"
            FROM "tbl_parts_category"
            ORDER BY "CategoryID"
            LIMIT 3
        ''')
        rows = db.execute(sample_sql).fetchall()
        logger.info("DEBUG tbl_parts_category SAMPLE = %s", rows)
    except Exception as exc:
        logger.exception("DEBUG ERROR sampling tbl_parts_category", exc_info=exc)

    try:
        # SHIPPING GROUPS
        count_sql2 = text('SELECT COUNT(*) AS cnt FROM "tbl_internalshippinggroups"')
        count_row2 = db.execute(count_sql2).fetchone()
        logger.info("DEBUG tbl_internalshippinggroups COUNT = %s", count_row2[0] if count_row2 else 0)

        sample_sql2 = text('''
            SELECT "ID", "Name", "Active"
            FROM "tbl_internalshippinggroups"
            ORDER BY "ID"
            LIMIT 6
        ''')
        rows2 = db.execute(sample_sql2).fetchall()
        logger.info("DEBUG tbl_internalshippinggroups SAMPLE = %s", rows2)
    except Exception as exc:
        logger.exception("DEBUG ERROR sampling tbl_internalshippinggroups", exc_info=exc)
```

### Dictionaries Endpoint
This endpoint (`GET /api/sq/dictionaries`) performs the actual data loading.
**Key Logic:**
1.  Tries to select from `"tbl_parts_category"`.
2.  If that fails (e.g., table not found), falls back to `public."tbl_parts_category"`.
3.  If both fail, logs the full exception and returns an empty list.
4.  Uses strict column casing (`"eBayCategoryName"`, `"CategoryDescr"`) to match the legacy schema.

```python path=backend/app/routers/sq_catalog.py start=406
async def get_sq_dictionaries(
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> dict:
    """Return dictionaries used by the SQ Create/Edit form."""
    
    # Check DB connection details
    from app.models_sqlalchemy import engine
    logger.info("SQ dictionaries DB URL host=%s db=%s", engine.url.host, engine.url.database)
    
    # Run debug queries
    await _debug_print_categories_and_shipping(db)

    # ---- INTERNAL CATEGORIES ----
    internal_categories = []
    try:
        # Try querying with explicit "tbl_parts_category" first (no schema).
        # Use correct casing and aliases for label construction.
        rows = db.execute(
            text(
                'SELECT "CategoryID" as id, "CategoryDescr" as descr, "eBayCategoryName" as ebay_name '
                'FROM "tbl_parts_category" ORDER BY "CategoryID"'
            )
        ).fetchall()
    except Exception as exc1:
        # Fallback: try public."tbl_parts_category" explicitly if previous failed
        try:
            rows = db.execute(
                text(
                    'SELECT "CategoryID" as id, "CategoryDescr" as descr, "eBayCategoryName" as ebay_name '
                    'FROM public."tbl_parts_category" ORDER BY "CategoryID"'
                )
            ).fetchall()
        except Exception as exc2:
            logger.exception("Failed to load internal categories from tbl_parts_category", exc_info=exc2)
            rows = []

    if rows:
        for row in rows:
            # Use indices or attribute access depending on driver; row mappings support key access.
            cat_id = row.id
            descr = str(row.descr or "").strip()
            ebay_name = str(row.ebay_name or "").strip()
            
            parts = [str(cat_id)]
            if descr:
                parts.append(descr)
            if ebay_name:
                parts.append(ebay_name)
            label = " — ".join(parts)
            
            internal_categories.append(
                {"id": cat_id, "code": str(cat_id), "label": label, "category_id": cat_id, "category_descr": descr, "ebay_category_name": ebay_name}
            )
    else:
        # AUDIT 2025-11-21:
        # Internal categories are loaded from tbl_parts_category (NOT from sq_internal_categories).
        # If the query returns 0 rows, we log a warning and return an empty list to the UI.
        logger.warning("Internal categories: 0 rows loaded from tbl_parts_category")

    # ---- SHIPPING GROUPS ----
    shipping_groups = []
    try:
        # ID, Name, Description, Active
        # Try without schema first
        rows = db.execute(
            text(
                'SELECT "ID" as id, \"Name\" as name, \"Active\" as active '
                'FROM "tbl_internalshippinggroups" '
                'WHERE "Active" = true '
                'ORDER BY "ID"'
            )
        ).fetchall()
    except Exception:
        try:
            # Fallback to public schema
            rows = db.execute(
                text(
                    'SELECT "ID" as id, \"Name\" as name, \"Active\" as active '
                    'FROM public."tbl_internalshippinggroups" '
                    'WHERE "Active" = true '
                    'ORDER BY "ID"'
                )
            ).fetchall()
        except Exception as exc:
            logger.exception("Failed to load shipping groups from tbl_internalshippinggroups", exc_info=exc)
            rows = []

    if rows:
        for row in rows:
            s_id = row.id
            s_name = str(row.name or "").strip()
            s_active = row.active
            label = f"{s_id}: {s_name}"
            shipping_groups.append({
                "id": s_id,
                "code": str(s_id),
                "name": s_name,
                "label": label,
                "active": s_active
            })
    else:
        # AUDIT 2025-11-21:
        # Shipping groups are loaded from tbl_internalshippinggroups.
        logger.warning("Shipping groups: 0 rows loaded from tbl_internalshippinggroups")
    
    # ... (rest of the function)
```

## Frontend Code (`frontend/src/components/SkuFormModal.tsx`)

The frontend receives the JSON response and renders it.
If the list is empty, it explicitly renders a disabled item saying "No categories found".

```tsx path=frontend/src/components/SkuFormModal.tsx start=667
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

```tsx path=frontend/src/components/SkuFormModal.tsx start=759
{dictionaries?.shipping_groups && dictionaries.shipping_groups.length > 0 ? (
    dictionaries.shipping_groups.map((g) => (
    <SelectItem key={g.id} value={g.code}>
        {g.label}
    </SelectItem>
    ))
) : (
    <SelectItem value="__empty" disabled>
        No shipping groups found (0 rows in tbl_internalshippinggroups)
    </SelectItem>
)}
```
