from app.routers.shipping_bulk import RateLineRequest, PurchaseSelection, _default_from_address


def test_rate_line_request_quantity_defaults():
    req = RateLineRequest(
        orderId="o1",
        orderLineItemId="l1",
        inventoryId=1,
        weightOz=10.0,
        quantity=0,
    )
    assert req.quantity == 1


def test_purchase_selection_quantity_normalized():
    sel = PurchaseSelection(
        orderId="o1",
        orderLineItemId="l1",
        inventoryId=1,
        carrierCode="USPS",
        serviceCode="USPS_PRIORITY",
        serviceName="Priority Mail",
        amount=8.5,
        weightOz=10.0,
        quantity=0,
    )
    assert sel.quantity == 1


def test_default_from_address_shape():
    addr = _default_from_address()
    assert isinstance(addr, dict)
    assert "countryCode" in addr





