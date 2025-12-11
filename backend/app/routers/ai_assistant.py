"""AI Assistant router - unified endpoint for all AI domains.

Phase 1: Analytics (read-only SQL generation from natural language)
Phase 2: Email, Cases, Messages (future)
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.models_sqlalchemy import get_db
from app.services.admin_auth import get_current_admin_user
from app.services.ai.schema_discovery import refresh_schema_catalog
from app.services.ai_query_engine import build_sql_from_prompt
from app.utils.logger import logger

router = APIRouter(prefix="/api/ai-assistant", tags=["ai-assistant"])


# ================== Schemas ==================

class QueryRequest(BaseModel):
    text: str
    locale: str = "ru-RU"
    source: str = "widget"  # "widget" | "admin-training"
    context: Optional[Dict[str, Any]] = None


class QueryResponse(BaseModel):
    rows: List[Dict[str, Any]]
    columns: List[str]
    explanation: str
    sql: str
    domain: str = "analytics"


class SchemaRefreshResponse(BaseModel):
    tables: int
    columns: int
    message: str


# ================== Endpoints ==================

@router.post("/schema-refresh", response_model=SchemaRefreshResponse)
async def refresh_schema(
    whitelist: Optional[List[str]] = None,
    db: Session = Depends(get_db),
    _admin = Depends(get_current_admin_user),  # Admin only
):
    """Refresh schema catalog from information_schema.
    
    Admin only. Populates ai_schema_tables and ai_schema_columns.
    """
    
    try:
        result = await refresh_schema_catalog(db, whitelist=whitelist)
        
        return SchemaRefreshResponse(
            tables=result["tables"],
            columns=result["columns"],
            message=f"Schema catalog refreshed: {result['tables']} tables, {result['columns']} columns"
        )
    
    except Exception as e:
        logger.error(f"Schema refresh failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Schema refresh failed: {str(e)}"
        )


@router.post("/query", response_model=QueryResponse)
async def ai_assistant_query(
    request: QueryRequest,
    db: Session = Depends(get_db),
):
    """Unified AI Assistant endpoint for all domains.
    
    Phase 1: domain forced to "analytics" (read-only SQL queries)
    """
    
    domain = "analytics"  # Phase 1: hardcoded
    
    logger.info(
        f"AI Assistant query: domain={domain}, locale={request.locale}, "
        f"source={request.source}, text='{request.text[:100]}...'"
    )
    
    try:
        # 1. Load schema context
        schema_tables = await _load_schema_context(db)
        
        if not schema_tables:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Schema catalog empty. Admin must run /schema-refresh first."
            )
        
        # 2. Load semantic rules (optional, Phase 1 may have none)
        semantic_rules = await _load_semantic_rules(db, domain=domain, locale=request.locale)
        
        # 3. Generate SQL using existing ai_query_engine
        sql, columns = await build_sql_from_prompt(
            prompt=request.text,
            allowed_tables=schema_tables,
            db=db,
        )
        
        # 4. Execute SQL
        rows, actual_columns = await _execute_sql(db, sql)
        
        # 5. Generate explanation
        explanation = await _generate_explanation(
            request.text, rows, request.locale
        )
        
        # 6. Log query
        await _log_query(
            db=db,
            domain=domain,
            input_text=request.text,
            input_locale=request.locale,
            context=request.context,
            sql=sql,
            row_count=len(rows),
            execution_ok=True,
        )
        
        return QueryResponse(
            rows=rows,
            columns=actual_columns or columns,
            explanation=explanation,
            sql=sql,
            domain=domain,
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"AI Assistant query failed: {e}", exc_info=True)
        
        # Log failed query
        await _log_query(
            db=db,
            domain=domain,
            input_text=request.text,
            input_locale=request.locale,
            context=request.context,
            sql="",
            row_count=0,
            execution_ok=False,
            error_message=str(e),
        )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AI query failed: {str(e)}"
        )


# ================== Helper Functions ==================

async def _load_schema_context(db: Session) -> List[str]:
    """Load list of active table names from schema catalog."""
    
    result = db.execute(text("""
        SELECT table_name 
        FROM ai_schema_tables
        WHERE is_active = true
        ORDER BY table_name
    """))
    
    return [row[0] for row in result.fetchall()]


async def _load_semantic_rules(
    db: Session,
    domain: str,
    locale: str,
) -> List[Dict]:
    """Load semantic rules for intent matching (Phase 1: may be empty)."""
    
    result = db.execute(text("""
        SELECT id, user_pattern, target_sql_template, confidence
        FROM ai_semantic_rules
        WHERE domain = :domain 
          AND locale = :locale
          AND is_active = true
        ORDER BY confidence DESC NULLS LAST
        LIMIT 10
    """), {"domain": domain, "locale": locale})
    
    return [
        {
            "id": str(row[0]),
            "pattern": row[1],
            "sql_template": row[2],
            "confidence": float(row[3]) if row[3] else None,
        }
        for row in result.fetchall()
    ]


async def _execute_sql(db: Session, sql: str) -> tuple[List[Dict], List[str]]:
    """Execute read-only SQL and return rows + column names."""
    
    result = db.execute(text(sql))
    rows_raw = result.fetchall()
    columns = list(result.keys()) if rows_raw else []
    
    # Convert to list of dicts
    rows = [
        {col: value for col, value in zip(columns, row)}
        for row in rows_raw
    ]
    
    return rows, columns


async def _generate_explanation(
    user_text: str,
    rows: List[Dict],
    locale: str,
) -> str:
    """Generate short explanation of results in user's locale."""
    
    if locale.startswith("ru"):
        if len(rows) == 0:
            return f"По запросу '{user_text}' ничего не найдено."
        else:
            return f"Найдено {len(rows)} результат(ов) по запросу '{user_text}'."
    else:
        if len(rows) == 0:
            return f"No results found for '{user_text}'."
        else:
            return f"Found {len(rows)} result(s) for '{user_text}'."


async def _log_query(
    db: Session,
    domain: str,
    input_text: str,
    input_locale: str,
    context: Optional[Dict],
    sql: str,
    row_count: int,
    execution_ok: bool,
    used_semantic_rule_id: Optional[str] = None,
    error_message: Optional[str] = None,
):
    """Log query to ai_queries_log."""
    
    try:
        execution_meta = {
            "rows_count": row_count,
        }
        
        if error_message:
            execution_meta["error_text"] = error_message
        
        db.execute(text("""
            INSERT INTO ai_queries_log (
                domain, prompt, sql, row_count, input_locale, context,
                used_semantic_rule_id, execution_ok, execution_result_meta,
                ai_answer_preview
            ) VALUES (
                :domain, :prompt, :sql, :row_count, :input_locale, :context,
                :used_semantic_rule_id, :execution_ok, :execution_meta,
                :ai_answer_preview
            )
        """), {
            "domain": domain,
            "prompt": input_text,
            "sql": sql,
            "row_count": row_count,
            "input_locale": input_locale,
            "context": context,
            "used_semantic_rule_id": used_semantic_rule_id,
            "execution_ok": execution_ok,
            "execution_meta": execution_meta,
            "ai_answer_preview": input_text[:200],
        })
        
        db.commit()
    except Exception as e:
        logger.error(f"Failed to log AI query: {e}")
        # Don't fail the request if logging fails
        pass
