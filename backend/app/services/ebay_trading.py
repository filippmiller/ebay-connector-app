from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

import httpx
from fastapi import HTTPException, status

from app.config import settings


NS = {"e": "urn:ebay:apis:eBLBaseComponents"}


def _mask_headers(headers: Dict[str, Any]) -> Dict[str, Any]:
    masked: Dict[str, Any] = {}
    for k, v in (headers or {}).items():
        lk = str(k).lower()
        if lk in {"authorization", "x-ebay-api-iaf-token"} or "token" in lk:
            masked[k] = "***"
        else:
            masked[k] = v
    return masked


def _xml_text(val: Any) -> str:
    return escape("" if val is None else str(val))


def _xml_cdata(val: Any) -> str:
    # CDATA cannot contain "]]>" safely; split if needed.
    s = "" if val is None else str(val)
    return "<![CDATA[" + s.replace("]]>", "]]]]><![CDATA[>") + "]]>"


def trading_endpoint() -> str:
    base = settings.ebay_api_base_url.rstrip("/")
    return f"{base}/ws/api.dll"


@dataclass
class TradingHttpResult:
    request_url: str
    request_headers_masked: Dict[str, Any]
    request_body_xml: str
    response_status: int
    response_headers: Dict[str, Any]
    response_body_xml: str
    duration_ms: int


def build_verify_add_fixed_price_item_xml(*, item_xml: str) -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<VerifyAddFixedPriceItemRequest xmlns="urn:ebay:apis:eBLBaseComponents">'
        "<ErrorLanguage>en_US</ErrorLanguage>"
        "<WarningLevel>High</WarningLevel>"
        f"{item_xml}"
        "</VerifyAddFixedPriceItemRequest>"
    )


def build_add_fixed_price_item_xml(*, item_xml: str) -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<AddFixedPriceItemRequest xmlns="urn:ebay:apis:eBLBaseComponents">'
        "<ErrorLanguage>en_US</ErrorLanguage>"
        "<WarningLevel>High</WarningLevel>"
        f"{item_xml}"
        "</AddFixedPriceItemRequest>"
    )


def build_item_xml(
    *,
    title: str,
    description_html: str,
    category_id: str,
    start_price: str,
    quantity: int,
    currency: str,
    country: str,
    location: str,
    postal_code: str,
    dispatch_time_max: int,
    condition_id: str,
    site: str,
    listing_duration: str,
    picture_urls: list[str],
    # Item specifics (common required aspects)
    brand: str,
    mpn: str,
    # Policies mode
    policies_mode: str,  # "seller_profiles" | "manual"
    # SellerProfiles IDs (preferred)
    shipping_profile_id: Optional[int] = None,
    payment_profile_id: Optional[int] = None,
    return_profile_id: Optional[int] = None,
    # Manual fallback (minimal)
    shipping_service: Optional[str] = None,
    shipping_cost: Optional[str] = None,
    returns_accepted_option: Optional[str] = None,
    returns_within_option: Optional[str] = None,
    refund_option: Optional[str] = None,
    shipping_cost_paid_by_option: Optional[str] = None,
    payment_methods: Optional[list[str]] = None,
    paypal_email_address: Optional[str] = None,
) -> str:
    pics = "".join(f"<PictureURL>{_xml_text(u)}</PictureURL>" for u in picture_urls if (u or "").strip())
    if not pics:
        pics = ""

    specifics = (
        "<ItemSpecifics>"
        f"<NameValueList><Name>Brand</Name><Value>{_xml_text(brand)}</Value></NameValueList>"
        f"<NameValueList><Name>MPN</Name><Value>{_xml_text(mpn)}</Value></NameValueList>"
        "</ItemSpecifics>"
    )

    seller_profiles_xml = ""
    manual_policies_xml = ""

    mode = (policies_mode or "seller_profiles").strip().lower()
    if mode == "seller_profiles":
        seller_profiles_xml = (
            "<SellerProfiles>"
            f"<SellerShippingProfile><ShippingProfileID>{int(shipping_profile_id or 0)}</ShippingProfileID></SellerShippingProfile>"
            f"<SellerReturnProfile><ReturnProfileID>{int(return_profile_id or 0)}</ReturnProfileID></SellerReturnProfile>"
            f"<SellerPaymentProfile><PaymentProfileID>{int(payment_profile_id or 0)}</PaymentProfileID></SellerPaymentProfile>"
            "</SellerProfiles>"
        )
    else:
        # Minimal manual fallback (domestic shipping + return policy; payment methods optional and account-dependent)
        ship_cost = shipping_cost if shipping_cost is not None else "0.0"
        ship_service = shipping_service or "USPSGroundAdvantage"
        manual_policies_xml = (
            "<ShippingDetails>"
            "<ShippingServiceOptions>"
            f"<ShippingService>{_xml_text(ship_service)}</ShippingService>"
            f'<ShippingServiceCost currencyID="{_xml_text(currency)}">{_xml_text(ship_cost)}</ShippingServiceCost>'
            "</ShippingServiceOptions>"
            "</ShippingDetails>"
            "<ReturnPolicy>"
            f"<ReturnsAcceptedOption>{_xml_text(returns_accepted_option or 'ReturnsAccepted')}</ReturnsAcceptedOption>"
            f"<ReturnsWithinOption>{_xml_text(returns_within_option or 'Days_30')}</ReturnsWithinOption>"
            f"<RefundOption>{_xml_text(refund_option or 'MoneyBack')}</RefundOption>"
            f"<ShippingCostPaidByOption>{_xml_text(shipping_cost_paid_by_option or 'Seller')}</ShippingCostPaidByOption>"
            "</ReturnPolicy>"
        )
        if payment_methods:
            manual_policies_xml += "".join(f"<PaymentMethods>{_xml_text(m)}</PaymentMethods>" for m in payment_methods)
        if paypal_email_address:
            manual_policies_xml += f"<PayPalEmailAddress>{_xml_text(paypal_email_address)}</PayPalEmailAddress>"

    return (
        "<Item>"
        f"<Title>{_xml_text(title)[:80]}</Title>"
        f"<Description>{_xml_cdata(description_html)}</Description>"
        f"<PrimaryCategory><CategoryID>{_xml_text(category_id)}</CategoryID></PrimaryCategory>"
        "<ListingType>FixedPriceItem</ListingType>"
        f"<ListingDuration>{_xml_text(listing_duration)}</ListingDuration>"
        f'<StartPrice currencyID="{_xml_text(currency)}">{_xml_text(start_price)}</StartPrice>'
        f"<Quantity>{int(quantity)}</Quantity>"
        f"<Currency>{_xml_text(currency)}</Currency>"
        f"<Country>{_xml_text(country)}</Country>"
        f"<Location>{_xml_text(location)}</Location>"
        f"<PostalCode>{_xml_text(postal_code)}</PostalCode>"
        f"<DispatchTimeMax>{int(dispatch_time_max)}</DispatchTimeMax>"
        f"<ConditionID>{_xml_text(condition_id)}</ConditionID>"
        f"<Site>{_xml_text(site)}</Site>"
        f"{specifics}"
        (f"<PictureDetails>{pics}</PictureDetails>" if pics else "")
        f"{seller_profiles_xml}"
        f"{manual_policies_xml}"
        "</Item>"
    )


async def call_trading_api(
    *,
    call_name: str,
    iaf_token: str,
    site_id: int,
    compatibility_level: int,
    request_xml: str,
) -> TradingHttpResult:
    if not iaf_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing_iaf_token")

    url = trading_endpoint()
    headers: Dict[str, Any] = {
        "X-EBAY-API-CALL-NAME": call_name,
        "X-EBAY-API-SITEID": str(site_id),
        "X-EBAY-API-COMPATIBILITY-LEVEL": str(compatibility_level),
        "X-EBAY-API-IAF-TOKEN": iaf_token,
        "Content-Type": "text/xml; charset=utf-8",
        "Accept": "text/xml",
    }

    start = time.time()
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
        try:
            resp = await client.post(url, headers=headers, content=request_xml.encode("utf-8"))
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"trading_http_error: {exc}",
            )

    duration_ms = int((time.time() - start) * 1000)
    body_text = resp.text or ""

    return TradingHttpResult(
        request_url=url,
        request_headers_masked=_mask_headers(headers),
        request_body_xml=request_xml,
        response_status=resp.status_code,
        response_headers=dict(resp.headers),
        response_body_xml=body_text,
        duration_ms=duration_ms,
    )


def parse_trading_response(xml_text: str) -> Dict[str, Any]:
    """Parse Trading API response XML into a compact summary."""
    out: Dict[str, Any] = {
        "ack": None,
        "item_id": None,
        "errors": [],
        "warnings": [],
        "fees": [],
    }
    if not xml_text:
        return out

    try:
        root = ET.fromstring(xml_text)
    except Exception:
        out["parse_error"] = "invalid_xml"
        return out

    ack = root.findtext(".//e:Ack", default=None, namespaces=NS)
    out["ack"] = ack

    item_id = root.findtext(".//e:ItemID", default=None, namespaces=NS)
    if item_id:
        out["item_id"] = item_id

    for err in root.findall(".//e:Errors", namespaces=NS):
        entry = {
            "code": err.findtext("e:ErrorCode", default=None, namespaces=NS),
            "severity": err.findtext("e:SeverityCode", default=None, namespaces=NS),
            "short": err.findtext("e:ShortMessage", default=None, namespaces=NS),
            "long": err.findtext("e:LongMessage", default=None, namespaces=NS),
            "classification": err.findtext("e:ErrorClassification", default=None, namespaces=NS),
        }
        if entry.get("severity") == "Warning":
            out["warnings"].append(entry)
        else:
            out["errors"].append(entry)

    for fee in root.findall(".//e:Fees/e:Fee", namespaces=NS):
        name = fee.findtext("e:Name", default=None, namespaces=NS)
        amount = None
        fee_amount = fee.find("e:Fee", namespaces=NS)
        if fee_amount is not None:
            amount = fee_amount.text
        out["fees"].append({"name": name, "amount": amount})

    return out


