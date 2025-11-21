"""Registry of eBay Notification API topics used by the connector.

This module centralizes the list of topicIds we care about so that:
- Admin diagnostics can iterate over a stable set of topics.
- Subscription/test helpers do not hard-code topicIds in multiple places.
- Future order/fulfillment/finances topics can be added in a single place once
  eBay exposes them via the Commerce Notification API.

As of 2025-11-21, the public eBay Commerce Notification API documentation
(GET /commerce/notification/v1/topic and the getTopics operation) exposes a
small set of topics such as:
- MARKETPLACE_ACCOUNT_DELETION
- AUTHORIZATION_REVOCATION
- ITEM_AVAILABILITY
- ITEM_PRICE_REVISION
- PRIORITY_LISTING_REVISION
- PLA_CAMPAIGN_BUDGET_STATUS

There are currently **no documented order/fulfillment/finances topics** in that
API. Phase 1 therefore keeps MARKETPLACE_ACCOUNT_DELETION as the only concrete
configured topic, and provides empty placeholders for order/fulfillment/
finances topic sets so that they can be populated when eBay adds them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, List


@dataclass(frozen=True)
class NotificationTopicConfig:
    """Static configuration for a single Notification API topic.

    Attributes:
        topic_id: Exact topicId as used by the Notification API.
        default_entity_type: Our high-level entity label when events for this
            topic are ingested (e.g. "ORDER", "FINANCES_TRANSACTION"). May be
            None for purely account-level topics like MARKETPLACE_ACCOUNT_DELETION.
        category: Logical group: "account", "order", "fulfillment",
            "finances", "ads", etc. Used mainly for diagnostics/filters.
        scope_hint: Optional hint about expected scope ("APPLICATION" or
            "USER"). The authoritative scope is always read from the live
            /topic/{topicId} response; this field is purely documentary.
        doc_url: Link to the eBay documentation page that describes this topic.
    """

    topic_id: str
    default_entity_type: Optional[str]
    category: str
    scope_hint: Optional[str]
    doc_url: Optional[str]


# Primary webhook topic configured today.
#
# Scope: APPLICATION (per eBay docs). The subscription operations for this
# topic must use an application access token obtained via client_credentials.
PRIMARY_WEBHOOK_TOPIC_ID = "MARKETPLACE_ACCOUNT_DELETION"


SUPPORTED_TOPICS: List[NotificationTopicConfig] = [
    NotificationTopicConfig(
        topic_id=PRIMARY_WEBHOOK_TOPIC_ID,
        default_entity_type=None,
        category="account",
        scope_hint="APPLICATION",
        # Generic Notification API topic docs; this URL documents topic
        # metadata including `scope` and supported schema versions.
        doc_url="https://developer.ebay.com/api-docs/sell/notification/resources/topic/methods/getTopic",
    ),
    NotificationTopicConfig(
        topic_id="NEW_MESSAGE",
        default_entity_type="MESSAGE",
        category="messaging",
        # NEW_MESSAGE is a user-scoped topic used for message notifications.
        scope_hint="USER",
        doc_url="https://developer.ebay.com/api-docs/sell/notification/resources/topic/methods/getTopic",
    ),
]


# Placeholders for future order/fulfillment/finances topics
# ---------------------------------------------------------
#
# The Commerce Notification API does not yet expose canonical order-related
# topics as of 2025-11-21. When eBay introduces such topics, they should be
# added here and associated with appropriate entity types so that the
# ingestion pipeline can treat them similarly to our polling-based
# ORDER_UPDATED / FINANCES_TRANSACTION_UPDATED events.

ORDER_RELATED_TOPIC_IDS: set[str] = set()
"""Notification topics that should be treated as order/fulfillment events.

Once eBay publishes official order/fulfillment topics (for example topics that
carry one or more orderId values), their topicIds should be appended to this
set and documented in docs/ebay-notification-topics.md.
"""

FULFILLMENT_RELATED_TOPIC_IDS: set[str] = set()
"""Notification topics that reflect shipment / tracking / fulfillment updates.

Currently empty; populated when eBay exposes such topics.
"""

FINANCES_RELATED_TOPIC_IDS: set[str] = set()
"""Notification topics that map to sell.finances transactions or payouts.

Currently empty; populated when eBay exposes such topics.
"""
