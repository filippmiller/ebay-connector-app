from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models_sqlalchemy import get_db
from app.models_sqlalchemy.ebay_workers import BackgroundWorker
from app.services.auth import admin_required
from app.models.user import User
from app.utils.logger import logger
from app.workers.inventory_mv_refresh_worker import (
    WORKER_NAME as INVENTORY_MV_WORKER_KEY,
    run_inventory_mv_refresh_once,
)


router = APIRouter(prefix="/api/admin/workers", tags=["admin-workers"])


class InventoryMvWorkerDto(BaseModel):
    worker_key: str
    display_name: str
    description: Optional[str]
    enabled: bool
    interval_seconds: int
    last_run_at: Optional[str]
    last_run_status: Optional[str]
    last_run_error: Optional[str]


class InventoryMvWorkerUpdateRequest(BaseModel):
    enabled: Optional[bool] = None
    interval_seconds: Optional[int] = None


def _get_or_create_inventory_worker(db: Session) -> BackgroundWorker:
    """Return the BackgroundWorker row for the inventory MV refresh worker.

    This helper mirrors the pattern used by other workers: there should be a
    single row identified by worker_name = INVENTORY_MV_WORKER_KEY.
    """

    worker: Optional[BackgroundWorker] = (
        db.query(BackgroundWorker)
        .filter(BackgroundWorker.worker_name == INVENTORY_MV_WORKER_KEY)
        .one_or_none()
    )
    if worker is None:
        worker = BackgroundWorker(
            worker_name=INVENTORY_MV_WORKER_KEY,
            display_name="Inventory MV Refresh",
            description=(
                "Refreshes inventory materialized views used by the Inventory V3 "
                "grid (SKU/ItemID Active/Sold counters)."
            ),
            enabled=True,
            interval_seconds=600,
        )
        db.add(worker)
        db.commit()
        db.refresh(worker)
    return worker


def _serialize_worker(worker: BackgroundWorker) -> InventoryMvWorkerDto:
    last_run_at: Optional[datetime] = worker.last_finished_at or worker.last_started_at
    last_run_iso = (
        last_run_at.astimezone(timezone.utc).isoformat() if last_run_at else None
    )

    return InventoryMvWorkerDto(
        worker_key=worker.worker_name,
        display_name=worker.display_name or "Inventory MV Refresh",
        description=worker.description,
        enabled=bool(worker.enabled),
        interval_seconds=int(worker.interval_seconds or 600),
        last_run_at=last_run_iso,
        last_run_status=worker.last_status,
        last_run_error=worker.last_error_message,
    )


@router.get(
    "/inventory-mv-refresh",
    response_model=InventoryMvWorkerDto,
    dependencies=[Depends(admin_required)],
)
async def get_inventory_mv_worker(
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required),  # noqa: ARG001
) -> InventoryMvWorkerDto:
    """Return current configuration and runtime info for the Inventory MV worker."""

    worker = _get_or_create_inventory_worker(db)
    return _serialize_worker(worker)


@router.put(
    "/inventory-mv-refresh",
    response_model=InventoryMvWorkerDto,
    dependencies=[Depends(admin_required)],
)
async def update_inventory_mv_worker(
    payload: InventoryMvWorkerUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required),  # noqa: ARG001
) -> InventoryMvWorkerDto:
    """Update enabled flag and/or interval_seconds for the Inventory MV worker."""

    worker = _get_or_create_inventory_worker(db)

    if payload.interval_seconds is not None:
        if payload.interval_seconds <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="interval_seconds_must_be_positive",
            )
        worker.interval_seconds = int(payload.interval_seconds)

    if payload.enabled is not None:
        worker.enabled = bool(payload.enabled)

    db.commit()
    db.refresh(worker)

    return _serialize_worker(worker)


class InventoryMvRunOnceResponse(BaseModel):
    status: str
    message: Optional[str] = None


@router.post(
    "/inventory-mv-refresh/run-once",
    response_model=InventoryMvRunOnceResponse,
    dependencies=[Depends(admin_required)],
)
async def run_inventory_mv_worker_once(
    db: Session = Depends(get_db),  # noqa: ARG001
    current_user: User = Depends(admin_required),  # noqa: ARG001
) -> InventoryMvRunOnceResponse:
    """Trigger a single refresh cycle of the inventory MV worker logic.

    This endpoint calls the shared run_inventory_mv_refresh_once() helper in
    the worker module, which executes the REFRESH MATERIALIZED VIEW statements
    and updates the BackgroundWorker status fields.
    """

    try:
        ok, error = run_inventory_mv_refresh_once()
    except Exception as exc:  # pragma: no cover - defensive
        logger.error(
            "[inventory-mv-refresh] run-once endpoint failed: %s", exc, exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="run_once_failed",
        ) from exc

    if ok:
        return InventoryMvRunOnceResponse(status="success")

    return InventoryMvRunOnceResponse(status="error", message=error or "unknown_error")
