# Accounting Ledger & Bank Statements (MVP)

This document describes how the Accounting module implements a basic ledger using existing tables and endpoints, and how CSV/XLSX imports and deduplication work.

## 1. Core entities (Postgres, existing tables)

We intentionally reuse the existing Accounting tables instead of introducing new ones:

- `accounting_bank_statement` (`AccountingBankStatement`)
  - One row per imported bank statement file.
  - Key fields: `bank_name`, `account_last4`, `currency`, `statement_period_start`, `statement_period_end`, `status`.
  - Status values:
    - `uploaded` – file stored, parsing not done or failed.
    - `parsed` – CSV/XLSX rows parsed into `accounting_bank_row`.
    - `review_in_progress` – at least some rows were committed to the ledger.

- `accounting_bank_statement_file` (`AccountingBankStatementFile`)
  - Metadata for uploaded files: `file_type`, `storage_path`, `uploaded_at`, `uploaded_by_user_id`.

- `accounting_bank_row` (`AccountingBankRow`)
  - One row per parsed line in a bank statement (CSV/XLSX, or future PDF parser).
  - Key fields: `bank_statement_id`, `row_index`, `operation_date`, `description_raw`, `amount`, `balance_after`, `currency`, `parsed_status`, `match_status`, `expense_category_id`.
  - `parsed_status` is currently `auto_parsed` or `ignored`.
  - `match_status` is `unmatched`, `matched_to_transaction`, etc.

- `accounting_transaction` (`AccountingTransaction`)
  - The **unified ledger** of money movements.
  - Populated from:
    - Bank statements (`source_type = 'bank_statement'`).
    - Cash expenses (`source_type = 'cash_manual'`).
    - Other future sources.
  - Key fields: `date`, `amount`, `direction` (`'in'` / `'out'`), `source_type`, `source_id`, `account_name`, `expense_category_id`, `storage_id`, `is_personal`, `is_internal_transfer`.

- `accounting_transaction_log` (`AccountingTransactionLog`)
  - Append-only audit log of changes to `accounting_transaction` rows.
  - Used when creating transactions from bank rows and cash expenses.

These tables together form the Accounting ledger:

- **Statements** = `AccountingBankStatement` + `AccountingBankRow`.
- **Ledger**     = `AccountingTransaction` (plus its logs).

## 2. Import flow (CSV/XLSX)

### 2.1 Upload endpoint

Endpoint (existing, extended):

- `POST /api/accounting/bank-statements`

Auth:

- Admin-only via `require_admin_user`.

Input (multipart/form-data):

- `bank_name` – required, e.g. `TD`, `RELAY`, `GOOGLE_SHEET_TD_ALL_BANKS`.
- `account_last4` – optional, last 4 digits.
- `currency` – optional, e.g. `USD`.
- `statement_period_start`, `statement_period_end` – optional dates.
- `file` – single file (CSV, TXT, XLSX, XLS, PDF, etc.).

Behaviour:

1. Creates `AccountingBankStatement` in status `uploaded`.
2. Creates `AccountingBankStatementFile` with a `storage_path` under `accounting/bank_statements/{statement_id}/{filename}`.
3. Reads file bytes into memory.
4. If the file looks **table-like** (CSV/TXT/XLS/XLSX), attempts auto-parsing into `AccountingBankRow`.
   - CSV/TXT → `_parse_csv_rows`.
   - XLS/XLSX → `_parse_xlsx_rows`.
5. On successful parse, sets `AccountingBankStatement.status = 'parsed'`. On failure, logs a warning and keeps `status = 'uploaded'`.
6. For non-table formats (e.g. PDF), only metadata is stored; parsing is deferred for future PDF-specific parsers.

### 2.2 CSV parsing

`_parse_csv_rows(file_bytes: bytes) -> List[Dict[str, Any]]`:

- Decodes bytes as UTF-8 (with `errors='ignore'`).
- Uses `csv.DictReader` to read rows.
- Headers are normalized via `_normalize_header(name: str)`:
  - Strips leading/trailing whitespace.
  - Collapses internal whitespace.
  - Lowercases the result.
- Each row is returned as a dict with:
  - `"__index__"` – 1-based row index.
  - Keys in normalized form, e.g. `"transaction date"`, `"amount"`, `"running balance"`, `"description"`, etc.

### 2.3 XLSX parsing

`_parse_xlsx_rows(file_bytes: bytes) -> List[Dict[str, Any]]`:

- Uses `openpyxl.load_workbook` in read-only mode (dependency: `openpyxl`).
- Reads the first sheet, finds the first non-empty row and treats it as headers.
- Normalizes headers with the same `_normalize_header` helper.
- For each subsequent row, returns a dict:
  - `"__index__"` – sequential index starting from 1.
  - Keys are normalized header names.

If `openpyxl` is not installed, a runtime `RuntimeError` is raised with a clear message.

### 2.4 Row mapping into AccountingBankRow

For each parsed row:

- **Amount**:
  - Attempts to read from:
    - `amount`, `transaction amount`, `debit`, `credit`, `Amount`, `AMOUNT`.
  - Parsed as `Decimal` with `Decimal(str(value))`, defaulting to `0` on failure.

- **Balance after**:
  - Attempts to read from:
    - `balance`, `running balance`, `Balance`, `BALANCE`.
  - Parsed as `Decimal` or `None` if parsing fails.

- **Operation date**:
  - Attempts to read from:
    - `date`, `transaction date`, `operation date`, `posting date`, `Date`, `operation_date`.
  - Parsed via `date.fromisoformat(str(raw))`, with `None` on error.

- **Description**:
  - Attempts to read from:
    - `description`, `transaction description`, `details`, `memo`, `Description`, `DESC`.
  - Falls back to empty string if nothing is present.

Each row becomes an `AccountingBankRow` with:

- `bank_statement_id = stmt.id`.
- `row_index = __index__`.
- `operation_date`.
- `description_raw` (as determined above).
- `amount` (numeric, signed according to input data).
- `balance_after`.
- `currency = row['currency']` or statement currency.
- `parsed_status = 'auto_parsed'`.
- `match_status = 'unmatched'`.

If parsing all rows succeeds, the statement `status` is set to `parsed`; otherwise it remains `uploaded`.

## 3. From bank rows to unified ledger (commit)

Endpoint (existing, extended only in logic):

- `POST /api/accounting/bank-statements/{statement_id}/commit-rows`

Parameters:

- `statement_id` – target `AccountingBankStatement`.
- `row_ids: Optional[List[int]]` – explicit subset of rows to commit.
- `commit_all_non_ignored: bool` – if true, commits all rows whose `parsed_status != 'ignored'`.
- `default_account_name: Optional[str]` – override account label, otherwise `"{bank_name} ****{account_last4}"`.
- `mark_as_internal_transfer: bool` – mark resulting ledger entries as internal transfers.
- `mark_as_personal: bool` – mark as personal expenses.

### 3.1 Transaction creation

For each selected `AccountingBankRow` `r`:

1. Convert `r.amount` to `Decimal` and skip if it is `0`.
2. Derive `direction`:
   - `"in"` if amount > 0.
   - `"out"` otherwise.
3. Compute:
   - `txn_date_val = r.operation_date or statement_period_start or today()`.
   - `account_name_val = default_account_name or f"{stmt.bank_name} ****{stmt.account_last4}"`.
   - `description_val = r.description_clean or r.description_raw or ""`.

### 3.2 In-memory deduplication

Before inserting, we compute a **dedupe key** purely in Python and check for an existing matching transaction.

Helper (defined inside `commit_bank_rows`):

```python
_def make_dedupe_key(txn_date, direction, amount_abs, description, currency, account_name) -> str:
    # Normalize description (lowercase, collapse spaces)
    # Build string: "{date}|{direction}|{amount}|{normalized_desc}|{CURRENCY}|{account_name}"
    # Return SHA-256 hex digest.
```

For each row:

1. `amount_abs = abs(amount)`.
2. `dedupe_key = make_dedupe_key(...)` (used only in-memory for now).
3. Query `accounting_transaction` for an existing row with:
   - Same `date`.
   - Same `direction`.
   - Same `amount` (absolute value, ledger stores `amount` unsigned + `direction`).
   - Same `account_name`.
   - Same `description`.
   - `source_type == 'bank_statement'`.
4. If such a transaction exists:
   - Mark the bank row as matched: `match_status = 'matched_to_transaction'`.
   - Do **not** create a new `AccountingTransaction`.

If no such transaction exists, a new `AccountingTransaction` is created with:

- `date = txn_date_val`.
- `amount = amount_abs`.
- `direction = 'in' | 'out'`.
- `source_type = 'bank_statement'`.
- `source_id = bank_row.id`.
- `account_name = account_name_val`.
- `description = description_val`.
- `expense_category_id = bank_row.expense_category_id`.
- `is_personal`, `is_internal_transfer` from request flags.

An `AccountingTransactionLog` entry is written with `field_name='create'` and
`new_value='created from bank_statement_row'`.

Finally, the statement `status` is set to `review_in_progress`, and the API
returns `{"created": <count>, "statement_status": ...}`.

### 3.3 Deduplication guarantees

With this approach:

- Re-importing the **same CSV/XLSX** or fragments (e.g. overlapping date ranges) will not produce duplicate `accounting_transaction` rows, as long as:
  - `date`, `direction`, absolute `amount`, `account_name`, and normalized description are the same.
- Bank rows for such duplicates will still be marked as `matched_to_transaction`, so they appear as reconciled but do not inflate the ledger.

This is intentionally implemented **without schema changes** so it works even
while production migrations are blocked.

## 4. Ledger endpoint and aggregates

Endpoint (existing, extended):

- `GET /api/accounting/transactions`

Filters:

- `date_from`, `date_to` – by `date`.
- `category_id` – by `expense_category_id`.
- `source_type` – e.g. `bank_statement`, `cash_manual`.
- `storage_id`.
- `is_personal`.
- `is_internal_transfer`.
- `limit`, `offset` – pagination.

Changes for Ledger view:

- The endpoint now also computes **aggregated totals** for the current filter:
  - `total_in` – sum of `amount` where `direction = 'in'`.
  - `total_out` – sum of `amount` where `direction = 'out'`.
  - `net = total_in - total_out`.
- Totals are computed using SQL expressions mirroring the active filters.

Response shape (simplified):

```json
{
  "rows": [...],
  "total": 123,
  "limit": 200,
  "offset": 0,
  "total_in": 10000.0,
  "total_out": 7500.0,
  "net": 2500.0
}
```

Existing consumers that only use `rows/total/limit/offset` remain compatible.

## 5. Frontend: Accounting UI

File: `frontend/src/pages/AccountingPage.tsx`

### 5.1 Tabs

Accounting is still admin-only. Tabs were adjusted as follows:

- **Statements** (was "Bank Statements")
  - Route prefix: `/accounting/bank-statements`.
  - Uses `BankStatementsList` and `BankStatementDetail` components.
  - Backed by `/api/accounting/bank-statements` and related row/detail endpoints.

- **Cash Expenses**
  - Unchanged; uses `CashExpensesTab` with `/api/accounting/cash-expenses` and `/api/accounting/cash-expenses` POST.

- **Ledger** (was "Transactions")
  - Route prefix: `/accounting/transactions`.
  - Uses `TransactionsTab` as the primary Ledger UI.

### 5.2 Ledger tab (TransactionsTab)

`TransactionsTab` now behaves as a ledger view:

- Filters:
  - Date range (`date_from`, `date_to`).
  - `source_type` (e.g. `bank_statement` / `cash_manual`).
  - `storage_id`.
  - `category_id`.
  - Flags: `is_personal`, `is_internal_transfer`.
- Uses `DataGridPage` with `gridKey="accounting_transactions"` to render `accounting_transaction` rows.
- Row click selects a transaction for editing (category, storage, flags) and PATCH-es via `/api/accounting/transactions/{id}`.

New behaviour:

- `TransactionsTab` now fetches aggregated totals from
  `GET /api/accounting/transactions` (same filters, `limit=1` for efficiency) and
  displays a small summary card above the filters:
  - **Total In** – green.
  - **Total Out** – red.
  - **Net** – green if positive, red if negative.

This makes the tab act as the unified ledger for all accounts and sources.

## 6. Usage patterns

### 6.1 Importing a bank CSV/XLSX from an online bank

1. Go to **Accounting → Statements**.
2. Fill in `Bank name`, `Account last4`, `Currency`, optional period.
3. Upload the CSV or XLSX file and submit.
4. The backend parses rows into `accounting_bank_row`.
5. Open the statement detail; review rows, optionally edit categories or mark some as `ignored`.
6. Use "Commit selected" or "Commit all non-ignored" to create ledger entries:
   - New `accounting_transaction` rows are created **only** for transactions that do not match an existing row under the dedupe rules.

### 6.2 Re-importing the same file or updated Google Sheet export

1. Upload the updated CSV/XLSX again as a new statement (e.g. with the same bank name and last4).
2. The parser will create new `accounting_bank_row` records.
3. On commit, deduplication logic will:
   - Recognize already-imported transactions by `(date, direction, amount, account_name, normalized description)`.
   - Skip creation of duplicate `accounting_transaction` rows.
   - Still mark corresponding bank rows as matched.

This allows safe repeated imports and partial overlaps without polluting the ledger.

## 7. Future extensions

The current design is intentionally conservative:

- No new tables or migrations are required; everything is built on top of the existing Accounting schema.
- Deduplication is purely logical (in code) rather than enforced by a DB constraint; once production migrations are unblocked, a `dedupe_key` column and unique index could be added to harden guarantees.
- PDF support is still stubbed at the upload stage (files are registered but not parsed). Dedicated parsers for TD/Relay PDF statements can be plugged into the same flow by mapping parsed rows into the `AccountingBankRow` structure.
- Additional sources (Google Sheets via API, bank APIs) can reuse the same pattern:
  - Normalize incoming rows to the same logical fields.
  - Insert into `accounting_bank_row`.
  - Rely on the same dedupe logic when committing to `accounting_transaction`.

## 8. Summary

- **Statements**: `AccountingBankStatement` + `AccountingBankRow` give a per-file view of imported raw transactions, with CSV/XLSX parsing and admin review tools.
- **Ledger**: `AccountingTransaction` is the single source of truth for money movements (bank + cash), now exposed with totals in the **Ledger** tab.
- **Deduplication**: Implemented in the commit step, preventing duplicate ledger entries across repeated imports without schema changes.
