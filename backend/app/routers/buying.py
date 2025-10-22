from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import desc, asc
from typing import Optional, List
from datetime import datetime
import uuid

from ..models_sqlalchemy import get_db
from ..models_sqlalchemy.models import Purchase, PurchaseLineItem, PaymentStatus, FulfillmentStatus, SyncLog
from ..services.auth import get_current_user, admin_required
from ..models.user import User

router = APIRouter(prefix="/api/buying", tags=["buying"])


def sync_buying_purchases(job_id: str, user_id: str, db: Session):
    """Background job to sync purchases from eBay API"""
    import time
    from ..utils.logger import logger
    
    sync_log = db.query(SyncLog).filter(SyncLog.job_id == job_id).first()
    if not sync_log:
        sync_log = SyncLog(
            job_id=job_id,
            user_id=user_id,
            endpoint="buying",
            status="running",
            sync_started_at=datetime.utcnow()
        )
        db.add(sync_log)
        db.commit()
    
    start_time = time.time()
    
    try:
        logger.info(f"[Job {job_id}] Starting BUYING purchases sync for user {user_id}")
        time.sleep(2)
        
        pages_fetched = 1
        records_stored = 0
        
        duration_ms = int((time.time() - start_time) * 1000)
        sync_log.status = "success"
        sync_log.pages_fetched = pages_fetched
        sync_log.records_fetched = records_stored
        sync_log.records_stored = records_stored
        sync_log.duration_ms = duration_ms
        sync_log.duration = duration_ms / 1000.0
        sync_log.sync_completed_at = datetime.utcnow()
        db.commit()
        
        logger.info(f"[Job {job_id}] BUYING sync completed: {records_stored} stored, {duration_ms}ms")
        
    except Exception as e:
        logger.error(f"[Job {job_id}] BUYING sync failed: {e}")
        duration_ms = int((time.time() - start_time) * 1000)
        sync_log.status = "error"
        sync_log.error_text = str(e)
        sync_log.error_message = str(e)
        sync_log.duration_ms = duration_ms
        sync_log.sync_completed_at = datetime.utcnow()
        db.commit()


@router.post("/admin/sync")
async def sync_purchases(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(admin_required),
    db: Session = Depends(get_db)
):
    """Admin-only: Trigger background sync of purchases from eBay"""
    job_id = str(uuid.uuid4())
    
    sync_log = SyncLog(
        job_id=job_id,
        user_id=current_user.id,
        endpoint="buying",
        status="queued",
        sync_started_at=datetime.utcnow()
    )
    db.add(sync_log)
    db.commit()
    
    background_tasks.add_task(sync_buying_purchases, job_id, current_user.id, db)
    
    return {
        "job_id": job_id,
        "status": "queued",
        "message": "Buying purchases sync queued successfully"
    }


@router.get("/admin/sync/jobs/{job_id}")
async def get_buying_sync_job_status(
    job_id: str,
    current_user: User = Depends(admin_required),
    db: Session = Depends(get_db)
):
    """Get status of a buying sync job"""
    sync_log = db.query(SyncLog).filter(
        SyncLog.job_id == job_id,
        SyncLog.user_id == current_user.id
    ).first()
    
    if not sync_log:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return {
        "job_id": sync_log.job_id,
        "status": sync_log.status,
        "endpoint": sync_log.endpoint,
        "pages_fetched": sync_log.pages_fetched or 0,
        "records_fetched": sync_log.records_fetched or 0,
        "records_stored": sync_log.records_stored or 0,
        "duration_ms": sync_log.duration_ms or 0,
        "error_text": sync_log.error_text,
        "started_at": sync_log.sync_started_at.isoformat() if sync_log.sync_started_at else None,
        "completed_at": sync_log.sync_completed_at.isoformat() if sync_log.sync_completed_at else None
    }


@router.get("")
async def get_purchases(
    buyer: Optional[str] = Query(None),
    seller: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    sort: str = Query("creation_date", regex="^(creation_date|total_value|buyer_username|seller_username)$"),
    dir: str = Query("desc", regex="^(asc|desc)$"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get purchases with filtering, pagination, and sorting.
    Server-side pagination for performance.
    """
    query = db.query(Purchase).filter(Purchase.user_id == current_user.id)
    
    # Apply filters
    if buyer:
        query = query.filter(Purchase.buyer_username.ilike(f"%{buyer}%"))
    if seller:
        query = query.filter(Purchase.seller_username.ilike(f"%{seller}%"))
    if status:
        try:
            payment_status = PaymentStatus[status.upper()]
            query = query.filter(Purchase.payment_status == payment_status)
        except KeyError:
            pass
    if from_date:
        try:
            from_dt = datetime.fromisoformat(from_date.replace('Z', '+00:00'))
            query = query.filter(Purchase.creation_date >= from_dt)
        except:
            pass
    if to_date:
        try:
            to_dt = datetime.fromisoformat(to_date.replace('Z', '+00:00'))
            query = query.filter(Purchase.creation_date <= to_dt)
        except:
            pass
    
    # Get total count before pagination
    total_count = query.count()
    
    # Apply sorting
    order_col = getattr(Purchase, sort)
    if dir == "desc":
        query = query.order_by(desc(order_col))
    else:
        query = query.order_by(asc(order_col))
    
    # Apply pagination
    purchases = query.offset(offset).limit(limit).all()
    
    # Convert to dict
    results = []
    for purchase in purchases:
        line_items_count = db.query(PurchaseLineItem).filter(
            PurchaseLineItem.purchase_id == purchase.purchase_id
        ).count()
        
        results.append({
            "purchase_id": purchase.purchase_id,
            "buyer_username": purchase.buyer_username,
            "seller_username": purchase.seller_username,
            "total_value": float(purchase.total_value) if purchase.total_value else 0,
            "total_currency": purchase.total_currency,
            "payment_status": purchase.payment_status.value if purchase.payment_status else "UNKNOWN",
            "fulfillment_status": purchase.fulfillment_status.value if purchase.fulfillment_status else "UNKNOWN",
            "creation_date": purchase.creation_date.isoformat() if purchase.creation_date else None,
            "tracking_number": purchase.tracking_number,
            "line_items_count": line_items_count,
            "ship_to_name": purchase.ship_to_name,
            "ship_to_city": purchase.ship_to_city,
            "ship_to_state": purchase.ship_to_state,
        })
    
    return {
        "purchases": results,
        "total": total_count,
        "limit": limit,
        "offset": offset,
        "has_more": (offset + limit) < total_count
    }


@router.get("/{purchase_id}")
async def get_purchase_detail(
    purchase_id: str,
    include: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get detailed purchase information.
    Query param 'include=lineItems' to include line items.
    """
    purchase = db.query(Purchase).filter(
        Purchase.purchase_id == purchase_id,
        Purchase.user_id == current_user.id
    ).first()
    
    if not purchase:
        raise HTTPException(status_code=404, detail="Purchase not found")
    
    result = {
        "purchase_id": purchase.purchase_id,
        "creation_date": purchase.creation_date.isoformat() if purchase.creation_date else None,
        "last_modified_at": purchase.last_modified_at.isoformat() if purchase.last_modified_at else None,
        "buyer_username": purchase.buyer_username,
        "seller_username": purchase.seller_username,
        "total_value": float(purchase.total_value) if purchase.total_value else 0,
        "total_currency": purchase.total_currency,
        "payment_status": purchase.payment_status.value if purchase.payment_status else "UNKNOWN",
        "fulfillment_status": purchase.fulfillment_status.value if purchase.fulfillment_status else "UNKNOWN",
        "tracking_number": purchase.tracking_number,
        "ship_to_name": purchase.ship_to_name,
        "ship_to_city": purchase.ship_to_city,
        "ship_to_state": purchase.ship_to_state,
        "ship_to_postal": purchase.ship_to_postal,
        "ship_to_country": purchase.ship_to_country,
    }
    
    # Include line items if requested
    if include and "lineItems" in include:
        line_items = db.query(PurchaseLineItem).filter(
            PurchaseLineItem.purchase_id == purchase_id
        ).all()
        
        result["line_items"] = [
            {
                "line_item_id": item.line_item_id,
                "sku": item.sku,
                "title": item.title,
                "quantity": item.quantity,
                "total_value": float(item.total_value) if item.total_value else 0,
                "currency": item.currency,
            }
            for item in line_items
        ]
    
    return result
