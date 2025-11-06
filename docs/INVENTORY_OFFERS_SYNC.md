# Inventory & Offers Sync Implementation

**Last Updated:** 2025-11-06  
**Status:** ✅ Implemented - Ready for Testing

---

## Overview

This document describes the implementation of inventory and offers synchronization from eBay API to the database, following eBay API documentation requirements.

---

## eBay API Documentation References

### Inventory Items
- **Endpoint:** `GET /sell/inventory/v1/inventory_item`
- **Documentation:** https://developer.ebay.com/api-docs/sell/inventory/resources/inventory_item/methods/getInventoryItems
- **Parameters:**
  - `limit` (string, optional): 1-200, default 25
  - `offset` (string, optional): default 0
- **Response:** Paginated list of inventory items

### Offers
- **Endpoint:** `GET /sell/inventory/v1/offer`
- **Documentation:** https://developer.ebay.com/api-docs/sell/inventory/resources/offer/methods/getOffers
- **Parameters:**
  - `sku` (string, **REQUIRED**): The seller-defined SKU value
  - `limit` (string, optional): Max 200
  - `offset` (string, optional): default 0
  - `format` (string, optional): Listing format filter
  - `marketplace_id` (string, optional): Marketplace filter
- **Response:** Offers for the specified SKU

**Critical:** The `getOffers` endpoint **requires** a `sku` parameter. To get all offers, you must:
1. First get all inventory items (which contain SKUs)
2. Then call `getOffers` for each SKU

---

## Implementation Details

### 1. `fetch_inventory_items()` Method

**File:** `backend/app/services/ebay.py`

**Purpose:** Fetch inventory items from eBay API with pagination.

**Signature:**
```python
async def fetch_inventory_items(
    self, 
    access_token: str, 
    limit: int = 200, 
    offset: int = 0
) -> Dict[str, Any]
```

**Request:**
```
GET https://api.ebay.com/sell/inventory/v1/inventory_item?limit=200&offset=0
Headers:
  Authorization: Bearer {access_token}
  Content-Type: application/json
  X-EBAY-C-MARKETPLACE-ID: EBAY_US
```

**Response Structure:**
```json
{
  "inventoryItems": [
    {
      "sku": "string",
      "product": {
        "title": "string",
        "categoryId": "string",
        "aspects": {
          "Brand": "string",
          "Model": "string",
          "Part Number": "string"
        },
        "imageUrls": ["string"]
      },
      "condition": "NEW|USED_GOOD|...",
      "availability": {
        "shipToLocationAvailability": {
          "quantity": 0
        }
      },
      "pricingSummary": {
        "price": {
          "value": "string",
          "currency": "USD"
        }
      },
      "offers": [
        {
          "offerId": "string",
          "status": "PUBLISHED|ENDED|..."
        }
      ]
    }
  ],
  "total": 0,
  "href": "string",
  "next": "string",
  "limit": 0,
  "offset": 0
}
```

**Logging:**
- `ebay_logger.log_ebay_event("fetch_inventory_items_request", ...)`
- `ebay_logger.log_ebay_event("fetch_inventory_items_success", ...)`
- `ebay_logger.log_ebay_event("fetch_inventory_items_failed", ...)`

---

### 2. `fetch_offers()` Method (Fixed)

**File:** `backend/app/services/ebay.py`

**Purpose:** Fetch offers for a specific SKU from eBay API.

**Signature:**
```python
async def fetch_offers(
    self, 
    access_token: str, 
    sku: str,  # REQUIRED
    filter_params: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]
```

**Request:**
```
GET https://api.ebay.com/sell/inventory/v1/offer?sku={sku}&limit=200&offset=0
Headers:
  Authorization: Bearer {access_token}
  Content-Type: application/json
  X-EBAY-C-MARKETPLACE-ID: EBAY_US
```

**Parameters:**
- `sku` (required): The SKU to get offers for
- `limit` (optional): Max 200, default 200
- `offset` (optional): Default 0
- `format` (optional): Listing format filter
- `marketplace_id` (optional): Marketplace filter

**Response Structure:**
```json
{
  "offers": [
    {
      "offerId": "string",
      "listingId": "string",
      "sku": "string",
      "status": "PUBLISHED|ENDED|...",
      "price": {
        "value": "string",
        "currency": "USD"
      },
      "availableQuantity": 0,
      "creationDate": "string",
      "expirationDate": "string"
    }
  ],
  "total": 0,
  "href": "string",
  "next": "string",
  "limit": 0,
  "offset": 0
}
```

**Logging:**
- `ebay_logger.log_ebay_event("fetch_offers_request", ...)`
- `ebay_logger.log_ebay_event("fetch_offers_success", ...)`
- `ebay_logger.log_ebay_event("fetch_offers_failed", ...)`

---

### 3. `sync_all_offers()` Method (Rewritten)

**File:** `backend/app/services/ebay.py`

**Purpose:** Synchronize all offers from eBay to database.

**Flow:**
1. **Step 1:** Get all inventory items via `getInventoryItems` (paginated)
   - Extract SKUs from each inventory item
   - Continue until all pages are fetched
2. **Step 2:** For each SKU, call `getOffers`
   - Fetch offers for that SKU
   - Store offers in database
   - Continue with next SKU

**Signature:**
```python
async def sync_all_offers(
    self, 
    user_id: str, 
    access_token: str, 
    run_id: Optional[str] = None
) -> Dict[str, Any]
```

**Logging (visible in terminal via SSE):**
- `event_logger.log_start()` - Start message
- `event_logger.log_info()` - Step 1: Fetching inventory items
- `event_logger.log_info()` - Step 1 complete: Found X SKUs
- `event_logger.log_info()` - Step 2: Fetching offers for X SKUs
- `event_logger.log_info()` - Progress: [X/Y] Fetching offers for SKU: {sku}
- `event_logger.log_info()` - Response: SKU {sku}: X offers (Yms)
- `event_logger.log_done()` - Final summary with counts

**Cancellation Support:**
- Checks for cancellation before starting
- Checks for cancellation between inventory pages
- Checks for cancellation between SKU requests
- Checks for cancellation during offer storage

**Error Handling:**
- If a SKU fails, logs warning and continues with next SKU
- Final error logged if entire sync fails

---

### 4. `sync_all_inventory()` Method

**File:** `backend/app/services/ebay.py`

**Purpose:** Synchronize all inventory items from eBay to database with pagination.

**Flow:**
1. Fetch inventory items page by page (limit=200)
2. For each item, extract and store in database
3. Continue until all pages are fetched

**Signature:**
```python
async def sync_all_inventory(
    self, 
    user_id: str, 
    access_token: str, 
    run_id: Optional[str] = None
) -> Dict[str, Any]
```

**Logging (visible in terminal via SSE):**
- `event_logger.log_start()` - Start message
- `event_logger.log_info()` - Requesting page X: GET /sell/inventory/v1/inventory_item
- `event_logger.log_http_request()` - HTTP request details
- `event_logger.log_info()` - Response: 200 OK (Xms) - Received Y items
- `event_logger.log_info()` - Storing Y items in database
- `event_logger.log_info()` - Database: Stored Y items (Xms)
- `event_logger.log_progress()` - Page X/Y complete with running totals
- `event_logger.log_done()` - Final summary with counts

**Cancellation Support:**
- Checks for cancellation before starting
- Checks for cancellation between pages
- Checks for cancellation during item storage

---

### 5. `upsert_inventory_item()` Method

**File:** `backend/app/services/postgres_ebay_database.py`

**Purpose:** Insert or update an inventory item from eBay API into the inventory table.

**Data Mapping:**

| eBay API Field | Database Column | Notes |
|----------------|-----------------|-------|
| `sku` | `sku_code` | Unique key |
| `product.title` | `title` | |
| `condition` | `condition` | Mapped to ConditionType enum |
| `availability.shipToLocationAvailability.quantity` | `quantity` | |
| `pricingSummary.price.value` | `price_value` | |
| `pricingSummary.price.currency` | `price_currency` | |
| `product.categoryId` | `category` | |
| `product.aspects['Part Number']` | `part_number` | Or MPN, Brand Part Number |
| `product.aspects['Model']` | `model` | Or Model Number |
| `offers[0].offerId` | `ebay_listing_id` | First offer ID |
| `offers[].status` | `ebay_status` | ACTIVE if any PUBLISHED, else ENDED |
| `product.imageUrls.length` | `photo_count` | |
| Full `inventory_item_data` | `raw_payload` | JSONB |

**Condition Mapping:**
```python
{
    'NEW': 'NEW',
    'NEW_OTHER': 'NEW_OTHER',
    'NEW_WITH_DEFECTS': 'NEW_WITH_DEFECTS',
    'MANUFACTURER_REFURBISHED': 'MANUFACTURER_REFURBISHED',
    'SELLER_REFURBISHED': 'SELLER_REFURBISHED',
    'USED_EXCELLENT': 'USED_EXCELLENT',
    'USED_VERY_GOOD': 'USED_VERY_GOOD',
    'USED_GOOD': 'USED_GOOD',
    'USED_ACCEPTABLE': 'USED_ACCEPTABLE',
    'FOR_PARTS_OR_NOT_WORKING': 'FOR_PARTS_OR_NOT_WORKING'
}
```

**eBay Status Logic:**
- If any offer has status `PUBLISHED` or `PUBLISHED_IN_PROGRESS` → `ACTIVE`
- Otherwise → `ENDED`
- If no offers → `UNKNOWN`

**SQL:**
```sql
INSERT INTO inventory 
(sku_code, title, condition, part_number, model, category,
 price_value, price_currency, quantity, ebay_listing_id, ebay_status,
 photo_count, raw_payload, rec_created, rec_updated)
VALUES (...)
ON CONFLICT (sku_code) 
DO UPDATE SET
    title = EXCLUDED.title,
    condition = EXCLUDED.condition,
    ...
    rec_updated = EXCLUDED.rec_updated
```

**Note:** Currently uses `sku_code` as unique key. May need schema update for multi-user support (add `user_id`).

---

## API Endpoints

### POST /ebay/sync/inventory

**Purpose:** Start inventory synchronization.

**Request:**
```json
POST /ebay/sync/inventory
Headers:
  Authorization: Bearer {jwt_token}
```

**Response:**
```json
{
  "run_id": "inventory_1234567890_abc123",
  "status": "started",
  "message": "Inventory sync started in background"
}
```

**Background Task:**
- Calls `sync_all_inventory()` with user's access token
- Runs asynchronously
- Progress visible via SSE stream at `/ebay/sync/events/{run_id}`

---

### POST /ebay/sync/offers

**Purpose:** Start offers synchronization.

**Request:**
```json
POST /ebay/sync/offers
Headers:
  Authorization: Bearer {jwt_token}
```

**Response:**
```json
{
  "run_id": "offers_1234567890_abc123",
  "status": "started",
  "message": "Offers sync started in background"
}
```

**Background Task:**
- Calls `sync_all_offers()` with user's access token
- Runs asynchronously
- Progress visible via SSE stream at `/ebay/sync/events/{run_id}`

---

## Terminal Logging

All sync operations log to terminal via Server-Sent Events (SSE). Users will see:

### Inventory Sync Logs:
```
[HH:MM:SS] Starting Inventory sync from eBay (production)
[HH:MM:SS] API Configuration: Inventory API v1 - getInventoryItems with pagination
[HH:MM:SS] → Requesting page 1: GET /sell/inventory/v1/inventory_item?limit=200&offset=0
[HH:MM:SS] ← Response: 200 OK (123ms) - Received 50 items (Total available: 50)
[HH:MM:SS] → Storing 50 inventory items in database...
[HH:MM:SS] ← Database: Stored 50 items (45ms)
[HH:MM:SS] Page 1/1 complete: 50 fetched, 50 stored | Running total: 50/50 fetched, 50 stored
[HH:MM:SS] Inventory sync completed: 50 fetched, 50 stored in 234ms
```

### Offers Sync Logs:
```
[HH:MM:SS] Starting Offers sync from eBay (production)
[HH:MM:SS] API Configuration: Inventory API v1 - getInventoryItems → getOffers per SKU
[HH:MM:SS] Step 1: Fetching all inventory items to get SKU list...
[HH:MM:SS] → Fetching inventory items page 1: GET /sell/inventory/v1/inventory_item?limit=200&offset=0
[HH:MM:SS] ← Response: 200 OK (123ms) - Received 50 items, 50 SKUs (Total: 50)
[HH:MM:SS] ✓ Step 1 complete: Found 50 unique SKUs
[HH:MM:SS] Step 2: Fetching offers for 50 SKUs...
[HH:MM:SS] → [1/50] Fetching offers for SKU: SKU001
[HH:MM:SS] ← [1/50] SKU SKU001: 2 offers (45ms)
[HH:MM:SS] → [2/50] Fetching offers for SKU: SKU002
[HH:MM:SS] ← [2/50] SKU SKU002: 1 offers (42ms)
...
[HH:MM:SS] ✓ Step 2 complete: Processed 50 SKUs
[HH:MM:SS] Offers sync completed: 75 offers fetched, 75 stored from 50 SKUs in 3456ms
```

---

## Testing Checklist

### Inventory Sync
- [ ] POST /ebay/sync/inventory returns run_id
- [ ] Terminal shows inventory sync progress
- [ ] All inventory items fetched with pagination
- [ ] Data correctly stored in inventory table
- [ ] STOP button works during sync
- [ ] "Fetched: X, Stored: Y" shows correct numbers

### Offers Sync
- [ ] POST /ebay/sync/offers returns run_id
- [ ] Terminal shows Step 1: Fetching inventory items
- [ ] Terminal shows Step 2: Fetching offers for each SKU
- [ ] All offers fetched and stored
- [ ] STOP button works during sync
- [ ] "Fetched: X, Stored: Y" shows correct numbers

### Data Verification
- [ ] Inventory table contains all items with correct fields
- [ ] Offers table contains all offers
- [ ] raw_payload contains full eBay API response
- [ ] sku_code is unique and correct
- [ ] price_value and price_currency are correct
- [ ] quantity matches eBay data
- [ ] ebay_status (ACTIVE/ENDED) is correct

---

## Known Limitations

1. **No user_id in inventory table:** Currently uses `sku_code` as unique key. If multiple users have same SKU, there will be conflicts. May need schema update.

2. **No incremental sync:** Always syncs all data. Future enhancement: use `ebay_sync_cursors` table to track last sync position.

3. **Rate limiting:** Small delays (0.2-0.8s) between requests to avoid rate limits. May need adjustment based on actual usage.

4. **Error handling:** If one SKU fails in offers sync, continues with next SKU. Failed SKUs are logged but not retried automatically.

---

## Future Enhancements

1. **Incremental Sync:** Use `ebay_sync_cursors` table to track last sync position and only fetch new/updated items.

2. **Bulk Operations:** Use `bulkGetInventoryItem` for fetching multiple SKUs at once (up to 25 at a time).

3. **Feed API Integration:** Use Feed API for large-scale inventory reports (Active Inventory Report).

4. **Multi-user Support:** Add `user_id` to inventory table for proper multi-account support.

5. **Retry Logic:** Automatic retry for failed SKU requests with exponential backoff.

---

## Related Files

- `backend/app/services/ebay.py` - Main service methods
- `backend/app/services/postgres_ebay_database.py` - Database operations
- `backend/app/routers/ebay.py` - API endpoints
- `backend/app/services/sync_event_logger.py` - Logging infrastructure
- `backend/app/models_sqlalchemy/models.py` - Inventory table model

---

## References

- eBay Inventory API: https://developer.ebay.com/api-docs/sell/inventory/overview.html
- getInventoryItems: https://developer.ebay.com/api-docs/sell/inventory/resources/inventory_item/methods/getInventoryItems
- getOffers: https://developer.ebay.com/api-docs/sell/inventory/resources/offer/methods/getOffers


