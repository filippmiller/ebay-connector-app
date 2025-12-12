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
