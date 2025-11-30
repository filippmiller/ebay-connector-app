from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy.exc import ProgrammingError

from app.models_sqlalchemy import get_db
from app.models_sqlalchemy.models import UiTweakSettings
from app.services.auth import get_current_active_user, admin_required
from app.models.user import User
from app.utils.logger import logger

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


def _get_or_create_settings_row(db: Session) -> UiTweakSettings | None:
    """Return the singleton UiTweakSettings row or create it if possible.

    If the underlying table does not exist yet (e.g. migration not applied in
    this environment), return ``None`` and let callers fall back to
    _DEFAULT_SETTINGS instead of raising 500.
    """
    try:
        row = db.query(UiTweakSettings).order_by(UiTweakSettings.id.asc()).first()
    except ProgrammingError as exc:  # psycopg2.ProgrammingError under the hood
        msg = str(exc)
        if "ui_tweak_settings" in msg and "UndefinedTable" in msg:
            logger.error(
                "ui_tweak_settings table is missing; /api/ui-tweak will serve defaults only. "
                "Apply Alembic migration ui_tweak_settings_20251121 to enable persistence.",
            )
            return None
        raise

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

    If the backing ``ui_tweak_settings`` table is missing (e.g. migration not
    yet applied in a given environment), this endpoint falls back to
    _DEFAULT_SETTINGS and still returns HTTP 200 instead of raising 500.
    """

    row = _get_or_create_settings_row(db)
    if row is None:
        # Graceful fallback: serve defaults only.
        return UiTweakSettingsPayload(**_DEFAULT_SETTINGS)

    stored = row.settings or {}
    # Merge with backend defaults so missing keys do not break the frontend.
    merged: Dict[str, Any] = {**_DEFAULT_SETTINGS, **stored}
    return UiTweakSettingsPayload(**merged)


@router.get("/admin/ui-tweak", response_model=UiTweakSettingsPayload)
async def get_admin_ui_tweak_settings(
    current_user: User = Depends(admin_required),  # noqa: ARG001
    db: Session = Depends(get_db),
) -> UiTweakSettingsPayload:
    """Admin view of UITweak settings (same payload as public read).

    When the underlying table is missing, this returns defaults only so that
    the Admin UI can still render and display a clear migration hint.
    """

    row = _get_or_create_settings_row(db)
    if row is None:
        return UiTweakSettingsPayload(**_DEFAULT_SETTINGS)

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

    If the backing table is missing, this endpoint returns a 503-style error
    with a clear message instead of creating the table implicitly. The actual
    table must be created via Alembic migrations.
    """

    row = _get_or_create_settings_row(db)
    if row is None:
        # Avoid silently creating the table from the app; require an explicit
        # Alembic migration instead so production DBs stay consistent.
        from fastapi import HTTPException

        raise HTTPException(
            status_code=503,
            detail=(
                "ui_tweak_settings table is missing; apply Alembic migration "
                "ui_tweak_settings_20251121 in the production database before "
                "editing UI tweak settings."
            ),
        )

    row.settings = payload.dict()
    db.add(row)
    db.commit()
    db.refresh(row)
    return payload
