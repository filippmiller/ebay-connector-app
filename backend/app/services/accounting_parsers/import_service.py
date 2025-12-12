"""
Bank Statement Import Service — JSON Import Pipeline

This module provides the business logic for importing Bank Statement v1.0 JSON
into the database. It handles:
- Validation via Pydantic schema
- Idempotency (duplicate detection)
- Transaction storage with classification
- Summary verification

Entry points:
- import_bank_statement_json(): Import from parsed JSON
- import_td_pdf_bytes(): Import from TD Bank PDF (calls TD parser first)
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass

from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.models_sqlalchemy.models import (
    AccountingBankStatement,
    AccountingBankRow,
    AccountingProcessLog,
    AccountingBankStatementImportRun,
)
from app.utils.logger import logger

from .bank_statement_schema import (
    BankStatementV1,
    validate_bank_statement_json,
    BankStatementTransactionV1,
    TransactionStatus,
)
from .transaction_classifier import classify_transaction, get_classification_summary
from .td_bank_parser import parse_td_pdf_to_bank_statement_v1
from .json_adapter import validate_and_adapt_json, detect_and_adapt_json



# ============================================================================
# RESULT TYPES
# ============================================================================

@dataclass
class ImportResult:
    """Result of a bank statement import operation."""
    success: bool
    statement_id: Optional[int] = None
    status: str = "UNKNOWN"  # PARSED, DUPLICATE, ERROR, VERIFICATION_FAILED
    
    # Counts
    transactions_total: int = 0
    transactions_inserted: int = 0
    duplicates_skipped: int = 0
    classification_unknown: int = 0
    
    # Metadata
    bank_name: Optional[str] = None
    bank_code: Optional[str] = None
    account_number: Optional[str] = None
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    
    # Verification
    verification_passed: Optional[bool] = None
    verification_message: Optional[str] = None
    
    # Errors
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "success": self.success,
            "statement_id": self.statement_id,
            "status": self.status,
            "transactions_total": self.transactions_total,
            "transactions_inserted": self.transactions_inserted,
            "duplicates_skipped": self.duplicates_skipped,
            "classification_unknown": self.classification_unknown,
            "bank_name": self.bank_name,
            "bank_code": self.bank_code,
            "account_number": self.account_number,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "verification_passed": self.verification_passed,
            "verification_message": self.verification_message,
            "error_message": self.error_message,
        }


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _compute_statement_hash(
    bank_code: str,
    account_number: str,
    period_start: date,
    period_end: date
) -> str:
    """Compute a unique hash for idempotency checking."""
    key = f"{bank_code}|{account_number}|{period_start.isoformat()}|{period_end.isoformat()}"
    return hashlib.sha256(key.encode()).hexdigest()


def _compute_row_dedupe_key(
    statement_id: int,
    posting_date: date,
    amount: Decimal,
    description: str
) -> str:
    """Compute a unique hash for row-level deduplication."""
    # Normalize description: lowercase, collapse spaces
    desc_normalized = " ".join(description.lower().split())
    key = f"{statement_id}|{posting_date.isoformat()}|{amount}|{desc_normalized}"
    return hashlib.sha256(key.encode()).hexdigest()


def _log_process(
    db: Session,
    stmt_id: int,
    message: str,
    level: str = "INFO",
    details: Optional[Dict[str, Any]] = None
) -> None:
    """Log a process step for admin UI debugging."""
    log_entry = AccountingProcessLog(
        bank_statement_id=stmt_id,
        level=level,
        message=message,
        details=details,
    )
    db.add(log_entry)
    db.flush()


# ============================================================================
# MAIN IMPORT FUNCTIONS
# ============================================================================

def import_bank_statement_json(
    db: Session,
    statement_data: Dict[str, Any],
    user_id: str,
    source_type: str = "JSON_UPLOAD",
    source_pdf_path: Optional[str] = None,
) -> ImportResult:
    """
    Import a Bank Statement v1.0 JSON into the database.
    
    This is the main entry point for JSON imports. It:
    1. Validates the JSON against BankStatementV1 schema
    2. Checks for duplicate statements (idempotency)
    3. Creates AccountingBankStatement record
    4. Creates AccountingBankRow records for each transaction
    5. Applies rule-based classification
    6. Verifies totals against summary
    
    Args:
        db: SQLAlchemy session
        statement_data: Raw dict to validate as BankStatementV1
        user_id: ID of user performing import
        source_type: Source type (JSON_UPLOAD, PDF_TD, etc.)
        source_pdf_path: Optional path to source PDF in storage
        
    Returns:
        ImportResult with status and counts
    """
    try:
        # 1. Validate JSON (with auto-adaptation for different formats)
        logger.info("Validating Bank Statement JSON (with format detection)...")
        try:
            # Use adapter to handle ChatGPT and other formats
            statement = validate_and_adapt_json(statement_data)
        except Exception as e:
            logger.error(f"JSON validation failed: {e}")
            return ImportResult(
                success=False,
                status="ERROR",
                error_message=f"Invalid JSON schema: {str(e)}"
            )

        
        bank_code = statement.source.bank_code
        bank_name = statement.statement_metadata.bank_name
        account_number = statement.statement_metadata.primary_account_number
        period_start = statement.statement_metadata.statement_period_start
        period_end = statement.statement_metadata.statement_period_end
        
        logger.info(
            f"Importing: {bank_name} ({bank_code}) "
            f"Account {account_number}, "
            f"Period {period_start} to {period_end}"
        )
        
        # 2. Check for duplicate statement (idempotency)
        stmt_hash = _compute_statement_hash(bank_code, account_number, period_start, period_end)
        
        existing = db.query(AccountingBankStatement).filter(
            AccountingBankStatement.statement_hash == stmt_hash
        ).first()
        
        if existing:
            logger.info(f"Duplicate statement detected (ID: {existing.id})")
            return ImportResult(
                success=True,
                statement_id=existing.id,
                status="DUPLICATE",
                bank_name=bank_name,
                bank_code=bank_code,
                account_number=account_number,
                period_start=str(period_start),
                period_end=str(period_end),
                error_message="Statement already exists",
            )
        
        # 3. Create AccountingBankStatement record
        stmt = AccountingBankStatement(
            bank_name=bank_name,
            bank_code=bank_code,
            account_last4=account_number[-4:] if len(account_number) >= 4 else account_number,
            currency=statement.statement_metadata.currency,
            statement_period_start=period_start,
            statement_period_end=period_end,
            opening_balance=statement.statement_summary.beginning_balance,
            closing_balance=statement.statement_summary.ending_balance,
            status="processing",
            source_type=source_type,
            statement_hash=stmt_hash,
            raw_json=statement_data,  # Store full JSON
            # Only set user_id if it's a valid UUID, otherwise leave null
            created_by_user_id=user_id if user_id and not user_id.startswith("test-") else None,
            supabase_path=source_pdf_path,
        )

        db.add(stmt)
        db.flush()
        
        statement_id = stmt.id
        logger.info(f"Created statement record ID: {statement_id}")
        
        _log_process(db, statement_id, f"Started import from {source_type}")
        _log_process(db, statement_id, f"Bank: {bank_name} ({bank_code}), Account: {account_number}")
        _log_process(db, statement_id, f"Period: {period_start} to {period_end}")
        
        # 4. Create import run for tracking
        import_run = AccountingBankStatementImportRun(
            bank_statement_id=statement_id,
            status="RUNNING",
            transactions_total=len(statement.transactions),
        )
        db.add(import_run)
        db.flush()
        
        # 5. Process transactions
        inserted_count = 0
        skipped_count = 0
        unknown_count = 0
        
        for txn in statement.transactions:
            # Apply classification
            group, code, status = classify_transaction(txn, bank_code)
            txn.accounting_group = group
            txn.classification = code
            txn.status = status
            
            if code.value == "UNKNOWN":
                unknown_count += 1
            
            # Compute dedupe key
            dedupe_key = _compute_row_dedupe_key(
                statement_id,
                txn.posting_date,
                txn.amount,
                txn.description,
            )
            
            # Check for duplicate row
            existing_row = db.query(AccountingBankRow).filter(
                AccountingBankRow.dedupe_key == dedupe_key
            ).first()
            
            if existing_row:
                skipped_count += 1
                continue
            
            # Create row record
            row = AccountingBankRow(
                bank_statement_id=statement_id,
                row_index=txn.id,
                operation_date=txn.posting_date,
                posting_date=txn.posting_date,
                description_raw=txn.description,
                description_clean=txn.description,  # Could be cleaned further
                amount=txn.amount,
                balance_after=txn.balance_after,
                currency=statement.statement_metadata.currency,
                parsed_status="auto_parsed",
                match_status="unmatched",
                dedupe_key=dedupe_key,
                
                # Bank Statement v1.0 fields
                bank_code=bank_code,
                bank_section=txn.bank_section.value if txn.bank_section else None,
                bank_subtype=txn.bank_subtype,
                direction=txn.direction.value if txn.direction else None,
                accounting_group=txn.accounting_group.value if txn.accounting_group else None,
                classification=txn.classification.value if txn.classification else None,
                classification_status=txn.status.value if txn.status else "UNKNOWN",
                check_number=txn.check_number,
                raw_transaction_json=txn.model_dump(mode="json"),
                
                created_by_user_id=user_id if user_id and not user_id.startswith("test-") else None,
            )

            db.add(row)
            inserted_count += 1
        
        db.flush()
        
        _log_process(
            db, statement_id,
            f"Inserted {inserted_count} transactions, skipped {skipped_count} duplicates, {unknown_count} need review"
        )
        
        # 6. Verify totals
        verification_passed = statement.verification_passed
        verification_message = statement.verification_message
        
        if verification_passed is None:
            # Compute our own verification
            credits = sum(t.amount for t in statement.transactions if t.amount > 0)
            debits = sum(t.amount for t in statement.transactions if t.amount < 0)
            expected_net = statement.statement_summary.ending_balance - statement.statement_summary.beginning_balance
            actual_net = credits + debits
            diff = abs(expected_net - actual_net)
            
            verification_passed = diff < Decimal("1.00")
            verification_message = f"Balance check: expected net ${expected_net}, actual ${actual_net}, diff ${diff}"
        
        if not verification_passed:
            _log_process(db, statement_id, f"Verification warning: {verification_message}", level="WARNING")
        
        # 7. Update statement status
        stmt.status = "parsed" if verification_passed else "verification_warning"
        stmt.total_credit = statement.statement_summary.ending_balance - statement.statement_summary.beginning_balance
        if stmt.total_credit < 0:
            stmt.total_debit = abs(stmt.total_credit)
            stmt.total_credit = Decimal("0")
        else:
            stmt.total_debit = Decimal("0")
        
        # Update import run
        import_run.status = "SUCCESS"
        import_run.finished_at = datetime.utcnow()
        import_run.transactions_total = len(statement.transactions)
        import_run.transactions_inserted = inserted_count
        import_run.duplicates_skipped = skipped_count
        
        db.commit()
        
        _log_process(db, statement_id, "Import completed successfully")
        
        logger.info(
            f"Import complete: {inserted_count} inserted, {skipped_count} skipped, "
            f"{unknown_count} unknown classification"
        )
        
        return ImportResult(
            success=True,
            statement_id=statement_id,
            status="PARSED",
            transactions_total=len(statement.transactions),
            transactions_inserted=inserted_count,
            duplicates_skipped=skipped_count,
            classification_unknown=unknown_count,
            bank_name=bank_name,
            bank_code=bank_code,
            account_number=account_number,
            period_start=str(period_start),
            period_end=str(period_end),
            verification_passed=verification_passed,
            verification_message=verification_message,
        )
        
    except Exception as e:
        logger.error(f"Import failed: {e}", exc_info=True)
        db.rollback()
        return ImportResult(
            success=False,
            status="ERROR",
            error_message=str(e),
        )


def import_td_pdf_bytes(
    db: Session,
    pdf_bytes: bytes,
    user_id: str,
    source_filename: Optional[str] = None,
    storage_path: Optional[str] = None,
) -> ImportResult:
    """
    Import a TD Bank PDF statement.
    
    This function:
    1. Parses the PDF using the deterministic TD parser (no OpenAI)
    2. Converts to BankStatementV1 JSON
    3. Imports via import_bank_statement_json()
    
    Args:
        db: SQLAlchemy session
        pdf_bytes: Raw PDF content
        user_id: ID of user performing import
        source_filename: Original filename
        storage_path: Path in Supabase storage
        
    Returns:
        ImportResult with status and counts
    """
    try:
        logger.info(f"Parsing TD Bank PDF: {source_filename}")
        
        # Parse PDF to BankStatementV1
        statement = parse_td_pdf_to_bank_statement_v1(pdf_bytes, source_filename)
        
        # Convert to dict for import
        statement_data = statement.model_dump(mode="json")
        
        # Import JSON
        return import_bank_statement_json(
            db=db,
            statement_data=statement_data,
            user_id=user_id,
            source_type="PDF_TD",
            source_pdf_path=storage_path,
        )
        
    except Exception as e:
        logger.error(f"TD PDF import failed: {e}", exc_info=True)
        return ImportResult(
            success=False,
            status="ERROR",
            error_message=f"Failed to parse TD Bank PDF: {str(e)}",
        )


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def get_supported_banks() -> List[Dict[str, str]]:
    """Get list of banks supported for internal PDF parsing."""
    return [
        {"code": "TD", "name": "TD Bank", "pdf_supported": True},
        # Future banks:
        # {"code": "BOA", "name": "Bank of America", "pdf_supported": False},
        # {"code": "CITI", "name": "Citibank", "pdf_supported": False},
    ]


def validate_json_format(data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """
    Validate JSON against Bank Statement v1.0 schema without importing.
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        validate_bank_statement_json(data)
        return True, None
    except Exception as e:
        return False, str(e)
