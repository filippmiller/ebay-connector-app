# Inventory SKU/ItemID Active/Sold Counters

## Purpose

The new Inventory V3 grid shows legacy-style counters for each row:

- `SKU` → `SKU (ActiveCount/SoldCount)`
- `ItemID` → `ItemID (ActiveCount/SoldCount)`

Counts are computed across the **entire** legacy inventory table `tbl_parts_inventory` but only for the SKUs and ItemIDs that appear on the current page of the grid. To keep the grid fast on large datasets (~500k+ rows), we pre-aggregate counts in Postgres materialized views and query those instead of doing live `COUNT(*)` on each request.

## Status mapping (strict IDs)

Legacy numeric status codes from `tbl_parts_inventorystatus` are mapped as follows:

- **Active**: `StatusSKU = 3` (`InventoryStatus_Name = 'AddedToEbay'`, `InventoryShortStatus_Name = 'ACTIVE'`)
- **Sold**: `StatusSKU = 5` (`InventoryStatus_Name = 'SoldOnEbay'`, `InventoryShortStatus_Name = 'SOLD'`)

`StatusSKU = 15` (`SoldOnPortableBay`) is **not** included in these counters.

All counters below are defined strictly in terms of these two IDs.

## Materialized views

Migration: `supabase/migrations/20251209080000_inventory_counts_materialized_views.sql`.

### Per-SKU counts

```sql
CREATE MATERIALIZED VIEW public.mv_tbl_parts_inventory_sku_counts AS
SELECT
    "SKU",
    COUNT(*) FILTER (WHERE "StatusSKU" = 3) AS sku_active_count,
    COUNT(*) FILTER (WHERE "StatusSKU" = 5) AS sku_sold_count
FROM
    "tbl_parts_inventory"
WHERE
    "SKU" IS NOT NULL
GROUP BY
    "SKU";

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_tbl_parts_inventory_sku_counts_sku
    ON public.mv_tbl_parts_inventory_sku_counts ("SKU");
```

### Per-ItemID counts

```sql
CREATE MATERIALIZED VIEW public.mv_tbl_parts_inventory_itemid_counts AS
SELECT
    "ItemID",
    COUNT(*) FILTER (WHERE "StatusSKU" = 3) AS item_active_count,
    COUNT(*) FILTER (WHERE "StatusSKU" = 5) AS item_sold_count
FROM
    "tbl_parts_inventory"
WHERE
    "ItemID" IS NOT NULL
GROUP BY
    "ItemID";

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_tbl_parts_inventory_itemid_counts_itemid
    ON public.mv_tbl_parts_inventory_itemid_counts ("ItemID");
```

Notes:

- No tenant / warehouse filters are applied in these views; counters are **global** across all rows in `tbl_parts_inventory`.
- `WHERE ... IS NOT NULL` avoids creating rows with `NULL` keys.

## How the backend uses the views

Endpoint: `GET /api/grids/inventory/data` (gridKey = `"inventory"`).

- When `includeCounts=false` (default), the grid behaves as before – no extra queries and no dependency on the MVs.
- When `includeCounts=true` (query param `includeCounts=1`):
  1. `_get_inventory_data` selects the current page from `tbl_parts_inventory` (with filters/sort/pagination).
  2. It collects distinct `SKU` and `ItemID` values present on that page.
  3. It runs **two lightweight queries** against the MVs:

     ```sql
     SELECT "SKU" AS sku_key, sku_active_count, sku_sold_count
     FROM public.mv_tbl_parts_inventory_sku_counts
     WHERE "SKU" = ANY(:sku_list);

     SELECT "ItemID" AS itemid_key, item_active_count, item_sold_count
     FROM public.mv_tbl_parts_inventory_itemid_counts
     WHERE "ItemID" = ANY(:itemid_list);
     ```

     `:sku_list` / `:itemid_list` are bound as Python lists via SQLAlchemy, which psycopg2 coerces to Postgres array parameters compatible with `= ANY(...)`.

  4. The results are stored in dictionaries:

     - `sku_counts[SKU] = {"active": A, "sold": S}`
     - `itemid_counts[ItemID] = {"active": A, "sold": S}`

  5. During row serialization, the raw `SKU` / `ItemID` values are decorated as:

     - `SKU` → `"<original> (A/S)"` when a match exists in `sku_counts`.
     - `ItemID` → `"<original> (A/S)"` when a match exists in `itemid_counts`.

If the views are missing or a query fails, the code falls back to **no counts** rather than breaking the grid.

## Refresh strategy

These materialized views are intentionally allowed to be slightly stale. They must be refreshed periodically.

### Manual refresh (SQL)

In Supabase SQL editor or psql:

```sql
REFRESH MATERIALIZED VIEW CONCURRENTLY public.mv_tbl_parts_inventory_sku_counts;
REFRESH MATERIALIZED VIEW CONCURRENTLY public.mv_tbl_parts_inventory_itemid_counts;
```

Use `CONCURRENTLY` to avoid long exclusive locks; this requires the unique indexes defined above.

### Recommended cadence

- For typical workloads, refreshing every **5–15 minutes** is a good balance between freshness and performance.
- For heavy bulk imports or large status updates, you may trigger an additional refresh after the batch.

### Worker / scheduler

At the moment, there is **no dedicated worker in this repo** that refreshes these views automatically. 

Options for automation (to be implemented separately):

- Supabase Scheduled Task or cron job that runs the two `REFRESH MATERIALIZED VIEW` statements on a fixed schedule.
- A lightweight Python worker using the existing backend stack which:
  - acquires a DB session, executes the two `REFRESH` statements,
  - is triggered by an external scheduler (system cron, Railway job, etc.).

When adding such a worker, document its schedule and link back to this file.

## Sanity checks

When verifying the feature:

1. Ensure migrations have been applied so that both MVs and indexes exist.
2. Run a manual refresh at least once after deployment.
3. For a given `SKU` / `ItemID`:
   - Query the MV directly
   - Compare `*_active_count` / `*_sold_count` with what the Inventory V3 grid shows when `includeCounts=1`.
4. Confirm that filters in the grid **do not** affect the global counts: they only decide which rows are shown, but the `(A/S)` numbers always come from a global aggregate over all of `tbl_parts_inventory`.
