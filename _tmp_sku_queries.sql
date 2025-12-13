SELECT "ID", "SKU", "ShippingGroup", "ShippingType", "Price", "Weight", "Unit", "ListingType", "ListingDuration", "SiteID", "MPN", "UPC", "Part_Number", "ConditionID", "PicURL1" 
FROM public."SKU_catalog" 
WHERE "SKU" = 100000000095909;

-- sample: any SKU using shipping group 4?
SELECT COUNT(*) AS sku_count_shipping_group_4 FROM public."SKU_catalog" WHERE "ShippingGroup" = 4;

-- list any other shipping-related tables
SELECT table_schema, table_name FROM information_schema.tables 
WHERE table_schema NOT IN ('pg_catalog','information_schema') AND table_name ILIKE '%shipping%'
ORDER BY table_schema, table_name;
