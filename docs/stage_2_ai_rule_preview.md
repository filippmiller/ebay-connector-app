# Stage 2 – AI Rule Preview / Rule SQL Generation (25 November 2025)

## 1. Goal

Extend the **Stage 1** AI integration with:

- An admin-only **AI Rule Preview / Generation** pipeline that converts natural-language descriptions of business rules into safe SQL boolean expressions (`rule_sql`).
- Backend endpoints for:
  - Previewing a rule (`/api/admin/ai/rules/preview` – no DB write).
  - Generating and saving a rule (`/api/admin/ai/rules/generate-and-save`).
- Frontend enhancements to `/admin/ai-rules` so that the admin can type a description, click **Generate SQL from Description**, inspect the generated condition, and then save it as an `ai_rules` row.

This is still **admin-only** and read-only with respect to data; it deals only with SQL conditions that will *later* be used by analytics and workers.

---

## 2. Backend Changes

### 2.1 AI Rules Engine Service

**File:** `backend/app/services/ai_rules_engine.py`

Purpose: encapsulate the call to OpenAI and validate that the returned `rule_sql` is a **safe boolean expression**, not a full SQL statement.

```python path=C:\Users\filip\.gemini\antigravity\playground\silent-spirit\backend\app\services\ai_rules_engine.py start=1
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

**Notes / Safety:**

- The validator enforces:
  - No `;`, `--`, `/*`, `*/`.
  - No `SELECT`, `INSERT`, `UPDATE`, `DELETE`, `MERGE`, `ALTER`, `DROP`, `TRUNCATE`, `CREATE`, `FROM`, `JOIN`, `UNION`, `WITH`.
  - Maximum length 500 characters.
- The model is asked explicitly to output only JSON with a single `rule_sql` field.
- Any violations raise `HTTPException` with a clear error message for the admin.


### 2.2 Admin AI Rules Extension Router

**File:** `backend/app/routers/admin_ai_rules_ext.py`

Purpose: expose dedicated endpoints for **previewing** and **generate+save**-ing rules, on top of the existing `admin_ai` router from Stage 1.

```python path=C:\Users\filip\.gemini\antigravity\playground\silent-spirit\backend\app\routers\admin_ai_rules_ext.py start=16
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

**Admin-only:** both endpoints depend on `admin_required`.

**Routing integration:** in `backend/app/main.py`:

```python path=C:\Users\filip\.gemini\antigravity\playground\silent-spirit\backend\app\main.py start=7
from app.routers import (
    auth,
    ebay,
    ...,
    admin_ai,
    admin_ai_rules_ext,
)
...
app.include_router(admin_ai.router)
app.include_router(admin_ai_rules_ext.router)
```

No new DB tables were required; we reuse `AiRule` from Stage 1.

---

## 3. Frontend Changes

### 3.1 Admin AI Rules Page – Generate SQL Button

**File:** `frontend/src/pages/AdminAiRulesPage.tsx`

The page already supported:
- Listing rules via `GET /api/admin/ai/rules`.
- Creating rules via `POST /api/admin/ai/rules` with manually entered `rule_sql`.

Stage 2 adds:
- Local loading flag for preview: `previewLoading`.
- A **Generate SQL from Description** button below the natural-language description textarea.
- Logic to call `/api/admin/ai/rules/preview` and populate the SQL textarea.

Key snippets:

```tsx path=C:\Users\filip\.gemini\antigravity\playground\silent-spirit\frontend\src\pages\AdminAiRulesPage.tsx start=17
export default function AdminAiRulesPage() {
  const [rules, setRules] = useState<AiRuleDto[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [ruleSql, setRuleSql] = useState('');
  const [previewLoading, setPreviewLoading] = useState(false);
```

Generate handler:

```tsx path=C:\Users\filip\.gemini\antigravity\playground\silent-spirit\frontend\src\pages\AdminAiRulesPage.tsx start=71
  const handleGenerateSql = async () => {
    const trimmedDescription = description.trim();
    if (!trimmedDescription) {
      setError('Сначала опишите правило на естественном языке.');
      return;
    }
    try {
      setPreviewLoading(true);
      setError(null);
      const resp = await api.post<{ rule_sql: string }>('/api/admin/ai/rules/preview', {
        description: trimmedDescription,
      });
      setRuleSql(resp.data.rule_sql || '');
    } catch (e: any) {
      const msg = e?.response?.data?.detail || e.message || 'Не удалось сгенерировать SQL-условие';
      setError(String(msg));
    } finally {
      setPreviewLoading(false);
    }
  };
```

UI integration:

```tsx path=C:\Users\filip\.gemini\antigravity\playground\silent-spirit\frontend\src\pages\AdminAiRulesPage.tsx start=92
<label className="block text-xs font-medium text-gray-600 mt-3">Описание (натуральный язык)</label>
<Textarea
  rows={3}
  value={description}
  onChange={(e) => setDescription(e.target.value)}
  placeholder="Например: Компьютер считается хорошим, если profit_percentage >= 100 и days_to_recover <= 60."
/>
<div className="flex justify-end mt-1">
  <Button variant="outline" size="sm" onClick={handleGenerateSql} disabled={previewLoading}>
    {previewLoading ? 'Генерация…' : 'Generate SQL from Description'}
  </Button>
</div>
```

The **Save rule** behavior (`handleCreate`) is unchanged and still uses `POST /api/admin/ai/rules` with the `ruleSql` textarea contents, whether typed by hand or generated.

### 3.2 Build Check

After changes, the frontend build was run:

```bash
cd frontend
npm run build
```

- TypeScript compilation and Vite build both succeeded.
- No additional runtime changes were needed.

---

## 4. Example Usage

### 4.1 Successful Rule Preview

**Scenario:** Admin wants a rule for “good computer” profitability.

1. Go to `/admin/ai-rules`.
2. In the **Описание (натуральный язык)** field, type (for example):

   > Компьютер считается хорошим, если доходность не ниже 100% и окупаемость не больше 60 дней.

3. Click **Generate SQL from Description**.
4. Backend calls `generate_rule_sql`, OpenAI returns JSON like:

   ```json
   { "rule_sql": "(profit_percentage >= 100 AND days_to_recover <= 60)" }
   ```

5. The SQL textarea is populated with:

   ```sql
   (profit_percentage >= 100 AND days_to_recover <= 60)
   ```

6. Admin presses **Сохранить правило**, which triggers the existing `POST /api/admin/ai/rules` endpoint (Stage 1) and stores an `AiRule` row.

### 4.2 Validation Error – Forbidden Keyword

**Scenario:** Model tries to return an unsafe fragment:

```sql
SELECT * FROM purchases WHERE profit_percentage > 100
```

- `_validate_rule_sql` sees `SELECT` and `FROM` in the uppercase string.
- An `AiRuleGenerationError` is raised, converted into:

```json
{
  "detail": "rule_sql contains forbidden keyword: SELECT"
}
```

- Frontend displays the error under the form (`setError(...)`), and the SQL textarea remains unchanged.

### 4.3 Validation Error – Comment or `;`

If AI returns something like:

```sql
(profit_percentage >= 100); -- good computer
```

- The validator finds `;` and `--` and rejects it with a message like:

> Forbidden token in rule_sql: ';'

Admin sees this message, and no rule is saved.

---

## 5. End-to-End Flow Summary

1. **Admin describes rule** in Russian or English in `/admin/ai-rules`.
2. **Preview step (no DB write):**
   - `POST /api/admin/ai/rules/preview { description }`.
   - `ai_rules_engine.generate_rule_sql` → OpenAI Chat Completions.
   - JSON `{ rule_sql }` returned or a clear validation error.
   - Frontend populates SQL textarea.
3. **Save step:**
   - Admin hits **Сохранить правило**.
   - `POST /api/admin/ai/rules` (Stage 1 endpoint) persists `AiRule` with `name`, `rule_sql`, `description`.
   - Rule appears in the list below with `WHERE {rule_sql}`.
4. **(Optional future)** `POST /api/admin/ai/rules/generate-and-save` can be used by automated flows or future UI variants to combine preview+save in a single call.

---

## 6. Safety Guarantees (Stage 2)

- `ai_rules_engine` enforces that **rule_sql is only a boolean condition**, never a full query:
  - No `SELECT`, `FROM`, `JOIN`, or other query/DDL keywords.
  - No semicolons or SQL comments.
- Both new endpoints are **admin-only**, reusing `admin_required`.
- Existing Stage 1 server-side validation in `create_ai_rule` still applies (`UPDATE/DELETE/INSERT/ALTER/DROP/TRUNCATE/CREATE` are blocked there as well).
- No new tables or migrations; we reuse `ai_rules` and existing safety layers.

---

## 7. How This Prepares Next Stages

With Stage 2 in place:

- Business rules like “good computer”, “fast payback”, “risky model”, etc., can be defined once in `ai_rules` using **AI-assisted SQL generation**.
- Future components can **reuse `rule_sql`** across:
  - Analytics queries (WHERE clauses in reports and grids).
  - eBay Monitor Workers (filter which auctions or BIN items qualify).
  - Sniper workers (which items should be auto-sniped, and at what max price).
- The pattern (natural language → safe SQL fragment) can be reused for other domains: complaints, packaging quality, refund risk, etc.
