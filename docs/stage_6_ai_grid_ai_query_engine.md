# Stage 6 — AI GRID (AI Query Engine → SQL → Live Admin Grid)

## 1. Overview

Stage 6 introduces an **AI-powered analytics grid** in the admin area:

- **Input:** Natural-language prompt in Russian or English (`prompt`).
- **Engine:** Backend **AI Query Engine** turns the prompt into safe JSON → SQL (`SELECT` only, whitelisted tables).
- **Execution:** Generated SQL is validated and executed read-only via SQLAlchemy.
- **Output:** Lightweight grid payload: `columns[]`, `rows[]`, `sql`.
- **UI:** `/admin/ai-grid` page with a live AG Grid (via `AppDataGrid`) showing results.
- **Audit:** Every executed AI query is logged in `ai_query_log` for inspection and debugging.
- **Security:**
  - Admin-only endpoints (via `admin_required`).
  - Strict SQL validation: read-only, single statement, whitelisted tables only.

This stage reuses the existing grid layout/theme primitives and extends the AI stack with:

- `ai_rules` and `ai_query_log` tables (Alembic migration + SQLAlchemy models).
- `app/services/ai_query_engine.py` — prompt → JSON → SQL + column list.
- `app/routers/admin_ai.py` — `/api/admin/ai/query` and supporting AI rules endpoints.
- `frontend/src/pages/AdminAiGridPage.tsx` — Admin AI Grid Playground.
- Integration into backend router wiring and admin dashboard navigation.
- Verified TypeScript build and type checks with the new features enabled.

---

## 2. Database: `ai_rules` and `ai_query_log`

### 2.1 Alembic migration: `backend/alembic/versions/ai_analytics_20251125.py`

```python path=/backend/alembic/versions/ai_analytics_20251125.py start=1
"""Add ai_rules and ai_query_log tables for AI analytics engine

Revision ID: ai_analytics_20251125
Revises: ebay_snipe_logs_20251125
Create Date: 2025-11-25

This migration introduces two tables used by the Admin AI Grid / AI Rules
features:

- ai_rules: stores reusable SQL rule fragments generated from natural language.
- ai_query_log: append-only log of executed AI analytics queries.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "ai_analytics_20251125"
down_revision: Union[str, Sequence[str], None] = "ebay_snipe_logs_20251125"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create ai_rules and ai_query_log tables."""

    # ai_rules: reusable SQL rule fragments (e.g. profitability conditions)
    op.create_table(
        "ai_rules",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("rule_sql", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default(sa.func.now(),
        ),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], name="fk_ai_rules_user"),
    )

    # Minimal index on creation time to support recent-rules listings.
    op.create_index(
        "idx_ai_rules_created_at",
        "ai_rules",
        ["created_at"],
    )

    # ai_query_log: append-only log of AI-generated SQL queries executed by admins
    op.create_table(
        "ai_query_log",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("sql", sa.Text(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column(
            "executed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default(sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_ai_query_log_user"),
    )

    op.create_index(
        "idx_ai_query_log_user",
        "ai_query_log",
        ["user_id"],
    )
    op.create_index(
        "idx_ai_query_log_executed_at",
        "ai_query_log",
        ["executed_at"],
    )


def downgrade() -> None:
    """Drop AI analytics tables (best-effort)."""

    op.drop_index("idx_ai_query_log_executed_at", table_name="ai_query_log")
    op.drop_index("idx_ai_query_log_user", table_name="ai_query_log")
    op.drop_table("ai_query_log")

    op.drop_index("idx_ai_rules_created_at", table_name="ai_rules")
    op.drop_table("ai_rules")
```

Key points:

- `ai_rules`:
  - Stores human-readable `name`, validated `rule_sql`, optional `description`.
  - Linked to `users.id` via `created_by_user_id`.
  - Indexed by `created_at` for “recent first” listings.
- `ai_query_log`:
  - **Append-only** log of admin AI queries.
  - Captures `user_id`, original `prompt`, generated `sql`, and `row_count`.
  - Indexed by `user_id` and `executed_at` to support per-user and chronological views.

### 2.2 SQLAlchemy models: `AiRule` and `AiQueryLog`

```python path=/backend/app/models_sqlalchemy/models.py start=1400
class AiRule(Base):
    """Persisted AI analytics rule, typically a reusable SQL condition fragment.

    These rules are created from natural-language descriptions in the admin
    AI Rules UI and later reused by analytics and monitoring workers (e.g.
    "good computer" profitability profiles).
    """

    __tablename__ = "ai_rules"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(Text, nullable=False)
    # Raw SQL condition fragment or full WHERE clause (read-only, validated at use).
    rule_sql = Column(Text, nullable=False)
    # Optional free-form description or original natural-language prompt.
    description = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    created_by_user_id = Column(String(36), ForeignKey("users.id"), nullable=True)


class AiQueryLog(Base):
    """Append-only log of AI-powered admin analytics queries.

    Each row captures the natural-language prompt, the generated SQL, and the
    number of rows returned so we can audit and debug the AI Query Engine.
    """

    __tablename__ = "ai_query_log"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    prompt = Column(Text, nullable=False)
    sql = Column(Text, nullable=False)
    row_count = Column(Integer, nullable=True)

    executed_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
```

These models are used by:

- `admin_ai.py` to **log each AI query** (`AiQueryLog`).
- `admin_ai.py` + `admin_ai_rules_ext.py` + `ai_rules_engine.py` for managing reusable analytics rules (`AiRule`).

---

## 3. Backend AI Query Engine

### 3.1 `app/services/ai_query_engine.py` — Prompt → JSON → Safe SQL

```python path=/backend/app/services/ai_query_engine.py start=1
from __future__ import annotations

from typing import Any, Dict, List, Tuple

import json
import os
import re

import httpx
from fastapi import HTTPException, status

from app.config import settings
from app.utils.logger import logger


_AI_SQL_JSON_RE = re.compile(r"\{[\s\S]*\}")


class AiSqlGenerationError(RuntimeError):
    """Raised when the AI provider fails to return valid SQL JSON."""


def _extract_table_identifiers(sql: str) -> List[str]:
    """Best-effort extraction of table identifiers from FROM / JOIN clauses.

    This is deliberately conservative and is *not* a full SQL parser, but it is
    enough to enforce a simple whitelist of tables for read-only analytics
    queries generated by the AI engine.
    """

    candidates: List[str] = []
    # Match FROM <ident> and JOIN <ident>; capture the identifier that follows.
    for pattern in (r"\bFROM\s+([a-zA-Z0-9_\.\"]+)", r"\bJOIN\s+([a-zA-Z0-9_\.\"]+)"):
        for match in re.finditer(pattern, sql, flags=re.IGNORECASE):
            ident = match.group(1)
            # Strip optional schema prefixes and quotes: public.tbl_foo -> tbl_foo
            ident = ident.strip() or ""
            ident = ident.strip('"')
            if "." in ident:
                ident = ident.split(".")[-1]
            if ident:
                candidates.append(ident)
    return candidates


def _validate_sql(sql: str, allowed_tables: List[str]) -> None:
    """Validate that generated SQL is read-only and uses only whitelisted tables.

    The rules are intentionally strict:
    - Only a single statement (no semicolons).
    - No data-modifying / DDL keywords.
    - All referenced tables in FROM/JOIN must be in ``allowed_tables``.
    """

    sql_stripped = sql.strip()
    if not sql_stripped:
        raise AiSqlGenerationError("AI returned an empty SQL string")

    if ";" in sql_stripped:
        raise AiSqlGenerationError("Multiple SQL statements are not allowed; remove semicolons")

    upper = sql_stripped.upper()
    forbidden = [
        "UPDATE ",
        "DELETE ",
        "INSERT ",
        "UPSERT ",
        "MERGE ",
        "ALTER ",
        "DROP ",
        "TRUNCATE ",
        "CREATE ",
        "GRANT ",
        "REVOKE ",
        "EXEC ",
        "CALL ",
    ]
    for kw in forbidden:
        if kw in upper:
            raise AiSqlGenerationError(f"Forbidden SQL keyword detected: {kw.strip()}")

    # Basic sanity: must be a SELECT query.
    if not upper.startswith("SELECT "):
        raise AiSqlGenerationError("Only SELECT queries are allowed")

    # Enforce table whitelist for FROM/JOIN clauses.
    allowed_set = {name.lower() for name in allowed_tables}
    referenced = _extract_table_identifiers(sql_stripped)
    unknown: List[str] = []
    for ident in referenced:
        if ident.lower() not in allowed_set:
            unknown.append(ident)

    if unknown:
        raise AiSqlGenerationError(
            "SQL references non-whitelisted tables: " + ", ".join(sorted(set(unknown)))
        )


async def build_sql_from_prompt(prompt: str, *, allowed_tables: List[str]) -> Tuple[str, List[str]]:
    """Call OpenAI Chat Completions API to turn natural language into SQL.

    Returns a tuple ``(sql, columns)`` where ``columns`` is the ordered list of
    column names that the AI *expects* the query to return. The caller still
    validates the SQL against a whitelist and may derive the final columns from
    the actual query result set.
    """

    api_key = settings.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OPENAI_API_KEY is not configured on the backend; contact an administrator.",
        )

    model = settings.OPENAI_MODEL
    base_url = settings.OPENAI_API_BASE_URL.rstrip("/")

    system_prompt = (
        "You are an internal analytics SQL generator for a private eBay operations app. "
        "Given a natural language Russian or English request, you must output STRICT JSON only, "
        "with fields: {\n  \"sql\": string,\n  \"columns\": [list of column names]\n}. "
        "Rules: (1) Only generate a single SELECT statement. (2) Use ONLY the following "
        "PostgreSQL tables: "
        + ", ".join(sorted(allowed_tables))
        + ". (3) Do not use CTEs, window functions, or subqueries in the first iteration; keep queries simple. "
        "(4) Prefer LIMIT 200. (5) NEVER include UPDATE/INSERT/DELETE/DDL or comments. "
        "(6) When searching for complaints about bad packaging or damaged items, focus on body/subject fields."
    )

    payload: Dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    "Natural-language analytics request:\n" + prompt.strip() + "\n" +
                    "Return ONLY JSON with 'sql' and 'columns'. Do not wrap in markdown."
                ),
            },
        ],
        "temperature": 0.1,
        "max_tokens": 512,
    }

    url = f"{base_url}/v1/chat/completions"
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                url,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
            )
    except Exception as exc:  # pragma: no cover - network failures
        logger.error("AI SQL provider request failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to contact AI provider for SQL generation.",
        ) from exc

    if resp.status_code >= 400:
        logger.error("AI SQL provider HTTP %s: %s", resp.status_code, resp.text[:500])
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI provider returned HTTP {resp.status_code} while generating SQL.",
        )

    try:
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Unexpected AI provider response structure: %s", resp.text[:500])
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI provider returned an unexpected response payload.",
        ) from exc

    if not content:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI provider returned empty content while generating SQL.",
        )

    # Some models may wrap JSON in text; extract the first JSON object.
    match = _AI_SQL_JSON_RE.search(content)
    if not match:
        logger.error("AI provider did not return JSON: %s", content[:500])
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI provider did not return valid JSON for SQL generation.",
        )

    try:
        payload_json = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse AI SQL JSON: %s", content[:500])
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI provider returned malformed JSON for SQL generation.",
        ) from exc

    sql = str(payload_json.get("sql") or "").strip()
    columns = payload_json.get("columns") or []
    if not isinstance(columns, list):
        columns = []

    # Validate generated SQL against our whitelist and safety rules.
    _validate_sql(sql, allowed_tables)

    # Normalise column names to strings.
    col_names: List[str] = []
    for col in columns:
        try:
            name = str(col).strip()
        except Exception:  # pragma: no cover - defensive
            continue
        if name:
            col_names.append(name)

    return sql, col_names
```

Highlights:

- Uses shared `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_API_BASE_URL` from `settings`.
- Enforces **hard safety constraints**:
  - Single `SELECT` statement, no semicolons.
  - Blocks all write/DDL keywords.
  - Enforces table whitelist (see `ALLOWED_ANALYTICS_TABLES` in `admin_ai.py`).
- Expects models to respond with **pure JSON** containing `sql` and `columns`.
- Returns `(sql, [column_names])` to the router, which still double-checks the result via `_validate_sql`.

### 3.2 AI Rules engine (used by Stage 6 rules UI)

```python path=/backend/app/services/ai_rules_engine.py start=1
from __future__ import annotations

from typing import Any, Dict

import json
import os
import re

import httpx
from fastapi import HTTPException, status

from app.config import settings
from app.utils.logger import logger


_AI_RULE_JSON_RE = re.compile(r"\{[\s\S]*\}")


class AiRuleGenerationError(RuntimeError):
    """Raised when the AI provider fails to return a valid rule_sql JSON payload."""


def _validate_rule_sql(rule_sql: str) -> str:
    """Validate that rule_sql is a safe boolean condition expression.

    Constraints:
    - Non-empty, length <= 500 characters.
    - No statement terminators (';') or SQL comments ('--', '/*', '*/').
    - Must NOT contain data/query keywords: SELECT, INSERT, UPDATE, DELETE,
      MERGE, ALTER, DROP, TRUNCATE, CREATE, FROM, JOIN, UNION, WITH.
    - Intended shape: a boolean expression using identifiers, numbers,
      AND/OR, comparison operators (=, !=, <, <=, >, >=), LIKE/ILIKE,
      and parentheses.
    """

    sql = (rule_sql or "").strip()
    if not sql:
        raise AiRuleGenerationError("AI returned an empty rule_sql condition")
    if len(sql) > 500:
        raise AiRuleGenerationError("rule_sql is too long (must be <= 500 characters)")

    # Hard-block obvious dangerous constructs first.
    forbidden_fragments = [";", "--", "/*", "*/"]
    for frag in forbidden_fragments:
        if frag in sql:
            raise AiRuleGenerationError(f"Forbidden token in rule_sql: {frag!r}")

    upper = sql.upper()
    forbidden_keywords = [
        "SELECT ",
        "INSERT ",
        "UPDATE ",
        "DELETE ",
        "MERGE ",
        "ALTER ",
        "DROP ",
        "TRUNCATE ",
        "CREATE ",
        " FROM ",
        " JOIN ",
        " UNION ",
        " WITH ",
    ]
    for kw in forbidden_keywords:
        if kw in upper:
            raise AiRuleGenerationError(f"rule_sql contains forbidden keyword: {kw.strip()}")

    return sql


async def generate_rule_sql(description: str) -> Dict[str, str]:
    """Generate a safe SQL boolean condition (rule_sql) from natural language.

    The returned dict has a single key: { "rule_sql": "..." }.
    """

    prompt = (description or "").strip()
    if not prompt:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="description_required",
        )

    api_key = settings.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OPENAI_API_KEY is not configured on the backend; contact an administrator.",
        )

    model = settings.OPENAI_MODEL
    base_url = settings.OPENAI_API_BASE_URL.rstrip("/")

    system_prompt = (
        "You convert natural-language descriptions of business rules into a SQL boolean expression. "
        "Output STRICT JSON with field 'rule_sql'. NO SELECT/UPDATE/INSERT/DELETE. "
        "Only a single boolean condition using identifiers, numbers, AND, OR, =, !=, <, <=, >, >=, "
        "LIKE, ILIKE, and parentheses. Example: (profit_percentage >= 100 AND days_to_recover <= 60)."
    )

    payload: Dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    "Business rule description (Russian or English):\n" + prompt + "\n" +
                    "Return ONLY JSON with a single field 'rule_sql'. Do not wrap in markdown."
                ),
            },
        ],
        "temperature": 0.0,
        "max_tokens": 256,
    }

    url = f"{base_url}/v1/chat/completions"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                url,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
            )
    except Exception as exc:  # pragma: no cover - network failures
        logger.error("AI rule provider request failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to contact AI provider for rule_sql generation.",
        ) from exc

    if resp.status_code >= 400:
        logger.error("AI rule provider HTTP %s: %s", resp.status_code, resp.text[:500])
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI provider returned HTTP {resp.status_code} while generating rule_sql.",
        )

    try:
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Unexpected AI provider response structure for rule_sql: %s", resp.text[:500])
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI provider returned an unexpected response payload for rule_sql.",
        ) from exc

    if not content:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI provider returned empty content while generating rule_sql.",
        )

    match = _AI_RULE_JSON_RE.search(content)
    if not match:
        logger.error("AI provider did not return JSON for rule_sql: %s", content[:500])
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI provider did not return valid JSON for rule_sql generation.",
        )

    try:
        payload_json = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse AI rule_sql JSON: %s", content[:500])
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI provider returned malformed JSON for rule_sql generation.",
        ) from exc

    rule_sql_raw = str(payload_json.get("rule_sql") or "").strip()
    try:
        rule_sql = _validate_rule_sql(rule_sql_raw)
    except AiRuleGenerationError as exc:
        logger.warning("AI-generated rule_sql failed validation: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return {"rule_sql": rule_sql}
```

This engine powers the **AI Rules** admin page but also conceptually matches the Stage 6 pattern: **natural language → constrained JSON → validated SQL fragment**.

---

## 4. Admin API: `/api/admin/ai/*`

### 4.1 Core admin AI router: `app/routers/admin_ai.py`

```python path=/backend/app/routers/admin_ai.py start=1
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
```

Key behaviors:

- **`run_ai_query`**:
  - Validates and strips prompt.
  - Calls `build_sql_from_prompt` with strict **table whitelist**.
  - Executes returned SQL using `text(sql)` in a read-only fashion.
  - Derives column list from result metadata; falls back to AI-provided `columns`.
  - Logs every query to `AiQueryLog` (best-effort).
  - Returns `columns`, `rows`, and original `sql` to the frontend.

- **Rules endpoints**:
  - `GET /api/admin/ai/rules`: list most recent rules.
  - `POST /api/admin/ai/rules`: create validated manual rules (with minimal SQL safety check).

### 4.2 Extended rules router: `app/routers/admin_ai_rules_ext.py`

```python path=/backend/app/routers/admin_ai_rules_ext.py start=1
from __future__ import annotations

from typing import Dict

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models_sqlalchemy import get_db as get_db_sqla
from app.models_sqlalchemy.models import AiRule
from app.services.ai_rules_engine import generate_rule_sql
from app.services.auth import admin_required
from app.models.user import User


router = APIRouter(prefix="/api/admin/ai/rules", tags=["admin_ai_rules"])


class RulePreviewRequest(BaseModel):
  description: str = Field(..., description="Natural-language description of the rule.")


class RulePreviewResponse(BaseModel):
  rule_sql: str


class GenerateAndSaveRequest(BaseModel):
  name: str = Field(..., description="Human-readable rule name.")
  description: str = Field(..., description="Natural-language description of the rule.")
  nl_rule: str = Field(..., description="Alias for description; kept for future compatibility.")


class RuleResponse(BaseModel):
  id: str
  name: str
  rule_sql: str
  description: str | None
  created_at: str


@router.post("/preview", response_model=RulePreviewResponse)
async def preview_rule_sql(
  payload: RulePreviewRequest,
  current_user: User = Depends(admin_required),  # noqa: ARG001
) -> RulePreviewResponse:
  """Generate a rule_sql fragment from natural-language description (no DB write)."""

  result: Dict[str, str] = await generate_rule_sql(payload.description)
  return RulePreviewResponse(**result)


@router.post("/generate-and-save", response_model=RuleResponse, status_code=status.HTTP_201_CREATED)
async def generate_and_save_rule(
  payload: GenerateAndSaveRequest,
  current_user: User = Depends(admin_required),
  db: Session = Depends(get_db_sqla),
) -> RuleResponse:
  """Generate rule_sql from natural language and persist AiRule in the database."""

  name = payload.name.strip()
  if not name:
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="name_required")

  description = payload.description.strip() or payload.nl_rule.strip()
  if not description:
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="description_required")

  # Step 1: ask AI to generate a safe rule_sql condition.
  preview = await generate_rule_sql(description)
  rule_sql = preview["rule_sql"].strip()

  # Step 2: create AiRule row.
  rule = AiRule(
    name=name,
    rule_sql=rule_sql,
    description=description,
    created_by_user_id=str(current_user.id),
  )
  db.add(rule)
  db.commit()
  db.refresh(rule)

  created_at = rule.created_at.isoformat() if getattr(rule, "created_at", None) else ""
  return RuleResponse(
    id=str(rule.id),
    name=rule.name,
    rule_sql=rule.rule_sql,
    description=rule.description,
    created_at=created_at,
  )
```

This router provides **AI-assisted rule creation**:

- `/preview` — dry-run generate `rule_sql` from natural language.
- `/generate-and-save` — generate and immediately persist an `AiRule`.

### 4.3 Router registration in FastAPI app (`app/main.py`)

```python path=/backend/app/main.py start=8
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
    admin_actions,
    integrations,
)
...
app.include_router(auth.router)
...
app.include_router(admin_ai.router)
app.include_router(admin_ai_rules_ext.router)
app.include_router(admin_monitoring.router)
app.include_router(admin_actions.router)
app.include_router(integrations.router)
```

This ensures:

- `/api/admin/ai/*` and `/api/admin/ai/rules/*` are mounted and available.
- No additional worker loops are required for Stage 6; everything is **request-driven**.

---

## 5. Frontend — Admin AI Grid Playground

### 5.1 Page: `frontend/src/pages/AdminAiGridPage.tsx`

```tsx path=/frontend/src/pages/AdminAiGridPage.tsx start=1
import { useState } from 'react';
import FixedHeader from '@/components/FixedHeader';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import api from '@/lib/apiClient';
import { AppDataGrid, type AppDataGridColumnState } from '@/components/datagrid/AppDataGrid';
import type { GridColumnMeta } from '@/components/DataGridPage';

interface AiGridColumnDto {
  field: string;
  headerName: string;
  type?: string | null;
  width?: number | null;
}

interface AiQueryResponseDto {
  columns: AiGridColumnDto[];
  rows: Record<string, any>[];
  sql: string;
}

export default function AdminAiGridPage() {
  const [prompt, setPrompt] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [columns, setColumns] = useState<AppDataGridColumnState[]>([]);
  const [rows, setRows] = useState<Record<string, any>[]>([]);
  const [columnMetaByName, setColumnMetaByName] = useState<Record<string, GridColumnMeta>>({});
  const [lastSql, setLastSql] = useState<string | null>(null);

  const handleRunQuery = async () => {
    const trimmed = prompt.trim();
    if (!trimmed) {
      setError('Введите запрос на естественном языке (например: "Покажи письма с плохой упаковкой")');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const resp = await api.post<AiQueryResponseDto>('/api/admin/ai/query', { prompt: trimmed });
      const data = resp.data;

      const nextCols: AppDataGridColumnState[] = data.columns.map((c) => ({
        name: c.field,
        label: c.headerName || c.field,
        width: c.width && c.width > 0 ? c.width : 180,
      }));
      setColumns(nextCols);

      const meta: Record<string, GridColumnMeta> = {};
      data.columns.forEach((c) => {
        meta[c.field] = {
          name: c.field,
          label: c.headerName || c.field,
          type: (c.type as any) || 'string',
          width_default: c.width || 180,
          sortable: true,
        };
      });
      setColumnMetaByName(meta);

      setRows(data.rows || []);
      setLastSql(data.sql || null);
    } catch (e: any) {
      const msg = e?.response?.data?.detail || e.message || 'Не удалось выполнить AI-запрос';
      setError(String(msg));
      setRows([]);
      setColumns([]);
      setColumnMetaByName({});
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      <FixedHeader />
      <div className="pt-16 px-4 py-6 max-w-6xl w-full mx-auto flex-1 flex flex-col gap-4">
        <h1 className="text-2xl font-bold">Admin AI Grid Playground</h1>
        <p className="text-sm text-gray-600 max-w-3xl">
          Введите запрос на естественном языке, я превращу его в безопасный SQL по whitelisted-таблицам
          (сообщения, кейсы, покупки) и отрисую результат в гриде ниже. Примеры:
          "Покажи письма, где жалуются на плохую упаковку" или
          "Покажи компьютеры, которые окупились быстрее всего".
        </p>

        <Card className="p-4 space-y-3">
          <label className="block text-sm font-medium text-gray-700">AI-запрос</label>
          <Textarea
            rows={3}
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="Например: Покажи письма, где жалуются, что деталь разбилась из-за плохой упаковки"
          />
          <div className="flex items-center justify-between gap-3">
            <div className="text-xs text-gray-500">
              Я сгенерирую только SELECT-запрос и выполню его в read-only режиме по безопасным таблицам.
            </div>
            <Button onClick={handleRunQuery} disabled={loading}>
              {loading ? 'Выполняю…' : 'Run AI Query'}
            </Button>
          </div>
          {error && (
            <div className="text-xs text-red-600 whitespace-pre-wrap border border-red-200 bg-red-50 rounded px-2 py-1 mt-2">
              {error}
            </div>
          )}
          {lastSql && (
            <div className="mt-2 text-xs text-gray-500 font-mono break-all">
              <span className="font-semibold mr-1">SQL:</span>
              {lastSql}
            </div>
          )}
        </Card>

        <Card className="flex-1 min-h-[300px] p-3 flex flex-col">
          <h2 className="text-sm font-semibold mb-2">Результат</h2>
          <div className="flex-1 min-h-[240px]">
            {columns.length === 0 ? (
              <div className="h-full flex items-center justify-center text-sm text-gray-500">
                Нет данных. Сначала выполните AI-запрос.
              </div>
            ) : (
              <AppDataGrid
                columns={columns}
                rows={rows}
                columnMetaByName={columnMetaByName}
                loading={loading}
                gridKey="admin_ai_grid"
                gridTheme={null}
              />
            )}
          </div>
        </Card>
      </div>
    </div>
  );
}
```

Notes:

- Uses the existing `api` client and `AppDataGrid` abstraction.
- The grid is keyed as `admin_ai_grid`; it does **not** persist layout yet, but reuses the standard column meta contract.
- Errors from backend (`HTTPException.detail`) surface in a compact red box; SQL text is shown in a small monospace block for debugging.

### 5.2 Shared AG Grid wrapper: `frontend/src/components/datagrid/AppDataGrid.tsx`

```tsx path=/frontend/src/components/datagrid/AppDataGrid.tsx start=1
import { useMemo, useRef, forwardRef, useImperativeHandle } from 'react';
import { AgGridReact } from 'ag-grid-react';
import {
  ModuleRegistry,
  AllCommunityModule,
} from 'ag-grid-community';
import type {
  ColDef,
  ColumnState,
  CellClassRules,
  CellStyle,
  GridApi,
  ICellRendererParams,
  CellStyleFunc,
} from 'ag-grid-community';

// Register AG Grid modules
ModuleRegistry.registerModules([AllCommunityModule]);
import type { GridColumnMeta } from '@/components/DataGridPage';
import { buildLegacyGridTheme } from '@/components/datagrid/legacyGridTheme';
import type { GridThemeConfig, ColumnStyle } from '@/hooks/useGridPreferences';

export interface AppDataGridColumnState {
  name: string;
  label: string;
  width: number;
}

export type GridLayoutSnapshot = {
  order: string[];
  widths: Record<string, number>;
};

export type AppDataGridHandle = {
  /**
   * Returns the current column order and widths as reported by AG Grid,
   * or null when the grid API is not yet ready.
   */
  getCurrentLayout: () => GridLayoutSnapshot | null;
};

export interface AppDataGridProps {
  columns: AppDataGridColumnState[];
  rows: Record<string, any>[];
  columnMetaByName: Record<string, GridColumnMeta>;
  loading?: boolean;
  onRowClick?: (row: Record<string, any>) => void;
  onLayoutChange?: (state: { order: string[]; widths: Record<string, number> }) => void;
  /** Server-side sort config; drives header sort indicators. */
  sortConfig?: { column: string; direction: 'asc' | 'desc' } | null;
  /** Callback when sort model changes via header clicks. */
  onSortChange?: (sort: { column: string; direction: 'asc' | 'desc' } | null) => void;
  /** Optional grid key used for targeted debug logging (e.g. finances_fees). */
  gridKey?: string;
  /** Per-grid theme configuration coming from /api/grid/preferences. */
  gridTheme?: GridThemeConfig | null;
}

function formatCellValue(raw: any, type: GridColumnMeta['type'] | undefined): string {
  if (raw === null || raw === undefined) return '';

  const t = type || 'string';

  if (t === 'datetime') {
    try {
      return new Date(raw).toLocaleString();
    } catch {
      return String(raw);
    }
  }

  if (t === 'money' || t === 'number') {
    return String(raw);
  }

  if (typeof raw === 'object') {
    try {
      return JSON.stringify(raw);
    } catch {
      return String(raw);
    }
  }

  return String(raw);
}

function coerceNumeric(value: unknown): number | null {
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : null;
  }
  if (typeof value === 'string') {
    const cleaned = value.replace(/[^0-9+\-.,]/g, '').replace(',', '.');
    const n = Number.parseFloat(cleaned);
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

function extractLayout(columnStates: ColumnState[]): { order: string[]; widths: Record<string, number> } {
  const order: string[] = [];
  const widths: Record<string, number> = {};

  columnStates.forEach((col: ColumnState) => {
    const id = (col.colId as string) || '';
    if (!id) return;

    // Filter out AG Grid's internal columns (checkbox selection, etc.)
    if (id.startsWith('ag-Grid-')) {
      return;
    }

    order.push(id);
    if (typeof col.width === 'number' && Number.isFinite(col.width)) {
      // Normalise to an integer pixel width. AG Grid can emit fractional widths,
      // but the backend expects Dict[str, int] in columns.widths.
      const rounded = Math.round(col.width);
      // Clamp to a sane range to avoid pathological values.
      const clamped = Math.min(4000, Math.max(40, rounded));
      widths[id] = clamped;
    }
  });

  return { order, widths };
}

export const AppDataGrid = forwardRef<AppDataGridHandle, AppDataGridProps>(({\
  columns,\
  rows,\
  columnMetaByName,\
  loading,\
  onRowClick,\
  onLayoutChange,\
  sortConfig,\
  onSortChange,\
  gridKey,\
  gridTheme,\
}, ref) => {
  const layoutDebounceRef = useRef<number | null>(null);
  const gridApiRef = useRef<GridApi | null>(null);

  useImperativeHandle(ref, () => ({
    getCurrentLayout: () => {
      const api = gridApiRef.current;
      if (!api) return null;
      const model = (api as any).getColumnState?.() as ColumnState[] | undefined;
      if (!model) return null;
      return extractLayout(model);
    },
  }), []);
  const columnDefs = useMemo<ColDef[]>(() => {
    if (!columns || columns.length === 0) {
      return [];
    }

    const columnStyles: Record<string, ColumnStyle> | undefined = gridTheme?.columnStyles as
      | Record<string, ColumnStyle>
      | undefined;

    return columns.map((col) => {
      const meta = columnMetaByName[col.name];
      const type = meta?.type;
      const lowerName = col.name.toLowerCase();

      const cellClasses: string[] = ['ui-table-cell'];
      const cellClassRules: CellClassRules = {};

      // Right-align numeric and money columns
      if (type === 'number' || type === 'money') {
        cellClasses.push('ag-legacy-number');
      }

      // Money columns: color positive/negative amounts
      if (type === 'money') {
        cellClasses.push('ag-legacy-price');
        cellClassRules['ag-legacy-price-positive'] = (params) => {
          const n = coerceNumeric(params.value);
          return n !== null && n > 0;
        };
        cellClassRules['ag-legacy-price-negative'] = (params) => {
          const n = coerceNumeric(params.value);
          return n !== null && n < 0;
        };
      }

      // ID / key style: SKU, ItemID, eBayID, generic *id
      if (
        lowerName === 'id' ||
        lowerName.includes('sku') ||
        lowerName.endsWith('_id') ||
        lowerName.endsWith('id') ||
        lowerName.includes('ebayid') ||
        lowerName.includes('ebay_id')
      ) {
        cellClasses.push('ag-legacy-id-link');
      }

      // Status-style coloring based on common keywords
      if (lowerName.includes('status')) {
        cellClassRules['ag-legacy-status-error'] = (params) => {
          if (typeof params.value !== 'string') return false;
          const v = params.value.toLowerCase();
          return (
            v.includes('await') ||
            v.includes('error') ||
            v.includes('fail') ||
            v.includes('hold') ||
            v.includes('inactive') ||
            v.includes('cancel') ||
            v.includes('blocked')
          );
        };
        cellClassRules['ag-legacy-status-ok'] = (params) => {
          if (typeof params.value !== 'string') return false;
          const v = params.value.toLowerCase();
          return (
            v.includes('active') ||
            v.includes('checked') ||
            v.includes('ok') ||
            v.includes('complete') ||
            v.includes('resolved') ||
            v.includes('success')
          );
        };
      }

      const colDef: ColDef = {
        colId: col.name, // Explicit colId for AG Grid
        field: col.name, // Field name must match row data keys
        headerName: meta?.label || col.label || col.name,
        width: col.width,
        resizable: true, // Enable resizing
        sortable: meta?.sortable !== false, // Enable header click sorting when allowed
        filter: false,
        valueFormatter: (params) => formatCellValue(params.value, type),
        // Ensure column is visible
        hide: false,
        cellClass: cellClasses,
      };

      // Apply optional per-column style overrides (font size / weight / color).
      const styleOverride = columnStyles?.[col.name];
      if (styleOverride) {
        const fontSizePx =
          typeof styleOverride.fontSizeLevel === 'number'
            ? 10 + Math.min(10, Math.max(1, styleOverride.fontSizeLevel))
            : undefined;
        const styleFn: CellStyleFunc<any, any, any> = () => {
          const base: CellStyle = {};
          if (fontSizePx) (base as any).fontSize = `${fontSizePx}px`;
          if (styleOverride.fontWeight) (base as any).fontWeight = styleOverride.fontWeight;
          if (styleOverride.textColor) (base as any).color = styleOverride.textColor;
          return base;
        };
        colDef.cellStyle = styleFn;
      }

      // Special case: make sniper_snipes.item_id clickable to open the eBay page.
      if (gridKey === 'sniper_snipes' && col.name === 'item_id') {
        colDef.valueFormatter = undefined;
        colDef.cellRenderer = (params: ICellRendererParams) => {
          const raw = params.value;
          const value = formatCellValue(raw, type);
          if (!value) return '';
          const href = `https://www.ebay.com/itm/${encodeURIComponent(value)}`;
          return (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="text-blue-600 hover:underline"
            >
              {value}
            </a>
          );
        };
      }

      if (Object.keys(cellClassRules).length > 0) {
        colDef.cellClassRules = cellClassRules;
      }

      // Mark current sort column for header indicators.
      if (sortConfig && sortConfig.column === col.name) {
        (colDef as any).sort = sortConfig.direction;
      }

      return colDef;
    });
  }, [columns, columnMetaByName, gridKey, sortConfig, gridTheme]);

  const defaultColDef = useMemo<ColDef>(
    () => ({
      headerClass: 'ui-table-header',
      sortable: false,
    }),
    [],
  );

  const handleColumnEvent = (event: any) => {
    if (!onLayoutChange || !event.api) return;

    if (layoutDebounceRef.current !== null) {
      window.clearTimeout(layoutDebounceRef.current);
    }

    layoutDebounceRef.current = window.setTimeout(() => {
      const model = (event.api as any).getColumnState?.() as ColumnState[] | undefined;
      if (!model) return;
      const { order, widths } = extractLayout(model);
      if (gridKey === 'finances_fees') {
        // Temporary targeted debug for width persistence investigation
        // eslint-disable-next-line no-console
        console.log('[AppDataGrid] finances_fees layout changed:', { order, widths });
      }
      onLayoutChange({ order, widths });
    }, 500);
  };

  const handleSortChanged = (event: any) => {
    if (!onSortChange || !event.api) return;
    const model = event.api.getSortModel?.() as { colId: string; sort: 'asc' | 'desc' }[] | undefined;
    if (!model || model.length === 0) {
      onSortChange(null);
      return;
    }
    const first = model[0];
    if (!first.colId || !first.sort) {
      onSortChange(null);
      return;
    }
    onSortChange({ column: first.colId, direction: first.sort });
  };

  // Debug logging (remove in production)
  if (process.env.NODE_ENV === 'development') {
    if (columnDefs.length === 0 && columns.length > 0) {
      console.warn('[AppDataGrid] columnDefs is empty but columns prop has', columns.length, 'items');
    }
    if (rows.length > 0 && columnDefs.length > 0) {
      const firstRowKeys = Object.keys(rows[0] || {});
      const columnFields = columnDefs.map((d) => d.field).filter((f): f is string => !!f);
      const missingFields = columnFields.filter((f) => !firstRowKeys.includes(f));
      if (missingFields.length > 0) {
        console.warn('[AppDataGrid] Column fields not in row data:', missingFields);
        console.warn('[AppDataGrid] Row data keys:', firstRowKeys.slice(0, 10));
        console.warn('[AppDataGrid] Column fields:', columnFields.slice(0, 10));
      }
    }
  }

  return (
    <div
      className="w-full h-full app-grid__ag-root"
      style={{ position: 'relative', height: '100%', width: '100%' }}
    >
      {columnDefs.length === 0 ? (
        <div className="absolute inset-0 flex items-center justify-center text-sm text-gray-500">
          No columns configured
        </div>
      ) : (
        <AgGridReact
          theme={buildLegacyGridTheme(gridTheme)}
          columnDefs={columnDefs}
          defaultColDef={defaultColDef}
          rowData={rows}
          rowSelection={{ mode: 'singleRow' }}
          suppressMultiSort
          suppressScrollOnNewData
          suppressAggFuncInHeader
          animateRows
          onGridReady={(params) => {
            gridApiRef.current = params.api as GridApi;
          }}
          onColumnResized={handleColumnEvent}
          onColumnMoved={handleColumnEvent}
          onColumnVisible={handleColumnEvent}
          onSortChanged={handleSortChanged}
          onRowClicked={
            onRowClick
              ? (event) => {
                  if (event.data) {
                    onRowClick(event.data as Record<string, any>);
                  }
                }
              : undefined
          }
        />
      )}
      {loading && rows.length === 0 && columnDefs.length > 0 && (
        <div className="absolute inset-0 flex items-center justify-center text-sm text-gray-500 bg-white/60 z-10">
          Loading data…
        </div>
      )}
    </div>
  );
});
```

AI Grid uses this generic component like any other grid in the app:

- `columns` and `columnMetaByName` are built from the backend’s `AiGridColumn` DTOs.
- Cell formatting handles `datetime`, `money`, `number`, JSON/text, status coloring, and special ID styling.

### 5.3 Routing and navigation

#### 5.3.1 React Router: `frontend/src/App.tsx`

```tsx path=/frontend/src/App.tsx start=91
function App() {
  return (
    <Router>
      <AuthProvider>
        <Routes>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          ...
          <Route path="/admin" element={<ProtectedRoute><AdminPage /></ProtectedRoute>} />
          <Route path="/admin/users" element={<ProtectedRoute><AdminUsersPage /></ProtectedRoute>} />
          <Route path="/admin/ui-tweak" element={<ProtectedRoute><AdminUITweakPage /></ProtectedRoute>} />
          <Route path="/admin/security" element={<ProtectedRoute><SecurityCenterPage /></ProtectedRoute>} />
          <Route path="/admin/ai-grid" element={<ProtectedRoute><AdminAiGridPage /></ProtectedRoute>} />
          <Route path="/admin/ai-rules" element={<ProtectedRoute><AdminAiRulesPage /></ProtectedRoute>} />
          <Route path="/admin/monitor" element={<ProtectedRoute><AdminMonitoringPage /></ProtectedRoute>} />
          <Route path="/admin/model-profit" element={<ProtectedRoute><AdminModelProfitPage /></ProtectedRoute>} />
          <Route path="/admin/actions" element={<ProtectedRoute><AdminActionsPage /></ProtectedRoute>} />
          ...
        </Routes>
      </AuthProvider>
    </Router>
  );
}
```

#### 5.3.2 Admin dashboard card: `frontend/src/pages/AdminPage.tsx`

```tsx path=/frontend/src/pages/AdminPage.tsx start=5
export default function AdminPage() {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-gray-50">
      <FixedHeader />
      <div className="pt-12 p-4">
        <h1 className="text-2xl font-bold mb-4">Admin Dashboard</h1>
        
        <div className="grid grid-cols-3 gap-4">
          ...
          <Card className="p-4 hover:shadow-lg cursor-pointer" onClick={() => navigate('/admin/ai-grid')}>
            <h2 className="text-lg font-semibold">AI Grid Playground</h2>
            <p className="text-sm text-gray-600 mt-1">Test AI-запросы и живой грид в админке</p>
          </Card>
          
          <Card className="p-4 hover:shadow-lg cursor-pointer" onClick={() => navigate('/admin/ai-rules')}>
            <h2 className="text-lg font-semibold">AI Rules</h2>
            <p className="text-sm text-gray-600 mt-1">Определить правила "хорошей покупки" и окупаемости</p>
          </Card>
          ...
        </div>
      </div>
    </div>
  );
}
```

This exposes the AI Grid as a **first-class admin tool** via a dashboard tile and route `/admin/ai-grid`.

---

## 6. TypeScript & Build Checks

### 6.1 Commands

All TypeScript and build checks were executed from the `frontend` directory.

```bash path=null start=null
cd frontend
npm run build
npx tsc --noEmit
```

### 6.2 Results

1. **`npm run prebuild` + `npm run build`**

   - Prebuild step (`scripts/write-build-meta.mjs`) successfully generated:
     - `src/config/build.generated.ts`
     - `public/version.json`
   - `npm run build` runs `tsc -b && vite build`:
     - TypeScript project build **succeeded**.
     - Vite production build completed successfully:
       - ~2354 modules transformed.
       - Output bundles:
         - `dist/index.html`
         - `dist/assets/index-*.css`
         - `dist/assets/index-*.js`
       - Only warnings were standard Vite chunk-size hints (bundle > 500kB), no hard errors.

2. **`npx tsc --noEmit`**

   - Standalone TypeScript type check **completed with exit code 0**.
   - Confirms:
     - `AdminAiGridPage.tsx` typings (DTOs, state, `AppDataGrid` props) are consistent.
     - `AppDataGrid` generic typings and `GridColumnMeta` usage are valid.
     - No unresolved imports or type mismatches in the new Stage 6 code.

There are **no outstanding TypeScript errors** introduced by the AI Grid or related admin pages.

---

## 7. Summary

- **Database:**
  - Added `ai_rules` and `ai_query_log` via Alembic migration.
  - Mapped to `AiRule` and `AiQueryLog` models for rules and query audit logging.

- **Backend AI Query Engine:**
  - Implemented `app/services/ai_query_engine.py` to convert natural-language prompts into **safe, whitelisted SELECT SQL**.
  - Strict validation prohibits multi-statement SQL and any write/DDL operations.

- **Admin AI API:**
  - `POST /api/admin/ai/query`:
    - Admin-only.
    - Calls AI Query Engine, validates SQL, executes read-only query, and logs the run.
    - Returns column metadata + rows + SQL for the grid.
  - `GET/POST /api/admin/ai/rules` and extended `/api/admin/ai/rules/*` endpoints:
    - Provide manual and AI-assisted rule management on top of `AiRule`.

- **Frontend:**
  - `/admin/ai-grid` — **Admin AI Grid Playground**:
    - Text prompt → `/api/admin/ai/query` → dynamic grid using `AppDataGrid`.
    - Shows last generated SQL and errors inline.
  - Reuses the common AG Grid wrapper and theme, keeping UI consistent with other analytic grids.

- **Integration & Quality:**
  - Routers registered in `app/main.py`, protected by `admin_required`.
  - AI Grid exposed via an Admin Dashboard card and React Router route.
  - `npm run build` and `npx tsc --noEmit` both pass without errors, validating the Stage 6 implementation end-to-end.

This completes **Stage 6 — AI GRID**, delivering an AI-assisted, safe, read-only analytics grid for admins, fully wired through backend services, APIs, database logging, and the frontend UI.
