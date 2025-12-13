"""eBay Monitoring Worker.

Periodically scans profitable models from model_profit_profile, queries the
Buy Browse API for potentially underpriced listings, and stores them in
ai_ebay_candidates for review in the admin UI.

This is a first complete version focused on conservative candidate selection:
- Only models with expected_profit >= MIN_PROFIT_MARGIN and max_buy_price > 0
  are considered.
- A listing is saved as a candidate only when:
    price + shipping <= max_buy_price
    AND predicted_profit (expected_profit - total_price) >= 0.
"""
from __future__ import annotations

import asyncio
from typing import List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config.worker_settings import MIN_PROFIT_MARGIN
from app.models_sqlalchemy import SessionLocal
from app.models_sqlalchemy.models import AiEbayCandidate, EbayAccount, EbayToken
from app.services.ebay_api_client import search_active_listings
from app.utils.logger import logger


async def run_monitoring_loop(interval_sec: int = 60) -> None:
    """Background loop that scans all models on a fixed interval.

    The interval is intentionally short (default 60 seconds) but the amount of
    work per iteration is bounded by the set of profitable models and the
    Browse API result limits.
    """

    logger.info("[monitor] eBay monitoring loop started (interval=%s seconds)", interval_sec)
    while True:
        try:
            await scan_all_models_once()
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("[monitor] scan_all_models_once failed: %s", exc, exc_info=True)
        await asyncio.sleep(interval_sec)


def _get_any_access_token(db: Session) -> Optional[str]:
    """Return an access token for any active eBay account, if available.

    The monitoring worker does not yet support per-account routing; it uses the
    first active account with a valid token. Token refresh is handled by the
    dedicated token refresh worker.
    """

    token: Optional[EbayToken] = (
        db.query(EbayToken)
        .join(EbayAccount, EbayToken.ebay_account_id == EbayAccount.id)
        .filter(EbayAccount.is_active.is_(True))
        .order_by(EbayAccount.connected_at.desc())
        .first()
    )
    if not token:
        return None

    try:
        return token.access_token
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("[monitor] Failed to decrypt eBay access token: %s", exc, exc_info=True)
        return None


async def scan_all_models_once() -> None:
    """Scan all profitable models once and refresh ai_ebay_candidates.

    This function opens its own SQLAlchemy session and is safe to call from
    both the loop and ad-hoc admin endpoints in the future.
    """

    db = SessionLocal()
    try:
        # 1) Load profitable models from model_profit_profile.
        rows = db.execute(
            text(
                """
                SELECT
                    model_id::text AS model_id,
                    max_buy_price,
                    expected_profit,
                    matched_rule,
                    rule_name
                FROM model_profit_profile
                WHERE expected_profit IS NOT NULL
                  AND max_buy_price IS NOT NULL
                  AND max_buy_price > 0
                  AND expected_profit >= :min_profit
                """
            ),
            {"min_profit": float(MIN_PROFIT_MARGIN)},
        ).mappings().all()

        if not rows:
            logger.info("[monitor] No profitable models found in model_profit_profile; skipping scan.")
            return

        access_token = _get_any_access_token(db)
        if not access_token:
            logger.warning("[monitor] No active eBay account with token found; monitoring scan skipped.")
            return

        logger.info("[monitor] Scanning %s profitable models for candidates", len(rows))

        for row in rows:
            model_id = str(row["model_id"])
            max_buy_price = float(row["max_buy_price"] or 0.0)
            expected_profit = float(row["expected_profit"] or 0.0)
            matched_rule = bool(row.get("matched_rule")) if "matched_rule" in row else None
            rule_name = row.get("rule_name") if "rule_name" in row else None

            try:
                await _scan_model(db, access_token, model_id, max_buy_price, expected_profit, matched_rule, rule_name)
            except Exception as exc:  # pragma: no cover - per-model isolation
                logger.error(
                    "[monitor] scan_model failed for model_id=%s: %s", model_id, exc, exc_info=True
                )

        db.commit()
        logger.info("[monitor] Monitoring scan completed")
    finally:
        db.close()


def _build_keywords_for_model(model_id: str) -> str:
    """Build a simple keyword string for a model.

    For the first iteration we use model_id itself as the primary token. This
    can be refined later to join against tbl_parts_models / SqItem for a more
    descriptive query.
    """

    return str(model_id)


async def _scan_model(
    db: Session,
    access_token: str,
    model_id: str,
    max_buy_price: float,
    expected_profit: float,
    matched_rule: Optional[bool],
    rule_name: Optional[str],
) -> None:
    """Scan eBay listings for a single model and store qualifying candidates."""

    if max_buy_price <= 0 or expected_profit <= 0:
        return

    keywords = _build_keywords_for_model(model_id)
    listings = await search_active_listings(access_token, keywords, limit=20)

    if not listings:
        logger.debug("[monitor] No listings found for model_id=%s (keywords=%s)", model_id, keywords)
        return

    logger.debug("[monitor] Found %s listings for model_id=%s", len(listings), model_id)

    for listing in listings:
        total_price = float((listing.price or 0.0) + (listing.shipping or 0.0))
        if total_price <= 0:
            continue

        predicted_profit = expected_profit - total_price
        if total_price > max_buy_price:
            continue
        if predicted_profit < 0:
            continue

        roi: Optional[float]
        try:
            roi = predicted_profit / total_price if total_price > 0 else None
        except ZeroDivisionError:
            roi = None

        # UPSERT behaviour: do not create duplicates for the same ebay_item_id.
        candidate: Optional[AiEbayCandidate] = (
            db.query(AiEbayCandidate)
            .filter(AiEbayCandidate.ebay_item_id == listing.item_id)
            .one_or_none()
        )

        if candidate is None:
            candidate = AiEbayCandidate(
                ebay_item_id=listing.item_id,
                model_id=model_id,
            )
            db.add(candidate)

        candidate.title = listing.title
        candidate.price = listing.price
        candidate.shipping = listing.shipping
        candidate.condition = listing.condition
        candidate.description = listing.description

        candidate.predicted_profit = predicted_profit
        candidate.roi = roi

        candidate.matched_rule = matched_rule
        candidate.rule_name = rule_name

        # The actual INSERT/UPDATE is deferred until db.commit() in the parent
        # function; onupdate=func.now() on updated_at will track refresh time.
