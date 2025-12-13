from __future__ import annotations

from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends, UploadFile, File, Form, Query, Body
from sqlalchemy.orm import Session

from app.models_sqlalchemy import get_db as get_db_sqla
from app.models.user import User
from app.services.admin_auth import require_admin_user

# Reuse implementations from the /api/accounting2 router.
from app.routers.accounting2 import (
    upload_bank_statement_v2 as _upload_bank_statement_v2,
    upload_bank_statement_xlsx_manual as _upload_bank_statement_xlsx_manual,
    get_bank_statement_preview_summary as _get_bank_statement_preview_summary,
    get_bank_statement_preview_rows as _get_bank_statement_preview_rows,
    approve_bank_statement as _approve_bank_statement,
    reject_bank_statement as _reject_bank_statement,
    get_bank_statement_pdf_url as _get_bank_statement_pdf_url,
    create_manual_bank_statement_from_text as _create_manual_bank_statement_from_text,
    ManualPastedStatement,
)

router = APIRouter(prefix="/accounting2", tags=["accounting2_public"])


@router.post("/bank-statements/upload")
async def upload_bank_statement_v2_public(
    file: UploadFile = File(...),
    bank_code: str = Form("TD"),
    db: Session = Depends(get_db_sqla),
    current_user: User = Depends(require_admin_user),
) -> Dict[str, Any]:
    return await _upload_bank_statement_v2(file=file, bank_code=bank_code, db=db, current_user=current_user)


@router.post("/bank-statements/upload-xlsx")
async def upload_bank_statement_xlsx_public(
    file: UploadFile = File(...),
    bank_name: str = Form("TD Bank"),
    bank_code: str = Form("TD"),
    currency: str = Form("USD"),
    db: Session = Depends(get_db_sqla),
    current_user: User = Depends(require_admin_user),
) -> Dict[str, Any]:
    return await _upload_bank_statement_xlsx_manual(
        file=file,
        bank_name=bank_name,
        bank_code=bank_code,
        currency=currency,
        db=db,
        current_user=current_user,
    )


@router.get("/bank-statements/{statement_id}")
async def get_bank_statement_preview_summary_public(
    statement_id: int,
    db: Session = Depends(get_db_sqla),
    current_user: User = Depends(require_admin_user),
) -> Dict[str, Any]:
    return await _get_bank_statement_preview_summary(statement_id=statement_id, db=db, current_user=current_user)


@router.get("/bank-statements/{statement_id}/rows")
async def get_bank_statement_preview_rows_public(
    statement_id: int,
    db: Session = Depends(get_db_sqla),
    current_user: User = Depends(require_admin_user),
) -> Dict[str, Any]:
    # Keep signature compatible with existing endpoint; ignore limit for now.
    return await _get_bank_statement_preview_rows(statement_id=statement_id, db=db, current_user=current_user)


@router.post("/bank-statements/{statement_id}/approve")
async def approve_bank_statement_public(
    statement_id: int,
    db: Session = Depends(get_db_sqla),
    current_user: User = Depends(require_admin_user),
) -> Dict[str, Any]:
    return await _approve_bank_statement(statement_id=statement_id, db=db, current_user=current_user)


@router.post("/bank-statements/{statement_id}/reject")
async def reject_bank_statement_public(
    statement_id: int,
    db: Session = Depends(get_db_sqla),
    current_user: User = Depends(require_admin_user),
) -> Dict[str, Any]:
    return await _reject_bank_statement(statement_id=statement_id, db=db, current_user=current_user)


@router.get("/bank-statements/{statement_id}/pdf-url")
async def get_bank_statement_pdf_url_public(
    statement_id: int,
    db: Session = Depends(get_db_sqla),
    current_user: User = Depends(require_admin_user),
) -> Dict[str, Any]:
    return await _get_bank_statement_pdf_url(statement_id=statement_id, db=db, current_user=current_user)


@router.post("/bank-statements/manual-from-text")
async def create_manual_bank_statement_from_text_public(
    payload: ManualPastedStatement,
    db: Session = Depends(get_db_sqla),
    current_user: User = Depends(require_admin_user),
) -> Dict[str, Any]:
    return await _create_manual_bank_statement_from_text(payload=payload, db=db, current_user=current_user)
