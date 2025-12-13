from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.models_sqlalchemy import get_db
from app.models_sqlalchemy.models import (
    EbayListingTestConfig,
    EbayListingTestLog,
    Inventory,
    InventoryStatus,
)
from app.models.ebay_worker_debug import (
    EbayListingDebugRequest,
    EbayListingDebugResponse,
    WorkerDebugTrace,
)
from app.services.auth import admin_required
from app.models.user import User
from app.services.ebay_listing_service import run_listing_worker_debug
from app.services.ebay_listing_service import _resolve_account_and_token
from app.services.ebay import ebay_service
from app.utils.logger import logger
from app.config import settings


router = APIRouter(prefix="/api/admin/ebay/test-listing", tags=["admin-ebay-test-listing"])


class TestListingConfigResponse(BaseModel):
    debug_enabled: bool
    test_inventory_status: Optional[str] = Field(
        None,
        description="InventoryStatus name to be treated as test-listing candidate (e.g. 'PENDING_LISTING').",
    )
    max_items_per_run: int = Field(50, ge=1, le=200)


class TestListingConfigUpdateRequest(BaseModel):
    debug_enabled: Optional[bool] = None
    test_inventory_status: Optional[str] = None
    max_items_per_run: Optional[int] = Field(None, ge=1, le=200)


class TestListingLogSummary(BaseModel):
    id: int
    created_at: datetime
    inventory_id: Optional[int]
    parts_detail_id: Optional[int]
    sku: Optional[str]
    status: str
    mode: str
    account_label: Optional[str]
    error_message: Optional[str]


class TestListingLogListResponse(BaseModel):
    items: List[TestListingLogSummary]
    total: int
    limit: int
    offset: int


class TestListingLogDetail(BaseModel):
    id: int
    created_at: datetime
    inventory_id: Optional[int]
    parts_detail_id: Optional[int]
    sku: Optional[str]
    status: str
    mode: str
    account_label: Optional[str]
    error_message: Optional[str]
    summary_json: Optional[dict]
    trace: Optional[WorkerDebugTrace]


class TestListingRunRequest(BaseModel):
    limit: Optional[int] = Field(50, ge=1, le=200)


class TestListingRunResponse(BaseModel):
    log_id: Optional[int]
    items_selected: int
    items_processed: int
    items_success: int
    items_failed: int


class TestListingFieldSource(BaseModel):
    table: str
    column: str


class TestListingFieldHelp(BaseModel):
    """Human-readable semantics for UI tooltips.

    - ebay_expected: what eBay expects for this field (format/meaning)
    - internal_semantics: how our internal value should be interpreted
    - lookup_rows: optional raw lookup rows (dictionaries) used to interpret the value
    """

    ebay_expected: str
    internal_semantics: Optional[str] = None
    lookup_rows: Optional[dict] = None


class TestListingPayloadField(BaseModel):
    key: str
    label: str
    required: bool
    value: Optional[str] = None
    missing: bool
    sources: list[TestListingFieldSource] = Field(default_factory=list)
    help: Optional[TestListingFieldHelp] = None


class TestListingPayloadResponse(BaseModel):
    legacy_inventory_id: int
    sku: Optional[str]
    legacy_status_code: Optional[str]
    legacy_status_name: Optional[str]
    parts_detail_id: Optional[int]
    mandatory_fields: list[TestListingPayloadField]
    optional_fields: list[TestListingPayloadField]


class TestListingListRequest(BaseModel):
    legacy_inventory_id: int = Field(..., ge=1, description="Legacy tbl_parts_inventory.ID")
    force: bool = Field(
        default=True,
        description="If true, force-run for the resolved parts_detail_id even if it doesn't satisfy normal Checked/status filters.",
    )


class TestListingPrepareRequest(BaseModel):
    legacy_inventory_id: int = Field(..., ge=1, description="Legacy tbl_parts_inventory.ID")


class TestListingPrepareResponse(BaseModel):
    legacy_inventory_id: int
    sku: str
    account_label: Optional[str] = None
    offer_id: Optional[str] = None
    chosen_offer: Optional[dict] = None
    offers_payload: Optional[dict] = None
    http_offer_lookup: Optional[dict] = None
    http_publish_planned: Optional[dict] = None


def _get_or_create_config(db: Session) -> EbayListingTestConfig:
    cfg: Optional[EbayListingTestConfig] = db.query(EbayListingTestConfig).order_by(EbayListingTestConfig.id.asc()).first()
    if cfg is None:
        cfg = EbayListingTestConfig(
            debug_enabled=False,
            test_inventory_status=None,
            max_items_per_run=50,
        )
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    return cfg


def _first_non_empty(*vals: Optional[object]) -> Optional[str]:
    for v in vals:
        if v is None:
            continue
        s = str(v).strip()
        if s == "" or s.lower() == "null":
            continue
        return s
    return None


def _build_field(
    *,
    key: str,
    label: str,
    required: bool,
    value: Optional[str],
    sources: list[tuple[str, str]],
    help: Optional[TestListingFieldHelp] = None,
) -> TestListingPayloadField:
    missing = value is None or str(value).strip() == ""
    return TestListingPayloadField(
        key=key,
        label=label,
        required=required,
        value=value,
        missing=missing if required else missing,
        sources=[TestListingFieldSource(table=t, column=c) for (t, c) in sources],
        help=help,
    )


def _make_help(
    *,
    ebay_expected: str,
    internal_semantics: Optional[str] = None,
    lookup_rows: Optional[dict] = None,
) -> TestListingFieldHelp:
    return TestListingFieldHelp(
        ebay_expected=ebay_expected.strip(),
        internal_semantics=internal_semantics.strip() if isinstance(internal_semantics, str) else internal_semantics,
        # Ensure everything is JSON-serializable (RowMapping, Decimal, datetime, etc.)
        # to avoid 500 errors during response serialization.
        lookup_rows=jsonable_encoder(lookup_rows) if lookup_rows is not None else None,
    )


def _resolve_parts_detail_id_for_legacy_sku(db: Session, sku: str) -> int:
    """Resolve parts_detail.id for a legacy numeric SKU.

    Primary attempt: `inventory.sku_code` mapping (if present).
    Fallback: direct lookup in `parts_detail` by sku/override_sku.

    This avoids failures in environments where `inventory.sku_code` is empty.
    """

    inv2 = db.execute(
        text("SELECT parts_detail_id FROM public.inventory WHERE sku_code = :sku ORDER BY id ASC LIMIT 1"),
        {"sku": sku},
    ).first()
    if inv2 and inv2[0] is not None:
        return int(inv2[0])

    # Fallback: find parts_detail row by sku/override_sku (string columns)
    row = db.execute(
        text(
            "SELECT id FROM public.parts_detail "
            "WHERE sku = :sku OR override_sku = :sku "
            "ORDER BY id DESC LIMIT 1"
        ),
        {"sku": sku},
    ).first()
    if not row or row[0] is None:
        raise HTTPException(status_code=400, detail="no_parts_detail_id_for_sku")
    return int(row[0])


@router.get("/config", response_model=TestListingConfigResponse, dependencies=[Depends(admin_required)])
async def get_test_listing_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required),  # noqa: ARG001
) -> TestListingConfigResponse:
    cfg = _get_or_create_config(db)
    return TestListingConfigResponse(
        debug_enabled=bool(cfg.debug_enabled),
        test_inventory_status=cfg.test_inventory_status,
        max_items_per_run=int(cfg.max_items_per_run or 50),
    )


@router.get("/payload", response_model=TestListingPayloadResponse, dependencies=[Depends(admin_required)])
async def get_test_listing_payload_preview(
    legacy_inventory_id: int = Query(..., ge=1, description="Legacy tbl_parts_inventory.ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required),  # noqa: ARG001
) -> TestListingPayloadResponse:
    """Build a prefilled payload preview for a single legacy inventory row.

    The caller provides a legacy `tbl_parts_inventory.ID`. We resolve its SKU,
    then merge data from:
    - tbl_parts_inventory overrides
    - parts_detail overrides (when available)
    - tbl_parts_detail (legacy payload table; the primary SKU payload source for this UI)
    - lookup tables (shipping groups, categories, conditions, status name)
    """

    inv_row = db.execute(
        text(
            'SELECT * FROM public."tbl_parts_inventory" WHERE "ID" = :id'
        ),
        {"id": legacy_inventory_id},
    ).mappings().first()
    if not inv_row:
        raise HTTPException(status_code=404, detail="legacy_inventory_not_found")

    sku_val = inv_row.get("SKU")
    sku = _first_non_empty(sku_val)

    # Legacy status: numeric code + lookup name
    legacy_status_code = _first_non_empty(inv_row.get("StatusSKU"))
    legacy_status_name = None
    if legacy_status_code:
        status_row = db.execute(
            text(
                'SELECT "InventoryStatus_Name" FROM public."tbl_parts_inventorystatus" WHERE "InventoryStatus_ID" = :sid'
            ),
            {"sid": int(float(legacy_status_code))},
        ).first()
        if status_row and status_row[0] is not None:
            legacy_status_name = str(status_row[0])

    # Try to resolve parts_detail_id via modern inventory table (best effort)
    parts_detail_id: Optional[int] = None
    if sku:
        inv2 = db.execute(
            text(
                "SELECT parts_detail_id FROM public.inventory WHERE sku_code = :sku ORDER BY id ASC LIMIT 1"
            ),
            {"sku": sku},
        ).first()
        if inv2 and inv2[0] is not None:
            try:
                parts_detail_id = int(inv2[0])
            except Exception:
                parts_detail_id = None

    pd_row = None
    if parts_detail_id is not None:
        pd_row = db.execute(
            text("SELECT * FROM public.parts_detail WHERE id = :pid"),
            {"pid": parts_detail_id},
        ).mappings().first()

    # tbl_parts_detail fallback
    tbl_parts_detail_row = None
    if sku:
        tbl_parts_detail_row = db.execute(
            text('SELECT * FROM public."tbl_parts_detail" WHERE "SKU" = :sku ORDER BY "ID" DESC LIMIT 1'),
            {"sku": int(float(sku))},
        ).mappings().first()

    # Shipping group dictionaries for label
    shipping_group_code = _first_non_empty(
        inv_row.get("ShippingGroupToChange"),
        (pd_row or {}).get("shipping_group") if isinstance(pd_row, dict) else None,  # defensive
        (tbl_parts_detail_row or {}).get("ShippingGroup"),
    )

    shipping_group_name = None
    shipping_group_lookup_rows: dict = {}
    if shipping_group_code:
        # Try tbl_internalshippinggroups first (legacy)
        sg_rows = db.execute(
            text(
                'SELECT to_jsonb(t) AS row FROM public.tbl_internalshippinggroups t WHERE (to_jsonb(t)->>\'ID\') = :id'
            ),
            {"id": str(int(float(shipping_group_code)))},
        ).fetchall()
        if sg_rows:
            shipping_group_lookup_rows["tbl_internalshippinggroups"] = [r[0] for r in sg_rows if r and r[0] is not None]
            # Prefer the first row name for display
            try:
                first = shipping_group_lookup_rows["tbl_internalshippinggroups"][0]
                if isinstance(first, dict):
                    name_val = first.get("Name") or first.get("name")
                    if name_val is not None:
                        shipping_group_name = str(name_val)
            except Exception:
                pass
        else:
            sg2 = db.execute(
                text("SELECT to_jsonb(s) AS row FROM public.sq_shipping_groups s WHERE id = :id LIMIT 1"),
                {"id": int(float(shipping_group_code))},
            ).first()
            if sg2 and sg2[0] is not None:
                shipping_group_lookup_rows["sq_shipping_groups"] = [sg2[0]]
                if isinstance(sg2[0], dict) and sg2[0].get("label") is not None:
                    shipping_group_name = str(sg2[0].get("label"))

    # Category label
    category_code = _first_non_empty(
        (tbl_parts_detail_row or {}).get("Category"),
    )
    category_label = None
    category_lookup_rows: dict = {}
    if category_code:
        cat = db.execute(
            text(
                'SELECT "CategoryDescr", "eBayCategoryName" FROM public."tbl_parts_category" WHERE "CategoryID" = :cid LIMIT 1'
            ),
            {"cid": int(float(category_code))},
        ).first()
        if cat:
            descr = str(cat[0] or "").strip()
            ebay_name = str(cat[1] or "").strip()
            parts = []
            if descr:
                parts.append(descr)
            if ebay_name:
                parts.append(ebay_name)
            category_label = " — ".join(parts) if parts else None
        # Also capture raw lookup row for tooltip semantics
        cat_row = db.execute(
            text('SELECT to_jsonb(c) AS row FROM public."tbl_parts_category" c WHERE "CategoryID" = :cid LIMIT 1'),
            {"cid": int(float(category_code))},
        ).first()
        if cat_row and cat_row[0] is not None:
            category_lookup_rows["tbl_parts_category"] = [cat_row[0]]

    # Condition label
    condition_id = _first_non_empty(
        inv_row.get("OverrideConditionID"),
        (pd_row or {}).get("override_condition_id") if isinstance(pd_row, dict) else None,
        (tbl_parts_detail_row or {}).get("ConditionID"),
    )
    condition_label = None
    condition_lookup_rows: dict = {}
    if condition_id:
        cond = db.execute(
            text("SELECT to_jsonb(c) AS row FROM public.item_conditions c WHERE id = :id LIMIT 1"),
            {"id": int(float(condition_id))},
        ).first()
        if cond and cond[0] is not None:
            condition_lookup_rows["item_conditions"] = [cond[0]]
            if isinstance(cond[0], dict):
                code = cond[0].get("code")
                label = cond[0].get("label")
                if code is not None and label:
                    condition_label = f"{code} — {label}"
                elif code is not None:
                    condition_label = str(code)

    # Pictures (prefer inventory overrides, then parts_detail, then tbl_parts_detail)
    pics: list[str] = []
    for i in range(1, 13):
        legacy_key = f"OverridePicURL{i}"
        pd_key = f"override_pic_url_{i}"
        sku_key = f"PicURL{i}"
        val = _first_non_empty(
            inv_row.get(legacy_key),
            (pd_row or {}).get(pd_key) if isinstance(pd_row, dict) else None,
            (tbl_parts_detail_row or {}).get(sku_key),
        )
        pics.append(val or "")

    pics_non_empty = [p for p in pics if p.strip()]

    # Core listing fields with precedence rules
    title = _first_non_empty(
        inv_row.get("OverrideTitle"),
        (pd_row or {}).get("override_title") if isinstance(pd_row, dict) else None,
        (tbl_parts_detail_row or {}).get("Part"),
    )
    price = _first_non_empty(
        inv_row.get("OverridePrice"),
        (pd_row or {}).get("override_price") if isinstance(pd_row, dict) else None,
        (pd_row or {}).get("price_to_change") if isinstance(pd_row, dict) else None,
        (tbl_parts_detail_row or {}).get("Price"),
    )
    quantity = _first_non_empty(inv_row.get("Quantity"))
    shipping_type = _first_non_empty(
        (tbl_parts_detail_row or {}).get("ShippingType"),
    )
    listing_type = _first_non_empty(
        (tbl_parts_detail_row or {}).get("ListingType"),
    )
    listing_duration = _first_non_empty(
        (tbl_parts_detail_row or {}).get("ListingDuration"),
    )
    site_id = _first_non_empty(
        (tbl_parts_detail_row or {}).get("SiteID"),
    )
    weight = _first_non_empty(
        (tbl_parts_detail_row or {}).get("Weight"),
    )
    unit = _first_non_empty(
        (tbl_parts_detail_row or {}).get("Unit"),
    )
    mpn = _first_non_empty(
        (tbl_parts_detail_row or {}).get("MPN"),
    )
    upc = _first_non_empty(
        (tbl_parts_detail_row or {}).get("UPC"),
    )
    part_number = _first_non_empty(
        (tbl_parts_detail_row or {}).get("Part_Number"),
    )
    description = _first_non_empty(
        inv_row.get("OverrideDescription"),
        (pd_row or {}).get("override_description") if isinstance(pd_row, dict) else None,
        (tbl_parts_detail_row or {}).get("Description"),
    )

    mandatory: list[TestListingPayloadField] = []
    optional: list[TestListingPayloadField] = []

    mandatory.append(
        _build_field(
            key="legacy_inventory_id",
            label="Legacy Inventory ID (tbl_parts_inventory.ID)",
            required=True,
            value=str(legacy_inventory_id),
            sources=[("tbl_parts_inventory", "ID")],
            help=_make_help(
                ebay_expected="Not sent to eBay. This is an internal key used to load data for preview.",
                internal_semantics=(
                    f"Loads tbl_parts_inventory row ID={legacy_inventory_id}. "
                    f"Resolved legacy status: {legacy_status_name or legacy_status_code or '—'}."
                ),
                lookup_rows={
                    "tbl_parts_inventory": [inv_row],
                    "tbl_parts_inventorystatus": (
                        [{"InventoryStatus_ID": int(float(legacy_status_code)), "InventoryStatus_Name": legacy_status_name}]
                        if legacy_status_code or legacy_status_name
                        else []
                    ),
                },
            ),
        )
    )
    mandatory.append(
        _build_field(
            key="sku",
            label="SKU",
            required=True,
            value=sku,
            sources=[("tbl_parts_inventory", "SKU"), ("tbl_parts_detail", "SKU"), ("parts_detail", "sku")],
            help=_make_help(
                ebay_expected="A stable SKU / merchant-managed identifier used to find/create inventory items and offers.",
                internal_semantics="We use the legacy numeric SKU stored on tbl_parts_inventory and tbl_parts_detail.",
                lookup_rows={
                    "tbl_parts_detail": [tbl_parts_detail_row] if tbl_parts_detail_row else [],
                    "parts_detail": [pd_row] if isinstance(pd_row, dict) else [],
                },
            ),
        )
    )
    mandatory.append(
        _build_field(
            key="title",
            label="Title (<=80 chars)",
            required=True,
            value=title,
            sources=[("tbl_parts_inventory", "OverrideTitle"), ("parts_detail", "override_title"), ("tbl_parts_detail", "Part")],
            help=_make_help(
                ebay_expected="A concise item title (often max 80 characters). Must follow eBay title rules for the category.",
                internal_semantics="We prefill from OverrideTitle → parts_detail.override_title → tbl_parts_detail.Part.",
            ),
        )
    )
    mandatory.append(
        _build_field(
            key="price",
            label="Price",
            required=True,
            value=price,
            sources=[("tbl_parts_inventory", "OverridePrice"), ("parts_detail", "override_price/price_to_change"), ("tbl_parts_detail", "Price")],
            help=_make_help(
                ebay_expected="Fixed price for Buy It Now listings. Must be a positive number; currency is implied by marketplace/account.",
                internal_semantics="We prefill from OverridePrice → parts_detail.override_price/price_to_change → tbl_parts_detail.Price.",
            ),
        )
    )
    mandatory.append(
        _build_field(
            key="quantity",
            label="Quantity",
            required=True,
            value=quantity,
            sources=[("tbl_parts_inventory", "Quantity")],
            help=_make_help(
                ebay_expected="Offer available quantity (integer).",
                internal_semantics="For our workflow, parts inventory quantity is usually 1; this comes from tbl_parts_inventory.Quantity.",
            ),
        )
    )
    mandatory.append(
        _build_field(
            key="condition_id",
            label="ConditionID",
            required=True,
            value=condition_id,
            sources=[("tbl_parts_inventory", "OverrideConditionID"), ("parts_detail", "override_condition_id"), ("tbl_parts_detail", "ConditionID")],
            help=_make_help(
                ebay_expected="A valid eBay Condition ID allowed for the selected category (e.g., New/Used/For parts).",
                internal_semantics="We store ConditionID on tbl_parts_detail and interpret it via item_conditions when possible.",
                lookup_rows=condition_lookup_rows or None,
            ),
        )
    )
    mandatory.append(
        _build_field(
            key="pictures",
            label="Pictures (at least 1 URL)",
            required=True,
            value=str(len(pics_non_empty)),
            sources=[("tbl_parts_inventory", "OverridePicURL1..12"), ("parts_detail", "override_pic_url_1..12"), ("tbl_parts_detail", "PicURL1..12")],
            help=_make_help(
                ebay_expected="At least 1 publicly accessible image URL (HTTPS). Images must meet eBay requirements (no watermarks, adequate resolution, etc.).",
                internal_semantics="We count non-empty URLs using OverridePicURL* → parts_detail.override_pic_url_* → tbl_parts_detail.PicURL*.",
                lookup_rows={
                    "pic_urls": [{"index": i + 1, "url": p} for i, p in enumerate(pics) if p.strip()],
                },
            ),
        )
    )
    # Mark pictures missing when none exist
    mandatory[-1].missing = len(pics_non_empty) == 0

    mandatory.append(
        _build_field(
            key="shipping_group",
            label="Shipping group",
            required=True,
            value=(
                f"{shipping_group_code}: {shipping_group_name}"
                if shipping_group_code and shipping_group_name
                else _first_non_empty(shipping_group_code, shipping_group_name)
            ),
            sources=[("tbl_parts_detail", "ShippingGroup"), ("tbl_internalshippinggroups", "ID/Name/Description"), ("sq_shipping_groups", "id/label")],
            help=_make_help(
                ebay_expected="Shipping configuration is expressed on eBay via shipping policies/services (not via our internal group id).",
                internal_semantics=(
                    "ShippingGroup is our internal preset. Example: “no international” means the offer/policy should disallow international shipping and use domestic services only."
                ),
                lookup_rows=shipping_group_lookup_rows or None,
            ),
        )
    )
    mandatory.append(
        _build_field(
            key="shipping_type",
            label="Shipping type",
            required=True,
            value=shipping_type,
            sources=[("tbl_parts_detail", "ShippingType")],
            help=_make_help(
                ebay_expected="Shipping price type: typically Flat (fixed amount) or Calculated (carrier/zone based).",
                internal_semantics="We store ShippingType on tbl_parts_detail as a hint for which eBay shipping policy/pricing mode to apply.",
            ),
        )
    )
    mandatory.append(
        _build_field(
            key="listing_type",
            label="Listing type (must be FixedPriceItem for BIN test)",
            required=True,
            value=listing_type,
            sources=[("tbl_parts_detail", "ListingType")],
            help=_make_help(
                ebay_expected="For our test tool we publish Buy It Now / fixed price only. Expected value: FixedPriceItem.",
                internal_semantics="ListingType is stored on tbl_parts_detail and should remain FixedPriceItem for this test flow.",
            ),
        )
    )
    mandatory.append(
        _build_field(
            key="listing_duration",
            label="Listing duration",
            required=True,
            value=listing_duration,
            sources=[("tbl_parts_detail", "ListingDuration")],
            help=_make_help(
                ebay_expected="Duration for fixed price listings (often GTC = Good 'Til Cancelled, or a fixed number of days depending on policy).",
                internal_semantics="ListingDuration is stored on tbl_parts_detail (e.g., GTC).",
            ),
        )
    )
    mandatory.append(
        _build_field(
            key="site_id",
            label="Site",
            required=True,
            value=site_id,
            sources=[("tbl_parts_detail", "SiteID")],
            help=_make_help(
                ebay_expected="Marketplace/site identifier (e.g., eBay US). Must match the publishing account marketplace.",
                internal_semantics="We store SiteID on tbl_parts_detail; for US this is commonly 0.",
            ),
        )
    )
    mandatory.append(
        _build_field(
            key="category",
            label="Category (internal or eBay category)",
            required=True,
            value=_first_non_empty(category_code, category_label),
            sources=[("tbl_parts_detail", "Category/ExternalCategory*"), ("tbl_parts_category", "CategoryID/CategoryDescr/eBayCategoryName")],
            help=_make_help(
                ebay_expected="A valid eBay category (or a mapping to one). Category drives allowed conditions, required item specifics, and shipping rules.",
                internal_semantics="We store internal Category (and optional ExternalCategory fields) on tbl_parts_detail; we decode internal Category via tbl_parts_category when available.",
                lookup_rows=category_lookup_rows or None,
            ),
        )
    )

    optional.append(
        _build_field(
            key="mpn",
            label="MPN",
            required=False,
            value=mpn,
            sources=[("tbl_parts_detail", "MPN")],
            help=_make_help(
                ebay_expected="Manufacturer Part Number. Optional in many categories but sometimes required unless “Does not apply” is accepted.",
                internal_semantics="We store MPN on tbl_parts_detail and pass it as an item identifier when applicable.",
            ),
        )
    )
    optional.append(
        _build_field(
            key="part_number",
            label="Part number",
            required=False,
            value=part_number,
            sources=[("tbl_parts_detail", "Part_Number")],
            help=_make_help(
                ebay_expected="Part number / manufacturer part identifier. Category-dependent requirements.",
                internal_semantics="We store Part_Number on tbl_parts_detail; often same as MPN in our dataset.",
            ),
        )
    )
    optional.append(
        _build_field(
            key="upc",
            label="UPC",
            required=False,
            value=upc,
            sources=[("tbl_parts_detail", "UPC")],
            help=_make_help(
                ebay_expected="Product identifier (UPC/EAN/ISBN). Some categories allow “Does not apply”.",
                internal_semantics="We store UPC on tbl_parts_detail; value “Does not apply” is commonly used when permitted.",
            ),
        )
    )
    optional.append(
        _build_field(
            key="weight",
            label="Weight",
            required=False,
            value=weight,
            sources=[("tbl_parts_detail", "Weight")],
            help=_make_help(
                ebay_expected="Package weight used for calculated shipping and label purchase (units must be consistent).",
                internal_semantics="We store Weight on tbl_parts_detail; unit may be stored separately (Unit).",
            ),
        )
    )
    optional.append(
        _build_field(
            key="unit",
            label="Weight unit",
            required=False,
            value=unit,
            sources=[("tbl_parts_detail", "Unit")],
            help=_make_help(
                ebay_expected="Weight unit (e.g., oz/lb/g/kg) consistent with marketplace/policy.",
                internal_semantics="We store Unit on tbl_parts_detail; if empty, the pipeline must assume a default (commonly oz).",
            ),
        )
    )
    mandatory.append(
        _build_field(
            key="description",
            label="Description (HTML/long)",
            required=True,
            value=description,
            sources=[("tbl_parts_inventory", "OverrideDescription"), ("parts_detail", "override_description"), ("tbl_parts_detail", "Description")],
            help=_make_help(
                ebay_expected="Long item description. For most categories and legacy listing flows, a description is required. HTML must be allowed/safe per eBay rules.",
                internal_semantics="We prefill from OverrideDescription → parts_detail.override_description → tbl_parts_detail.Description. If empty, listing should be blocked in debug UI.",
            ),
        )
    )
    optional.append(
        _build_field(
            key="condition_label",
            label="Condition label (dictionary)",
            required=False,
            value=condition_label,
            sources=[("item_conditions", "id/code/label")],
            help=_make_help(
                ebay_expected="Human-readable label for ConditionID.",
                internal_semantics="Resolved via item_conditions when IDs align in this environment.",
                lookup_rows=condition_lookup_rows or None,
            ),
        )
    )

    # Provide raw picture urls as optional fields (PicURL1..12)
    for i in range(1, 13):
        optional.append(
            _build_field(
                key=f"pic_url_{i}",
                label=f"Picture URL #{i}",
                required=False,
                value=pics[i - 1] or None,
                sources=[("tbl_parts_inventory", f"OverridePicURL{i}"), ("parts_detail", f"override_pic_url_{i}"), ("tbl_parts_detail", f"PicURL{i}")],
                help=_make_help(
                    ebay_expected="Image URL (HTTPS). Must be publicly accessible and meet eBay image requirements.",
                    internal_semantics="We prefill using the same precedence as the pictures count.",
                ),
            )
        )

    return TestListingPayloadResponse(
        legacy_inventory_id=legacy_inventory_id,
        sku=sku,
        legacy_status_code=legacy_status_code,
        legacy_status_name=legacy_status_name,
        parts_detail_id=parts_detail_id,
        mandatory_fields=mandatory,
        optional_fields=optional,
    )


@router.post("/list", response_model=EbayListingDebugResponse, dependencies=[Depends(admin_required)])
async def list_single_legacy_inventory_id(
    payload: TestListingListRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required),  # noqa: ARG001
) -> EbayListingDebugResponse:
    """Force-run the listing worker for a single legacy inventory row.

    This is a debug-only endpoint used by the admin UI's Preview → LIST flow.
    It resolves:
    - legacy tbl_parts_inventory.ID -> SKU
    - SKU -> modern inventory.parts_detail_id (best effort)
    - parts_detail_id -> parts_detail ORM row

    Then runs `run_listing_worker_debug` for that single row and returns the
    full WorkerDebugTrace so the UI can display raw HTTP requests/responses.

    Note: the underlying worker primarily publishes existing offers
    (bulkPublishOffer). It does not yet create offers from tbl_parts_detail.
    """

    inv_row = db.execute(
        text('SELECT * FROM public."tbl_parts_inventory" WHERE "ID" = :id'),
        {"id": payload.legacy_inventory_id},
    ).mappings().first()
    if not inv_row:
        raise HTTPException(status_code=404, detail="legacy_inventory_not_found")

    sku = _first_non_empty(inv_row.get("SKU"))
    if not sku:
        raise HTTPException(status_code=400, detail="legacy_inventory_missing_sku")

    try:
        parts_detail_id = _resolve_parts_detail_id_for_legacy_sku(db, sku)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid_parts_detail_id")

    from app.models_sqlalchemy.models import PartsDetail  # local import to avoid circulars

    pd = db.query(PartsDetail).filter(PartsDetail.id == parts_detail_id).first()
    if not pd:
        raise HTTPException(status_code=404, detail="parts_detail_not_found")

    req = EbayListingDebugRequest(ids=[parts_detail_id], dry_run=False, max_items=1)

    # Force-run by injecting candidates_override (bypasses _select_candidates_for_listing filters).
    candidates_override = [pd] if payload.force else None
    resp = await run_listing_worker_debug(db, req, candidates_override=candidates_override)
    return resp


@router.post("/prepare", response_model=TestListingPrepareResponse, dependencies=[Depends(admin_required)])
async def prepare_test_listing_real_http(
    payload: TestListingPrepareRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required),  # noqa: ARG001
) -> TestListingPrepareResponse:
    """Prepare a real HTTP preview for listing (no publish).

    Performs the real eBay offer lookup call (GET offers by SKU), selects the
    offerId the same way the worker does, and returns:
    - real HTTP request/response metadata for offer lookup (Authorization masked)
    - resolved offerId
    - planned publish request (bulkPublishOffer) with resolved offerId

    This does NOT publish to eBay.
    """

    inv_row = db.execute(
        text('SELECT * FROM public."tbl_parts_inventory" WHERE "ID" = :id'),
        {"id": payload.legacy_inventory_id},
    ).mappings().first()
    if not inv_row:
        raise HTTPException(status_code=404, detail="legacy_inventory_not_found")

    sku = _first_non_empty(inv_row.get("SKU"))
    if not sku:
        raise HTTPException(status_code=400, detail="legacy_inventory_missing_sku")

    try:
        parts_detail_id = _resolve_parts_detail_id_for_legacy_sku(db, sku)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid_parts_detail_id")

    from app.models_sqlalchemy.models import PartsDetail  # local import to avoid circulars

    pd = db.query(PartsDetail).filter(PartsDetail.id == parts_detail_id).first()
    if not pd:
        raise HTTPException(status_code=404, detail="parts_detail_not_found")

    # Resolve account + token (same logic as worker live mode)
    account, access_token, account_error = _resolve_account_and_token(db, pd.username or "", pd.ebay_id or "")
    if account_error or not account or not access_token:
        raise HTTPException(status_code=400, detail=account_error or "account_or_token_not_available")

    account_label = f"{account.username or 'UNKNOWN'} (ebay_id={account.id or 'N/A'})"

    # Real offer lookup HTTP call (masked)
    try:
        offers_debug = await ebay_service.fetch_offers_debug(access_token, sku=str(pd.override_sku or pd.sku or sku), filter_params={"limit": 200})
    except HTTPException as exc:
        # Bubble up with useful details (still masked)
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)

    offers_payload = offers_debug.get("payload") if isinstance(offers_debug, dict) else None
    http_offer_lookup = offers_debug.get("http") if isinstance(offers_debug, dict) else None

    offers = (offers_payload or {}).get("offers") or []
    chosen_offer: Optional[dict] = None

    # Prefer marketplace match when possible (matches worker behavior)
    for off in offers:
        marketplace_id = off.get("marketplaceId") or off.get("marketplace_id")
        if getattr(account, "marketplace_id", None) and marketplace_id == account.marketplace_id:
            chosen_offer = off
            break

    if chosen_offer is None and offers:
        chosen_offer = offers[0]

    offer_id = None
    if chosen_offer is not None:
        offer_id = str(chosen_offer.get("offerId") or "").strip() or None

    http_publish_planned = {
        "request": {
            "method": "POST",
            "url": f"{settings.ebay_api_base_url.rstrip('/')}/sell/inventory/v1/bulk_publish_offer",
            "headers": {
                "Authorization": "Bearer ***",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            "body": {"requests": [{"offerId": offer_id or "<offerId_not_resolved>"}]},
        },
        "meta": {
            "note": "Planned publish call. Actual publish happens only after user confirms LIST.",
            "listing_mode": (getattr(settings, "ebay_listing_mode", "stub") or "stub").lower(),
        },
    }

    return TestListingPrepareResponse(
        legacy_inventory_id=payload.legacy_inventory_id,
        sku=str(pd.override_sku or pd.sku or sku),
        account_label=account_label,
        offer_id=offer_id,
        chosen_offer=jsonable_encoder(chosen_offer) if chosen_offer is not None else None,
        offers_payload=jsonable_encoder(offers_payload) if offers_payload is not None else None,
        http_offer_lookup=jsonable_encoder(http_offer_lookup) if http_offer_lookup is not None else None,
        http_publish_planned=jsonable_encoder(http_publish_planned),
    )


@router.put("/config", response_model=TestListingConfigResponse, dependencies=[Depends(admin_required)])
async def update_test_listing_config(
    payload: TestListingConfigUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required),  # noqa: ARG001
) -> TestListingConfigResponse:
    cfg = _get_or_create_config(db)

    if payload.debug_enabled is not None:
        cfg.debug_enabled = bool(payload.debug_enabled)

    if payload.test_inventory_status is not None:
        # We allow free-form strings but prefer values matching InventoryStatus names.
        status_name = payload.test_inventory_status.strip().upper() or None
        if status_name is not None and status_name not in InventoryStatus.__members__:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown InventoryStatus '{payload.test_inventory_status}'",
            )
        cfg.test_inventory_status = status_name

    if payload.max_items_per_run is not None:
        cfg.max_items_per_run = int(payload.max_items_per_run)

    db.commit()
    db.refresh(cfg)

    return TestListingConfigResponse(
        debug_enabled=bool(cfg.debug_enabled),
        test_inventory_status=cfg.test_inventory_status,
        max_items_per_run=int(cfg.max_items_per_run or 50),
    )


@router.get("/logs", response_model=TestListingLogListResponse, dependencies=[Depends(admin_required)])
async def list_test_listing_logs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status_filter: Optional[str] = Query(None, description="Filter by status (SUCCESS/ERROR)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required),  # noqa: ARG001
) -> TestListingLogListResponse:
    q = db.query(EbayListingTestLog)
    if status_filter:
        q = q.filter(EbayListingTestLog.status == status_filter.upper())

    total = q.count()
    rows = (
        q.order_by(EbayListingTestLog.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    items = [
        TestListingLogSummary(
            id=row.id,
            created_at=row.created_at or datetime.utcnow(),
            inventory_id=row.inventory_id,
            parts_detail_id=row.parts_detail_id,
            sku=row.sku,
            status=row.status,
            mode=row.mode,
            account_label=row.account_label,
            error_message=row.error_message,
        )
        for row in rows
    ]

    return TestListingLogListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/logs/{log_id}", response_model=TestListingLogDetail, dependencies=[Depends(admin_required)])
async def get_test_listing_log_detail(
    log_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required),  # noqa: ARG001
) -> TestListingLogDetail:
    row: Optional[EbayListingTestLog] = db.query(EbayListingTestLog).filter(EbayListingTestLog.id == log_id).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="log_not_found")

    trace_model: Optional[WorkerDebugTrace] = None
    if row.trace_json:
        try:
            trace_model = WorkerDebugTrace.parse_obj(row.trace_json)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to parse WorkerDebugTrace for log_id=%s: %s", log_id, exc)
            trace_model = None

    return TestListingLogDetail(
        id=row.id,
        created_at=row.created_at or datetime.utcnow(),
        inventory_id=row.inventory_id,
        parts_detail_id=row.parts_detail_id,
        sku=row.sku,
        status=row.status,
        mode=row.mode,
        account_label=row.account_label,
        error_message=row.error_message,
        summary_json=row.summary_json or None,
        trace=trace_model,
    )


@router.post("/run", response_model=TestListingRunResponse, dependencies=[Depends(admin_required)])
async def run_test_listing_once(
    payload: TestListingRunRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required),
) -> TestListingRunResponse:
    """Run the eBay listing worker once for Inventory rows in test status.

    This endpoint selects Inventory rows with the configured test_inventory_status
    and no ebay_listing_id, resolves their parts_detail_id values and runs the
    existing eBay listing worker (run_listing_worker_debug) against those
    candidates. The full WorkerDebugTrace is persisted into
    ebay_listing_test_logs so the admin UI can inspect the HTTP traffic.
    """

    cfg = _get_or_create_config(db)
    if not cfg.test_inventory_status:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="test_inventory_status_not_configured",
        )

    status_name = cfg.test_inventory_status.upper()
    try:
        target_status = InventoryStatus[status_name]
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Configured test_inventory_status '{cfg.test_inventory_status}' is not a valid InventoryStatus",
        )

    limit = payload.limit or cfg.max_items_per_run or 50
    if limit > 200:
        limit = 200

    inv_rows: List[Inventory] = (
        db.query(Inventory)
        .filter(
            Inventory.status == target_status,
            Inventory.ebay_listing_id.is_(None),
            Inventory.parts_detail_id.isnot(None),
        )
        .order_by(Inventory.id.asc())
        .limit(limit)
        .all()
    )

    parts_detail_ids: List[int] = [
        int(r.parts_detail_id) for r in inv_rows if r.parts_detail_id is not None
    ]

    if not parts_detail_ids:
        return TestListingRunResponse(
            log_id=None,
            items_selected=0,
            items_processed=0,
            items_success=0,
            items_failed=0,
        )

    listing_mode = (getattr(settings, "ebay_listing_mode", "stub") or "stub").lower()

    req = EbayListingDebugRequest(
        ids=parts_detail_ids,
        dry_run=False,
        max_items=min(len(parts_detail_ids), cfg.max_items_per_run or 50, 200),
    )

    resp = await run_listing_worker_debug(db, req)

    summary = resp.summary
    status_str = "SUCCESS" if summary.items_failed == 0 else "ERROR"

    if cfg.debug_enabled:
        # Persist full trace for deep inspection in the admin UI.
        log_row = EbayListingTestLog(
            created_by_user_id=current_user.id,
            inventory_id=None,  # batch run over multiple inventory rows
            parts_detail_id=None,
            sku=None,
            status=status_str,
            mode=listing_mode,
            account_label=resp.trace.account,
            error_message=(
                None
                if summary.items_failed == 0
                else f"{summary.items_failed} items failed during test-listing run"
            ),
            summary_json=summary.dict(),
            trace_json=resp.trace.dict(),
        )
        db.add(log_row)
        db.commit()
        db.refresh(log_row)
        log_id = log_row.id
    else:
        # When debug is disabled we do not store the heavy trace; callers still
        # get summary information back.
        log_id = None

    return TestListingRunResponse(
        log_id=log_id,
        items_selected=summary.items_selected,
        items_processed=summary.items_processed,
        items_success=summary.items_success,
        items_failed=summary.items_failed,
    )
