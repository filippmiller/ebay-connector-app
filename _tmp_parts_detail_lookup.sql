-- Look for the specific SKU in both places
SELECT id, sku, override_sku, status_sku, listing_status, override_title,
       override_price, price_to_change,
       override_condition_id,
       override_pic_url_1, override_pic_url_2
FROM public.parts_detail
WHERE sku = '100000000095909' OR override_sku = '100000000095909'
ORDER BY id DESC
LIMIT 20;

SELECT "ID", "SKU", "ShippingGroup", "ShippingType", "Price", "ConditionID", "PicURL1"
FROM public."tbl_parts_detail"
WHERE "SKU" = 100000000095909
ORDER BY "ID" DESC
LIMIT 20;
