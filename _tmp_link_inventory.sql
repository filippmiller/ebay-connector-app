-- Link back to the inventory row we previously saw (legacy tbl_parts_inventory)
SELECT "ID", "SKU", "StatusSKU", "OverrideTitle", "OverridePrice", "OverrideConditionID", "OverridePicURL1"
FROM public.tbl_parts_inventory
WHERE "SKU" = 100000000095909;

-- If the modern inventory table exists, see if it has a row for this sku_code
SELECT id, sku_code, sku_id, status, parts_detail_id, ebay_listing_id
FROM public.inventory
WHERE sku_code = '100000000095909'
   OR sku_id IN (SELECT id FROM public.sku WHERE sku_code = '100000000095909')
LIMIT 20;
