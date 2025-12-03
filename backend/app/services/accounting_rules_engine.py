from __future__ import annotations

import re
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models_sqlalchemy.models import (
    AccountingBankRow,
    AccountingBankRule,
    AccountingExpenseCategory,
)
from app.utils.logger import logger

def apply_rules_to_bank_rows(db: Session, rows: List[AccountingBankRow]) -> int:
    """Apply active bank rules to the given list of bank rows.
    
    Returns the number of rows that were updated (categorized).
    """
    if not rows:
        return 0

    # 1. Fetch all active rules, ordered by priority (lower number = higher priority)
    rules = (
        db.query(AccountingBankRule)
        .filter(AccountingBankRule.is_active == True)
        .order_by(AccountingBankRule.priority.asc(), AccountingBankRule.id.asc())
        .all()
    )

    if not rules:
        return 0

    updated_count = 0

    # 2. Iterate through rows and apply rules
    for row in rows:
        # Skip if already categorized (unless we want to support re-running rules to overwrite?)
        # For now, let's assume we only auto-categorize rows that have no category.
        if row.expense_category_id is not None:
            continue

        matched_rule = None
        description = (row.description_clean or row.description_raw or "").lower()
        
        for rule in rules:
            pattern = (rule.pattern_value or "").lower()
            
            if rule.pattern_type == "contains":
                if pattern in description:
                    matched_rule = rule
                    break
            
            elif rule.pattern_type == "regex":
                try:
                    if re.search(pattern, description, re.IGNORECASE):
                        matched_rule = rule
                        break
                except re.error:
                    logger.warning(f"Invalid regex in bank rule {rule.id}: {pattern}")
                    continue
            
            elif rule.pattern_type == "counterparty":
                # Assuming 'counterparty' logic is similar to 'contains' but strictly for counterparty field if we had it extracted separately.
                # Since we mostly rely on description, we'll treat it as contains for now, or maybe exact match?
                # Let's treat it as 'contains' on description for simplicity until we have better counterparty extraction.
                if pattern in description:
                    matched_rule = rule
                    break
            
            # 'llm_label' type would be handled by a separate AI process, not this synchronous rule engine.

        if matched_rule:
            row.expense_category_id = matched_rule.expense_category_id
            row.parsed_status = "auto_categorized"
            updated_count += 1

    return updated_count
