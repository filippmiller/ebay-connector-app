# Accounting 2 — Inventory & Redesign Plan

## 1. Existing Accounting UI & API Inventory (v1)

### 1.1 Frontend entrypoints

- `frontend/src/pages/AccountingPage.tsx`
  - Exposes `/accounting/*` routes and tabs:
    - **Statements**: `/accounting/bank-statements` → `BankStatementsList`
    - **Statement Detail**: `/accounting/bank-statements/:id` → `BankStatementDetail`
    - **Cash Expenses**: `/accounting/cash` → `CashExpensesTab`
    - **Ledger**: `/accounting/transactions` → `TransactionsTab`
    - **Rules**: `/accounting/rules` → `RulesTab` (with `RulesSubTab` + `ClassificationCodesManager`)
  - Guards access by `user.role === 'admin'`.

### 1.2 Backend concepts (from docs)

From `docs/accounting_ledger_overview.md` and `docs/accounting-bank-statements-pipeline-v1-2025-12-06.md` the current schema / entities are:

- `accounting_bank_statement`
- `accounting_bank_statement_file`
- `accounting_bank_row`
- `accounting_transaction`
- `accounting_transaction_log`
- `accounting_process_log`
- Classification-related tables (from UI + docs):
  - `accounting_classification_groups` (inferred)
  - `accounting_classification_codes`
  - `accounting_rules`
  - `accounting_categories`

### 1.3 Key existing endpoints used by UI

Bank statements & rows:
- `POST   /api/accounting/bank-statements` — upload (CSV/XLSX/PDF/OpenAI)
- `GET    /api/accounting/bank-statements` — list
- `GET    /api/accounting/bank-statements/{id}` — summary
- `GET    /api/accounting/bank-statements/{id}/rows` — rows (with search & pagination)
- `POST   /api/accounting/bank-statements/{id}/commit-rows` — commit to ledger
- `DELETE /api/accounting/bank-statements/{id}` — delete statement + rows + committed ledger entries

Internal JSON / TD PDF import:
- `POST /api/accounting/bank-statements/import-json`
- `POST /api/accounting/bank-statements/import-json-body`
- `POST /api/accounting/bank-statements/upload-pdf-td`
- `POST /api/accounting/bank-statements/validate-json`

Ledger transactions:
- `GET  /api/accounting/transactions` — ledger with aggregates (`total_in`, `total_out`, `net`)
- `PUT  /api/accounting/transactions/{id}` — update fields from UI

Cash expenses:
- `GET  /api/accounting/cash-expenses` — grid
- `POST /api/accounting/cash-expenses` — create

Rules & categories:
- `GET    /api/accounting/categories`
- `GET    /api/accounting/rules`
- `POST   /api/accounting/rules`
- `DELETE /api/accounting/rules/{id}`
- `GET    /api/accounting/classification-groups`
- `GET    /api/accounting/classification-codes`
- `POST   /api/accounting/classification-codes`
- `PUT    /api/accounting/classification-codes/{id}`
- `DELETE /api/accounting/classification-codes/{id}`

### 1.4 Supabase-specific pieces

- Migration `20251205131610_create_bank_statements_bucket.sql` — placeholder (currently empty in repo, will remain unused once the new Accounting 2 migration below is active).
- Migration `20251205133218_audit_logging_and_raw_response.sql` — adds `raw_openai_response` to `accounting_bank_statement` and creates `accounting_process_log` table with `ON DELETE CASCADE` by `bank_statement_id`.
- Migration `20251208110000_accounting2_staging_and_bucket.sql` — **implemented**:
  - Creates Supabase Storage bucket `accounting_bank_statements` for original PDF/CSV/XLSX files.
  - Creates `public.transaction_spending` staging table for parsed transactions pending user approval.

## 2. Target Design — "Accounting 2" Navigation & Grids

### 2.1 New navigation entry

- New route root: `/accounting2/*` (parallel to existing `/accounting/*`).
- New page component: `frontend/src/pages/Accounting2Page.tsx`.
- New navbar / router entry in `frontend/src/App.tsx` pointing to `Accounting2Page`.

Tabs under Accounting 2:
- **Bank Statements 2** — list of statements with selection + guarded delete flow.
- **Statement Review 2** — modal-driven flow for freshly uploaded statements (preview parsed transactions before commit).
- **Ledger 2** — ledger grid with totals, filters, and strong connection to statements.
- **Cash Expenses 2** — reimplemented grid & form (fixing broken current tab).
- **Rules 2** — reuse backend endpoints + improved grid and confirmation UX.

### 2.2 Core UX rules (as per spec)

1. **Statement ↔ Transactions ownership**
   - Every transaction belongs to exactly one statement.
   - Transactions **cannot exist** without a parent statement.
   - Deleting a statement deletes all attached transactions.

2. **Upload & review flow**
   - User uploads a PDF statement.
   - Parser runs (existing JSON/TD PDF logic can be reused).
   - **Before commit**, results live in a temporary table (planned: `transaction_spending`).
   - A modal shows:
     - Bank name (e.g. `TD Bank`).
     - Account (masked last4 / IBAN part if available).
     - Date interval.
     - Total transaction count (e.g. `450`).
     - Grid of parsed transactions.
   - User actions in modal:
     - **View PDF in Supabase bucket** (PDF is uploaded first and visible in a viewer link).
     - **Accept all transactions** → move from `transaction_spending` into final tables and mark statement as "committed".
     - **Reject / cancel** → discard `transaction_spending` rows and do **not** persist statement.

3. **Deletion UX**
   - In statements grid: checkbox selection + `Delete` button.
   - Delete triggered flow:
     1. Modal: "Точно ли хотите удалить?" with statement summary.
     2. Second modal step: user must type **`Delete`** to confirm (case-sensitive per UX decision).
   - On confirmation:
     - Delete statement.
     - Delete all attached transactions.
     - Delete raw logs and audit rows.
     - (If possible) delete PDFs from Supabase bucket.

4. **PDF storage**
   - For each statement:
     - Store original PDF in Supabase Storage bucket, path convention like `accounting/bank_statements/{statement_id}/original.pdf`.
     - Also store parsed JSON (`BankStatementV1.0`) in `accounting_bank_statement.raw_json`.

5. **Rules application**
   - Rules UI reused, but all grid rendering is rewritten.
   - When user defines a rule (e.g. substring in description), backend:
     - Finds all candidate transactions.
     - Returns a count and preview list.
   - Frontend shows modal with *"N matching transactions"* and preview grid.
   - Only after user confirms, changes are applied in DB.

### 2.3 New / adjusted DB pieces (high-level)

- New table (temporary bucket of unapproved rows): `transaction_spending` — holds parsed transactions from a newly uploaded statement **before** user approval.
- Existing tables reused for committed data:
  - `accounting_bank_statement` (+ `raw_json`, `raw_openai_response`, etc.).
  - `accounting_bank_row` or successor for parsed lines.
  - `accounting_transaction` as canonical ledger.

## 3. Planned New Frontend Files (Accounting 2)

_All code will be new (no direct reuse), but behaviour will be based on existing v1 functions._

1. `frontend/src/pages/Accounting2Page.tsx`
   - New top-level page with tabs for Accounting 2.
   - Wiring for `/accounting2/*` routes.

2. `frontend/src/pages/accounting2/StatementsPage2.tsx`
   - Grid showing bank statements (v2 design).
   - Supports:
     - Filters (bank, status, date range).
     - Row selection.
     - Delete with double-confirm flow.
     - Link to open Statement Review modal / detail.

3. `frontend/src/pages/accounting2/StatementReviewModal2.tsx`
   - Modal triggered immediately after upload or from statements grid.
   - Shows parsed metadata + parsed transactions grid (from `transaction_spending` or equivalent endpoint).
   - Buttons: **Approve all**, **Reject all**.

4. `frontend/src/pages/accounting2/LedgerPage2.tsx`
   - Ledger grid bound tightly to statements.
   - Reuses `/api/accounting/transactions` endpoints but surfaces statement link and aggregates.

5. `frontend/src/pages/accounting2/CashExpensesPage2.tsx`
   - Fully working replacement for broken Cash Expenses tab.
   - Similar layout as `CashExpensesTab` but with explicit validation, error handling, and DataGrid configuration decoupled from v1.

6. `frontend/src/pages/accounting2/RulesPage2.tsx`
   - Reuses rules endpoints.
   - New grids and modals to:
     - Show all rules.
     - Preview affected transactions before applying a new rule.

7. Shared components under `frontend/src/components/accounting2/`
   - `StatementSummary2.tsx` — header block showing bank / period / status.
   - `TransactionsPreviewGrid2.tsx` — table for parsed transactions in modal.
   - `DeleteConfirmModal2.tsx` — reusable two-step delete modal.

## 4. Planned New Backend / Supabase Artifacts (high-level)

> NOTE: Implementation will be done in the backend repo + Supabase migrations via CLI / Railway; listed here for traceability.

- Supabase Storage:
  - Bucket: `accounting_bank_statements` (from existing migration `20251205131610_create_bank_statements_bucket.sql`, to be filled).
- New migration(s):
  - Define `transaction_spending` table (staging for parsed transactions).
  - Ensure `accounting_bank_statement` has:
    - `raw_json` JSONB.
    - `statement_hash` TEXT.
    - `source_type`, `bank_code` fields as per docs.
- Service endpoints (to be implemented / extended in backend):
  - `POST /api/accounting2/bank-statements/upload` — PDF upload → Supabase bucket + parse → `transaction_spending` + draft `accounting_bank_statement`.
  - `POST /api/accounting2/bank-statements/{id}/approve` — move from `transaction_spending` to final tables.
  - `POST /api/accounting2/bank-statements/{id}/reject` — delete draft statement + staging rows + PDF.

## 5. Migration / Deletion Plan for Old Accounting

1. Build and stabilize `Accounting 2` UI and endpoints alongside existing `/accounting`.
2. Once feature parity and business rules are verified:
   - Point users to `/accounting2` instead of `/accounting`.
3. After acceptance:
   - Remove old frontend page `frontend/src/pages/AccountingPage.tsx` and related v1-only components.
   - Remove `gridKey` configs specific to old accounting grids.
   - Optionally deprecate / remove legacy endpoints that are no longer used.

---

This document will be updated as we implement each piece of Accounting 2 (frontend, backend endpoints, Supabase migrations) and as we identify additional files that should be deleted from the old Accounting implementation.