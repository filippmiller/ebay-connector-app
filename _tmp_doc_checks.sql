SELECT jsonb_pretty(to_jsonb(t))
FROM public."tbl_internalshippinggroups" t
WHERE (to_jsonb(t)->>'ID')='4'
LIMIT 1;

SELECT "ID", "SKU", "ShippingGroup", "ShippingType", "Price", "Weight", "Unit", "ListingType", "ListingDuration", "SiteID", "MPN", "UPC", "Part_Number", "ConditionID", "PicURL1"
FROM public."SKU_catalog"
WHERE "SKU" = 100000000095909;

SELECT "ID", "SKU", "StatusSKU", "OverrideTitle", "OverridePrice", "Quantity"
FROM public.tbl_parts_inventory
WHERE "ID" = 501610;
