import pytest
from app.services.ebay_offers_service import ebay_offers_service

def test_snapshot_signature_determinism():
    data1 = {
        "pricingSummary.price.value": "10.00",
        "availableQuantity": 5,
        "status": "PUBLISHED"
    }
    data2 = {
        "status": "PUBLISHED",
        "availableQuantity": 5,
        "pricingSummary.price.value": "10.00"
    }
    
    sig1 = ebay_offers_service._compute_snapshot_signature(data1)
    sig2 = ebay_offers_service._compute_snapshot_signature(data2)
    
    assert sig1 == sig2
    assert len(sig1) == 64 # SHA-256 hex digest length

def test_changed_fields_diff():
    old = {"a": 1, "b": 2}
    new = {"a": 1, "b": 3}
    
    diff = ebay_offers_service._compute_changed_fields(old, new)
    assert diff == {"b": {"old": 2, "new": 3}}
    
    diff_none = ebay_offers_service._compute_changed_fields(old, old)
    assert diff_none is None

def test_event_type_classification():
    # Price change
    diff_price = {"pricingSummary.price.value": {"old": "10.00", "new": "12.00"}}
    assert ebay_offers_service._determine_event_type(diff_price, False) == "price_change"
    
    # Qty change
    diff_qty = {"availableQuantity": {"old": 5, "new": 0}}
    assert ebay_offers_service._determine_event_type(diff_qty, False) == "qty_change"
    
    # Status change
    diff_status = {"status": {"old": "PUBLISHED", "new": "UNPUBLISHED"}}
    assert ebay_offers_service._determine_event_type(diff_status, False) == "status_change"
    
    # New offer
    assert ebay_offers_service._determine_event_type({}, True) == "created"

def test_interesting_fields_extraction():
    payload = {
        "offerId": "123",
        "sku": "ABC",
        "pricingSummary": {
            "price": {
                "value": "19.99",
                "currency": "USD"
            }
        },
        "availableQuantity": 10,
        "status": "PUBLISHED",
        "listing": {
            "listingStatus": "ACTIVE"
        }
    }
    
    fields = ebay_offers_service._get_interesting_fields(payload)
    assert fields["pricingSummary.price.value"] == "19.99"
    assert fields["pricingSummary.price.currency"] == "USD"
    assert fields["availableQuantity"] == 10
    assert fields["status"] == "PUBLISHED"
    assert fields["listing.listingStatus"] == "ACTIVE"
    assert fields.get("quantityLimitPerBuyer") is None
