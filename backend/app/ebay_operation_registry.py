from __future__ import annotations

"""Central registry of eBay API operations.

This module is the single source of truth for:
- operation identifiers (logical names)
- API family and category
- HTTP method and relative path
- required OAuth scopes (names only, no secrets)
- minimal info about required path/query/body parameters

The goal is to gradually route all eBay HTTP calls through this registry so we
avoid duplicating magic strings (paths, scopes, etc.) across routers/services
and the interactive debugger.

NOTE: this is intentionally conservative for now – we only register operations
we already use in the codebase (identity + fulfillment + inventory). Post-Order
and Trading XML operations can be added later using the same pattern.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional, TypedDict


EbayApiFamily = Literal["REST_IDENTITY", "REST_SELL", "REST_POSTORDER", "TRADING_XML"]
EbayCategory = Literal[
    "identity",
    "orders",
    "disputes",
    "cases",
    "selling",
    "shipping",
    "messages",
]


class RequiredParamSpec(TypedDict, total=False):
    """Specification for a single required parameter.

    For now we keep it minimal – name + human description. In future we can
    extend with type information, enums, grouping rules (AT_LEAST_ONE_OF_GROUP,
    etc.) as suggested in the design document.
    """

    name: str
    description: str


@dataclass(frozen=True)
class EbayOperationSpec:
    """Specification of a single logical eBay operation."""

    id: str
    family: EbayApiFamily
    category: EbayCategory
    http_method: Literal["GET", "POST", "PUT", "DELETE", "PATCH"]
    # Relative path, without base URL. May contain ``{placeholders}`` for
    # path parameters.
    path: str
    # Names of OAuth scopes that are acceptable for this operation.
    oauth_scopes: List[str] = field(default_factory=list)
    # Header names that MUST be present (values are assembled by builder).
    required_headers: List[str] = field(default_factory=list)
    # Required path/query/body parameters. We intentionally only capture the
    # name + human-readable description for now.
    required_path_params: List[RequiredParamSpec] = field(default_factory=list)
    required_query_params: List[RequiredParamSpec] = field(default_factory=list)
    required_body_fields: List[RequiredParamSpec] = field(default_factory=list)


# ---- Operation IDs -------------------------------------------------------

IDENTITY_GET_USER = "IDENTITY_GET_USER"
FULFILLMENT_GET_ORDERS = "FULFILLMENT_GET_ORDERS"
FULFILLMENT_GET_ORDER = "FULFILLMENT_GET_ORDER"
FULFILLMENT_GET_PAYMENT_DISPUTE_SUMMARIES = "FULFILLMENT_GET_PAYMENT_DISPUTE_SUMMARIES"
FULFILLMENT_GET_PAYMENT_DISPUTE = "FULFILLMENT_GET_PAYMENT_DISPUTE"
FULFILLMENT_GET_SHIPPING_FULFILLMENTS = "FULFILLMENT_GET_SHIPPING_FULFILLMENTS"
INVENTORY_GET_ITEMS = "INVENTORY_GET_ITEMS"
INVENTORY_GET_ITEM = "INVENTORY_GET_ITEM"


_REGISTRY: Dict[str, EbayOperationSpec] = {
    # 1) Identity API ------------------------------------------------------
    IDENTITY_GET_USER: EbayOperationSpec(
        id=IDENTITY_GET_USER,
        family="REST_IDENTITY",
        category="identity",
        http_method="GET",
        path="/identity/v1/oauth2/userinfo",
        oauth_scopes=[
            # In practice any seller scope is enough; we list the base scope
            # for documentation purposes.
            "https://api.ebay.com/oauth/api_scope",
        ],
        required_headers=["Authorization", "Accept"],
    ),

    # 2) Fulfillment API – Orders -----------------------------------------
    FULFILLMENT_GET_ORDERS: EbayOperationSpec(
        id=FULFILLMENT_GET_ORDERS,
        family="REST_SELL",
        category="orders",
        http_method="GET",
        path="/sell/fulfillment/v1/order",
        oauth_scopes=[
            "https://api.ebay.com/oauth/api_scope/sell.fulfillment",
            "https://api.ebay.com/oauth/api_scope/sell.fulfillment.readonly",
        ],
        required_headers=["Authorization", "Accept"],
        required_query_params=[
            {
                "name": "limit",
                "description": "Maximum number of orders per page (1-200).",
            },
        ],
    ),
    FULFILLMENT_GET_ORDER: EbayOperationSpec(
        id=FULFILLMENT_GET_ORDER,
        family="REST_SELL",
        category="orders",
        http_method="GET",
        path="/sell/fulfillment/v1/order/{orderId}",
        oauth_scopes=[
            "https://api.ebay.com/oauth/api_scope/sell.fulfillment",
            "https://api.ebay.com/oauth/api_scope/sell.fulfillment.readonly",
        ],
        required_headers=["Authorization", "Accept"],
        required_path_params=[
            {
                "name": "orderId",
                "description": "Fulfillment orderId (not legacyOrderId).",
            }
        ],
    ),

    # 3) Fulfillment API – Payment Disputes --------------------------------
    FULFILLMENT_GET_PAYMENT_DISPUTE_SUMMARIES: EbayOperationSpec(
        id=FULFILLMENT_GET_PAYMENT_DISPUTE_SUMMARIES,
        family="REST_SELL",
        category="disputes",
        http_method="GET",
        path="/sell/fulfillment/v1/payment_dispute_summary",
        oauth_scopes=["https://api.ebay.com/oauth/api_scope/sell.payment.dispute"],
        required_headers=["Authorization", "Accept"],
    ),
    FULFILLMENT_GET_PAYMENT_DISPUTE: EbayOperationSpec(
        id=FULFILLMENT_GET_PAYMENT_DISPUTE,
        family="REST_SELL",
        category="disputes",
        http_method="GET",
        path="/sell/fulfillment/v1/payment_dispute/{payment_dispute_id}",
        oauth_scopes=["https://api.ebay.com/oauth/api_scope/sell.payment.dispute"],
        required_headers=["Authorization", "Accept"],
        required_path_params=[
            {
                "name": "payment_dispute_id",
                "description": "Identifier returned by getPaymentDisputeSummaries.",
            }
        ],
    ),

    # 4) Fulfillment API – Shipping Fulfillments ---------------------------
    FULFILLMENT_GET_SHIPPING_FULFILLMENTS: EbayOperationSpec(
        id=FULFILLMENT_GET_SHIPPING_FULFILLMENTS,
        family="REST_SELL",
        category="shipping",
        http_method="GET",
        path="/sell/fulfillment/v1/order/{orderId}/shipping_fulfillment",
        oauth_scopes=[
            "https://api.ebay.com/oauth/api_scope/sell.fulfillment",
            "https://api.ebay.com/oauth/api_scope/sell.fulfillment.readonly",
        ],
        required_headers=["Authorization", "Accept"],
        required_path_params=[{"name": "orderId", "description": "Fulfillment order id."}],
    ),

    # 5) Inventory API – selling / listings --------------------------------
    INVENTORY_GET_ITEMS: EbayOperationSpec(
        id=INVENTORY_GET_ITEMS,
        family="REST_SELL",
        category="selling",
        http_method="GET",
        path="/sell/inventory/v1/inventory_item",
        oauth_scopes=["https://api.ebay.com/oauth/api_scope/sell.inventory"],
        required_headers=["Authorization", "Accept"],
    ),
    INVENTORY_GET_ITEM: EbayOperationSpec(
        id=INVENTORY_GET_ITEM,
        family="REST_SELL",
        category="selling",
        http_method="GET",
        path="/sell/inventory/v1/inventory_item/{sku}",
        oauth_scopes=["https://api.ebay.com/oauth/api_scope/sell.inventory"],
        required_headers=["Authorization", "Accept"],
        required_path_params=[{"name": "sku", "description": "Seller SKU."}],
    ),
}


def get_operation_spec(op_id: str) -> EbayOperationSpec:
    """Return the spec for the given operation id.

    Raises ``KeyError`` if the id is unknown. We keep the error type simple so
    callers can decide how to surface it (HTTP 400, internal error, etc.).
    """

    return _REGISTRY[op_id]
