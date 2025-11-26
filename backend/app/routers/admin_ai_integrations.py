from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models_sqlalchemy import get_db as get_db_sqla
from app.models_sqlalchemy.models import AiProvider
from app.services.auth import admin_required
from app.models.user import User


router = APIRouter(prefix="/api/ai/integrations", tags=["admin_ai_integrations"])


class OpenAiSettingsUpdate(BaseModel):
    """Payload for updating OpenAI integration settings.

    - api_key: optional new API key. If null/empty, the existing key is preserved.
    - model_default: logical default model name (e.g. "gpt-4.1-mini").
    """

    api_key: Optional[str] = None
    model_default: str


DEFAULT_MODEL = "gpt-4.1-mini"


@router.get("/ai-provider/openai")
async def get_openai_settings(
    db: Session = Depends(get_db_sqla),
    current_user: User = Depends(admin_required),  # noqa: ARG001
) -> dict:
    """Return current OpenAI settings without exposing the raw API key.

    Example response:
    {
        "has_api_key": true,
        "model_default": "gpt-4.1-mini"
    }
    """

    provider = (
        db.query(AiProvider)
        .filter(AiProvider.provider_code == "openai")
        .one_or_none()
    )

    if not provider:
        # No row yet – assume no key and a sensible default model.
        return {
            "has_api_key": False,
            "model_default": DEFAULT_MODEL,
        }

    has_api_key = bool(provider.api_key)
    model_default = provider.model_default or DEFAULT_MODEL

    return {
        "has_api_key": has_api_key,
        "model_default": model_default,
    }


@router.post("/ai-provider/openai")
async def upsert_openai_settings(
    payload: OpenAiSettingsUpdate,
    db: Session = Depends(get_db_sqla),
    current_user: User = Depends(admin_required),  # noqa: ARG001
) -> dict:
    """Create or update the OpenAI provider configuration.

    - If ``api_key`` is provided and non-empty, it is encrypted and stored.
    - ``model_default`` is always stored (trimmed).
    """

    provider = (
        db.query(AiProvider)
        .filter(AiProvider.provider_code == "openai")
        .one_or_none()
    )

    if not provider:
        provider = AiProvider(
            provider_code="openai",
            name="OpenAI",
            owner_user_id=str(current_user.id),
        )
        db.add(provider)

    # Update API key only when a non-empty value is provided, so an
    # accidental empty submit does not wipe the key.
    if payload.api_key is not None and payload.api_key.strip() != "":
        provider.api_key = payload.api_key

    provider.model_default = (payload.model_default or DEFAULT_MODEL).strip()

    db.commit()
    db.refresh(provider)

    return {"ok": True}