from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text as sa_text
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
    """Return detailed information for a single tbl_ebay_buyer row.

    Uses raw SQL to query the legacy Supabase table tbl_ebay_buyer, matching what
    the grid does. No org/account filtering since the legacy table has no FK.
    """
    
    # Query the legacy tbl_ebay_buyer table directly
    sql = """
        SELECT
            b."ID" AS id,
            b."ItemID" AS item_id,
            b."TransactionID" AS transaction_id,
            b."OrderLineItemID" AS order_line_item_id,
            b."Title" AS title,
            b."TrackingNumber" AS tracking_number,
            b."Storage" AS storage,
            b."QuantityPurchased" AS quantity_purchased,
            b."BuyerID" AS buyer_id,
            b."SellerID" AS seller_id,
            b."SellerLocation" AS seller_location,
            b."ConditionDisplayName" AS condition_display_name,
            b."ShippingCarrier" AS shipping_carrier,
            COALESCE(b."TotalTransactionPrice", b."CurrentPrice") AS amount_paid,
            b."PaidTime" AS paid_time,
            b."ItemStatus" AS item_status_id,
            b."Comment" AS comment,
            b."GalleryURL" AS gallery_url,
            sb."label" AS item_status_label,
            sb."color_hex" AS status_color_hex,
            sb."text_color_hex" AS status_text_color_hex
        FROM "tbl_ebay_buyer" b
        LEFT JOIN "ebay_status_buyer" sb ON b."ItemStatus" = sb."id"
        WHERE b."ID" = :buyer_id
    """
    
    result = db.execute(sa_text(sql), {"buyer_id": buyer_id}).first()
    
    if not result:
        raise HTTPException(status_code=404, detail="Purchase not found")

    return {
        "id": result.id,
        "item_id": result.item_id,
        "transaction_id": result.transaction_id,
        "order_line_item_id": result.order_line_item_id,
        "title": result.title,
        "tracking_number": result.tracking_number,
        "storage": result.storage,
        "quantity_purchased": result.quantity_purchased,
        "buyer_id": result.buyer_id,
        "seller_id": result.seller_id,
        "seller_location": result.seller_location,
        "condition_display_name": result.condition_display_name,
        "shipping_carrier": result.shipping_carrier,
        "amount_paid": float(result.amount_paid) if result.amount_paid is not None else None,
        "paid_time": result.paid_time,
        "item_status_id": result.item_status_id,
        "item_status_label": result.item_status_label,
        "comment": result.comment,
        "gallery_url": result.gallery_url,
        "picture_url": result.gallery_url,  # Use gallery_url for picture_url as well
    }


@router.patch("/{buyer_id}/status")
async def update_status_and_comment(
    buyer_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update ItemStatus and/or Comment for a purchase in tbl_ebay_buyer.

    Body:
        { "status_id": int | null, " comment": str | null }
    """
    status_id = payload.get("status_id") if "status_id" in payload else None
    comment = payload.get("comment") if "comment" in payload else None

    if status_id is None and comment is None:
        return {"updated": False}

    # Build UPDATE SET clause dynamically
    updates = []
    params = {"buyer_id": buyer_id}
    
    if "status_id" in payload:
        updates.append('"ItemStatus" = :status_id')
        params["status_id"] = status_id
    
    if "comment" in payload:
        updates.append('"Comment" = :comment')
        params["comment"] = comment
    
    if not updates:
        return {"updated": False}
    
    # Update the legacy table directly
    update_sql = f"""
        UPDATE "tbl_ebay_buyer"
        SET {", ".join(updates)}
        WHERE "ID" = :buyer_id
    """
    
    result = db.execute(sa_text(update_sql), params)
    db.commit()
    
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Purchase not found")

    return {
        "id": buyer_id,
        "item_status_id": status_id,
        "comment": comment,
        "updated": True,
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
    """Update Model_ID for a purchase in tbl_ebay_buyer.
    
    Body: { "model_id": int }
    """
    model_id = payload.get("model_id")
    if model_id is None:
        raise HTTPException(status_code=400, detail="model_id is required")

    update_sql = """
        UPDATE "tbl_ebay_buyer"
        SET "Model_ID" = :model_id
        WHERE "ID" = :buyer_id
    """
    
    result = db.execute(sa_text(update_sql), {"buyer_id": buyer_id, "model_id": model_id})
    db.commit()
    
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Purchase not found")

    return {"success": True, "model_id": model_id}
