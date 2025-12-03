from __future__ import annotations

from typing import List, Optional, Dict, Any
from datetime import date
from decimal import Decimal
import csv
import io
from typing import Iterable

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models_sqlalchemy import get_db as get_db_sqla
from app.models_sqlalchemy.models import (
    AccountingExpenseCategory,
    AccountingBankStatement,
    AccountingBankStatementFile,
    AccountingBankRow,
    AccountingCashExpense,
    AccountingTransaction,
    AccountingTransactionLog,
    User,
)
from app.services.admin_auth import require_admin_user
from app.utils.logger import logger


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
    pattern_type: str,
    pattern_value: str,
    expense_category_id: int,
    priority: int = 10,
    is_active: bool = True,
    db: Session = Depends(get_db_sqla),
    current_user: User = Depends(require_admin_user),
):
    rule = AccountingBankRule(
        pattern_type=pattern_type,
        pattern_value=pattern_value,
        expense_category_id=expense_category_id,
        priority=priority,
        is_active=is_active,
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



# --- Bank statements upload & rows ---


import hashlib
from app.services.accounting_parsers.csv_parser import parse_csv_bytes
from app.services.accounting_parsers.xlsx_parser import parse_xlsx_bytes
from app.services.accounting_parsers.pdf_parser import parse_pdf_bytes
from app.services.accounting_rules_engine import apply_rules_to_bank_rows



@router.post("/bank-statements", status_code=status.HTTP_201_CREATED)
async def upload_bank_statement(
    bank_name: str = Form(...),
    account_last4: Optional[str] = Form(None),
    currency: Optional[str] = Form(None),
    statement_period_start: Optional[date] = Form(None),
    statement_period_end: Optional[date] = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db_sqla),
    current_user: User = Depends(require_admin_user),
):
    # 1. Read file and compute hash
    file_bytes = await file.read()
    file_hash = hashlib.sha256(file_bytes).hexdigest()

    # 2. Check for duplicate statement
    existing_stmt = (
        db.query(AccountingBankStatement)
        .filter(AccountingBankStatement.file_hash == file_hash)
        .first()
    )
    if existing_stmt:
        # If already uploaded, just return the existing one
        # We could also check if it was parsed successfully and retry if not,
        # but for now let's assume "uploaded" means we have it.
        return {"id": existing_stmt.id, "status": existing_stmt.status, "message": "Statement already uploaded"}

    # 3. Create new statement record
    stmt = AccountingBankStatement(
        bank_name=bank_name,
        account_last4=account_last4,
        currency=currency,
        statement_period_start=statement_period_start,
        statement_period_end=statement_period_end,
        status="uploaded",
        file_hash=file_hash,
        created_by_user_id=current_user.id,
        updated_by_user_id=current_user.id,
    )
    db.add(stmt)
    db.flush()

    storage_path = f"accounting/bank_statements/{stmt.id}/{file.filename}"
    # NOTE: actual writing to storage/bucket is environment-specific and reused from existing infra (to be wired separately)

    stmt_file = AccountingBankStatementFile(
        bank_statement_id=stmt.id,
        file_type=file.content_type or "",
        storage_path=storage_path,
        uploaded_by_user_id=current_user.id,
    )
    db.add(stmt_file)

    ext = (file.filename or "").lower()
    content_type = (file.content_type or "").lower()
    is_csv_like = ext.endswith(".csv") or ext.endswith(".txt")
    is_xlsx_like = ext.endswith(".xlsx") or ext.endswith(".xls")
    is_pdf_like = ext.endswith(".pdf") or "pdf" in content_type

    new_rows = []

    if is_pdf_like:
        try:
            parsed = await parse_pdf_bytes(file_bytes)
            
            # Helper to generate row dedupe key (reused)
            def _make_row_dedupe_key(row_data: Dict[str, Any], stmt_id: int) -> str:
                raw_str = f"{stmt_id}|{row_data.get('__index__')}|{row_data.get('date')}|{row_data.get('amount')}|{row_data.get('description')}"
                return hashlib.sha256(raw_str.encode('utf-8')).hexdigest()

            for row in parsed:
                amount_raw = row.get("amount")
                try:
                    amount_val = Decimal(str(amount_raw)) if amount_raw not in (None, "") else Decimal("0")
                except Exception:
                    amount_val = Decimal("0")

                bal_raw = row.get("balance")
                try:
                    bal_val = Decimal(str(bal_raw)) if bal_raw not in (None, "") else None
                except Exception:
                    bal_val = None

                op_date_raw = row.get("date")
                op_date: Optional[date] = None
                if op_date_raw:
                    try:
                        op_date = date.fromisoformat(str(op_date_raw))
                    except Exception:
                        op_date = None

                description_raw = row.get("description") or ""

                dedupe_key = _make_row_dedupe_key(row, stmt.id)

                db_row = AccountingBankRow(
                    bank_statement_id=stmt.id,
                    row_index=row.get("__index__"),
                    operation_date=op_date,
                    description_raw=description_raw,
                    amount=amount_val,
                    balance_after=bal_val,
                    currency=row.get("currency") or currency,
                    parsed_status="auto_parsed",
                    match_status="unmatched",
                    dedupe_key=dedupe_key,
                    created_by_user_id=current_user.id,
                    updated_by_user_id=current_user.id,
                )
                db.add(db_row)
                new_rows.append(db_row)

            stmt.status = "parsed"
        except Exception as e:
            logger.warning(f"Failed to parse PDF bank statement: {e}")
            stmt.status = "error_parsing_failed"

    elif is_csv_like or is_xlsx_like:
        try:
            parsed = parse_xlsx_bytes(file_bytes) if is_xlsx_like else parse_csv_bytes(file_bytes)
            
            # Helper to generate row dedupe key
            def _make_row_dedupe_key(row_data: Dict[str, Any], stmt_id: int) -> str:
                # Combine statement ID with row content to ensure uniqueness within the system
                # but allow same transaction in different statements (if desired, or globally unique?)
                # Requirement says: "At bank row level (idempotent re-upload of the same file)."
                # Since we already dedupe the file by hash, this is a secondary check.
                # Let's use a content hash.
                raw_str = f"{stmt_id}|{row_data.get('__index__')}|{row_data.get('date')}|{row_data.get('amount')}|{row_data.get('description')}"
                return hashlib.sha256(raw_str.encode('utf-8')).hexdigest()

            for row in parsed:
                # The header normalizer stores keys in lower-case form, so we
                # first try those and then fall back to a few common variants
                # used by legacy exports.
                amount_raw = (
                    row.get("amount")
                    or row.get("transaction amount")
                    or row.get("debit")
                    or row.get("credit")
                    or row.get("Amount")
                    or row.get("AMOUNT")
                )
                try:
                    amount_val = Decimal(str(amount_raw)) if amount_raw not in (None, "") else Decimal("0")
                except Exception:
                    amount_val = Decimal("0")

                bal_raw = (
                    row.get("balance")
                    or row.get("running balance")
                    or row.get("Balance")
                    or row.get("BALANCE")
                )
                try:
                    bal_val = Decimal(str(bal_raw)) if bal_raw not in (None, "") else None
                except Exception:
                    bal_val = None

                op_date_raw = (
                    row.get("date")
                    or row.get("transaction date")
                    or row.get("operation date")
                    or row.get("posting date")
                    or row.get("Date")
                    or row.get("operation_date")
                )
                op_date: Optional[date] = None
                if op_date_raw:
                    try:
                        op_date = date.fromisoformat(str(op_date_raw))
                    except Exception:
                        op_date = None

                description_raw = (
                    row.get("description")
                    or row.get("transaction description")
                    or row.get("details")
                    or row.get("memo")
                    or row.get("Description")
                    or row.get("DESC")
                    or ""
                )

                dedupe_key = _make_row_dedupe_key(row, stmt.id)

                db_row = AccountingBankRow(
                    bank_statement_id=stmt.id,
                    row_index=row.get("__index__"),
                    operation_date=op_date,
                    description_raw=description_raw,
                    amount=amount_val,
                    balance_after=bal_val,
                    currency=row.get("currency") or row.get("Currency") or currency,
                    parsed_status="auto_parsed",
                    match_status="unmatched",
                    dedupe_key=dedupe_key,
                    created_by_user_id=current_user.id,
                    updated_by_user_id=current_user.id,
                )
                db.add(db_row)
                new_rows.append(db_row)

            stmt.status = "parsed"
        except Exception as e:
            logger.warning(f"Failed to auto-parse bank statement table file: {e}")
            stmt.status = "uploaded"
    else:
        # PDF and other formats: only store file, no parsing yet
        stmt.status = "uploaded"

    # Apply auto-categorization rules
    if new_rows:
        apply_rules_to_bank_rows(db, new_rows)

    db.commit()
    db.refresh(stmt)

    return {"id": stmt.id, "status": stmt.status}


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
            func.sum(func.case([(AccountingBankRow.amount > 0, AccountingBankRow.amount)], else_=0)),
            func.sum(func.case([(AccountingBankRow.amount < 0, AccountingBankRow.amount)], else_=0)),
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
        "statement_period_start": stmt.statement_period_start.isoformat() if stmt.statement_period_start else None,
        "statement_period_end": stmt.statement_period_end.isoformat() if stmt.statement_period_end else None,
        "status": stmt.status,
        "rows_count": rows_count,
        "total_credit": float(total_credit),
        "total_debit": float(total_debit),
    }


@router.get("/bank-statements/{statement_id}/rows")
async def list_bank_rows(
    statement_id: int,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    search: Optional[str] = None,
    parsed_status: Optional[str] = None,
    match_status: Optional[str] = None,
    db: Session = Depends(get_db_sqla),
    current_user: User = Depends(require_admin_user),
):
    stmt = db.query(AccountingBankStatement).get(statement_id)
    if not stmt:
        raise HTTPException(status_code=404, detail="Bank statement not found")

    query = db.query(AccountingBankRow).filter(AccountingBankRow.bank_statement_id == stmt.id)
    if search:
        like = f"%{search}%"
        query = query.filter(
            AccountingBankRow.description_raw.ilike(like)
            | AccountingBankRow.description_clean.ilike(like)
        )
    if parsed_status:
        query = query.filter(AccountingBankRow.parsed_status == parsed_status)
    if match_status:
        query = query.filter(AccountingBankRow.match_status == match_status)

    total = query.count()
    rows = (
        query.order_by(AccountingBankRow.operation_date, AccountingBankRow.row_index)
        .offset(offset)
        .limit(limit)
        .all()
    )

    return {
        "rows": [
            {
                "id": r.id,
                "row_index": r.row_index,
                "operation_date": r.operation_date.isoformat() if r.operation_date else None,
                "posting_date": r.posting_date.isoformat() if r.posting_date else None,
                "description_raw": r.description_raw,
                "description_clean": r.description_clean,
                "amount": float(r.amount) if r.amount is not None else None,
                "balance_after": float(r.balance_after) if r.balance_after is not None else None,
                "currency": r.currency,
                "parsed_status": r.parsed_status,
                "match_status": r.match_status,
                "expense_category_id": r.expense_category_id,
                "auto_guessed_category": None,
            }
            for r in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.put("/bank-rows/{row_id}")
async def update_bank_row(
    row_id: int,
    description_clean: Optional[str] = None,
    parsed_status: Optional[str] = None,
    match_status: Optional[str] = None,
    expense_category_id: Optional[int] = None,
    db: Session = Depends(get_db_sqla),
    current_user: User = Depends(require_admin_user),
):
    row = db.query(AccountingBankRow).get(row_id)
    if not row:
        raise HTTPException(status_code=404, detail="Bank row not found")

    if description_clean is not None:
        row.description_clean = description_clean
    if parsed_status is not None:
        row.parsed_status = parsed_status
    if match_status is not None:
        row.match_status = match_status
    if expense_category_id is not None:
        row.expense_category_id = expense_category_id

    row.updated_by_user_id = current_user.id
    db.commit()
    db.refresh(row)
    return {"ok": True}


@router.post("/bank-statements/{statement_id}/commit-rows")
async def commit_bank_rows(
    statement_id: int,
    row_ids: Optional[List[int]] = None,
    commit_all_non_ignored: bool = False,
    default_account_name: Optional[str] = None,
    mark_as_internal_transfer: bool = False,
    mark_as_personal: bool = False,
    db: Session = Depends(get_db_sqla),
    current_user: User = Depends(require_admin_user),
):
    stmt = db.query(AccountingBankStatement).get(statement_id)
    if not stmt:
        raise HTTPException(status_code=404, detail="Bank statement not found")

    query = db.query(AccountingBankRow).filter(AccountingBankRow.bank_statement_id == stmt.id)
    if row_ids:
        query = query.filter(AccountingBankRow.id.in_(row_ids))
    elif commit_all_non_ignored:
        query = query.filter(AccountingBankRow.parsed_status != "ignored")

    rows = query.all()
    if not rows:
        return {"created": 0}

    def _make_dedupe_key(
        *,
        txn_date: date,
        direction: str,
        amount_abs: Decimal,
        description: str,
        currency: Optional[str],
        account_name: Optional[str],
    ) -> str:
        """Create a deterministic dedupe key for ledger transactions.

        This is computed purely in Python and **not** stored in the database;
        we use it to search for an existing AccountingTransaction that matches
        the same logical movement of money. This keeps the behaviour
        idempotent across repeated imports without requiring a schema change.
        """

        import hashlib

        desc_norm = " ".join((description or "").strip().lower().split())
        parts = [
            txn_date.isoformat(),
            direction,
            f"{amount_abs:.2f}",
            desc_norm,
            (currency or "").upper(),
            (account_name or ""),
        ]
        raw = "|".join(parts)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    created_count = 0
    for r in rows:
        amount = Decimal(str(r.amount)) if r.amount is not None else Decimal("0")
        if amount == 0:
            continue
        direction = "in" if amount > 0 else "out"
        amount_abs = abs(amount)
        txn_date_val: date = r.operation_date or stmt.statement_period_start or date.today()
        account_name_val = default_account_name or f"{stmt.bank_name} ****{stmt.account_last4}".strip()
        description_val = r.description_clean or r.description_raw or ""

        # Compute an in-memory dedupe key and search for an existing transaction
        # that matches the same logical movement. This protects against
        # duplicate ledger entries when the same statement (or its fragment) is
        # uploaded and committed multiple times.
        dedupe_key = _make_dedupe_key(
            txn_date=txn_date_val,
            direction=direction,
            amount_abs=amount_abs,
            description=description_val,
            currency=stmt.currency,
            account_name=account_name_val,
        )

        existing = (
            db.query(AccountingTransaction)
            .filter(
                AccountingTransaction.date == txn_date_val,
                AccountingTransaction.direction == direction,
                AccountingTransaction.amount == amount_abs,
                AccountingTransaction.account_name == account_name_val,
                AccountingTransaction.description == description_val,
                AccountingTransaction.source_type == "bank_statement",
            )
            .first()
        )
        if existing:
            # Mark the bank row as matched, but do not create a duplicate
            # AccountingTransaction.
            r.match_status = "matched_to_transaction"
            r.updated_by_user_id = current_user.id
            continue

        txn = AccountingTransaction(
            date=txn_date_val,
            amount=amount_abs,
            direction=direction,
            source_type="bank_statement",
            source_id=r.id,
            bank_row_id=r.id,
            account_name=account_name_val,
            account_id=None,
            counterparty=None,
            description=description_val,
            expense_category_id=r.expense_category_id,
            is_personal=mark_as_personal,
            is_internal_transfer=mark_as_internal_transfer,
            created_by_user_id=current_user.id,
            updated_by_user_id=current_user.id,
        )
        db.add(txn)
        db.flush()

        log = AccountingTransactionLog(
            transaction_id=txn.id,
            changed_by_user_id=current_user.id,
            field_name="create",
            old_value=None,
            new_value="created from bank_statement_row",
        )
        db.add(log)

        r.match_status = "matched_to_transaction"
        r.updated_by_user_id = current_user.id
        created_count += 1

    stmt.status = "review_in_progress"
    db.commit()

    return {"created": created_count, "statement_status": stmt.status}


# --- Cash expenses ---


@router.post("/cash-expenses", status_code=status.HTTP_201_CREATED)
async def create_cash_expense(
    date_value: date,
    amount: Decimal,
    currency: Optional[str] = None,
    paid_by_user_id: Optional[str] = None,
    counterparty: Optional[str] = None,
    description: Optional[str] = None,
    expense_category_id: int = None,
    storage_id: Optional[str] = None,
    receipt_image_path: Optional[str] = None,
    db: Session = Depends(get_db_sqla),
    current_user: User = Depends(require_admin_user),
):
    paid_by = paid_by_user_id or current_user.id
    if expense_category_id is None:
        raise HTTPException(status_code=400, detail="expense_category_id is required")

    cash = AccountingCashExpense(
        date=date_value,
        amount=amount,
        currency=currency,
        paid_by_user_id=paid_by,
        counterparty=counterparty,
        description=description,
        expense_category_id=expense_category_id,
        storage_id=storage_id,
        receipt_image_path=receipt_image_path,
        created_by_user_id=current_user.id,
        updated_by_user_id=current_user.id,
    )
    db.add(cash)
    db.flush()

    txn = AccountingTransaction(
        date=date_value,
        amount=abs(amount),
        direction="out",
        source_type="cash_manual",
        source_id=cash.id,
        account_name="Cash",
        description=description,
        expense_category_id=expense_category_id,
        storage_id=storage_id,
        is_personal=False,
        is_internal_transfer=False,
        created_by_user_id=current_user.id,
        updated_by_user_id=current_user.id,
    )
    db.add(txn)
    db.flush()

    log = AccountingTransactionLog(
        transaction_id=txn.id,
        changed_by_user_id=current_user.id,
        field_name="create",
        old_value=None,
        new_value="created from cash_expense",
    )
    db.add(log)

    db.commit()
    db.refresh(cash)

    return {"id": cash.id}


@router.get("/cash-expenses")
async def list_cash_expenses(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    expense_category_id: Optional[int] = None,
    paid_by_user_id: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db_sqla),
    current_user: User = Depends(require_admin_user),
):
    query = db.query(AccountingCashExpense)

    if date_from:
        query = query.filter(AccountingCashExpense.date >= date_from)
    if date_to:
        query = query.filter(AccountingCashExpense.date <= date_to)
    if expense_category_id:
        query = query.filter(AccountingCashExpense.expense_category_id == expense_category_id)
    if paid_by_user_id:
        query = query.filter(AccountingCashExpense.paid_by_user_id == paid_by_user_id)

    total = query.count()
    rows = (
        query.order_by(AccountingCashExpense.date.desc(), AccountingCashExpense.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return {
        "rows": [
            {
                "id": r.id,
                "date": r.date.isoformat() if r.date else None,
                "amount": float(r.amount) if r.amount is not None else None,
                "currency": r.currency,
                "paid_by_user_id": r.paid_by_user_id,
                "counterparty": r.counterparty,
                "description": r.description,
                "expense_category_id": r.expense_category_id,
                "storage_id": r.storage_id,
                "receipt_image_path": r.receipt_image_path,
                "created_by_user_id": r.created_by_user_id,
            }
            for r in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.put("/cash-expenses/{expense_id}")
async def update_cash_expense(
    expense_id: int,
    date_value: Optional[date] = None,
    amount: Optional[Decimal] = None,
    currency: Optional[str] = None,
    counterparty: Optional[str] = None,
    description: Optional[str] = None,
    expense_category_id: Optional[int] = None,
    storage_id: Optional[str] = None,
    db: Session = Depends(get_db_sqla),
    current_user: User = Depends(require_admin_user),
):
    cash = db.query(AccountingCashExpense).get(expense_id)
    if not cash:
        raise HTTPException(status_code=404, detail="Cash expense not found")

    old_values: Dict[str, Any] = {
        "date": cash.date,
        "amount": cash.amount,
        "currency": cash.currency,
        "counterparty": cash.counterparty,
        "description": cash.description,
        "expense_category_id": cash.expense_category_id,
        "storage_id": cash.storage_id,
    }

    if date_value is not None:
        cash.date = date_value
    if amount is not None:
        cash.amount = amount
    if currency is not None:
        cash.currency = currency
    if counterparty is not None:
        cash.counterparty = counterparty
    if description is not None:
        cash.description = description
    if expense_category_id is not None:
        cash.expense_category_id = expense_category_id
    if storage_id is not None:
        cash.storage_id = storage_id

    cash.updated_by_user_id = current_user.id

    txn = (
        db.query(AccountingTransaction)
        .filter(
            AccountingTransaction.source_type == "cash_manual",
            AccountingTransaction.source_id == cash.id,
        )
        .first()
    )

    if txn:
        fields_to_check = ["date", "amount", "expense_category_id", "storage_id"]
        for field in fields_to_check:
            old_val = old_values.get(field)
            new_val = getattr(cash, field) if hasattr(cash, field) else getattr(txn, field)
            if field == "amount":
                txn.amount = abs(cash.amount)
                new_val = txn.amount
            elif field == "date":
                txn.date = cash.date
                new_val = txn.date
            elif field == "expense_category_id":
                txn.expense_category_id = cash.expense_category_id
                new_val = txn.expense_category_id
            elif field == "storage_id":
                txn.storage_id = cash.storage_id
                new_val = txn.storage_id

            if str(old_val) != str(new_val):
                log = AccountingTransactionLog(
                    transaction_id=txn.id,
                    changed_by_user_id=current_user.id,
                    field_name=field,
                    old_value=str(old_val) if old_val is not None else None,
                    new_value=str(new_val) if new_val is not None else None,
                )
                db.add(log)

        txn.description = cash.description
        txn.updated_by_user_id = current_user.id

    db.commit()
    return {"ok": True}


# --- Unified transactions ---


@router.get("/transactions")
async def list_transactions(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    category_id: Optional[int] = Query(None, alias="category_id"),
    source_type: Optional[str] = None,
    storage_id: Optional[str] = None,
    is_personal: Optional[bool] = None,
    is_internal_transfer: Optional[bool] = None,
    direction_filter: Optional[str] = Query(None, alias="direction"),
    min_amount: Optional[Decimal] = None,
    max_amount: Optional[Decimal] = None,
    account_name: Optional[str] = None,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db_sqla),
    current_user: User = Depends(require_admin_user),
):
    query = db.query(AccountingTransaction)

    if date_from:
        query = query.filter(AccountingTransaction.date >= date_from)
    if date_to:
        query = query.filter(AccountingTransaction.date <= date_to)
    if category_id:
        query = query.filter(AccountingTransaction.expense_category_id == category_id)
    if source_type:
        query = query.filter(AccountingTransaction.source_type == source_type)
    if storage_id:
        query = query.filter(AccountingTransaction.storage_id == storage_id)
    if is_personal is not None:
        query = query.filter(AccountingTransaction.is_personal == is_personal)
    if is_internal_transfer is not None:
        query = query.filter(AccountingTransaction.is_internal_transfer == is_internal_transfer)
    if direction_filter in {"in", "out"}:
        query = query.filter(AccountingTransaction.direction == direction_filter)
    if min_amount is not None:
        query = query.filter(AccountingTransaction.amount >= min_amount)
    if max_amount is not None:
        query = query.filter(AccountingTransaction.amount <= max_amount)
    if account_name:
        like = f"%{account_name}%"
        query = query.filter(AccountingTransaction.account_name.ilike(like))

    total = query.count()

    # Aggregate totals for ledger-style overview (Total In / Total Out / Net)
    sums = (
        db.query(
            func.sum(func.case([(AccountingTransaction.direction == "in", AccountingTransaction.amount)], else_=0)),
            func.sum(func.case([(AccountingTransaction.direction == "out", AccountingTransaction.amount)], else_=0)),
        )
        .select_from(AccountingTransaction)
        .filter(query.whereclause if query.whereclause is not None else True)
        .one()
    )
    total_in = sums[0] or Decimal("0")
    total_out = sums[1] or Decimal("0")
    net = (total_in or Decimal("0")) - (total_out or Decimal("0"))

    rows = (
        query.order_by(AccountingTransaction.date.desc(), AccountingTransaction.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return {
        "rows": [
            {
                "id": r.id,
                "date": r.date.isoformat() if r.date else None,
                "amount": float(r.amount) if r.amount is not None else None,
                "direction": r.direction,
                "source_type": r.source_type,
                "source_id": r.source_id,
                "account_name": r.account_name,
                "account_id": r.account_id,
                "counterparty": r.counterparty,
                "description": r.description,
                "expense_category_id": r.expense_category_id,
                "subcategory": r.subcategory,
                "storage_id": r.storage_id,
                "linked_object_type": r.linked_object_type,
                "linked_object_id": r.linked_object_id,
                "is_personal": r.is_personal,
                "is_internal_transfer": r.is_internal_transfer,
            }
            for r in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
        "total_in": float(total_in),
        "total_out": float(total_out),
        "net": float(net),
    }


@router.put("/transactions/{transaction_id}")
async def update_transaction(
    transaction_id: int,
    expense_category_id: Optional[int] = None,
    is_personal: Optional[bool] = None,
    is_internal_transfer: Optional[bool] = None,
    storage_id: Optional[str] = None,
    db: Session = Depends(get_db_sqla),
    current_user: User = Depends(require_admin_user),
):
    txn = db.query(AccountingTransaction).get(transaction_id)
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")

    changes: List[AccountingTransactionLog] = []

    def _log(field: str, old: Any, new: Any) -> None:
        if str(old) == str(new):
            return
        changes.append(
            AccountingTransactionLog(
                transaction_id=txn.id,
                changed_by_user_id=current_user.id,
                field_name=field,
                old_value=str(old) if old is not None else None,
                new_value=str(new) if new is not None else None,
            )
        )

    if expense_category_id is not None:
        _log("expense_category_id", txn.expense_category_id, expense_category_id)
        txn.expense_category_id = expense_category_id
    if is_personal is not None:
        _log("is_personal", txn.is_personal, is_personal)
        txn.is_personal = is_personal
    if is_internal_transfer is not None:
        _log("is_internal_transfer", txn.is_internal_transfer, is_internal_transfer)
        txn.is_internal_transfer = is_internal_transfer
    if storage_id is not None:
        _log("storage_id", txn.storage_id, storage_id)
        txn.storage_id = storage_id

    txn.updated_by_user_id = current_user.id

    for log in changes:
        db.add(log)

    db.commit()
    return {"ok": True}
