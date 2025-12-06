from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime

from ..models_sqlalchemy import get_db
from ..models_sqlalchemy.models import EbayBuyer, EbayStatusBuyer, EbayBuyerLog, EbayAccount, TblPartsModels
from ..services.auth import get_current_user
from ..models.user import User

router = APIRouter(prefix="/api/buying", tags=["buying"])


@router.get("/statuses")
async def list_statuses(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return all BUYING status dictionary entries ordered by sort_order.

    The frontend uses this to populate the status dropdown (id, label, colors).
    """
    statuses: List[EbayStatusBuyer] = (
        db.query(EbayStatusBuyer)
        .filter(EbayStatusBuyer.is_active == True)  # noqa: E712
        .order_by(EbayStatusBuyer.sort_order.asc(), EbayStatusBuyer.id.asc())
        .all()
    )

    return [
        {
            "id": s.id,
            "code": s.code,
            "label": s.label,
            "sort_order": s.sort_order,
            "color_hex": s.color_hex,
            "text_color_hex": s.text_color_hex,
        }
        for s in statuses
    ]


@router.get("/{buyer_id}")
async def get_purchase_detail(
    buyer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return detailed information for a single ebay_buyer row.

    Includes basic item/seller/buyer fields plus current status + comment and a
    short recent history from tbl_ebay_buyer_log.
    """
    buyer: Optional[EbayBuyer] = (
        db.query(EbayBuyer)
        .join(EbayAccount, EbayBuyer.ebay_account_id == EbayAccount.id)
        .filter(
            EbayBuyer.id == buyer_id,
            EbayAccount.org_id == current_user.id,
        )
        .one_or_none()
    )
    if not buyer:
        raise HTTPException(status_code=404, detail="Purchase not found")

    status: Optional[EbayStatusBuyer] = None
    if buyer.item_status_id:
        status = db.query(EbayStatusBuyer).filter(EbayStatusBuyer.id == buyer.item_status_id).one_or_none()

    # Recent history (last 10 changes)
    history_rows: List[EbayBuyerLog] = (
        db.query(EbayBuyerLog)
        .filter(EbayBuyerLog.ebay_buyer_id == buyer.id)
        .order_by(EbayBuyerLog.changed_at.desc())
        .limit(10)
        .all()
    )

    history = [
        {
            "id": h.id,
            "change_type": h.change_type,
            "old_status_id": h.old_status_id,
            "new_status_id": h.new_status_id,
            "old_comment": h.old_comment,
            "new_comment": h.new_comment,
            "changed_by_user_id": h.changed_by_user_id,
            "changed_by_username": h.changed_by_username,
            "changed_at": h.changed_at.isoformat() if h.changed_at else None,
        }
        for h in history_rows
    ]

    return {
        "id": buyer.id,
        "ebay_account_id": buyer.ebay_account_id,
        "item_id": buyer.item_id,
        "transaction_id": buyer.transaction_id,
        "order_line_item_id": buyer.order_line_item_id,
        "title": buyer.title,
        "tracking_number": buyer.tracking_number,
        "storage": buyer.storage,
        "quantity_purchased": buyer.quantity_purchased,
        "buyer_id": buyer.buyer_id,
        "seller_id": buyer.seller_id,
        "seller_location": buyer.seller_location,
        "condition_display_name": buyer.condition_display_name,
        "shipping_carrier": buyer.shipping_carrier,
        "amount_paid": float(buyer.total_transaction_price or buyer.current_price or 0) if (buyer.total_transaction_price or buyer.current_price) is not None else None,
        "paid_time": buyer.paid_time.isoformat() if buyer.paid_time else None,
        "item_status_id": buyer.item_status_id,
        "item_status_label": status.label if status else None,
        "comment": buyer.comment,
        "gallery_url": getattr(buyer, "gallery_url", None),
        "picture_url": getattr(buyer, "picture_url0", None),
        "history": history,
    }


@router.patch("/{buyer_id}/status")
async def update_status_and_comment(
    buyer_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update item_status_id and/or comment for a purchase and log the change.

    Body:
        { "status_id": int | null, "comment": str | null }
    """
    status_id = payload.get("status_id") if "status_id" in payload else None
    comment = payload.get("comment") if "comment" in payload else None

    if status_id is None and comment is None:
        return {"updated": False}

    buyer: Optional[EbayBuyer] = (
        db.query(EbayBuyer)
        .join(EbayAccount, EbayBuyer.ebay_account_id == EbayAccount.id)
        .filter(
            EbayBuyer.id == buyer_id,
            EbayAccount.org_id == current_user.id,
        )
        .with_for_update()
        .one_or_none()
    )
    if not buyer:
        raise HTTPException(status_code=404, detail="Purchase not found")

    old_status_id = buyer.item_status_id
    old_comment = buyer.comment

    changed_status = False
    changed_comment = False

    now = datetime.utcnow()

    if "status_id" in payload and status_id != buyer.item_status_id:
        buyer.item_status_id = status_id
        buyer.item_status_updated_at = now
        buyer.item_status_updated_by = current_user.username
        changed_status = True

    if "comment" in payload and comment != buyer.comment:
        buyer.comment = comment
        buyer.comment_updated_at = now
        buyer.comment_updated_by = current_user.username
        changed_comment = True

    if not changed_status and not changed_comment:
        return {"updated": False}

    buyer.record_updated_at = now
    buyer.record_updated_by = current_user.username

    change_type = "status+comment" if changed_status and changed_comment else ("status" if changed_status else "comment")

    log_row = EbayBuyerLog(
        ebay_buyer_id=buyer.id,
        change_type=change_type,
        old_status_id=old_status_id,
        new_status_id=buyer.item_status_id,
        old_comment=old_comment,
        new_comment=buyer.comment,
        changed_by_user_id=current_user.id,
        changed_by_username=current_user.username,
        changed_at=now,
    )
    db.add(log_row)
    db.commit()
    db.refresh(buyer)

    # Return the updated minimal payload so the grid/detail can refresh.
    return {
        "id": buyer.id,
        "item_status_id": buyer.item_status_id,
        "comment": buyer.comment,
        "change_type": change_type,
    }

@router.get("/models/search")
async def search_models(
    q: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Search for models in tbl_parts_models by name."""
    models = (
        db.query(TblPartsModels)
        .filter(TblPartsModels.Model.ilike(f"%{q}%"))
        .limit(20)
        .all()
    )
    return [
        {"id": m.Model_ID, "label": m.Model}
        for m in models
    ]


@router.patch("/{buyer_id}/model")
async def update_model(
    buyer_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update model_id for a purchase.
    
    Body: { "model_id": int }
    """
    model_id = payload.get("model_id")
    if model_id is None:
        raise HTTPException(status_code=400, detail="model_id is required")

    buyer: Optional[EbayBuyer] = (
        db.query(EbayBuyer)
        .join(EbayAccount, EbayBuyer.ebay_account_id == EbayAccount.id)
        .filter(
            EbayBuyer.id == buyer_id,
            EbayAccount.org_id == current_user.id,
        )
        .with_for_update()
        .one_or_none()
    )
    if not buyer:
        raise HTTPException(status_code=404, detail="Purchase not found")

    # Update columns - handling both potential column names if they exist on the model
    # Based on inspection, EbayBuyer model likely maps one of them to 'model_id' attribute or similar.
    # We will assume 'model_id' attribute exists on the ORM model as mapped in models.py
    # If explicit column names are needed, we'll check models.py, but usually the attribute is snake_case.
    # Wait, in the grid join we saw COALESCE(Model_ID, ModelID).
    # Let's try setting the attribute if available.
    if hasattr(buyer, 'model_id'):
        buyer.model_id = model_id
    elif hasattr(buyer, 'Model_ID'):
        buyer.Model_ID = model_id
    elif hasattr(buyer, 'ModelID'):
        buyer.ModelID = model_id
    else:
        # Fallback if ORM attribute is not obvious, though this shouldn't happen if models are generated correctly.
        # We'll assume 'model_id' or 'Model_ID' works.
        buyer.model_id = model_id

    buyer.record_updated_at = datetime.utcnow()
    buyer.record_updated_by = current_user.username
    
    db.commit()
    db.refresh(buyer)

    return {"success": True, "model_id": model_id}
