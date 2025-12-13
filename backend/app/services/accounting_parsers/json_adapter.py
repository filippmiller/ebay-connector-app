"""
JSON Adapter - Converts various JSON formats to Bank Statement v1.0

This module handles JSON from different sources (ChatGPT, other banks, etc.)
and normalizes it to our canonical BankStatementV1 format.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from typing import Dict, Any, Optional

from app.utils.logger import logger

from .bank_statement_schema import (
    BankStatementV1,
    BankStatementSourceV1,
    BankStatementMetadataV1,
    BankStatementSummaryV1,
    BankStatementTransactionV1,
    BankSectionCode,
    TransactionDirection,
    AccountingGroup,
    ClassificationCode,
    TransactionStatus,
)


# ============================================================================
# CODE MAPPINGS — Map external codes to our enums
# ============================================================================

# Map external bank_section codes to our BankSectionCode enum
BANK_SECTION_MAP = {
    "ELECTRONIC_DEPOSIT": BankSectionCode.ELECTRONIC_DEPOSIT,
    "OTHER_CREDIT": BankSectionCode.OTHER_CREDIT,
    "CHECKS_PAID": BankSectionCode.CHECKS_PAID,
    "ELECTRONIC_PAYMENT": BankSectionCode.ELECTRONIC_PAYMENT,
    "OTHER_WITHDRAWAL": BankSectionCode.OTHER_WITHDRAWAL,
    "SERVICE_CHARGE": BankSectionCode.SERVICE_CHARGE,
    "INTEREST_EARNED": BankSectionCode.INTEREST_EARNED,
    # ChatGPT mappings
    "CHECK": BankSectionCode.CHECKS_PAID,
}

# Map external accounting_group codes to our AccountingGroup enum
ACCOUNTING_GROUP_MAP = {
    "INCOME": AccountingGroup.INCOME,
    "COGS": AccountingGroup.COGS,
    "OPERATING_EXPENSE": AccountingGroup.OPERATING_EXPENSE,
    "BANK_FEE": AccountingGroup.BANK_FEE,
    "INTEREST_INCOME": AccountingGroup.INTEREST_INCOME,
    "PAYROLL": AccountingGroup.PAYROLL,
    "TAXES": AccountingGroup.TAXES,
    "TRANSFER": AccountingGroup.TRANSFER,
    "OWNER_DRAW": AccountingGroup.OWNER_DRAW,
    "PERSONAL": AccountingGroup.PERSONAL,
    "OTHER": AccountingGroup.OTHER,
    # ChatGPT extra mappings
    "COGS_OR_EXPENSE": AccountingGroup.COGS,
    "EBAY_FEES": AccountingGroup.COGS,
    "INCOME_REFUND": AccountingGroup.INCOME,
    "OTHER_EXPENSE": AccountingGroup.OPERATING_EXPENSE,
    "PAYMENT_CHECK": AccountingGroup.TRANSFER,
}

# Map external classification codes to our ClassificationCode enum  
CLASSIFICATION_MAP = {
    # Our codes (direct match)
    "INCOME_EBAY_PAYOUT": ClassificationCode.INCOME_EBAY_PAYOUT,
    "INCOME_AMAZON_PAYOUT": ClassificationCode.INCOME_AMAZON_PAYOUT,
    "INCOME_STRIPE": ClassificationCode.INCOME_STRIPE,
    "INCOME_PAYPAL": ClassificationCode.INCOME_PAYPAL,
    "COGS_INVENTORY_PURCHASE": ClassificationCode.COGS_INVENTORY_PURCHASE,
    "OPEX_SOFTWARE": ClassificationCode.OPEX_SOFTWARE,
    "OPEX_SHIPPING": ClassificationCode.OPEX_SHIPPING,
    "FEE_BANK_SERVICE": ClassificationCode.FEE_BANK_SERVICE,
    "FEE_OVERDRAFT": ClassificationCode.FEE_OVERDRAFT,
    "UNKNOWN": ClassificationCode.UNKNOWN,
    
    # ChatGPT extra mappings
    "INCOME_PAYPAL_TRANSFER": ClassificationCode.INCOME_PAYPAL,
    "EBAY_PURCHASE_OR_FEE": ClassificationCode.COGS_INVENTORY_PURCHASE,
    "EBAY_IAT_FEE_OR_PAYOUT": ClassificationCode.COGS_OTHER,
    "BANK_FEE_INTL_TXN": ClassificationCode.FEE_OTHER,
    "BANK_FEE_MAINTENANCE": ClassificationCode.FEE_BANK_SERVICE,
    "BANK_FEE_OVERDRAFT": ClassificationCode.FEE_OVERDRAFT,
    "CHECK_PAYMENT": ClassificationCode.TRANSFER_OTHER,
    "EXPENSE_FUEL": ClassificationCode.OPEX_OTHER,
    "EXPENSE_POSTAGE": ClassificationCode.OPEX_SHIPPING,
    "EXPENSE_SUBSCRIPTION": ClassificationCode.OPEX_SOFTWARE,
    "EXPENSE_TELECOM_CUSTOMS": ClassificationCode.OPEX_OTHER,
    "OTHER_ELECTRONIC_PAYMENT": ClassificationCode.OPEX_OTHER,
    "REFUND_BANK_FEES": ClassificationCode.INCOME_OTHER,
    "REFUND_CARD_EBAY": ClassificationCode.INCOME_OTHER,
    "TRANSFER_TO_PAYPAL": ClassificationCode.TRANSFER_OTHER,
}


# ============================================================================
# ADAPTER FUNCTIONS
# ============================================================================

def safe_get_enum(value: str, mapping: Dict[str, Any], default: Any) -> Any:
    """Safely get enum value from mapping with fallback."""
    if value is None:
        return default
    return mapping.get(value.upper(), default)


def adapt_chatgpt_json(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Adapt ChatGPT-generated JSON to our BankStatementV1 format.
    
    ChatGPT format has slight variations:
    - statement_period is a nested dict instead of separate fields
    - Uses some different classification codes
    - Amount signs may not follow our convention
    
    Args:
        data: Raw JSON dict from ChatGPT
        
    Returns:
        Adapted dict that can be validated as BankStatementV1
    """
    # Source adaptation
    source = data.get('source', {})
    adapted_source = {
        "statement_type": "BANK_ACCOUNT",
        "bank_name": source.get('bank_name', 'TD Bank'),
        "bank_code": "TD",
        "generated_by": "chatgpt_adapter_v1",
        "generated_from_pdf": source.get('generated_from_pdf'),
    }
    
    # Metadata adaptation 
    meta = data.get('statement_metadata', {})
    statement_period = meta.get('statement_period', {})
    
    # Handle period in nested or flat format
    period_start = statement_period.get('start_date') or meta.get('statement_period_start')
    period_end = statement_period.get('end_date') or meta.get('statement_period_end')
    
    adapted_metadata = {
        "bank_name": meta.get('bank_name', 'TD Bank'),
        "product_name": meta.get('account_product') or meta.get('product_name'),
        "account_owner": meta.get('account_owner'),
        "primary_account_number": meta.get('primary_account_number', 'UNKNOWN'),
        "statement_period_start": period_start,
        "statement_period_end": period_end,
        "currency": meta.get('currency', 'USD'),
    }
    
    # Summary adaptation
    summary = data.get('statement_summary', {})
    adapted_summary = {
        "beginning_balance": str(summary.get('beginning_balance', 0)),
        "ending_balance": str(summary.get('ending_balance', 0)),
        "electronic_deposits_total": str(summary.get('electronic_deposits_total')) if summary.get('electronic_deposits_total') else None,
        "other_credits_total": str(summary.get('other_credits_total')) if summary.get('other_credits_total') else None,
        "checks_paid_total": str(summary.get('checks_paid_total')) if summary.get('checks_paid_total') else None,
        "electronic_payments_total": str(summary.get('electronic_payments_total')) if summary.get('electronic_payments_total') else None,
        "other_withdrawals_total": str(summary.get('other_withdrawals_total')) if summary.get('other_withdrawals_total') else None,
        "service_charges_fees_total": str(summary.get('service_charges_total')) if summary.get('service_charges_total') else None,
    }
    
    # Transactions adaptation
    adapted_transactions = []
    for txn in data.get('transactions', []):
        # Get direction
        direction_str = txn.get('direction', 'DEBIT').upper()
        direction = TransactionDirection.CREDIT if direction_str == 'CREDIT' else TransactionDirection.DEBIT
        
        # Adapt amount sign
        amount = Decimal(str(txn.get('amount', 0)))
        if direction == TransactionDirection.DEBIT and amount > 0:
            amount = -amount  # Make debits negative
        
        # Map codes
        bank_section = safe_get_enum(
            txn.get('bank_section'),
            BANK_SECTION_MAP,
            BankSectionCode.UNKNOWN
        )
        accounting_group = safe_get_enum(
            txn.get('accounting_group'),
            ACCOUNTING_GROUP_MAP,
            AccountingGroup.OTHER
        )
        classification = safe_get_enum(
            txn.get('classification'),
            CLASSIFICATION_MAP,
            ClassificationCode.UNKNOWN
        )
        
        adapted_txn = {
            "id": txn.get('id'),
            "posting_date": txn.get('posting_date'),
            "description": txn.get('description'),
            "amount": str(amount),
            "bank_section": bank_section.value,
            "bank_subtype": txn.get('bank_subtype'),
            "direction": direction.value,
            "accounting_group": accounting_group.value,
            "classification": classification.value,
            "status": "OK",
            "check_number": txn.get('check_number'),
        }
        adapted_transactions.append(adapted_txn)
    
    return {
        "schema_version": "1.0",
        "source": adapted_source,
        "statement_metadata": adapted_metadata,
        "statement_summary": adapted_summary,
        "transactions": adapted_transactions,
    }


def detect_and_adapt_json(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Detect the JSON format and apply appropriate adapter.
    
    Args:
        data: Raw JSON dict
        
    Returns:
        Adapted dict in BankStatementV1 format
    """
    # Check if it's already in our exact format
    source = data.get('source', {})
    
    # If source has bank_code, it's likely our format
    if source.get('bank_code'):
        # Already in our format, minimal adaptation needed
        return data
    
    # Check for ChatGPT format markers
    meta = data.get('statement_metadata', {})
    if meta.get('statement_period') and isinstance(meta.get('statement_period'), dict):
        # ChatGPT uses nested statement_period
        logger.info("Detected ChatGPT JSON format, applying adapter")
        return adapt_chatgpt_json(data)
    
    # Default: try ChatGPT adapter as it's most permissive
    logger.info("Unknown JSON format, applying ChatGPT adapter")
    return adapt_chatgpt_json(data)


def validate_and_adapt_json(data: Dict[str, Any]) -> BankStatementV1:
    """
    Detect format, adapt, and validate JSON as BankStatementV1.
    
    This is the main entry point for external JSON.
    
    Args:
        data: Raw JSON dict from any source
        
    Returns:
        Validated BankStatementV1 object
        
    Raises:
        pydantic.ValidationError: If data cannot be adapted/validated
    """
    adapted = detect_and_adapt_json(data)
    return BankStatementV1.model_validate(adapted)
