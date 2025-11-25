from __future__ import annotations

from sqlalchemy.orm import Session

from app.models_sqlalchemy import SessionLocal
from app.models.ebay_worker_debug import EbayListingDebugRequest, EbayListingDebugResponse
from app.services.ebay_listing_service import run_listing_worker_debug


async def run_listing_worker_once(
    request: EbayListingDebugRequest,
    db: Session | None = None,
) -> EbayListingDebugResponse:
    """Convenience entry point for running the listing worker once.

    The debug HTTP endpoint typically injects a SQLAlchemy Session via FastAPI
    dependencies and calls `run_listing_worker_debug` directly. This wrapper is
    provided so that future background workers or scripts can trigger the same
    flow without going through HTTP.
    """

    owns_session = False
    if db is None:
        db = SessionLocal()
        owns_session = True

    try:
        return await run_listing_worker_debug(db, request)
    finally:
        if owns_session:
            db.close()
