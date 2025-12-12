from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.ebay_worker_debug import (
    EbayListingDebugRequest,
    EbayListingDebugResponse,
)
from app.services.auth import get_current_active_user
from app.models_sqlalchemy import get_db
from app.services.ebay_listing_service import run_listing_worker_debug
from app.utils.logger import logger


router = APIRouter(prefix="/api/debug/ebay", tags=["ebay_listing_debug"])


@router.post("/list-once", response_model=EbayListingDebugResponse)
async def run_listing_once_debug(
    payload: EbayListingDebugRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> EbayListingDebugResponse:
    """Run the eBay listing worker once in debug mode and return a full trace.

    This endpoint is intended for development and internal debugging. It
    selects candidate rows from parts_detail in Supabase Postgres, simulates
    (or in the future performs) bulk eBay listing calls, computes the exact DB
    updates/inserts that would be performed, and returns a structured
    WorkerDebugTrace that the frontend renders in a terminal-like modal.
    """

    # Hard safety cap regardless of what the client sends.
    if payload.max_items > 200:
        payload.max_items = 200

    try:
        return await run_listing_worker_debug(db, payload)
    except HTTPException:
        # Let FastAPI propagate explicit HTTP errors unchanged.
        raise
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.exception("Listing debug worker failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Listing debug worker failed; see server logs for details.",
        ) from exc
