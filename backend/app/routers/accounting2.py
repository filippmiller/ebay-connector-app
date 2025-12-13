from __future__ import annotations

from typing import Optional, List, Dict, Any
from datetime import date
from decimal import Decimal
import json
import hashlib

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, Body
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.models_sqlalchemy import get_db as get_db_sqla
from app.models_sqlalchemy.models import (
    AccountingBankStatement,
    AccountingBankRow,
    AccountingBankStatementFile,
    AccountingTransaction,
    User,
)
from app.services.admin_auth import require_admin_user
from app.services.accounting_parsers.td_bank_parser import parse_pdf_by_bank_code
from app.services.accounting_parsers.transaction_classifier import classify_transaction
from app.services.accounting_parsers.xlsx_td_export_parser import parse_td_xlsx_export
from app.services.supabase_storage import upload_file_to_storage, get_signed_url, delete_file
from app.utils.logger import logger


router = APIRouter(prefix="/api/accounting2", tags=["accounting2"])


class ManualPastedTransaction(BaseModel):
    date: date
    description: str
    direction: str  # 'debit' or 'credit'
    amount: Decimal


class ManualPastedStatement(BaseModel):
    bank_name: str
    bank_code: Optional[str] = None
    account_last4: Optional[str] = None
    currency: str = "USD"
    period_start: date
    period_end: date
    opening_balance: Optional[Decimal] = None
    closing_balance: Optional[Decimal] = None
    transactions: List[ManualPastedTransaction]


def _ensure_statement_owner(db: Session, statement_id: int) -> AccountingBankStatement:
    stmt = db.query(AccountingBankStatement).get(statement_id)
    if not stmt:
        raise HTTPException(status_code=404, detail="Bank statement not found")
    return stmt


@router.post("/bank-statements/manual-from-text")
async def create_manual_bank_statement_from_text(
    payload: ManualPastedStatement,
    db: Session = Depends(get_db_sqla),
    current_user: User = Depends(require_admin_user),
) -> Dict[str, Any]:
    """Create a bank statement and rows from manually pasted text.

    This bypasses PDF parsing and lets the user define rows explicitly.
    """
    if not payload.transactions:
        raise HTTPException(status_code=400, detail="At least one transaction is required")

    stmt = AccountingBankStatement(
        bank_name=payload.bank_name,
        bank_code=payload.bank_code or "MANUAL",
        account_last4=payload.account_last4,
        currency=payload.currency,
        statement_period_start=payload.period_start,
        statement_period_end=payload.period_end,
        opening_balance=payload.opening_balance,
        closing_balance=payload.closing_balance,
        status="parsed",
        source_type="MANUAL_PASTE",
        created_by_user_id=current_user.id,
    )
    db.add(stmt)
    db.flush()

    total_rows = 0
    for t in payload.transactions:
        direction = (t.direction or "credit").lower()
        signed_amount = Decimal(t.amount)
        if direction == "debit":
            signed_amount = -abs(signed_amount)
        else:
            signed_amount = abs(signed_amount)

        bank_row = AccountingBankRow(
            bank_statement_id=stmt.id,
            row_index=None,
            operation_date=t.date,
            posting_date=t.date,
            description_raw=t.description,
            description_clean=t.description,
            amount=signed_amount,
            balance_after=None,
            currency=payload.currency,
            parsed_status="manual_parsed",
            match_status="unmatched",
            created_by_user_id=current_user.id,
        )
        db.add(bank_row)
        total_rows += 1

    db.commit()

    return {
        "id": stmt.id,
        "status": stmt.status,
        "bank_name": stmt.bank_name,
        "account_last4": stmt.account_last4,
        "currency": stmt.currency,
        "period_start": payload.period_start.isoformat(),
        "period_end": payload.period_end.isoformat(),
        "rows_count": total_rows,
        "message": "Manual statement created successfully.",
    }


@router.post("/bank-statements/upload")
async def upload_bank_statement_v2(
    file: UploadFile = File(...),
    bank_code: str = Form("TD"),
    db: Session = Depends(get_db_sqla),
    current_user: User = Depends(require_admin_user),
) -> Dict[str, Any]:
    """Upload a bank statement PDF and stage parsed transactions in `transaction_spending`.

    This is the Accounting 2 entrypoint:
    - Parses PDF via internal parser (no OpenAI).
    - Creates AccountingBankStatement with status 'staged'.
    - Uploads original PDF to Supabase bucket `accounting_bank_statements`.
    - Writes parsed transactions into `public.transaction_spending` ONLY (no ledger yet).
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="File name is required")

    file_bytes = await file.read()
    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    # 1) Parse PDF into canonical BankStatementV1
    try:
        statement = parse_pdf_by_bank_code(bank_code, file_bytes, file.filename)
    except Exception as e:
        logger.error(f"Accounting2: failed to parse PDF: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"Failed to parse PDF: {e}")

    meta = statement.statement_metadata
    summary = statement.statement_summary

    # 2) Create AccountingBankStatement in 'staged' status
    stmt = AccountingBankStatement(
        bank_name=meta.bank_name,
        bank_code=bank_code,
        account_last4=meta.primary_account_number[-4:] if meta.primary_account_number and len(meta.primary_account_number) >= 4 else meta.primary_account_number,
        currency=meta.currency,
        statement_period_start=meta.statement_period_start,
        statement_period_end=meta.statement_period_end,
        opening_balance=summary.beginning_balance,
        closing_balance=summary.ending_balance,
        status="staged",
        source_type="PDF_TD_V2",
        raw_json=statement.model_dump(mode="json"),
        created_by_user_id=current_user.id,
    )
    db.add(stmt)
    db.flush()  # get stmt.id

    # 3) Upload original PDF to bank-statements bucket used for all bank files
    storage_filename = f"{stmt.id}/{file.filename}"
    try:
        storage_path = upload_file_to_storage(
            "bank-statements",
            storage_filename,
            file_bytes,
            file.content_type or "application/pdf",
        )
        stmt.supabase_bucket = "bank-statements"
        stmt.supabase_path = storage_path
    except Exception as e:
        logger.error(f"Accounting2: failed to upload PDF to Supabase: {e}")
        raise HTTPException(status_code=500, detail="Failed to upload file to storage")

    # 4) Stage transactions into transaction_spending
    logger.info(f"Accounting2: staging {len(statement.transactions)} transactions for statement_id={stmt.id}")
    total_rows = 0
    for txn in statement.transactions:
        # Apply classification rules so preview shows meaningful info
        group, code, status = classify_transaction(txn, bank_code)
        txn.accounting_group = group
        txn.classification = code
        txn.status = status

        # Basic cleanup of description: ensure space after commas
        desc = txn.description or ""
        desc_clean = ", ".join(part.strip() for part in desc.split(",")) if "," in desc else desc

        amount = txn.amount
        balance_after = txn.balance_after
        op_date: Optional[date] = txn.posting_date
        currency = meta.currency

        try:
            db.execute(
                text(
                    """
                    insert into public.transaction_spending (
                        bank_statement_id,
                        operation_date,
                        description_raw,
                        description_clean,
                        amount,
                        balance_after,
                        currency,
                        bank_section,
                        raw_transaction_json
                    ) values (
                        :bank_statement_id,
                        :operation_date,
                        :description_raw,
                        :description_clean,
                        :amount,
                        :balance_after,
                        :currency,
                        :bank_section,
                        :raw_transaction_json
                    )
                    """
                ),
                {
                    "bank_statement_id": stmt.id,
                    "operation_date": op_date,
                    "description_raw": txn.description,
                    "description_clean": desc_clean,
                    "amount": float(amount) if amount is not None else None,
                    "balance_after": float(balance_after) if balance_after is not None else None,
                    "currency": currency,
                    "bank_section": txn.bank_section.value if txn.bank_section else None,
                    "raw_transaction_json": json.dumps(txn.model_dump(mode="json")),
                },
            )
            total_rows += 1
        except Exception as e:
            logger.error(f"Accounting2: Failed to insert transaction {txn.id}: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to insert transaction: {e}")

    try:
        db.commit()
    except Exception as e:
        logger.error(f"Accounting2: Failed to commit transactions: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to commit transactions: {e}")
    logger.info(f"Accounting2: committed {total_rows} transactions for statement_id={stmt.id}")
    
    # Verify rows were actually saved
    verify_res = db.execute(
        text("SELECT COUNT(*) FROM public.transaction_spending WHERE bank_statement_id = :sid"),
        {"sid": stmt.id}
    )
    actual_count = verify_res.scalar()
    logger.info(f"Accounting2: verification count = {actual_count} for statement_id={stmt.id}")

    return {
        "id": stmt.id,
        "status": stmt.status,
        "bank_name": stmt.bank_name,
        "account_last4": stmt.account_last4,
        "currency": stmt.currency,
        "period_start": meta.statement_period_start.isoformat() if meta.statement_period_start else None,
        "period_end": meta.statement_period_end.isoformat() if meta.statement_period_end else None,
        "rows_count": total_rows,
        "message": "Statement uploaded and transactions staged for review.",
    }


@router.post("/bank-statements/upload-xlsx")
async def upload_bank_statement_xlsx_manual(
    file: UploadFile = File(...),
    bank_name: str = Form("TD Bank"),
    bank_code: str = Form("TD"),
    currency: str = Form("USD"),
    db: Session = Depends(get_db_sqla),
    current_user: User = Depends(require_admin_user),
) -> Dict[str, Any]:
    """Upload TD-style XLSX export and import directly into ledger as manual transactions.

    Unlike the PDF flow (/upload), this endpoint:
    - Creates AccountingBankStatement with source_type=MANUAL_XLSX and status='parsed'
    - Inserts AccountingBankRow rows
    - Inserts AccountingTransaction rows directly with source_type='manual' and source_id=<statement_id>

    Idempotency: dedupes by SHA256(file_bytes) stored in AccountingBankStatement.file_hash.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="File name is required")

    if not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Only .xlsx files are supported for XLSX import")

    file_bytes = await file.read()
    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    file_hash = hashlib.sha256(file_bytes).hexdigest()

    existing_stmt = (
        db.query(AccountingBankStatement)
        .filter(AccountingBankStatement.file_hash == file_hash)
        .order_by(AccountingBankStatement.id.desc())
        .first()
    )
    if existing_stmt:
        return {
            "id": existing_stmt.id,
            "status": existing_stmt.status,
            "bank_name": existing_stmt.bank_name,
            "account_last4": existing_stmt.account_last4,
            "currency": existing_stmt.currency,
            "period_start": existing_stmt.statement_period_start.isoformat() if existing_stmt.statement_period_start else None,
            "period_end": existing_stmt.statement_period_end.isoformat() if existing_stmt.statement_period_end else None,
            "rows_count": None,
            "message": "This XLSX file was already imported (file_hash match).",
            "duplicate": True,
        }

    # Parse
    try:
        rows = parse_td_xlsx_export(file_bytes)
    except Exception as e:
        logger.error(f"Accounting2 XLSX: failed to parse: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"Failed to parse XLSX: {e}")

    if not rows:
        raise HTTPException(status_code=400, detail="No transactions found in XLSX")

    period_start = min(r.posting_date for r in rows)
    period_end = max(r.posting_date for r in rows)

    account_number = next((r.account_number for r in rows if r.account_number), None) or ""
    account_last4 = account_number[-4:] if len(account_number) >= 4 else (account_number or None)

    statement_hash_key = f"{bank_code}|{account_number}|{period_start.isoformat()}|{period_end.isoformat()}"
    statement_hash = hashlib.sha256(statement_hash_key.encode()).hexdigest()

    total_credit = sum((r.amount_abs for r in rows if r.direction_ledger == "in"), Decimal("0"))
    total_debit = sum((r.amount_abs for r in rows if r.direction_ledger == "out"), Decimal("0"))

    stmt = AccountingBankStatement(
        bank_name=bank_name,
        bank_code=bank_code,
        account_last4=account_last4,
        currency=currency,
        statement_period_start=period_start,
        statement_period_end=period_end,
        opening_balance=None,
        closing_balance=None,
        total_credit=total_credit,
        total_debit=total_debit,
        status="parsed",
        file_hash=file_hash,
        statement_hash=statement_hash,
        source_type="MANUAL_XLSX",
        raw_json={
            "source": "manual_xlsx",
            "filename": file.filename,
            "file_hash": file_hash,
        },
        created_by_user_id=current_user.id,
        updated_by_user_id=current_user.id,
    )
    db.add(stmt)
    db.flush()

    statement_id = int(stmt.id)

    inserted_rows = 0
    inserted_ledger = 0

    CHUNK = 500
    for i in range(0, len(rows), CHUNK):
        chunk = rows[i : i + CHUNK]

        bank_rows: list[AccountingBankRow] = []
        for r in chunk:
            raw_txn = {
                "source": "manual_xlsx",
                "source_file": file.filename,
                "sheet": r.sheet_name,
                "excel_row": r.excel_row,
                "date": r.posting_date.isoformat(),
                "bank_rtn": r.bank_rtn,
                "account_number": r.account_number,
                "transaction_type_raw": r.transaction_type_raw,
                "description": r.description,
                "debit": str(r.debit) if r.debit is not None else None,
                "credit": str(r.credit) if r.credit is not None else None,
                "signed_amount": str(r.signed_amount),
                "check_number": r.check_number,
            }

            bank_rows.append(
                AccountingBankRow(
                    bank_statement_id=statement_id,
                    row_index=r.excel_row,
                    operation_date=r.posting_date,
                    posting_date=r.posting_date,
                    description_raw=r.description or "",
                    description_clean=r.description or "",
                    amount=r.signed_amount,
                    balance_after=None,
                    currency=currency,
                    parsed_status="manual_xlsx",
                    match_status="unmatched",
                    bank_code=bank_code,
                    bank_section=None,
                    bank_subtype=r.transaction_type_raw,
                    direction=r.direction_bank,
                    accounting_group=None,
                    classification=None,
                    classification_status="UNKNOWN",
                    check_number=r.check_number,
                    raw_transaction_json=raw_txn,
                    created_by_user_id=current_user.id,
                    updated_by_user_id=current_user.id,
                )
            )

        db.add_all(bank_rows)
        db.flush()

        ledger_txns: list[AccountingTransaction] = []
        for br, r in zip(bank_rows, chunk, strict=True):
            storage_id = f"manual_xlsx:{file.filename}:{r.sheet_name}:{r.excel_row}"
            ledger_txns.append(
                AccountingTransaction(
                    date=r.posting_date,
                    amount=r.amount_abs,
                    direction=r.direction_ledger,
                    source_type="manual",
                    source_id=statement_id,
                    bank_row_id=br.id,
                    account_name=(f"{bank_name} ****{account_last4}" if account_last4 else bank_name),
                    account_id=r.account_number,
                    counterparty=None,
                    description=r.description,
                    expense_category_id=None,
                    subcategory=r.transaction_type_raw,
                    storage_id=storage_id,
                    linked_object_type=None,
                    linked_object_id=None,
                    is_personal=False,
                    is_internal_transfer=False,
                    created_by_user_id=current_user.id,
                    updated_by_user_id=current_user.id,
                )
            )

        db.add_all(ledger_txns)
        db.flush()

        inserted_rows += len(bank_rows)
        inserted_ledger += len(ledger_txns)

    db.commit()

    return {
        "id": statement_id,
        "status": stmt.status,
        "bank_name": stmt.bank_name,
        "account_last4": stmt.account_last4,
        "currency": stmt.currency,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "rows_count": inserted_rows,
        "ledger_rows_count": inserted_ledger,
        "message": "XLSX imported and committed to ledger as manual transactions.",
    }


@router.get("/bank-statements/{statement_id}")
async def get_bank_statement_preview_summary(
    statement_id: int,
    db: Session = Depends(get_db_sqla),
    current_user: User = Depends(require_admin_user),
) -> Dict[str, Any]:
    """Return summary for Accounting 2 statement (using staged rows).

    Includes header fields from the parsed BankStatement JSON so the UI can
    render the TD-style ACCOUNT SUMMARY block.
    """
    stmt = _ensure_statement_owner(db, statement_id)

    # Count staged rows (transaction_spending) for this statement
    res = db.execute(
        text("select count(*) from public.transaction_spending where bank_statement_id = :sid"),
        {"sid": statement_id},
    )
    rows_count = int(res.scalar() or 0)

    account_summary: Dict[str, Any] | None = None
    if isinstance(stmt.raw_json, dict):
        raw_summary = stmt.raw_json.get("statement_summary")
        if isinstance(raw_summary, dict):
            account_summary = raw_summary

    return {
        "id": stmt.id,
        "bank_name": stmt.bank_name,
        "account_last4": stmt.account_last4,
        "currency": stmt.currency,
        "statement_period_start": stmt.statement_period_start,
        "statement_period_end": stmt.statement_period_end,
        "opening_balance": stmt.opening_balance,
        "closing_balance": stmt.closing_balance,
        "status": stmt.status,
        "created_at": stmt.created_at,
        "rows_count": rows_count,
        "account_summary": account_summary,
    }


@router.get("/bank-statements/{statement_id}/rows")
async def get_bank_statement_preview_rows(
    statement_id: int,
    db: Session = Depends(get_db_sqla),
    current_user: User = Depends(require_admin_user),
) -> Dict[str, Any]:
    """Return staged rows from transaction_spending for preview grid."""
    _ensure_statement_owner(db, statement_id)

    res = db.execute(
        text(
            """
            select
                id,
                operation_date,
                description_raw,
                description_clean,
                amount,
                balance_after,
                currency,
                bank_section
            from public.transaction_spending
            where bank_statement_id = :sid
            order by operation_date nulls first, id
            """
        ),
        {"sid": statement_id},
    )

    rows = [dict(r._mapping) for r in res]
    return {"rows": rows}


@router.post("/bank-statements/{statement_id}/approve")
async def approve_bank_statement(
    statement_id: int,
    db: Session = Depends(get_db_sqla),
    current_user: User = Depends(require_admin_user),
) -> Dict[str, Any]:
    """Approve staged transactions and move them into accounting_bank_row.

    Does **not** commit to ledger yet; that is still done via
    /api/accounting/bank-statements/{id}/commit-rows so Accounting 2 can
    reuse existing ledger commit logic.
    """
    stmt = _ensure_statement_owner(db, statement_id)
    logger.info(f"Accounting2: approve called for statement_id={statement_id}, status={stmt.status}")

    res = db.execute(
        text(
            """
            select
                id,
                operation_date,
                description_raw,
                description_clean,
                amount,
                balance_after,
                currency,
                bank_section,
                raw_transaction_json
            from public.transaction_spending
            where bank_statement_id = :sid
            order by operation_date nulls first, id
            """
        ),
        {"sid": statement_id},
    )
    staged_rows = list(res.mappings())
    logger.info(f"Accounting2: found {len(staged_rows)} staged rows for statement_id={statement_id}")
    
    if not staged_rows:
        # Debug: check if statement has raw_json with transactions
        tx_count = 0
        if isinstance(stmt.raw_json, dict):
            txns = stmt.raw_json.get("transactions", [])
            tx_count = len(txns) if isinstance(txns, list) else 0
        logger.warning(f"Accounting2: No staged rows but raw_json has {tx_count} transactions")
        raise HTTPException(
            status_code=400, 
            detail=f"No staged transactions to approve (statement has {tx_count} in raw_json but 0 in transaction_spending)"
        )

    inserted = 0
    new_bank_rows: List[AccountingBankRow] = []

    for r in staged_rows:
        op_date = r["operation_date"]
        desc_raw = r["description_raw"]
        desc_clean = r["description_clean"]
        amount = r["amount"]
        balance_after = r["balance_after"]
        currency = r["currency"]
        bank_section = r["bank_section"]
        raw_txn = r["raw_transaction_json"]

        # Extract additional fields from raw_transaction_json if available
        direction = None
        bank_subtype = None
        accounting_group = None
        classification = None
        if raw_txn:
            txn_data = raw_txn if isinstance(raw_txn, dict) else {}
            direction = txn_data.get("direction")
            bank_subtype = txn_data.get("bank_subtype")
            accounting_group = txn_data.get("accounting_group")
            classification = txn_data.get("classification")

        bank_row = AccountingBankRow(
            bank_statement_id=stmt.id,
            row_index=None,
            operation_date=op_date,
            posting_date=op_date,
            description_raw=desc_raw or "",
            description_clean=desc_clean,
            amount=Decimal(str(amount)) if amount is not None else Decimal("0"),
            balance_after=Decimal(str(balance_after)) if balance_after is not None else None,
            currency=currency or stmt.currency,
            parsed_status="auto_parsed",
            match_status="unmatched",
            bank_code="TD",
            bank_section=bank_section,
            bank_subtype=bank_subtype,
            direction=direction,
            accounting_group=accounting_group,
            classification=classification,
            raw_transaction_json=raw_txn,
            created_by_user_id=current_user.id,
        )
        db.add(bank_row)
        new_bank_rows.append(bank_row)
        inserted += 1

    # Mark statement as parsed and clear staging
    stmt.status = "parsed"

    db.execute(
        text("delete from public.transaction_spending where bank_statement_id = :sid"),
        {"sid": statement_id},
    )

    db.commit()

    return {
        "statement_id": stmt.id,
        "inserted_rows": inserted,
        "status": stmt.status,
    }


@router.post("/bank-statements/{statement_id}/reject")
async def reject_bank_statement(
    statement_id: int,
    db: Session = Depends(get_db_sqla),
    current_user: User = Depends(require_admin_user),
) -> Dict[str, Any]:
    """Reject a staged statement: delete staging rows, PDF, and the statement itself."""
    stmt = _ensure_statement_owner(db, statement_id)

    # Delete staged rows
    db.execute(
        text("delete from public.transaction_spending where bank_statement_id = :sid"),
        {"sid": statement_id},
    )

    # Delete PDF from storage if present
    if stmt.supabase_bucket and stmt.supabase_path:
        try:
            delete_file(stmt.supabase_bucket, stmt.supabase_path)
        except Exception as e:
            logger.error(f"Accounting2: failed to delete PDF from storage: {e}")

    db.delete(stmt)
    db.commit()

    return {"statement_id": statement_id, "status": "rejected"}


@router.get("/bank-statements/{statement_id}/pdf-url")
async def get_bank_statement_pdf_url(
    statement_id: int,
    db: Session = Depends(get_db_sqla),
    current_user: User = Depends(require_admin_user),
) -> Dict[str, Any]:
    """Return a signed URL for the original PDF in Supabase Storage.

    Backwards compatible:
    - New Accounting 2 statements store bucket/path on AccountingBankStatement.
    - Legacy statements use accounting_bank_statement_file rows in bucket "bank-statements".
    """
    stmt = _ensure_statement_owner(db, statement_id)

    bucket = stmt.supabase_bucket
    path = stmt.supabase_path

    if not path:
        # Fallback to legacy accounting_bank_statement_file table
        file_row: AccountingBankStatementFile | None = (
            db.query(AccountingBankStatementFile)
            .filter(AccountingBankStatementFile.bank_statement_id == statement_id)
            .order_by(AccountingBankStatementFile.id.asc())
            .first()
        )
        if not file_row:
            raise HTTPException(status_code=404, detail="No PDF stored for this statement")
        bucket = bucket or "bank-statements"
        path = file_row.storage_path

    # Default bucket if still not set
    if not bucket:
        bucket = "bank-statements"

    url = get_signed_url(bucket, path, expiry_seconds=3600)
    if not url:
        raise HTTPException(status_code=500, detail="Failed to generate signed URL")

    return {"url": url}
