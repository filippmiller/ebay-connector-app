"""Auto-Offer / Auto-Buy planner worker.

Consumes ai_ebay_candidates, combines them with model_profit_profile and
produces planned actions in ai_ebay_actions. In DRY_RUN mode the worker only
writes draft actions and does not call real eBay APIs; in live mode it calls
stubbed eBay buy/offer functions that will be replaced in a future phase.
"""
from __future__ import annotations

import asyncio
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config.worker_settings import (
    AUTO_BUY_DRY_RUN,
    AUTO_BUY_MIN_PROFIT,
    AUTO_BUY_MIN_ROI,
)
from app.models_sqlalchemy import SessionLocal
from app.models_sqlalchemy.models import AiEbayCandidate, AiEbayAction
from app.services.ebay_api_client import place_buy_now_stub, place_offer_stub
from app.utils.logger import logger


async def run_auto_offer_buy_loop(interval_sec: int = 120) -> None:
    """Background loop that periodically processes candidate listings.

    The loop is lightweight and safe to run frequently; filtering thresholds
    and uniqueness constraints on ai_ebay_actions keep the volume bounded.
    """

    logger.info(
        "[auto-actions] Auto-offer/Buy planner loop started (interval=%s seconds, dry_run=%s)",
        interval_sec,
        AUTO_BUY_DRY_RUN,
    )
    while True:
        try:
            await process_candidates_batch()
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("[auto-actions] process_candidates_batch failed: %s", exc, exc_info=True)
        await asyncio.sleep(interval_sec)


async def process_candidates_batch(limit: int = 100) -> None:
    """Process a batch of monitoring candidates into planned actions.

    For each recent ai_ebay_candidate that has no existing non-terminal action,
    the worker:

    - Loads the associated profitability profile from model_profit_profile.
    - Computes total_price, predicted_profit and ROI.
    - Applies AUTO_BUY_MIN_PROFIT and AUTO_BUY_MIN_ROI thresholds.
    - Chooses action_type 'buy_now' or 'offer' based on ROI.
    - Writes an AiEbayAction row with status 'draft' (dry run) or 'ready' /
      'executed' (live, using stubbed eBay calls).
    """

    db = SessionLocal()
    try:
        logger.info("[auto-actions] Processing candidates batch (limit=%s)", limit)

        # Subquery of item_ids that already have a non-terminal action.
        active_item_ids_subq = (
            db.query(AiEbayAction.ebay_item_id)
            .filter(AiEbayAction.status.in_(["draft", "ready", "executed"]))
            .subquery()
        )

        candidates = (
            db.query(AiEbayCandidate)
            .filter(~AiEbayCandidate.ebay_item_id.in_(active_item_ids_subq))
            .order_by(AiEbayCandidate.created_at.desc())
            .limit(limit)
            .all()
        )

        if not candidates:
            logger.info("[auto-actions] No new candidates to process.")
            return

        processed = 0
        created_actions = 0

        for cand in candidates:
            if not cand.model_id:
                continue

            total_price = float((cand.price or 0.0) + (cand.shipping or 0.0))
            if total_price <= 0:
                continue

            profile = _load_profit_profile(db, str(cand.model_id))
            if profile is None:
                continue

            max_buy_price = profile["max_buy_price"]
            expected_profit = profile["expected_profit"]
            if max_buy_price is None or expected_profit is None:
                continue

            max_buy_price_f = float(max_buy_price or 0.0)
            expected_profit_f = float(expected_profit or 0.0)
            if max_buy_price_f <= 0 or expected_profit_f <= 0:
                continue

            predicted_profit = expected_profit_f - total_price
            if predicted_profit < AUTO_BUY_MIN_PROFIT:
                continue

            roi: Optional[float]
            try:
                roi = predicted_profit / total_price if total_price > 0 else None
            except ZeroDivisionError:
                roi = None

            if roi is None or roi < AUTO_BUY_MIN_ROI:
                continue

            if total_price > max_buy_price_f:
                # Safety: do not exceed max_buy_price from profile.
                continue

            # Simple heuristic: very high ROI → buy_now, otherwise offer.
            action_type = "buy_now" if roi >= AUTO_BUY_MIN_ROI * 2 else "offer"
            offer_amount = min(total_price, max_buy_price_f)

            action = (
                db.query(AiEbayAction)
                .filter(
                    AiEbayAction.ebay_item_id == cand.ebay_item_id,
                    AiEbayAction.action_type == action_type,
                )
                .one_or_none()
            )

            if action is None:
                action = AiEbayAction(
                    ebay_item_id=cand.ebay_item_id,
                    model_id=str(cand.model_id),
                    action_type=action_type,
                )
                db.add(action)
                created_actions += 1

            action.original_price = cand.price
            action.shipping = cand.shipping
            action.offer_amount = offer_amount
            action.predicted_profit = predicted_profit
            action.roi = roi
            action.rule_name = cand.rule_name

            if AUTO_BUY_DRY_RUN:
                action.status = "draft"
                action.error_message = None
                logger.info(
                    "[auto-actions] DRY-RUN action planned: type=%s item_id=%s amount=%.2f",
                    action_type,
                    cand.ebay_item_id,
                    offer_amount,
                )
            else:
                # In live mode, attempt stubbed execution immediately.
                action.status = "ready"
                try:
                    if action_type == "buy_now":
                        success = await place_buy_now_stub(cand.ebay_item_id, float(offer_amount or 0.0))
                    else:
                        success = await place_offer_stub(cand.ebay_item_id, float(offer_amount or 0.0))

                    if success:
                        action.status = "executed"
                        action.error_message = None
                    else:
                        action.status = "failed"
                        action.error_message = "eBay stub reported failure"
                except Exception as exc:  # pragma: no cover - defensive
                    action.status = "failed"
                    action.error_message = f"Stub execution failed: {exc}"

            processed += 1

        db.commit()
        logger.info(
            "[auto-actions] Batch completed: processed=%s, actions_created=%s", processed, created_actions
        )
    finally:
        db.close()


def _load_profit_profile(db: Session, model_id: str) -> Optional[dict]:
    """Load profitability profile for a single model_id from model_profit_profile.

    Returns a mapping with at least keys "max_buy_price" and "expected_profit"
    or None when no profile exists.
    """

    row = db.execute(
        text(
            """
            SELECT max_buy_price, expected_profit
            FROM model_profit_profile
            WHERE model_id::text = :model_id
            """
        ),
        {"model_id": model_id},
    ).mappings().one_or_none()

    if not row:
        return None

    return {
        "max_buy_price": row.get("max_buy_price"),
        "expected_profit": row.get("expected_profit"),
    }
