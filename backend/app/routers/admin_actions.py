from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.models_sqlalchemy import get_db
from app.models_sqlalchemy.models import AiEbayAction
from app.services.auth import admin_required


router = APIRouter(prefix="/api/admin/ai/actions", tags=["admin-actions"])


class AiEbayActionDto(BaseModel):
    id: int
    ebay_item_id: str
    model_id: Optional[str]
    action_type: str
    offer_amount: Optional[float]
    original_price: Optional[float]
    shipping: Optional[float]
    predicted_profit: Optional[float]
    roi: Optional[float]
    rule_name: Optional[str]
    status: str
    error_message: Optional[str]
    created_at: Optional[str]
    updated_at: Optional[str]


@router.get("/", response_model=List[AiEbayActionDto], dependencies=[Depends(admin_required)])
async def list_ai_ebay_actions(
    limit: int = 200,
    offset: int = 0,
    db: Session = Depends(get_db),
) -> List[AiEbayActionDto]:
    """List AI-planned eBay actions for admin review."""

    limit = max(1, min(limit, 500))
    actions = (
        db.query(AiEbayAction)
        .order_by(AiEbayAction.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return [
        AiEbayActionDto(
            id=a.id,
            ebay_item_id=a.ebay_item_id,
            model_id=a.model_id,
            action_type=a.action_type,
            offer_amount=a.offer_amount,
            original_price=a.original_price,
            shipping=a.shipping,
            predicted_profit=a.predicted_profit,
            roi=a.roi,
            rule_name=a.rule_name,
            status=a.status,
            error_message=a.error_message,
            created_at=a.created_at.isoformat() if a.created_at else None,
            updated_at=a.updated_at.isoformat() if a.updated_at else None,
        )
        for a in actions
    ]


@router.get("/{action_id}", response_model=AiEbayActionDto, dependencies=[Depends(admin_required)])
async def get_ai_ebay_action(
    action_id: int,
    db: Session = Depends(get_db),
) -> AiEbayActionDto:
    """Get a single AI eBay action by ID."""

    action = db.query(AiEbayAction).filter(AiEbayAction.id == action_id).one_or_none()
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")

    return AiEbayActionDto(
        id=action.id,
        ebay_item_id=action.ebay_item_id,
        model_id=action.model_id,
        action_type=action.action_type,
        offer_amount=action.offer_amount,
        original_price=action.original_price,
        shipping=action.shipping,
        predicted_profit=action.predicted_profit,
        roi=action.roi,
        rule_name=action.rule_name,
        status=action.status,
        error_message=action.error_message,
        created_at=action.created_at.isoformat() if action.created_at else None,
        updated_at=action.updated_at.isoformat() if action.updated_at else None,
    )