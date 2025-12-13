# First Stage AI Integration Brief – eBay Connector App (25 November 2025)

## 1. Purpose & Scope

This brief documents the **first stage of AI integration** into the eBay Connector App:

- Admin-only **AI Grid Playground** that converts natural-language analytics questions into read-only SQL and renders the result into a live grid.
- Admin-only **AI Rules** builder for storing reusable SQL rule fragments (e.g. what is a “good computer” purchase).
- Backend plumbing for **safe SQL generation** via OpenAI, with strict table whitelists and read-only enforcement.
- Production-grade **DB migrations** and wiring into the existing FastAPI + Supabase/Postgres + React/AG Grid stack.

This stage is intentionally narrow: it focuses on *analytics and experimentation* in the admin area, without yet triggering automatic actions (bids/offers/snipes). Those will build on top of these primitives.


## 2. High-Level Architecture

### 2.1 Components Added in This Stage

**Backend**
- OpenAI-related config fields in `Settings` (no secrets hard-coded, only via env).
- AI SQL generation service: `ai_query_engine` (talks to OpenAI Chat Completions API).
- New models: `AiRule`, `AiQueryLog` (for rules and query auditing).
- Alembic migration `ai_analytics_20251125` creating `ai_rules` and `ai_query_log` in Supabase.
- Admin router `admin_ai` exposing:
  - `POST /api/admin/ai/query` – run AI-generated SELECT and return grid JSON.
  - `GET /api/admin/ai/rules` – list saved rules.
  - `POST /api/admin/ai/rules` – create a new rule.

**Frontend**
- `AdminAiGridPage` – admin AI grid playground at `/admin/ai-grid`.
- `AdminAiRulesPage` – admin AI rules page at `/admin/ai-rules`.
- Registration of both pages in React routing and Admin dashboard tiles.

### 2.2 Data Flow Overview

1. Admin opens `/admin/ai-grid`.
2. Admin types a natural-language query (RU/EN), e.g.:
   > Покажи письма, где жалуются, что деталь разбилась из-за плохой упаковки.
3. Frontend sends `POST /api/admin/ai/query { prompt }`.
4. Backend:
   - Uses OpenAI to translate prompt → JSON `{ sql, columns }` under a strict **whitelist** of tables.
   - Validates SQL (single SELECT, no DML/DDL, only allowed tables in FROM/JOIN).
   - Executes SQL against Supabase/Postgres in read-only mode.
   - Logs the query in `ai_query_log`.
   - Returns `{ columns, rows, sql }` to frontend.
5. Frontend renders JSON into `AppDataGrid` (AG Grid wrapper) with all the usual grid affordances (sort, copy, zebra, etc.).

6. Separately, in `/admin/ai-rules` admins can define and save **rules** as SQL WHERE fragments, which will later be reused by analytics and workers (e.g. “good computer” conditions).


## 3. Backend Changes

### 3.1 Settings: OpenAI Configuration

File: `backend/app/config.py`

```python path=C:\Users\filip\.gemini\antigravity\playground\silent-spirit\backend\app\config.py start=13
    DEBUG: bool = False

    # Optional OpenAI configuration for internal analytics/AI features.
    # OPENAI_API_KEY must be provided via environment in production; when missing,
    # AI-driven admin features (AI Grid, AI Rules builder) will return a clear
    # error instead of failing with a generic 500.
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_API_BASE_URL: str = os.getenv("OPENAI_API_BASE_URL", "https://api.openai.com")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
```

Notes:
- No secrets are hard-coded. `OPENAI_API_KEY` is expected from environment.
- If `OPENAI_API_KEY` is missing, admin AI endpoints respond with 503 + a clear error instead of breaking the whole app.


### 3.2 AI SQL Generation Service

File: `backend/app/services/ai_query_engine.py`

```python path=C:\Users\filip\.gemini\antigravity\playground\silent-spirit\backend\app\services\ai_query_engine.py start=1
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
    """Best-effort extraction of table identifiers from FROM / JOIN clauses."""
    candidates: List[str] = []
    for pattern in (r"\bFROM\s+([a-zA-Z0-9_\.\"]+)", r"\bJOIN\s+([a-zA-Z0-9_\.\"]+)"):
        for match in re.finditer(pattern, sql, flags=re.IGNORECASE):
            ident = match.group(1).strip().strip('"')
            if "." in ident:
                ident = ident.split(".")[-1]
            if ident:
                candidates.append(ident)
    return candidates


def _validate_sql(sql: str, allowed_tables: List[str]) -> None:
    """Validate that generated SQL is read-only and uses only whitelisted tables."""
    sql_stripped = sql.strip()
    if not sql_stripped:
        raise AiSqlGenerationError("AI returned an empty SQL string")
    if ";" in sql_stripped:
        raise AiSqlGenerationError("Multiple SQL statements are not allowed; remove semicolons")

    upper = sql_stripped.upper()
    forbidden = [
        "UPDATE ", "DELETE ", "INSERT ", "UPSERT ", "MERGE ",
        "ALTER ", "DROP ", "TRUNCATE ", "CREATE ", "GRANT ",
        "REVOKE ", "EXEC ", "CALL ",
    ]
    for kw in forbidden:
        if kw in upper:
            raise AiSqlGenerationError(f"Forbidden SQL keyword detected: {kw.strip()}")

    if not upper.startswith("SELECT "):
        raise AiSqlGenerationError("Only SELECT queries are allowed")

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
    """Call OpenAI Chat Completions API to turn natural language into SQL."""

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
        "with fields: {\\n  \\\"sql\\\": string,\\n  \\\"columns\\\": [list of column names]\\n}. "
        "Rules: (1) Only generate a single SELECT statement. (2) Use ONLY the following "
        "PostgreSQL tables: " + ", ".join(sorted(allowed_tables)) + ". "
        "(3) Do not use CTEs, window functions, or subqueries in the first iteration; keep queries simple. "
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
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(
            url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
        )

    if resp.status_code >= 400:
        logger.error("AI SQL provider HTTP %s: %s", resp.status_code, resp.text[:500])
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI provider returned HTTP {resp.status_code} while generating SQL.",
        )

    data = resp.json()
    content = data["choices"][0]["message"]["content"]
    if not content:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI provider returned empty content while generating SQL.",
        )

    match = _AI_SQL_JSON_RE.search(content)
    if not match:
        logger.error("AI provider did not return JSON: %s", content[:500])
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI provider did not return valid JSON for SQL generation.",
        )

    payload_json = json.loads(match.group(0))
    sql = str(payload_json.get("sql") or "").strip()
    columns = payload_json.get("columns") or []
    if not isinstance(columns, list):
        columns = []

    _validate_sql(sql, allowed_tables)

    col_names: List[str] = []
    for col in columns:
        name = str(col).strip()
        if name:
            col_names.append(name)

    return sql, col_names
```

Key properties:
- Strict **read-only** SQL policy (SELECT only, no multiple statements).
- **Table whitelist** enforced at SQL validation level.
- AI is treated as a helper for text → SQL; the backend still fully owns validation and execution.


### 3.3 Models: AiRule and AiQueryLog

File: `backend/app/models_sqlalchemy/models.py`

```python path=C:\Users\filip\.gemini\antigravity\playground\silent-spirit\backend\app\models_sqlalchemy\models.py start=1395
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
    """Append-only log of AI-powered admin analytics queries."""

    __tablename__ = "ai_query_log"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    prompt = Column(Text, nullable=False)
    sql = Column(Text, nullable=False)
    row_count = Column(Integer, nullable=True)

    executed_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
```

Use cases:
- `AiRule`: persisted "business rules" like “good computer = 100% profit in 60 days”, represented as SQL WHERE fragment.
- `AiQueryLog`: audit trail for AI-driven analytics usage (who asked what, which SQL was executed, and how many rows came back).


### 3.4 Alembic Migration: ai_analytics_20251125

File: `backend/alembic/versions/ai_analytics_20251125.py`

- Creates `ai_rules` and `ai_query_log` tables, including indexes on `created_at`, `user_id`, and `executed_at`.
- `down_revision` = `ebay_snipe_logs_20251125` to sit on top of recent sniper work.
- Applied in production via:
  - `railway run poetry -C backend run alembic upgrade heads`
  - Verified with `alembic current -v` that `ai_analytics_20251125` is one of the heads.


### 3.5 Admin AI Router

File: `backend/app/routers/admin_ai.py`

```python path=C:\Users\filip\.gemini\antigravity\playground\silent-spirit\backend\app\routers\admin_ai.py start=18
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
```

#### Endpoint: `POST /api/admin/ai/query`

```python path=C:\Users\filip\.gemini\antigravity\playground\silent-spirit\backend\app\routers\admin_ai.py start=77
@router.post("/query", response_model=AiQueryResponse)
async def run_ai_query(
    payload: AiQueryRequest,
    current_user: User = Depends(admin_required),
    db: Session = Depends(get_db_sqla),
) -> AiQueryResponse:
    """Run an AI-generated read-only SQL query and return a lightweight grid payload."""

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

    result_col_names: List[str] = list(result.keys()) if result.keys() else []
    if not result_col_names and ai_columns:
        result_col_names = ai_columns

    columns: List[AiGridColumn] = []
    for name in result_col_names:
        label = name.replace("_", " ").title()
        columns.append(AiGridColumn(field=name, headerName=label, type=None, width=180))

    try:
        log = AiQueryLog(
            user_id=str(current_user.id),
            prompt=prompt,
            sql=sql,
            row_count=len(row_dicts),
        )
        db.add(log)
        db.commit()
    except Exception as exc:
        logger.warning("Failed to log AI query: %s", exc)

    return AiQueryResponse(columns=columns, rows=row_dicts, sql=sql)
```

#### Endpoints: `GET /api/admin/ai/rules`, `POST /api/admin/ai/rules`

```python path=C:\Users\filip\.gemini\antigravity\playground\silent-spirit\backend\app\routers\admin_ai.py start=147
@router.get("/rules", response_model=List[AiRuleResponse])
async def list_ai_rules(
    current_user: User = Depends(admin_required),
    db: Session = Depends(get_db_sqla),
) -> List[AiRuleResponse]:
    rules: List[AiRule] = (
        db.query(AiRule)
        .order_by(AiRule.created_at.desc())
        .limit(200)
        .all()
    )
    out: List[AiRuleResponse] = []
    for r in rules:
        created_at = r.created_at.isoformat() if getattr(r, "created_at", None) else ""
        out.append(AiRuleResponse(
            id=str(r.id), name=r.name, rule_sql=r.rule_sql,
            description=r.description, created_at=created_at,
        ))
    return out


@router.post("/rules", response_model=AiRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_ai_rule(
    payload: AiRuleCreateRequest,
    current_user: User = Depends(admin_required),
    db: Session = Depends(get_db_sqla),
) -> AiRuleResponse:
    name = payload.name.strip()
    rule_sql = payload.rule_sql.strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="name_required")
    if not rule_sql:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="rule_sql_required")

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


## 4. Frontend Changes

### 4.1 Admin AI Grid Page

File: `frontend/src/pages/AdminAiGridPage.tsx`

```tsx path=C:\Users\filip\.gemini\antigravity\playground\silent-spirit\frontend\src\pages\AdminAiGridPage.tsx start=1
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
          (сообщения, кейсы, покупки) и отрисую результат в гриде ниже.
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

This page:
- Is **admin-only** (wired through `ProtectedRoute` and admin dashboard).
- Posts prompts to `/api/admin/ai/query` and directly pipes the JSON response into `AppDataGrid`.
- Shows the raw SQL below the prompt for transparency and debugging.


### 4.2 Admin AI Rules Page

File: `frontend/src/pages/AdminAiRulesPage.tsx`

```tsx path=C:\Users\filip\.gemini\antigravity\playground\silent-spirit\frontend\src\pages\AdminAiRulesPage.tsx start=17
export default function AdminAiRulesPage() {
  const [rules, setRules] = useState<AiRuleDto[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [ruleSql, setRuleSql] = useState('');

  const loadRules = async () => {
    try {
      setLoading(true);
      setError(null);
      const resp = await api.get<AiRuleDto[]>('/api/admin/ai/rules');
      setRules(resp.data || []);
    } catch (e: any) {
      const msg = e?.response?.data?.detail || e.message || 'Не удалось загрузить правила';
      setError(String(msg));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadRules();
  }, []);

  const handleCreate = async () => {
    const trimmedName = name.trim();
    const trimmedSql = ruleSql.trim();
    if (!trimmedName || !trimmedSql) {
      setError('Нужно указать и имя правила, и SQL-условие.');
      return;
    }
    try {
      setLoading(true);
      setError(null);
      await api.post<AiRuleDto>('/api/admin/ai/rules', {
        name: trimmedName,
        rule_sql: trimmedSql,
        description: description.trim() || null,
      });
      setName('');
      setDescription('');
      setRuleSql('');
      await loadRules();
    } catch (e: any) {
      const msg = e?.response?.data?.detail || e.message || 'Не удалось сохранить правило';
      setError(String(msg));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      <FixedHeader />
      <div className="pt-16 px-4 py-6 max-w-6xl w-full mx-auto flex-1 flex flex-col gap-4">
        <h1 className="text-2xl font-bold">Admin AI Rules</h1>
        <p className="text-sm text-gray-600 max-w-3xl">
          Здесь можно хранить переиспользуемые SQL-правила (условия), которые описывают, что такое
          "хорошая покупка" и быстрая окупаемость.
        </p>

        {/* Form for new rule */}
        {/* ... see full file for layout ... */}
      </div>
    </div>
  );
}
```

(Полный файл содержит карточки с формой и списком правил; см. исходник для всех деталей верстки.)

The page implements basic CRUD for rules (create + list). Deletion/editing can be added later.


### 4.3 Routing and Admin Dashboard Links

`frontend/src/App.tsx`:

```tsx path=C:\Users\filip\.gemini\antigravity\playground\silent-spirit\frontend\src\App.tsx start=39
import SniperPage from './pages/SniperPage';
import AdminAiGridPage from './pages/AdminAiGridPage';
import AdminAiRulesPage from './pages/AdminAiRulesPage';
```

Routes:

```tsx path=C:\Users\filip\.gemini\antigravity\playground\silent-spirit\frontend\src\App.tsx start=129
<Route path="/admin/ui-tweak" element={<ProtectedRoute><AdminUITweakPage /></ProtectedRoute>} />
<Route path="/admin/security" element={<ProtectedRoute><SecurityCenterPage /></ProtectedRoute>} />
<Route path="/admin/ai-grid" element={<ProtectedRoute><AdminAiGridPage /></ProtectedRoute>} />
<Route path="/admin/ai-rules" element={<ProtectedRoute><AdminAiRulesPage /></ProtectedRoute>} />
```

Admin dashboard tiles (`frontend/src/pages/AdminPage.tsx`):

```tsx path=C:\Users\filip\.gemini\antigravity\playground\silent-spirit\frontend\src\pages\AdminPage.tsx start=55
<Card className="p-4 hover:shadow-lg cursor-pointer" onClick={() => navigate('/admin/ui-tweak')}>
  <h2 className="text-lg font-semibold">UI Tweak</h2>
  <p className="text-sm text-gray-600 mt-1">Adjust navigation, text size, and grid density</p>
</Card>

<Card className="p-4 hover:shadow-lg cursor-pointer" onClick={() => navigate('/admin/ai-grid')}>
  <h2 className="text-lg font-semibold">AI Grid Playground</h2>
  <p className="text-sm text-gray-600 mt-1">Test AI-запросы и живой грид в админке</p>
</Card>

<Card className="p-4 hover:shadow-lg cursor-pointer" onClick={() => navigate('/admin/ai-rules')}>
  <h2 className="text-lg font-semibold">AI Rules</h2>
  <p className="text-sm text-gray-600 mt-1">Определить правила "хорошей покупки" и окупаемости</p>
</Card>
```


## 5. Example Flows

### 5.1 Complaints About Bad Packaging

1. Admin → `/admin/ai-grid`.
2. Prompt:
   > Покажи письма, где жалуются, что деталь разбилась из-за плохой упаковки.
3. Backend asks OpenAI for SQL – expected pattern (simplified):
   - `FROM tbl_ebay_messages` or `FROM ebay_messages`.
   - `WHERE body ILIKE '%poor packaging%' OR body ILIKE '%bad packaging%' OR body ILIKE '%broken%' OR body ILIKE '%damaged%' ...`.
4. SQL validated against whitelist, executed in Postgres.
5. Grid shows matching messages with dates, senders, subjects, etc.

### 5.2 “Good Computers” by Profit and Payback

1. Admin defines rule in `/admin/ai-rules`:
   - Name: `good_computer_100pct_60days`.
   - Description: "Компьютер считается хорошим, если profit_percentage ≥ 100 и days_to_recover ≤ 60.".
   - SQL: `profit_percentage >= 100 AND days_to_recover <= 60`.
2. Rule persists in `ai_rules` and is visible in the list.
3. Later stages will:
   - Inject this rule into analytics queries (e.g. `WHERE {rule_sql}` on profitability views).
   - Use it in eBay monitoring / sniper workers to filter **what to buy** and **what to bid on**.


## 6. Safety & Constraints

- All AI-generated SQL is **read-only**:
  - Only `SELECT`.
  - Single statement (no `;`).
  - Hard blocklist for DML/DDL keywords.
- AI queries are limited to an explicit set of **whitelisted tables** related to messages, cases, buying, and fees.
- Each admin AI query is **logged** with user, prompt, SQL, and row count.
- If OpenAI config (`OPENAI_API_KEY`) is missing or the provider fails, admin endpoints return structured errors without affecting core app functionality.


## 7. Next Steps (Future Stages)

Not implemented yet, but this brief sets the ground for:

1. **Rule Preview / Generation**
   - Endpoint like `POST /api/admin/ai/rules/preview { prompt } → { rule_sql }` to convert voice/text definitions of “good purchases” into SQL fragments.
   - UI button “Generate Rule SQL” on `/admin/ai-rules`.

2. **Deeper Analytics Grids**
   - Connecting rules and AI SQL to existing grids (buying, transactions, inventory) for views like:
     - “Computers that paid back fastest in last N days”.
     - “Models with worst packaging complaint rate per supplier." 

3. **Integration with Workers (Sniper, Monitoring)**
   - Use `ai_rules` as a configuration layer for:
     - Which models to monitor on eBay.
     - Max buy price thresholds.
     - Risk scoring.

4. **Voice Interface Layer**
   - Later, wrap these admin endpoints with a voice/assistant interface that:
     - Interprets spoken requests.
     - Chooses between **analytics queries** and **actions** (snipes/offers).

---

This document describes only the **First Stage AI Integration** (admin analytics + rules). The architecture is deliberately conservative on safety and scope to make it reviewable and auditable before we wire it into real-time buying and sniper flows.