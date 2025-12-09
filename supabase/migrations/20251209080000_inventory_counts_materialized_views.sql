-- Materialized views for fast per-SKU / per-ItemID Active/Sold counters
--
-- Active  = StatusSKU = 3  (AddedToEbay / ACTIVE)
-- Sold    = StatusSKU = 5  (SoldOnEbay / SOLD)
--
-- These views are intentionally slightly stale; they must be refreshed
-- periodically via REFRESH MATERIALIZED VIEW (see docs).

-- Per-SKU aggregates
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


-- Per-ItemID aggregates
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
