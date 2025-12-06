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

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, status, BackgroundTasks, Body
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
    User,
)

from app.services.admin_auth import require_admin_user
from app.utils.logger import logger

from app.services.accounting_parsers.csv_parser import parse_csv_bytes
from app.services.accounting_parsers.xlsx_parser import parse_xlsx_bytes
from app.services.accounting_parsers.pdf_parser import parse_pdf_bytes, parse_pdf_with_metadata
from app.services.accounting_rules_engine import apply_rules_to_bank_rows
from app.services.supabase_storage import upload_file_to_storage, delete_files

# Bank Statement v1.0 imports
from app.services.accounting_parsers.import_service import (
    import_bank_statement_json,
    import_td_pdf_bytes,
    get_supported_banks,
    validate_json_format,
    ImportResult,
)
from app.services.accounting_parsers.bank_statement_schema import (
    BankStatementV1,
    validate_bank_statement_json,
)



def _log_process(db: Session, stmt_id: int, message: str, level: str = "INFO", details: Optional[Dict[str, Any]] = None):
    try:
        log_entry = AccountingProcessLog(
            bank_statement_id=stmt_id,
            message=message,
            level=level,
            details=details
        )
        db.add(log_entry)
        # We don't commit here to avoid breaking the main transaction flow, 
        # but in a production system we might want a separate db session for logs 
        # to persist them even on rollback.
    except Exception as e:
        logger.error(f"Failed to write process log: {e}")


async def process_bank_statement_background(statement_id: int, file_bytes: bytes, file_name: str, content_type: str, user_id: str):
    """Background task to parse the file and update the statement."""
    logger.info(f"Starting background processing for statement {statement_id}...")
    
    # New DB session for the background task
    db = SessionLocal()
    try:
        stmt = db.query(AccountingBankStatement).get(statement_id)
        if not stmt:
            logger.error(f"Statement {statement_id} not found in background task.")
            return

        ext = (file_name or "").lower()
        is_csv_like = ext.endswith(".csv") or ext.endswith(".txt")
        is_xlsx_like = ext.endswith(".xlsx") or ext.endswith(".xls")
        is_pdf_like = ext.endswith(".pdf") or "pdf" in content_type

        # Default fallback metadata
        extracted_bank_name = stmt.bank_name
        extracted_account_last4 = stmt.account_last4
        extracted_currency = stmt.currency
        extracted_period_start = stmt.statement_period_start
        extracted_period_end = stmt.statement_period_end
        
        parsed_transactions = []
        pdf_raw_response: Optional[Dict[str, Any]] = None
        parsing_error = None
        new_rows = []

        if is_pdf_like:
            try:
                # This is the slow part!
                pdf_result = await parse_pdf_with_metadata(file_bytes)
                
                # Update metadata if not manually set
                if stmt.bank_name == "Unknown Bank" and pdf_result.bank_name:
                    extracted_bank_name = pdf_result.bank_name
                if not stmt.account_last4 and pdf_result.account_last4:
                    extracted_account_last4 = pdf_result.account_last4
                if not stmt.currency or stmt.currency == "USD":
                    if pdf_result.currency:
                        extracted_currency = pdf_result.currency
                
                # Period handling
                if not stmt.statement_period_start and pdf_result.period_start:
                    try:
                        extracted_period_start = date.fromisoformat(pdf_result.period_start)
                    except Exception:
                        pass
                if not stmt.statement_period_end and pdf_result.period_end:
                    try:
                        extracted_period_end = date.fromisoformat(pdf_result.period_end)
                    except Exception:
                        pass
                
                parsed_transactions = pdf_result.transactions
                pdf_raw_response = pdf_result.raw_json
                
                # Save raw response for debugging
                stmt.raw_openai_response = pdf_raw_response

                _log_process(db, stmt.id, f"PDF processed by OpenAI. Found {len(parsed_transactions)} transactions.", details={"bank": extracted_bank_name})
                logger.info(f"PDF parsed for stmt {statement_id}: {len(parsed_transactions)} txs")

            except Exception as e:
                parsing_error = str(e)
                logger.error(f"Failed to parse PDF bank statement {statement_id}: {e}")
                stmt.status = "error_parsing_failed"
                stmt.error_message = str(e)
                _log_process(db, stmt.id, "Parsing Failed", level="ERROR", details={"error": str(e)})
                db.commit()
                return # Exit early on fatal parsing error
        
        elif is_csv_like or is_xlsx_like:
            try:
                parsed = parse_xlsx_bytes(file_bytes) if is_xlsx_like else parse_csv_bytes(file_bytes)
                parsed_transactions = parsed # Use same list
                _log_process(db, stmt.id, f"Spreadsheet parsed locally. Found {len(parsed_transactions)} rows.")
            except Exception as e:
                parsing_error = str(e)
                logger.error(f"Failed to parse spreadsheet {statement_id}: {e}")
                stmt.status = "error_parsing_failed"
                stmt.error_message = str(e)
                _log_process(db, stmt.id, "Parsing Failed", level="ERROR", details={"error": str(e)})
                db.commit()
                return

        # Common Row Creation Logic
        def _make_row_dedupe_key(row_data: Dict[str, Any], stmt_id: int) -> str:
            raw_str = f"{stmt_id}|{row_data.get('__index__')}|{row_data.get('date')}|{row_data.get('amount')}|{row_data.get('description')}"
            return hashlib.sha256(raw_str.encode('utf-8')).hexdigest()

        if parsed_transactions:
            for row in parsed_transactions:
                # Normalization logic (handles both PDF result dicts and CSV dicts)
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
                    or row.get("operation date")
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
                    currency=row.get("currency") or row.get("Currency") or extracted_currency or "USD",
                    parsed_status="auto_parsed",
                    match_status="unmatched",
                    dedupe_key=dedupe_key,
                    created_by_user_id=user_id,
                    updated_by_user_id=user_id,
                )
                db.add(db_row)
                new_rows.append(db_row)

            # Apply updates to Statement
            stmt.bank_name = extracted_bank_name
            stmt.account_last4 = extracted_account_last4
            stmt.currency = extracted_currency
            stmt.statement_period_start = extracted_period_start
            stmt.statement_period_end = extracted_period_end
            
            if pdf_raw_response:
                stmt.raw_openai_response = pdf_raw_response

            stmt.status = "parsed"
            _log_process(db, stmt.id, "Parsing Completed", details={"total_rows": len(new_rows)})

        else:
             # No rows found
             stmt.status = "uploaded"
             message = "No transactions extracted."
             stmt.error_message = message if not stmt.error_message else stmt.error_message
             _log_process(db, stmt.id, "Parsing Finished - No Rows", level="WARNING")

        # Apply auto-categorization rules
        if new_rows:
            apply_rules_to_bank_rows(db, new_rows)
            _log_process(db, stmt.id, "Auto-categorization rules applied.")

        db.commit()
    
    except Exception as e:
        logger.error(f"Fatal error in background statement processing: {e}")
        try:
            # Try to recover session to update status
            db.rollback()
            stmt = db.query(AccountingBankStatement).get(statement_id)
            if stmt:
                 stmt.status = "error_internal"
                 stmt.error_message = f"System error: {str(e)}"
                 db.commit()
        except:
            pass
    finally:
        db.close()
        logger.info(f"Background task finished for statement {statement_id}")


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


@router.post("/bank-statements", status_code=status.HTTP_202_ACCEPTED)
async def upload_bank_statement(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    bank_name: Optional[str] = Form(None),
    account_last4: Optional[str] = Form(None),
    currency: Optional[str] = Form(None),
    statement_period_start: Optional[date] = Form(None),
    statement_period_end: Optional[date] = Form(None),
    db: Session = Depends(get_db_sqla),
    current_user: User = Depends(require_admin_user),
):
    """Upload a bank statement file (CSV, XLSX, or PDF) and process it in the background.

    For PDF files, processing via OpenAI can take a while, so we return 202 immediately.
    Clients should poll the statements list to see the status update from 'processing' to 'parsed'.
    """
    logger.info(f"Upload request received for: {file.filename}")
    
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
        # Always allow re-processing of the same file. Delete the old one.
        logger.info(f"Duplicate file hash {file_hash} found (ID {existing_stmt.id}). Deleting and re-processing.")
        db.delete(existing_stmt)
        db.flush()

    # 3. Create new statement record
    stmt = AccountingBankStatement(
        bank_name=bank_name or "Unknown Bank",
        account_last4=account_last4,
        currency=currency or "USD",
        statement_period_start=statement_period_start,
        statement_period_end=statement_period_end,
        status="processing",
        file_hash=file_hash,
        created_by_user_id=current_user.id,
        updated_by_user_id=current_user.id,
    )
    db.add(stmt)
    db.flush()  # get ID
    
    # Upload to Supabase Storage
    storage_filename = f"{stmt.id}/{file.filename}"
    storage_path = ""
    try:
        logger.info(f"Uploading statement {stmt.id} to storage bucket 'bank-statements'")
        uploaded_path = upload_file_to_storage("bank-statements", storage_filename, file_bytes, file.content_type or "application/octet-stream")
        storage_path = uploaded_path
    except Exception as e:
        logger.error(f"Failed to upload bank statement file to Supabase: {e}")
        # Assuming we want to FAIL the request if we can't archive the file securely
        raise HTTPException(status_code=500, detail="Failed to upload file to secure storage.")

    # Update statement with storage info
    stmt.supabase_bucket = "bank-statements"
    stmt.supabase_path = storage_path
    db.add(stmt)
    
    _log_process(db, stmt.id, "Statement initialized.", details={"original_filename": file.filename, "file_hash": file_hash})
    _log_process(db, stmt.id, f"File uploaded to Supabase: {storage_path}")

    # Track file record
    stmt_file = AccountingBankStatementFile(
        bank_statement_id=stmt.id,
        file_type=file.content_type or "",
        storage_path=storage_path,
        uploaded_by_user_id=current_user.id,
    )
    db.add(stmt_file)
    db.commit()
    db.refresh(stmt)

    # 4. Trigger Background Processing
    background_tasks.add_task(
        process_bank_statement_background,
        statement_id=stmt.id,
        file_bytes=file_bytes,
        file_name=file.filename,
        content_type=file.content_type or "",
        user_id=current_user.id
    )

    return {
        "id": stmt.id, 
        "status": "processing",
        "message": "Statement uploaded. Parsing started in background.",
        "bank_name": stmt.bank_name,
        "rows_count": 0
    }


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
    return rows


@router.post("/bank-statements/{statement_id}/commit-rows")
async def commit_bank_rows_to_transactions(
    statement_id: int,
    row_ids: Optional[List[int]] = Query(None, alias="row_ids"),
    commit_all_non_ignored: bool = Body(False),
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
    if commit_all_non_ignored:
        rows_q = rows_q.filter(AccountingBankRow.parsed_status != "ignored")
    elif row_ids:
        rows_q = rows_q.filter(AccountingBankRow.id.in_(row_ids))
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

        txn = AccountingTransaction(
            date=r.operation_date or r.posting_date or stmt.statement_period_start or dt.date.today(),
            amount=amount,
            direction=direction,
            source_type=r.source_type or "bank_statement",
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
# Bank Statement v1.0 — Internal Parser Endpoints (NO OpenAI)
# ============================================================================

@router.get("/bank-statements/supported-banks")
async def list_supported_banks(
    current_user: User = Depends(require_admin_user),
):
    """Get list of banks supported for internal PDF parsing (no OpenAI)."""
    return {
        "banks": get_supported_banks(),
        "json_schema_version": "1.0",
    }


@router.post("/bank-statements/import-json")
async def import_json_bank_statement(
    db: Session = Depends(get_db_sqla),
    current_user: User = Depends(require_admin_user),
    file: UploadFile = File(None),
    json_body: Optional[Dict[str, Any]] = None,
):
    """
    Import a Bank Statement v1.0 JSON file or request body.
    
    This endpoint accepts the canonical Bank Statement v1.0 JSON format.
    It uses deterministic rule-based classification (NO OpenAI).
    
    You can either:
    - Upload a .json file via multipart form
    - POST the JSON directly in the request body
    
    The endpoint:
    1. Validates the JSON against BankStatementV1 schema
    2. Checks for duplicate statements (idempotency by bank+account+period)
    3. Creates AccountingBankStatement and AccountingBankRow records
    4. Applies rule-based classification
    5. Verifies totals against summary
    6. Saves the original JSON file to Supabase storage
    
    Returns structured result with counts and status.
    """
    import json as json_module
    
    # Get JSON data from file or body
    statement_data: Optional[Dict[str, Any]] = None
    file_bytes: Optional[bytes] = None
    original_filename: Optional[str] = None
    
    if file and file.filename:
        # Read JSON from uploaded file
        try:
            file_bytes = await file.read()
            statement_data = json_module.loads(file_bytes.decode('utf-8'))
            original_filename = file.filename
        except json_module.JSONDecodeError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid JSON file: {str(e)}"
            )
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to read file: {str(e)}"
            )
    elif json_body:
        statement_data = json_body
        # Generate JSON bytes from body for storage
        file_bytes = json_module.dumps(statement_data, indent=2).encode('utf-8')
        original_filename = "statement.json"
    
    if not statement_data:
        raise HTTPException(
            status_code=400,
            detail="Please provide either a JSON file or JSON body"
        )
    
    # Import the statement
    result = import_bank_statement_json(
        db=db,
        statement_data=statement_data,
        user_id=current_user.id,
        source_type="JSON_UPLOAD",
    )
    
    if not result.success and result.status != "DUPLICATE":
        raise HTTPException(
            status_code=400,
            detail=result.error_message or "Import failed"
        )
    
    # Save the original JSON file to storage and create file record
    if result.success and result.statement_id and file_bytes:
        try:
            # Upload JSON to storage: bank-statements/{statement_id}/{filename}
            storage_filename = f"{result.statement_id}/{original_filename}"
            storage_path = upload_file_to_storage(
                "bank-statements",
                storage_filename,
                file_bytes,
                "application/json"
            )
            
            # Update statement with storage path
            stmt = db.query(AccountingBankStatement).get(result.statement_id)
            if stmt:
                stmt.supabase_bucket = "bank-statements"
                stmt.supabase_path = storage_path
                
                # Create file record
                stmt_file = AccountingBankStatementFile(
                    bank_statement_id=result.statement_id,
                    file_type="application/json",
                    storage_path=storage_path,
                    uploaded_by_user_id=current_user.id,
                )
                db.add(stmt_file)
                db.commit()
                
                logger.info(f"Saved JSON file for statement {result.statement_id} to {storage_path}")
        except Exception as e:
            logger.error(f"Failed to save JSON file to storage: {e}")
            # Don't fail the import if storage fails - statement is already imported
    
    return result.to_dict()


@router.post("/bank-statements/import-json-body")
async def import_json_bank_statement_body(
    statement_data: Dict[str, Any],
    db: Session = Depends(get_db_sqla),
    current_user: User = Depends(require_admin_user),
):
    """
    Import a Bank Statement v1.0 JSON from request body.
    
    This is an alternative endpoint that accepts JSON directly in the body
    (easier to use from code/scripts).
    """
    result = import_bank_statement_json(
        db=db,
        statement_data=statement_data,
        user_id=current_user.id,
        source_type="JSON_UPLOAD",
    )
    
    if not result.success and result.status != "DUPLICATE":
        raise HTTPException(
            status_code=400,
            detail=result.error_message or "Import failed"
        )
    
    return result.to_dict()


@router.post("/bank-statements/upload-pdf-td")
async def upload_td_pdf_statement(
    file: UploadFile = File(...),
    db: Session = Depends(get_db_sqla),
    current_user: User = Depends(require_admin_user),
):
    """
    Upload a TD Bank PDF statement and parse it using internal parser (NO OpenAI).
    
    This endpoint:
    1. Validates the file is a PDF
    2. Parses using deterministic TD Bank PDF parser
    3. Converts to Bank Statement v1.0 JSON
    4. Imports via standard JSON import pipeline
    5. Stores the original PDF in Supabase
    
    Use this for TD Bank statements when you want fast, predictable parsing
    without AI costs.
    """
    # Validate file type
    if not file.filename or not file.filename.lower().endswith('.pdf'):
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are accepted for TD Bank parser"
        )
    
    # Read file
    file_bytes = await file.read()
    
    # Validate file size (max 10MB)
    if len(file_bytes) > 10 * 1024 * 1024:
        raise HTTPException(
            status_code=400,
            detail="File too large. Maximum size is 10MB."
        )
    
    # Parse and import first (need statement_id for storage path)
    result = import_td_pdf_bytes(
        db=db,
        pdf_bytes=file_bytes,
        user_id=current_user.id,
        source_filename=file.filename,
        storage_path=None,  # Will set after upload
    )
    
    if not result.success:
        raise HTTPException(
            status_code=400,
            detail=result.error_message or "TD PDF parsing failed"
        )
    
    # Upload PDF to storage and create file record
    if result.statement_id:
        try:
            # Upload to consistent path: bank-statements/{statement_id}/{filename}
            storage_filename = f"{result.statement_id}/{file.filename}"
            storage_path = upload_file_to_storage(
                "bank-statements", 
                storage_filename, 
                file_bytes, 
                "application/pdf"
            )
            
            # Update statement with storage path
            stmt = db.query(AccountingBankStatement).get(result.statement_id)
            if stmt:
                stmt.supabase_bucket = "bank-statements"
                stmt.supabase_path = storage_path
                
                # Create file record
                stmt_file = AccountingBankStatementFile(
                    bank_statement_id=result.statement_id,
                    file_type="application/pdf",
                    storage_path=storage_path,
                    uploaded_by_user_id=current_user.id,
                )
                db.add(stmt_file)
                db.commit()
                
                logger.info(f"Saved TD PDF for statement {result.statement_id} to {storage_path}")
        except Exception as e:
            logger.error(f"Failed to save TD PDF to storage: {e}")
            # Don't fail the import if storage fails - statement is already imported
    
    return result.to_dict()


@router.post("/bank-statements/validate-json")
async def validate_json_schema(
    statement_data: Dict[str, Any],
    current_user: User = Depends(require_admin_user),
):
    """
    Validate a JSON object against Bank Statement v1.0 schema.
    
    Does NOT import the data, just validates the structure.
    Useful for testing JSON before actual import.
    """
    is_valid, error_message = validate_json_format(statement_data)
    
    return {
        "valid": is_valid,
        "error": error_message,
        "schema_version": "1.0",
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
