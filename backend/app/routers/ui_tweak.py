from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models_sqlalchemy import get_db
from app.models_sqlalchemy.models import UiTweakSettings
from app.services.auth import get_current_active_user, admin_required
from app.models.user import User

router = APIRouter(prefix="/api", tags=["ui_tweak"])


class UiTweakSettingsPayload(BaseModel):
    """Pydantic model mirroring the frontend UITweakSettings shape.

    We keep this intentionally loose and allow extra fields so the frontend can
    evolve without requiring a strict backend migration for every tweak.
    """

    fontScale: float = Field(1.0, ge=0.5, le=3.0)
    navScale: float = Field(1.0, ge=0.5, le=3.0)
    gridDensity: str = Field("normal", pattern="^(compact|normal|comfortable)$")

    navActiveBg: str = "#2563eb"
    navActiveText: str = "#ffffff"
    navInactiveBg: str = "transparent"
    navInactiveText: str = "#374151"

    typography: Dict[str, Any] = Field(default_factory=dict)
    colors: Dict[str, Any] = Field(default_factory=dict)
    controls: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        extra = "allow"


_DEFAULT_SETTINGS = UiTweakSettingsPayload().dict()


def _get_or_create_settings_row(db: Session) -> UiTweakSettings:
    row = db.query(UiTweakSettings).order_by(UiTweakSettings.id.asc()).first()
    if row is None:
        row = UiTweakSettings(settings=_DEFAULT_SETTINGS)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


@router.get("/ui-tweak", response_model=UiTweakSettingsPayload)
async def get_ui_tweak_settings(
    current_user: User = Depends(get_current_active_user),  # noqa: ARG001
    db: Session = Depends(get_db),
) -> UiTweakSettingsPayload:
    """Return effective global UITweak settings for any authenticated user.

    This endpoint is read-only and is used by the UITweakProvider on app start
    so that all users (not only admins) see the same global UI configuration.
    """

    row = _get_or_create_settings_row(db)
    stored = row.settings or {}
    # Merge with backend defaults so missing keys do not break the frontend.
    merged: Dict[str, Any] = {**_DEFAULT_SETTINGS, **stored}
    return UiTweakSettingsPayload(**merged)


@router.get("/admin/ui-tweak", response_model=UiTweakSettingsPayload)
async def get_admin_ui_tweak_settings(
    current_user: User = Depends(admin_required),  # noqa: ARG001
    db: Session = Depends(get_db),
) -> UiTweakSettingsPayload:
    """Admin view of UITweak settings (same payload as public read)."""

    row = _get_or_create_settings_row(db)
    stored = row.settings or {}
    merged: Dict[str, Any] = {**_DEFAULT_SETTINGS, **stored}
    return UiTweakSettingsPayload(**merged)


@router.put("/admin/ui-tweak", response_model=UiTweakSettingsPayload)
async def update_admin_ui_tweak_settings(
    payload: UiTweakSettingsPayload,
    current_user: User = Depends(admin_required),  # noqa: ARG001
    db: Session = Depends(get_db),
) -> UiTweakSettingsPayload:
    """Update global UITweak settings. Admin-only.

    The payload is stored as a single JSON document in ui_tweak_settings.settings
    so that the frontend can add new fields without schema changes.
    """

    row = _get_or_create_settings_row(db)
    row.settings = payload.dict()
    db.add(row)
    db.commit()
    db.refresh(row)
    return payload
