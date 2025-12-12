from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
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
    WorkerDebugTrace,
)
from app.services.auth import admin_required
from app.models.user import User
from app.services.ebay_listing_service import run_listing_worker_debug
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


class TestListingPayloadField(BaseModel):
    key: str
    label: str
    required: bool
    value: Optional[str] = None
    missing: bool
    sources: list[TestListingFieldSource] = Field(default_factory=list)


class TestListingPayloadResponse(BaseModel):
    legacy_inventory_id: int
    sku: Optional[str]
    legacy_status_code: Optional[str]
    legacy_status_name: Optional[str]
    parts_detail_id: Optional[int]
    mandatory_fields: list[TestListingPayloadField]
    optional_fields: list[TestListingPayloadField]


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
) -> TestListingPayloadField:
    missing = value is None or str(value).strip() == ""
    return TestListingPayloadField(
        key=key,
        label=label,
        required=required,
        value=value,
        missing=missing if required else missing,
        sources=[TestListingFieldSource(table=t, column=c) for (t, c) in sources],
    )


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
    - "SKU_catalog" (SQ edit form payload)
    - tbl_parts_detail (legacy payload fallback)
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

    # SKU_catalog (mixed-case table)
    sku_catalog_row = None
    if sku:
        sku_catalog_row = db.execute(
            text('SELECT * FROM public."SKU_catalog" WHERE "SKU" = :sku ORDER BY "ID" DESC LIMIT 1'),
            {"sku": int(float(sku))},
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
        (sku_catalog_row or {}).get("ShippingGroup"),
        (tbl_parts_detail_row or {}).get("ShippingGroup"),
    )

    shipping_group_name = None
    if shipping_group_code:
        # Try tbl_internalshippinggroups first (legacy)
        sg = db.execute(
            text(
                'SELECT "Name", "Description" FROM public.tbl_internalshippinggroups WHERE (to_jsonb(tbl_internalshippinggroups)->>\'ID\') = :id LIMIT 1'
            ),
            {"id": str(int(float(shipping_group_code)))},
        ).first()
        if sg and sg[0] is not None:
            shipping_group_name = str(sg[0])
        else:
            sg2 = db.execute(
                text("SELECT label FROM public.sq_shipping_groups WHERE id = :id LIMIT 1"),
                {"id": int(float(shipping_group_code))},
            ).first()
            if sg2 and sg2[0] is not None:
                shipping_group_name = str(sg2[0])

    # Category label
    category_code = _first_non_empty(
        (sku_catalog_row or {}).get("Category"),
        (tbl_parts_detail_row or {}).get("Category"),
    )
    category_label = None
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

    # Condition label
    condition_id = _first_non_empty(
        inv_row.get("OverrideConditionID"),
        (pd_row or {}).get("override_condition_id") if isinstance(pd_row, dict) else None,
        (sku_catalog_row or {}).get("ConditionID"),
        (tbl_parts_detail_row or {}).get("ConditionID"),
    )
    condition_label = None
    if condition_id:
        cond = db.execute(
            text("SELECT code, label FROM public.item_conditions WHERE id = :id LIMIT 1"),
            {"id": int(float(condition_id))},
        ).first()
        if cond:
            condition_label = f"{cond[0]} — {cond[1]}" if cond[1] else str(cond[0])

    # Pictures (prefer inventory overrides, then parts_detail, then SKU_catalog, then tbl_parts_detail)
    pics: list[str] = []
    for i in range(1, 13):
        legacy_key = f"OverridePicURL{i}"
        pd_key = f"override_pic_url_{i}"
        sku_key = f"PicURL{i}"
        val = _first_non_empty(
            inv_row.get(legacy_key),
            (pd_row or {}).get(pd_key) if isinstance(pd_row, dict) else None,
            (sku_catalog_row or {}).get(sku_key),
            (tbl_parts_detail_row or {}).get(sku_key),
        )
        pics.append(val or "")

    pics_non_empty = [p for p in pics if p.strip()]

    # Core listing fields with precedence rules
    title = _first_non_empty(
        inv_row.get("OverrideTitle"),
        (pd_row or {}).get("override_title") if isinstance(pd_row, dict) else None,
        (sku_catalog_row or {}).get("Part"),
        (tbl_parts_detail_row or {}).get("Part"),
    )
    price = _first_non_empty(
        inv_row.get("OverridePrice"),
        (pd_row or {}).get("override_price") if isinstance(pd_row, dict) else None,
        (pd_row or {}).get("price_to_change") if isinstance(pd_row, dict) else None,
        (sku_catalog_row or {}).get("Price"),
        (tbl_parts_detail_row or {}).get("Price"),
    )
    quantity = _first_non_empty(inv_row.get("Quantity"))
    shipping_type = _first_non_empty(
        (sku_catalog_row or {}).get("ShippingType"),
        (tbl_parts_detail_row or {}).get("ShippingType"),
    )
    listing_type = _first_non_empty(
        (sku_catalog_row or {}).get("ListingType"),
        (tbl_parts_detail_row or {}).get("ListingType"),
    )
    listing_duration = _first_non_empty(
        (sku_catalog_row or {}).get("ListingDuration"),
        (tbl_parts_detail_row or {}).get("ListingDuration"),
    )
    site_id = _first_non_empty(
        (sku_catalog_row or {}).get("SiteID"),
        (tbl_parts_detail_row or {}).get("SiteID"),
    )
    weight = _first_non_empty(
        (sku_catalog_row or {}).get("Weight"),
        (tbl_parts_detail_row or {}).get("Weight"),
    )
    unit = _first_non_empty(
        (sku_catalog_row or {}).get("Unit"),
        (tbl_parts_detail_row or {}).get("Unit"),
    )
    mpn = _first_non_empty(
        (sku_catalog_row or {}).get("MPN"),
        (tbl_parts_detail_row or {}).get("MPN"),
    )
    upc = _first_non_empty(
        (sku_catalog_row or {}).get("UPC"),
        (tbl_parts_detail_row or {}).get("UPC"),
    )
    part_number = _first_non_empty(
        (sku_catalog_row or {}).get("Part_Number"),
        (tbl_parts_detail_row or {}).get("Part_Number"),
    )
    description = _first_non_empty(
        inv_row.get("OverrideDescription"),
        (pd_row or {}).get("override_description") if isinstance(pd_row, dict) else None,
        (sku_catalog_row or {}).get("Description"),
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
        )
    )
    mandatory.append(
        _build_field(
            key="sku",
            label="SKU",
            required=True,
            value=sku,
            sources=[("tbl_parts_inventory", "SKU"), ("SKU_catalog", "SKU"), ("tbl_parts_detail", "SKU"), ("parts_detail", "sku")],
        )
    )
    mandatory.append(
        _build_field(
            key="title",
            label="Title (<=80 chars)",
            required=True,
            value=title,
            sources=[("tbl_parts_inventory", "OverrideTitle"), ("parts_detail", "override_title"), ("SKU_catalog", "Part"), ("tbl_parts_detail", "Part")],
        )
    )
    mandatory.append(
        _build_field(
            key="price",
            label="Price",
            required=True,
            value=price,
            sources=[("tbl_parts_inventory", "OverridePrice"), ("parts_detail", "override_price/price_to_change"), ("SKU_catalog", "Price"), ("tbl_parts_detail", "Price")],
        )
    )
    mandatory.append(
        _build_field(
            key="quantity",
            label="Quantity",
            required=True,
            value=quantity,
            sources=[("tbl_parts_inventory", "Quantity")],
        )
    )
    mandatory.append(
        _build_field(
            key="condition_id",
            label="ConditionID",
            required=True,
            value=condition_id,
            sources=[("tbl_parts_inventory", "OverrideConditionID"), ("parts_detail", "override_condition_id"), ("SKU_catalog", "ConditionID"), ("tbl_parts_detail", "ConditionID")],
        )
    )
    mandatory.append(
        _build_field(
            key="pictures",
            label="Pictures (at least 1 URL)",
            required=True,
            value=str(len(pics_non_empty)),
            sources=[("tbl_parts_inventory", "OverridePicURL1..12"), ("parts_detail", "override_pic_url_1..12"), ("SKU_catalog", "PicURL1..12"), ("tbl_parts_detail", "PicURL1..12")],
        )
    )
    # Mark pictures missing when none exist
    mandatory[-1].missing = len(pics_non_empty) == 0

    mandatory.append(
        _build_field(
            key="shipping_group",
            label="Shipping group",
            required=True,
            value=_first_non_empty(shipping_group_code, shipping_group_name),
            sources=[("SKU_catalog", "ShippingGroup"), ("tbl_parts_detail", "ShippingGroup"), ("tbl_internalshippinggroups", "ID/Name"), ("sq_shipping_groups", "id/label")],
        )
    )
    mandatory.append(
        _build_field(
            key="shipping_type",
            label="Shipping type",
            required=True,
            value=shipping_type,
            sources=[("SKU_catalog", "ShippingType"), ("tbl_parts_detail", "ShippingType")],
        )
    )
    mandatory.append(
        _build_field(
            key="listing_type",
            label="Listing type (must be FixedPriceItem for BIN test)",
            required=True,
            value=listing_type,
            sources=[("SKU_catalog", "ListingType"), ("tbl_parts_detail", "ListingType")],
        )
    )
    mandatory.append(
        _build_field(
            key="listing_duration",
            label="Listing duration",
            required=True,
            value=listing_duration,
            sources=[("SKU_catalog", "ListingDuration"), ("tbl_parts_detail", "ListingDuration")],
        )
    )
    mandatory.append(
        _build_field(
            key="site_id",
            label="Site",
            required=True,
            value=site_id,
            sources=[("SKU_catalog", "SiteID"), ("tbl_parts_detail", "SiteID")],
        )
    )
    mandatory.append(
        _build_field(
            key="category",
            label="Category (internal or eBay category)",
            required=True,
            value=_first_non_empty(category_code, category_label),
            sources=[("SKU_catalog", "Category/ExternalCategory*"), ("tbl_parts_detail", "Category/ExternalCategory*"), ("tbl_parts_category", "CategoryID/CategoryDescr/eBayCategoryName")],
        )
    )

    optional.append(
        _build_field(
            key="mpn",
            label="MPN",
            required=False,
            value=mpn,
            sources=[("SKU_catalog", "MPN"), ("tbl_parts_detail", "MPN")],
        )
    )
    optional.append(
        _build_field(
            key="part_number",
            label="Part number",
            required=False,
            value=part_number,
            sources=[("SKU_catalog", "Part_Number"), ("tbl_parts_detail", "Part_Number")],
        )
    )
    optional.append(
        _build_field(
            key="upc",
            label="UPC",
            required=False,
            value=upc,
            sources=[("SKU_catalog", "UPC"), ("tbl_parts_detail", "UPC")],
        )
    )
    optional.append(
        _build_field(
            key="weight",
            label="Weight",
            required=False,
            value=weight,
            sources=[("SKU_catalog", "Weight"), ("tbl_parts_detail", "Weight")],
        )
    )
    optional.append(
        _build_field(
            key="unit",
            label="Weight unit",
            required=False,
            value=unit,
            sources=[("SKU_catalog", "Unit"), ("tbl_parts_detail", "Unit")],
        )
    )
    optional.append(
        _build_field(
            key="description",
            label="Description (HTML/long)",
            required=False,
            value=description,
            sources=[("tbl_parts_inventory", "OverrideDescription"), ("parts_detail", "override_description"), ("SKU_catalog", "Description"), ("tbl_parts_detail", "Description")],
        )
    )
    optional.append(
        _build_field(
            key="condition_label",
            label="Condition label (dictionary)",
            required=False,
            value=condition_label,
            sources=[("item_conditions", "id/code/label")],
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
                sources=[("tbl_parts_inventory", f"OverridePicURL{i}"), ("parts_detail", f"override_pic_url_{i}"), ("SKU_catalog", f"PicURL{i}"), ("tbl_parts_detail", f"PicURL{i}")],
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
