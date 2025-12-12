# FULL eBay API HTTP Request - Ready for Review 🔍

## 📋 Request Overview
This document shows the **COMPLETE** HTTP request that will be sent to eBay API for publishing your listing.

---

## 🌐 HTTP Request Details

### **Method & URL**
```http
POST https://api.ebay.com/sell/inventory/v1/bulk_publish_offer
```

*Note: If using sandbox environment:*
```http
POST https://api.sandbox.ebay.com/sell/inventory/v1/bulk_publish_offer
```

---

## 🔐 HTTP Headers

```json
{
  "Authorization": "Bearer <YOUR_EBAY_ACCESS_TOKEN>",
  "Content-Type": "application/json",
  "Accept": "application/json"
}
```

**Security Note:** The actual OAuth access token will be automatically resolved from your connected eBay account. It is never logged or displayed in full for security reasons.

---

## 📦 Request Body (JSON Payload)

### Complete Request Structure
```json
{
  "requests": [
    {
      "offerId": "<resolved_at_runtime_for_sku_1000000000095909>"
    }
  ]
}
```

### ⚙️ How `offerId` is Resolved

**Before** sending this request, the system performs these steps:

1. **GET Offers by SKU**
   ```http
   GET https://api.ebay.com/sell/inventory/v1/offer?sku=1000000000095909&limit=200
   ```
   
   Headers:
   ```json
   {
     "Authorization": "Bearer <YOUR_EBAY_ACCESS_TOKEN>",
     "Content-Type": "application/json",
     "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"
   }
   ```

2. **Extract offerId** from the response (example):
   ```json
   {
     "offers": [
       {
         "offerId": "91234567890",
         "sku": "1000000000095909",
         "marketplaceId": "EBAY_US",
         "format": "FIXED_PRICE",
         "listingDescription": "...",
         "pricingSummary": {
           "price": {
             "value": "17.99",
             "currency": "USD"
           }
         },
         "quantityLimitPerBuyer": 1,
         "availableQuantity": 1,
         "categoryId": "119"
       }
     ]
   }
   ```

3. **Use the `offerId`** in the bulk_publish_offer request

---

## 📊 Variables / Payload Fields Used for Listing

Based on your screenshot, here are ALL the fields that will be used:

### **Mandatory Fields**

| Field | Value | Source |
|-------|-------|--------|
| `legacy_inventory_id` | `591218` | `tbl_parts_inventory.ID` |
| `sku` | `1000000000095909` | `tbl_parts_inventory.SKU` |
| `title` | `Genuine HP 15-GB 15.6" Palmrest Touchpad w/ Keyboard zNZ9H000100 Read #Q353` | `tbl_parts_detail.Part` or Override |
| `price` | `17.99` | `tbl_parts_  detail.Price` or Override |
| `quantity` | `1` | `tbl_parts_inventory.Quantity` |
| `condition_id` | `7000` | `tbl_parts_detail.ConditionID` |
| `pictures` | `4` (images) | `tbl_parts_detail.PicURL1..12` |
| `shipping_group` | `4: no international` | `tbl_parts_detail.ShippingGroup` |
| `shipping_type` | `Flat` | `tbl_parts_detail.ShippingType` |
| `listing_type` | `FixedPriceItem` | `tbl_parts_detail.ListingType` |
| `listing_duration` | `GTC` | `tbl_parts_detail.ListingDuration` |
| `ufc_id` | `--` | (Not applicable) |
| `category` | `119` | `tbl_parts_detail.Category` |

### **Optional Fields**

| Field | Value | Source |
|-------|-------|--------|
| `mpn` | `zNZ9H000100` | `tbl_parts_detail.MPN` |
| `part_number` | `zNZ9H000100` | `tbl_parts_detail.Part_Number` |
| `upc` | `Does not apply` | `tbl_parts_detail.UPC` |
| `weight` | `32` | `tbl_parts_detail.Weight` |
| `unit` | `--` | `tbl_parts_detail.Unit` |
| `description` | `--` | `tbl_parts_detail.Description` |
| `condition_label` | `--` | Resolved from `item_conditions` table |
| `pic_url_1` | `https://i.frog.ink/xsujdkiqg33-j.jpg?v=a37df2df-3f96-4a14-bbb8-ddf722c34c2d` | `tbl_parts_detail.PicURL1` |
| `pic_url_2..12` | (additional URLs if present) | `tbl_parts_detail.PicURL2..12` |

---

## 🔄 Complete API Call Sequence

Here's the **FULL SEQUENCE** of HTTP calls that happen when you click "LIST":

### **Step 1: Fetch Offers**
```http
GET /sell/inventory/v1/offer?sku=1000000000095909&limit=200
Host: api.ebay.com
Authorization: Bearer v^1.1#i^1#...
Content-Type: application/json
X-EBAY-C-MARKETPLACE-ID: EBAY_US
```

**Response (200 OK):**
```json
{
  "total": 1,
  "offers": [
    {
      "offerId": "91234567890",
      "sku": "1000000000095909",
      "marketplaceId": "EBAY_US",
      "format": "FIXED_PRICE",
      "availableQuantity": 1,
      "categoryId": "119",
      "pricingSummary": {
        "price": {
          "value": "17.99",
          "currency": "USD"
        }
      }
    }
  ]
}
```

---

### **Step 2: Publish Offer (Bulk Publish)**
```http
POST /sell/inventory/v1/bulk_publish_offer
Host: api.ebay.com
Authorization: Bearer v^1.1#i^1#...
Content-Type: application/json
Accept: application/json
```

**Request Body:**
```json
{
  "requests": [
    {
      "offerId": "91234567890"
    }
  ]
}
```

**Expected Response (200 or 207 Multi-Status):**
```json
{
  "responses": [
    {
      "offerId": "91234567890",
      "listingId": "115xxxxxxxxx",
      "statusCode": 200,
      "status": "SUCCESS"
    }
  ]
}
```

---

## ⚠️ Important Notes

### What is **NOT** included in the HTTP request:
- ❌ `legacy_inventory_id` (internal only, not sent to eBay)
- ❌ Individual fields like `title`, `price`, `description` (these are already part of the **offer** that was created previously)

### What **IS** sent:
- ✅ `offerId` - This is the **only** field sent in the bulk_publish_offer request
- ✅ The offer (identified by `offerId`) already contains ALL listing details (title, price, description, pictures, category, condition, etc.)

### Why is it so simple?
The eBay Inventory API follows a **two-phase** listing process:
1. **Phase 1 (Already Done):** Create/Update the **Inventory Item** and **Offer** with ALL details (title, price, pictures, etc.)
2. **Phase 2 (This Request):** **Publish** the existing offer to make it live on eBay

So this `bulk_publish_offer` request is just saying:
> "Take offer #91234567890 (which already has all the details) and make it live on eBay marketplace"

---

## 🔍 For Your Smart Friend to Review

### Key Points to Verify:
1. ✅ **offerId Resolution:** Does the system correctly fetch offers by SKU before publishing?
2. ✅ **Headers:** Are all required headers present (Authorization, Content-Type, Accept)?
3. ✅ **Endpoint:** Is the correct eBay API endpoint being used (`/sell/inventory/v1/bulk_publish_offer`)?
4. ✅ **Environment:** Is the request going to the right environment (sandbox vs production)?
5. ✅ **Error Handling:** Does the system handle both HTTP-level errors and eBay business errors in the response?

### Actual Values for THIS Listing:
- **SKU:** `1000000000095909`
- **Title:** `Genuine HP 15-GB 15.6" Palmrest Touchpad w/ Keyboard zNZ9H000100 Read #Q353`
- **Price:** `$17.99 USD`
- **Quantity:** `1`
- **Condition:** `7000` (Used - check eBay condition ID mapping)
- **Category:** `119` (verify this is correct eBay category ID)
- **Pictures:** 4 images (first one: `https://i.frog.ink/xsujdkiqg33-j.jpg?v=a37df2df-3f96-4a14-bbb8-ddf722c34c2d`)
- **Shipping:** Flat rate, no international
- **Duration:** GTC (Good 'Til Cancelled)

---

## 🚀 Ready to Send?

Once your friend confirms everything looks good, click the **"LIST"** button in the UI to execute this request!

**The system will:**
1. Fetch the offerID for SKU `1000000000095909`
2. Send the `bulk_publish_offer` request to eBay
3. Update the database with the returned `listingId`
4. Show you the complete HTTP trace in the UI
