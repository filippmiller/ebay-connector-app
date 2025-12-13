# Legacy Schema (Refreshed)


## `buying`

| column_name | data_type |
|-------------|-----------|
| id | integer |
| item_id | character varying |
| tracking_number | character varying |
| buyer_id | character varying |
| buyer_username | character varying |
| seller_id | character varying |
| seller_username | character varying |
| title | text |
| paid_date | timestamp without time zone |
| amount_paid | double precision |
| sale_price | double precision |
| ebay_fee | double precision |
| shipping_cost | double precision |
| refund | double precision |
| profit | double precision |
| status | character varying |
| storage | character varying |
| comment | text |
| author | character varying |
| rec_created | timestamp without time zone |
| rec_updated | timestamp without time zone |


## `tbl_ebay_buyer`

| column_name | data_type |
|-------------|-----------|
| ID | numeric |
| ItemID | text |
| Title | text |
| TransactionID | text |
| OrderLineItemID | text |
| ShippingCarrier | text |
| TrackingNumber | text |
| BuyerCheckoutMessage | text |
| ConditionDisplayName | text |
| SellerEmail | text |
| SellerID | text |
| SellerSite | text |
| SellerLocation | text |
| QuantityPurchased | text |
| CurrentPrice | text |
| ShippingServiceCost | text |
| TotalPrice | text |
| TotalTransactionPrice | text |
| PaymentHoldStatus | text |
| BuyerPaidStatus | text |
| PaidTime | text |
| ShippedTime | text |
| Platform | text |
| BuyerID | text |
| ItemURL | text |
| GalleryURL | text |
| PictureURL0 | text |
| PictureURL1 | text |
| PictureURL2 | text |
| PictureURL3 | text |
| PictureURL4 | text |
| PictureURL5 | text |
| PictureURL6 | text |
| PictureURL7 | text |
| PictureURL8 | text |
| PictureURL9 | text |
| PictureURL10 | text |
| PictureURL11 | text |
| Description | text |
| PrivateNotes | text |
| MyComment | text |
| Storage | text |
| Model_ID | numeric |
| ModelID | numeric |
| ItemStatus | integer |
| ItemStatus_updated | timestamp without time zone |
| ItemStatus_updated_by | text |
| Comment | text |
| Comment_updated | timestamp without time zone |
| Comment_updated_by | text |
| record_updated | timestamp without time zone |
| record_updated_by | text |
| record_created | timestamp without time zone |
| payment_email | text |
| PriceChecked | boolean |
| ReturnID | text |
| AssignedLabels | text |
| Author | text |
| EarningsFlag | boolean |
| earnings_updated | timestamp without time zone |
| earnings_updated_by | text |
| feedback | integer |
| TrackingNumberSkipFlag | boolean |
| ItemTransactionsErrorCode | text |
| ItemTransactionsErrorMessage | text |
| SingleItemErrorCode | text |
| SingleItemErrorMessage | text |
| SingleItemSkipFlag | boolean |
| GetMyeBayBuyingErrorMessage | text |
| GetMyeBayBuyingErrorCode | text |
| GlobalStoragePayPalEmailFlag | boolean |
| GlobalStoragePayPalEmail_updated | timestamp without time zone |
| GlobalStoragePayPalEmail_updated_by | text |
| TrackingNumberScannerFlag | boolean |
| Profit | numeric |
| Profit_updated | timestamp without time zone |
| Profit_updated_by | text |
| ShippingService | text |
| TrackingNumberUpdatedQuantity | numeric |
| TrackingNumberUpdatedQuantity_updated | timestamp without time zone |
| RelocatedPicURL1 | text |
| RelocatedPicURL2 | text |
| RelocatedPicURL3 | text |
| RelocatedPicURL4 | text |
| RelocatedPicURL5 | text |
| RelocatedPicURL6 | text |
| RelocatedPicURL7 | text |
| RelocatedPicURL8 | text |
| RelocatedPicURL9 | text |
| RelocatedPicURL10 | text |
| RelocatedPicURL11 | text |
| RelocatedPicURL12 | text |
| RelocatedPicFlag | boolean |
| GlobalBuyerID | text |
| LotFlag | boolean |
| LotFlag_updated | timestamp without time zone |
| LotFlag_updated_by | text |
| Refund | numeric |
| RefundFlag | boolean |
| RefundFlag_updated | timestamp without time zone |
| RefundFlag_updated_by | text |


## `tbl_ebay_buyer_log`

| column_name | data_type |
|-------------|-----------|
| idx | numeric |
| ID | numeric |
| ItemID | text |
| Title | text |
| TransactionID | text |
| OrderLineItemID | text |
| ShippingCarrier | text |
| TrackingNumber | text |
| ConditionDisplayName | text |
| SellerEmail | text |
| SellerID | text |
| SellerSite | text |
| SellerLocation | text |
| QuantityPurchased | text |
| CurrentPrice | text |
| ShippingServiceCost | text |
| TotalPrice | text |
| TotalTransactionPrice | text |
| PaymentHoldStatus | text |
| BuyerPaidStatus | text |
| PaidTime | text |
| ShippedTime | text |
| Platform | text |
| BuyerID | text |
| ItemURL | text |
| GalleryURL | text |
| PictureURL0 | text |
| PictureURL1 | text |
| PictureURL2 | text |
| PictureURL3 | text |
| PictureURL4 | text |
| PictureURL5 | text |
| PictureURL6 | text |
| PictureURL7 | text |
| PictureURL8 | text |
| PictureURL9 | text |
| PictureURL10 | text |
| PictureURL11 | text |
| Description | text |
| PrivateNotes | text |
| MyComment | text |
| Storage | text |
| Model_ID | numeric |
| ModelID | numeric |
| ItemStatus | integer |
| ItemStatus_updated | timestamp without time zone |
| ItemStatus_updated_by | text |
| Comment | text |
| Comment_updated | timestamp without time zone |
| Comment_updated_by | text |
| record_updated | timestamp without time zone |
| record_updated_by | text |
| record_created | timestamp without time zone |
| log_created | timestamp without time zone |
| log_created_by | text |
| payment_email | text |
| PriceChecked | boolean |
| ReturnID | text |
| AssignedLabels | text |
| BuyerCheckoutMessage | text |
| Author | text |
| EarningsFlag | boolean |
| earnings_updated | timestamp without time zone |
| earnings_updated_by | text |
| feedback | integer |


## `tbl_parts_detail_log`

| column_name | data_type |
|-------------|-----------|
| idx | numeric |
| ID | numeric |
| Part_ID | numeric |
| SKU | numeric |
| Model_ID | numeric |
| Part | text |
| Price | numeric |
| PreviousPrice | numeric |
| Price_updated | timestamp without time zone |
| Market | text |
| UseEbayID | text |
| Category | numeric |
| Description | text |
| ShippingType | text |
| ShippingGroup | integer |
| ConditionID | integer |
| PicURL1 | text |
| PicURL2 | text |
| PicURL3 | text |
| PicURL4 | text |
| PicURL5 | text |
| PicURL6 | text |
| PicURL7 | text |
| PicURL8 | text |
| PicURL9 | text |
| PicURL10 | text |
| PicURL11 | text |
| PicURL12 | text |
| Weight | numeric |
| Part_Number | text |
| AlertFlag | boolean |
| AlertMessage | text |
| RecordStatus | numeric |
| RecordStatusFlag | boolean |
| CheckedStatus | boolean |
| Checked | timestamp without time zone |
| CheckedBy | text |
| OneTimeAuction | boolean |
| record_created_by | text |
| record_created | timestamp without time zone |
| record_updated_by | text |
| record_updated | timestamp without time zone |
| log_created | timestamp without time zone |
| log_created_by | text |


## `tbl_parts_inventory`

| column_name | data_type |
|-------------|-----------|
| ID | numeric |
| SKU | numeric |
| OverrideSKU | text |
| ItemID | text |
| Quantity | integer |
| Storage | text |
| AlternativeStorage | text |
| PrivateNotes | text |
| OverridePrice | numeric |
| OverrideConditionID | integer |
| OverrideTitle | text |
| OverrideDescription | text |
| OverridePicURL1 | text |
| OverridePicURL2 | text |
| OverridePicURL3 | text |
| OverridePicURL4 | text |
| OverridePicURL5 | text |
| OverridePicURL6 | text |
| OverridePicURL7 | text |
| OverridePicURL8 | text |
| OverridePicURL9 | text |
| OverridePicURL10 | text |
| OverridePicURL11 | text |
| OverridePicURL12 | text |
| EbayID | text |
| UserName | text |
| StatusSKU | integer |
| StatusUpdated | timestamp without time zone |
| StatusUpdatedBy | text |
| AmountPaid | numeric |
| Comment | text |
| CommentUpdated | timestamp without time zone |
| CommentUpdatedBy | text |
| AlertFlag | boolean |
| AlertMsg | text |
| AlertMsgUpdated | timestamp without time zone |
| AlertMsgUpdatedBy | text |
| VerifyAck | text |
| VerifyTimestamp | text |
| VerifyError | text |
| AddAck | text |
| AddTimestamp | timestamp without time zone |
| AddError | text |
| ReviseAck | text |
| ReviseTimestamp | timestamp without time zone |
| ReviseError | text |
| record_created | timestamp without time zone |
| record_created_by | text |
| record_updated | timestamp without time zone |
| record_updated_by | text |
| PromotionalSaleID | text |
| SerialNumber | text |
| StatusInBox | integer |
| stocktaking_updated | timestamp without time zone |
| stocktaking_updated_by | text |
| WarehouseID | integer |
| StorageAlias | text |
| ListingStartTime | text |
| ListingEndTime | text |
| ListingTimeUpdated | timestamp without time zone |
| RelistFlag | boolean |
| RelistQuantity | numeric |
| Relist_updated | timestamp without time zone |
| Relist_updated_by | text |
| MarkAsListed_updated | timestamp without time zone |
| MarkAsListed_updated_by | text |
| CloneSKUFlag | boolean |
| CloneSKU_updated | timestamp without time zone |
| CloneSKU_updated_by | text |
| ListingStatus | text |
| ListingStatus_updated | timestamp without time zone |
| ListingStatus_updated_by | text |
| PriceToChange | numeric |
| PriceToChangeFlag | boolean |
| PriceToChangeQueueFlag | boolean |
| batch_error_flag | boolean |
| batch_error_message | text |
| batch_success_flag | boolean |
| batch_success_message | text |
| PriceToChange_updated | timestamp without time zone |
| PriceToChange_updated_by | text |
| MarkAsListedQueueFlag | boolean |
| MarkAsListedQueue_updated | timestamp without time zone |
| MarkAsListedQueue_updated_by | text |
| ListingPriceBatchFlag | boolean |
| BestOfferEnabledFlag | boolean |
| BestOfferEnabled_updated | timestamp without time zone |
| BestOfferEnabled_updated_by | text |
| CancelListingFlag | boolean |
| CancelListingFlag_updated | timestamp without time zone |
| CancelListingFlag_updated_by | text |
| CancelListingQueueFlag | boolean |
| CancelListingQueueFlag_updated | timestamp without time zone |
| CancelListingQueueFlag_updated_by | text |
| ListingEndedBatchFlag | boolean |
| JustSoldFlag | boolean |
| JustSoldFlag_created | timestamp without time zone |
| JustSoldFlag_updated | timestamp without time zone |
| CommentShippingFlag | boolean |
| PriceToChangeOneTime | numeric |
| PriceToChangeOneTimeFlag | boolean |
| PriceToChangeOneTimeQueueFlag | boolean |
| PriceToChangeOneTime_updated | timestamp without time zone |
| PriceToChangeOneTime_updated_by | text |
| SerialNumber_updated | timestamp without time zone |
| SerialNumber_updated_by | text |
| ConditionDescriptionToChange | text |
| ConditionDescriptionToChangeFlag | boolean |
| ConditionDescriptionToChange_updated | timestamp without time zone |
| ConditionDescriptionToChange_updated_by | text |
| DescriptionToChange | text |
| DescriptionToChangeFlag | boolean |
| DescriptionToChange_updated | timestamp without time zone |
| DescriptionToChange_updated_by | text |
| TitleToChange | text |
| TitleToChangeFlag | boolean |
| TitleToChange_updated | timestamp without time zone |
| TitleToChange_updated_by | text |
| FreezeListingFlag | boolean |
| FreezeListingFlag_updated | timestamp without time zone |
| FreezeListingFlag_updated_by | text |
| FreezeListingQueueFlag | boolean |
| FreezeListingQueueFlag_updated | timestamp without time zone |
| FreezeListingQueueFlag_updated_by | text |
| BestOfferAutoAcceptPriceFlag | boolean |
| BestOfferAutoAcceptPricePercent | numeric |
| BestOfferAutoAcceptPriceFlag_updated | timestamp without time zone |
| BestOfferAutoAcceptPriceFlag_updated_by | text |
| BestOfferMinimumPriceFlag | boolean |
| BestOfferMinimumPricePercent | numeric |
| BestOfferMinimumPriceFlag_updated | timestamp without time zone |
| BestOfferMinimumPriceFlag_updated_by | text |
| MarkAsRelistedFlag | boolean |
| MarkAsRelisted_updated | timestamp without time zone |
| MarkAsRelisted_updated_by | text |
| MarkAsRelistedQueueFlag | boolean |
| MarkAsRelistedQueue_updated | timestamp without time zone |
| MarkAsRelistedQueue_updated_by | text |
| BestOfferToChangeFlag | boolean |
| BestOfferToChangeFlag_updated | timestamp without time zone |
| BestOfferToChangeFlag_updated_by | text |
| RelistListingFlag | boolean |
| RelistListingFlag_updated | timestamp without time zone |
| RelistListingFlag_updated_by | text |
| RelistListingQueueFlag | boolean |
| RelistListingQueueFlag_updated | timestamp without time zone |
| RelistListingQueueFlag_updated_by | text |
| GlobalEbayIDForRelist | text |
| GlobalEbayIDForRelistFlag | boolean |
| LossFlag | boolean |
| OverrideDomesticOnlyFlag | boolean |
| PhantomCancelListingFlag | boolean |
| PhantomCancelListingFlag_updated | timestamp without time zone |
| PhantomCancelListingFlag_updated_by | text |
| ChangedItem_updated | timestamp without time zone |
| ChangedItem_updated_by | text |
| ClearLog_updated | timestamp without time zone |
| ItemListedDateTime | timestamp without time zone |
| SKU2 | text |
| ReturnFlag | boolean |
| ReturnFlag_updated | timestamp without time zone |
| ReturnFlag_updated_by | text |
| CancelListingForSectionValue | text |
| ShippingGroupToChange | integer |
| ShippingGroupToChangeFlag | boolean |
| ShippingGroupToChange_updated | timestamp without time zone |
| ShippingGroupToChange_updated_by | text |
| EndedForRelistFlag | boolean |
| EndedForRelistQuantity | numeric |
| ActiveBestOfferFlag | boolean |
| ActiveBestOfferManualFlag | boolean |
| ActiveBestOfferManualFlag_updated | timestamp without time zone |
| ActiveBestOfferManualFlag_updated_by | text |
| CancelListingToCheckedQueueFlag | boolean |
| CancelListingToCheckedQuantity | numeric |
| CancelListingToCheckedQueueFlag_updated | timestamp without time zone |
| CancelListingToCheckedQueueFlag_updated_by | text |
| CancelListingToMarkAsGroupListedQueueFlag | boolean |
| CancelListingToMarkAsGroupListedQuantity | numeric |
| CancelListingToMarkAsGroupListedQueueFlag_updated | timestamp without time zone |
| CancelListingToMarkAsGroupListedQueueFlag_updated_by | text |
| ChangeListingDurationFlag | boolean |
| ChangeListingDuration | text |
| ChangeListingDurationInDays | numeric |
| CancelListingStatusSKU | integer |
| BestOfferAutoAcceptPriceValue | numeric |
| BestOfferMinimumPriceValue | numeric |
| BestOfferMode | text |
| ReplacementInventoryID | numeric |
| ReplacementInventoryID_updated | timestamp without time zone |
| ReplacementInventoryID_updated_by | text |
| FilterValueWarehouseID | text |
| FilterValueStatusSKU | numeric |
| ManifestMontrealFlag | boolean |
| ManifestMontrealFlag_updated | timestamp without time zone |
| ManifestMontrealFlag_updated_by | text |
| CancelListingInterface | text |
| CancelListingInterface_updated | timestamp without time zone |
| CancelListingInterface_updated_by | text |


## Missing tables


- `tbl_parts_inventory_log` not present in this database
