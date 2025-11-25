from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models_sqlalchemy.models import PartsDetail, PartsDetailLog, PartsDetailStatus
from app.models.ebay_worker_debug import (
    ColumnChange,
    EbayListingDebugRequest,
    EbayListingDebugResponse,
    EbayListingDebugSummary,
    WorkerDebugDbChange,
    WorkerDebugHttp,
    WorkerDebugStep,
    WorkerDebugTrace,
)


MAX_ITEMS_PER_EBAY_BULK_CALL = 25


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _make_step(
    *,
    step_type: str,
    message: str,
    label: Optional[str] = None,
    http: Optional[WorkerDebugHttp] = None,
    db_change: Optional[WorkerDebugDbChange] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> WorkerDebugStep:
    return WorkerDebugStep(
        timestamp=_utc_now(),
        type=step_type,  # type: ignore[arg-type]
        label=label,
        message=message,
        http=http,
        db_change=db_change,
        extra=extra or {},
    )


def _mask_headers(headers: Dict[str, Any]) -> Dict[str, Any]:
    masked: Dict[str, Any] = {}
    for k, v in headers.items():
        lk = k.lower()
        if lk in {"authorization", "proxy-authorization"} or "token" in lk or "secret" in lk:
            masked[k] = "***"  # never expose raw tokens
        else:
            masked[k] = v
    return masked


def _group_by_account(parts: Iterable[PartsDetail]) -> Dict[Tuple[str, str], List[PartsDetail]]:
    groups: Dict[Tuple[str, str], List[PartsDetail]] = defaultdict(list)
    for row in parts:
        key = (row.username or "", row.ebay_id or "")
        groups[key].append(row)
    return groups


def _select_candidates_for_listing(
    db: Session,
    req: EbayListingDebugRequest,
) -> List[PartsDetail]:
    """Select candidate PartsDetail rows from Postgres.

    Selection rules (first approximation):
    - status_sku = CHECKED
    - item_id IS NULL
    - not frozen/cancelled
    - optional explicit ID filter from req.ids
    """

    q = db.query(PartsDetail)

    if req.ids:
        q = q.filter(PartsDetail.id.in_(req.ids))

    q = q.filter(
        PartsDetail.status_sku == PartsDetailStatus.CHECKED.value,
        PartsDetail.item_id.is_(None),
        (PartsDetail.freeze_listing_flag.is_(None)) | (PartsDetail.freeze_listing_flag.is_(False)),
        (PartsDetail.cancel_listing_flag.is_(None)) | (PartsDetail.cancel_listing_flag.is_(False)),
    )

    q = q.order_by(PartsDetail.id.asc()).limit(req.max_items)
    return list(q.all())


def _build_success_changes(
    row: PartsDetail,
    *,
    listing_id: str,
    now: datetime,
) -> Dict[str, ColumnChange]:
    """Compute column-level changes for a successful publish.

    This does not mutate the ORM object; the caller is responsible for
    applying `new` values when dry_run is False.
    """

    changes: Dict[str, ColumnChange] = {}

    def add(name: str, new: Any) -> None:
        old = getattr(row, name)
        if old != new:
            changes[name] = ColumnChange(old=old, new=new)

    add("item_id", listing_id)
    add("add_ack", "Success")
    add("add_timestamp", now)
    add("add_error", None)
    add("listing_status", "Active")
    add("item_listed_at", now)
    add("batch_success_flag", True)
    add("batch_success_message", {"operation": "bulkPublishOffer", "listingId": listing_id})
    add("batch_error_flag", False)
    add("batch_error_message", None)
    add("status_sku", PartsDetailStatus.LISTED_ACTIVE.value)
    add("status_updated_at", now)
    add("status_updated_by", "EBAY_WORKER")
    add("mark_as_listed_queue_flag", False)

    return changes


def _build_publish_failed_changes(
    row: PartsDetail,
    *,
    error_message: str,
    error_payload: Dict[str, Any],
    now: datetime,
) -> Dict[str, ColumnChange]:
    """Compute column-level changes for a failed publish (business/transport)."""

    changes: Dict[str, ColumnChange] = {}

    def add(name: str, new: Any) -> None:
        old = getattr(row, name)
        if old != new:
            changes[name] = ColumnChange(old=old, new=new)

    add("add_ack", "Failure")
    add("add_timestamp", now)
    add("add_error", error_message[:2000])
    add("batch_error_flag", True)
    add("batch_error_message", error_payload)
    add("batch_success_flag", False)
    add("batch_success_message", None)
    # Keep item_id NULL on failure.
    # Conservative default: mark as PublishError so worker does not loop forever.
    add("status_sku", PartsDetailStatus.PUBLISH_ERROR.value)
    add("status_updated_at", now)
    add("status_updated_by", "EBAY_WORKER")
    add("mark_as_listed_queue_flag", False)

    return changes


def _apply_changes(row: PartsDetail, changes: Dict[str, ColumnChange]) -> None:
    for name, change in changes.items():
        setattr(row, name, change.new)


def _build_log_row_for_success(row: PartsDetail, listing_id: str, now: datetime) -> PartsDetailLog:
    return PartsDetailLog(
        part_detail_id=row.id,
        sku=row.override_sku or row.sku,
        part=row.override_title,
        price=row.override_price or row.price_to_change,
        previous_price=row.price_to_change_one_time,
        price_updated_at=row.listing_time_updated,
        category=None,
        description=row.override_description,
        checked_status="EBAY_LISTED",
        checked_at=now,
        checked_by="EBAY_WORKER",
        record_status="ActiveListing",
        alert_flag=False,
        alert_message=f"Published to eBay, ItemID={listing_id}",
        log_created_at=now,
        log_created_by="EBAY_WORKER",
    )


def _build_log_row_for_failure(row: PartsDetail, error_message: str, now: datetime) -> PartsDetailLog:
    return PartsDetailLog(
        part_detail_id=row.id,
        sku=row.override_sku or row.sku,
        part=row.override_title,
        price=row.override_price or row.price_to_change,
        previous_price=row.price_to_change_one_time,
        price_updated_at=row.listing_time_updated,
        category=None,
        description=row.override_description,
        checked_status="PublishFailed",
        checked_at=now,
        checked_by="EBAY_WORKER",
        record_status="Error",
        alert_flag=True,
        alert_message=error_message[:2000],
        log_created_at=now,
        log_created_by="EBAY_WORKER",
    )


async def run_listing_worker_debug(
    db: Session,
    req: EbayListingDebugRequest,
) -> EbayListingDebugResponse:
    """Run a single debug pass of the eBay listing worker.

    NOTE: The current implementation uses a **stubbed** eBay bulk publish
    flow: it does not yet call the real Inventory/Offer APIs. Instead it
    simulates per-item successes so that we can validate DB mappings and the
    debug trace end-to-end. Real HTTP integration will be added as a
    follow-up, reusing the same debug trace structures.
    """

    job_id = uuid4().hex
    trace = WorkerDebugTrace(job_id=job_id, account=None, items_count=0, steps=[])

    # 1) Select candidates
    candidates = _select_candidates_for_listing(db, req)
    trace.items_count = len(candidates)
    trace.steps.append(
        _make_step(
            step_type="db-select",
            label="select candidates",
            message=f"Selected {len(candidates)} parts_detail rows for listing",
            extra={"ids": [c.id for c in candidates]},
        )
    )

    if not candidates:
        summary = EbayListingDebugSummary(
            items_selected=0,
            items_processed=0,
            items_success=0,
            items_failed=0,
            accounts=[],
        )
        return EbayListingDebugResponse(trace=trace, summary=summary)

    groups = _group_by_account(candidates)
    if len(groups) == 1:
        (username, ebay_id), _ = next(iter(groups.items()))
        trace.account = f"{username or 'UNKNOWN'} (ebay_id={ebay_id or 'N/A'})"

    total_processed = 0
    total_success = 0
    total_failed = 0
    account_summaries: List[Dict[str, Any]] = []

    for (username, ebay_id), rows in groups.items():
        account_label = f"{username or 'UNKNOWN'} (ebay_id={ebay_id or 'N/A'})"
        batches: List[List[PartsDetail]] = [
            rows[i : i + MAX_ITEMS_PER_EBAY_BULK_CALL]
            for i in range(0, len(rows), MAX_ITEMS_PER_EBAY_BULK_CALL)
        ]

        acct_success = 0
        acct_failed = 0

        for batch_idx, batch in enumerate(batches, start=1):
            trace.steps.append(
                _make_step(
                    step_type="info",
                    label="batch",
                    message=f"Processing batch {batch_idx}/{len(batches)} for {account_label}",
                    extra={"batch_size": len(batch)},
                )
            )

            # 2) Build stubbed eBay payload and response
            # In dry_run or stub mode we only log what *would* be sent.
            request_body = {
                "requests": [
                    {
                        "sku": (p.override_sku or p.sku),
                        "title": p.override_title,
                        "price": float(p.override_price or p.price_to_change or 0) if (p.override_price or p.price_to_change) is not None else None,
                    }
                    for p in batch
                ]
            }
            http_req = WorkerDebugHttp(
                method="POST",
                url="/sell/inventory/v1/bulk_publish_offer (stub)",
                headers=_mask_headers({"Authorization": "Bearer ***", "Content-Type": "application/json"}),
                body=request_body,
            )
            trace.steps.append(
                _make_step(
                    step_type="ebay-request",
                    label="bulkPublishOffer",
                    message=f"Stubbed bulk publish request for {len(batch)} offers",
                    http=http_req,
                )
            )

            # Stubbed per-item results: mark everything as success with fake listing ids
            now = _utc_now()
            fake_response_body: Dict[str, Any] = {
                "results": [
                    {
                        "sku": (p.override_sku or p.sku),
                        "offerId": f"OFFER-{p.id}",
                        "listingId": f"STUB-{p.id}",
                        "status": "SUCCESS",
                    }
                    for p in batch
                ]
            }
            http_res = WorkerDebugHttp(
                method="POST",
                url="/sell/inventory/v1/bulk_publish_offer (stub)",
                headers=_mask_headers({"Content-Type": "application/json"}),
                body=fake_response_body,
                status_code=200,
                duration_ms=0,
            )
            trace.steps.append(
                _make_step(
                    step_type="ebay-response",
                    label="bulkPublishOffer",
                    message="Stubbed 200 OK bulk publish response",
                    http=http_res,
                )
            )

            # 3) For each item, compute DB changes and optionally apply them.
            for p in batch:
                listing_id = f"STUB-{p.id}"
                success_changes = _build_success_changes(p, listing_id=listing_id, now=now)

                db_change = WorkerDebugDbChange(
                    table_name="parts_detail",
                    row_id=p.id,
                    changes=success_changes,
                )
                trace.steps.append(
                    _make_step(
                        step_type="db-update",
                        label="parts_detail",
                        message=f"Update parts_detail id={p.id} for publish success",
                        db_change=db_change,
                    )
                )

                log_row = _build_log_row_for_success(p, listing_id=listing_id, now=now)
                if not req.dry_run:
                    _apply_changes(p, success_changes)
                    db.add(log_row)

                # For dry_run we still show the INSERT shape in the trace.
                log_change = WorkerDebugDbChange(
                    table_name="parts_detail_log",
                    row_id=0 if req.dry_run else -1,  # concrete id only known after flush
                    changes={
                        "sku": ColumnChange(old=None, new=log_row.sku),
                        "checked_status": ColumnChange(old=None, new=log_row.checked_status),
                        "record_status": ColumnChange(old=None, new=log_row.record_status),
                        "alert_flag": ColumnChange(old=None, new=log_row.alert_flag),
                        "alert_message": ColumnChange(old=None, new=log_row.alert_message),
                    },
                )
                trace.steps.append(
                    _make_step(
                        step_type="log-insert",
                        label="parts_detail_log",
                        message=f"Insert publish-success log for part_detail_id={p.id}",
                        db_change=log_change,
                    )
                )

                acct_success += 1
                total_success += 1
                total_processed += 1

        account_summaries.append(
            {
                "username": username,
                "ebay_id": ebay_id,
                "items": len(rows),
                "success": acct_success,
                "failed": acct_failed,
            }
        )

    if not req.dry_run:
        db.flush()
        db.commit()

    summary = EbayListingDebugSummary(
        items_selected=len(candidates),
        items_processed=total_processed,
        items_success=total_success,
        items_failed=total_failed,
        accounts=account_summaries,
    )

    trace.steps.append(
        _make_step(
            step_type="info",
            label="summary",
            message=(
                f"Job complete: selected={len(candidates)} processed={total_processed} "
                f"success={total_success} failed={total_failed}"
            ),
        )
    )

    return EbayListingDebugResponse(trace=trace, summary=summary)
