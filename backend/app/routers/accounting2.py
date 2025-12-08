from __future__ import annotations

from typing import Optional, List, Dict, Any
from datetime import date
from decimal import Decimal
import json

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, Body
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.models_sqlalchemy import get_db as get_db_sqla
from app.models_sqlalchemy.models import (
    AccountingBankStatement,
    AccountingBankRow,
    AccountingBankStatementFile,
    User,
)
from app.services.admin_auth import require_admin_user
from app.services.accounting_parsers.td_bank_parser import parse_pdf_by_bank_code
from app.services.accounting_parsers.transaction_classifier import classify_transaction
from app.services.supabase_storage import upload_file_to_storage, get_signed_url, delete_file
from app.utils.logger import logger


router = APIRouter(prefix="/api/accounting2", tags=["accounting2"])


def _ensure_statement_owner(db: Session, statement_id: int) -> AccountingBankStatement:
    stmt = db.query(AccountingBankStatement).get(statement_id)
    if not stmt:
        raise HTTPException(status_code=404, detail="Bank statement not found")
    return stmt


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
                    raw_transaction_json
                ) values (
                    :bank_statement_id,
                    :operation_date,
                    :description_raw,
                    :description_clean,
                    :amount,
                    :balance_after,
                    :currency,
                    :raw_transaction_json
                )
                """
            ),
            {
                "bank_statement_id": stmt.id,
                "operation_date": op_date,
                "description_raw": txn.description,
                "description_clean": desc_clean,
                "amount": amount,
                "balance_after": balance_after,
                "currency": currency,
                "raw_transaction_json": json.dumps(txn.model_dump(mode="json")),
            },
        )
        total_rows += 1

    db.commit()

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


@router.get("/bank-statements/{statement_id}")
async def get_bank_statement_preview_summary(
    statement_id: int,
    db: Session = Depends(get_db_sqla),
    current_user: User = Depends(require_admin_user),
) -> Dict[str, Any]:
    """Return summary for Accounting 2 statement (using staged rows)."""
    stmt = _ensure_statement_owner(db, statement_id)

    # Count staged rows
    res = db.execute(
        text("select count(*) from public.transaction_spending where bank_statement_id = :sid"),
        {"sid": statement_id},
    )
    rows_count = int(res.scalar() or 0)

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
                currency
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
                raw_transaction_json
            from public.transaction_spending
            where bank_statement_id = :sid
            order by operation_date nulls first, id
            """
        ),
        {"sid": statement_id},
    )
    staged_rows = list(res.mappings())
    if not staged_rows:
        raise HTTPException(status_code=400, detail="No staged transactions to approve")

    inserted = 0
    new_bank_rows: List[AccountingBankRow] = []

    for r in staged_rows:
        op_date = r["operation_date"]
        desc_raw = r["description_raw"]
        desc_clean = r["description_clean"]
        amount = r["amount"]
        balance_after = r["balance_after"]
        currency = r["currency"]
        raw_txn = r["raw_transaction_json"]

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
