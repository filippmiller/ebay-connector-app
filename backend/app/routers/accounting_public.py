from __future__ import annotations

from fastapi import APIRouter, Depends, Body
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date

from app.models_sqlalchemy import get_db as get_db_sqla
from app.models.user import User
from app.services.admin_auth import require_admin_user

# Reuse implementations from the /api/accounting router.
from app.routers.accounting import (
    list_bank_statements as _list_bank_statements,
    get_bank_statement_detail as _get_bank_statement_detail,
    get_bank_statement_rows as _get_bank_statement_rows,
    commit_bank_rows_to_transactions as _commit_bank_rows_to_transactions,
    delete_bank_statement as _delete_bank_statement,
    CommitRowsRequest,
)


router = APIRouter(prefix="/accounting", tags=["accounting_public"])


@router.get("/bank-statements")
async def list_bank_statements_public(
    limit: int = 50,
    offset: int = 0,
    bank_name: Optional[str] = None,
    status_filter: Optional[str] = None,
    period_from: Optional[date] = None,
    period_to: Optional[date] = None,
    db: Session = Depends(get_db_sqla),
    current_user: User = Depends(require_admin_user),
):
    # Delegate to existing implementation
    return await _list_bank_statements(
        limit=limit,
        offset=offset,
        bank_name=bank_name,
        status_filter=status_filter,
        period_from=period_from,
        period_to=period_to,
        db=db,
        current_user=current_user,
    )


@router.get("/bank-statements/{statement_id}")
async def get_bank_statement_detail_public(
    statement_id: int,
    db: Session = Depends(get_db_sqla),
    current_user: User = Depends(require_admin_user),
):
    return await _get_bank_statement_detail(statement_id=statement_id, db=db, current_user=current_user)


@router.get("/bank-statements/{statement_id}/rows")
async def get_bank_statement_rows_public(
    statement_id: int,
    db: Session = Depends(get_db_sqla),
    current_user: User = Depends(require_admin_user),
):
    return await _get_bank_statement_rows(statement_id=statement_id, db=db, current_user=current_user)


@router.post("/bank-statements/{statement_id}/commit-rows")
async def commit_bank_rows_to_transactions_public(
    statement_id: int,
    body: CommitRowsRequest = Body(default=CommitRowsRequest()),
    db: Session = Depends(get_db_sqla),
    current_user: User = Depends(require_admin_user),
):
    return await _commit_bank_rows_to_transactions(
        statement_id=statement_id,
        body=body,
        db=db,
        current_user=current_user,
    )


@router.delete("/bank-statements/{statement_id}")
async def delete_bank_statement_public(
    statement_id: int,
    db: Session = Depends(get_db_sqla),
    current_user: User = Depends(require_admin_user),
):
    return await _delete_bank_statement(statement_id=statement_id, db=db, current_user=current_user)
