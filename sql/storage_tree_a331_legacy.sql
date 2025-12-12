-- Legacy storage tree for a specific StorageID ('A331')

WITH inv AS (
  SELECT
    pi."ID"              AS parts_inventory_id,
    pi."Storage"         AS storage,
    pi."AlternativeStorage",
    pi."SKU",
    pi."OverrideSKU",
    pi."ItemID",
    pi."Quantity",
    pi."OverridePrice",
    pi."OverrideTitle",
    pi."UserName",
    pi."StatusSKU"
  FROM tbl_parts_inventory pi
  WHERE pi."Storage" = 'A331'
     OR pi."AlternativeStorage" = 'A331'
),
buy AS (
  SELECT *
  FROM buying
  WHERE storage = 'A331'
     OR storage ILIKE 'A331%'
),
buyer AS (
  SELECT
    b.* 
  FROM tbl_ebay_buyer b
  WHERE b."Storage" = 'A331'
     OR b."ItemID" IN (SELECT DISTINCT "ItemID" FROM inv)
),
buyer_log AS (
  SELECT
    bl.*
  FROM tbl_ebay_buyer_log bl
  WHERE bl."Storage" = 'A331'
     OR bl."ItemID" IN (SELECT DISTINCT "ItemID" FROM inv)
)
SELECT
  inv.storage,
  inv.parts_inventory_id,
  inv."SKU",
  inv."ItemID",
  inv."OverridePrice",
  inv."OverrideTitle",
  buyer."TransactionID",
  buyer."OrderLineItemID",
  buyer."TotalPrice",
  buyer."TotalTransactionPrice",
  buyer."ShippingServiceCost",
  buyer."BuyerID",
  buyer."PaidTime",
  buyer."ShippedTime",
  buyer_log."Profit",
  buyer_log."Refund",
  buyer_log."RefundFlag"
FROM inv
LEFT JOIN buyer    ON buyer."ItemID"   = inv."ItemID"
                  AND buyer."Storage"  = inv.storage
LEFT JOIN buyer_log bl ON bl."ItemID"  = inv."ItemID"
                      AND bl."Storage" = inv.storage
ORDER BY inv.parts_inventory_id, buyer."TransactionID";


-- Parameterized template for arbitrary StorageID (Postgres-style bind parameter :storage_id)
-- Replace :storage_id with your value or bind from application code.

WITH inv AS (
  SELECT
    pi."ID"              AS parts_inventory_id,
    pi."Storage"         AS storage,
    pi."AlternativeStorage",
    pi."SKU",
    pi."OverrideSKU",
    pi."ItemID",
    pi."Quantity",
    pi."OverridePrice",
    pi."OverrideTitle",
    pi."UserName",
    pi."StatusSKU"
  FROM tbl_parts_inventory pi
  WHERE pi."Storage" = :storage_id
     OR pi."AlternativeStorage" = :storage_id
),
buy AS (
  SELECT *
  FROM buying
  WHERE storage = :storage_id
     OR storage ILIKE (:storage_id || '%')
),
buyer AS (
  SELECT
    b.* 
  FROM tbl_ebay_buyer b
  WHERE b."Storage" = :storage_id
     OR b."ItemID" IN (SELECT DISTINCT "ItemID" FROM inv)
),
buyer_log AS (
  SELECT
    bl.*
  FROM tbl_ebay_buyer_log bl
  WHERE bl."Storage" = :storage_id
     OR bl."ItemID" IN (SELECT DISTINCT "ItemID" FROM inv)
)
SELECT
  inv.storage,
  inv.parts_inventory_id,
  inv."SKU",
  inv."ItemID",
  inv."OverridePrice",
  inv."OverrideTitle",
  buyer."TransactionID",
  buyer."OrderLineItemID",
  buyer."TotalPrice",
  buyer."TotalTransactionPrice",
  buyer."ShippingServiceCost",
  buyer."BuyerID",
  buyer."PaidTime",
  buyer."ShippedTime",
  buyer_log."Profit",
  buyer_log."Refund",
  buyer_log."RefundFlag"
FROM inv
LEFT JOIN buyer    ON buyer."ItemID"   = inv."ItemID"
                  AND buyer."Storage"  = inv.storage
LEFT JOIN buyer_log bl ON bl."ItemID"  = inv."ItemID"
                      AND bl."Storage" = inv.storage
ORDER BY inv.parts_inventory_id, buyer."TransactionID";
