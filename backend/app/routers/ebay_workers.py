from __future__ import annotations

from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.services.auth import get_current_active_user
from app.models.user import User
from app.models_sqlalchemy import get_db
from app.models_sqlalchemy.models import EbayAccount
from app.models_sqlalchemy.ebay_workers import EbaySyncState, EbayWorkerRun, EbayApiWorkerLog
from app.services.ebay_account_service import ebay_account_service
from app.utils.logger import logger

from app.services.ebay_workers.state import (
    are_workers_globally_enabled,
    set_workers_globally_enabled,
    get_or_create_sync_state,
)
from app.services.ebay_workers.orders_worker import run_orders_worker_for_account
from app.services.ebay_workers.transactions_worker import run_transactions_worker_for_account
from app.services.ebay_workers.offers_worker import run_offers_worker_for_account
from app.services.ebay_workers.messages_worker import run_messages_worker_for_account
from app.services.ebay_workers.active_inventory_worker import run_active_inventory_worker_for_account
from app.services.ebay_workers.cases_worker import run_cases_worker_for_account
from app.services.ebay_workers.finances_worker import run_finances_worker_for_account
from app.services.ebay_workers.purchases_worker import run_purchases_worker_for_account
from app.services.ebay_workers.inquiries_worker import run_inquiries_worker_for_account
from app.services.ebay_workers.runs import get_active_run


router = APIRouter(prefix="/ebay/workers", tags=["ebay_workers"])


class WorkerConfigItem(BaseModel):
    api_family: str
    enabled: bool
    cursor_type: Optional[str] = None
    cursor_value: Optional[str] = None
    last_run_at: Optional[str] = None
    last_error: Optional[str] = None
    last_run_status: Optional[str] = None
    last_run_started_at: Optional[str] = None
    last_run_finished_at: Optional[str] = None
    last_run_summary: Optional[Dict[str, Any]] = None


class WorkerConfigResponse(BaseModel):
    workers_enabled: bool
    account: Dict[str, Any]
    workers: List[WorkerConfigItem]


class UpdateWorkerConfigRequest(BaseModel):
    api_family: str
    enabled: bool


class GlobalToggleRequest(BaseModel):
    workers_enabled: bool


class WorkerScheduleRun(BaseModel):
    run_at: str
    window_from: str | None
    window_to: str | None


class WorkerScheduleItem(BaseModel):
    api_family: str
    enabled: bool
    overlap_minutes: int | None = None
    initial_backfill_days: int | None = None
    runs: List[WorkerScheduleRun]


class WorkerScheduleResponse(BaseModel):
    account: Dict[str, Any]
    interval_minutes: int
    hours: int
    workers: List[WorkerScheduleItem]


@router.get("/config", response_model=WorkerConfigResponse)
async def get_worker_config(
    account_id: str = Query(..., description="eBay account id"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Return worker configuration and last run info for a given eBay account."""

    account: EbayAccount | None = ebay_account_service.get_account(db, account_id)
    if not account or account.org_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    workers_enabled = are_workers_globally_enabled(db)

    # Load existing sync state rows for this account and index by api_family
    existing_states: List[EbaySyncState] = (
        db.query(EbaySyncState)
        .filter(EbaySyncState.ebay_account_id == account_id)
        .all()
    )

    states_by_api: Dict[str, EbaySyncState] = {s.api_family: s for s in existing_states}

    # Ensure we have at least Orders / Transactions / Offers / Messages /
    # Active Inventory / Cases / Inquiries / Finances / Buyer workers
    # configured so they always appear in the Workers control UI for this
    # account.
    ensured_families = [
        "orders",
        "transactions",
        "offers",
        "messages",
        "active_inventory",
        "cases",
        "inquiries",
        "finances",
        "buyer",
    ]
    ebay_user_id = account.ebay_user_id or "unknown"
    for api_family in ensured_families:
        if api_family not in states_by_api:
            states_by_api[api_family] = get_or_create_sync_state(
                db,
                ebay_account_id=account_id,
                ebay_user_id=ebay_user_id,
                api_family=api_family,
            )

    # Use a stable ordering for display purposes
    ordered_api_families = sorted(states_by_api.keys())
    states: List[EbaySyncState] = [states_by_api[api] for api in ordered_api_families]

    items: List[WorkerConfigItem] = []
    for state in states:
        # Last run info
        last_run: Optional[EbayWorkerRun] = (
            db.query(EbayWorkerRun)
            .filter(
                EbayWorkerRun.ebay_account_id == account_id,
                EbayWorkerRun.api_family == state.api_family,
            )
            .order_by(EbayWorkerRun.started_at.desc())
            .first()
        )

        items.append(
            WorkerConfigItem(
                api_family=state.api_family,
                enabled=state.enabled,
                cursor_type=state.cursor_type,
                cursor_value=state.cursor_value,
                last_run_at=state.last_run_at.isoformat() if state.last_run_at else None,
                last_error=state.last_error,
                last_run_status=last_run.status if last_run else None,
                last_run_started_at=last_run.started_at.isoformat() if last_run and last_run.started_at else None,
                last_run_finished_at=last_run.finished_at.isoformat() if last_run and last_run.finished_at else None,
                last_run_summary=last_run.summary_json if last_run and last_run.summary_json else None,
            )
        )

    return WorkerConfigResponse(
        workers_enabled=workers_enabled,
        account={
            "id": account.id,
            "ebay_user_id": account.ebay_user_id,
            "username": account.username,
            "house_name": account.house_name,
        },
        workers=items,
    )


@router.post("/config")
async def update_worker_config(
    payload: UpdateWorkerConfigRequest,
    account_id: str = Query(..., description="eBay account id"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Enable/disable a specific worker (api_family) for an account."""

    account: EbayAccount | None = ebay_account_service.get_account(db, account_id)
    if not account or account.org_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    state = get_or_create_sync_state(
        db,
        ebay_account_id=account_id,
        ebay_user_id=account.ebay_user_id,
        api_family=payload.api_family,
    )
    state.enabled = payload.enabled
    db.commit()

    logger.info(
        f"Worker config updated account={account_id} api={payload.api_family} enabled={payload.enabled}"
    )

    return {"status": "ok"}


@router.get("/global-config")
async def get_global_worker_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    workers_enabled = are_workers_globally_enabled(db)
    return {"workers_enabled": workers_enabled}


@router.post("/global-toggle")
async def toggle_global_workers(
    payload: GlobalToggleRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    cfg = set_workers_globally_enabled(db, payload.workers_enabled)
    logger.info(f"Global workers_enabled set to {cfg.workers_enabled}")
    return {"workers_enabled": cfg.workers_enabled}


@router.post("/run")
async def run_worker_once(
    account_id: str = Query(..., description="eBay account id"),
    api: str = Query("orders", description="API family to run (e.g. 'orders', 'transactions')"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):

    if not are_workers_globally_enabled(db):
        return {"status": "skipped", "reason": "workers_disabled"}

    if api not in {"orders", "transactions", "offers", "messages", "active_inventory", "cases", "inquiries", "finances", "buyer"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported api_family")

    account: EbayAccount | None = ebay_account_service.get_account(db, account_id)
    if not account or account.org_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    # Dispatch by API family with robust error handling so the client always
    # gets a structured response instead of a generic 5xx/502.
    try:
        if api == "orders":
            run_id = await run_orders_worker_for_account(account_id)
            api_family = "orders"
        elif api == "transactions":
            run_id = await run_transactions_worker_for_account(account_id)
            api_family = "transactions"
        elif api == "offers":
            run_id = await run_offers_worker_for_account(account_id)
            api_family = "offers"
        elif api == "messages":
            run_id = await run_messages_worker_for_account(account_id)
            api_family = "messages"
        elif api == "active_inventory":
            run_id = await run_active_inventory_worker_for_account(account_id)
            api_family = "active_inventory"
        elif api == "cases":
            run_id = await run_cases_worker_for_account(account_id)
            api_family = "cases"
        elif api == "inquiries":
            run_id = await run_inquiries_worker_for_account(account_id)
            api_family = "inquiries"
        elif api == "finances":
            run_id = await run_finances_worker_for_account(account_id)
            api_family = "finances"
        elif api == "buyer":
            run_id = await run_purchases_worker_for_account(account_id)
            api_family = "buyer"
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported api_family")
    except HTTPException:
        # Preserve explicit HTTP errors (e.g. bad api_family).
        raise
    except Exception as exc:
        # Log and surface a clear error message instead of propagating a 500.
        logger.error(f"Failed to start worker run account={account_id} api={api}: {exc}", exc_info=True)
        return {
            "status": "error",
            "api_family": api,
            "error_message": str(exc),
        }

    if not run_id:
        active = get_active_run(db, ebay_account_id=account_id, api_family=api_family)
        if active:
            return {"status": "skipped", "reason": "already_running", "run_id": active.id}
        return {"status": "skipped", "reason": "not_started"}

    return {"status": "started", "run_id": run_id, "api_family": api_family}


@router.get("/runs")
async def list_worker_runs(
    account_id: str = Query(..., description="eBay account id"),
    api: Optional[str] = Query(None, description="Filter by api_family"),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """List recent worker runs for an account (optionally filtered by api_family)."""

    account: EbayAccount | None = ebay_account_service.get_account(db, account_id)
    if not account or account.org_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    query = db.query(EbayWorkerRun).filter(EbayWorkerRun.ebay_account_id == account_id)
    if api:
        query = query.filter(EbayWorkerRun.api_family == api)
    runs = (
        query.order_by(EbayWorkerRun.started_at.desc()).limit(limit).all()
    )

    result = []
    for r in runs:
        result.append(
            {
                "id": r.id,
                "api_family": r.api_family,
                "status": r.status,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                "summary": r.summary_json,
            }
        )

    return {"runs": result}


@router.get("/schedule", response_model=WorkerScheduleResponse)
async def get_worker_schedule(
    account_id: str = Query(..., description="eBay account id"),
    hours: int = Query(5, ge=1, le=24, description="How many hours ahead to simulate"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Return a simulated schedule of worker runs and windows for the next N hours.

    This does *not* mutate any state; it simply projects what windows each
    worker would use on future 5-minute runs, based on the current cursor.
    """

    account: EbayAccount | None = ebay_account_service.get_account(db, account_id)
    if not account or account.org_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    # Load or create sync states for known workers so they always appear.
    ensured_families = [
        "orders",
        "transactions",
        "offers",
        "messages",
        "active_inventory",
        "cases",
        "inquiries",
        "finances",
        "buyer",
    ]
    ebay_user_id = account.ebay_user_id or "unknown"

    existing_states: List[EbaySyncState] = (
        db.query(EbaySyncState)
        .filter(EbaySyncState.ebay_account_id == account_id)
        .all()
    )
    states_by_api: Dict[str, EbaySyncState] = {s.api_family: s for s in existing_states}

    for api_family in ensured_families:
        if api_family not in states_by_api:
            states_by_api[api_family] = get_or_create_sync_state(
                db,
                ebay_account_id=account_id,
                ebay_user_id=ebay_user_id,
                api_family=api_family,
            )

    # Per-API overlap/backfill configuration (mirrors worker constants).
    overlap_by_api: Dict[str, int] = {
        "orders": 60,
        "transactions": 60,
        "finances": 60,
        "cases": 60,
        "inquiries": 60,
        "offers": 360,
        "messages": 360,
    }
    backfill_by_api: Dict[str, int] = {
        "orders": 90,
        "transactions": 90,
        "finances": 90,
        "cases": 90,
        "inquiries": 90,
        "offers": 90,
        "messages": 90,
    }

    interval_minutes = 5
    total_runs = hours * (60 // interval_minutes)

    from datetime import datetime, timezone, timedelta

    now = datetime.now(timezone.utc)

    def compute_window_from_cursor(
        cursor_value: str | None,
        *,
        now_dt: datetime,
        overlap_min: int,
        backfill_days: int,
    ) -> tuple[datetime, datetime]:
        """Pure version of compute_sync_window for schedule simulation."""

        window_to = now_dt
        if cursor_value:
            raw = cursor_value
            try:
                if raw.endswith("Z"):
                    raw = raw.replace("Z", "+00:00")
                cursor_dt = datetime.fromisoformat(raw)
            except Exception:
                cursor_dt = window_to - timedelta(days=backfill_days)
            window_from_dt = cursor_dt - timedelta(minutes=overlap_min)
        else:
            window_from_dt = window_to - timedelta(days=backfill_days)
        return window_from_dt, window_to

    worker_items: List[WorkerScheduleItem] = []

    for api_family, state in sorted(states_by_api.items()):
        enabled = bool(state.enabled)

        # Active inventory is a snapshot worker – no date window, but we still
        # show the planned run times.
        if api_family == "active_inventory":
            runs: List[WorkerScheduleRun] = []
            for i in range(total_runs):
                run_at_dt = now + timedelta(minutes=interval_minutes * (i + 1))
                run_at_iso = run_at_dt.replace(microsecond=0).isoformat() + "Z"
                runs.append(
                    WorkerScheduleRun(
                        run_at=run_at_iso,
                        window_from=None,
                        window_to=None,
                    )
                )

            worker_items.append(
                WorkerScheduleItem(
                    api_family=api_family,
                    enabled=enabled,
                    overlap_minutes=None,
                    initial_backfill_days=None,
                    runs=runs,
                )
            )
            continue

        overlap = overlap_by_api.get(api_family, 60)
        backfill = backfill_by_api.get(api_family, 90)

        # Simulate future windows by evolving a local cursor.
        cursor_value = state.cursor_value
        api_runs: List[WorkerScheduleRun] = []
        for i in range(total_runs):
            run_at_dt = now + timedelta(minutes=interval_minutes * (i + 1))
            window_from_dt, window_to_dt = compute_window_from_cursor(
                cursor_value,
                now_dt=run_at_dt,
                overlap_min=overlap,
                backfill_days=backfill,
            )

            from_iso = window_from_dt.replace(microsecond=0).isoformat() + "Z"
            to_iso = window_to_dt.replace(microsecond=0).isoformat() + "Z"

            api_runs.append(
                WorkerScheduleRun(
                    run_at=run_at_dt.replace(microsecond=0).isoformat() + "Z",
                    window_from=from_iso,
                    window_to=to_iso,
                )
            )

            # Next run will treat this run's window_to as the new cursor.
            cursor_value = to_iso

        worker_items.append(
            WorkerScheduleItem(
                api_family=api_family,
                enabled=enabled,
                overlap_minutes=overlap,
                initial_backfill_days=backfill,
                runs=api_runs,
            )
        )

    return WorkerScheduleResponse(
        account={
            "id": account.id,
            "ebay_user_id": account.ebay_user_id,
            "username": account.username,
            "house_name": account.house_name,
        },
        interval_minutes=interval_minutes,
        hours=hours,
        workers=worker_items,
    )


@router.get("/logs/{run_id}")
async def get_worker_logs(
    run_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Return detailed worker logs for a specific run_id."""

    # Ensure the run belongs to one of the current user's accounts
    run: EbayWorkerRun | None = db.query(EbayWorkerRun).filter(EbayWorkerRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

    account: EbayAccount | None = ebay_account_service.get_account(db, run.ebay_account_id)
    if not account or account.org_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")

    logs: List[EbayApiWorkerLog] = (
        db.query(EbayApiWorkerLog)
        .filter(EbayApiWorkerLog.run_id == run_id)
        .order_by(EbayApiWorkerLog.timestamp.asc())
        .all()
    )

    items = []
    for entry in logs:
        items.append(
            {
                "id": entry.id,
                "event_type": entry.event_type,
                "timestamp": entry.timestamp.isoformat() if entry.timestamp else None,
                "details": entry.details_json or {},
            }
        )

    return {
        "run": {
            "id": run.id,
            "api_family": run.api_family,
            "status": run.status,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "summary": run.summary_json,
        },
        "logs": items,
    }


# Note: a full run-cycle endpoint (for all accounts) will be added later once
# we have a cheap way to enumerate all active accounts. For now the frontend or
# external scheduler can call /run per account.
