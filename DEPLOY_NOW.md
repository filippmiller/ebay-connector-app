# Deploy Normalized Backend - 2 Minute Guide

## Quick Steps

### 1. Navigate and Deploy
```bash
cd /home/ubuntu/ebay-connector-app/backend
flyctl auth login
flyctl deploy --app app-qngipkhc
```

### 2. Wait for Deployment
- Takes ~2-3 minutes
- Watch for "✓ Deployment successful"
- Migration runs automatically

### 3. Re-sync Orders
1. Open: https://ebay-connection-app-k0ge3h93.devinapps.com/admin
2. Login: filippmiller@gmail.com / TestPass123!
3. Click "Sync Orders"
4. Wait ~30 seconds

### 4. Verify Normalization
Go to: https://ebay-connection-app-k0ge3h93.devinapps.com/orders

You should see:
✅ Real dates (e.g., "2024-10-15 14:30")
✅ Payment status (PAID/FAILED)
✅ Fulfillment status (FULFILLED/IN_PROGRESS)
✅ Line item counts (e.g., "3 items")
✅ Tracking numbers
✅ Shipping addresses
