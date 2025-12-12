import json
from decimal import Decimal

import pytest

from app.services.postgres_ebay_database import PostgresEbayDatabase


class _DummySession:
    def __init__(self) -> None:
        self.last_query = None
        self.last_params = None

    def execute(self, query, params=None):  # pragma: no cover - trivial plumbing
        self.last_query = query
        self.last_params = dict(params or {})

    def commit(self):  # pragma: no cover - trivial plumbing
        return None

    def rollback(self):  # pragma: no cover - trivial plumbing
        return None

    def close(self):  # pragma: no cover - trivial plumbing
        return None


class _TestablePostgresEbayDatabase(PostgresEbayDatabase):
    """Subclass that injects a dummy Session so we can inspect SQL params.

    This avoids the need for a real Postgres instance while still exercising the
    real mapping logic in ``upsert_return``.
    """

    def __init__(self) -> None:
        # Do not call super().__init__ – the base class does not define one and
        # we do not want to touch real DB state.
        self._dummy_session = _DummySession()

    def _get_session(self):  # type: ignore[override]
        return self._dummy_session


@pytest.fixture
def sample_return_payload() -> dict:
    """Merged summary+detail payload mirroring the prompt example."""

    return {
        "summary": {
            "returnId": "5305512242",
            "orderId": "26-13721-98548",
            "buyerLoginName": "jl3717",
            "sellerLoginName": "mil_243",
            "currentType": "MONEY_BACK",
            "state": "ITEM_READY_TO_SHIP",
            "creationInfo": {
                "item": {
                    "itemId": "396222604727",
                    "transactionId": "10075571665126",
                    "returnQuantity": 1,
                },
                "type": "MONEY_BACK",
                "reason": "DEFECTIVE_ITEM",
                "reasonType": "SNAD",
                "comments": {"content": "Item arrived with iCloud "},
                "creationDate": {"value": "2025-11-12T21:40:55.000Z"},
            },
            "sellerTotalRefund": {
                "estimatedRefundAmount": {"value": 143.99, "currency": "USD"}
            },
            "buyerTotalRefund": {
                "estimatedRefundAmount": {"value": 155.87, "currency": "USD"}
            },
            "sellerResponseDue": {
                "activityDue": "SELLER_APPROVE_REQUEST",
                "respondByDate": {"value": "2025-12-04T07:59:59.000Z"},
            },
            "buyerResponseDue": {
                "activityDue": "NOTIFIED_SHIPPED",
                "respondByDate": {"value": "2025-11-27T07:59:59.000Z"},
            },
            "timeoutDate": {"value": "2025-12-18T07:59:59.999Z"},
        },
        "detail": {
            "marketplaceId": "EBAY_US",
            "itemDetail": {
                "itemId": "396222604727",
                "transactionId": "10075571665126",
                "itemTitle": 'Apple Macbook Air 13" A2337 2020 M1 Logic Board...',
                "transactionDate": {"value": "2025-10-24T19:53:45.000Z"},
                "itemPrice": {"value": 143.99, "currency": "USD"},
            },
            "buyerLoginName": "jl3717",
            "sellerLoginName": "mil_243",
            "responseHistory": [
                {
                    "author": "BUYER",
                    "activity": "BUYER_CREATE_RETURN",
                    "fromState": "INITIAL",
                    "toState": "RETURN_REQUESTED",
                    "creationDate": {"value": "2025-11-12T21:40:55.000Z"},
                    "notes": "Item arrived with iCloud ",
                    "attributes": {
                        "sellerReturnAddress": {
                            "name": "Miller Sells It LLC",
                            "address": {
                                "addressLine1": "32 Power Dam Way",
                                "addressLine2": "Ste 112",
                                "city": "Plattsburgh",
                                "stateOrProvince": "NY",
                                "postalCode": "12901-3792",
                                "country": "US",
                            },
                        },
                        "sellerRefundWindow": 2,
                    },
                }
            ],
            "returnShipmentInfo": {
                "shipmentTracking": {
                    "shipmentId": "510735175010",
                    "shippingMethod": "SHIPPING_LABEL",
                    "shippedBy": "BUYER",
                    "trackingNumber": "9302010584700053503681",
                    "carrierEnum": "USPS",
                    "carrierName": "USPS",
                    "deliveryStatus": "UNKNOWN",
                    "labelDate": {"value": "2025-11-12T21:40:58.000Z"},
                },
                "shippingLabelCost": {
                    "totalAmount": {"value": 5.24, "currency": "USD"}
                },
                "shipByDate": {"value": "2025-12-04T08:00:00.001Z"},
            },
            "files": [
                {
                    "fileId": "5275229378",
                    "fileName": "ebayiOSUpload.jpg",
                    "filePurpose": "ITEM_RELATED",
                    "fileStatus": "PUBLISHED",
                    "submitter": "BUYER",
                    "fileFormat": "JPEG",
                    "creationDate": {"value": "2025-11-12T21:40:53.000Z"},
                }
            ],
            "closeInfo": {
                "returnCloseReason": "OTHER",
                "buyerCloseReason": "UNKNOWN",
            },
            "returnContentOnHold": False,
        },
    }


@pytest.mark.parametrize("explicit_return_id", [None, "5305512242"])
def test_upsert_return_mapping_merged_payload(explicit_return_id, sample_return_payload):
    db = _TestablePostgresEbayDatabase()

    user_id = "user-123"
    ebay_account_id = "acc-456"
    # Worker currently passes account.ebay_user_id as ebay_user_id; mapping
    # should override it with seller login from payload.
    worker_ebay_user_id = "account-login"

    ok = db.upsert_return(
        user_id=user_id,
        return_data=sample_return_payload,
        ebay_account_id=ebay_account_id,
        ebay_user_id=worker_ebay_user_id,
        return_id=explicit_return_id,
    )

    assert ok is True
    params = db._dummy_session.last_params  # type: ignore[attr-defined]
    assert params is not None

    # Core identifiers
    assert params["return_id"] == "5305512242"
    assert params["order_id"] == "26-13721-98548"
    assert params["item_id"] == "396222604727"
    assert params["transaction_id"] == "10075571665126"

    # Actors & account linkage
    assert params["buyer_username"] == "jl3717"
    assert params["seller_username"] == "mil_243"
    # ebay_user_id should be the seller login from payload, not the worker arg.
    assert params["ebay_user_id"] == "mil_243"
    assert params["ebay_account_id"] == ebay_account_id
    assert params["user_id"] == user_id

    # Type & state
    assert params["return_type"] == "MONEY_BACK"
    assert params["return_state"] == "ITEM_READY_TO_SHIP"

    # Reason string: "SNAD:DEFECTIVE_ITEM"
    assert isinstance(params["reason"], str)
    assert "SNAD" in params["reason"]
    assert "DEFECTIVE_ITEM" in params["reason"]

    # Money: sellerTotalRefund wins
    assert isinstance(params["total_amount_value"], (Decimal, float, int))
    assert float(params["total_amount_value"]) == pytest.approx(143.99)
    assert params["total_amount_currency"] == "USD"

    # Dates – just assert they were parsed into datetimes, not exact values.
    assert params["creation_date"] is not None
    assert params["last_modified_date"] is not None
    # Sample payload has no explicit close timestamp, so closed_date should be None.
    assert params["closed_date"] is None

    # Raw JSON should contain the full merged payload and include nested keys
    # like returnShipmentInfo for future auditing.
    raw_json = params["raw_json"]
    assert isinstance(raw_json, str)
    assert "returnShipmentInfo" in raw_json
    # Sanity check: it should be valid JSON.
    decoded = json.loads(raw_json)
    assert "summary" in decoded and "detail" in decoded
