# Stage 5 – Auto-Offer / Auto-Buy Planner (Dry Run by Default)

## Overview

Stage 5 добавляет поверх существующих стадий:

- Stage 3 – `model_profit_profile` (профиль прибыльности модели),
- Stage 4 – `ai_ebay_candidates` (мониторинг выгодных листингов),

новый слой **"Auto-Offer / Auto-Buy PLANNER"**.

**Вход:**
- `model_profit_profile` – ожидаемая прибыль и `max_buy_price` по `model_id`.
- `ai_ebay_candidates` – кандидаты с eBay (цена, доставка, ROI, правила).

**Выход:**
- `ai_ebay_actions` – таблица запланированных действий по конкретным eBay‑листингам:
  - `action_type`: `offer` | `buy_now` | (логика сейчас использует только эти два варианта),
  - `offer_amount`: запланированная цена предложения / покупки,
  - `status`: `draft` | `ready` | `executed` | `failed`.

**Ключевые свойства Stage 5:**

- Работает в фоне через отдельный воркер `auto_offer_buy_worker`.
- **По умолчанию DRY RUN** – `AUTO_BUY_DRY_RUN = True`:
  - Никаких реальных вызовов eBay Buy/Offer,
  - только запись `draft`‑действий в `ai_ebay_actions`.
- При `AUTO_BUY_DRY_RUN = False` воркер сразу же пытается выполнить действие через **stub‑функции** (заглушки) eBay Buy/Offer и переводит статусы в `executed` / `failed`.
- Весь функционал завязан на admin‑интерфейс:
  - Backend API: `/api/admin/ai/actions`.
  - Frontend‑страница: `/admin/actions` – грид по `ai_ebay_actions`.

Ниже собраны все элементы реализации: миграция, модели, воркер, настройки, startup‑подключение, admin‑API, frontend и TypeScript‑проверки.

---

## Database – `ai_ebay_actions`

### Alembic‑миграция

Файл: `backend/alembic/versions/ai_ebay_actions_20251125.py`

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

**Важно:**

- `down_revision = "ai_ebay_candidates_20251125"` — миграция Stage 5 логически следует сразу после Stage 4.
- `id` — строковый UUID (36 символов) как PK.
- Уникальный констрейнт `uq_ai_ebay_actions_item_type` гарантирует, что для каждых `(ebay_item_id, action_type)` будет максимум одна строка (защита от дубликатов действий).
- Индекс `idx_ai_ebay_actions_model_id` нужен для фильтрации по `model_id` и аналитики.

### SQLAlchemy‑модель

Файл: `backend/app/models_sqlalchemy/models.py` (фрагмент с `AiEbayCandidate` и `AiEbayAction`).

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

**Семантика `AiEbayAction`:**

- Связан с кандидатами косвенно по `ebay_item_id` и `model_id` (FK не обязательны, т.к. кандидаты могут чиститься независимо).
- `action_type` — тип действия: сейчас используется `offer` и `buy_now`.
- `offer_amount` — реальная сумма, которую мы готовы заплатить / предложить.
- `predicted_profit` / `roi` — пересчитанные значения с учётом профиля прибыльности.
- `rule_name` — имя AI‑правила, сработавшего при отборе кандидата (тащится из `AiEbayCandidate`).
- `status` — жизненный цикл планируемого действия:
  - `draft` — только "план", ничего не отправлено на eBay (режим Dry Run),
  - `ready` — в live‑режиме перед фактическим вызовом stub‑функции,
  - `executed` — stub‑вызов прошёл успешно,
  - `failed` — stub‑вызов не прошёл / выбросил исключение.

---

## Worker Settings – DRY_RUN и пороги

Глобальные настройки воркеров расположены в `backend/app/config/worker_settings.py`.

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

Использование:

- `AUTO_BUY_DRY_RUN` — главный флаг безопасности:
  - `True` — воркер **никогда** не вызывает eBay API (даже stubs можно считать "логическими"), только пишет `draft`‑действия.
  - `False` — воркер переходит к попыткам stub‑исполнения Buy/Offer сразу после планирования.
- `AUTO_BUY_MIN_ROI` и `AUTO_BUY_MIN_PROFIT` — пороги, ниже которых кандидат вообще не рассматривается для авто‑действий.

---

## Worker – `auto_offer_buy_worker.py`

Воркеры Stage 5 живут в `backend/app/workers`. Auto‑offer / auto‑buy воркер:

- периодически просматривает `ai_ebay_candidates`,
- подгружает из `model_profit_profile` `expected_profit` и `max_buy_price`,
- применяет пороги и ограничения,
- создаёт/обновляет строки в `ai_ebay_actions`.

Файл: `backend/app/workers/auto_offer_buy_worker.py`

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

**Суть логики:**

1. Фильтруем кандидатов:
   - ещё нет действий в статусах `draft`/`ready`/`executed` для данного `ebay_item_id`,
   - есть валидный `model_id` и положительный `total_price`.
2. Подгружаем профиль прибыльности по `model_id` из `model_profit_profile`.
3. Считаем `predicted_profit` и `roi`, применяем `AUTO_BUY_MIN_PROFIT`, `AUTO_BUY_MIN_ROI` и ограничение `total_price <= max_buy_price`.
4. Выбираем `action_type = buy_now` или `offer` и `offer_amount`.
5. Через upsert (по `(ebay_item_id, action_type)`) создаём/обновляем `AiEbayAction`.
6. В Dry Run режиме — только статус `draft`, в live режиме — stub‑вызовы eBay и статусы `executed` / `failed`.

---

## Startup Wiring – включение воркера и роутера

### Workers package

Файл: `backend/app/workers/__init__.py`

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

### FastAPI‑приложение (`app.main`)

Файл: `backend/app/main.py` (фрагменты подключения роутера и запуска воркера).

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

Итого:

- Router `admin_actions` зарегистрирован в API.
- Планировщик `run_auto_offer_buy_loop()` стартует при поднятии приложения наряду с прочими воркерами, но только в Postgres‑окружении.

---

## Admin API – `/api/admin/ai/actions`

Админ‑роутер предоставляет чтение `ai_ebay_actions`.

**Файл:** `backend/app/routers/admin_actions.py`

```python path=/C:/Users/filip/.gemini/antigravity/playground/silent-spirit/backend/app/routers/admin_actions.py start=1
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
```

**Особенности:**

- Используются **реальные** текущие зависимости:
  - `get_db` — из `app.models_sqlalchemy`;
  - `admin_required` — из `app.services.auth`;
  - `BaseModel` — стандартный Pydantic.
- Никаких осиротевших модулей (`app.dependencies`, `app.auth_dependencies`, `ApiBaseModel`) в живом коде нет.
- `GET /api/admin/ai/actions` — отдаёт список (по умолчанию до 200, максимум 500) действий, отсортированных по `created_at DESC`.
- `GET /api/admin/ai/actions/{id}` — детальный просмотр одной записи.

---

## Frontend – Admin Actions Page (`/admin/actions`)

### Страница `AdminActionsPage.tsx`

Файл: `frontend/src/pages/AdminActionsPage.tsx`

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

**Поведение страницы:**

- При монтировании делает `GET /api/admin/ai/actions` и сохраняет ответ в `rows`.
- Локальный поиск по `ebay_item_id`, `model_id`, `action_type`, `rule_name`, `status`.
- Отрисовывает грид через общий `AppDataGrid`, с компактной плотностью и фиксированным набором колонок.

### Подключение роутов в `App.tsx`

Файл: `frontend/src/App.tsx` (фрагмент).

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

- Страница `/admin/actions` защищена `ProtectedRoute` на фронте и `admin_required` на бекенде.

### Плитка на `AdminPage`

Файл: `frontend/src/pages/AdminPage.tsx` (фрагмент с AI/Monitoring/Actions блоками).

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

- Кнопка "Auto-Offer / Auto-Buy Actions" ведёт в грид действий по Stage 5.

---

## TypeScript Checks

После добавления `AdminActionsPage` и роутов были выполнены TS‑проверки и сборка фронтенда.

### `npm run build`

```bash path=null start=null
npm run build
```

- Скрипт делает:
  - `tsc -b` (TypeScript project build),
  - затем `vite build`.

**Ошибки, обнаруженные и исправленные в процессе:**

1. **Неверный путь импорта AppDataGrid**
   - Изначально: `import { AppDataGrid, GridColumnMeta } from '@/components/grid/AppDataGrid';`
   - Ошибка TS2307: модуль не найден.
   - Фактический путь компонента: `src/components/datagrid/AppDataGrid.tsx`.
   - Исправлено на:
     ```ts path=null start=null
     import { AppDataGrid } from '@/components/datagrid/AppDataGrid';
     import type { GridColumnMeta } from '@/components/DataGridPage';
     ```

2. **Несоответствие пропсов AppDataGrid**
   - Изначально `AdminActionsPage` пыталась передать пропы в стиле MUI DataGrid (`rows`, `columns`, `getRowId` и т.п.).
   - Реальный интерфейс `AppDataGridProps`:
     ```ts path=null start=null
     export interface AppDataGridProps {
       columns: AppDataGridColumnState[];
       rows: Record<string, any>[];
       columnMetaByName: Record<string, GridColumnMeta>;
       ...
     }
     ```
   - Исправлено:
     - введён `columnMeta: GridColumnMeta[]`;
     - `columns` строится как массив `{ name, label, width }`;
     - `columnMetaByName` — словарь `name → GridColumnMeta`;
     - `rows` приводятся к `Record<string, any>[]`.

После исправлений `npm run build` проходит успешно (остаётся только стандартное предупреждение Vite о размере чанков > 500 kB, присутствовавшее и до Stage 5).

### `npx tsc --noEmit`

```bash path=null start=null
npx tsc --noEmit
```

- Запускает полный TypeScript‑чекап без генерации JS.
- Статус: **exit code 0**, ошибок типов нет.

Это подтверждает, что новый функционал Stage 5 полностью согласован с текущей TS‑конфигурацией проекта.

---

## Summary (вывод по Stage 5)

1. **Схема БД**:
   - Добавлена таблица `ai_ebay_actions` с PK `id` (UUID‑строка), уникальным `(ebay_item_id, action_type)` и индексом по `model_id`.
   - ORM‑модель `AiEbayAction` отражает эту схему и хранит все ключевые поля планируемых авто‑действий.

2. **Настройки воркера**:
   - В `worker_settings.py` добавлены:
     - `AUTO_BUY_DRY_RUN` (по умолчанию `True`),
     - `AUTO_BUY_MIN_ROI`, `AUTO_BUY_MIN_PROFIT`.
   - Эти настройки централизуют бизнес‑пороги для авто‑покупок.

3. **Auto‑offer / Auto‑buy воркер**:
   - `auto_offer_buy_worker.py` раз в 120 секунд просматривает новых кандидатов из `ai_ebay_candidates`,
   - подмешивает туда данные из `model_profit_profile`,
   - применяет пороги по ROI/прибыли и `max_buy_price`,
   - создаёт/обновляет записи в `ai_ebay_actions` с учётом уникальности `(ebay_item_id, action_type)`.
   - В DRY RUN режиме — только `draft`‑действия, без eBay API.
   - В live режиме — вызовы stub‑функций `place_buy_now_stub` / `place_offer_stub` и статусы `executed`/`failed`.

4. **Startup‑интеграция**:
   - Воркер экспортирован из `app.workers.__init__` как `run_auto_offer_buy_loop`.
   - В `app.main` он стартует вместе с остальными фоновыми задачами (только в Postgres‑режиме).

5. **Admin API**:
   - Новый роутер `admin_actions.py` с:
     - `GET /api/admin/ai/actions` — список действий,
     - `GET /api/admin/ai/actions/{id}` — детальный просмотр.
   - Доступ только для админов через `admin_required`.
   - Используются реальные, существующие зависимости (`get_db` из `app.models_sqlalchemy`, `admin_required` из `app.services.auth`, Pydantic `BaseModel`).

6. **Frontend**:
   - Страница `/admin/actions` (`AdminActionsPage.tsx`) отрисовывает грид по `ai_ebay_actions` через `AppDataGrid`.
   - Добавлена навигация:
     - маршрут в `App.tsx`,
     - плитка "Auto-Offer / Auto-Buy Actions" в `AdminPage.tsx`.

7. **TypeScript**:
   - `npm run build` и `npx tsc --noEmit` проходят успешно, все TS‑ошибки, появившиеся по пути, устранены.

В текущем виде Stage 5 реализует **безопасный по умолчанию** (DRY RUN) слой планирования авто‑предложений/покупок, опирающийся на AI‑правила, профили прибыльности и мониторинг eBay, и интегрирован в общую админ‑панель и фоновую архитектуру приложения.