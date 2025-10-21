# Deploy eBay Data Normalization - Quick Guide

## What's Ready
✅ Complete normalization code implemented
✅ Database migration for new columns and line_items table
✅ Batch upsert optimized for 1,811+ orders
✅ All code committed to: feature/database-and-ui-pages branch

## Deploy Steps (5 minutes)

### 1. Deploy Backend
```bash
cd /home/ubuntu/ebay-connector-app/backend
flyctl auth login
flyctl deploy --app app-qngipkhc
```

The deployment will:
- Run migration to add raw_payload column
- Create order_line_items table
- Add normalized columns (tracking, shipping address, etc.)

### 2. Verify Deployment
Check logs:
```bash
flyctl logs --app app-qngipkhc
```

Look for:
- "Running database migrations..."
- "Application startup complete"

### 3. Re-sync All Orders
1. Go to: https://ebay-connection-app-k0ge3h93.devinapps.com
2. Login with filippmiller@gmail.com
3. Go to Admin section
4. Click "Sync Orders" button
5. Wait ~30 seconds for 1,811 orders to sync

### 4. Verify Normalization
Go to Orders page and verify you see:
- ✅ Real creation dates (not "N/A")
- ✅ Payment status (PAID, FAILED, etc. not "UNKNOWN")
- ✅ Fulfillment status (FULFILLED, etc.)
- ✅ Line item counts (e.g., "3 items" not "0 items")
- ✅ Tracking numbers displayed
- ✅ Shipping addresses (city, state, postal code)

## What Changed

### Database Schema
New columns in `ebay_orders`:
- `raw_payload` JSONB - stores complete eBay response
- `order_total_value` NUMERIC
- `order_total_currency` CHAR(3)
- `line_items_count` INT
- `buyer_registered` BOOLEAN
- `tracking_number` TEXT
- `ship_to_name`, `ship_to_city`, `ship_to_state`, `ship_to_postal_code`, `ship_to_country_code`

New table `order_line_items`:
- Links to orders via foreign key
- Stores SKU, title, quantity, price per line item
- Has its own raw_payload for each item

### Code Changes
- `normalize_order()` function extracts all eBay fields correctly
- `batch_upsert_orders()` uses normalization
- `batch_upsert_line_items()` handles line items separately
- Proper datetime parsing (ISO 8601 to UTC)
- Money parsing (value + currency)
- Safe nested field extraction

## Troubleshooting

### Migration Fails
If migration fails, check:
```bash
flyctl ssh console --app app-qngipkhc
cd /app && poetry run alembic current
```

### Orders Not Syncing
Check backend logs:
```bash
flyctl logs --app app-qngipkhc --tail
```

### Still Seeing "N/A" or "UNKNOWN"
- Make sure you re-synced AFTER deployment
- Old data won't auto-update, only re-sync updates it

## Next Steps After Deployment
1. Verify all 1,811 orders show correct data
2. Test filtering by payment status
3. Test searching by tracking number
4. Check line items are stored in database
5. (Optional) Update UI to show line items per order
