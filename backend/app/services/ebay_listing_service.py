from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Tuple
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.models_sqlalchemy.models import EbayAccount, PartsDetail, PartsDetailLog, PartsDetailStatus
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
from app.services.ebay import ebay_service
from app.services.ebay_account_service import ebay_account_service


MAX_ITEMS_PER_EBAY_BULK_CALL = 25


@dataclass
class ListingCandidate:
    """Minimal listing candidate derived from a PartsDetail row."""

    row: PartsDetail
    sku: Optional[str]
    title: Optional[str]
    price: Optional[Decimal]


@dataclass
class ListingResult:
    """Outcome of attempting to publish a single listing candidate."""

    candidate: ListingCandidate
    success: bool
    listing_id: Optional[str] = None
    offer_id: Optional[str] = None
    error_message: Optional[str] = None
    error_payload: Optional[Dict[str, Any]] = None


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


def _build_listing_candidate(row: PartsDetail) -> ListingCandidate:
    """Map a PartsDetail ORM row into a ListingCandidate.

    For now we only project SKU, title and price fields that are needed for
    offer lookup and debug payloads. More fields (condition, shipping,
    pictures, etc.) can be added incrementally as the live path matures.
    """

    return ListingCandidate(
        row=row,
        sku=row.override_sku or row.sku,
        title=row.override_title,
        price=(row.override_price or row.price_to_change),
    )


def _resolve_account_and_token(
    db: Session,
    username: str,
    ebay_id: str,
) -> Tuple[Optional[EbayAccount], Optional[str], Optional[str]]:
    """Resolve EbayAccount + OAuth access token for a (username, ebay_id) group.

    Returns a triple ``(account, access_token, error_message)``. When
    ``error_message`` is not None, either ``account`` or ``access_token`` may
    be None and the caller should treat the whole batch as a business failure.
    """

    account: Optional[EbayAccount] = None

    # Preferred mapping: explicit ebay_id matches EbayAccount.id
    if ebay_id:
        account = db.query(EbayAccount).filter(EbayAccount.id == ebay_id).first()

    # Fallback: match by username when available
    if account is None and username:
        account = (
            db.query(EbayAccount)
            .filter(EbayAccount.username == username)
            .order_by(EbayAccount.connected_at.desc())
            .first()
        )

    if account is None:
        return None, None, (
            f"No active eBay account found for username={username or 'UNKNOWN'} "
            f"ebay_id={ebay_id or 'N/A'}"
        )

    token = ebay_account_service.get_token(db, account.id)
    access_token = token.access_token if token else None
    if not access_token:
        return (
            account,
            None,
            f"No active eBay token for account id={account.id} (username={account.username})",
        )

    return account, access_token, None


async def _publish_batch_live_for_account(
    *,
    account: EbayAccount,
    access_token: str,
    batch: List[PartsDetail],
    trace: WorkerDebugTrace,
) -> List[ListingResult]:
    """Publish a batch of candidates for a single account using live eBay APIs.

    This helper performs per-SKU ``getOffers`` lookups and a single
    ``bulk_publish_offer`` call for the resolved offers. It does **not**
    mutate the database; the caller is responsible for applying the
    returned ListingResult objects via _build_success_changes /
    _build_publish_failed_changes.
    """

    results: List[ListingResult] = []
    offer_ids: List[str] = []
    offer_to_candidate: Dict[str, ListingCandidate] = {}

    # 1) Map ORM rows to ListingCandidate objects and resolve offerIds per SKU.
    for row in batch:
        candidate = _build_listing_candidate(row)

        if not candidate.sku:
            results.append(
                ListingResult(
                    candidate=candidate,
                    success=False,
                    error_message="Missing SKU for listing candidate; cannot resolve offers",
                    error_payload={"reason": "missing_sku"},
                )
            )
            continue

        try:
            offers_response = await ebay_service.fetch_offers(
                access_token,
                sku=candidate.sku,
                filter_params={"limit": 200},
            )
        except HTTPException as exc:
            # Treat transport/auth errors as per-item failures while still
            # allowing the rest of the batch to proceed.
            detail = exc.detail
            msg = (
                f"fetch_offers failed for sku={candidate.sku}: "
                f"{detail if isinstance(detail, str) else str(detail)}"
            )
            results.append(
                ListingResult(
                    candidate=candidate,
                    success=False,
                    error_message=msg[:2000],
                    error_payload={"detail": detail},
                )
            )
            continue

        offers = offers_response.get("offers") or []
        chosen_offer: Optional[Dict[str, Any]] = None

        # Prefer an offer whose marketplaceId matches the account, when known.
        for off in offers:
            marketplace_id = off.get("marketplaceId") or off.get("marketplace_id")
            if account.marketplace_id and marketplace_id == account.marketplace_id:
                chosen_offer = off
                break

        if chosen_offer is None and offers:
            chosen_offer = offers[0]

        if chosen_offer is None:
            results.append(
                ListingResult(
                    candidate=candidate,
                    success=False,
                    error_message=f"No offers found for sku={candidate.sku}",
                    error_payload={"offers_response": offers_response},
                )
            )
            continue

        offer_id = str(chosen_offer.get("offerId") or "").strip()
        if not offer_id:
            results.append(
                ListingResult(
                    candidate=candidate,
                    success=False,
                    error_message=(
                        f"Selected offer for sku={candidate.sku} is missing offerId; "
                        "cannot publish"
                    ),
                    error_payload={"offer": chosen_offer},
                )
            )
            continue

        offer_ids.append(offer_id)
        offer_to_candidate[offer_id] = candidate

    if not offer_ids:
        # All candidates failed before reaching publish stage.
        return results

    # 2) Call bulk_publish_offer for resolved offers and record HTTP steps.
    request_body = {"requests": [{"offerId": oid} for oid in offer_ids]}
    http_req = WorkerDebugHttp(
        method="POST",
        url="/sell/inventory/v1/bulk_publish_offer",
        headers=_mask_headers({
            "Authorization": "Bearer ***",
            "Content-Type": "application/json",
        }),
        body=request_body,
    )
    trace.steps.append(
        _make_step(
            step_type="ebay-request",
            label="bulkPublishOffer",
            message=f"bulkPublishOffer for {len(offer_ids)} offers",
            http=http_req,
        )
    )

    try:
        status_code, payload = await ebay_service.bulk_publish_offers(
            access_token,
            offer_ids,
        )
    except HTTPException as exc:
        detail = exc.detail
        http_res = WorkerDebugHttp(
            method="POST",
            url="/sell/inventory/v1/bulk_publish_offer",
            headers=_mask_headers({"Content-Type": "application/json"}),
            body=detail,
            status_code=exc.status_code,
        )
        trace.steps.append(
            _make_step(
                step_type="ebay-response",
                label="bulkPublishOffer",
                message=f"bulkPublishOffer failed with HTTP {exc.status_code}",
                http=http_res,
            )
        )

        msg = detail if isinstance(detail, str) else str(detail)
        for oid, candidate in offer_to_candidate.items():
            results.append(
                ListingResult(
                    candidate=candidate,
                    success=False,
                    offer_id=oid,
                    error_message=(
                        f"bulkPublishOffer HTTP error {exc.status_code} for offerId={oid}: {msg}"
                    )[:2000],
                    error_payload={"detail": detail},
                )
            )
        return results

    http_res = WorkerDebugHttp(
        method="POST",
        url="/sell/inventory/v1/bulk_publish_offer",
        headers=_mask_headers({"Content-Type": "application/json"}),
        body=payload,
        status_code=status_code,
    )
    trace.steps.append(
        _make_step(
            step_type="ebay-response",
            label="bulkPublishOffer",
            message=f"bulkPublishOffer HTTP {status_code}",
            http=http_res,
        )
    )

    responses = (
        payload.get("responses")
        or payload.get("result")
        or payload.get("results")
        or []
    )
    seen_offers: set[str] = set()

    for item in responses:
        offer_id = str(item.get("offerId") or "").strip()
        if not offer_id or offer_id not in offer_to_candidate:
            continue
        seen_offers.add(offer_id)

        candidate = offer_to_candidate[offer_id]
        listing_id_val = item.get("listingId")
        listing_id = str(listing_id_val) if listing_id_val is not None else None

        item_status_code = item.get("statusCode")
        try:
            item_status_int = int(item_status_code) if item_status_code is not None else None
        except (TypeError, ValueError):
            item_status_int = None
        status_text = str(item.get("status") or "").upper()

        errors = item.get("errors") or []
        success = bool(listing_id) and not errors and (
            (item_status_int is not None and 200 <= item_status_int < 300)
            or status_text == "SUCCESS"
        )

        if success:
            results.append(
                ListingResult(
                    candidate=candidate,
                    success=True,
                    listing_id=listing_id,
                    offer_id=offer_id,
                    error_message=None,
                    error_payload=None,
                )
            )
        else:
            err_msg: Optional[str] = None
            if isinstance(errors, list) and errors:
                first = errors[0]
                if isinstance(first, dict):
                    err_msg = (
                        first.get("message")
                        or first.get("longMessage")
                        or str(first)
                    )
                else:
                    err_msg = str(first)

            if not err_msg:
                err_msg = (
                    f"bulkPublishOffer failed for offerId={offer_id} "
                    f"status={status_text or item_status_code}"
                )

            results.append(
                ListingResult(
                    candidate=candidate,
                    success=False,
                    offer_id=offer_id,
                    error_message=err_msg[:2000],
                    error_payload=item,
                )
            )

    # Any offers without explicit response entries are treated as failures.
    for oid, candidate in offer_to_candidate.items():
        if oid in seen_offers:
            continue
        results.append(
            ListingResult(
                candidate=candidate,
                success=False,
                offer_id=oid,
                error_message="bulkPublishOffer returned no response entry for this offerId",
                error_payload=None,
            )
        )

    return results


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

    The worker supports two modes controlled by ``settings.ebay_listing_mode``:

    - "stub" (default): do **not** call live eBay APIs; instead simulate
      bulkPublishOffer responses to validate DB mappings and the debug trace.
    - "live": resolve EbayAccount + OAuth token per (username, ebay_id)
      group, call Inventory/Offers APIs (getOffers + bulk_publish_offer) and
      update parts_detail / parts_detail_log based on real results.
    """

    job_id = uuid4().hex
    trace = WorkerDebugTrace(job_id=job_id, account=None, items_count=0, steps=[])

    listing_mode = (getattr(settings, "ebay_listing_mode", "stub") or "stub").lower()
    use_stub = listing_mode != "live"
    trace.steps.append(
        _make_step(
            step_type="info",
            label="mode",
            message=f"Listing worker mode={listing_mode}",
        )
    )

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

        resolved_account: Optional[EbayAccount] = None
        access_token: Optional[str] = None
        account_error: Optional[str] = None

        if not use_stub:
            resolved_account, access_token, account_error = _resolve_account_and_token(
                db,
                username or "",
                ebay_id or "",
            )
            if account_error:
                trace.steps.append(
                    _make_step(
                        step_type="error",
                        label="account",
                        message=account_error,
                        extra={"username": username, "ebay_id": ebay_id},
                    )
                )

        for batch_idx, batch in enumerate(batches, start=1):
            trace.steps.append(
                _make_step(
                    step_type="info",
                    label="batch",
                    message=f"Processing batch {batch_idx}/{len(batches)} for {account_label}",
                    extra={"batch_size": len(batch)},
                )
            )

            if use_stub:
                # 2a) Stubbed eBay payload and response (no live HTTP calls)
                request_body = {
                    "requests": [
                        {
                            "sku": (p.override_sku or p.sku),
                            "title": p.override_title,
                            "price": float(p.override_price or p.price_to_change or 0)
                            if (p.override_price or p.price_to_change) is not None
                            else None,
                        }
                        for p in batch
                    ]
                }
                http_req = WorkerDebugHttp(
                    method="POST",
                    url="/sell/inventory/v1/bulk_publish_offer (stub)",
                    headers=_mask_headers(
                        {"Authorization": "Bearer ***", "Content-Type": "application/json"}
                    ),
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

                # 3a) For each item, compute DB changes and optionally apply them.
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

                continue  # next batch

            # 2b) Live mode: use resolved account + token, or mark failures if missing
            now = _utc_now()

            if account_error or not access_token or not resolved_account:
                error_msg = account_error or "Missing eBay access token for account"
                for p in batch:
                    changes = _build_publish_failed_changes(
                        p,
                        error_message=error_msg,
                        error_payload={"reason": "account_resolution_failed"},
                        now=now,
                    )

                    db_change = WorkerDebugDbChange(
                        table_name="parts_detail",
                        row_id=p.id,
                        changes=changes,
                    )
                    trace.steps.append(
                        _make_step(
                            step_type="db-update",
                            label="parts_detail",
                            message=(
                                f"Mark parts_detail id={p.id} as PublishError "
                                "(account/token missing)"
                            ),
                            db_change=db_change,
                        )
                    )

                    log_row = _build_log_row_for_failure(p, error_msg, now=now)
                    if not req.dry_run:
                        _apply_changes(p, changes)
                        db.add(log_row)

                    log_change = WorkerDebugDbChange(
                        table_name="parts_detail_log",
                        row_id=0 if req.dry_run else -1,
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
                            message=(
                                "Insert publish-failure log for part_detail_id="
                                f"{p.id} (account/token missing)"
                            ),
                            db_change=log_change,
                        )
                    )

                    acct_failed += 1
                    total_failed += 1
                    total_processed += 1

                continue

            # Normal live path using real eBay APIs
            live_results = await _publish_batch_live_for_account(
                account=resolved_account,
                access_token=access_token,
                batch=batch,
                trace=trace,
            )

            now = _utc_now()
            for result in live_results:
                row = result.candidate.row

                if result.success and result.listing_id:
                    changes = _build_success_changes(
                        row,
                        listing_id=result.listing_id,
                        now=now,
                    )
                else:
                    err_msg = result.error_message or "Unknown eBay error"
                    changes = _build_publish_failed_changes(
                        row,
                        error_message=err_msg,
                        error_payload=result.error_payload or {},
                        now=now,
                    )

                db_change = WorkerDebugDbChange(
                    table_name="parts_detail",
                    row_id=row.id,
                    changes=changes,
                )
                trace.steps.append(
                    _make_step(
                        step_type="db-update",
                        label="parts_detail",
                        message=(
                            f"Update parts_detail id={row.id} for publish "
                            f"{'success' if result.success else 'failure'}"
                        ),
                        db_change=db_change,
                    )
                )

                if result.success and result.listing_id:
                    log_row = _build_log_row_for_success(
                        row,
                        listing_id=result.listing_id,
                        now=now,
                    )
                else:
                    log_row = _build_log_row_for_failure(
                        row,
                        error_message=result.error_message or "Unknown eBay error",
                        now=now,
                    )

                if not req.dry_run:
                    _apply_changes(row, changes)
                    db.add(log_row)

                log_change = WorkerDebugDbChange(
                    table_name="parts_detail_log",
                    row_id=0 if req.dry_run else -1,
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
                        message=(
                            "Insert publish-" + ("success" if result.success else "failure")
                            + f" log for part_detail_id={row.id}"
                        ),
                        db_change=log_change,
                    )
                )

                if result.success:
                    acct_success += 1
                    total_success += 1
                else:
                    acct_failed += 1
                    total_failed += 1
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
