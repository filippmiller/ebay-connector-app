from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config_worker_settings import (
    MIN_PROFIT_MARGIN,
    AUTO_BUY_DRY_RUN,
    AUTO_BUY_MIN_ROI,
    AUTO_BUY_MIN_PROFIT,
)
from app.models_sqlalchemy import get_db as get_db_sqla
from app.models_sqlalchemy.models import AiRule, AiQueryLog, AiEbayCandidate, AiEbayAction
from app.services.auth import admin_required
from app.models.user import User


router = APIRouter(prefix="/api/admin/ai/overview", tags=["admin_ai_overview"])


class AiOverviewRules(BaseModel):
    total: int
    last_created_at: Optional[str]


class AiOverviewQueries(BaseModel):
    total: int
    last_24h: int
    last_executed_at: Optional[str]


class AiOverviewModels(BaseModel):
    profiles_total: int


class AiOverviewCandidates(BaseModel):
    total: int
    by_rule: Dict[str, int]


class AiOverviewActions(BaseModel):
    total: int
    by_status: Dict[str, int]


class AiOverviewConfig(BaseModel):
    MIN_PROFIT_MARGIN: float
    AUTO_BUY_DRY_RUN: bool
    AUTO_BUY_MIN_ROI: float
    AUTO_BUY_MIN_PROFIT: float


class AiOverviewResponse(BaseModel):
    rules: AiOverviewRules
    queries: AiOverviewQueries
    models: AiOverviewModels
    candidates: AiOverviewCandidates
    actions: AiOverviewActions
    config: AiOverviewConfig


@router.get("/", response_model=AiOverviewResponse, dependencies=[Depends(admin_required)])
async def get_ai_overview(
    db: Session = Depends(get_db_sqla),
    current_user: User = Depends(admin_required),  # noqa: ARG001
) -> AiOverviewResponse:
    """Return a high-level overview of AI rules, queries, candidates and actions.

    This endpoint is read-only and is intended for the Admin AI & Automation
    Center dashboard. It aggregates lightweight counts and timestamps without
    exposing any sensitive data.
    """

    now = datetime.now(timezone.utc)
    window_start = now - timedelta(hours=24)

    # Rules
    rules_total = db.query(func.count(AiRule.id)).scalar() or 0
    last_rule_created_at = db.query(func.max(AiRule.created_at)).scalar()
    rules_block = AiOverviewRules(
        total=int(rules_total),
        last_created_at=last_rule_created_at.isoformat() if last_rule_created_at else None,
    )

    # Queries
    queries_total = db.query(func.count(AiQueryLog.id)).scalar() or 0
    queries_last_24h = (
        db.query(func.count(AiQueryLog.id))
        .filter(AiQueryLog.executed_at >= window_start)
        .scalar()
        or 0
    )
    last_query_executed_at = db.query(func.max(AiQueryLog.executed_at)).scalar()
    queries_block = AiOverviewQueries(
        total=int(queries_total),
        last_24h=int(queries_last_24h),
        last_executed_at=last_query_executed_at.isoformat() if last_query_executed_at else None,
    )

    # Models: model_profit_profile is a plain SQL projection; it may not exist in all environments.
    try:
        profiles_total_row = db.execute(
            func.count().select().select_from(func.cast(func.text("model_profit_profile"), None))  # type: ignore[arg-type]
        )
        # The above is intentionally defensive; if it ever fails we fall back to 0 below.
        profiles_total = int(list(profiles_total_row)[0][0])  # pragma: no cover - extremely defensive
    except Exception:  # pragma: no cover - table might not exist
        try:
            result = db.execute("SELECT COUNT(*) FROM model_profit_profile")
            profiles_total = int(result.scalar() or 0)
        except Exception:
            profiles_total = 0
    models_block = AiOverviewModels(profiles_total=profiles_total)

    # Candidates
    candidates_total = db.query(func.count(AiEbayCandidate.id)).scalar() or 0
    by_rule_rows = (
        db.query(AiEbayCandidate.rule_name, func.count(AiEbayCandidate.id))
        .group_by(AiEbayCandidate.rule_name)
        .all()
    )
    by_rule: Dict[str, int] = {}
    for rule_name, count in by_rule_rows:
        key = rule_name or "__NO_RULE__"
        by_rule[key] = int(count or 0)
    candidates_block = AiOverviewCandidates(total=int(candidates_total), by_rule=by_rule)

    # Actions
    actions_total = db.query(func.count(AiEbayAction.id)).scalar() or 0
    by_status_rows = (
        db.query(AiEbayAction.status, func.count(AiEbayAction.id))
        .group_by(AiEbayAction.status)
        .all()
    )
    by_status: Dict[str, int] = {}
    for status_value, count in by_status_rows:
        key = status_value or "unknown"
        by_status[key] = int(count or 0)
    actions_block = AiOverviewActions(total=int(actions_total), by_status=by_status)

    config_block = AiOverviewConfig(
        MIN_PROFIT_MARGIN=float(MIN_PROFIT_MARGIN),
        AUTO_BUY_DRY_RUN=bool(AUTO_BUY_DRY_RUN),
        AUTO_BUY_MIN_ROI=float(AUTO_BUY_MIN_ROI),
        AUTO_BUY_MIN_PROFIT=float(AUTO_BUY_MIN_PROFIT),
    )

    return AiOverviewResponse(
        rules=rules_block,
        queries=queries_block,
        models=models_block,
        candidates=candidates_block,
        actions=actions_block,
        config=config_block,
    )