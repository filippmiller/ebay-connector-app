# eBay Notification topics used by the connector

This document records which eBay Commerce Notification API topics are
configured in the connector and how they are intended to be used.

## 1. Background

The backend talks to the **Commerce Notification API** at
`/commerce/notification/v1`. Topic metadata is retrieved via:

- `GET /commerce/notification/v1/topic/{topicId}`
- `GET /commerce/notification/v1/topic` (getTopics)

As of 2025-11-21, the public documentation and topic listing expose a small
set of topics, including:

- `MARKETPLACE_ACCOUNT_DELETION`
- `AUTHORIZATION_REVOCATION`
- `ITEM_AVAILABILITY`
- `ITEM_PRICE_REVISION`
- `PRIORITY_LISTING_REVISION`
- `PLA_CAMPAIGN_BUDGET_STATUS`

No **order/fulfillment/payment/finances**-related topics are documented in
this API at the time of writing.

> Reference: see the Commerce Notification API topic resources and getTopics
> operation in the official eBay Sell API docs.

## 2. Topics configured in Phase 1

In Phase 1 of the Notifications Center, the connector configures and manages
the following concrete topics:

- `MARKETPLACE_ACCOUNT_DELETION`
  - Scope: `APPLICATION` (application-scoped topic; subscriptions and tests
    must use an application access token obtained via client_credentials).
  - Purpose: receive account-deletion events for connected seller accounts.
  - Webhook: `POST /webhooks/ebay/events`.

- `NEW_MESSAGE`
  - Scope: `USER` (user-scoped topic; subscriptions and tests use the seller's
    user access token).
  - Purpose: receive notifications about new messages in the seller's inbox.
  - Webhook: `POST /webhooks/ebay/events`.
  - Notes: the webhook currently logs these events into `ebay_events` with
    `entity_type="MESSAGE"` and `entity_id` set to the best-effort message or
    thread identifier. A later Messages UI will consume these events.

The topic registry is implemented in
`backend/app/services/ebay_notification_topics.py` and is consumed by the
admin diagnostics endpoints.

## 3. Order / fulfillment / finances topics

The product spec for the Notifications Center anticipates that we will be able
to subscribe to **order / fulfillment / payment** events via the Notification
API and use those events to drive the same ingestion logic as our polling
workers.

However, based on the current official Commerce Notification API
documentation (topic listing and individual topic docs), there are **no
published topicIds for orders, fulfillments, or finances transactions** yet.

Because of this, Phase 1 deliberately keeps the order/fulfillment/finances
notification topic sets **empty**:

- `ORDER_RELATED_TOPIC_IDS` – empty `set[str]`.
- `FULFILLMENT_RELATED_TOPIC_IDS` – empty `set[str]`.
- `FINANCES_RELATED_TOPIC_IDS` – empty `set[str]`.

These are defined in `backend/app/services/ebay_notification_topics.py` and
used by the ingestion scaffolding. Once eBay exposes official topics for these
areas, they should be added there with pointers back to the relevant eBay
documentation pages.

## 4. How to add future order/fulfillment/finances topics

When eBay introduces new Notification API topics for orders, fulfillments or
payments:

1. **Locate the official docs**
   - Identify the exact `topicId` string and its `scope` (APPLICATION or
     USER) from the `GET /commerce/notification/v1/topic/{topicId}` response.
   - Note which IDs are present in the notification payload
     (e.g. `orderId`, `lineItemId`, `transactionId`).

2. **Update the registry module**
   - Edit `backend/app/services/ebay_notification_topics.py` and append a new
     `NotificationTopicConfig` entry to `SUPPORTED_TOPICS` with:
     - `topic_id`
     - `default_entity_type` such as `"ORDER"` or
       `"FINANCES_TRANSACTION"`.
     - `category` (e.g. `"order"`, `"fulfillment"`, `"finances"`).
     - `scope_hint` set to the documented `scope`.
     - `doc_url` pointing at the eBay topic documentation page.
   - Add the new `topic_id` to one of the sets:
     - `ORDER_RELATED_TOPIC_IDS`
     - `FULFILLMENT_RELATED_TOPIC_IDS`
     - `FINANCES_RELATED_TOPIC_IDS`

3. **Extend the ingestion mapping (if needed)**
   - Update the ingestion helper (e.g.
     `backend/app/services/ebay_event_processor.py`) so that when an
     `ebay_events` row has this `topic` it:
     - Extracts the relevant IDs from the payload.
     - Calls the appropriate REST API:
       - Orders/shipments → `GET /sell/fulfillment/v1/order/{orderId}`.
       - Payments → `GET /sell/finances/v1/transaction?transaction_id={id}`
         (or the canonical lookup path from the docs).
     - Feeds the resulting JSON into the existing ingestion services:
       `PostgresEbayDatabase.batch_upsert_orders`,
       `upsert_finances_transaction`, etc.

4. **Verify via admin UI**
   - Use the Notifications Center (Admin → “eBay Notifications Center”) to:
     - Ensure the new topic shows up under Diagnostics → Topics.
     - Run a test for the new topic using the generic
       `/api/admin/notifications/test-topic` endpoint.
     - Confirm that any resulting events appear in `ebay_events` and, once
       the ingestion mapping is in place, that orders/transactions are
       upserted into the existing tables.

By centralizing topic configuration and documenting the current limitations,
we can safely evolve the Notifications Center from the current
`MARKETPLACE_ACCOUNT_DELETION`-only setup to full order/fulfillment/finances
coverage as eBay expands the Commerce Notification API.
