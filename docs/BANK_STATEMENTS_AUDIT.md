# Bank Statements & Accounting Audit

## 1. Overview

The codebase currently contains a foundational implementation of an accounting system, including bank statement uploads, basic CSV/XLSX parsing, and a double-entry-style ledger (`AccountingTransaction`).

**Key Findings:**
*   **Status**: Partial implementation.
*   **PDF Parsing**: **Not implemented**. A stub exists in `backend/app/services/accounting_parsers/pdf_parser.py` but raises `NotImplementedError`.
*   **CSV/XLSX Parsing**: Implemented but located directly in the router (`backend/app/routers/accounting.py`). It uses a "best-effort" header normalization approach.
*   **AI/LLM Integration**: **Missing** for accounting. There is a generic `ai_rules_engine.py` for generating SQL from natural language, but it is not connected to transaction categorization or parsing.
*   **Smart Rules**: **Missing**. There is no `bank_rules` table or logic to auto-categorize transactions based on patterns.
*   **Frontend**: A functional UI exists (`AccountingPage.tsx`) for uploading files, viewing rows, and managing the ledger.

## 2. Repository Map

The following files contain the core banking and accounting logic:

### Files with Banking-Related Logic

| # | File path | Layer | Role | Mentions |
| :--- | :--- | :--- | :--- | :--- |
| 1 | `backend/app/routers/accounting.py` | Backend | Controller / Logic | `bank_statements`, `upload`, `parse_csv`, `AccountingTransaction` |
| 2 | `backend/app/models_sqlalchemy/models.py` | Backend | DB Schema | `AccountingBankStatement`, `AccountingBankRow`, `AccountingTransaction` |
| 3 | `backend/app/services/accounting_parsers/pdf_parser.py` | Backend | Service (Stub) | `parse_td_pdf`, `parse_relay_pdf`, `NotImplementedError` |
| 4 | `backend/alembic/versions/accounting_20251118.py` | Backend | DB Migration | Table definitions for `accounting_*` tables |
| 5 | `frontend/src/pages/AccountingPage.tsx` | Frontend | UI Page | `BankStatementsList`, `BankStatementDetail`, `TransactionsTab` |
| 6 | `backend/app/services/ai_rules_engine.py` | Backend | Service | Generic AI SQL generation (not yet used in accounting) |

### Banking Features and Endpoints

| ID | File path | Symbol | Type | Purpose | Input | Output | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | `backend/app/routers/accounting.py` | `upload_bank_statement` | API Endpoint | Uploads file, creates DB record, attempts CSV/XLSX parse | `multipart/form-data` (File) | `AccountingBankStatement` | Production (Basic) |
| 2 | `backend/app/routers/accounting.py` | `_parse_csv_rows` | Function | Parses CSV bytes into dict rows with normalized headers | `bytes` | `List[Dict]` | Production (Basic) |
| 3 | `backend/app/routers/accounting.py` | `commit_bank_rows` | API Endpoint | Converts raw bank rows into ledger transactions | `statement_id` | `AccountingTransaction` count | Production |
| 4 | `backend/app/services/accounting_parsers/pdf_parser.py` | `parse_generic_pdf` | Function | Stub for PDF parsing | `bytes` | `NotImplementedError` | **Unimplemented** |
| 5 | `backend/app/routers/accounting.py` | `list_bank_statements` | API Endpoint | Lists uploaded statements with status | `Query params` | JSON List | Production |
| 6 | `frontend/src/pages/AccountingPage.tsx` | `BankStatementsList` | UI Component | UI for uploading and listing statements | User Interaction | UI | Production |

## 3. Issues and Potential Problems

| # | File path | Location | Issue type | Description | Suggested fix | Severity |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | `backend/app/routers/accounting.py` | `upload_bank_statement` | Missing Feature | PDF files are accepted but explicitly marked as "error_pdf_not_supported". | Implement PDF parsing in `pdf_parser.py` using `pdfplumber` + OpenAI. | High |
| 2 | `backend/app/routers/accounting.py` | `_parse_csv_rows` | Code Smell | Parsing logic is tightly coupled within the router file. | Move all parsing logic (CSV/XLSX) to `backend/app/services/accounting_parsers/`. | Medium |
| 3 | `backend/app/routers/accounting.py` | `_make_dedupe_key` | Logic / Smell | Deduplication logic is hardcoded in the router. | Move to a service or model method to ensure consistency. | Low |
| 4 | `backend/app/models_sqlalchemy/models.py` | `AccountingBankRow` | Missing Feature | No support for "Smart Rules" or auto-categorization beyond basic manual assignment. | Add `bank_rules` table and integrate an AI/Regex matching engine. | High |
| 5 | `backend/app/routers/accounting.py` | `upload_bank_statement` | Security / Infra | File storage is "environment-specific" and might just be reading into memory/temp. | Ensure files are persisted to S3/Supabase Storage for reliability. | Medium |

## 4. DB Schema

The current schema (defined in `models.py` and `accounting_20251118.py`) includes:

*   **`accounting_bank_statement`**: Tracks the file upload, bank name, period, and status (`uploaded`, `parsed`, etc.).
*   **`accounting_bank_statement_file`**: Links the physical file path to the statement.
*   **`accounting_bank_row`**: Represents a raw line from the statement (date, description, amount).
    *   Has `parsed_status` (`auto_parsed`, `ignored`) and `match_status`.
    *   Has `expense_category_id` (FK to `accounting_expense_category`).
*   **`accounting_transaction`**: The "Ledger" table. Represents the actual financial record after a row is "committed".
    *   Includes `source_type` (`bank_statement`, `cash_manual`) and `source_id`.
*   **`accounting_expense_category`**: Simple dictionary of categories (e.g., "Office Supplies", "Rent").

**Missing:**
*   `bank_rules`: Table for storing regex/AI rules for auto-categorization.
*   `bank_files`: (The current `accounting_bank_statement` serves this purpose, but could be renamed or expanded).

## 5. Recommendations

1.  **Implement PDF Parsing**:
    *   Flesh out `backend/app/services/accounting_parsers/pdf_parser.py`.
    *   Use a library like `pdfplumber` to extract text/tables.
    *   Integrate OpenAI (as requested) to structure the extracted text into JSON transactions.

2.  **Refactor Parsing Logic**:
    *   Move `_parse_csv_rows` and `_parse_xlsx_rows` from `accounting.py` to `backend/app/services/accounting_parsers/csv_parser.py` (and `xlsx_parser.py`).
    *   Create a unified `StatementParser` interface that selects the correct parser based on file type.

3.  **Develop "Smart Brain" (Categorization Engine)**:
    *   Create a new table `accounting_bank_rules` (pattern, category_id, priority).
    *   Implement a service that runs these rules against `AccountingBankRow` records upon import.
    *   Add an "Auto-Categorize" button in the UI that uses OpenAI to suggest categories for unmatched rows.

4.  **Enhance UI**:
    *   Add a "Rules" management tab in `AccountingPage.tsx`.
    *   Allow users to create rules directly from a transaction row ("Always categorize 'Starbucks' as 'Meals'").

5.  **Storage**:
    *   Verify where `storage_path` actually points and ensure it's using a durable object store (S3/Supabase) rather than local ephemeral disk.

## 6. Next Steps

1.  **Design `bank_rules` Schema**: Create a migration for the rules table.
2.  **Implement PDF Parser**: Connect `pdf_parser.py` to OpenAI for intelligent extraction.
3.  **Refactor Router**: Move parsing logic out of `accounting.py`.
4.  **Update UI**: Add the "Rules" tab and "Auto-Categorize" functionality.
