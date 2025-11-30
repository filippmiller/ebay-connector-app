from __future__ import annotations

from typing import Any, Dict, List, Optional

import hashlib
import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models_sqlalchemy import get_db
from app.models_sqlalchemy.models import UserGridLayout
from app.routers.grid_layouts import (
    _allowed_columns_for_grid,
    _columns_meta_for_grid,
    GRID_DEFAULTS,
    ColumnMeta,
    GridSort,
)
from app.services.auth import get_current_active_user
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/grid", tags=["grid_preferences"])


class GridTheme(BaseModel):
    density: str = Field("normal", pattern="^(compact|normal|comfortable)$")
    fontSize: str = Field("medium", pattern="^(small|medium|large)$")
    headerStyle: str = Field("default", pattern="^(default|bold|accent)$")
    colorScheme: str = Field("default", pattern="^(default|blue|dark|highContrast)$")
    buttonLayout: str = Field("right", pattern="^(left|right|split)$")

    class Config:
        extra = "allow"  # allow forward-compatible flags (e.g. stripedRows, showRowBorders)


class GridColumnsConfig(BaseModel):
    visible: List[str]
    order: List[str]
    widths: Dict[str, int] = {}
    sort: Optional[GridSort] = None


class GridPreferencesResponse(BaseModel):
    grid_key: str
    available_columns: List[ColumnMeta]
    columns: GridColumnsConfig
    theme: GridTheme


class GridPreferencesUpdate(BaseModel):
    grid_key: str
    columns: GridColumnsConfig
    theme: GridTheme


_DEFAULT_THEME: Dict[str, Any] = {
    "density": "normal",
    "fontSize": "medium",
    "headerStyle": "default",
    "colorScheme": "default",
    "buttonLayout": "right",
}


def _build_columns_from_layout(grid_key: str, layout: Optional[UserGridLayout]) -> GridColumnsConfig:
    allowed_cols = _allowed_columns_for_grid(grid_key)
    if not allowed_cols:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown grid_key")

    defaults = GRID_DEFAULTS.get(grid_key, {})
    default_visible = [c for c in defaults.get("visible_columns", allowed_cols) if c in allowed_cols]
    default_sort = defaults.get("sort")

    if layout is None:
        return GridColumnsConfig(
            visible=default_visible or allowed_cols,
            order=default_visible or allowed_cols,
            widths={},
            sort=default_sort,
        )

    visible = layout.visible_columns or default_visible or allowed_cols
    # Preserve only allowed columns and canonicalise order
    visible_clean = [c for c in visible if c in allowed_cols]
    if not visible_clean:
        visible_clean = default_visible or allowed_cols

    widths_raw = layout.column_widths or {}
    widths_clean: Dict[str, int] = {}
    for k, v in widths_raw.items():
        if k in allowed_cols:
            try:
                widths_clean[k] = int(v)
            except (TypeError, ValueError):
                continue

    sort_obj = layout.sort or default_sort

    return GridColumnsConfig(
        visible=visible_clean,
        order=visible_clean,
        widths=widths_clean,
        sort=sort_obj,
    )


def _build_theme_from_layout(layout: Optional[UserGridLayout]) -> GridTheme:
    base = dict(_DEFAULT_THEME)
    if layout and layout.theme:
        try:
            base.update(layout.theme or {})
        except Exception:
            # If legacy data is malformed, fall back to defaults
            logger.warning("Invalid theme payload on user_grid_layouts id=%s", layout.id)
    return GridTheme(**base)


@router.get("/preferences", response_model=GridPreferencesResponse)
async def get_grid_preferences(
    grid_key: str = Query(..., description="Unique grid key (e.g. transactions, orders, offers)"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> GridPreferencesResponse:
    """Return effective per-user grid preferences for the given grid.

    This wraps the existing user_grid_layouts table and GRID_DEFAULTS so that callers
    always see a complete, server-computed configuration even if the user has never
    customised the grid before.
    """

    allowed_cols = _allowed_columns_for_grid(grid_key)
    if not allowed_cols:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown grid_key")

    layout: Optional[UserGridLayout] = (
        db.query(UserGridLayout)
        .filter(UserGridLayout.user_id == current_user.id, UserGridLayout.grid_key == grid_key)
        .first()
    )

    available_columns = _columns_meta_for_grid(grid_key)
    columns_cfg = _build_columns_from_layout(grid_key, layout)
    theme_cfg = _build_theme_from_layout(layout)

    return GridPreferencesResponse(
        grid_key=grid_key,
        available_columns=available_columns,
        columns=columns_cfg,
        theme=theme_cfg,
    )


@router.delete("/preferences", status_code=status.HTTP_204_NO_CONTENT)
async def delete_grid_preferences(
    grid_key: str = Query(..., description="Unique grid key (e.g. transactions, orders, offers)"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> None:
    """Delete a user's preferences for a grid, reverting to GRID_DEFAULTS on next fetch."""

    allowed_cols = _allowed_columns_for_grid(grid_key)
    if not allowed_cols:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown grid_key")

    layout: Optional[UserGridLayout] = (
        db.query(UserGridLayout)
        .filter(UserGridLayout.user_id == current_user.id, UserGridLayout.grid_key == grid_key)
        .first()
    )
    if not layout:
        return

    db.delete(layout)
    db.commit()
    logger.info("grid_preferences.delete user_id=%s grid_key=%s", current_user.id, grid_key)


@router.post("/preferences", response_model=GridPreferencesResponse)
async def upsert_grid_preferences(
    payload: GridPreferencesUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> GridPreferencesResponse:
    """Create or update per-user grid preferences for a grid.

    The combination (user_id, grid_key) is unique so this behaves as an upsert.
    """
    logger.info(
        "upsert_grid_preferences: user_id=%s grid_key=%s payload_len=%s",
        current_user.id,
        payload.grid_key,
        len(payload.json()),
    )

    grid_key = payload.grid_key
    allowed_cols = _allowed_columns_for_grid(grid_key)
    if not allowed_cols:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown grid_key")

    # Validate requested columns against allowed set
    invalid = [c for c in payload.columns.order if c not in allowed_cols]
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid columns for grid {grid_key}: {', '.join(invalid)}",
        )

    # Filter widths
    cleaned_widths: Dict[str, int] = {}
    for k, v in payload.columns.widths.items():
        if k not in allowed_cols:
            continue
        try:
            cleaned_widths[k] = int(v)
        except (TypeError, ValueError):
            continue

    # Temporary targeted debug for finances_fees width persistence
    if grid_key == "finances_fees":
        try:
            logger.info(
                "grid_preferences.finances_fees_widths user_id=%s raw_keys=%s cleaned_keys=%s",
                current_user.id,
                sorted(list(payload.columns.widths.keys())),
                sorted(list(cleaned_widths.keys())),
            )
        except Exception:
            # Best-effort only; never fail the request because of logging
            logger.debug("grid_preferences.finances_fees_widths: logging failed")

    # Validate sort column
    sort_dict: Optional[Dict[str, Any]] = None
    if payload.columns.sort:
        if payload.columns.sort.column not in allowed_cols:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid sort column: {payload.columns.sort.column}",
            )
        sort_dict = payload.columns.sort.dict()

    layout: Optional[UserGridLayout] = (
        db.query(UserGridLayout)
        .filter(UserGridLayout.user_id == current_user.id, UserGridLayout.grid_key == grid_key)
        .first()
    )

    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)

    theme_payload = payload.theme.dict()

    # Compute effective visible columns:
    # 1. Start with 'order', but filter to only include those in 'visible'.
    # 2. Append any in 'visible' that are not in 'order'.
    visible_set = set(payload.columns.visible)
    ordered_visible = [c for c in payload.columns.order if c in visible_set]

    existing_in_order = set(ordered_visible)
    for c in payload.columns.visible:
        if c not in existing_in_order:
            ordered_visible.append(c)

    # Validate against allowed_cols just in case
    final_visible = [c for c in ordered_visible if c in allowed_cols]

    if layout:
        layout.visible_columns = final_visible
        layout.column_widths = cleaned_widths
        layout.sort = sort_dict
        layout.theme = theme_payload
        layout.updated_at = now
    else:
        layout = UserGridLayout(
            id=str(uuid.uuid4()),
            user_id=current_user.id,
            grid_key=grid_key,
            visible_columns=final_visible,
            column_widths=cleaned_widths,
            sort=sort_dict,
            theme=theme_payload,
            created_at=now,
            updated_at=now,
        )
        db.add(layout)

    db.commit()
    db.refresh(layout)

    # Log a concise message with a short hash of the payload (without sensitive data)
    try:
        to_hash = {
            "grid_key": grid_key,
            "user_id": current_user.id,
            "columns": payload.columns.dict(),
            "theme": theme_payload,
        }
        digest = hashlib.sha256(json.dumps(to_hash, sort_keys=True).encode("utf-8")).hexdigest()[:8]
        logger.info("grid_preferences.save user_id=%s grid_key=%s hash=%s", current_user.id, grid_key, digest)
    except Exception:
        logger.info("grid_preferences.save user_id=%s grid_key=%s", current_user.id, grid_key)

    available_columns = _columns_meta_for_grid(grid_key)
    columns_cfg = _build_columns_from_layout(grid_key, layout)
    theme_cfg = _build_theme_from_layout(layout)

    return GridPreferencesResponse(
        grid_key=grid_key,
        available_columns=available_columns,
        columns=columns_cfg,
        theme=theme_cfg,
    )
