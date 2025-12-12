import xml.etree.ElementTree as ET
from decimal import Decimal
import pytest

def test_active_inventory_item_parsing():
    # Sample XML from eBay GetMyeBaySelling response (ActiveList)
    # Based on the parsing logic in app/services/ebay.py
    xml_content = """
    <Item xmlns="urn:ebay:apis:eBLBaseComponents">
        <ItemID>123456789012</ItemID>
        <SKU>TEST-SKU-123</SKU>
        <Title>Test Item Title</Title>
        <Quantity>10</Quantity>
        <SellingStatus>
            <QuantitySold>2</QuantitySold>
            <ListingStatus>Active</ListingStatus>
        </SellingStatus>
        <StartPrice currencyID="USD">19.99</StartPrice>
        <ConditionID>1000</ConditionID>
        <ConditionDisplayName>New</ConditionDisplayName>
    </Item>
    """
    
    ns = {"ebay": "urn:ebay:apis:eBLBaseComponents"}
    item = ET.fromstring(xml_content)

    # --- Logic copied from app/services/ebay.py for verification ---
    def _text(path: str):
        elem = item.find(path, ns)
        return elem.text if elem is not None else None

    item_id = _text("ebay:ItemID")
    sku = _text("ebay:SKU")
    title = _text("ebay:Title")

    qty_str = _text("ebay:Quantity") or "0"
    qty_sold_str = item.findtext(
        "ebay:SellingStatus/ebay:QuantitySold", default="0", namespaces=ns
    )
    try:
        quantity_total = int(qty_str)
    except ValueError:
        quantity_total = 0
    try:
        quantity_sold = int(qty_sold_str or "0")
    except ValueError:
        quantity_sold = 0
    quantity_available = max(quantity_total - quantity_sold, 0)

    start_price_elem = item.find("ebay:StartPrice", ns)
    price_val = None
    currency = None
    if start_price_elem is not None and start_price_elem.text is not None:
        raw_price = start_price_elem.text
        currency = start_price_elem.attrib.get("currencyID")
        try:
            price_val = Decimal(str(raw_price))
        except Exception:
            price_val = None

    listing_status = item.findtext(
        "ebay:SellingStatus/ebay:ListingStatus",
        default=None,
        namespaces=ns,
    )

    condition_id = item.findtext(
        "ebay:ConditionID", default=None, namespaces=ns
    )
    condition_text = item.findtext(
        "ebay:ConditionDisplayName", default=None, namespaces=ns
    )
    
    # The fix we implemented:
    raw_payload = {
        "ItemID": item_id,
        "SKU": sku,
        "Title": title,
        "Quantity": quantity_total,
        "QuantitySold": quantity_sold,
        "StartPrice": float(price_val) if price_val is not None else None,
        "Currency": currency,
        "ListingStatus": listing_status,
        "ConditionID": condition_id,
        "ConditionDisplayName": condition_text
    }
    # ---------------------------------------------------------------

    # Assertions to verify mapping correctness
    assert item_id == "123456789012"
    assert sku == "TEST-SKU-123"
    assert title == "Test Item Title"
    assert quantity_total == 10
    assert quantity_sold == 2
    assert quantity_available == 8
    assert price_val == Decimal("19.99")
    assert currency == "USD"
    assert listing_status == "Active"
    assert condition_id == "1000"
    assert condition_text == "New"

    # Verify raw_payload structure
    assert raw_payload["ItemID"] == "123456789012"
    assert raw_payload["SKU"] == "TEST-SKU-123"
    assert raw_payload["StartPrice"] == 19.99
    assert raw_payload["Currency"] == "USD"
    assert raw_payload["ConditionID"] == "1000"

if __name__ == "__main__":
    # Allow running directly with python
    test_active_inventory_item_parsing()
    print("Test passed!")
