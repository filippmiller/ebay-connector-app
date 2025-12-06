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

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, status, BackgroundTasks
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
    User,
)
from app.services.admin_auth import require_admin_user
from app.utils.logger import logger

from app.services.accounting_parsers.csv_parser import parse_csv_bytes
from app.services.accounting_parsers.xlsx_parser import parse_xlsx_bytes
from app.services.accounting_parsers.pdf_parser import parse_pdf_bytes, parse_pdf_with_metadata
from app.services.accounting_rules_engine import apply_rules_to_bank_rows
from app.services.supabase_storage import upload_file_to_storage


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


@router.delete("/bank-statements/{statement_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bank_statement(
    statement_id: int,
    db: Session = Depends(get_db_sqla),
    current_user: User = Depends(require_admin_user),
):
    stmt = db.query(AccountingBankStatement).get(statement_id)
    if not stmt:
        raise HTTPException(status_code=404, detail="Statement not found")
    
    # Rows and files should cascade if configured, but let's be explicit if needed
    db.delete(stmt)
    db.commit()
    return None


# --- Test endpoint ---

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
