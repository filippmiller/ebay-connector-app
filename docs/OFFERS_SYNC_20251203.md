# eBay Offers Sync and History Subsystem

**Date:** 2025-12-03
**Status:** Implemented

## Overview

This subsystem implements a robust sync and history logging mechanism for eBay Inventory Offers. It allows tracking changes to offers (price, quantity, status, policies) over time, providing a timeline view of updates.

## Database Schema

Two new tables have been added:

### 1. `ebay_inventory_offers` (Current State)
Stores the latest known state of each eBay Inventory Offer.

- `id` (PK): UUID
- `ebay_account_id`: FK to `ebay_accounts.id`
- `offer_id`: eBay Offer ID
- `sku`: SKU
- `status`: Offer status (PUBLISHED, UNPUBLISHED)
- `listing_status`: Listing status (ACTIVE, ENDED)
- `price_value`, `price_currency`: Current price
- `available_quantity`: Current available quantity
- `sold_quantity`: Quantity sold
- `raw_payload`: Full JSON payload from eBay
- `created_at`, `updated_at`

### 2. `ebay_inventory_offer_events` (History Log)
Append-only log of meaningful changes.

- `id` (PK): UUID
- `ebay_account_id`, `offer_id`, `sku`
- `event_type`: `created`, `price_change`, `qty_change`, `status_change`, `policy_change`, `snapshot`
- `snapshot_signature`: SHA-256 hash of "interesting fields" for deduplication
- `changed_fields`: JSON diff of old vs new values
- `snapshot_payload`: Full JSON payload at this version
- `source`: `inventory.getOffers`
- `fetched_at`: Timestamp of fetch

## Logic

### Snapshot Signature & Diffing
To avoid storing duplicate history entries when nothing has changed, we compute a `snapshot_signature`:
1. Extract "interesting fields" (price, qty, status, policies, dates).
2. Serialize to a deterministic JSON string.
3. Compute SHA-256 hash.

When syncing:
- If `snapshot_signature` matches the last known state (or rather, if no fields changed), we only update `ebay_inventory_offers.updated_at`.
- If fields changed, we insert a new row into `ebay_inventory_offer_events` and update `ebay_inventory_offers`.

### Event Types
- `created`: First time seeing the offer.
- `price_change`: Price value or currency changed.
- `qty_change`: Available quantity changed.
- `status_change`: Offer or listing status changed.
- `policy_change`: Listing policies or tax info changed.
- `snapshot`: Other changes.

## API Endpoints

### Internal Admin Sync
`POST /api/admin/internal/sync-offers`
- Headers: `INTERNAL_API_KEY: <key>`
- Body: `{"account_id": "optional-uuid", "limit_per_run": 100}`
- Triggers the sync process for one or all active accounts.

### Offer History
`GET /api/inventory-offers/{offer_id}/history`
- Query Params: `account_id` (optional), `limit` (default 50)
- Returns list of history events ordered by `fetched_at` descending.

## Worker Integration

The existing worker scheduler (Cloudflare/Railway) should be configured to call `POST /api/admin/internal/sync-offers` periodically (e.g., every 30-60 minutes).

## Testing

Unit tests should verify:
- Deterministic snapshot signature calculation.
- Correct diff generation.
- Event type classification.

Integration tests should verify:
- Database inserts/updates.
- Idempotency (running sync twice with same data produces no new events).
