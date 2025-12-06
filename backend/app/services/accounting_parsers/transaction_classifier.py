"""
Bank Transaction Classifier — Rule-based classification (no AI).

This module provides centralized transaction classification logic that maps
bank transaction descriptions to accounting groups and detailed classification codes.

Architecture:
- Rule-based classification runs synchronously during import
- Provides hook for future AI classification (not implemented in v1)
- All rules are defined in code for now; can be moved to DB later
"""

from __future__ import annotations

import re
from typing import Tuple, Optional, List
from dataclasses import dataclass

from .bank_statement_schema import (
    BankStatementTransactionV1,
    BankSectionCode,
    TransactionDirection,
    AccountingGroup,
    ClassificationCode,
    TransactionStatus,
)
from app.utils.logger import logger


# ============================================================================
# CLASSIFICATION RULES
# ============================================================================

@dataclass
class ClassificationRule:
    """A single classification rule."""
    pattern: str  # Regex or substring pattern
    pattern_type: str  # 'contains' or 'regex'
    bank_section: Optional[BankSectionCode]  # Optional section filter
    accounting_group: AccountingGroup
    classification: ClassificationCode
    priority: int  # Lower = higher priority (evaluated first)
    description: str  # Human-readable rule description


# TD Bank specific rules (can be expanded for other banks)
TD_CLASSIFICATION_RULES: List[ClassificationRule] = [
    # ============ INCOME ============
    # eBay Payouts
    ClassificationRule(
        pattern=r'EBAY\s*(COM|INC)?.*(?:PAYOUT|MARKETPLACE|PAYMENT)',
        pattern_type='regex',
        bank_section=BankSectionCode.ELECTRONIC_DEPOSIT,
        accounting_group=AccountingGroup.INCOME,
        classification=ClassificationCode.INCOME_EBAY_PAYOUT,
        priority=10,
        description="eBay marketplace payout"
    ),
    ClassificationRule(
        pattern='EBAY COM',
        pattern_type='contains',
        bank_section=BankSectionCode.ELECTRONIC_DEPOSIT,
        accounting_group=AccountingGroup.INCOME,
        classification=ClassificationCode.INCOME_EBAY_PAYOUT,
        priority=11,
        description="eBay deposit (generic)"
    ),
    
    # Amazon Payouts
    ClassificationRule(
        pattern=r'AMAZON.*(?:PAYOUT|PAYMENT|PAYMENTS)',
        pattern_type='regex',
        bank_section=BankSectionCode.ELECTRONIC_DEPOSIT,
        accounting_group=AccountingGroup.INCOME,
        classification=ClassificationCode.INCOME_AMAZON_PAYOUT,
        priority=10,
        description="Amazon payout"
    ),
    ClassificationRule(
        pattern='AMAZON PAYMENTS',
        pattern_type='contains',
        bank_section=BankSectionCode.ELECTRONIC_DEPOSIT,
        accounting_group=AccountingGroup.INCOME,
        classification=ClassificationCode.INCOME_AMAZON_PAYOUT,
        priority=11,
        description="Amazon payment deposit"
    ),
    
    # Stripe
    ClassificationRule(
        pattern='STRIPE',
        pattern_type='contains',
        bank_section=BankSectionCode.ELECTRONIC_DEPOSIT,
        accounting_group=AccountingGroup.INCOME,
        classification=ClassificationCode.INCOME_STRIPE,
        priority=10,
        description="Stripe payout"
    ),
    
    # PayPal
    ClassificationRule(
        pattern='PAYPAL',
        pattern_type='contains',
        bank_section=BankSectionCode.ELECTRONIC_DEPOSIT,
        accounting_group=AccountingGroup.INCOME,
        classification=ClassificationCode.INCOME_PAYPAL,
        priority=10,
        description="PayPal deposit"
    ),
    
    # ============ COGS — Cost of Goods Sold ============
    # Inventory suppliers
    ClassificationRule(
        pattern=r'(?:INVENTORY|WHOLESALE|LIQUIDATION)',
        pattern_type='regex',
        bank_section=BankSectionCode.ELECTRONIC_PAYMENT,
        accounting_group=AccountingGroup.COGS,
        classification=ClassificationCode.COGS_INVENTORY_PURCHASE,
        priority=20,
        description="Inventory purchase"
    ),
    ClassificationRule(
        pattern='ALIBABA',
        pattern_type='contains',
        bank_section=None,  # Any section
        accounting_group=AccountingGroup.COGS,
        classification=ClassificationCode.COGS_INVENTORY_PURCHASE,
        priority=20,
        description="Alibaba supplier payment"
    ),
    
    # Shipping supplies
    ClassificationRule(
        pattern=r'(?:ULINE|STAPLES|OFFICE DEPOT).*(?:SHIP|PACK|BOX)',
        pattern_type='regex',
        bank_section=None,
        accounting_group=AccountingGroup.COGS,
        classification=ClassificationCode.COGS_SHIPPING_SUPPLY,
        priority=25,
        description="Shipping supplies"
    ),
    
    # ============ OPERATING EXPENSES ============
    # Shipping (outgoing)
    ClassificationRule(
        pattern='USPS',
        pattern_type='contains',
        bank_section=BankSectionCode.ELECTRONIC_PAYMENT,
        accounting_group=AccountingGroup.OPERATING_EXPENSE,
        classification=ClassificationCode.OPEX_SHIPPING,
        priority=30,
        description="USPS shipping"
    ),
    ClassificationRule(
        pattern='UPS',
        pattern_type='contains',
        bank_section=BankSectionCode.ELECTRONIC_PAYMENT,
        accounting_group=AccountingGroup.OPERATING_EXPENSE,
        classification=ClassificationCode.OPEX_SHIPPING,
        priority=30,
        description="UPS shipping"
    ),
    ClassificationRule(
        pattern='FEDEX',
        pattern_type='contains',
        bank_section=None,
        accounting_group=AccountingGroup.OPERATING_EXPENSE,
        classification=ClassificationCode.OPEX_SHIPPING,
        priority=30,
        description="FedEx shipping"
    ),
    ClassificationRule(
        pattern='PIRATESHIP',
        pattern_type='contains',
        bank_section=None,
        accounting_group=AccountingGroup.OPERATING_EXPENSE,
        classification=ClassificationCode.OPEX_SHIPPING,
        priority=30,
        description="Pirateship shipping"
    ),
    ClassificationRule(
        pattern='SHIPSTATION',
        pattern_type='contains',
        bank_section=None,
        accounting_group=AccountingGroup.OPERATING_EXPENSE,
        classification=ClassificationCode.OPEX_SHIPPING,
        priority=30,
        description="ShipStation"
    ),
    
    # Software & subscriptions
    ClassificationRule(
        pattern=r'(?:MICROSOFT|GOOGLE|APPLE|AMAZON WEB|AWS|DROPBOX|SLACK|ZOOM|GITHUB)',
        pattern_type='regex',
        bank_section=None,
        accounting_group=AccountingGroup.OPERATING_EXPENSE,
        classification=ClassificationCode.OPEX_SOFTWARE,
        priority=30,
        description="Software subscription"
    ),
    ClassificationRule(
        pattern='QUICKBOOKS',
        pattern_type='contains',
        bank_section=None,
        accounting_group=AccountingGroup.OPERATING_EXPENSE,
        classification=ClassificationCode.OPEX_SOFTWARE,
        priority=30,
        description="QuickBooks"
    ),
    
    # Advertising
    ClassificationRule(
        pattern=r'(?:FACEBOOK|META|GOOGLE ADS|BING ADS)',
        pattern_type='regex',
        bank_section=None,
        accounting_group=AccountingGroup.OPERATING_EXPENSE,
        classification=ClassificationCode.OPEX_ADVERTISING,
        priority=30,
        description="Advertising"
    ),
    
    # Rent
    ClassificationRule(
        pattern=r'(?:RENT|LEASE|PROPERTY\s*MGMT)',
        pattern_type='regex',
        bank_section=BankSectionCode.ELECTRONIC_PAYMENT,
        accounting_group=AccountingGroup.OPERATING_EXPENSE,
        classification=ClassificationCode.OPEX_RENT,
        priority=30,
        description="Rent payment"
    ),
    
    # Utilities
    ClassificationRule(
        pattern=r'(?:ELECTRIC|GAS|WATER|UTILITY|UTILITIES)',
        pattern_type='regex',
        bank_section=None,
        accounting_group=AccountingGroup.OPERATING_EXPENSE,
        classification=ClassificationCode.OPEX_UTILITIES,
        priority=30,
        description="Utilities"
    ),
    ClassificationRule(
        pattern=r'(?:COMCAST|VERIZON|ATT|T-MOBILE|AT&T|SPECTRUM)',
        pattern_type='regex',
        bank_section=None,
        accounting_group=AccountingGroup.OPERATING_EXPENSE,
        classification=ClassificationCode.OPEX_UTILITIES,
        priority=30,
        description="Telecom/Internet"
    ),
    
    # Insurance
    ClassificationRule(
        pattern=r'(?:INSURANCE|INSUR|INS PREM)',
        pattern_type='regex',
        bank_section=None,
        accounting_group=AccountingGroup.OPERATING_EXPENSE,
        classification=ClassificationCode.OPEX_INSURANCE,
        priority=30,
        description="Insurance"
    ),
    
    # Office supplies
    ClassificationRule(
        pattern=r'(?:STAPLES|OFFICE DEPOT|OFFICEMAX)',
        pattern_type='regex',
        bank_section=None,
        accounting_group=AccountingGroup.OPERATING_EXPENSE,
        classification=ClassificationCode.OPEX_OFFICE_SUPPLIES,
        priority=35,
        description="Office supplies"
    ),
    
    # Professional services
    ClassificationRule(
        pattern=r'(?:ATTORNEY|LAWYER|LEGAL|CPA|ACCOUNTANT|ACCOUNTING)',
        pattern_type='regex',
        bank_section=None,
        accounting_group=AccountingGroup.OPERATING_EXPENSE,
        classification=ClassificationCode.OPEX_PROFESSIONAL_SERVICES,
        priority=30,
        description="Professional services"
    ),
    
    # ============ BANK FEES ============
    ClassificationRule(
        pattern=r'(?:SERVICE\s*CHARGE|MAINTENANCE\s*FEE|MONTHLY\s*FEE)',
        pattern_type='regex',
        bank_section=BankSectionCode.SERVICE_CHARGE,
        accounting_group=AccountingGroup.BANK_FEE,
        classification=ClassificationCode.FEE_BANK_SERVICE,
        priority=10,
        description="Bank service fee"
    ),
    ClassificationRule(
        pattern='WIRE FEE',
        pattern_type='contains',
        bank_section=None,
        accounting_group=AccountingGroup.BANK_FEE,
        classification=ClassificationCode.FEE_WIRE_TRANSFER,
        priority=10,
        description="Wire transfer fee"
    ),
    ClassificationRule(
        pattern='OVERDRAFT',
        pattern_type='contains',
        bank_section=None,
        accounting_group=AccountingGroup.BANK_FEE,
        classification=ClassificationCode.FEE_OVERDRAFT,
        priority=10,
        description="Overdraft fee"
    ),
    
    # ============ INTEREST EARNED ============
    ClassificationRule(
        pattern=r'INTEREST\s*(?:EARNED|PAID|PAYMENT|CREDIT)',
        pattern_type='regex',
        bank_section=BankSectionCode.INTEREST_EARNED,
        accounting_group=AccountingGroup.INTEREST_INCOME,
        classification=ClassificationCode.INTEREST_EARNED,
        priority=10,
        description="Interest earned"
    ),
    
    # ============ PAYROLL ============
    ClassificationRule(
        pattern=r'(?:PAYROLL|PAYCHECK|DIRECT\s*DEP.*PAYROLL)',
        pattern_type='regex',
        bank_section=BankSectionCode.ELECTRONIC_PAYMENT,
        accounting_group=AccountingGroup.PAYROLL,
        classification=ClassificationCode.PAYROLL_WAGE,
        priority=20,
        description="Payroll payment"
    ),
    ClassificationRule(
        pattern='GUSTO',
        pattern_type='contains',
        bank_section=None,
        accounting_group=AccountingGroup.PAYROLL,
        classification=ClassificationCode.PAYROLL_WAGE,
        priority=20,
        description="Gusto payroll"
    ),
    ClassificationRule(
        pattern='ADP',
        pattern_type='contains',
        bank_section=None,
        accounting_group=AccountingGroup.PAYROLL,
        classification=ClassificationCode.PAYROLL_WAGE,
        priority=20,
        description="ADP payroll"
    ),
    ClassificationRule(
        pattern=r'(?:EFTPS|IRS|STATE\s*TAX)',
        pattern_type='regex',
        bank_section=None,
        accounting_group=AccountingGroup.PAYROLL,
        classification=ClassificationCode.PAYROLL_TAX,
        priority=20,
        description="Payroll tax payment"
    ),
    
    # ============ TAXES ============
    ClassificationRule(
        pattern=r'(?:SALES\s*TAX|STATE\s*TAX)',
        pattern_type='regex',
        bank_section=BankSectionCode.ELECTRONIC_PAYMENT,
        accounting_group=AccountingGroup.TAXES,
        classification=ClassificationCode.TAX_SALES,
        priority=25,
        description="Sales tax payment"
    ),
    ClassificationRule(
        pattern=r'(?:IRS|INCOME\s*TAX)',
        pattern_type='regex',
        bank_section=None,
        accounting_group=AccountingGroup.TAXES,
        classification=ClassificationCode.TAX_INCOME,
        priority=25,
        description="Income tax payment"
    ),
    
    # ============ TRANSFERS ============
    ClassificationRule(
        pattern=r'(?:TRANSFER|XFER).*(?:TO|FROM)',
        pattern_type='regex',
        bank_section=None,
        accounting_group=AccountingGroup.TRANSFER,
        classification=ClassificationCode.TRANSFER_INTERNAL,
        priority=40,
        description="Internal transfer"
    ),
    ClassificationRule(
        pattern=r'(?:OWNER|DRAW|DISTRIBUTION)',
        pattern_type='regex',
        bank_section=None,
        accounting_group=AccountingGroup.OWNER_DRAW,
        classification=ClassificationCode.TRANSFER_OWNER_DRAW,
        priority=40,
        description="Owner draw"
    ),
    ClassificationRule(
        pattern=r'(?:LOAN|MORTGAGE).*(?:PAYMENT|PMT)',
        pattern_type='regex',
        bank_section=None,
        accounting_group=AccountingGroup.TRANSFER,
        classification=ClassificationCode.TRANSFER_LOAN_PAYMENT,
        priority=40,
        description="Loan payment"
    ),
]

# Default rules applicable to all banks
DEFAULT_RULES = TD_CLASSIFICATION_RULES  # Start with TD rules as default

# Bank-specific rule overrides
BANK_RULES: dict[str, List[ClassificationRule]] = {
    "TD": TD_CLASSIFICATION_RULES,
    # Future banks:
    # "BOA": BOA_CLASSIFICATION_RULES,
    # "CITI": CITI_CLASSIFICATION_RULES,
}


# ============================================================================
# CLASSIFICATION ENGINE
# ============================================================================

def classify_transaction(
    txn: BankStatementTransactionV1,
    bank_code: str = "TD"
) -> Tuple[AccountingGroup, ClassificationCode, TransactionStatus]:
    """
    Classify a transaction using rule-based matching.
    
    Args:
        txn: The transaction to classify
        bank_code: Bank code for bank-specific rules
        
    Returns:
        Tuple of (accounting_group, classification, status)
    """
    # Get rules for this bank (or default)
    rules = BANK_RULES.get(bank_code.upper(), DEFAULT_RULES)
    
    # Sort by priority
    sorted_rules = sorted(rules, key=lambda r: r.priority)
    
    description = (txn.description or "").upper()
    
    for rule in sorted_rules:
        # Check section filter if specified
        if rule.bank_section and txn.bank_section != rule.bank_section:
            continue
        
        # Check pattern match
        matched = False
        if rule.pattern_type == 'contains':
            matched = rule.pattern.upper() in description
        elif rule.pattern_type == 'regex':
            try:
                matched = bool(re.search(rule.pattern, description, re.IGNORECASE))
            except re.error:
                logger.warning(f"Invalid regex in rule: {rule.pattern}")
                continue
        
        if matched:
            logger.debug(f"Transaction matched rule: {rule.description}")
            return rule.accounting_group, rule.classification, TransactionStatus.OK
    
    # No rule matched
    return AccountingGroup.OTHER, ClassificationCode.UNKNOWN, TransactionStatus.UNKNOWN


def classify_transactions_batch(
    transactions: List[BankStatementTransactionV1],
    bank_code: str = "TD"
) -> List[BankStatementTransactionV1]:
    """
    Classify a batch of transactions, modifying them in place.
    
    Args:
        transactions: List of transactions to classify
        bank_code: Bank code for bank-specific rules
        
    Returns:
        The same list with classification fields populated
    """
    classified_count = 0
    unknown_count = 0
    
    for txn in transactions:
        group, code, status = classify_transaction(txn, bank_code)
        txn.accounting_group = group
        txn.classification = code
        txn.status = status
        
        if code != ClassificationCode.UNKNOWN:
            classified_count += 1
        else:
            unknown_count += 1
    
    logger.info(
        f"Classified {classified_count}/{len(transactions)} transactions; "
        f"{unknown_count} unknown/need review"
    )
    
    return transactions


# ============================================================================
# FUTURE AI HOOK (not implemented in v1)
# ============================================================================

class AIClassificationHook:
    """
    Placeholder for future AI-based classification.
    
    This hook can be used to:
    1. Mark transactions for AI review
    2. Send batches to an AI service
    3. Learn from user corrections
    
    NOT IMPLEMENTED IN V1 — rule-based only.
    """
    
    @staticmethod
    def mark_for_ai_review(transactions: List[BankStatementTransactionV1]) -> List[BankStatementTransactionV1]:
        """Mark unknown transactions for AI review (future implementation)."""
        for txn in transactions:
            if txn.classification == ClassificationCode.UNKNOWN:
                txn.status = TransactionStatus.UNKNOWN  # Can be picked up by AI later
        return transactions
    
    @staticmethod
    def is_enabled() -> bool:
        """Check if AI classification is enabled (always False in v1)."""
        return False


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def get_classification_summary(transactions: List[BankStatementTransactionV1]) -> dict:
    """Get summary statistics of transaction classifications."""
    summary = {
        "total": len(transactions),
        "classified": 0,
        "unknown": 0,
        "by_group": {},
        "by_classification": {},
    }
    
    for txn in transactions:
        if txn.classification != ClassificationCode.UNKNOWN:
            summary["classified"] += 1
        else:
            summary["unknown"] += 1
        
        group_name = txn.accounting_group.value
        summary["by_group"][group_name] = summary["by_group"].get(group_name, 0) + 1
        
        class_name = txn.classification.value
        summary["by_classification"][class_name] = summary["by_classification"].get(class_name, 0) + 1
    
    return summary
