"""Parsing helpers for Accounting / Ledger imports.

This package contains:
- Bank Statement v1.0 schema (bank_statement_schema.py)
- TD Bank PDF parser (td_bank_parser.py) - NO OpenAI
- Transaction classifier (transaction_classifier.py) - rule-based
- Import service (import_service.py) - main import logic
- Legacy parsers: csv_parser.py, xlsx_parser.py, pdf_parser.py (OpenAI-based)
"""

from .bank_statement_schema import (
    BankStatementV1,
    BankStatementTransactionV1,
    BankSectionCode,
    TransactionDirection,
    AccountingGroup,
    ClassificationCode,
    validate_bank_statement_json,
)

from .import_service import (
    import_bank_statement_json,
    import_td_pdf_bytes,
    get_supported_banks,
    validate_json_format,
    ImportResult,
)

from .td_bank_parser import (
    parse_td_pdf_to_bank_statement_v1,
    get_available_bank_parsers,
    parse_pdf_by_bank_code,
)

from .transaction_classifier import (
    classify_transaction,
    classify_transactions_batch,
    get_classification_summary,
)

__all__ = [
    # Schema
    "BankStatementV1",
    "BankStatementTransactionV1",
    "BankSectionCode",
    "TransactionDirection",
    "AccountingGroup",
    "ClassificationCode",
    "validate_bank_statement_json",
    # Import service
    "import_bank_statement_json",
    "import_td_pdf_bytes",
    "get_supported_banks",
    "validate_json_format",
    "ImportResult",
    # Parsers
    "parse_td_pdf_to_bank_statement_v1",
    "get_available_bank_parsers",
    "parse_pdf_by_bank_code",
    # Classifier
    "classify_transaction",
    "classify_transactions_batch",
    "get_classification_summary",
]
