# Stage 4 – eBay Monitoring Worker

Date: 2025-11-25  
Environment: Railway production (Supabase Postgres)  
Scope: eBay Connector App – backend (FastAPI/SQLAlchemy/Alembic) + frontend (React/TS, Vite, AG Grid)

## 1. Overview

Stage 4 builds on the Model Profitability Engine (Stage 3) and introduces the
**eBay Monitoring Worker** plus an admin dashboard to inspect its results.

The monitoring subsystem:

1. Reads profitable models from `model_profit_profile`.
2. For each model, calls the eBay Browse/Search API (Buy Browse) using model
   keywords.
3. Parses active listings (BIN + auctions/newly listed) into normalized
   candidates.
4. Compares each listing against the model profitability profile
   (`expected_profit`, `max_buy_price`).
5. Applies AI rule context (from `ai_rules` via `model_profit_profile` fields
   `matched_rule` and `rule_name`).
6. Stores qualifying listings into `ai_ebay_candidates`.
7. Exposes candidates in the admin UI at `/admin/monitor`.

This is a **first complete version** with conservative logic designed for
safety and observability rather than maximum coverage.

## 2. Database – `ai_ebay_candidates`

### 2.1 Alembic migration

A new Alembic migration was added:

- File: `backend/alembic/versions/ai_ebay_candidates_20251125.py`
- Revision ID: `ai_ebay_candidates_20251125`
- `down_revision`: `ai_analytics_20251125`

Migration behavior:

- Creates table `ai_ebay_candidates` with the columns listed below.
- Adds a unique constraint on `ebay_item_id`.
- Adds an index on `model_id`.

### 2.2 Table schema

Table: `ai_ebay_candidates`

- **id** `String(36)` – UUID primary key
- **ebay_item_id** `text` – eBay item identifier, unique
- **model_id** `text` – internal model identifier (stringified)
- **title** `text` – listing title
- **price** `numeric(14,2)` – item price
- **shipping** `numeric(14,2)` – shipping cost (0 when not present)
- **condition** `text` – condition label from Browse API
- **description** `text` – short description/summary when available
- **predicted_profit** `numeric(14,2)` – `expected_profit - (price + shipping)`
- **roi** `numeric(10,4)` – `predicted_profit / (price + shipping)`
- **matched_rule** `boolean` – copy of model-level rule match flag
- **rule_name** `text` – name of the first matching AI rule
- **created_at** `timestamptz` – default `now()`
- **updated_at** `timestamptz` – default `now()`, updated on each change

Constraints and indexes:

- Unique constraint: `uq_ai_ebay_candidates_ebay_item_id (ebay_item_id)`
- Index: `idx_ai_ebay_candidates_model_id (model_id)`

### 2.3 SQLAlchemy model

File:

- `backend/app/models_sqlalchemy/models.py`

Model:

- `class AiEbayCandidate(Base)`
  - Mapped to `ai_ebay_candidates`.
  - Mirrors the columns above using `String(36)`, `Text`, `Numeric`, `Boolean`,
    and `DateTime(timezone=True)` types.
  - Uses `func.now()` as server default for `created_at`/`updated_at` and
    sets `onupdate=func.now()` for `updated_at`.
  - Declares `Index("idx_ai_ebay_candidates_model_id", "model_id")`.

## 3. eBay Browse/Search API Client

A minimal Browse API client dedicated to the monitoring worker was added.

File:

- `backend/app/services/ebay_api_client.py`

### 3.1 Data structure

`@dataclass EbayListingSummary`:

- `item_id: str`
- `title: str`
- `price: float`
- `shipping: float`
- `condition: Optional[str]`
- `description: Optional[str]`

This is a normalized subset of Browse API `itemSummaries` fields.

### 3.2 Search function

`async def search_active_listings(access_token: str, keywords: str, *, limit: int = 20) -> List[EbayListingSummary]`:

- Uses `settings.ebay_api_base_url` with path
  `/buy/browse/v1/item_summary/search`.
- Query params:
  - `q` – provided `keywords` string.
  - `limit` – clamped to `1..50` per call.
  - `sort` – `NEWLY_LISTED` (bias recent listings).
- Headers:
  - `Authorization: Bearer <access_token>`
  - `Accept: application/json`
  - `Content-Type: application/json`
  - `X-EBAY-C-MARKETPLACE-ID: EBAY_US`

Error handling:

- Network errors (`httpx.RequestError`) → log and return `[]`.
- `401` → raise `HTTPException(401, "eBay Browse API token is invalid or expired")`.
- `>= 500` or other non-200 → log and return `[]`.
- JSON parsing errors → log and return `[]`.

Mapping logic:

- `item_id`: `itemId` or `legacyItemId`.
- `title`: `title` (string, stripped).
- `price`: `float(item["price"]["value"])` with safe fallbacks.
- `shipping`:
  - Supports both `shippingOptions` (list) and `shippingCost` shapes.
  - Extracts first `shippingCost.value` if present; otherwise `0.0`.
- `condition`: `condition` or `conditionDisplayName`.
- `description`: `shortDescription` when available.

The client returns a list of `EbayListingSummary` instances ready for further
processing by the worker.

## 4. Monitoring Worker – `ebay_monitor_worker.py`

File:

- `backend/app/workers/ebay_monitor_worker.py`

Exports:

- `async run_monitoring_loop(interval_sec: int = 60)`
- `async scan_all_models_once()`

### 4.1 Worker startup wiring

Workers package (`backend/app/workers/__init__.py`):

- Imports: `from app.workers.ebay_monitor_worker import run_monitoring_loop`.
- `__all__` includes `"run_monitoring_loop"`.

Application startup (`backend/app/main.py`):

- Router import list extended to include `admin_monitoring`.
- Router registration:
  - `app.include_router(admin_monitoring.router)`.
- In the `startup_event` worker block (Postgres path):

  - Imports now include `run_monitoring_loop` from `app.workers`.
  - After starting token refresh, health check, sync workers, and sniper loop:

    ```python
    asyncio.create_task(run_monitoring_loop())
    logger.info("✅ eBay monitoring worker started (runs every %s seconds)", 60)
    ```

Thus, in production the monitoring worker runs automatically once the DB and
workers are initialized.

### 4.2 Access token resolution

Helper:

- `_get_any_access_token(db: Session) -> Optional[str]`

Behavior:

- Queries `EbayToken` joined with `EbayAccount`:
  - Filters `EbayAccount.is_active IS TRUE`.
  - Orders by `EbayAccount.connected_at DESC`.
  - Takes the first matching token.
- Returns `token.access_token` via the encrypted property accessors.
- On error/decryption failure logs and returns `None`.

Notes:

- Monitoring currently uses **one** active account as a global context.
- Token refresh remains the responsibility of the existing token refresh worker.

### 4.3 Model scan – `scan_all_models_once`

Flow:

1. Create a `SessionLocal()` DB session.
2. Execute a raw SQL query against `model_profit_profile`:

   ```sql
   SELECT
       model_id::text AS model_id,
       max_buy_price,
       expected_profit,
       matched_rule,
       rule_name
   FROM model_profit_profile
   WHERE expected_profit IS NOT NULL
     AND max_buy_price IS NOT NULL
     AND max_buy_price > 0
     AND expected_profit >= :min_profit
   ```

   - `:min_profit` is `float(MIN_PROFIT_MARGIN)` from
     `backend/app/config/worker_settings.py`.

3. If no rows are returned, log and skip the scan:
   - `"No profitable models found in model_profit_profile; skipping scan."`
4. Resolve an access token via `_get_any_access_token`.
   - If none found, log warning and skip:
     - `"No active eBay account with token found; monitoring scan skipped."`
5. For each model row, call `_scan_model(...)` within a `try/except` so that
   one failing model does not stop others.
6. Commit once after processing all models.
7. Close the session in a `finally` block.

### 4.4 Per-model scan – `_scan_model`

Signature:

```python
async def _scan_model(
    db: Session,
    access_token: str,
    model_id: str,
    max_buy_price: float,
    expected_profit: float,
    matched_rule: Optional[bool],
    rule_name: Optional[str],
) -> None:
```

Steps:

1. Short-circuit if `max_buy_price <= 0` or `expected_profit <= 0`.
2. Build a keyword string for the model via `_build_keywords_for_model(model_id)`.
   - For this first version it returns `str(model_id)`.
   - This can later be enhanced to join SQ catalog / models tables for
     human-readable names.
3. Call `search_active_listings(access_token, keywords, limit=20)`.
   - If no listings, log at DEBUG and return.
4. For each `EbayListingSummary`:

   - `total_price = price + shipping` (floats; `None` treated as `0.0`).
   - Skip if `total_price <= 0`.
   - `predicted_profit = expected_profit - total_price`.
   - Enforce constraints:
     - `total_price <= max_buy_price`.
     - `predicted_profit >= 0`.
   - Compute `roi = predicted_profit / total_price` when `total_price > 0`.

5. UPSERT into `ai_ebay_candidates`:

   - Look up existing row by `ebay_item_id`:

     ```python
     candidate = (
         db.query(AiEbayCandidate)
         .filter(AiEbayCandidate.ebay_item_id == listing.item_id)
         .one_or_none()
     )
     ```

   - If no candidate exists:
     - Create `AiEbayCandidate(ebay_item_id=listing.item_id, model_id=model_id)`.
     - Add to session.
   - In both cases update:
     - `title`, `price`, `shipping`, `condition`, `description`.
     - `predicted_profit`, `roi`.
     - `matched_rule`, `rule_name` (copied from model profile row).

6. Actual insert/update for all candidates is finalized by the `db.commit()`
   call in `scan_all_models_once`. `updated_at` is automatically advanced via
   `onupdate=func.now()`.

Debouncing:

- The **unique constraint** on `ebay_item_id` and per-item UPSERT logic ensure
  that the same listing is not stored multiple times.

## 5. Admin API – Monitoring Router

File:

- `backend/app/routers/admin_monitoring.py`

Router:

- `router = APIRouter(prefix="/api/admin/ai/monitor", tags=["admin_ai_monitoring"])`

Auth & dependencies:

- DB session: `Depends(get_db_sqla)` (from `app.models_sqlalchemy`).
- Admin requirement: `Depends(admin_required)` (from `app.services.auth`).
- Current user object (`User`) is accepted but not used beyond auth.

### 5.1 DTO model

`class AiEbayCandidateDto(BaseModel)`:

- `ebay_item_id: str`
- `model_id: str`
- `title: Optional[str]`
- `price: Optional[float]`
- `shipping: Optional[float]`
- `condition: Optional[str]`
- `description: Optional[str]`
- `predicted_profit: Optional[float]`
- `roi: Optional[float]`
- `matched_rule: Optional[bool]`
- `rule_name: Optional[str]`
- `created_at: datetime`
- `updated_at: datetime`

Config:

- `orm_mode = True` for direct mapping from `AiEbayCandidate` ORM instances.

### 5.2 Endpoints

1. `GET /api/admin/ai/monitor/candidates`

   - Query parameters:
     - `limit: int = 200` (1–1000)
     - `offset: int = 0` (>= 0)
   - Returns: `List[AiEbayCandidateDto]`.
   - Behavior:
     - Queries `AiEbayCandidate` ordered by `created_at DESC`.
     - Applies limit/offset.

2. `GET /api/admin/ai/monitor/candidate/{item_id}`

   - Path parameter: `item_id` = `ebay_item_id`.
   - Returns: `AiEbayCandidateDto`.
   - Behavior:
     - Looks up candidate by `AiEbayCandidate.ebay_item_id`.
     - On missing row: `HTTPException(404, "Candidate not found")`.

These endpoints provide a simple JSON API for the admin UI and future
automation (e.g., notifications in later stages).

## 6. Frontend – Admin Monitoring Dashboard

File:

- `frontend/src/pages/AdminMonitoringPage.tsx`

Route:

- `/admin/monitor`

### 6.1 Routing and navigation

`frontend/src/App.tsx`:

- Imports:

  - `import AdminMonitoringPage from './pages/AdminMonitoringPage';`

- Protected route:

  ```tsx
  <Route
    path="/admin/monitor"
    element={<ProtectedRoute><AdminMonitoringPage /></ProtectedRoute>}
  />
  ```

Admin dashboard tile (`frontend/src/pages/AdminPage.tsx`):

- New card:

  - Title: **Monitoring Candidates**
  - Description: "Кандидаты на покупку из eBay мониторинга по моделям"
  - `onClick={() => navigate('/admin/monitor')}`

### 6.2 Page behavior

Component: `AdminMonitoringPage` (default export).

State:

- `rows: AiEbayCandidateDto[]`
- `loading: boolean`
- `error: string | null`
- `search: string`

Data loading:

- On mount, performs a single request:

  ```ts
  GET /api/admin/ai/monitor/candidates?limit=500&offset=0
  ```

- On success: stores `resp.data` into `rows`.
- On error: displays backend `detail` or a fallback message.

### 6.3 Grid configuration (AG Grid via AppDataGrid)

The page uses the shared `AppDataGrid` component directly:

Imports:

- `AppDataGrid, AppDataGridColumnState` from
  `frontend/src/components/datagrid/AppDataGrid.tsx`.
- `GridColumnMeta` from `frontend/src/components/DataGridPage.tsx`.

Columns:

`baseColumns: AppDataGridColumnState[]`:

- `ebay_item_id` – label "eBay Item ID", width 160
- `model_id` – label "Model ID", width 130
- `title` – label "Title", width 260
- `price` – label "Price", width 110
- `shipping` – label "Shipping", width 110
- `predicted_profit` – label "Predicted Profit", width 150
- `roi` – label "ROI", width 110
- `matched_rule` – label "Matched Rule", width 130
- `rule_name` – label "Rule Name", width 200
- `created_at` – label "Created At", width 180

Column metadata (`Record<string, GridColumnMeta>`):

- `ebay_item_id`: type `string`.
- `model_id`: type `string`.
- `title`: type `string`.
- `price`, `shipping`, `predicted_profit`, `roi`:
  - type `number` so they benefit from numeric formatting/alignment.
- `matched_rule`, `rule_name`: type `string`.
- `created_at`: type `datetime` (formatted via shared helpers).

Grid props:

- `columns={columns}` (after applying stored layout order & widths).
- `rows={filteredRows as any}`.
- `columnMetaByName={columnMetaByName}`.
- `loading={loading}`.
- `gridKey="admin_monitor"`.
- `gridTheme={null}` (default AG Grid theme + project CSS).
- `onLayoutChange={({ order, widths }) => handleLayoutChange({ order, widths })}`.

Features:

- **Sorting** – enabled per column by AppDataGrid via AG Grid defaults.
- **Zebra striping + copyable cells** – inherited from global grid CSS and
  AppDataGrid implementation used across the app.
- **Client-side searching** – a text input filters `rows` via a simple
  substring match on `ebay_item_id`, `model_id`, `title`, and `rule_name`.

### 6.4 Persistent preferences (gridKey = "admin_monitor")

The page implements **client-side persistent layout preferences** backed by
`localStorage`.

Storage key:

- `const GRID_KEY = 'admin_monitor'`
- `const LAYOUT_STORAGE_KEY = \\`grid_layout_${GRID_KEY}\\``

Stored shape:

```ts
type StoredLayout = {
  order: string[];
  widths: Record<string, number>;
};
``

Initialization:

- On first render, `useMemo` attempts to parse `LAYOUT_STORAGE_KEY`.
- If present, it:
  - Reorders `baseColumns` according to `stored.order`.
  - Applies saved widths from `stored.widths`.
- If absent, it uses `baseColumns` as-is.

Updates:

- `handleLayoutChange` receives `{ order, widths }` from `AppDataGrid`'s
  `onLayoutChange` handler and writes a new `StoredLayout` to localStorage.
- This persists column order and widths across page reloads on the same
  browser.

## 7. Edge Cases & Considerations

- **Missing `model_profit_profile` data**:
  - If the table is empty or missing required columns, the monitoring worker
    will log that no profitable models were found and skip scanning.
  - This keeps Stage 4 safe even if Stage 3 is not fully populated yet.
- **No active eBay accounts**:
  - When `_get_any_access_token` cannot find an active account with a token,
    the worker logs a warning and skips the scan without raising.
- **Expired/invalid tokens**:
  - The Browse client raises `HTTPException(401, ...)` on invalid tokens.
  - This will be logged by the worker; token refresh remains delegated to the
    existing token refresh worker.
- **Browse API errors**:
  - 5xx or unexpected responses are logged and result in empty listing sets;
    scanning continues for other models.
- **Duplicate listings**:
  - Enforced by `uq_ai_ebay_candidates_ebay_item_id` and UPSERT logic.
- **ROI computation**:
  - Uses `predicted_profit / total_price` with protection against zero
    division; ROI may be `null` when `total_price <= 0`.

## 8. TypeScript Checks

After implementing Stage 4 backend and frontend changes, the following commands
were executed from `frontend/`:

```bash
npm run build
npx tsc --noEmit
```

Both commands completed **successfully** (no TypeScript errors).

- `npm run build` runs `tsc -b` followed by `vite build`; the build completed
  with only the existing bundle size warning.
- `npx tsc --noEmit` completed with exit code `0` and no diagnostics.

**TS check result:** ✔ TS check passed (no errors).

## 9. Summary of Stage 4 Deliverables

- **Database**:
  - `ai_ebay_candidates` table created via Alembic with unique `ebay_item_id` and
    index on `model_id`.
- **Worker**:
  - `ebay_monitor_worker.py` implemented with `run_monitoring_loop` and
    `scan_all_models_once`, scanning profitable models and persisting
    candidates.
- **API**:
  - Admin monitoring router `admin_monitoring.py` with endpoints:
    - `GET /api/admin/ai/monitor/candidates`
    - `GET /api/admin/ai/monitor/candidate/{item_id}`
- **Frontend**:
  - Admin Monitoring Dashboard at `/admin/monitor` with AG Grid, search,
    sorting, zebra styling, copyable cells, and client-side persistent
    preferences keyed by `gridKey="admin_monitor"`.
- **TypeScript**:
  - `npm run build` and `npx tsc --noEmit` both passed without errors.
