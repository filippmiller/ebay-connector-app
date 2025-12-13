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
