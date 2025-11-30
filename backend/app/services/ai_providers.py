from __future__ import annotations

from typing import Optional, Tuple
import os

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
from app.models_sqlalchemy.models import AiProvider


def get_openai_api_config(db: Session | None = None) -> Tuple[str, str, str]:
    """Resolve OpenAI API configuration (api_key, model, base_url).

    Precedence for api_key:
    1. ai_providers row for provider_code="openai" (encrypted at rest).
    2. settings.OPENAI_API_KEY / OPENAI_API_KEY env var.

    The model name is taken from AiProvider.model_default when present,
    otherwise falls back to settings.OPENAI_MODEL.
    """

    api_key: Optional[str] = None
    model: str = settings.OPENAI_MODEL
    base_url: str = settings.OPENAI_API_BASE_URL.rstrip("/")

    if db is not None:
        provider = (
            db.query(AiProvider)
            .filter(AiProvider.provider_code == "openai")
            .one_or_none()
        )
        if provider and provider.api_key:
            api_key = provider.api_key
            if provider.model_default:
                model = provider.model_default

    if not api_key:
        api_key = settings.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY")

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OPENAI_API_KEY is not configured on the backend; contact an administrator.",
        )

    return api_key, model, base_url