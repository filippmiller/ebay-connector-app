# eBay History Logging Architecture

## Overview

We use a centralized `ebay_events` table to log all historical changes and events for eBay resources. This allows us to track the history of mutable resources like Orders, Returns, Cases, etc., even when the main resource table is updated in-place.

## Architecture

The system consists of:
1.  **`ebay_events` Table**: The central log table.
2.  **Workers/Services**: Responsible for fetching data from eBay and upserting it into the database.
3.  **`log_ebay_event` Helper**: A utility function in `app.services.ebay_event_inbox` to standardize logging.

### `ebay_events` Schema

The `ebay_events` table contains:
-   `event_time`: Timestamp of the event (from eBay).
-   `topic`: Event topic (e.g., `ORDER_UPDATED`, `RETURN_UPDATED`).
-   `entity_type`: Type of the entity (e.g., `ORDER`, `RETURN`).
-   `entity_id`: ID of the entity (e.g., Order ID, Return ID).
-   `payload`: Full JSON payload of the event/resource at that point in time.
-   `ebay_account`: The eBay account associated with the event.

### Usage

When a worker fetches a resource (e.g., a Return), it should:
1.  Upsert the current state into the specific table (e.g., `ebay_returns`).
2.  Log the event to `ebay_events` using `log_ebay_event`.

This ensures that `ebay_returns` always has the latest state for quick access, while `ebay_events` preserves the full history.

## Coverage

The following resources are currently covered:

| Resource | Worker | Logged? | Notes |
| :--- | :--- | :--- | :--- |
| **Orders** | `orders_worker` | ✅ Yes | Logged in `batch_upsert_orders` |
| **Disputes** | `cases_worker` | ✅ Yes | Logged in `upsert_dispute` |
| **Inquiries** | `inquiries_worker` | ✅ Yes | Logged in `upsert_inquiry` |
| **Cases** | `cases_worker` | ✅ Yes | Logged in `upsert_case` |
| **Returns** | `returns_worker` | ✅ Yes | Logged in `upsert_return` |
| **Finances** | `finances_worker` | ✅ Yes | Logged in `upsert_finances_transaction` |
| **Offers** | `offers_worker` | ✅ Yes | Logged in `upsert_offer` |
| **Transactions** | `transactions_worker` | ✅ Yes | Logged in `upsert_transaction` |
| **Messages** | `messages_worker` | ✅ Yes | Logged in `sync_all_messages` |
| **Inventory** | `active_inventory_worker` | ✅ Yes | Logged in `upsert_inventory_item` |
| **Purchases** | `purchases_worker` | ✅ Yes | Logged in `purchases_worker` |

## Querying History

To view the history of a specific resource (e.g., a Return), query the `ebay_events` table:

```sql
SELECT event_time, topic, payload
FROM ebay_events
WHERE entity_type = 'RETURN'
  AND entity_id = '5000123456'
ORDER BY event_time DESC;
```

This will return all recorded states of the return, allowing you to see how it changed over time.
