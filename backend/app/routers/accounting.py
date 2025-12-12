from __future__ import annotations

from typing import List, Optional, Dict, Any
from datetime import date
from decimal import Decimal
import datetime as dt
import csv
import io
import hashlib
import asyncio
from typing import Iterable

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks, status, Query, Form, Body
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func, case

from app.models_sqlalchemy import get_db as get_db_sqla, SessionLocal
from app.models_sqlalchemy.models import (
    AccountingExpenseCategory,
    AccountingBankStatement,
    AccountingBankStatementFile,
    AccountingBankRow,
    AccountingCashExpense,
    AccountingTransaction,
    AccountingTransactionLog,
    AccountingBankRule,
    AccountingProcessLog,
    AccountingGroup,
    AccountingClassificationCode,
    AccountingTransactionTag,
    User,
)

from app.services.admin_auth import require_admin_user
from app.utils.logger import logger

from app.services.supabase_storage import delete_files



def _log_process(db: Session, stmt_id: int, message: str, level: str = "INFO", details: Optional[Dict[str, Any]] = None):
    """Legacy logging helper used only by old bank-statement background parser.

    Kept as a harmless no-op shim so that any historical background tasks that
    might still reference it do not crash. New Accounting 2 flows do not use it.
    """
    try:
        log_entry = AccountingProcessLog(
            bank_statement_id=stmt_id,
            message=message,
            level=level,
            details=details,
        )
        db.add(log_entry)
    except Exception as e:
        logger.error(f"Failed to write process log: {e}")


# NOTE: The entire legacy OpenAI / CSV / XLSX background parser has been
# removed as part of Accounting v1 decommissioning. All new uploads go
# through /api/accounting2/bank-statements/upload.


router = APIRouter(prefix="/api/accounting", tags=["accounting"])


# --- Expense categories ---


@router.get("/categories")
async def list_categories(
    is_active: Optional[bool] = Query(None),
    db: Session = Depends(get_db_sqla),
    current_user: User = Depends(require_admin_user),
):
    query = db.query(AccountingExpenseCategory)
    if is_active is not None:
        query = query.filter(AccountingExpenseCategory.is_active == is_active)

    rows = query.order_by(AccountingExpenseCategory.sort_order.nulls_last(), AccountingExpenseCategory.code).all()
    return [
        {
            "id": r.id,
            "code": r.code,
            "name": r.name,
            "type": r.type,
            "is_active": r.is_active,
            "sort_order": r.sort_order,
        }
        for r in rows
    ]


@router.post("/categories", status_code=status.HTTP_201_CREATED)
async def create_category(
    code: str,
    name: str,
    type: str,
    is_active: bool = True,
    sort_order: Optional[int] = None,
    db: Session = Depends(get_db_sqla),
    current_user: User = Depends(require_admin_user),
):
    existing = db.query(AccountingExpenseCategory).filter(AccountingExpenseCategory.code == code).first()
    if existing:
        raise HTTPException(status_code=400, detail="Category with this code already exists")

    cat = AccountingExpenseCategory(
        code=code,
        name=name,
        type=type,
        is_active=is_active,
        sort_order=sort_order,
    )
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return {
        "id": cat.id,
        "code": cat.code,
        "name": cat.name,
        "type": cat.type,
        "is_active": cat.is_active,
        "sort_order": cat.sort_order,
    }


@router.put("/categories/{category_id}")
async def update_category(
    category_id: int,
    name: Optional[str] = None,
    type: Optional[str] = None,
    is_active: Optional[bool] = None,
    sort_order: Optional[int] = None,
    db: Session = Depends(get_db_sqla),
    current_user: User = Depends(require_admin_user),
):
    cat = db.query(AccountingExpenseCategory).get(category_id)
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")

    if name is not None:
        cat.name = name
    if type is not None:
        cat.type = type
    if is_active is not None:
        cat.is_active = is_active
    if sort_order is not None:
        cat.sort_order = sort_order

    db.commit()
    db.refresh(cat)
    return {
        "id": cat.id,
        "code": cat.code,
        "name": cat.name,
        "type": cat.type,
        "is_active": cat.is_active,
        "sort_order": cat.sort_order,
    }


# --- Bank Rules ---


class AccountingRuleCreate(BaseModel):
    pattern_type: str
    pattern_value: str
    expense_category_id: int
    priority: int = 10
    is_active: bool = True


@router.get("/rules")
async def list_rules(
    is_active: Optional[bool] = Query(None),
    db: Session = Depends(get_db_sqla),
    current_user: User = Depends(require_admin_user),
):
    query = db.query(AccountingBankRule)
    if is_active is not None:
        query = query.filter(AccountingBankRule.is_active == is_active)
    
    # Order by priority (asc) then id
    rows = query.order_by(AccountingBankRule.priority.asc(), AccountingBankRule.id.asc()).all()
    return [
        {
            "id": r.id,
            "pattern_type": r.pattern_type,
            "pattern_value": r.pattern_value,
            "expense_category_id": r.expense_category_id,
            "priority": r.priority,
            "is_active": r.is_active,
        }
        for r in rows
    ]


@router.post("/rules", status_code=status.HTTP_201_CREATED)
async def create_rule(
    payload: AccountingRuleCreate,
    db: Session = Depends(get_db_sqla),
    current_user: User = Depends(require_admin_user),
):
    rule = AccountingBankRule(
        pattern_type=payload.pattern_type,
        pattern_value=payload.pattern_value,
        expense_category_id=payload.expense_category_id,
        priority=payload.priority,
        is_active=payload.is_active,
        created_by_user_id=current_user.id,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return {
        "id": rule.id,
        "pattern_type": rule.pattern_type,
        "pattern_value": rule.pattern_value,
        "expense_category_id": rule.expense_category_id,
        "priority": rule.priority,
        "is_active": rule.is_active,
    }


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(
    rule_id: int,
    db: Session = Depends(get_db_sqla),
    current_user: User = Depends(require_admin_user),
):
    rule = db.query(AccountingBankRule).get(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    
    db.delete(rule)
    db.commit()
    return None



# --- Bank statements list/detail for legacy data (still used by Accounting 2) ---


@router.get("/bank-statements")
async def list_bank_statements(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    bank_name: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    period_from: Optional[date] = None,
    period_to: Optional[date] = None,
    db: Session = Depends(get_db_sqla),
    current_user: User = Depends(require_admin_user),
):
    query = db.query(AccountingBankStatement)

    if bank_name:
        query = query.filter(AccountingBankStatement.bank_name.ilike(f"%{bank_name}%"))
    if status_filter:
        query = query.filter(AccountingBankStatement.status == status_filter)
    if period_from:
        query = query.filter(AccountingBankStatement.statement_period_start >= period_from)
    if period_to:
        query = query.filter(AccountingBankStatement.statement_period_end <= period_to)

    total = query.count()
    rows = (
        query.order_by(AccountingBankStatement.statement_period_start.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    # Preload row counts
    counts = (
        db.query(AccountingBankRow.bank_statement_id, func.count(AccountingBankRow.id))
        .filter(AccountingBankRow.bank_statement_id.in_([r.id for r in rows]))
        .group_by(AccountingBankRow.bank_statement_id)
        .all()
    )
    count_map = {bid: c for bid, c in counts}

    return {
        "items": [
            {
                "id": r.id,
                "bank_name": r.bank_name,
                "account_last4": r.account_last4,
                "currency": r.currency,
                "statement_period_start": r.statement_period_start.isoformat() if r.statement_period_start else None,
                "statement_period_end": r.statement_period_end.isoformat() if r.statement_period_end else None,
                "opening_balance": str(r.opening_balance) if r.opening_balance is not None else None,
                "closing_balance": str(r.closing_balance) if r.closing_balance is not None else None,
                "status": r.status,
                "rows_count": int(count_map.get(r.id, 0)),
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/bank-statements/{statement_id}")
async def get_bank_statement_detail(
    statement_id: int,
    db: Session = Depends(get_db_sqla),
    current_user: User = Depends(require_admin_user),
):
    stmt = db.query(AccountingBankStatement).get(statement_id)
    if not stmt:
        raise HTTPException(status_code=404, detail="Bank statement not found")

    rows_q = db.query(AccountingBankRow).filter(AccountingBankRow.bank_statement_id == stmt.id)
    rows_count = rows_q.count()

    # Separate debit/credit totals
    sums = (
        db.query(
            func.sum(case((AccountingBankRow.amount > 0, AccountingBankRow.amount), else_=0)),
            func.sum(case((AccountingBankRow.amount < 0, AccountingBankRow.amount), else_=0)),
        )
        .filter(AccountingBankRow.bank_statement_id == stmt.id)
        .one()
    )
    total_credit = sums[0] or Decimal("0")
    total_debit = sums[1] or Decimal("0")

    return {
        "id": stmt.id,
        "bank_name": stmt.bank_name,
        "account_last4": stmt.account_last4,
        "currency": stmt.currency,
        "statement_period_start": stmt.statement_period_start,
        "statement_period_end": stmt.statement_period_end,
        "status": stmt.status,
        "created_at": stmt.created_at,
        "rows_count": rows_count,
        "total_credit": total_credit,
        "total_debit": total_debit,
        "error_message": stmt.error_message,
        "raw_response": stmt.raw_openai_response,
        "raw_json": stmt.raw_json,
        "raw_header_json": stmt.raw_header_json,
        "logs": [
            {"timestamp": log.timestamp, "level": log.level, "message": log.message, "details": log.details}
            for log in db.query(AccountingProcessLog).filter(AccountingProcessLog.bank_statement_id == stmt.id).order_by(AccountingProcessLog.timestamp).all()
        ]
    }


@router.get("/bank-statements/{statement_id}/rows")
async def get_bank_statement_rows(
    statement_id: int,
    db: Session = Depends(get_db_sqla),
    current_user: User = Depends(require_admin_user),
):
    """Return all rows for a statement."""
    rows = (
        db.query(AccountingBankRow)
        .filter(AccountingBankRow.bank_statement_id == statement_id)
        .order_by(AccountingBankRow.row_index.asc())
        .all()
    )
    return {"rows": rows}


class CommitRowsRequest(BaseModel):
    commit_all_non_ignored: bool = False
    row_ids: Optional[List[int]] = None

@router.post("/bank-statements/{statement_id}/commit-rows")
async def commit_bank_rows_to_transactions(
    statement_id: int,
    body: CommitRowsRequest = Body(default=CommitRowsRequest()),
    db: Session = Depends(get_db_sqla),
    current_user: User = Depends(require_admin_user),
):
    """
    Create accounting transactions from parsed bank rows.
    - If commit_all_non_ignored is True: commit all rows for the statement whose parsed_status != 'ignored'.
    - Else if row_ids provided: commit only those rows.
    Skips rows already committed (bank_row_id unique).
    """
    stmt = db.query(AccountingBankStatement).get(statement_id)
    if not stmt:
        raise HTTPException(status_code=404, detail="Bank statement not found")

    rows_q = db.query(AccountingBankRow).filter(AccountingBankRow.bank_statement_id == stmt.id)
    if body.commit_all_non_ignored:
        rows_q = rows_q.filter(AccountingBankRow.parsed_status != "ignored")
    elif body.row_ids:
        rows_q = rows_q.filter(AccountingBankRow.id.in_(body.row_ids))
    else:
        raise HTTPException(status_code=400, detail="Provide row_ids or set commit_all_non_ignored=true")

    rows = rows_q.all()
    if not rows:
        return {"committed": 0, "skipped_existing": 0, "total_selected": 0}

    from decimal import Decimal

    committed = 0
    skipped = 0

    for r in rows:
        # Skip if already committed (unique bank_row_id)
        existing = db.query(AccountingTransaction).filter(AccountingTransaction.bank_row_id == r.id).first()
        if existing:
            skipped += 1
            continue

        raw_amount: Decimal = r.amount or Decimal("0")
        # Determine direction and absolute amount
        if r.direction and r.direction.upper() in ("CREDIT", "DEBIT"):
            direction = "in" if r.direction.upper() == "CREDIT" else "out"
            amount = abs(raw_amount)
        else:
            direction = "in" if raw_amount >= 0 else "out"
            amount = abs(raw_amount)

        # Manual uploads (MANUAL_PASTE / MANUAL_XLSX) should be tagged as source_type=manual
        src_type = "manual" if (stmt.source_type or "").upper().startswith("MANUAL") else "bank_statement"

        txn = AccountingTransaction(
            date=r.operation_date or r.posting_date or stmt.statement_period_start or dt.date.today(),
            amount=amount,
            direction=direction,
            source_type=src_type,
            source_id=r.bank_statement_id,
            bank_row_id=r.id,
            account_name=(f"{stmt.bank_name} ****{stmt.account_last4}" if stmt.account_last4 else stmt.bank_name),
            counterparty=None,
            description=r.description_clean or r.description_raw,
            expense_category_id=r.expense_category_id,
            storage_id=None,
            is_personal=False,
            is_internal_transfer=False,
            created_by_user_id=current_user.id,
            updated_by_user_id=current_user.id,
        )
        db.add(txn)
        committed += 1

    db.commit()

    return {
        "committed": committed,
        "skipped_existing": skipped,
        "total_selected": len(rows),
    }


@router.delete("/bank-statements/{statement_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bank_statement(
    statement_id: int,
    db: Session = Depends(get_db_sqla),
    current_user: User = Depends(require_admin_user),
):
    """
    Delete a bank statement along with all associated data:
    - Committed ledger transactions (accounting_transaction)
    - Parsed rows (accounting_bank_row) - cascade via FK
    - File records (accounting_bank_statement_file) - cascade via FK
    - Files in Supabase storage
    """
    stmt = db.query(AccountingBankStatement).get(statement_id)
    if not stmt:
        raise HTTPException(status_code=404, detail="Statement not found")
    
    # 1. Delete committed transactions that reference this statement's rows
    # (accounting_transaction.bank_row_id doesn't have CASCADE, so manual cleanup)
    row_ids = [r.id for r in db.query(AccountingBankRow.id).filter(
        AccountingBankRow.bank_statement_id == statement_id
    ).all()]
    
    if row_ids:
        deleted_txns = db.query(AccountingTransaction).filter(
            AccountingTransaction.bank_row_id.in_(row_ids)
        ).delete(synchronize_session=False)
        logger.info(f"Deleted {deleted_txns} committed transactions for statement {statement_id}")
    
    # 2. Get file records for storage cleanup
    file_records = db.query(AccountingBankStatementFile).filter(
        AccountingBankStatementFile.bank_statement_id == statement_id
    ).all()
    
    storage_paths = [f.storage_path for f in file_records if f.storage_path]
    
    # 3. Delete the statement (rows and file records will cascade)
    db.delete(stmt)
    db.commit()
    
    # 4. Clean up Supabase storage
    if storage_paths:
        try:
            delete_files("bank-statements", storage_paths)
            logger.info(f"Deleted {len(storage_paths)} files from storage for statement {statement_id}")
        except Exception as e:
            logger.error(f"Failed to delete files from storage: {e}")
            # Don't fail the request - DB cleanup is more important
    
    return None


@router.get("/transactions")
async def get_transactions_totals(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    source_type: Optional[str] = None,
    storage_id: Optional[str] = None,
    category_id: Optional[int] = None,
    direction: Optional[str] = None,
    min_amount: Optional[float] = None,
    max_amount: Optional[float] = None,
    account_name: Optional[str] = None,
    is_personal: Optional[bool] = None,
    is_internal_transfer: Optional[bool] = None,
    db: Session = Depends(get_db_sqla),
    current_user: User = Depends(require_admin_user),
):
    query = db.query(AccountingTransaction)

    if date_from:
        query = query.filter(AccountingTransaction.date >= date_from)
    if date_to:
        query = query.filter(AccountingTransaction.date <= date_to)
    if source_type:
        query = query.filter(AccountingTransaction.source_type == source_type)
    if storage_id:
        query = query.filter(AccountingTransaction.storage_id.ilike(f"%{storage_id}%"))
    if category_id:
        query = query.filter(AccountingTransaction.expense_category_id == category_id)
    if direction:
        query = query.filter(AccountingTransaction.direction == direction)
    if min_amount is not None:
        query = query.filter(AccountingTransaction.amount >= min_amount)
    if max_amount is not None:
        query = query.filter(AccountingTransaction.amount <= max_amount)
    if account_name:
        query = query.filter(AccountingTransaction.account_name.ilike(f"%{account_name}%"))
    if is_personal is not None:
        query = query.filter(AccountingTransaction.is_personal == is_personal)
    if is_internal_transfer is not None:
        query = query.filter(AccountingTransaction.is_internal_transfer == is_internal_transfer)

    # Calculate totals
    sums = query.with_entities(
        func.sum(case((AccountingTransaction.direction == 'in', AccountingTransaction.amount), else_=0)),
        func.sum(case((AccountingTransaction.direction == 'out', AccountingTransaction.amount), else_=0))
    ).first()

    total_in = sums[0] or Decimal("0")
    total_out = sums[1] or Decimal("0")
    net = total_in - total_out

    return {
        "total_in": float(total_in),
        "total_out": float(total_out),
        "net": float(net)
    }


class AccountingTransactionUpdate(BaseModel):
    expense_category_id: Optional[int] = None
    storage_id: Optional[str] = None
    is_personal: Optional[bool] = None
    is_internal_transfer: Optional[bool] = None
    flag_code: Optional[str] = None  # stored in AccountingTransaction.subcategory


@router.put("/transactions/{transaction_id}")
async def update_transaction(
    transaction_id: int,
    payload: AccountingTransactionUpdate,
    db: Session = Depends(get_db_sqla),
    current_user: User = Depends(require_admin_user),
):
    txn = db.query(AccountingTransaction).get(transaction_id)
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")

    # Track old values for logging
    changes: Dict[str, Any] = {}

    def _set_attr(field: str, value: Any):
        old = getattr(txn, field)
        if value is not None and old != value:
            setattr(txn, field, value)
            changes[field] = {"old": str(old), "new": str(value)}

    if payload.expense_category_id is not None:
        _set_attr("expense_category_id", payload.expense_category_id)
    if payload.storage_id is not None:
        _set_attr("storage_id", payload.storage_id)
    if payload.is_personal is not None:
        _set_attr("is_personal", payload.is_personal)
    if payload.is_internal_transfer is not None:
        _set_attr("is_internal_transfer", payload.is_internal_transfer)
    if payload.flag_code is not None:
        # Use subcategory field as a simple string flag/tag code
        _set_attr("subcategory", payload.flag_code)

    if not changes:
        return {"id": txn.id, "updated": False}

    txn.updated_by_user_id = current_user.id

    # Write logs for each changed field
    for field, meta in changes.items():
        log = AccountingTransactionLog(
            transaction_id=txn.id,
            changed_by_user_id=current_user.id,
            field_name=field,
            old_value=meta["old"],
            new_value=meta["new"],
        )
        db.add(log)

    db.commit()
    db.refresh(txn)

    return {"id": txn.id, "updated": True}


class RuleApplyRequest(BaseModel):
    transaction_ids: List[int]
    expense_category_id: Optional[int] = None


@router.post("/rules/{rule_id}/apply")
async def apply_rule_to_transactions(
    rule_id: int,
    payload: RuleApplyRequest,
    db: Session = Depends(get_db_sqla),
    current_user: User = Depends(require_admin_user),
):
    if not payload.transaction_ids:
        raise HTTPException(status_code=400, detail="transaction_ids cannot be empty")

    rule = db.query(AccountingBankRule).get(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    category_id = payload.expense_category_id or rule.expense_category_id
    if not category_id:
        raise HTTPException(status_code=400, detail="No expense_category_id provided on rule or request")

    txns = (
        db.query(AccountingTransaction)
        .filter(AccountingTransaction.id.in_(payload.transaction_ids))
        .all()
    )

    updated = 0
    for txn in txns:
        old_cat = txn.expense_category_id
        if old_cat == category_id:
            continue
        txn.expense_category_id = category_id
        txn.updated_by_user_id = current_user.id
        log = AccountingTransactionLog(
            transaction_id=txn.id,
            changed_by_user_id=current_user.id,
            field_name="expense_category_id",
            old_value=str(old_cat),
            new_value=str(category_id),
        )
        db.add(log)
        updated += 1

    db.commit()

    return {"rule_id": rule_id, "updated": updated, "category_id": category_id}


# --- Transaction tags (flags) ---


class AccountingTagCreate(BaseModel):
    code: str
    label: str
    color: Optional[str] = None


@router.get("/tags")
async def list_tags(
    include_inactive: bool = Query(False),
    db: Session = Depends(get_db_sqla),
    current_user: User = Depends(require_admin_user),
):
    q = db.query(AccountingTransactionTag)
    if not include_inactive:
        q = q.filter(AccountingTransactionTag.is_active == True)
    tags = q.order_by(AccountingTransactionTag.code.asc()).all()
    return [
        {
            "id": t.id,
            "code": t.code,
            "label": t.label,
            "color": t.color,
            "is_active": t.is_active,
        }
        for t in tags
    ]


@router.post("/tags", status_code=status.HTTP_201_CREATED)
async def create_tag(
    payload: AccountingTagCreate,
    db: Session = Depends(get_db_sqla),
    current_user: User = Depends(require_admin_user),
):
    code = payload.code.upper().replace(" ", "_")
    existing = db.query(AccountingTransactionTag).filter(AccountingTransactionTag.code == code).first()
    if existing:
        raise HTTPException(status_code=400, detail="Tag with this code already exists")

    tag = AccountingTransactionTag(
        code=code,
        label=payload.label,
        color=payload.color,
        created_by_user_id=current_user.id,
    )
    db.add(tag)
    db.commit()
    db.refresh(tag)
    return {
        "id": tag.id,
        "code": tag.code,
        "label": tag.label,
        "color": tag.color,
        "is_active": tag.is_active,
    }

@router.post("/test-openai")
async def test_openai_connection(
    current_user: User = Depends(require_admin_user),
):
    """Simple test to verify OpenAI API key is valid and models are reachable."""
    try:
        from app.config import settings
        import openai
        import time

        if not settings.OPENAI_API_KEY:
             return {"success": False, "message": "OPENAI_API_KEY is not set in environment."}

        client = openai.Client(api_key=settings.OPENAI_API_KEY)
        
        start = time.time()
        # Just list models - quick and cheap
        resp = client.models.list()
        elapsed = time.time() - start

        model_count = len(list(resp))
        masked_key = f"{settings.OPENAI_API_KEY[:6]}...{settings.OPENAI_API_KEY[-4:]}"
        
        # Check if our target model exists
        models = [m.id for m in resp]
        target_model = settings.OPENAI_MODEL or "gpt-4o"
        has_model = any(target_model in m for m in models)

        return {
            "success": True,
            "message": f"OpenAI connection successful. Found {model_count} models.",
            "latency_ms": int(elapsed * 1000),
            "model_count": model_count,
            "target_model_available": has_model,
            "configured_model": target_model,
            "masked_key": masked_key
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Connection failed: {str(e)}",
            "masked_key": settings.OPENAI_API_KEY[:6] + "..." if settings.OPENAI_API_KEY else "None"
        }


# ============================================================================
# CLASSIFICATION CODES MANAGEMENT
# ============================================================================

@router.get("/classification-groups")
async def list_classification_groups(
    include_inactive: bool = False,
    db: Session = Depends(get_db_sqla),
    current_user: User = Depends(require_admin_user),
):
    """List all accounting groups with their classification codes counts."""
    query = db.query(AccountingGroup)
    if not include_inactive:
        query = query.filter(AccountingGroup.is_active == True)
    
    groups = query.order_by(AccountingGroup.sort_order).all()
    
    result = []
    for g in groups:
        # Count codes in this group
        code_count = db.query(AccountingClassificationCode).filter(
            AccountingClassificationCode.accounting_group == g.code,
            AccountingClassificationCode.is_active == True
        ).count()
        
        result.append({
            "id": g.id,
            "code": g.code,
            "name": g.name,
            "description": g.description,
            "color": g.color,
            "sort_order": g.sort_order,
            "is_active": g.is_active,
            "codes_count": code_count,
        })
    
    return result


@router.get("/classification-codes")
async def list_classification_codes(
    group: Optional[str] = None,
    include_inactive: bool = False,
    db: Session = Depends(get_db_sqla),
    current_user: User = Depends(require_admin_user),
):
    """List all classification codes, optionally filtered by group."""
    query = db.query(AccountingClassificationCode)
    
    if group:
        query = query.filter(AccountingClassificationCode.accounting_group == group)
    if not include_inactive:
        query = query.filter(AccountingClassificationCode.is_active == True)
    
    codes = query.order_by(
        AccountingClassificationCode.accounting_group,
        AccountingClassificationCode.sort_order
    ).all()
    
    return [
        {
            "id": c.id,
            "code": c.code,
            "name": c.name,
            "description": c.description,
            "accounting_group": c.accounting_group,
            "keywords": c.keywords,
            "sort_order": c.sort_order,
            "is_active": c.is_active,
            "is_system": c.is_system,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "updated_at": c.updated_at.isoformat() if c.updated_at else None,
        }
        for c in codes
    ]


@router.post("/classification-codes")
async def create_classification_code(
    code: str = Form(...),
    name: str = Form(...),
    accounting_group: str = Form(...),
    description: Optional[str] = Form(None),
    keywords: Optional[str] = Form(None),
    db: Session = Depends(get_db_sqla),
    current_user: User = Depends(require_admin_user),
):
    """Create a new classification code."""
    # Validate code format (uppercase, underscores)
    code = code.upper().replace(" ", "_")
    
    # Check if code already exists
    existing = db.query(AccountingClassificationCode).filter(
        AccountingClassificationCode.code == code
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Code '{code}' already exists")
    
    # Validate group exists
    group = db.query(AccountingGroup).filter(AccountingGroup.code == accounting_group).first()
    if not group:
        raise HTTPException(status_code=400, detail=f"Group '{accounting_group}' not found")
    
    # Get next sort order
    max_order = db.query(func.max(AccountingClassificationCode.sort_order)).filter(
        AccountingClassificationCode.accounting_group == accounting_group
    ).scalar() or 0
    
    new_code = AccountingClassificationCode(
        code=code,
        name=name,
        description=description,
        accounting_group=accounting_group,
        keywords=keywords,
        sort_order=max_order + 1,
        is_system=False,  # User-created codes are not system
    )
    db.add(new_code)
    db.commit()
    db.refresh(new_code)
    
    return {
        "id": new_code.id,
        "code": new_code.code,
        "name": new_code.name,
        "description": new_code.description,
        "accounting_group": new_code.accounting_group,
        "keywords": new_code.keywords,
        "sort_order": new_code.sort_order,
        "is_active": new_code.is_active,
        "is_system": new_code.is_system,
    }


@router.put("/classification-codes/{code_id}")
async def update_classification_code(
    code_id: int,
    name: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    keywords: Optional[str] = Form(None),
    is_active: Optional[bool] = Form(None),
    db: Session = Depends(get_db_sqla),
    current_user: User = Depends(require_admin_user),
):
    """Update an existing classification code."""
    code_obj = db.query(AccountingClassificationCode).get(code_id)
    if not code_obj:
        raise HTTPException(status_code=404, detail="Code not found")
    
    if name is not None:
        code_obj.name = name
    if description is not None:
        code_obj.description = description
    if keywords is not None:
        code_obj.keywords = keywords
    if is_active is not None:
        code_obj.is_active = is_active
    
    db.commit()
    db.refresh(code_obj)
    
    return {
        "id": code_obj.id,
        "code": code_obj.code,
        "name": code_obj.name,
        "description": code_obj.description,
        "accounting_group": code_obj.accounting_group,
        "keywords": code_obj.keywords,
        "sort_order": code_obj.sort_order,
        "is_active": code_obj.is_active,
        "is_system": code_obj.is_system,
    }


@router.delete("/classification-codes/{code_id}")
async def delete_classification_code(
    code_id: int,
    db: Session = Depends(get_db_sqla),
    current_user: User = Depends(require_admin_user),
):
    """Delete a classification code (soft delete for system codes)."""
    code_obj = db.query(AccountingClassificationCode).get(code_id)
    if not code_obj:
        raise HTTPException(status_code=404, detail="Code not found")
    
    if code_obj.is_system:
        # Soft delete for system codes - just deactivate
        code_obj.is_active = False
        db.commit()
        return {"message": f"System code '{code_obj.code}' deactivated (cannot be deleted)"}
    
    # Hard delete for user-created codes
    db.delete(code_obj)
    db.commit()
    return {"message": f"Code '{code_obj.code}' deleted"}


@router.post("/classification-groups")
async def create_classification_group(
    code: str = Form(...),
    name: str = Form(...),
    description: Optional[str] = Form(None),
    color: Optional[str] = Form("#6b7280"),
    db: Session = Depends(get_db_sqla),
    current_user: User = Depends(require_admin_user),
):
    """Create a new accounting group."""
    code = code.upper().replace(" ", "_")
    
    existing = db.query(AccountingGroup).filter(AccountingGroup.code == code).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Group '{code}' already exists")
    
    max_order = db.query(func.max(AccountingGroup.sort_order)).scalar() or 0
    
    new_group = AccountingGroup(
        code=code,
        name=name,
        description=description,
        color=color,
        sort_order=max_order + 1,
    )
    db.add(new_group)
    db.commit()
    db.refresh(new_group)
    
    return {
        "id": new_group.id,
        "code": new_group.code,
        "name": new_group.name,
        "description": new_group.description,
        "color": new_group.color,
        "sort_order": new_group.sort_order,
        "is_active": new_group.is_active,
    }


@router.put("/classification-groups/{group_id}")
async def update_classification_group(
    group_id: int,
    name: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    color: Optional[str] = Form(None),
    is_active: Optional[bool] = Form(None),
    db: Session = Depends(get_db_sqla),
    current_user: User = Depends(require_admin_user),
):
    """Update an accounting group."""
    group = db.query(AccountingGroup).get(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    
    if name is not None:
        group.name = name
    if description is not None:
        group.description = description
    if color is not None:
        group.color = color
    if is_active is not None:
        group.is_active = is_active
    
    db.commit()
    db.refresh(group)
    
    return {
        "id": group.id,
        "code": group.code,
        "name": group.name,
        "description": group.description,
        "color": group.color,
        "sort_order": group.sort_order,
        "is_active": group.is_active,
    }
