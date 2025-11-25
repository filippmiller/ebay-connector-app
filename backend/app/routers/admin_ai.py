from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models_sqlalchemy import get_db as get_db_sqla
from app.models_sqlalchemy.models import AiRule, AiQueryLog
from app.services.ai_query_engine import build_sql_from_prompt, AiSqlGenerationError
from app.services.auth import admin_required
from app.models.user import User
from app.utils.logger import logger


router = APIRouter(prefix="/api/admin/ai", tags=["admin_ai"])


ALLOWED_ANALYTICS_TABLES: List[str] = [
    # Core complaint / communication sources
    "tbl_ebay_messages",
    "tbl_ebay_cases",
    # Buying / profitability-related legacy tables
    "tbl_ebay_buyer",
    "tbl_ebay_seller_info",
    "tbl_ebay_fees",
    # Supabase projections used by the app
    "ebay_messages",
    "ebay_cases",
    "purchases",
    "purchase_line_items",
    "transactions",
    "fees",
]


class AiQueryRequest(BaseModel):
    prompt: str = Field(..., description="Natural-language analytics request in Russian or English.")


class AiGridColumn(BaseModel):
    field: str
    headerName: str
    type: Optional[str] = None
    width: Optional[int] = None


class AiQueryResponse(BaseModel):
    columns: List[AiGridColumn]
    rows: List[Dict[str, Any]]
    sql: str


class AiRulePreviewRequest(BaseModel):
    prompt: str = Field(..., description="Natural-language description of the rule (e.g. what is a 'good computer').")


class AiRuleCreateRequest(BaseModel):
    name: str = Field(..., description="Human-readable rule name.")
    rule_sql: str = Field(..., description="SQL condition fragment to apply in WHERE clauses.")
    description: Optional[str] = Field(
        None,
        description="Optional free-form description or original natural-language definition.",
    )


class AiRuleResponse(BaseModel):
    id: str
    name: str
    rule_sql: str
    description: Optional[str]
    created_at: str


@router.post("/query", response_model=AiQueryResponse)
async def run_ai_query(
    payload: AiQueryRequest,
    current_user: User = Depends(admin_required),
    db: Session = Depends(get_db_sqla),
) -> AiQueryResponse:
    """Run an AI-generated read-only SQL query and return a lightweight grid payload.

    This endpoint is admin-only and is used exclusively by the Admin AI Grid
    playground. It never exposes write capabilities; the AI Query Engine is
    constrained to a small set of whitelisted tables and SELECT-only queries.
    """

    prompt = payload.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="prompt_required")

    try:
        sql, ai_columns = await build_sql_from_prompt(prompt, allowed_tables=ALLOWED_ANALYTICS_TABLES)
    except AiSqlGenerationError as exc:
        logger.warning("AI SQL validation failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    logger.info("[admin_ai] user_id=%s running AI SQL: %s", current_user.id, sql)

    try:
        result = db.execute(text(sql))
    except Exception as exc:
        logger.error("AI SQL execution error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to execute generated SQL: {type(exc).__name__}: {exc}",
        ) from exc

    rows_raw = result.mappings().all()
    row_dicts: List[Dict[str, Any]] = [dict(row) for row in rows_raw]

    # Derive column names from the result set when available; fall back to AI-suggested list.
    result_col_names: List[str] = list(result.keys()) if result.keys() else []
    if not result_col_names and ai_columns:
        result_col_names = ai_columns

    columns: List[AiGridColumn] = []
    for name in result_col_names:
        label = name.replace("_", " ").title()
        columns.append(
            AiGridColumn(
                field=name,
                headerName=label,
                type=None,
                width=180,
            )
        )

    # Log query in ai_query_log for audit/debug.
    try:
        log = AiQueryLog(
            user_id=str(current_user.id),
            prompt=prompt,
            sql=sql,
            row_count=len(row_dicts),
        )
        db.add(log)
        db.commit()
    except Exception as exc:  # pragma: no cover - logging must be best-effort
        logger.warning("Failed to log AI query: %s", exc)

    return AiQueryResponse(columns=columns, rows=row_dicts, sql=sql)


@router.get("/rules", response_model=List[AiRuleResponse])
async def list_ai_rules(
    current_user: User = Depends(admin_required),  # noqa: ARG001
    db: Session = Depends(get_db_sqla),
) -> List[AiRuleResponse]:
    """Return all AI rules ordered by creation time (newest first)."""

    rules: List[AiRule] = (
        db.query(AiRule)
        .order_by(AiRule.created_at.desc())
        .limit(200)
        .all()
    )

    out: List[AiRuleResponse] = []
    for r in rules:
        created_at = r.created_at.isoformat() if getattr(r, "created_at", None) else ""
        out.append(
            AiRuleResponse(
                id=str(r.id),
                name=r.name,
                rule_sql=r.rule_sql,
                description=r.description,
                created_at=created_at,
            )
        )
    return out


@router.post("/rules", response_model=AiRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_ai_rule(
    payload: AiRuleCreateRequest,
    current_user: User = Depends(admin_required),
    db: Session = Depends(get_db_sqla),
) -> AiRuleResponse:
    """Create a new AI rule from a validated SQL condition fragment."""

    name = payload.name.strip()
    rule_sql = payload.rule_sql.strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="name_required")
    if not rule_sql:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="rule_sql_required")

    # Very lightweight safety check: rule_sql must not contain forbidden keywords.
    upper = rule_sql.upper()
    forbidden = ["UPDATE ", "DELETE ", "INSERT ", "ALTER ", "DROP ", "TRUNCATE ", "CREATE "]
    for kw in forbidden:
        if kw in upper:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"rule_sql contains forbidden keyword: {kw.strip()}",
            )

    rule = AiRule(
        name=name,
        rule_sql=rule_sql,
        description=(payload.description or "").strip() or None,
        created_by_user_id=str(current_user.id),
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)

    created_at = rule.created_at.isoformat() if getattr(rule, "created_at", None) else ""
    return AiRuleResponse(
        id=str(rule.id),
        name=rule.name,
        rule_sql=rule.rule_sql,
        description=rule.description,
        created_at=created_at,
    )
