from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models_sqlalchemy import get_db as get_db_sqla
from app.models_sqlalchemy.models import AiEbayCandidate
from app.services.auth import admin_required
from app.models.user import User


router = APIRouter(prefix="/api/admin/ai/monitor", tags=["admin_ai_monitoring"])


class AiEbayCandidateDto(BaseModel):
    ebay_item_id: str
    model_id: str
    title: Optional[str]
    price: Optional[float]
    shipping: Optional[float]
    condition: Optional[str]
    description: Optional[str]
    predicted_profit: Optional[float]
    roi: Optional[float]
    matched_rule: Optional[bool]
    rule_name: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True


@router.get("/candidates", response_model=List[AiEbayCandidateDto])
async def list_candidates(
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db_sqla),
    current_user: User = Depends(admin_required),  # noqa: ARG001
) -> List[AiEbayCandidateDto]:
    """List recent eBay monitoring candidates for admin review."""

    rows: List[AiEbayCandidate] = (
        db.query(AiEbayCandidate)
        .order_by(AiEbayCandidate.created_at.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )
    return rows


@router.get("/candidate/{item_id}", response_model=AiEbayCandidateDto)
async def get_candidate(
    item_id: str,
    db: Session = Depends(get_db_sqla),
    current_user: User = Depends(admin_required),  # noqa: ARG001
) -> AiEbayCandidateDto:
    """Return detailed information about a single monitoring candidate."""

    candidate = (
        db.query(AiEbayCandidate)
        .filter(AiEbayCandidate.ebay_item_id == item_id)
        .one_or_none()
    )
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return candidate
