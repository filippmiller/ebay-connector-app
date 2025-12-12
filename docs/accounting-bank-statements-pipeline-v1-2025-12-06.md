# Bank Statements Pipeline v1.0 — Architecture & Implementation

**Date:** 2025-12-06  
**Status:** IMPLEMENTED  
**Author:** AI Assistant  

---

## 📋 Overview

This document describes the Bank Statements v1.0 pipeline architecture, which provides:

1. **Canonical JSON Schema** (`BankStatementV1.0`) - universal format for all banks
2. **Deterministic TD Bank PDF Parser** - no OpenAI dependency
3. **Rule-based Transaction Classification** - fast, predictable categorization
4. **Idempotent Import Pipeline** - duplicate detection and prevention
5. **Extensible Multi-bank Architecture** - easy to add new bank parsers

The existing OpenAI-based PDF parser remains functional for banks without dedicated parsers.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        BANK STATEMENT IMPORT PIPELINE                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌──────────────┐    ┌──────────────┐    ┌──────────────────────────────┐  │
│   │  TD Bank PDF │───▶│ TD Parser    │───▶│                              │  │
│   │              │    │ (no OpenAI)  │    │                              │  │
│   └──────────────┘    └──────────────┘    │                              │  │
│                                           │    Bank Statement v1.0       │  │
│   ┌──────────────┐                        │          JSON                │  │
│   │  JSON File   │───────────────────────▶│    (Canonical Format)        │  │
│   │              │                        │                              │  │
│   └──────────────┘                        │                              │  │
│                                           └───────────────┬──────────────┘  │
│   ┌──────────────┐    ┌──────────────┐                    │                 │
│   │  Any PDF     │───▶│ OpenAI Parser│───────────────────▶│                 │
│   │  (legacy)    │    │ (existing)   │                    ▼                 │
│   └──────────────┘    └──────────────┘    ┌──────────────────────────────┐  │
│                                           │    Transaction Classifier     │  │
│                                           │       (Rule-based)             │  │
│                                           └───────────────┬──────────────┘  │
│                                                           │                 │
│                                                           ▼                 │
│                                           ┌──────────────────────────────┐  │
│                                           │     Import Service            │  │
│                                           │  - Validation                 │  │
│                                           │  - Idempotency Check          │  │
│                                           │  - DB Storage                 │  │
│                                           └───────────────┬──────────────┘  │
│                                                           │                 │
│                                                           ▼                 │
│                           ┌────────────────────────────────────────────┐    │
│                           │                DATABASE                     │    │
│                           │  accounting_bank_statement                  │    │
│                           │  accounting_bank_row                        │    │
│                           │  accounting_transaction                     │    │
│                           └────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 📁 File Structure

```
backend/app/services/accounting_parsers/
├── __init__.py                    # Package exports
├── bank_statement_schema.py       # BankStatementV1 Pydantic schema
├── td_bank_parser.py              # TD Bank PDF parser (no OpenAI)
├── transaction_classifier.py      # Rule-based classifier
├── import_service.py              # Main import logic
├── csv_parser.py                  # Legacy CSV parser
├── xlsx_parser.py                 # Legacy XLSX parser
└── pdf_parser.py                  # Legacy OpenAI PDF parser
```

---

## 📄 Bank Statement v1.0 JSON Schema

### Core Types

```python
# Source metadata
class BankStatementSourceV1:
    statement_type: Literal["BANK_ACCOUNT"]
    bank_name: str           # "TD Bank"
    bank_code: str           # "TD"
    generated_by: str        # "td_pdf_parser_v1"
    generated_from_pdf: str  # Original filename

# Statement metadata
class BankStatementMetadataV1:
    bank_name: str
    product_name: str        # "TD Business Checking Account"
    account_owner: str       # "ACME CORP LLC"
    primary_account_number: str  # "****4567"
    statement_period_start: date
    statement_period_end: date
    currency: str            # "USD"

# Summary totals
class BankStatementSummaryV1:
    beginning_balance: Decimal
    ending_balance: Decimal
    electronic_deposits_total: Decimal
    checks_paid_total: Decimal
    # ... other category totals

# Transaction
class BankStatementTransactionV1:
    id: int                      # Line number
    posting_date: date
    description: str
    amount: Decimal              # Positive=credit, Negative=debit
    bank_section: BankSectionCode
    bank_subtype: str            # "CCD DEPOSIT", "ACH DEBIT"
    direction: TransactionDirection
    accounting_group: AccountingGroup
    classification: ClassificationCode
    status: TransactionStatus
    check_number: str | None
    balance_after: Decimal | None
```

### Example JSON

```json
{
  "schema_version": "1.0",
  "source": {
    "statement_type": "BANK_ACCOUNT",
    "bank_name": "TD Bank",
    "bank_code": "TD",
    "generated_by": "td_pdf_parser_v1"
  },
  "statement_metadata": {
    "bank_name": "TD Bank",
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
      "direction": "CREDIT",
      "accounting_group": "INCOME",
      "classification": "INCOME_EBAY_PAYOUT",
      "status": "OK"
    }
  ]
}
```

---

## 🏦 Classification Codes

### Accounting Groups

| Code | Description |
|------|-------------|
| `INCOME` | Revenue from sales |
| `COGS` | Cost of Goods Sold |
| `OPERATING_EXPENSE` | General operating expenses |
| `BANK_FEE` | Bank fees and charges |
| `INTEREST_INCOME` | Interest earned |
| `PAYROLL` | Wages and payroll taxes |
| `TAXES` | Tax payments |
| `TRANSFER` | Internal transfers |
| `OWNER_DRAW` | Owner withdrawals |
| `PERSONAL` | Personal expenses (flagged) |
| `OTHER` | Uncategorized |

### Classification Codes

| Code | Group | Description |
|------|-------|-------------|
| `INCOME_EBAY_PAYOUT` | INCOME | eBay marketplace payout |
| `INCOME_AMAZON_PAYOUT` | INCOME | Amazon seller payout |
| `INCOME_STRIPE` | INCOME | Stripe deposits |
| `INCOME_PAYPAL` | INCOME | PayPal deposits |
| `COGS_INVENTORY_PURCHASE` | COGS | Inventory purchases |
| `COGS_SHIPPING_SUPPLY` | COGS | Shipping supplies |
| `OPEX_SOFTWARE` | OPERATING_EXPENSE | Software subscriptions |
| `OPEX_SHIPPING` | OPERATING_EXPENSE | Outgoing shipping |
| `OPEX_RENT` | OPERATING_EXPENSE | Rent payments |
| `FEE_BANK_SERVICE` | BANK_FEE | Bank service fees |
| `PAYROLL_WAGE` | PAYROLL | Wage payments |
| `PAYROLL_TAX` | PAYROLL | Payroll taxes |
| `UNKNOWN` | OTHER | Needs manual classification |

---

## 🔌 API Endpoints

### New Endpoints (Bank Statement v1.0)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/accounting/bank-statements/supported-banks` | List banks with internal parsers |
| `POST` | `/api/accounting/bank-statements/import-json` | Import JSON file |
| `POST` | `/api/accounting/bank-statements/import-json-body` | Import JSON from request body |
| `POST` | `/api/accounting/bank-statements/upload-pdf-td` | Upload TD Bank PDF (no OpenAI) |
| `POST` | `/api/accounting/bank-statements/validate-json` | Validate JSON schema |

### Existing Endpoints (unchanged)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/accounting/bank-statements` | Upload any file (uses OpenAI for PDF) |
| `GET` | `/api/accounting/bank-statements` | List statements |
| `GET` | `/api/accounting/bank-statements/{id}` | Get statement details |
| `GET` | `/api/accounting/bank-statements/{id}/rows` | Get statement rows |

---

## 💾 Database Schema

### New Fields in `accounting_bank_statement`

| Column | Type | Description |
|--------|------|-------------|
| `raw_json` | JSONB | Full Bank Statement v1.0 JSON |
| `statement_hash` | TEXT | Idempotency hash (bank+account+period) |
| `source_type` | TEXT | JSON_UPLOAD, PDF_TD, CSV, XLSX, OPENAI |
| `bank_code` | TEXT | Short bank code (TD, BOA, etc.) |

### New Fields in `accounting_bank_row`

| Column | Type | Description |
|--------|------|-------------|
| `bank_code` | TEXT | Short bank code |
| `bank_section` | TEXT | Statement section (ELECTRONIC_DEPOSIT, etc.) |
| `bank_subtype` | TEXT | Transaction subtype (CCD DEPOSIT, etc.) |
| `direction` | TEXT | CREDIT or DEBIT |
| `accounting_group` | TEXT | Business classification group |
| `classification` | TEXT | Detailed classification code |
| `classification_status` | TEXT | OK, UNKNOWN, ERROR |
| `check_number` | TEXT | Check number if applicable |
| `raw_transaction_json` | JSONB | Raw transaction from Bank Statement v1.0 |

---

## 🚀 Usage Examples

### Import JSON via curl

```bash
curl -X POST "http://localhost:8000/api/accounting/bank-statements/import-json-body" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d @statement.json
```

### Upload TD Bank PDF

```bash
curl -X POST "http://localhost:8000/api/accounting/bank-statements/upload-pdf-td" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@td_statement_jan2025.pdf"
```

### Validate JSON

```bash
curl -X POST "http://localhost:8000/api/accounting/bank-statements/validate-json" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d @statement.json
```

---

## 🔧 Adding a New Bank Parser

To add support for a new bank (e.g., Bank of America):

1. **Create parser file**: `backend/app/services/accounting_parsers/boa_bank_parser.py`

2. **Implement parser class**:
```python
class BOABankPDFParser:
    def __init__(self, pdf_bytes: bytes, source_filename: str):
        ...
    
    def parse(self) -> BankStatementV1:
        # Extract text, parse transactions, return BankStatementV1
        ...
```

3. **Add to parser registry** in `td_bank_parser.py`:
```python
PDF_PARSER_REGISTRY = {
    "TD": parse_td_pdf_to_bank_statement_v1,
    "BOA": parse_boa_pdf_to_bank_statement_v1,  # Add here
}
```

4. **Add classification rules** in `transaction_classifier.py`:
```python
BOA_CLASSIFICATION_RULES = [...]
BANK_RULES["BOA"] = BOA_CLASSIFICATION_RULES
```

---

## 📊 Verification & Testing

### Balance Verification

The import service verifies that:
- `ending_balance - beginning_balance = sum(transactions)`
- Difference < $1.00 is acceptable (rounding)
- Larger differences trigger `verification_warning` status

### Testing the Pipeline

```python
# Test JSON import
from app.services.accounting_parsers import import_bank_statement_json

result = import_bank_statement_json(
    db=session,
    statement_data=json_data,
    user_id="user-123",
)
assert result.success
print(f"Imported {result.transactions_inserted} transactions")
```

---

## 🔮 Future Enhancements

### Priority 1: Classification Codes Management (User Request)
- **Database-driven codes**: Move classification codes from Python enums to `classification_codes` database table
- **Admin UI for codes**: Add/edit/delete classification codes through admin interface
- **User-defined rules**: Allow users to create custom classification rules without code changes

### Priority 2: Additional Features
1. **More Bank Parsers**: Bank of America, Citi, Chase, Wells Fargo
2. **AI Classification Hook**: For transactions that rules can't classify (404 transactions in last import)
3. **Custom Rule Editor**: UI for creating/editing classification rules
4. **Multi-account Consolidation**: Merge statements from multiple accounts
5. **Reconciliation**: Match bank transactions to eBay/Amazon payouts
6. **JSON Format Adapters**: Support for more JSON formats (QuickBooks, other accounting software)

### Tested Import Results (2025-12-06)
- **452 transactions** imported from TD Bank statement
- **Balance verification passed** (diff = $0.00)
- **48 classified** by rules, **404 need review** (mostly eBay purchases)


---

## 📝 Changelog

| Date | Version | Changes |
|------|---------|---------|
| 2025-12-06 | 1.0 | Initial implementation with TD Bank parser |

---

*Document generated as part of the Bank Statements Pipeline v1.0 implementation.*
