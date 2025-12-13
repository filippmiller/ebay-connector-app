# Bank Statements Pipeline Documentation

## Overview
The bank statement pipeline allows users to upload, parse, and categorize bank transactions from various sources (CSV, XLSX, PDF). It includes deduplication logic to prevent double-entry and a rules engine for auto-categorization.

## Architecture

### 1. Upload & Deduplication
- **Endpoint**: `POST /api/accounting/bank-statements`
- **File Deduplication**: SHA256 hash of the file content is computed. If a file with the same hash exists, the upload is rejected (or returns existing).
- **Row Deduplication**: Each row generates a `dedupe_key` (SHA256 of statement_id + date + amount + description). This ensures idempotency if rows are re-processed.

### 2. Parsers
Located in `backend/app/services/accounting_parsers/`:
- **CSV**: `csv_parser.py` - Normalizes headers and extracts date/amount/description.
- **XLSX**: `xlsx_parser.py` - Uses `openpyxl` to read Excel files.
- **PDF**: `pdf_parser.py` - Uses `pdfplumber` for text extraction and OpenAI (GPT-4o) to structure the data into JSON.

### 3. Rules Engine
Located in `backend/app/services/accounting_rules_engine.py`.
- **Model**: `AccountingBankRule`
- **Logic**:
    - Rules are applied in order of `priority` (ascending).
    - Supports `contains` (substring match) and `regex` patterns.
    - If a match is found, the row's `expense_category_id` is set, and `parsed_status` becomes `auto_categorized`.

### 4. Transaction Creation
- **Endpoint**: `POST /api/accounting/bank-statements/{id}/commit-rows`
- **Logic**: Converts `AccountingBankRow` into `AccountingTransaction` (the ledger).
- **Linking**: `AccountingTransaction.bank_row_id` links back to the source row.

## Usage

### Managing Rules
1. Go to **Accounting > Rules**.
2. Create a new rule (e.g., Pattern: "UBER", Category: "Transport").
3. Set priority (default 10). Lower numbers run first.

### Uploading Statements
1. Go to **Accounting > Statements**.
2. Upload a file.
3. The system will parse and auto-categorize rows based on active rules.
4. Review rows in the detail view.
5. Commit valid rows to the ledger.

## Development

### Adding a New Parser
1. Create `backend/app/services/accounting_parsers/new_format_parser.py`.
2. Implement a function returning `List[Dict]`.
3. Register it in `backend/app/routers/accounting.py`.

### Running Tests
```bash
pytest backend/tests/services/test_accounting_parsers.py
pytest backend/tests/services/test_accounting_rules.py
```
