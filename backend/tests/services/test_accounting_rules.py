import pytest
from unittest.mock import MagicMock
from app.services.accounting_rules_engine import apply_rules_to_bank_rows
from app.models_sqlalchemy.models import AccountingBankRow, AccountingBankRule

def test_apply_rules_simple_contains():
    # Setup mock DB session
    mock_db = MagicMock()
    
    # Setup rules
    rule1 = AccountingBankRule(
        id=1,
        pattern_type="contains",
        pattern_value="UBER",
        expense_category_id=101,
        priority=10,
        is_active=True
    )
    rule2 = AccountingBankRule(
        id=2,
        pattern_type="contains",
        pattern_value="AMZN",
        expense_category_id=102,
        priority=20,
        is_active=True
    )
    
    # Mock query return
    mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [rule1, rule2]
    
    # Setup rows
    row1 = AccountingBankRow(id=1, description_raw="UBER TRIP 123", expense_category_id=None)
    row2 = AccountingBankRow(id=2, description_raw="AMZN MKTPLACE", expense_category_id=None)
    row3 = AccountingBankRow(id=3, description_raw="UNKNOWN VENDOR", expense_category_id=None)
    row4 = AccountingBankRow(id=4, description_raw="UBER EATS", expense_category_id=None) # Should match rule1
    
    rows = [row1, row2, row3, row4]
    
    # Apply rules
    count = apply_rules_to_bank_rows(mock_db, rows)
    
    assert count == 3
    assert row1.expense_category_id == 101
    assert row1.parsed_status == "auto_categorized"
    
    assert row2.expense_category_id == 102
    assert row2.parsed_status == "auto_categorized"
    
    assert row3.expense_category_id is None
    
    assert row4.expense_category_id == 101

def test_apply_rules_priority():
    mock_db = MagicMock()
    
    # Rule 1: "AMAZON" -> 101 (Priority 10)
    # Rule 2: "AMAZON WEB SERVICES" -> 102 (Priority 5) - Higher priority!
    
    rule1 = AccountingBankRule(pattern_type="contains", pattern_value="AMAZON", expense_category_id=101, priority=10, is_active=True)
    rule2 = AccountingBankRule(pattern_type="contains", pattern_value="AMAZON WEB SERVICES", expense_category_id=102, priority=5, is_active=True)
    
    # Return in priority order (rule2 first)
    mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [rule2, rule1]
    
    row = AccountingBankRow(description_raw="PAYMENT TO AMAZON WEB SERVICES", expense_category_id=None)
    
    apply_rules_to_bank_rows(mock_db, [row])
    
    # Should match rule2 because it's checked first
    assert row.expense_category_id == 102

def test_apply_rules_regex():
    mock_db = MagicMock()
    
    rule = AccountingBankRule(
        pattern_type="regex",
        pattern_value=r"^AWS \d+$", # Starts with AWS, space, digits, end of string
        expense_category_id=200,
        priority=10,
        is_active=True
    )
    
    mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [rule]
    
    row1 = AccountingBankRow(description_raw="AWS 12345", expense_category_id=None)
    row2 = AccountingBankRow(description_raw="AWS SOMETHING ELSE", expense_category_id=None)
    
    apply_rules_to_bank_rows(mock_db, [row1, row2])
    
    assert row1.expense_category_id == 200
    assert row2.expense_category_id is None
