from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

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
