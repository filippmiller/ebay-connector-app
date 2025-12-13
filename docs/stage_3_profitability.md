# Stage 3 – Model Profitability Engine

Date: 2025-11-25
Environment: Railway production (Supabase Postgres)
Scope: eBay Connector App – backend (FastAPI/SQLAlchemy/Alembic) + frontend (React/TS, Vite, AG Grid)

## 1. Overview

Stage 3 introduces the **Model Profitability Engine** – an internal analytics layer that
computes profitability profiles per hardware model and exposes them via an admin
UI. These profiles will later be consumed by:

- eBay Monitoring Worker
- Auto-Offer Worker
- Auto-Buy Worker
- Sniper Worker
- AI Analytics / AI Grid

This implementation focuses on:

- Creating the persistent table `model_profit_profile`.
- Implementing a background worker that aggregates transaction-level profit per
  model and derives `expected_profit` and `max_buy_price`.
- Applying `ai_rules.rule_sql` directly against `model_profit_profile` to
  classify models (e.g. "good computer" vs "risky").
- Creating an admin dashboard page `/admin/model-profit` that surfaces these
  metrics for humans.
- Verifying TypeScript via `npm run build` and `npx tsc --noEmit`.

Component-level averages (motherboard/screen/etc.) and some advanced metrics
are intentionally left as **NULL** for the first iteration; they can be
incrementally filled in future phases without schema changes.

## 2. Database – `model_profit_profile`

A new table was introduced via Alembic migration:

- File: `backend/alembic/versions/model_profit_profile_20251125.py`
- Revision ID: `model_profit_profile_20251125`
- `down_revision`: `ai_analytics_20251125`

Schema:

- **id** `uuid` (as `String(36)`) – primary key
- **model_id** `String(36)` – logical model identifier (from `SqItem.model_id`), indexed
- **sample_size** `Integer` – number of transactions included in the aggregates
- **avg_mb_price** `Numeric(14,2)` – NULL (reserved for future component analytics)
- **avg_screen_price** `Numeric(14,2)` – NULL (reserved)
- **avg_keyboard_price** `Numeric(14,2)` – NULL (reserved)
- **avg_case_price** `Numeric(14,2)` – NULL (reserved)
- **avg_ram_price** `Numeric(14,2)` – NULL (reserved)
- **avg_battery_price** `Numeric(14,2)` – NULL (reserved)
- **avg_charger_price** `Numeric(14,2)` – NULL (reserved)
- **avg_shipping_cost** `Numeric(14,2)` – NULL (reserved)
- **avg_ebay_fee** `Numeric(14,2)` – NULL (reserved)
- **avg_sale_time_days** `Numeric(10,4)` – NULL (reserved)
- **refund_rate** `Numeric(10,4)` – NULL (reserved)
- **expected_profit** `Numeric(14,2)` – average `Transaction.profit` per model
- **max_buy_price** `Numeric(14,2)` – derived from `expected_profit`
- **rule_name** `Text` – name of first matching AI rule (from `ai_rules`)
- **matched_rule** `Boolean` – whether any AI rule matched this profile
- **updated_at** `TIMESTAMP WITH TIME ZONE` – last update time, default `now()`

Index:

- `idx_model_profit_profile_model_id` on `(model_id)`

SQLAlchemy model:

- File: `backend/app/models_sqlalchemy/models.py`
- Class: `ModelProfitProfile`

This class mirrors the table above and is used by the worker and admin API.

## 3. Worker Configuration – `MIN_PROFIT_MARGIN`

To keep the engine configurable without code changes, a small worker settings
module was added:

- File: `backend/app/config/worker_settings.py`
- Constant:

  - `MIN_PROFIT_MARGIN: float = 40.0`

Interpretation:

- Currency units are the same as `Transaction.profit` (USD-equivalent in this
  environment).
- `max_buy_price` is computed as:

  - `max_buy_price = max(expected_profit - MIN_PROFIT_MARGIN, 0)`

This is intentionally conservative for the first iteration. It can be tuned
later as more data is collected.

## 4. Model Profitability Worker

File:

- `backend/app/workers/model_profitability_worker.py`

Public entry points:

- `async recompute_all_model_profit_profiles() -> None`
  - Executes a single full recompute of `model_profit_profile`.
- `async run_model_profitability_loop(interval_seconds: int = 3600) -> None`
  - Background loop, default: recompute once per hour.

### 4.1 Data sources and joins

The worker currently uses **historical transaction-level profit** as the main
signal. Data sources:

- `SqItem` – SKU catalog mirror with `model_id`.
- `Transaction` – historic eBay sales transactions with `sku`, `profit`, etc.

Join strategy:

- `SqItem.model_id` (BigInteger/Number) is treated as the canonical model key.
- `Transaction.sku` and `SqItem.sku` can differ in type (string vs numeric), so
  the worker joins by **casting both to string**:

  - `cast(Transaction.sku, String) == cast(SqItem.sku, String)`

Aggregation:

- Grouped by `SqItem.model_id`.
- For each group, compute:

  - `sample_size = COUNT(Transaction.transaction_id)` where `Transaction.profit IS NOT NULL`.
  - `avg_profit = AVG(Transaction.profit)`.

### 4.2 Expected profit and max buy price

Helper:

- `_compute_expected_profit_and_max_buy(avg_profit: Optional[float]) -> dict`

Logic:

- If `avg_profit` is `None`:
  - `expected_profit = None`
  - `max_buy_price = None`
- Else:
  - `expected_profit = float(avg_profit)`
  - `max_buy_raw = expected_profit - MIN_PROFIT_MARGIN`
  - `max_buy_price = max(max_buy_raw, 0.0)`

This is an intentionally simple heuristic. It answers the question:

> "Given historic profit per machine for this model, what is the **maximum
>  price** we should be willing to pay to still maintain at least
>  `MIN_PROFIT_MARGIN` of profit?"

### 4.3 Upsert into `model_profit_profile`

Within `_recompute_profiles_once(db: Session)`:

1. Aggregate rows from the join described above.
2. For each aggregated row:
   - Skip if `model_id` is `NULL`.
   - Convert `model_id` to string for storage in `ModelProfitProfile.model_id`.
   - Derive `sample_size`, `expected_profit` and `max_buy_price`.
   - Upsert into `model_profit_profile`:
     - If profile for `model_id` exists: update `sample_size`, `expected_profit`, `max_buy_price`.
     - Else: create a new `ModelProfitProfile` record.
3. Commit once after processing all rows.

Notes:

- All component-level average fields remain `NULL` in this version.
- `avg_sale_time_days` and `refund_rate` are also left `NULL` for now.

### 4.4 Rule application via `ai_rules`

The worker integrates **AI rules** from Stage 1/2 by applying the `rule_sql`
conditions directly against `model_profit_profile`.

Data source:

- `AiRule` model from `backend/app/models_sqlalchemy/models.py`.

Process:

1. After recomputing all profiles, reset rule flags:
   - `matched_rule = False`
   - `rule_name = NULL`
   - Done via a single bulk `UPDATE` on `model_profit_profile`.
2. Load all AI rules ordered by `created_at ASC`.
3. For each rule:
   - Use `rule.rule_sql` as a **WHERE-condition fragment** in a text SQL
     statement:

     - `UPDATE model_profit_profile SET matched_rule = TRUE, rule_name = :rule_name WHERE (matched_rule IS NOT TRUE) AND (<rule_sql>)`

   - Bind only `rule_name` as a parameter; `rule_sql` is already validated when
     the rule is saved (no `SELECT/INSERT/UPDATE/DELETE`, no semicolons, no
     `FROM/JOIN/UNION/WITH`, etc.).
   - Because the UPDATE includes `matched_rule IS NOT TRUE`, **first match
     wins**: once a profile is matched by any rule, it will not be
     reassigned by subsequent rules.

This means that AI rules can reference any columns from
`model_profit_profile`, for example:

- `expected_profit > 80 AND max_buy_price > 150`
- `expected_profit > 100 AND refund_rate < 0.05`
- `max_buy_price BETWEEN 80 AND 200`

As more metrics are filled (e.g. `avg_sale_time_days`, `refund_rate`), these
same rules can become more expressive without changing worker code.

### 4.5 Worker startup wiring

File:

- `backend/app/workers/__init__.py`

Exports:

- `recompute_all_model_profit_profiles`
- `run_model_profitability_loop`

Startup integration (FastAPI app):

- File: `backend/app/main.py`
- In `@app.on_event("startup")` when `start_workers` is `True` (Postgres
  environment), the following is now imported:

  - `from app.workers import (..., run_sniper_loop, run_model_profitability_loop)`

- And scheduled:

  - `asyncio.create_task(run_model_profitability_loop())`
  - Logged as:
    - `"✅ Model profitability worker started (runs every %s seconds)", 3600`

Thus, in production the profitability worker runs automatically alongside
existing workers once the DB is available.

## 5. Admin API – Profitability Router

File:

- `backend/app/routers/admin_profitability.py`

Router registration:

- Imported in `backend/app/routers/__init__.py` as `admin_profitability`.
- Added to FastAPI in `backend/app/main.py`:

  - `app.include_router(admin_profitability.router)`

Auth:

- All endpoints are **admin-only**, enforced via `Depends(admin_required)`.

Dependencies:

- DB session: `Depends(get_db_sqla)`.

### 5.1 DTOs

Two Pydantic models are defined for clean API responses.

`ModelProfitProfileSummary`:

- `model_id: str`
- `sample_size: int`
- `expected_profit: Optional[float]`
- `max_buy_price: Optional[float]`
- `refund_rate: Optional[float]`
- `avg_sale_time_days: Optional[float]`
- `matched_rule: Optional[bool]`
- `rule_name: Optional[str]`
- `updated_at: datetime`

`ModelProfitProfileDetail`:

- `id: str`
- `model_id: str`
- `sample_size: int`
- All component and cost fields (`avg_mb_price`, `avg_screen_price`, ...),
  currently `Optional[float]` and usually `NULL`.
- `avg_sale_time_days: Optional[float]`
- `refund_rate: Optional[float]`
- `expected_profit: Optional[float]`
- `max_buy_price: Optional[float]`
- `rule_name: Optional[str]`
- `matched_rule: Optional[bool]`
- `updated_at: datetime`

Both models set `Config.orm_mode = True` for direct ORM model mapping.

### 5.2 Endpoints

1. `GET /api/admin/ai/profit/models`

   - Query params:
     - `limit: int = 200` (1–1000)
     - `offset: int = 0` (>= 0)
   - Returns: `List[ModelProfitProfileSummary]`
   - Behavior:
     - Lists model profitability profiles ordered by `updated_at DESC`.
     - Intended for the Admin Model Profitability grid.

2. `GET /api/admin/ai/profit/model/{model_id}`

   - Path param:
     - `model_id: str`
   - Returns: `ModelProfitProfileDetail`
   - Behavior:
     - Looks up a profile by `model_id`.
     - On missing profile: `404` with `{"detail": "Model profile not found"}`.

## 6. Frontend – Admin Profitability Dashboard

New page component:

- File: `frontend/src/pages/AdminModelProfitPage.tsx`
- Route: `/admin/model-profit`

### 6.1 Routing and navigation

`frontend/src/App.tsx`:

- Imports:

  - `import { AdminModelProfitPage } from './pages/AdminModelProfitPage';`

- Protected route:

  - `<Route path="/admin/model-profit" element={<ProtectedRoute><AdminModelProfitPage /></ProtectedRoute>} />`

Admin dashboard tile:

- File: `frontend/src/pages/AdminPage.tsx`
- Added a new card:

  - Title: **Model Profitability**
  - Description: "Просмотр профилей прибыльности моделей и max_buy_price"
  - `onClick={() => navigate('/admin/model-profit')}`

### 6.2 Page behavior

Component: `AdminModelProfitPage`.

State:

- `rows: ModelProfitProfileDto[]`
- `loading: boolean`
- `error: string | null`

Data fetch:

- On mount, performs:

  - `GET /api/admin/ai/profit/models`

- On success: stores the returned array in `rows`.
- On failure: extracts a backend error (`response.data.detail`) if present,
  otherwise falls back to `err.message` or a generic string.

### 6.3 Grid configuration

The page uses the shared AG Grid wrapper for consistent UX:

- Component: `AppDataGrid` from `frontend/src/components/datagrid/AppDataGrid.tsx`.

Columns (`AppDataGridColumnState[]`):

- `model_id` – label: "Model ID", width: 150
- `sample_size` – label: "Samples", width: 110
- `expected_profit` – label: "Expected Profit", width: 150
- `max_buy_price` – label: "Max Buy Price", width: 150
- `refund_rate` – label: "Refund Rate", width: 130
- `avg_sale_time_days` – label: "Avg Sale Time (days)", width: 170
- `matched_rule` – label: "Matched Rule", width: 130
- `rule_name` – label: "Rule Name", width: 200
- `updated_at` – label: "Updated At", width: 180

Column metadata (`Record<string, GridColumnMeta>`):

- `model_id` pinned to the left.
- Numeric columns (`sample_size`, `expected_profit`, `max_buy_price`,
  `refund_rate`, `avg_sale_time_days`) marked as `type: 'number'` with default
  widths and aggregation functions (`sum`/`avg`) where appropriate.
- `updated_at` uses `type: 'datetime'` so the grid's formatting logic applies.

Grid props:

- `columns={columnDefs}`
- `rows={rows as any}` (rows are plain DTOs, compatible with the grid's
  `Record<string, any>` API)
- `columnMetaByName={columnMetaByName}`
- `loading={loading}`
- `gridKey="admin_model_profit"`
- `gridTheme={null}` (simple default theme for now)

Layout:

- Uses the existing `FixedHeader` + gray background layout used by other admin
  pages (same visual language as `/admin/ai-grid`).
- Page title: "Model Profitability Profiles".
- Subtitle paragraph explains how this ties to monitoring, auto-offer,
  auto-buy and sniper logic.

## 7. Algorithm Limitations and Future Extensions

This Stage 3 implementation intentionally focuses on a **minimal but useful
baseline**:

- It uses only `Transaction.profit` as the profitability signal.
- It does not yet:
  - Compute per-component averages (`avg_mb_price`, `avg_screen_price`, etc.).
  - Compute `avg_shipping_cost` or `avg_ebay_fee`.
  - Compute `avg_sale_time_days` from purchase-to-sale intervals.
  - Derive `refund_rate` from explicit returns / refund tables.

Despite these gaps, it already enables:

- Ranking models by `expected_profit`.
- Deriving conservative `max_buy_price` thresholds per model.
- Classifying models via `ai_rules` using conditions over
  `expected_profit`, `max_buy_price`, and any future metrics.