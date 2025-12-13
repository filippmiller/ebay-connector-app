# Legacy Analytics Dump for StorageID 'A331'


## Buying (A331)

### SQL
```sql
SELECT *
        FROM buying
        WHERE storage = :storage_id
           OR storage ILIKE :storage_prefix;
```

### Result
_No rows_


## PartsInventory (tbl_parts_inventory, A331)

### SQL
```sql
SELECT *
        FROM tbl_parts_inventory
        WHERE "Storage" = :storage_id
           OR "AlternativeStorage" = :storage_id;
```

### Result
| ID | SKU | OverrideSKU | ItemID | Quantity | Storage | AlternativeStorage | PrivateNotes | OverridePrice | OverrideConditionID | OverrideTitle | OverrideDescription | OverridePicURL1 | OverridePicURL2 | OverridePicURL3 | OverridePicURL4 | OverridePicURL5 | OverridePicURL6 | OverridePicURL7 | OverridePicURL8 | OverridePicURL9 | OverridePicURL10 | OverridePicURL11 | OverridePicURL12 | EbayID | UserName | StatusSKU | StatusUpdated | StatusUpdatedBy | AmountPaid | Comment | CommentUpdated | CommentUpdatedBy | AlertFlag | AlertMsg | AlertMsgUpdated | AlertMsgUpdatedBy | VerifyAck | VerifyTimestamp | VerifyError | AddAck | AddTimestamp | AddError | ReviseAck | ReviseTimestamp | ReviseError | record_created | record_created_by | record_updated | record_updated_by | PromotionalSaleID | SerialNumber | StatusInBox | stocktaking_updated | stocktaking_updated_by | WarehouseID | StorageAlias | ListingStartTime | ListingEndTime | ListingTimeUpdated | RelistFlag | RelistQuantity | Relist_updated | Relist_updated_by | MarkAsListed_updated | MarkAsListed_updated_by | CloneSKUFlag | CloneSKU_updated | CloneSKU_updated_by | ListingStatus | ListingStatus_updated | ListingStatus_updated_by | PriceToChange | PriceToChangeFlag | PriceToChangeQueueFlag | batch_error_flag | batch_error_message | batch_success_flag | batch_success_message | PriceToChange_updated | PriceToChange_updated_by | MarkAsListedQueueFlag | MarkAsListedQueue_updated | MarkAsListedQueue_updated_by | ListingPriceBatchFlag | BestOfferEnabledFlag | BestOfferEnabled_updated | BestOfferEnabled_updated_by | CancelListingFlag | CancelListingFlag_updated | CancelListingFlag_updated_by | CancelListingQueueFlag | CancelListingQueueFlag_updated | CancelListingQueueFlag_updated_by | ListingEndedBatchFlag | JustSoldFlag | JustSoldFlag_created | JustSoldFlag_updated | CommentShippingFlag | PriceToChangeOneTime | PriceToChangeOneTimeFlag | PriceToChangeOneTimeQueueFlag | PriceToChangeOneTime_updated | PriceToChangeOneTime_updated_by | SerialNumber_updated | SerialNumber_updated_by | ConditionDescriptionToChange | ConditionDescriptionToChangeFlag | ConditionDescriptionToChange_updated | ConditionDescriptionToChange_updated_by | DescriptionToChange | DescriptionToChangeFlag | DescriptionToChange_updated | DescriptionToChange_updated_by | TitleToChange | TitleToChangeFlag | TitleToChange_updated | TitleToChange_updated_by | FreezeListingFlag | FreezeListingFlag_updated | FreezeListingFlag_updated_by | FreezeListingQueueFlag | FreezeListingQueueFlag_updated | FreezeListingQueueFlag_updated_by | BestOfferAutoAcceptPriceFlag | BestOfferAutoAcceptPricePercent | BestOfferAutoAcceptPriceFlag_updated | BestOfferAutoAcceptPriceFlag_updated_by | BestOfferMinimumPriceFlag | BestOfferMinimumPricePercent | BestOfferMinimumPriceFlag_updated | BestOfferMinimumPriceFlag_updated_by | MarkAsRelistedFlag | MarkAsRelisted_updated | MarkAsRelisted_updated_by | MarkAsRelistedQueueFlag | MarkAsRelistedQueue_updated | MarkAsRelistedQueue_updated_by | BestOfferToChangeFlag | BestOfferToChangeFlag_updated | BestOfferToChangeFlag_updated_by | RelistListingFlag | RelistListingFlag_updated | RelistListingFlag_updated_by | RelistListingQueueFlag | RelistListingQueueFlag_updated | RelistListingQueueFlag_updated_by | GlobalEbayIDForRelist | GlobalEbayIDForRelistFlag | LossFlag | OverrideDomesticOnlyFlag | PhantomCancelListingFlag | PhantomCancelListingFlag_updated | PhantomCancelListingFlag_updated_by | ChangedItem_updated | ChangedItem_updated_by | ClearLog_updated | ItemListedDateTime | SKU2 | ReturnFlag | ReturnFlag_updated | ReturnFlag_updated_by | CancelListingForSectionValue | ShippingGroupToChange | ShippingGroupToChangeFlag | ShippingGroupToChange_updated | ShippingGroupToChange_updated_by | EndedForRelistFlag | EndedForRelistQuantity | ActiveBestOfferFlag | ActiveBestOfferManualFlag | ActiveBestOfferManualFlag_updated | ActiveBestOfferManualFlag_updated_by | CancelListingToCheckedQueueFlag | CancelListingToCheckedQuantity | CancelListingToCheckedQueueFlag_updated | CancelListingToCheckedQueueFlag_updated_by | CancelListingToMarkAsGroupListedQueueFlag | CancelListingToMarkAsGroupListedQuantity | CancelListingToMarkAsGroupListedQueueFlag_updated | CancelListingToMarkAsGroupListedQueueFlag_updated_by | ChangeListingDurationFlag | ChangeListingDuration | ChangeListingDurationInDays | CancelListingStatusSKU | BestOfferAutoAcceptPriceValue | BestOfferMinimumPriceValue | BestOfferMode | ReplacementInventoryID | ReplacementInventoryID_updated | ReplacementInventoryID_updated_by | FilterValueWarehouseID | FilterValueStatusSKU | ManifestMontrealFlag | ManifestMontrealFlag_updated | ManifestMontrealFlag_updated_by | CancelListingInterface | CancelListingInterface_updated | CancelListingInterface_updated_by |
|----|-----|-------------|--------|----------|---------|--------------------|--------------|---------------|---------------------|---------------|---------------------|-----------------|-----------------|-----------------|-----------------|-----------------|-----------------|-----------------|-----------------|-----------------|------------------|------------------|------------------|--------|----------|-----------|---------------|-----------------|------------|---------|----------------|------------------|-----------|----------|-----------------|-------------------|-----------|-----------------|-------------|--------|--------------|----------|-----------|-----------------|-------------|----------------|-------------------|----------------|-------------------|-------------------|--------------|-------------|---------------------|------------------------|-------------|--------------|------------------|----------------|--------------------|------------|----------------|----------------|-------------------|----------------------|-------------------------|--------------|------------------|---------------------|---------------|-----------------------|--------------------------|---------------|-------------------|------------------------|------------------|---------------------|--------------------|-----------------------|-----------------------|--------------------------|-----------------------|---------------------------|------------------------------|-----------------------|----------------------|--------------------------|-----------------------------|-------------------|---------------------------|------------------------------|------------------------|--------------------------------|-----------------------------------|-----------------------|--------------|----------------------|----------------------|---------------------|----------------------|--------------------------|-------------------------------|------------------------------|---------------------------------|----------------------|-------------------------|------------------------------|----------------------------------|--------------------------------------|-----------------------------------------|---------------------|-------------------------|-----------------------------|--------------------------------|---------------|-------------------|-----------------------|--------------------------|-------------------|---------------------------|------------------------------|------------------------|--------------------------------|-----------------------------------|------------------------------|---------------------------------|--------------------------------------|-----------------------------------------|---------------------------|------------------------------|-----------------------------------|--------------------------------------|--------------------|------------------------|---------------------------|-------------------------|-----------------------------|--------------------------------|-----------------------|-------------------------------|----------------------------------|-------------------|---------------------------|------------------------------|------------------------|--------------------------------|-----------------------------------|-----------------------|---------------------------|----------|--------------------------|--------------------------|----------------------------------|-------------------------------------|---------------------|------------------------|------------------|--------------------|------|------------|--------------------|-----------------------|------------------------------|-----------------------|---------------------------|-------------------------------|----------------------------------|--------------------|------------------------|---------------------|---------------------------|-----------------------------------|--------------------------------------|---------------------------------|--------------------------------|-----------------------------------------|--------------------------------------------|-------------------------------------------|------------------------------------------|---------------------------------------------------|------------------------------------------------------|---------------------------|-----------------------|-----------------------------|------------------------|-------------------------------|----------------------------|---------------|------------------------|--------------------------------|-----------------------------------|------------------------|----------------------|----------------------|------------------------------|---------------------------------|------------------------|--------------------------------|-----------------------------------|
| 494399 | 100000000147448 |  | 396396793058 | 1 | A331 |  |  | 74.99 | 3000 | Acer Aspire R 15 R5-571TG i7-7500U 2.7Ghz Motherboard NVIDIA 940MX NBGKH11002 |  | https://i.frg.im/7kBiux4M/mg544f06.jpg?v=1714544608.627?v=51df04b0-2d5e-4889-b8be-e3af2e17b78b | https://i.frg.im/qZ6XrsMv/mg544f07.jpg?v=1714544614.767?v=2b22786f-54bd-49a0-a04d-575e5ea2d221 | https://i.frg.im/MqhXJ7rj/mg544f08.jpg?v=1714544620.317?v=c2b4ed65-c4f1-45db-ac1c-83d903bc1a6a | https://i.frg.im/npggTc0o/a331c.jpg?v=1754465623.203?v=db319de1-eb34-4b82-bd54-5b7caf70d79a |  |  |  |  |  |  |  |  | mil_243 | Gordey | 5 | 2025-09-20 18:31:06.020000 | system |  |  |  |  | False |  | 2025-09-06 12:50:51.233000 | system |  |  |  |  |  |  |  |  |  | 2025-09-03 03:45:15.317000 | Gordey | 2025-09-06 12:50:51.250000 | system (Inventory::class) |  |  |  |  |  | 3 |  |  |  | 2025-09-16 16:00:33.280000 |  |  |  |  | 2025-09-06 12:48:47.607000 | Sergey |  |  |  |  |  |  | 74.99 | False | False |  |  |  |  | 2025-09-06 12:44:45.050000 | Sergey | False | 2025-09-06 12:44:45.050000 | Sergey | True | False |  |  |  |  |  |  |  |  |  | False | 2025-09-20 18:31:06.020000 | 2025-09-20 18:32:15.223000 |  |  |  |  |  |  |  |  |  | False | 2025-09-06 12:44:45.050000 | Sergey |  | False | 2025-09-06 12:44:45.050000 | Sergey | Acer Aspire R 15 R5-571TG i7-7500U 2.7Ghz Motherboard NVIDIA 940MX NBGKH11002 | False | 2025-09-06 12:44:45.050000 | Sergey |  |  |  |  |  |  | False | 0 | 2025-09-06 12:44:45.050000 | Sergey | False | 0 | 2025-09-06 12:44:45.050000 | Sergey |  |  |  |  |  |  |  | 2025-09-06 12:44:45.050000 | Sergey |  |  |  |  |  |  |  |  |  | False |  |  |  | 2025-09-06 12:48:47.607000 | Sergey |  | 2025-09-06 12:50:51.233000 | 100000000147448 |  |  |  |  |  | False | 2025-09-06 12:44:45.050000 | Sergey |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | 0 | 0 |  |  |  |  |  | 0 |  |  |  |  |  |  |


## Distinct SKU/OverrideSKU/ItemID/UserName/StatusSKU

### SQL
```sql
SELECT DISTINCT
          "SKU",
          "OverrideSKU",
          "ItemID",
          "UserName",
          "StatusSKU"
        FROM tbl_parts_inventory
        WHERE "Storage" = :storage_id
           OR "AlternativeStorage" = :storage_id;
```

### Result
| SKU | OverrideSKU | ItemID | UserName | StatusSKU |
|-----|-------------|--------|----------|-----------|
| 100000000147448 |  | 396396793058 | Gordey | 5 |


## EbayBuyer (tbl_ebay_buyer, A331)

### SQL
```sql
SELECT *
        FROM tbl_ebay_buyer
        WHERE "Storage" = :storage_id
           OR "ItemID" IN (
               SELECT DISTINCT "ItemID"
               FROM tbl_parts_inventory
               WHERE "Storage" = :storage_id
                  OR "AlternativeStorage" = :storage_id
           );
```

### Result
_No rows_


## EbayBuyerLog (tbl_ebay_buyer_log, A331)

### SQL
```sql
SELECT *
        FROM tbl_ebay_buyer_log
        WHERE "Storage" = :storage_id
           OR "ItemID" IN (
               SELECT DISTINCT "ItemID"
               FROM tbl_parts_inventory
               WHERE "Storage" = :storage_id
                  OR "AlternativeStorage" = :storage_id
           );
```

### Result
_No rows_


## PartsDetailLog (tbl_parts_detail_log, by SKU for A331)


tbl_parts_detail_log not present in this database; skipping query.


## Combined SELECT (tree)


```sql

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

```
