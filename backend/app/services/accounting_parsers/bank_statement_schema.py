"""
Bank Statement v1.0 — Unified JSON Schema for All Banks

This module defines the "gold standard" JSON schema that all bank statement parsers
(TD Bank, Bank of America, Citi, etc.) must produce before importing into the database.

The schema is versioned (currently 1.0) to allow future migrations.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional, Literal
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator, field_serializer, ConfigDict


# ============================================================================
# ENUMS — Business Classification
# ============================================================================

class BankSectionCode(str, Enum):
    """Section codes from bank statement structure (TD Bank format)."""
    ELECTRONIC_DEPOSIT = "ELECTRONIC_DEPOSIT"
    OTHER_CREDIT = "OTHER_CREDIT"
    CHECKS_PAID = "CHECKS_PAID"
    ELECTRONIC_PAYMENT = "ELECTRONIC_PAYMENT"
    OTHER_WITHDRAWAL = "OTHER_WITHDRAWAL"
    SERVICE_CHARGE = "SERVICE_CHARGE"
    INTEREST_EARNED = "INTEREST_EARNED"
    UNKNOWN = "UNKNOWN"


class TransactionDirection(str, Enum):
    """Direction of money flow."""
    CREDIT = "CREDIT"  # Money IN
    DEBIT = "DEBIT"    # Money OUT


class AccountingGroup(str, Enum):
    """High-level business classification for ledger purposes."""
    INCOME = "INCOME"
    COGS = "COGS"  # Cost of Goods Sold
    OPERATING_EXPENSE = "OPERATING_EXPENSE"
    BANK_FEE = "BANK_FEE"
    INTEREST_INCOME = "INTEREST_INCOME"
    PAYROLL = "PAYROLL"
    TAXES = "TAXES"
    TRANSFER = "TRANSFER"
    OWNER_DRAW = "OWNER_DRAW"
    PERSONAL = "PERSONAL"
    OTHER = "OTHER"


class ClassificationCode(str, Enum):
    """Detailed classification codes for transaction categorization."""
    # Income
    INCOME_EBAY_PAYOUT = "INCOME_EBAY_PAYOUT"
    INCOME_AMAZON_PAYOUT = "INCOME_AMAZON_PAYOUT"
    INCOME_STRIPE = "INCOME_STRIPE"
    INCOME_PAYPAL = "INCOME_PAYPAL"
    INCOME_OTHER = "INCOME_OTHER"
    
    # COGS
    COGS_INVENTORY_PURCHASE = "COGS_INVENTORY_PURCHASE"
    COGS_SHIPPING_SUPPLY = "COGS_SHIPPING_SUPPLY"
    COGS_SUPPLIER_PAYMENT = "COGS_SUPPLIER_PAYMENT"
    COGS_OTHER = "COGS_OTHER"
    
    # Operating Expenses
    OPEX_SOFTWARE = "OPEX_SOFTWARE"
    OPEX_RENT = "OPEX_RENT"
    OPEX_UTILITIES = "OPEX_UTILITIES"
    OPEX_INSURANCE = "OPEX_INSURANCE"
    OPEX_SHIPPING = "OPEX_SHIPPING"
    OPEX_ADVERTISING = "OPEX_ADVERTISING"
    OPEX_OFFICE_SUPPLIES = "OPEX_OFFICE_SUPPLIES"
    OPEX_PROFESSIONAL_SERVICES = "OPEX_PROFESSIONAL_SERVICES"
    OPEX_OTHER = "OPEX_OTHER"
    
    # Bank & Financial
    FEE_BANK_SERVICE = "FEE_BANK_SERVICE"
    FEE_WIRE_TRANSFER = "FEE_WIRE_TRANSFER"
    FEE_OVERDRAFT = "FEE_OVERDRAFT"
    FEE_OTHER = "FEE_OTHER"
    INTEREST_EARNED = "INTEREST_EARNED"
    
    # Payroll
    PAYROLL_WAGE = "PAYROLL_WAGE"
    PAYROLL_TAX = "PAYROLL_TAX"
    PAYROLL_BENEFIT = "PAYROLL_BENEFIT"
    PAYROLL_CONTRACTOR = "PAYROLL_CONTRACTOR"
    
    # Taxes
    TAX_SALES = "TAX_SALES"
    TAX_INCOME = "TAX_INCOME"
    TAX_PROPERTY = "TAX_PROPERTY"
    TAX_OTHER = "TAX_OTHER"
    
    # Transfers
    TRANSFER_INTERNAL = "TRANSFER_INTERNAL"
    TRANSFER_OWNER_DRAW = "TRANSFER_OWNER_DRAW"
    TRANSFER_LOAN_PAYMENT = "TRANSFER_LOAN_PAYMENT"
    TRANSFER_OTHER = "TRANSFER_OTHER"
    
    # Personal (non-business but tracked)
    PERSONAL_EXPENSE = "PERSONAL_EXPENSE"
    
    # Unknown / Needs Review
    UNKNOWN = "UNKNOWN"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class TransactionStatus(str, Enum):
    """Processing status of a transaction."""
    OK = "OK"
    PARSE_ERROR = "PARSE_ERROR"
    CLASSIFICATION_ERROR = "CLASSIFICATION_ERROR"
    UNKNOWN = "UNKNOWN"
    SUSPICIOUS = "SUSPICIOUS"  # Balance mismatch or similar


# ============================================================================
# SCHEMA MODELS — Bank Statement v1.0
# ============================================================================

class BankStatementSourceV1(BaseModel):
    """Metadata about the source of the bank statement."""
    statement_type: Literal["BANK_ACCOUNT"] = "BANK_ACCOUNT"
    bank_name: str = Field(..., description="Full bank name, e.g. 'TD Bank'")
    bank_code: str = Field(..., description="Short bank code, e.g. 'TD', 'BOA', 'CITI'")
    generated_by: str = Field(..., description="Parser that generated this JSON, e.g. 'td_pdf_parser_v1'")
    generated_from_pdf: Optional[str] = Field(None, description="Original PDF filename if applicable")
    parsing_timestamp: Optional[str] = Field(None, description="ISO timestamp of when parsing occurred")


class BankStatementMetadataV1(BaseModel):
    """Core statement metadata extracted from header/summary."""
    bank_name: str
    product_name: Optional[str] = Field(None, description="Account product, e.g. 'TD Business Checking Account'")
    account_owner: Optional[str] = Field(None, description="Account holder name")
    primary_account_number: str = Field(..., description="Account number (masked or full), e.g. '****4567'")
    statement_period_start: date
    statement_period_end: date
    statement_address: Optional[str] = Field(None, description="Address on statement")
    currency: str = Field("USD", description="Currency code")


class BankStatementSummaryV1(BaseModel):
    """Summary totals from the ACCOUNT SUMMARY section."""
    beginning_balance: Decimal
    ending_balance: Decimal
    
    # Detailed category totals (TD Bank specific but useful for verification)
    electronic_deposits_total: Optional[Decimal] = None
    other_credits_total: Optional[Decimal] = None
    checks_paid_total: Optional[Decimal] = None
    electronic_payments_total: Optional[Decimal] = None
    other_withdrawals_total: Optional[Decimal] = None
    service_charges_fees_total: Optional[Decimal] = None
    interest_earned_total: Optional[Decimal] = None
    
    # Optional grace period info (TD specific)
    grace_period_balance: Optional[Decimal] = None
    grace_period_start: Optional[date] = None
    grace_period_end: Optional[date] = None

    @field_serializer('beginning_balance', 'ending_balance', 'electronic_deposits_total',
                      'other_credits_total', 'checks_paid_total', 'electronic_payments_total',
                      'other_withdrawals_total', 'service_charges_fees_total', 'interest_earned_total',
                      'grace_period_balance', when_used='json')
    def serialize_decimal(self, v: Optional[Decimal]) -> Optional[float]:
        return float(v) if v is not None else None


class BankStatementTransactionV1(BaseModel):
    """A single transaction line from the statement."""
    id: int = Field(..., description="Line number in statement (1-indexed)")
    
    # Core fields
    posting_date: date
    description: str = Field(..., description="Full transaction description")
    amount: Decimal = Field(..., description="Transaction amount (positive for credits, negative for debits)")
    
    # Bank classification (extracted from statement structure)
    bank_section: BankSectionCode = Field(BankSectionCode.UNKNOWN, description="Section in the statement")
    bank_subtype: Optional[str] = Field(None, description="Subtype like 'CCD DEPOSIT', 'ACH DEBIT', etc.")
    
    # Business classification (computed by our rules engine)
    direction: TransactionDirection
    accounting_group: AccountingGroup = AccountingGroup.OTHER
    classification: ClassificationCode = ClassificationCode.UNKNOWN
    
    # Processing metadata
    status: TransactionStatus = TransactionStatus.OK
    
    # Optional fields
    check_number: Optional[str] = Field(None, description="Check number if applicable")
    balance_after: Optional[Decimal] = Field(None, description="Running balance after this transaction")
    
    # Parsed components from description
    counterparty: Optional[str] = Field(None, description="Identified counterparty name")
    memo: Optional[str] = Field(None, description="Additional memo/notes from description")
    
    # Raw preservation
    description_raw: Optional[str] = Field(None, description="Original unprocessed description")

    @field_validator('amount', mode='before')
    @classmethod
    def coerce_amount(cls, v):
        if isinstance(v, str):
            # Remove commas and convert
            return Decimal(v.replace(',', ''))
        return Decimal(str(v))

    @field_serializer('amount', 'balance_after', when_used='json')
    def serialize_decimal(self, v: Optional[Decimal]) -> Optional[float]:
        return float(v) if v is not None else None


class BankStatementV1(BaseModel):
    """
    Root schema for Bank Statement v1.0.
    
    This is the canonical format that all bank parsers (TD, BOA, etc.) must produce.
    It can be imported directly via the import-json endpoint.
    """
    schema_version: Literal["1.0"] = "1.0"
    
    source: BankStatementSourceV1
    statement_metadata: BankStatementMetadataV1
    statement_summary: BankStatementSummaryV1
    transactions: List[BankStatementTransactionV1]
    
    # Optional processing notes
    parsing_notes: Optional[str] = Field(None, description="Notes from the parser about any issues encountered")
    verification_passed: Optional[bool] = Field(None, description="True if totals matched summary")
    verification_message: Optional[str] = Field(None, description="Details about verification")

    class Config:
        json_schema_extra = {
            "example": {
                "schema_version": "1.0",
                "source": {
                    "statement_type": "BANK_ACCOUNT",
                    "bank_name": "TD Bank",
                    "bank_code": "TD",
                    "generated_by": "td_pdf_parser_v1",
                    "generated_from_pdf": "statement_2025-01.pdf"
                },
                "statement_metadata": {
                    "bank_name": "TD Bank",
                    "product_name": "TD Business Checking Account",
                    "account_owner": "ACME CORP LLC",
                    "primary_account_number": "****4567",
                    "statement_period_start": "2025-01-01",
                    "statement_period_end": "2025-01-31",
                    "currency": "USD"
                },
                "statement_summary": {
                    "beginning_balance": "10000.00",
                    "ending_balance": "12500.50"
                },
                "transactions": [
                    {
                        "id": 1,
                        "posting_date": "2025-01-05",
                        "description": "CCD DEPOSIT EBAY COM MARKETPLACE",
                        "amount": "1500.00",
                        "bank_section": "ELECTRONIC_DEPOSIT",
                        "bank_subtype": "CCD DEPOSIT",
                        "direction": "CREDIT",
                        "accounting_group": "INCOME",
                        "classification": "INCOME_EBAY_PAYOUT",
                        "status": "OK"
                    }
                ]
            }
        }


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def validate_bank_statement_json(data: dict) -> BankStatementV1:
    """
    Validate and parse a dict into BankStatementV1.
    Raises pydantic.ValidationError on invalid data.
    """
    return BankStatementV1.model_validate(data)


def get_schema_version() -> str:
    """Return current schema version."""
    return "1.0"
