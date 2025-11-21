from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import asc, desc, or_, text, cast, Text as SAText
from sqlalchemy.orm import Session

from app.models_sqlalchemy import get_db
from app.models_sqlalchemy.models import (
    ShippingJob,
    ShippingPackage,
    ShippingLabel,
    ShippingStatusLog,
    ShippingJobStatus,
    ShippingStatusSource,
    ShippingLabelProvider,
    EbayAccount,
)
from app.services.auth import get_current_user
from app.models.user import User as UserModel


router = APIRouter(prefix="/api/shipping", tags=["shipping"])


class ShippingJobFromOrder(BaseModel):
    ebay_account_id: Optional[str] = Field(None, description="ID of ebay_accounts row, if known")
    ebay_order_id: str = Field(..., description="eBay orderId from Fulfillment API")
    ebay_order_line_item_ids: Optional[List[str]] = Field(
        default=None,
        description="Optional explicit list of lineItemId values",
    )


class JobsFromOrdersRequest(BaseModel):
    orders: List[ShippingJobFromOrder]


class BulkPackageUpdateItem(BaseModel):
    shippingJobId: str
    weightOz: Optional[float] = None
    lengthIn: Optional[float] = None
    widthIn: Optional[float] = None
    heightIn: Optional[float] = None
    packageType: Optional[str] = None
    carrierPreference: Optional[str] = None


class StatusUpdateRequest(BaseModel):
    status: ShippingJobStatus
    reason: Optional[str] = None
    source: Optional[ShippingStatusSource] = None


class ManualLabelRequest(BaseModel):
    shippingJobId: str
    trackingNumber: str
    carrier: str
    serviceName: str
    labelUrl: Optional[str] = None
    labelCostAmount: Optional[float] = None
    labelCostCurrency: Optional[str] = "USD"
    labelFileType: Optional[str] = "pdf"


class VoidLabelRequest(BaseModel):
    voided: bool = True


def _serialize_ship_to_summary(addr: Optional[Dict[str, Any]]) -> Optional[str]:
    if not addr:
        return None
    # eBay shipTo has structure { fullName, contactAddress: { city, stateOrProvince, postalCode, countryCode } }
    full_name = addr.get("fullName") or addr.get("name")
    contact = addr.get("contactAddress") or {}
    city = contact.get("city") or addr.get("city")
    state = contact.get("stateOrProvince") or addr.get("stateOrProvince")
    postal = contact.get("postalCode") or addr.get("postalCode")
    country = contact.get("countryCode") or addr.get("countryCode")
    parts = [p for p in [full_name, city, state, postal, country] if p]
    return ", ".join(parts) if parts else None


def _job_to_row(job: ShippingJob) -> Dict[str, Any]:
    label: Optional[ShippingLabel] = job.label
    ship_to = job.ship_to_address or {}

    return {
        "id": job.id,
        "ebay_account_id": job.ebay_account_id,
        "ebay_order_id": job.ebay_order_id,
        "ebay_order_line_item_ids": job.ebay_order_line_item_ids or [],
        "buyer_user_id": job.buyer_user_id,
        "buyer_name": job.buyer_name,
        "ship_to_address": ship_to,
        "ship_to_summary": _serialize_ship_to_summary(ship_to),
        "warehouse_id": job.warehouse_id,
        "storage_ids": job.storage_ids or [],
        "status": job.status.value if job.status else None,
        "label": {
            "id": label.id,
            "tracking_number": label.tracking_number,
            "carrier": label.carrier,
            "service_name": label.service_name,
            "voided": label.voided,
        }
        if label
        else None,
        "paid_time": job.paid_time.isoformat() if job.paid_time else None,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
    }


@router.get("/awaiting")
async def list_awaiting_shipment(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    include_picking: bool = Query(True, description="Include PICKING jobs in the queue"),
    warehouse_id: Optional[str] = None,
    ebay_account_id: Optional[str] = None,
    search: Optional[str] = Query(None, description="Search by order id, buyer, or storage"),
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Return jobs that are awaiting shipment (status NEW and optionally PICKING).

    The result includes basic label info if a job is already linked to a label.
    """

    # Scope jobs to accounts belonging to the current org/user when possible.
    q = (
        db.query(ShippingJob)
        .outerjoin(EbayAccount, ShippingJob.ebay_account_id == EbayAccount.id)
        .filter(or_(EbayAccount.org_id == current_user.id, ShippingJob.ebay_account_id.is_(None)))
    )

    statuses = [ShippingJobStatus.NEW]
    if include_picking:
        statuses.append(ShippingJobStatus.PICKING)
    q = q.filter(ShippingJob.status.in_(statuses))

    if warehouse_id:
        q = q.filter(ShippingJob.warehouse_id == warehouse_id)

    if ebay_account_id:
        q = q.filter(ShippingJob.ebay_account_id == ebay_account_id)

    if search:
        like = f"%{search}%"
        q = q.filter(
            or_(
                ShippingJob.ebay_order_id.ilike(like),
                ShippingJob.buyer_user_id.ilike(like),
                ShippingJob.buyer_name.ilike(like),
                cast(ShippingJob.storage_ids, SAText).ilike(like),
            )
        )

    total = q.count()
    q = q.order_by(desc(ShippingJob.paid_time), desc(ShippingJob.created_at))
    jobs: List[ShippingJob] = q.offset(offset).limit(limit).all()

    rows = [_job_to_row(job) for job in jobs]
    return {"rows": rows, "limit": limit, "offset": offset, "total": total}


@router.post("/jobs/from-orders")
async def create_jobs_from_orders(
    payload: JobsFromOrdersRequest,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Create or update ShippingJob rows from ebay_orders records.

    This endpoint is designed for workers that know which orders are ready to
    ship. It is tolerant of missing ebay_orders data and will create minimal
    jobs when necessary.
    """

    created = 0
    updated = 0

    for item in payload.orders:
        if not item.ebay_order_id:
            continue

        job: Optional[ShippingJob] = (
            db.query(ShippingJob)
            .filter(
                ShippingJob.ebay_order_id == item.ebay_order_id,
                ShippingJob.ebay_account_id == item.ebay_account_id,
            )
            .one_or_none()
        )

        buyer_user_id: Optional[str] = None
        buyer_name: Optional[str] = None
        ship_to_address: Optional[Dict[str, Any]] = None
        paid_time: Optional[datetime] = None

        # Best-effort lookup from ebay_orders table (normalized orders).
        try:
            params: Dict[str, Any] = {"order_id": item.ebay_order_id}
            sql = "SELECT order_data, creation_date, buyer_username FROM ebay_orders WHERE order_id = :order_id"
            if item.ebay_account_id:
                sql += " AND ebay_account_id = :ebay_account_id"
                params["ebay_account_id"] = item.ebay_account_id
            row = db.execute(text(sql), params).fetchone()
            if row is not None:
                m = row._mapping
                paid_time = m.get("creation_date") or paid_time
                buyer_user_id = m.get("buyer_username") or buyer_user_id
                raw_data = m.get("order_data")
                parsed: Optional[Dict[str, Any]] = None
                if isinstance(raw_data, dict):
                    parsed = raw_data
                elif isinstance(raw_data, str):
                    try:
                        parsed = json.loads(raw_data)
                    except Exception:
                        parsed = None
                if isinstance(parsed, dict):
                    buyer = parsed.get("buyer") or {}
                    buyer_user_id = buyer.get("username") or buyer_user_id
                    ship_to = (
                        (parsed.get("fulfillmentStartInstructions") or [{}])[0]
                        .get("shippingStep", {})
                        .get("shipTo")
                    )
                    if isinstance(ship_to, dict):
                        ship_to_address = ship_to
                        buyer_name = ship_to.get("fullName") or buyer_name
        except Exception:
            # Do not break workers if ebay_orders shape is unexpected.
            pass

        now = datetime.utcnow()

        if job is None:
            job = ShippingJob(
                id=str(uuid.uuid4()),
                ebay_account_id=item.ebay_account_id,
                ebay_order_id=item.ebay_order_id,
                ebay_order_line_item_ids=item.ebay_order_line_item_ids or [],
                buyer_user_id=buyer_user_id,
                buyer_name=buyer_name,
                ship_to_address=ship_to_address,
                warehouse_id=None,
                storage_ids=[],
                status=ShippingJobStatus.NEW,
                paid_time=paid_time,
                created_at=now,
                updated_at=now,
                created_by=current_user.id,
            )
            db.add(job)
            created += 1
        else:
            # Update in-place but do not regress status if job already progressed.
            if item.ebay_order_line_item_ids:
                job.ebay_order_line_item_ids = item.ebay_order_line_item_ids
            if buyer_user_id:
                job.buyer_user_id = buyer_user_id
            if buyer_name:
                job.buyer_name = buyer_name
            if ship_to_address:
                job.ship_to_address = ship_to_address
            if paid_time and not job.paid_time:
                job.paid_time = paid_time
            job.updated_at = now
            updated += 1

    db.commit()
    return {"created": created, "updated": updated, "total": len(payload.orders)}


@router.post("/packages/bulk-update")
async def bulk_update_packages(
    items: List[BulkPackageUpdateItem],
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Create or update ShippingPackage rows for the given jobs."""

    updated = 0

    for item in items:
        job: Optional[ShippingJob] = db.query(ShippingJob).filter(ShippingJob.id == item.shippingJobId).one_or_none()
        if not job:
            continue

        pkg: Optional[ShippingPackage] = (
            db.query(ShippingPackage)
            .filter(ShippingPackage.shipping_job_id == job.id)
            .order_by(asc(ShippingPackage.created_at))
            .first()
        )
        now = datetime.utcnow()
        if pkg is None:
            pkg = ShippingPackage(
                id=str(uuid.uuid4()),
                shipping_job_id=job.id,
                created_at=now,
                updated_at=now,
            )
            db.add(pkg)

        if item.weightOz is not None:
            pkg.weight_oz = item.weightOz
        if item.lengthIn is not None:
            pkg.length_in = item.lengthIn
        if item.widthIn is not None:
            pkg.width_in = item.widthIn
        if item.heightIn is not None:
            pkg.height_in = item.heightIn
        if item.packageType is not None:
            pkg.package_type = item.packageType
        if item.carrierPreference is not None:
            pkg.carrier_preference = item.carrierPreference

        pkg.updated_at = now
        updated += 1

    db.commit()
    return {"updated": updated}


@router.post("/jobs/{job_id}/status")
async def update_job_status(
    job_id: str,
    payload: StatusUpdateRequest,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Change ShippingJob.status and append a ShippingStatusLog row."""

    job: Optional[ShippingJob] = db.query(ShippingJob).filter(ShippingJob.id == job_id).one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Shipping job not found")

    before = job.status
    after = payload.status
    now = datetime.utcnow()

    job.status = after
    job.updated_at = now

    log_row = ShippingStatusLog(
        id=str(uuid.uuid4()),
        shipping_job_id=job.id,
        status_before=before,
        status_after=after,
        source=payload.source or ShippingStatusSource.MANUAL,
        reason=payload.reason,
        user_id=current_user.id,
        created_at=now,
    )
    db.add(log_row)
    db.commit()
    db.refresh(job)

    return _job_to_row(job)


@router.post("/labels/manual")
async def create_manual_label(
    payload: ManualLabelRequest,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Manually attach a label + tracking to a shipping job and mark it SHIPPED.

    Phase 1 implementation does not call any external provider; the label
    metadata is provided by the user.
    """

    job: Optional[ShippingJob] = db.query(ShippingJob).filter(ShippingJob.id == payload.shippingJobId).one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Shipping job not found")

    now = datetime.utcnow()

    label = ShippingLabel(
        id=str(uuid.uuid4()),
        shipping_job_id=job.id,
        provider=ShippingLabelProvider.MANUAL,
        provider_shipment_id=None,
        tracking_number=payload.trackingNumber,
        carrier=payload.carrier,
        service_name=payload.serviceName,
        label_url=payload.labelUrl or "about:blank",
        label_file_type=payload.labelFileType or "pdf",
        label_cost_amount=payload.labelCostAmount,
        label_cost_currency=payload.labelCostCurrency or "USD",
        purchased_at=now,
        voided=False,
        created_at=now,
        updated_at=now,
    )
    db.add(label)
    db.flush()  # ensure label.id is available

    # Link label to job and mark as shipped.
    job.label_id = label.id
    before_status = job.status
    job.status = ShippingJobStatus.SHIPPED
    job.updated_at = now

    status_log = ShippingStatusLog(
        id=str(uuid.uuid4()),
        shipping_job_id=job.id,
        status_before=before_status,
        status_after=ShippingJobStatus.SHIPPED,
        source=ShippingStatusSource.API,
        reason="Manual label created",
        user_id=current_user.id,
        created_at=now,
    )
    db.add(status_log)

    db.commit()
    db.refresh(label)
    db.refresh(job)

    # TODO: Future integration point for eBay Logistics / external providers.
    # At this point we would call ShippingRateProvider.buy_label(...) and
    # propagate tracking to eBay Fulfillment API.

    return {
        "id": label.id,
        "shipping_job_id": label.shipping_job_id,
        "provider": label.provider.value if label.provider else None,
        "tracking_number": label.tracking_number,
        "carrier": label.carrier,
        "service_name": label.service_name,
        "label_url": label.label_url,
        "label_file_type": label.label_file_type,
        "label_cost_amount": float(label.label_cost_amount) if label.label_cost_amount is not None else None,
        "label_cost_currency": label.label_cost_currency,
        "purchased_at": label.purchased_at.isoformat() if label.purchased_at else None,
        "voided": label.voided,
    }


@router.get("/jobs")
async def list_jobs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status: Optional[ShippingJobStatus] = Query(None),
    exclude_status: Optional[ShippingJobStatus] = Query(None),
    warehouse_id: Optional[str] = None,
    ebay_account_id: Optional[str] = None,
    search: Optional[str] = Query(None, description="Search by order id, buyer, storage, or tracking"),
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Generic job listing used by Status and Shipping tabs."""

    q = (
        db.query(ShippingJob)
        .outerjoin(EbayAccount, ShippingJob.ebay_account_id == EbayAccount.id)
        .filter(or_(EbayAccount.org_id == current_user.id, ShippingJob.ebay_account_id.is_(None)))
    )

    if status is not None:
        q = q.filter(ShippingJob.status == status)
    if exclude_status is not None:
        q = q.filter(ShippingJob.status != exclude_status)
    if warehouse_id:
        q = q.filter(ShippingJob.warehouse_id == warehouse_id)
    if ebay_account_id:
        q = q.filter(ShippingJob.ebay_account_id == ebay_account_id)

    if search:
        like = f"%{search}%"
        q = q.filter(
            or_(
                ShippingJob.ebay_order_id.ilike(like),
                ShippingJob.buyer_user_id.ilike(like),
                ShippingJob.buyer_name.ilike(like),
                cast(ShippingJob.storage_ids, SAText).ilike(like),
            )
        )

    total = q.count()
    q = q.order_by(desc(ShippingJob.created_at))
    jobs: List[ShippingJob] = q.offset(offset).limit(limit).all()

    rows = [_job_to_row(job) for job in jobs]
    return {"rows": rows, "limit": limit, "offset": offset, "total": total}


@router.get("/labels")
async def list_labels(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    provider: Optional[ShippingLabelProvider] = Query(None),
    carrier: Optional[str] = None,
    voided: Optional[bool] = None,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """List shipping labels with basic filters."""

    # Join via job -> account to scope to current org/user.
    q = (
        db.query(ShippingLabel)
        .join(ShippingJob, ShippingLabel.shipping_job_id == ShippingJob.id)
        .outerjoin(EbayAccount, ShippingJob.ebay_account_id == EbayAccount.id)
        .filter(or_(EbayAccount.org_id == current_user.id, ShippingJob.ebay_account_id.is_(None)))
    )

    if provider is not None:
        q = q.filter(ShippingLabel.provider == provider)
    if carrier:
        q = q.filter(ShippingLabel.carrier.ilike(f"%{carrier}%"))
    if voided is not None:
        q = q.filter(ShippingLabel.voided == voided)

    total = q.count()
    q = q.order_by(desc(ShippingLabel.purchased_at), desc(ShippingLabel.created_at))
    labels: List[ShippingLabel] = q.offset(offset).limit(limit).all()

    rows: List[Dict[str, Any]] = []
    for lbl in labels:
        rows.append(
            {
                "id": lbl.id,
                "shipping_job_id": lbl.shipping_job_id,
                "provider": lbl.provider.value if lbl.provider else None,
                "tracking_number": lbl.tracking_number,
                "carrier": lbl.carrier,
                "service_name": lbl.service_name,
                "label_url": lbl.label_url,
                "label_file_type": lbl.label_file_type,
                "label_cost_amount": float(lbl.label_cost_amount) if lbl.label_cost_amount is not None else None,
                "label_cost_currency": lbl.label_cost_currency,
                "purchased_at": lbl.purchased_at.isoformat() if lbl.purchased_at else None,
                "voided": lbl.voided,
            }
        )

    return {"rows": rows, "limit": limit, "offset": offset, "total": total}


@router.post("/labels/{label_id}/void")
async def void_label(
    label_id: str,
    payload: VoidLabelRequest,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Mark a label as voided (logical flag only in Phase 1)."""

    lbl: Optional[ShippingLabel] = (
        db.query(ShippingLabel)
        .join(ShippingJob, ShippingLabel.shipping_job_id == ShippingJob.id)
        .outerjoin(EbayAccount, ShippingJob.ebay_account_id == EbayAccount.id)
        .filter(
            ShippingLabel.id == label_id,
            or_(EbayAccount.org_id == current_user.id, ShippingJob.ebay_account_id.is_(None)),
        )
        .one_or_none()
    )
    if not lbl:
        raise HTTPException(status_code=404, detail="Label not found")

    lbl.voided = payload.voided
    lbl.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(lbl)

    return {
        "id": lbl.id,
        "shipping_job_id": lbl.shipping_job_id,
        "provider": lbl.provider.value if lbl.provider else None,
        "tracking_number": lbl.tracking_number,
        "carrier": lbl.carrier,
        "service_name": lbl.service_name,
        "label_url": lbl.label_url,
        "label_file_type": lbl.label_file_type,
        "label_cost_amount": float(lbl.label_cost_amount) if lbl.label_cost_amount is not None else None,
        "label_cost_currency": lbl.label_cost_currency,
        "purchased_at": lbl.purchased_at.isoformat() if lbl.purchased_at else None,
        "voided": lbl.voided,
    }
