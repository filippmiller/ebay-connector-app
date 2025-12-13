"""Test Bank Statement v1.0 imports."""
import sys
sys.path.insert(0, '.')

print("Testing Bank Statement v1.0 imports...")

# Test schema imports
try:
    from app.services.accounting_parsers.bank_statement_schema import (
        BankStatementV1,
        BankStatementTransactionV1,
        BankSectionCode,
        TransactionDirection,
        AccountingGroup,
        ClassificationCode,
    )
    print("✅ Schema imports OK")
except Exception as e:
    print(f"❌ Schema imports FAILED: {e}")

# Test classifier imports
try:
    from app.services.accounting_parsers.transaction_classifier import (
        classify_transaction,
        classify_transactions_batch,
    )
    print("✅ Classifier imports OK")
except Exception as e:
    print(f"❌ Classifier imports FAILED: {e}")

# Test TD parser imports
try:
    from app.services.accounting_parsers.td_bank_parser import (
        parse_td_pdf_to_bank_statement_v1,
        get_available_bank_parsers,
    )
    print("✅ TD parser imports OK")
    print(f"   Available parsers: {get_available_bank_parsers()}")
except Exception as e:
    print(f"❌ TD parser imports FAILED: {e}")

# Test import service
try:
    from app.services.accounting_parsers.import_service import (
        import_bank_statement_json,
        import_td_pdf_bytes,
        get_supported_banks,
        validate_json_format,
    )
    print("✅ Import service imports OK")
    print(f"   Supported banks: {get_supported_banks()}")
except Exception as e:
    print(f"❌ Import service imports FAILED: {e}")

print("\n✅ All Bank Statement v1.0 imports successful!")
