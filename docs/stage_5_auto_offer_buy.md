# Stage 5 – Auto-Offer / Auto-Buy Planner (Dry Run by Default)

## Overview

Stage 5 adds a new "Auto-Offer / Auto-Buy" planner layer on top of the existing profitability engine (Stage 3) and eBay monitoring worker (Stage 4).

Inputs:
- `model_profit_profile` – expected profitability and max_buy_price per model.
- `ai_ebay_candidates` – monitored eBay listings that look potentially profitable.

Output:
- `ai_ebay_actions` – planned actions for specific eBay listings:
  - `action_type`: `offer` | `buy_now`
  - `offer_amount`: planned offer / buy amount
  - `status`: `draft` | `ready` | `executed` | `failed`

The planner runs as a background worker, respects global thresholds, and is **DRY-RUN by default**: it only writes `draft` actions to the database and does not call real eBay APIs. When the `AUTO_BUY_DRY_RUN` flag is turned off, the worker immediately attempts to execute actions via eBay Buy/Offer **stubs**, updating statuses accordingly.

The phase also adds:
- Admin API to list actions.
- Admin UI page at `/admin/actions`.
- TypeScript checks for the frontend.

---

## Database – `ai_ebay_actions`

Stage 5 introduces a dedicated table for planned auto-offer / auto-buy actions. This table is populated by the planner worker and surfaced via the Admin Actions UI.

### Alembic migration

File: `backend/alembic/versions/ai_ebay_actions_20251125.py`

```python path=/C:/Users/filip/.gemini/antigravity/playground/silent-spirit/backend/alembic/versions/ai_ebay_actions_20251125.py start=1
"""Create ai_ebay_actions table for auto-offer/auto-buy planner

Revision ID: ai_ebay_actions_20251125
Revises: ai_ebay_candidates_20251125
Create Date: 2025-11-25
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "ai_ebay_actions_20251125"
down_revision: Union[str, Sequence[str], None] = "ai_ebay_candidates_20251125"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = "ai_ebay_actions"


def upgrade() -> None:
    op.create_table(
        TABLE_NAME,
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("ebay_item_id", sa.Text(), nullable=False),
        sa.Column("model_id", sa.Text(), nullable=False),
        sa.Column("action_type", sa.Text(), nullable=False),
        sa.Column("offer_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("original_price", sa.Numeric(14, 2), nullable=True),
        sa.Column("shipping", sa.Numeric(14, 2), nullable=True),
        sa.Column("predicted_profit", sa.Numeric(14, 2), nullable=True),
        sa.Column("roi", sa.Numeric(10, 4), nullable=True),
        sa.Column("rule_name", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_unique_constraint(
        "uq_ai_ebay_actions_item_type",
        TABLE_NAME,
        ["ebay_item_id", "action_type"],
    )
    op.create_index(
        "idx_ai_ebay_actions_model_id",
        TABLE_NAME,
        ["model_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_ai_ebay_actions_model_id", table_name=TABLE_NAME)
    op.drop_constraint("uq_ai_ebay_actions_item_type", TABLE_NAME, type_="unique")
    op.drop_table(TABLE_NAME)
```

Key points:
- `down_revision` is `ai_ebay_candidates_20251125`, chaining Stage 5 after Stage 4.
- `id` is a string UUID (36 chars) primary key.
- Unique constraint `uq_ai_ebay_actions_item_type` prevents duplicate actions per `(ebay_item_id, action_type)`.
- Index `idx_ai_ebay_actions_model_id` supports filtering by `model_id`.

### SQLAlchemy model

File: `backend/app/models_sqlalchemy/models.py`

```python path=/C:/Users/filip/.gemini/antigravity/playground/silent-spirit/backend/app/models_sqlalchemy/models.py start=1434
class AiEbayCandidate(Base):
    """Candidate eBay listing discovered by the monitoring worker.

    Each row represents a potentially profitable listing for a given model
    discovered via the eBay Browse/Search API.
    """

    __tablename__ = "ai_ebay_candidates"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    ebay_item_id = Column(Text, nullable=False, unique=True)
    model_id = Column(Text, nullable=False, index=True)

    title = Column(Text, nullable=True)
    price = Column(Numeric(14, 2), nullable=True)
    shipping = Column(Numeric(14, 2), nullable=True)
    condition = Column(Text, nullable=True)
    description = Column(Text, nullable=True)

    predicted_profit = Column(Numeric(14, 2), nullable=True)
    roi = Column(Numeric(10, 4), nullable=True)

    matched_rule = Column(Boolean, nullable=True)
    rule_name = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        Index("idx_ai_ebay_candidates_model_id", "model_id"),
    )


class AiEbayAction(Base):
    """Planned auto-offer / auto-buy action for a discovered eBay candidate.

    This table is populated by the auto-offer/auto-buy worker and can be
    reviewed in the admin UI before enabling live execution.
    """

    __tablename__ = "ai_ebay_actions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    ebay_item_id = Column(Text, nullable=False)
    model_id = Column(Text, nullable=False, index=True)

    # 'offer' | 'buy_now'
    action_type = Column(Text, nullable=False)

    # Planned amount we intend to pay or offer (same currency as original_price).
    offer_amount = Column(Numeric(14, 2), nullable=True)
    original_price = Column(Numeric(14, 2), nullable=True)
    shipping = Column(Numeric(14, 2), nullable=True)

    predicted_profit = Column(Numeric(14, 2), nullable=True)
    roi = Column(Numeric(10, 4), nullable=True)

    rule_name = Column(Text, nullable=True)

    # 'draft' | 'ready' | 'executed' | 'failed'
    status = Column(Text, nullable=False, default="draft")
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        Index("idx_ai_ebay_actions_model_id", "model_id"),
        Index("uq_ai_ebay_actions_item_type", "ebay_item_id", "action_type", unique=True),
    )
```

Notes:
- `AiEbayAction` is independent of `AiEbayCandidate` but shares `ebay_item_id` and `model_id`.
- Status is a simple text field; business logic enforces the `draft/ready/executed/failed` lifecycle.

---

## Worker Settings – DRY_RUN and Thresholds

Worker-level configuration is centralized in `backend/app/config/worker_settings.py`. Stage 5 adds a new DRY-RUN flag and thresholds used by the planner.

```python path=/C:/Users/filip/.gemini/antigravity/playground/silent-spirit/backend/app/config/worker_settings.py start=1
"""Worker-level configuration for background analytics and automation workers.

This module centralises numeric thresholds and feature flags so they can be
adjusted without code changes.
"""

# Minimum desired profit margin per computer (in the same currency units as
# expected_profit). The model profitability and monitoring workers use this to
# derive max_buy_price and filter profitable models.
MIN_PROFIT_MARGIN: float = 40.0

# --- Auto-Offer / Auto-Buy planner settings ---

# When True, the auto-offer/buy worker only plans actions (writes ai_ebay_actions
# in 'draft' status) and NEVER calls real eBay APIs.
AUTO_BUY_DRY_RUN: bool = True

# Minimum required ROI (predicted_profit / total_price) for a candidate to be
# considered for auto-offer/auto-buy.
AUTO_BUY_MIN_ROI: float = 0.30  # 30%

# Minimum absolute predicted profit required for a candidate to be considered
# for auto-offer/auto-buy.
AUTO_BUY_MIN_PROFIT: float = 40.0  # currency units
```

- **AUTO_BUY_DRY_RUN** controls whether the planner only produces `draft` rows, or also executes stubbed eBay actions.
- **AUTO_BUY_MIN_ROI** and **AUTO_BUY_MIN_PROFIT** gate which candidates are considered.

---

## Worker – `auto_offer_buy_worker.py`

The auto-offer / auto-buy worker periodically scans `ai_ebay_candidates`, joins in profitability information from `model_profit_profile`, and creates or updates `ai_ebay_actions` accordingly.

File: `backend/app/workers/auto_offer_buy_worker.py`

```python path=/C:/Users/filip/.gemini/antigravity/playground/silent-spirit/backend/app/workers/auto_offer_buy_worker.py start=1
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
```

### Planner behavior

1. **Candidate selection**
   - Skips candidates that already have an action in a non-terminal state (`draft`, `ready`, `executed`). This is implemented via a subquery over `AiEbayAction`.
   - Orders by `AiEbayCandidate.created_at DESC` and limits to `limit` (default 100).

2. **Profitability join**
   - For each candidate, loads `model_profit_profile` by `model_id::text`.
   - Requires non-null, positive `max_buy_price` and `expected_profit`.

3. **Thresholds**
   - Computes `total_price = price + shipping`.
   - Computes `predicted_profit = expected_profit - total_price`.
   - Requires `predicted_profit >= AUTO_BUY_MIN_PROFIT`.
   - Computes `roi = predicted_profit / total_price` and requires `roi >= AUTO_BUY_MIN_ROI`.
   - Enforces `total_price <= max_buy_price` as a hard cap.

4. **Action selection**
   - If `roi >= AUTO_BUY_MIN_ROI * 2` → action type `buy_now`.
   - Otherwise → action type `offer`.
   - `offer_amount = min(total_price, max_buy_price)`.
   - Upserts `AiEbayAction` for `(ebay_item_id, action_type)`:
     - Creates a new row when none exists.
     - Otherwise updates the existing one.

5. **Execution & DRY_RUN**
   - In `AUTO_BUY_DRY_RUN=True`:
     - Sets `status='draft'`, clears `error_message`.
     - Logs an informational DRY-RUN message.
   - In `AUTO_BUY_DRY_RUN=False`:
     - Sets initial `status='ready'`.
     - Invokes stub functions:
       - `place_buy_now_stub(ebay_item_id, offer_amount)` for `buy_now`.
       - `place_offer_stub(ebay_item_id, offer_amount)` for `offer`.
     - On `success=True` → `status='executed'`.
     - On `success=False` → `status='failed'`, `error_message="eBay stub reported failure"`.
     - On exception → `status='failed'`, `error_message` with exception text.

The real Buy/Offer API integration is intentionally left for a future phase; today these are non-destructive stubs.

---

## Startup Wiring

### Workers package

File: `backend/app/workers/__init__.py`

```python path=/C:/Users/filip/.gemini/antigravity/playground/silent-spirit/backend/app/workers/__init__.py start=1
"""
Background Workers for eBay Connector

This module contains background workers that run periodically to maintain
the health and functionality of eBay account connections.

Workers:
- token_refresh_worker: Runs every 10 minutes to refresh tokens expiring within 5 minutes
- health_check_worker: Runs every 15 minutes to verify all account connections are healthy
"""

from app.workers.token_refresh_worker import refresh_expiring_tokens, run_token_refresh_worker_loop
from app.workers.health_check_worker import run_all_health_checks, run_health_check_worker_loop
from app.workers.ebay_workers_loop import run_ebay_workers_loop, run_ebay_workers_once
from app.workers.tasks_reminder_worker import run_tasks_reminder_worker_loop
from app.workers.sniper_executor import run_sniper_loop
from app.workers.ebay_monitor_worker import run_monitoring_loop
from app.workers.auto_offer_buy_worker import run_auto_offer_buy_loop

__all__ = [
    "refresh_expiring_tokens",
    "run_token_refresh_worker_loop",
    "run_all_health_checks",
    "run_health_check_worker_loop",
    "run_ebay_workers_loop",
    "run_ebay_workers_once",
    "run_tasks_reminder_worker_loop",
    "run_sniper_loop",
    "run_monitoring_loop",
    "run_auto_offer_buy_loop",
]
```

- The planner loop is exported from the workers package as `run_auto_offer_buy_loop`.

### FastAPI startup event

File: `backend/app/main.py` (excerpt)

```python path=/C:/Users/filip/.gemini/antigravity/playground/silent-spirit/backend/app/main.py start=8
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.routers import (
    auth,
    ebay,
    orders,
    messages,
    offers,
    migration,
    buying,
    inventory,
    transactions,
    financials,
    admin,
    offers_v2,
    inventory_v2,
    ebay_accounts,
    ebay_workers,
    admin_db,
    grid_layouts,
    orders_api,
    grids_data,
    admin_mssql,
    ai_messages,
    timesheets,
    grid_preferences,
    admin_migration,
    admin_db_migration_console,
    tasks,
    listing,
    sq_catalog,
    ebay_notifications,
    shipping,
    ui_tweak,
    security_center,
    admin_users,
    sniper,
    ebay_listing_debug,
    admin_ai,
    admin_ai_rules_ext,
    admin_monitoring,
    admin_profitability,
    admin_actions,
)
...
app.include_router(admin_ai.router)
app.include_router(admin_ai_rules_ext.router)
app.include_router(admin_monitoring.router)
app.include_router(admin_profitability.router)
app.include_router(admin_actions.router)
...
    if start_workers:
        logger.info("🔄 Starting background workers...")
        try:
            from app.workers import (
                run_token_refresh_worker_loop,
                run_health_check_worker_loop,
                run_ebay_workers_loop,
                run_tasks_reminder_worker_loop,
                run_sniper_loop,
                run_monitoring_loop,
                run_auto_offer_buy_loop,
            )
            
            asyncio.create_task(run_token_refresh_worker_loop())
            logger.info("✅ Token refresh worker started (runs every 10 minutes)")
            
            asyncio.create_task(run_health_check_worker_loop())
            logger.info("✅ Health check worker started (runs every 15 minutes)")

            # eBay data workers loop – runs every 5 minutes and triggers all
            # enabled workers (orders, transactions, offers, messages, cases,
            # finances, active inventory) for all active accounts.
            asyncio.create_task(run_ebay_workers_loop())
            logger.info("✅ eBay workers loop started (runs every 5 minutes)")

            # Tasks & reminders worker – fires due reminders and snoozed reminders.
            asyncio.create_task(run_tasks_reminder_worker_loop())
            logger.info("✅ Tasks & reminders worker started (runs every 60 seconds)")

            asyncio.create_task(run_sniper_loop())
            logger.info("✅ Sniper executor worker started (runs every %s seconds)", 5)

            asyncio.create_task(run_monitoring_loop())
            logger.info("✅ eBay monitoring worker started (runs every %s seconds)", 60)

            asyncio.create_task(run_auto_offer_buy_loop())
            logger.info("✅ Auto-offer / Auto-buy planner worker started (runs every %s seconds)", 120)
            
        except Exception as e:
            logger.error(f"⚠️  Failed to start background workers: {e}")
            logger.info("Workers can be run separately if needed")
```

- The auto-offer/buy planner is started alongside existing background workers, only when running against Postgres (Supabase) as in production.
- The log line includes the run interval (120 seconds) and, from the worker itself, the `dry_run` flag value.

---

## Admin API – Actions Router

An admin-only router exposes the contents of `ai_ebay_actions`.

File: `backend/app/routers/admin_actions.py`

```python path=/C:/Users/filip/.gemini/antigravity/playground/silent-spirit/backend/app/routers/admin_actions.py start=1
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.models_sqlalchemy.models import AiEbayAction
from app.routers.auth_dependencies import admin_required
from app.schemas.base import ApiBaseModel


router = APIRouter(prefix="/api/admin/ai/actions", tags=["admin-actions"])


class AiEbayActionDto(ApiBaseModel):
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
```

- **Routes**:
  - `GET /api/admin/ai/actions` – list of actions, ordered by `created_at DESC`, with `limit/offset`.
  - `GET /api/admin/ai/actions/{id}` – single action by its internal ID.
- `admin_required` dependency ensures only admin users can access these endpoints.

The router is registered in `app.main` as shown in the Startup section.

---

## Frontend – Admin Actions Page

The frontend adds an Admin page that displays the contents of `ai_ebay_actions` using the shared `AppDataGrid` component.

### Page component

File: `frontend/src/pages/AdminActionsPage.tsx`

```tsx path=/C:/Users/filip/.gemini/antigravity/playground/silent-spirit/frontend/src/pages/AdminActionsPage.tsx start=1
import React, { useEffect, useState, useMemo } from 'react';
import FixedHeader from '@/components/FixedHeader';
import { AppDataGrid } from '@/components/datagrid/AppDataGrid';
import type { GridColumnMeta } from '@/components/DataGridPage';
import { Card } from '@/components/ui/card';

export interface AiEbayActionDto {
  id: number;
  ebay_item_id: string;
  model_id?: string | null;
  action_type: string;
  offer_amount?: number | null;
  original_price?: number | null;
  shipping?: number | null;
  predicted_profit?: number | null;
  roi?: number | null;
  rule_name?: string | null;
  status: string;
  error_message?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

const GRID_KEY = 'admin_actions';

const AdminActionsPage: React.FC = () => {
  const [rows, setRows] = useState<AiEbayActionDto[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      setError(null);
      try {
        const resp = await fetch('/api/admin/ai/actions');
        if (!resp.ok) {
          throw new Error(`Failed to load actions: ${resp.status}`);
        }
        const data: AiEbayActionDto[] = await resp.json();
        setRows(data || []);
      } catch (err: any) {
        setError(err.message || 'Failed to load actions');
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, []);

  const filteredRows = useMemo(() => {
    if (!search.trim()) return rows;
    const q = search.toLowerCase();
    return rows.filter((row) => {
      return (
        row.ebay_item_id.toLowerCase().includes(q) ||
        (row.model_id && row.model_id.toLowerCase().includes(q)) ||
        (row.action_type && row.action_type.toLowerCase().includes(q)) ||
        (row.rule_name && row.rule_name.toLowerCase().includes(q)) ||
        (row.status && row.status.toLowerCase().includes(q))
      );
    });
  }, [rows, search]);

  const columnMeta: GridColumnMeta[] = [
    { name: 'ebay_item_id', label: 'Item ID', width_default: 160 },
    { name: 'model_id', label: 'Model ID', width_default: 140 },
    { name: 'action_type', label: 'Action', width_default: 120 },
    { name: 'offer_amount', label: 'Offer Amount', type: 'number', width_default: 130 },
    { name: 'original_price', label: 'Original Price', type: 'number', width_default: 130 },
    { name: 'shipping', label: 'Shipping', type: 'number', width_default: 110 },
    { name: 'predicted_profit', label: 'Predicted Profit', type: 'number', width_default: 150 },
    { name: 'roi', label: 'ROI', type: 'number', width_default: 100 },
    { name: 'rule_name', label: 'Rule', width_default: 160 },
    { name: 'status', label: 'Status', width_default: 120 },
    { name: 'error_message', label: 'Error', width_default: 200 },
    { name: 'created_at', label: 'Created At', type: 'datetime', width_default: 180 },
  ];

  const columns = useMemo(
    () =>
      columnMeta.map((c) => ({
        name: c.name,
        label: c.label,
        width: c.width_default ?? 150,
      })),
    [],
  );

  const columnMetaByName: Record<string, GridColumnMeta> = useMemo(() => {
    const map: Record<string, GridColumnMeta> = {};
    columnMeta.forEach((m) => {
      map[m.name] = m;
    });
    return map;
  }, []);

  return (
    <div className="min-h-screen bg-gray-50">
      <FixedHeader />
      <div className="pt-12 p-4 space-y-4">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold">Auto-Offer / Auto-Buy Actions</h1>
        </div>

        <Card className="p-4 mb-4">
          <div className="flex items-center gap-4">
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by item, model, rule, or status..."
              className="border rounded px-3 py-2 w-80 text-sm"
            />
            {loading && <span className="text-sm text-gray-600">Loading...</span>}
            {error && <span className="text-sm text-red-600">{error}</span>}
          </div>
        </Card>

        <div className="bg-white rounded shadow">
          <AppDataGrid
            columns={columns}
            rows={filteredRows as unknown as Record<string, any>[]}
            columnMetaByName={columnMetaByName}
            gridKey={GRID_KEY}
          />
        </div>
      </div>
    </div>
  );
};

export default AdminActionsPage;
```

- `AiEbayActionDto` mirrors the backend DTO.
- Data is fetched from `GET /api/admin/ai/actions`.
- Simple text search filters client-side by item, model, rule name, or status.
- `AppDataGrid` is reused in a static-config mode: columns and metadata are defined locally for this grid, but still benefit from the shared AG Grid theming and behavior.
- `gridKey="admin_actions"` will allow future integration with layout preferences if desired.

### App routing

File: `frontend/src/App.tsx` (excerpt)

```tsx path=/C:/Users/filip/.gemini/antigravity/playground/silent-spirit/frontend/src/App.tsx start=40
import AdminAiGridPage from './pages/AdminAiGridPage';
import AdminAiRulesPage from './pages/AdminAiRulesPage';
import AdminMonitoringPage from './pages/AdminMonitoringPage';
import AdminModelProfitPage from './pages/AdminModelProfitPage';
import AdminActionsPage from './pages/AdminActionsPage';
import './App.css';
import './App.css';
...
          <Route path="/admin/ai-grid" element={<ProtectedRoute><AdminAiGridPage /></ProtectedRoute>} />
          <Route path="/admin/ai-rules" element={<ProtectedRoute><AdminAiRulesPage /></ProtectedRoute>} />
          <Route path="/admin/monitor" element={<ProtectedRoute><AdminMonitoringPage /></ProtectedRoute>} />
          <Route path="/admin/model-profit" element={<ProtectedRoute><AdminModelProfitPage /></ProtectedRoute>} />
          <Route path="/admin/actions" element={<ProtectedRoute><AdminActionsPage /></ProtectedRoute>} />
```

- `/admin/actions` is a protected route; only authenticated users with valid sessions (and appropriate admin rights on the backend) can load it.

### Admin dashboard tile

File: `frontend/src/pages/AdminPage.tsx` (excerpt)

```tsx path=/C:/Users/filip/.gemini/antigravity/playground/silent-spirit/frontend/src/pages/AdminPage.tsx start=60
          <Card className="p-4 hover:shadow-lg cursor-pointer" onClick={() => navigate('/admin/ai-grid')}>
            <h2 className="text-lg font-semibold">AI Grid Playground</h2>
            <p className="text-sm text-gray-600 mt-1">Test AI-запросы и живой грид в админке</p>
          </Card>
          
          <Card className="p-4 hover:shadow-lg cursor-pointer" onClick={() => navigate('/admin/ai-rules')}>
            <h2 className="text-lg font-semibold">AI Rules</h2>
            <p className="text-sm text-gray-600 mt-1">Определить правила "хорошей покупки" и окупаемости</p>
          </Card>
          
          <Card className="p-4 hover:shadow-lg cursor-pointer" onClick={() => navigate('/admin/monitor')}>
            <h2 className="text-lg font-semibold">Monitoring Candidates</h2>
            <p className="text-sm text-gray-600 mt-1">Кандидаты на покупку из eBay мониторинга по моделям</p>
          </Card>
          
          <Card className="p-4 hover:shadow-lg cursor-pointer" onClick={() => navigate('/admin/model-profit')}>
            <h2 className="text-lg font-semibold">Model Profitability</h2>
            <p className="text-sm text-gray-600 mt-1">Просмотр профилей прибыльности моделей и max_buy_price</p>
          </Card>

          <Card className="p-4 hover:shadow-lg cursor-pointer" onClick={() => navigate('/admin/actions')}>
            <h2 className="text-lg font-semibold">Auto-Offer / Auto-Buy Actions</h2>
            <p className="text-sm text-gray-600 mt-1">Планировщик действий (draft / ready / executed / failed)</p>
          </Card>
```

- A new tile appears on the Admin Dashboard under AI-related cards, linking directly to `/admin/actions`.

---

## TypeScript Checks

After implementing the Stage 5 frontend pieces, the following commands were run from `frontend/`:

### `npm run build`

```bash path=null start=null
npm run build
```

- This runs `tsc -b` (project build) and then `vite build`.
- Initial errors encountered and fixed:
  1. **Missing AppDataGrid import path**
     - Error: `Cannot find module '@/components/grid/AppDataGrid'` in `AdminActionsPage.tsx`.
     - Fix: switched to the existing shared grid wrapper at `@/components/datagrid/AppDataGrid` and adjusted the import.
  2. **Incorrect AppDataGrid props**
     - Error: `Property 'getRowId' does not exist` and `GridColumnMeta` not exported from AppDataGrid.
     - Fix: aligned `AdminActionsPage` with the `AppDataGrid` API used by `DataGridPage`:
       - Imported `GridColumnMeta` type from `@/components/DataGridPage`.
       - Constructed `columns` as `{ name, label, width }` objects.
       - Built `columnMetaByName` map and passed `rows` as `Record<string, any>[]` plus `columnMetaByName` to `AppDataGrid`.

- Final `npm run build` output:
  - Build succeeded; only standard Vite bundle size warnings remain (unchanged from prior stages).

### `npx tsc --noEmit`

```bash path=null start=null
npx tsc --noEmit
```

- Type-checks the entire frontend without emitting JavaScript.
- Result: exit code `0`, no TypeScript errors.

These commands confirm that the Stage 5 additions integrate cleanly into the existing TypeScript build.

---

## Summary

Stage 5 introduces an Auto-Offer / Auto-Buy planner that:
- Reads from `ai_ebay_candidates` and joins `model_profit_profile` for profitability.
- Applies global profitability thresholds (`AUTO_BUY_MIN_PROFIT`, `AUTO_BUY_MIN_ROI`) and `max_buy_price` caps.
- Writes planned actions into `ai_ebay_actions`, with a unique `(ebay_item_id, action_type)` constraint to ensure idempotency.
- Supports DRY-RUN mode via `AUTO_BUY_DRY_RUN=True`, producing only `draft` actions without calling eBay.
- When DRY-RUN is disabled, executes stubbed Buy/Offer calls and updates statuses to `executed` or `failed`.
- Starts automatically alongside other background workers in production.
- Exposes planned actions via an admin-only REST API and a dedicated `/admin/actions` page.
- Passes full TypeScript build and `tsc --noEmit` checks.

This completes the Auto-Offer / Auto-Buy planner layer on top of the existing profitability and monitoring infrastructure, while remaining safe-by-default through DRY-RUN behavior and using stubbed eBay integrations.```