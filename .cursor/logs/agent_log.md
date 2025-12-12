2025-12-09T21:00:00Z - Added sortable preview grid (click headers to sort by date/section/amount/etc) + Balance Reconciliation Panel showing Beginning + Credits + Debits = Calculated vs Expected with variance; Accept button shows warning if unbalanced
2025-12-09T20:30:00Z - Fixed 56052 bug in _extract_summary: now searches ONLY in ACCOUNT SUMMARY section (removed DOTALL that was capturing wrong values); improved period_dates regex to handle "Jan 012025" (no space); added plural/singular forms for Other Credit[s], Interest Earned; increased desc limit to 800 chars
2025-12-09T20:00:00Z - Added diagnostic logging to approve/upload endpoints (statement_id, row counts, verification); fixed frontend alert to properly serialize error objects; pushed to main
2025-12-09T19:45:00Z - Applied Supabase migrations (bank_section column already existed); investigating "No staged transactions to approve" error
2025-12-09T19:30:00Z - Fixed TD parser based on 6-point code review: (1) period_dates regex now handles optional year + "through/to" separators; (2) header search expanded to first 3 pages; (3) ACCOUNT SUMMARY uses regex with IGNORECASE; (4) pdfplumber uses layout=True + x/y_tolerance; (5) finditer for ALL DAILY ACCOUNT ACTIVITY sections across pages; (6) added period_any debug pattern
2025-12-09T19:00:00Z - Added diagnostic logging to TD parser for header/period/summary debugging: logs first page preview (2000 chars), header text (800 chars), period regex match result, ACCOUNT SUMMARY section preview; pushed to main for production deployment
2025-12-09T18:00:00Z - Major TD parser rewrite focusing on header/summary: new period_dates regex (6 capture groups for month/day/year), _extract_summary now finds Subtotals from transaction sections, section detection uses LONGEST-FIRST keyword order (avoids "Deposits" matching "Electronic Deposits"), removed space sensitivity in section matching
2025-12-09T15:00:00Z - Rewrote TD parser from scratch after rollback: improved _extract_summary for two-column layout, _extract_transactions for multi-line descriptions grouped by date, added field_serializers for Decimal→float JSON (fixes toFixed error)
2025-12-09T15:30:00Z - Fixed Accounting2Page.tsx line 796: balance_after.toFixed() now checks typeof before calling to handle string/null values from old data
2025-12-09T16:00:00Z - Rewrote TD parser again: _extract_summary uses direct regex patterns (Beginning Balance, Ending Balance, etc.); _extract_transactions properly detects section headers, filters daily balance lines, applies correct signs (+/- by section)
2025-12-09T16:15:00Z - Fixed TD parser: simplified tx block extraction (single range instead of loop), changed date_re from \s to \b, relaxed section header detection (keyword anywhere in line), reduced skip patterns
2025-12-09T16:45:00Z - Added bank_section support: migration for transaction_spending column, backend saves/retrieves bank_section, approve copies to accounting_bank_row, frontend shows colored section badges
2025-12-09T17:15:00Z - Major TD parser cleanup: remove "How to Balance", "FOR CONSUMER ACCOUNTS", "INTEREST NOTICE" sections before parsing; skip page headers (STATEMENTOFACCOUNT, PAGE:, MILLER SELLS IT, etc.); limit description to 500 chars; skip too-short descriptions
2025-12-09T17:30:00Z - Fixed statement period extraction: new regex for "Statement Period: Apr 01 2025-Apr 302025" format; added _parse_date_flexible to handle merged day+year (e.g., "302025" → day 30, year 2025)
2025-12-06T17:20:00Z – Reviewed AccountingPage/DataGridPage and backend grids (ledger/statements) for missing data.
2025-11-08T20:53:41.7734824+03:00 - Cloned repo from GitHub to C:\dev\ebay-connector-app
2025-11-08T20:55:10.9328222+03:00 - Starting comparison with archived project
2025-11-08T20:56:48.7831915+03:00 - Completed directory diff with archived project (no differences reported)
2025-11-08T20:59:37.8485890+03:00 - Listed 20 most recently modified files for comparison focus
2025-11-08T21:04:41.7901713+03:00 - Inspected recent files in archived project for comparison
2025-11-08T21:05:58.6248923+03:00 - Noted: disregard local SQLite fallback; aim for Supabase only
2025-11-08T21:10:19.1171208+03:00 - Created backend/.env with Supabase Railway configuration
2025-11-08T21:12:26.8871319+03:00 - Created frontend/.env pointing to Railway backend
2025-11-08T21:28:59.0780805+03:00 - Waiting for Poetry installation by user
2025-11-08T21:35:51.0890517+03:00 - Verified Poetry already installed (2.2.1)
2025-11-08T21:37:11.7797990+03:00 - Ran backend poetry install (dependencies satisfied)
2025-11-09T11:55:26.2626683+03:00 - fastapi dev failed due to UnicodeEncodeError (emoji output on Windows console)
2025-11-11T13:12:24.0619735+03:00 - Checked C:\dev for echocare directory
2025-11-11T13:14:04.1180222+03:00 - Changed working directory to C:\dev\echocare
2025-11-11T13:25:50.3942758+03:00 - Reviewed latest modified files in C:\dev\echocare for handoff info
2025-11-11T15:11:35.3445523+03:00 - Updated ClearMind ESLint setup, installed flat-config deps, ran typecheck/lint/build
2025-11-11T15:17:06.8570572+03:00 - Created branch fix/stabilize-20251111 for ESLint stabilization work
2025-11-11T15:49:11.9965210+03:00 - Synced package.json and pnpm-lock.yaml for Railway install, rebuilt configs
2025-12-04T12:00:00+03:00 - Created Vision Brain Layer: LLM Brain (OpenAI), Vision Brain Orchestrator, Operator Guidance Service, Brain Repository
2025-12-04T12:00:00+03:00 - Created Supabase migration: 20251204_vision_brain_tables.sql (vision_sessions, vision_detections, vision_ocr_results, vision_brain_decisions, vision_operator_events)
2025-12-04T12:00:00+03:00 - Created API endpoints: /cv/brain/* (REST + WebSocket)
2025-12-04T12:00:00+03:00 - Created Frontend: BrainInstructionPanel, SessionTimeline, BrainStatusPanel, VisionBrainPage
2025-12-04T12:00:00+03:00 - Created documentation: docs/vision_brain_layer-20251204.md
2025-12-04T14:42:00+03:00 - Bank Statement Upload Refactor: Enhanced PDF parser with metadata extraction (bank_name, account, period, currency via OpenAI)
2025-12-04T14:42:00+03:00 - Backend: Made bank_name optional in /api/accounting/bank-statements, auto-extract from PDF
2025-12-04T14:42:00+03:00 - Frontend: Simplified AccountingPage upload form - removed all manual fields, now just file picker + upload button with status feedback
2025-12-04T18:30:00+03:00 - eBay Token Provider: Created unified EbayTokenProvider (backend/app/services/ebay_token_provider.py)
2025-12-04T18:30:00+03:00 - eBay Token Provider: Added internal HTTP endpoint POST /api/admin/internal/ebay/accounts/{account_id}/access-token
2025-12-04T18:30:00+03:00 - eBay Workers Refactor: Updated all 10 workers to use unified token provider with triggered_by parameter
2025-12-04T18:30:00+03:00 - eBay Workers Refactor: Updated scheduler.py to pass triggered_by="scheduler" to all workers
2025-12-04T18:30:00+03:00 - eBay Workers Refactor: Updated ebay_workers.py router to pass triggered_by="manual" for Run now
2025-12-04T18:30:00+03:00 - Documentation: Created docs/worker-token-endpoint-20251204.md with full implementation details
2025-12-06T20:10:04.6566310+03:00 - Investigated blank Edit SKU form; reviewed SKUPage.tsx and SkuFormModal.tsx for prefill flow
2025-12-06T20:21:02.8658590+03:00 - Added skuId validation on edit open, enforced numeric ID in SkuFormModal fetch, and added loading overlay for SKU prefill
2025-12-06T20:28:26.5790198+03:00 - Updated inventory grid status mapping to InventoryShortStatus_Name with color, added frontend renderer to apply status color
2025-12-06T20:30:40.6643627+03:00 - Fixed /api/sq/items/{id} to coerce legacy boolean fields before Pydantic validation to unblock SKU edit prefill
2025-12-06T20:34:45.4404481+03:00 - Coerced external_category_id and other numeric fields to strings and added use_ebay_id to boolean coercion for SKU read endpoint
2025-12-06T20:38:34.9602834+03:00 - Disabled live search in DataGridPage; search now applies on Enter/Go click with same %...% semantics to reduce load on large datasets
2025-12-06T20:41:21.2480611+03:00 - Prefill fallback: SKU edit modal now uses part/title/model_id to populate title/model when fields are empty in DB
2025-12-06T20:54:15.8809348+03:00 - Added inventory column filters (ID, SKU, ItemID, Title, StatusSKU, Storage, Serial) applied on Enter; backend supports per-column ilike filters
2025-12-06T20:59:00Z - Added backend commit endpoint to convert bank rows into accounting transactions for Ledger/Statements flow
2025-12-06T21:04:27.5811335+03:00 - Slimmed inventory layout, removed duplicate top filters, added StatusSKU dropdown fed from tbl_parts_inventorystatus, tightened padding
2025-12-06T21:14:28.1773934+03:00 - Made inventory filters compact single-row with fixed widths and added Reset button to clear all filters
2025-12-06T21:21:55.1350146+03:00 - Removed filter labels/“Filter” text, kept single Inventory heading, placed compact filters between title and grid toolbar
2025-12-06T21:37:44.2423490+03:00 - Moved inventory filters into grid topContent below toolbar, added DataGridPage hideTitle/topContent props to drop extra Inventory label
2025-12-06T22:41:00.8207855+03:00 - Rewired buying grid to legacy Supabase table tbl_ebay_buyer with tbl_ebay_status_buyer for status labels
2025-12-06T22:46:47.5785861+03:00 - Added numpy>=1.26.0 to backend requirements to satisfy cv camera imports
2025-12-06T23:05:10.8100557+03:00 - Added BUYING logs endpoint (tbl_ebay_buyer_log), appended Logs button column, modal shows status/comment history per buyer
2025-12-06T23:08:56.5369444+03:00 - Fixed build: import ColDef from ag-grid-community in DataGridPage extraColumns typing
2025-12-06T23:15:07.0849855+03:00 - Fixed BUYING SQL column casing to snake_case, default sort now id desc to show newest rows on top
2025-12-06T21:18:00Z - Added bank statement multi-select delete flow with confirmation prompt (type DELETE)
2025-12-06T21:27:00Z - DataGridPage auto-recovers hidden columns by restoring all available columns when prefs are empty
2025-12-07T08:45:00Z - Fixed Ledger grid not displaying rows: changed AppDataGrid wrapper to use flex layout (flex flex-col, flex-1 min-h-0) to ensure AG Grid receives proper height instead of relying on broken height:100% chain
2025-12-07T09:00:00Z - Fixed AG Grid v33+ theme conflict: added theme="legacy" prop to AgGridReact to use CSS file themes instead of conflicting Theming API
2025-12-07T13:10:00Z - Investigating eBrowser search 404 (“detail”:“Not Found”) and API wiring
2025-12-07T15:10:00Z - Adjusted AppDataGrid to flex 100% height and updated inventory/financials/transactions/orders pages to let grids fill available vertical space
2025-12-07T15:25:00Z - Fixed CF proxy to preserve /api path and switched eBrowser search to auth-enabled api client
2025-12-07T15:35:00Z - Adjusted eBrowser search API call to use relative path so /api baseURL is kept
2025-12-07T15:55:00Z - Updated CF proxy to avoid double /api when API_PUBLIC_BASE_URL already includes path; added combined path build
2025-12-07T16:05:00Z - Added proxy path comment to document preserving /api prefix to prevent 404
2025-12-07T16:15:00Z - Added API_PUBLIC_EBROWSER_BASE_URL override in CF proxy to isolate eBrowser backend base
2025-12-07T16:25:00Z - Proxy now forces /api prefix if missing (fallback for prod stripping)
2025-12-07T17:40:00Z - Reported BUYING fonts (filters, headers, grid cells)
2025-12-07T17:55:00Z - Tightened grid typography to legacy-like compact black text
2025-12-07T18:05:00Z - Updated DataGridPage fetch to fall back to items array so bank statements grid renders rows
2025-12-08T00:00:00Z - Started bank statements grid investigation; reviewed AccountingPage/DataGridPage and backend grid serialization.
2025-12-08T00:20:00Z - Adjusted Cloudflare proxy routing to not force /api prefix for /grid/preferences (bank statements grid prefs).
2025-12-11T05:10:00Z - Cleaned AdminAiTrainingPage unused React/default import and examples state to fix build TS6133
2025-12-11T05:18:00Z - Merged cursor/fix-admin-ai-training into main and deleted branch locally/remotely
2025-12-11T06:45:00Z - Added Supabase migration 20251211090000_ui_tweak_settings.sql and updated AdminTestComputerAnalyticsGraphPage.tsx to load live tables/columns and multi-select key fields
2025-12-11T06:55:00Z - Fixed TS build errors: removed unused handlers and set Button size to sm in AdminTestComputerAnalyticsGraphPage.tsx
2025-12-11T07:05:00Z - Attempted supabase db push; adjusted shipping_jobs.ebay_account_id to TEXT to match remote key type after FK mismatch
2025-12-11T07:12:00Z - Updated shipping migration FKs to TEXT for users/ebay_accounts and added uuid-ossp extension to ai_training_center migration before retrying supabase db push
2025-12-11T07:18:00Z - Switched ai_training_center IDs to gen_random_uuid() with pgcrypto extension after uuid_generate_v4() missing on remote
2025-12-11T07:25:00Z - Added console signal + type=button to Save graph mapping button to ensure click fires visibly
2025-12-11T07:35:00Z - Pointed computer analytics defaults to tbl_ebay_buyer (graph + classic) for buying container
2025-12-11T07:45:00Z - Made buying query storage-aware via inspector (handles Storage/storage/storage_id variants)
2025-12-11T08:05:00Z - Timesheets: admin view now loads all records newest-first by default; MyTimesheet adds Monday-based weekly calendar and week selector (read-only); backend timesheets endpoints allow unpaged fetches for full history
2025-12-11T08:25:00Z - Timesheets: admin page now supports paged “Load more” newest-first; user page shows weekly totals and CSV export for selected Monday-start week
2025-12-11T08:40:00Z - Timesheets: admin view now loads all entries at once again (no pagination button) to allow full edit/delete visibility
2025-12-11T08:45:00Z - Fixed build TS6133 by removing unused import X from EbayItemModal.tsx
2025-12-11T08:55:00Z - Timesheets: fixed admin role check (supports UserRole enum + allowlist); admin grid uses 50-per-page pagination again
2025-12-11T09:00:00Z - Timesheets: fixed 500 on admin list (added UserRole import for role check)
2025-12-11T09:20:00Z - Timesheets: switched ORM mapping to tbl_timesheet to show legacy rows (admin/user flows now read tbl_timesheet with 50-per-page pagination)
2025-12-11T08:55:00Z - Timesheets: added admin allowlist override (email/username) for role checks; admin list defaults to pageSize=50; frontend admin page shows paginated 50-per-page newest-first with next/prev controls
2025-12-11T08:35:00Z - Timesheets admin: reverted to initial “fetch all” on first load (pageSize unset) so all rows show immediately for edit/delete
2025-12-12T16:48:49Z - Fixed SKU grid backend filters/search (cast numeric SKU/Category to text; use Part/Description instead of @property title) and changed sku_catalog default sort to id desc in GRID_DEFAULTS
