from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.models.user import User
from app.models_sqlalchemy import get_db
from app.services.auth import admin_required
from app.services.ebay_listing_service import _resolve_account_and_token
from app.services.ebay_trading import (
    build_add_fixed_price_item_xml,
    build_item_xml,
    build_verify_add_fixed_price_item_xml,
    call_trading_api,
    parse_trading_response,
)
from app.utils.logger import logger


router = APIRouter(prefix="/api/admin/ebay/bin", tags=["admin-ebay-bin-listing"])


SITE_ID_TO_CODE = {
    0: "US",
}


class GlobalSiteDto(BaseModel):
    site_id: int
    global_id: Optional[str] = None
    site_name: Optional[str] = None
    territory: Optional[str] = None
    language: Optional[str] = None
    active: bool = True


class BinDebugRequest(BaseModel):
    legacy_inventory_id: int = Field(..., ge=1, description="Legacy tbl_parts_inventory.ID")

    # Policies mode: keep canonical SellerProfiles, but allow manual fallback.
    policies_mode: str = Field(
        "seller_profiles",
        description="seller_profiles (canonical) or manual (fallback)",
    )

    # Business Policies (SellerProfiles) – preferred strategy
    shipping_profile_id: Optional[int] = Field(None, ge=1)
    payment_profile_id: Optional[int] = Field(None, ge=1)
    return_profile_id: Optional[int] = Field(None, ge=1)

    # Manual fallback (minimal). Used when policies_mode=manual.
    shipping_service: Optional[str] = None
    shipping_cost: Optional[str] = None
    returns_accepted_option: Optional[str] = None
    returns_within_option: Optional[str] = None
    refund_option: Optional[str] = None
    shipping_cost_paid_by_option: Optional[str] = None
    payment_methods: Optional[list[str]] = None
    paypal_email_address: Optional[str] = None

    # Item specifics (minimum)
    brand: Optional[str] = Field(None, description="ItemSpecifics Brand (defaults to Unbranded)")
    mpn: Optional[str] = Field(None, description="ItemSpecifics MPN (defaults to tbl_parts_detail.MPN/Part_Number or Does Not Apply)")

    # Listing + site settings
    site_id: int = Field(0, description="Trading API SiteID header value (default US=0)")
    site_code: str = Field("US", description="Item.Site two-letter code (must match site_id)")
    compatibility_level: int = Field(1311, description="X-EBAY-API-COMPATIBILITY-LEVEL")

    listing_duration: str = Field("GTC", description="Item.ListingDuration")
    currency: str = Field("USD", description="Item.Currency and StartPrice currencyID")

    # Location / handling
    country: str = Field("US", description="Item.Country")
    location: str = Field(..., min_length=1, description="Item.Location (city/state)")
    postal_code: str = Field(..., min_length=3, description="Item.PostalCode")
    dispatch_time_max: int = Field(1, ge=0, le=30, description="Item.DispatchTimeMax")


class BinDebugResponse(BaseModel):
    mode: str  # VERIFY | LIST
    legacy_inventory_id: int
    sku: str
    parts_detail_id: Optional[int]
    meta: Dict[str, Any] = Field(default_factory=dict)
    request_url: str
    request_headers_masked: Dict[str, Any]
    request_body_xml: str
    response_http_status: int
    response_headers: Dict[str, Any]
    response_body_xml: str
    parsed: Dict[str, Any]
    log_saved: bool = False
    log_error: Optional[str] = None
    run_id: Optional[int] = None
    item_id_saved_to_parts_detail: bool = False
    item_id_saved_to_map: bool = False


class BinSourcePreview(BaseModel):
    legacy_inventory_id: int
    sku: str
    parts_detail_id: Optional[int]
    # DB-derived core fields
    title: Optional[str]
    description: Optional[str]
    category_id: Optional[str]
    start_price: Optional[str]
    quantity: Optional[int]
    condition_id: Optional[str]
    condition_display_name: Optional[str] = None
    condition_row: Optional[Dict[str, Any]] = None
    picture_urls: list[str]
    missing_db_fields: list[str]


@router.get("/site-ids", response_model=list[GlobalSiteDto], dependencies=[Depends(admin_required)])
async def list_global_site_ids(
    active_only: bool = Query(True),
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required),  # noqa: ARG001
) -> list[GlobalSiteDto]:
    """
    Source of truth for Trading API SiteID selection.
    Backed by public.tbl_globalsiteid (legacy dictionary).
    """
    rows = db.execute(
        text(
            """
            SELECT "SiteID", "GlobalID", "SiteName", "Territory", "Language", COALESCE("Active", TRUE) AS active
            FROM public.tbl_globalsiteid
            WHERE (:active_only = FALSE OR COALESCE("Active", TRUE) = TRUE)
            ORDER BY ("SiteID"::int) ASC
            """
        ),
        {"active_only": active_only},
    ).mappings().all()

    out: list[GlobalSiteDto] = []
    for r in rows:
        try:
            sid = int(str(r.get("SiteID") or "").strip())
        except Exception:
            continue
        out.append(
            GlobalSiteDto(
                site_id=sid,
                global_id=r.get("GlobalID"),
                site_name=r.get("SiteName"),
                territory=r.get("Territory"),
                language=r.get("Language"),
                active=bool(r.get("active")),
            )
        )
    return out


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _first_non_empty(*vals: Any) -> Optional[str]:
    for v in vals:
        if v is None:
            continue
        s = str(v).strip()
        if not s or s.lower() == "null":
            continue
        return s
    return None


def _load_legacy_inventory(db: Session, legacy_inventory_id: int) -> dict:
    row = db.execute(
        text('SELECT * FROM public."tbl_parts_inventory" WHERE "ID" = :id'),
        {"id": legacy_inventory_id},
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="legacy_inventory_not_found")
    return dict(row)


def _load_tbl_parts_detail_by_sku(db: Session, sku: str) -> dict:
    row = db.execute(
        text('SELECT * FROM public."tbl_parts_detail" WHERE "SKU" = :sku ORDER BY "ID" DESC LIMIT 1'),
        {"sku": int(float(sku))},
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="tbl_parts_detail_not_found_for_sku")
    return dict(row)


def _load_condition_meta(db: Session, condition_id: Optional[str]) -> tuple[Optional[str], Optional[Dict[str, Any]]]:
    if not condition_id:
        return None, None
    try:
        cid = int(float(condition_id))
    except Exception:
        return None, None
    row = db.execute(
        text('SELECT * FROM public.tbl_parts_condition WHERE "ConditionID" = :cid LIMIT 1'),
        {"cid": cid},
    ).mappings().first()
    if not row:
        return None, None
    d = dict(row)
    return (d.get("ConditionDisplayName"), d)


def _resolve_parts_detail_id(db: Session, sku: str) -> Optional[int]:
    inv2 = db.execute(
        text("SELECT parts_detail_id FROM public.inventory WHERE sku_code = :sku ORDER BY id ASC LIMIT 1"),
        {"sku": sku},
    ).first()
    if inv2 and inv2[0] is not None:
        try:
            return int(inv2[0])
        except Exception:
            return None
    # fallback to parts_detail table match
    row = db.execute(
        text(
            "SELECT id FROM public.parts_detail WHERE sku = :sku OR override_sku = :sku ORDER BY id DESC LIMIT 1"
        ),
        {"sku": sku},
    ).first()
    if row and row[0] is not None:
        try:
            return int(row[0])
        except Exception:
            return None
    return None


def _precheck_missing(fields: Dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for k, v in fields.items():
        if v is None:
            missing.append(k)
            continue
        if isinstance(v, str) and not v.strip():
            missing.append(k)
            continue
        if isinstance(v, (list, tuple)) and len(v) == 0:
            missing.append(k)
            continue
    return missing


def _extract_pictures(legacy_inv: dict, tbl_parts_detail: dict) -> list[str]:
    pics: list[str] = []
    for i in range(1, 13):
        val = _first_non_empty(
            legacy_inv.get(f"OverridePicURL{i}"),
            tbl_parts_detail.get(f"PicURL{i}"),
        )
        if val:
            pics.append(val)
    # Dedup while preserving order
    seen = set()
    out: list[str] = []
    for p in pics:
        if p in seen:
            continue
        seen.add(p)
        out.append(p)
    return out


@router.get("/source", response_model=BinSourcePreview, dependencies=[Depends(admin_required)])
async def get_bin_source_preview(
    legacy_inventory_id: int = Query(..., ge=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required),  # noqa: ARG001
) -> BinSourcePreview:
    """Return DB-derived fields used for BIN Trading API mapping (no eBay calls)."""
    legacy_inv = _load_legacy_inventory(db, legacy_inventory_id)
    sku = _first_non_empty(legacy_inv.get("SKU"))
    if not sku:
        raise HTTPException(status_code=400, detail="legacy_inventory_missing_sku")

    tbl_pd = _load_tbl_parts_detail_by_sku(db, sku)
    parts_detail_id = _resolve_parts_detail_id(db, sku)

    title = _first_non_empty(legacy_inv.get("OverrideTitle"), tbl_pd.get("Part"))
    # Description can live in multiple legacy SKU fields; prefer OverrideDescription, then Description, then ConditionDescription.
    description = _first_non_empty(
        legacy_inv.get("OverrideDescription"),
        tbl_pd.get("Description"),
        tbl_pd.get("CustomTemplateDescription"),
        tbl_pd.get("ConditionDescription"),
    )
    category_id = _first_non_empty(tbl_pd.get("Category"))
    start_price = _first_non_empty(legacy_inv.get("OverridePrice"), tbl_pd.get("Price"))
    qty_raw = legacy_inv.get("Quantity")
    quantity = int(qty_raw) if qty_raw is not None else None
    condition_id = _first_non_empty(legacy_inv.get("OverrideConditionID"), tbl_pd.get("ConditionID"))
    condition_display_name, condition_row = _load_condition_meta(db, condition_id)
    pics = _extract_pictures(legacy_inv, tbl_pd)

    missing_db_fields = _precheck_missing(
        {
            "title": title,
            "description": description,
            "category_id": category_id,
            "start_price": start_price,
            "quantity": quantity if (quantity or 0) > 0 else None,
            "condition_id": condition_id,
            "picture_urls": pics,
        }
    )

    return BinSourcePreview(
        legacy_inventory_id=legacy_inventory_id,
        sku=str(sku),
        parts_detail_id=parts_detail_id,
        title=title,
        description=description,
        category_id=category_id,
        start_price=start_price,
        quantity=quantity,
        condition_id=condition_id,
        condition_display_name=condition_display_name,
        condition_row=condition_row,
        picture_urls=pics,
        missing_db_fields=missing_db_fields,
    )


async def _call_trading(
    *,
    mode: str,
    call_name: str,
    req: BinDebugRequest,
    db: Session,
    current_user: User,
) -> BinDebugResponse:
    # Validate site_code/site_id consistency
    expected = SITE_ID_TO_CODE.get(req.site_id)
    if expected and expected.upper() != req.site_code.strip().upper():
        raise HTTPException(
            status_code=400,
            detail=f"site_mismatch: site_id={req.site_id} expects Item.Site={expected}",
        )

    legacy_inv = _load_legacy_inventory(db, req.legacy_inventory_id)
    sku = _first_non_empty(legacy_inv.get("SKU"))
    if not sku:
        raise HTTPException(status_code=400, detail="legacy_inventory_missing_sku")

    tbl_pd = _load_tbl_parts_detail_by_sku(db, sku)
    parts_detail_id = _resolve_parts_detail_id(db, sku)

    # DB → eBay mapping (tbl_parts_detail is source of truth, legacy inventory provides Quantity and overrides)
    title = _first_non_empty(legacy_inv.get("OverrideTitle"), tbl_pd.get("Part"))
    description = _first_non_empty(
        legacy_inv.get("OverrideDescription"),
        tbl_pd.get("Description"),
        tbl_pd.get("CustomTemplateDescription"),
        tbl_pd.get("ConditionDescription"),
    )
    category_id = _first_non_empty(tbl_pd.get("Category"))
    start_price = _first_non_empty(legacy_inv.get("OverridePrice"), tbl_pd.get("Price"))
    qty_raw = legacy_inv.get("Quantity")
    quantity = int(qty_raw) if qty_raw is not None else 0
    condition_id = _first_non_empty(legacy_inv.get("OverrideConditionID"), tbl_pd.get("ConditionID"))
    condition_display_name, _ = _load_condition_meta(db, condition_id)
    pics = _extract_pictures(legacy_inv, tbl_pd)

    # Item specifics (minimum). No Brand column in tbl_parts_detail in this environment.
    brand = (req.brand or "").strip() or "Unbranded"
    mpn = (req.mpn or "").strip() or _first_non_empty(tbl_pd.get("MPN"), tbl_pd.get("Part_Number")) or "Does Not Apply"

    # Description fallback template (do it now; empty Description is a common hard failure)
    if not description or not str(description).strip():
        cond_txt = condition_display_name or str(condition_id or "").strip() or "Unknown condition"
        description = (
            f"<p><b>{_first_non_empty(title) or 'Item'}</b></p>"
            f"<p><b>Condition:</b> {cond_txt} (ConditionID {condition_id})</p>"
            f"<p><b>SKU:</b> {sku}</p>"
            "<p>See photos for the exact item.</p>"
            "<p><b>Included:</b> Item as pictured only.</p>"
            "<p><b>Not included:</b> Accessories unless shown.</p>"
        )

    precheck = {
        "Item.Title": title,
        "Item.Description": description,
        "Item.PrimaryCategory.CategoryID": category_id,
        "Item.ListingType": "FixedPriceItem",
        "Item.ListingDuration": req.listing_duration,
        "Item.StartPrice": start_price,
        "Item.Quantity": quantity if quantity > 0 else None,
        "Item.Currency": req.currency,
        "Item.Country": req.country,
        "Item.Location": req.location,
        "Item.PostalCode": req.postal_code,
        "Item.DispatchTimeMax": req.dispatch_time_max,
        "Item.PictureDetails.PictureURL[]": pics,
        "Item.ConditionID": condition_id,
        "Item.Site": req.site_code,
        "ItemSpecifics.Brand": brand,
        "ItemSpecifics.MPN": mpn,
    }
    mode = (req.policies_mode or "seller_profiles").strip().lower()
    if mode == "seller_profiles":
        precheck["Item.SellerProfiles.PaymentProfileID"] = req.payment_profile_id
        precheck["Item.SellerProfiles.ReturnProfileID"] = req.return_profile_id
        precheck["Item.SellerProfiles.ShippingProfileID"] = req.shipping_profile_id
    else:
        precheck["Item.ShippingDetails.ShippingService"] = req.shipping_service or "USPSGroundAdvantage"
        precheck["Item.ReturnPolicy.ReturnsAcceptedOption"] = req.returns_accepted_option or "ReturnsAccepted"
        precheck["Item.ReturnPolicy.ReturnsWithinOption"] = req.returns_within_option or "Days_30"
        precheck["Item.ReturnPolicy.RefundOption"] = req.refund_option or "MoneyBack"
        precheck["Item.ReturnPolicy.ShippingCostPaidByOption"] = req.shipping_cost_paid_by_option or "Seller"

    missing = _precheck_missing(precheck)
    if missing:
        raise HTTPException(
            status_code=400,
            detail={"message": "precheck_missing_fields", "missing": missing},
        )

    # Resolve eBay account token for Trading (OAuth header)
    # We use the same mapping as worker: username + ebay_id from parts_detail if available, else error.
    pd_row = None
    if parts_detail_id is not None:
        pd_row = db.execute(
            text("SELECT username, ebay_id FROM public.parts_detail WHERE id = :id"),
            {"id": parts_detail_id},
        ).mappings().first()
    if not pd_row:
        raise HTTPException(status_code=400, detail="parts_detail_account_not_resolved")

    username = (pd_row.get("username") or "").strip()
    ebay_id = (pd_row.get("ebay_id") or "").strip()
    account, token, err = _resolve_account_and_token(db, username, ebay_id)
    if err or not token:
        raise HTTPException(status_code=400, detail=err or "missing_oauth_token")

    item_xml = build_item_xml(
        title=str(title),
        description_html=str(description),
        category_id=str(category_id),
        start_price=str(start_price),
        quantity=int(quantity),
        currency=req.currency,
        country=req.country,
        location=req.location,
        postal_code=req.postal_code,
        dispatch_time_max=req.dispatch_time_max,
        condition_id=str(condition_id),
        site=req.site_code,
        listing_duration=req.listing_duration,
        picture_urls=pics,
        brand=brand,
        mpn=mpn,
        policies_mode=mode,
        shipping_profile_id=req.shipping_profile_id,
        payment_profile_id=req.payment_profile_id,
        return_profile_id=req.return_profile_id,
        shipping_service=req.shipping_service,
        shipping_cost=req.shipping_cost,
        returns_accepted_option=req.returns_accepted_option,
        returns_within_option=req.returns_within_option,
        refund_option=req.refund_option,
        shipping_cost_paid_by_option=req.shipping_cost_paid_by_option,
        payment_methods=req.payment_methods,
        paypal_email_address=req.paypal_email_address,
    )

    request_xml = (
        build_verify_add_fixed_price_item_xml(item_xml=item_xml)
        if call_name == "VerifyAddFixedPriceItem"
        else build_add_fixed_price_item_xml(item_xml=item_xml)
    )

    http_res = await call_trading_api(
        call_name=call_name,
        iaf_token=token,
        site_id=req.site_id,
        compatibility_level=req.compatibility_level,
        request_xml=request_xml,
    )

    parsed = parse_trading_response(http_res.response_body_xml)

    # Logging into ebay_bin_test_runs. We return explicit status so UI can warn if logging failed.
    log_saved = False
    log_error: Optional[str] = None
    run_id: Optional[int] = None
    try:
        row = db.execute(
            text(
                """
                INSERT INTO public.ebay_bin_test_runs
                (created_at, user_id, legacy_inventory_id, parts_detail_id, sku, mode,
                 request_url, request_headers_masked, request_body_xml,
                 response_http_status, response_headers, response_body_xml,
                 parsed_ack, parsed_errors, parsed_warnings, item_id)
                VALUES
                (:created_at, :user_id, :legacy_inventory_id, :parts_detail_id, :sku, :mode,
                 :request_url, :request_headers_masked::jsonb, :request_body_xml,
                 :response_http_status, :response_headers::jsonb, :response_body_xml,
                 :parsed_ack, :parsed_errors::jsonb, :parsed_warnings::jsonb, :item_id)
                RETURNING id
                """
            ),
            {
                "created_at": _now(),
                "user_id": getattr(current_user, "id", None),
                "legacy_inventory_id": req.legacy_inventory_id,
                "parts_detail_id": parts_detail_id,
                "sku": sku,
                "mode": mode,
                "request_url": http_res.request_url,
                "request_headers_masked": http_res.request_headers_masked,
                "request_body_xml": http_res.request_body_xml,
                "response_http_status": http_res.response_status,
                "response_headers": http_res.response_headers,
                "response_body_xml": http_res.response_body_xml,
                "parsed_ack": parsed.get("ack"),
                "parsed_errors": parsed.get("errors") or [],
                "parsed_warnings": parsed.get("warnings") or [],
                "item_id": parsed.get("item_id"),
            },
        )
        db.commit()
        log_saved = True
        try:
            run_id = int(row.scalar() or 0) or None
        except Exception:
            run_id = None
    except Exception as exc:
        db.rollback()
        log_error = str(exc)
        logger.warning("Failed to insert ebay_bin_test_runs log row: %s", exc)

    # If LIST succeeded and returned ItemID, persist into parts_detail.item_id
    saved_to_parts_detail = False
    saved_to_map = False
    if mode == "LIST" and parsed.get("item_id") and parts_detail_id is not None:
        item_id = str(parsed["item_id"])
        try:
            db.execute(
                text("UPDATE public.parts_detail SET item_id = :item_id WHERE id = :id"),
                {"item_id": item_id, "id": parts_detail_id},
            )
            db.commit()
            saved_to_parts_detail = True
        except Exception as exc:
            db.rollback()
            logger.warning("Failed to persist ItemID into parts_detail.id=%s: %s", parts_detail_id, exc)

        # Always write mapping row (hard guarantee), even if parts_detail update failed.
        try:
            db.execute(
                text(
                    """
                    INSERT INTO public.ebay_bin_listings_map
                    (run_id, legacy_inventory_id, parts_detail_id, sku, item_id)
                    VALUES (:run_id, :legacy_inventory_id, :parts_detail_id, :sku, :item_id)
                    """
                ),
                {
                    "run_id": run_id,
                    "legacy_inventory_id": req.legacy_inventory_id,
                    "parts_detail_id": parts_detail_id,
                    "sku": sku,
                    "item_id": item_id,
                },
            )
            db.commit()
            saved_to_map = True
        except Exception as exc:
            db.rollback()
            logger.warning("Failed to insert ebay_bin_listings_map row: %s", exc)

    return BinDebugResponse(
        mode=mode,
        legacy_inventory_id=req.legacy_inventory_id,
        sku=str(sku),
        parts_detail_id=parts_detail_id,
        meta={
            "site_id_header": req.site_id,
            "site_code_xml": req.site_code,
            "currency": req.currency,
            "country": req.country,
            "listing_duration": req.listing_duration,
            "category_id": str(category_id),
            "condition_id": str(condition_id) if condition_id is not None else None,
            "condition_display_name": condition_display_name,
            "policies_mode": mode,
            "seller_profiles": {
                "shipping_profile_id": req.shipping_profile_id,
                "payment_profile_id": req.payment_profile_id,
                "return_profile_id": req.return_profile_id,
            },
            "item_specifics": {"brand": brand, "mpn": mpn},
            "environment": getattr(settings, "EBAY_ENVIRONMENT", None) or getattr(settings, "ebay_environment", None),
        },
        request_url=http_res.request_url,
        request_headers_masked=http_res.request_headers_masked,
        request_body_xml=http_res.request_body_xml,
        response_http_status=http_res.response_status,
        response_headers=http_res.response_headers,
        response_body_xml=http_res.response_body_xml,
        parsed=parsed,
        log_saved=log_saved,
        log_error=log_error,
        run_id=run_id,
        item_id_saved_to_parts_detail=saved_to_parts_detail,
        item_id_saved_to_map=saved_to_map,
    )


@router.post("/verify", response_model=BinDebugResponse, dependencies=[Depends(admin_required)])
async def verify_bin_listing(
    req: BinDebugRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required),
) -> BinDebugResponse:
    """VerifyAddFixedPriceItem (preflight) using Trading API XML."""
    return await _call_trading(
        mode="VERIFY",
        call_name="VerifyAddFixedPriceItem",
        req=req,
        db=db,
        current_user=current_user,
    )


@router.post("/list", response_model=BinDebugResponse, dependencies=[Depends(admin_required)])
async def list_bin_listing(
    req: BinDebugRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required),
) -> BinDebugResponse:
    """AddFixedPriceItem (creates listing + ItemID) using Trading API XML."""
    return await _call_trading(
        mode="LIST",
        call_name="AddFixedPriceItem",
        req=req,
        db=db,
        current_user=current_user,
    )


