# Grid System Audit – Data Sources, Columns, and Metadata

This document summarizes, **from code only**, where each grid gets its data and column metadata, and under what conditions `available_columns` or `availableColumns` might be empty.

Because this environment has **no `DATABASE_URL`**, there is **no live DB access** – everything here is derived from code (models, SQL snippets, router logic), *not* from `information_schema` or Supabase/Railway introspection.

---

## 0. DB Connectivity (Honesty Check)

I explicitly checked whether `DATABASE_URL` is available in this environment:

```bash
cd C:\dev\ebay-connector-app\backend
python -c "import os; print('DATABASE_URL =', os.getenv('DATABASE_URL'))"
# Output: DATABASE_URL = None
```

Conclusion:

- `DATABASE_URL` is **not set** here.
- I **cannot** connect to the real Postgres/Supabase instance.
- All DB-related claims below (table names, columns) are **inferred from code only**.
- Anywhere I say “Columns confirmed in DB?” the answer is “no – code-only”.

---

## 1. Grid Usage and Endpoints (Code-Level)

### 1.1 Frontend → gridKey mapping

Every shared grid uses `DataGridPage` from `frontend/src/components/DataGridPage.tsx`. I searched all usages of `<DataGridPage gridKey="...">` under `frontend/src/pages`.

**Frontend pages & gridKeys (code):**

- `OrdersPage.tsx` → `gridKey="orders"`
- `TransactionsPage.tsx` → `gridKey="transactions"`
- `FinancialsPage.tsx`:
  - Ledger tab → `gridKey="finances"`
  - Fees tab → `gridKey="finances_fees"`
- `BuyingPage.tsx` → `gridKey="buying"`
- `SKUPage.tsx` → `gridKey="sku_catalog"`
- `ListingPage.tsx` → top SKU grid uses `gridKey="sku_catalog"`
- `InventoryPage.tsx` → `gridKey="active_inventory"`
- `InventoryPageV3.tsx` → `gridKey="inventory"`
- `CasesPage.tsx` → `gridKey="cases"`
- `OffersPageV2.tsx` → `gridKey="offers"`
- `AccountingPage.tsx`:
  - Bank statements tab → `gridKey="accounting_bank_statements"`
  - Cash expenses tab → `gridKey="accounting_cash_expenses"`
  - Accounting transactions tab → `gridKey="accounting_transactions"`

### 1.2 Backend endpoints for each gridKey

All grids share the same data route shape:

- Data: `GET /api/grids/{grid_key}/data` in `backend/app/routers/grids_data.py:get_grid_data`
- Preferences: `GET /api/grid/preferences?grid_key=...` in `backend/app/routers/grid_preferences.py:get_grid_preferences`
- Legacy layout: `GET /api/grids/{grid_key}/layout` in `backend/app/routers/grid_layouts.py:get_grid_layout`

**Grid mapping table (code-level):**

| gridKey                     | Frontend usage (DataGridPage)                                                      | Data endpoint (path → file:function)                                                                                           | Data helper for this gridKey (inside `get_grid_data`)                                                     | Preferences/Layout endpoints (path → file:function)                                                                                                                                                          |
|-----------------------------|------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `orders`                    | `OrdersPage.tsx` → `<DataGridPage gridKey="orders" />`                            | `GET /api/grids/orders/data` → `backend/app/routers/grids_data.py:get_grid_data`                                             | Branch `grid_key == "orders"` → `await _get_orders_data(...)`          | Preferences: `GET /api/grid/preferences?grid_key=orders` → `grid_preferences.get_grid_preferences`; legacy layout: `GET /api/grids/orders/layout` → `grid_layouts.get_grid_layout`                         |
| `transactions`              | `TransactionsPage.tsx` → `<DataGridPage gridKey="transactions" />`               | `GET /api/grids/transactions/data` → same `get_grid_data`                                                                    | Branch `grid_key == "transactions"` → `_get_transactions_data(...)`    | Same prefs endpoint with `grid_key=transactions`; legacy layout: `/api/grids/transactions/layout`                                                                                                           |
| `finances`                  | `FinancialsPage` ledger tab → `<DataGridPage gridKey="finances" ... />`          | `GET /api/grids/finances/data` → `get_grid_data`                                                                             | Branch `grid_key == "finances"` → `_get_finances_data(...)`           | Same prefs endpoint with `grid_key=finances`; legacy layout: `/api/grids/finances/layout`                                                                                                                   |
| `finances_fees`             | `FinancialsPage` fees tab → `<DataGridPage gridKey="finances_fees" ... />`       | `GET /api/grids/finances_fees/data` → `get_grid_data`                                                                        | Branch `grid_key == "finances_fees"` → `_get_finances_fees_data(...)` | Same prefs endpoint with `grid_key=finances_fees`; legacy layout: `/api/grids/finances_fees/layout`                                                                                                         |
| `buying`                    | `BuyingPage.tsx` → `<DataGridPage gridKey="buying" ... />`                        | `GET /api/grids/buying/data` → `get_grid_data`                                                                               | Branch `grid_key == "buying"` → `_get_buying_data(...)`               | Same prefs endpoint with `grid_key=buying`; legacy layout: `/api/grids/buying/layout`                                                                                                                       |
| `sku_catalog`               | `SKUPage.tsx`, `ListingPage.tsx` → `<DataGridPage gridKey="sku_catalog" ... />`  | `GET /api/grids/sku_catalog/data` → `get_grid_data`                                                                          | Branch `grid_key == "sku_catalog"` → `_get_sku_catalog_data(...)`     | Same prefs endpoint with `grid_key=sku_catalog`; legacy layout: `/api/grids/sku_catalog/layout`                                                                                                            |
| `active_inventory`          | `InventoryPage.tsx` → `<DataGridPage gridKey="active_inventory" ... />`          | `GET /api/grids/active_inventory/data` → `get_grid_data`                                                                     | Branch `grid_key == "active_inventory"` → `_get_active_inventory_data(...)` | Same prefs endpoint with `grid_key=active_inventory`; legacy layout: `/api/grids/active_inventory/layout`                                                                                             |
| `inventory`                 | `InventoryPageV3.tsx` → `<DataGridPage gridKey="inventory" ... />`               | `GET /api/grids/inventory/data` → `get_grid_data`                                                                            | Branch `grid_key == "inventory"` → `_get_inventory_data(...)`         | Same prefs endpoint with `grid_key=inventory`; legacy layout: `/api/grids/inventory/layout`                                                                                                                 |
| `cases`                     | `CasesPage.tsx` → `<DataGridPage gridKey="cases" ... />`                          | `GET /api/grids/cases/data` → `get_grid_data`                                                                                | Branch `grid_key == "cases"` → `_get_cases_data(...)`                 | Same prefs endpoint with `grid_key=cases`; legacy layout: `/api/grids/cases/layout`                                                                                                                         |
| `offers`                    | `OffersPageV2.tsx` → `<DataGridPage gridKey="offers" ... />`                     | `GET /api/grids/offers/data` → `get_grid_data`                                                                               | Branch `grid_key == "offers"` → `_get_offers_data(...)`               | Same prefs endpoint with `grid_key=offers`; legacy layout: `/api/grids/offers/layout`                                                                                                                       |
| `accounting_bank_statements`| `AccountingPage.tsx` → `<DataGridPage gridKey="accounting_bank_statements" ...>` | `GET /api/grids/accounting_bank_statements/data` → `get_grid_data`                                                           | Branch `grid_key == "accounting_bank_statements"` → `_get_accounting_bank_statements_data(...)` **(helper missing)** | Same prefs endpoint with `grid_key=accounting_bank_statements`; legacy layout: `/api/grids/accounting_bank_statements/layout`                                                         |
| `accounting_cash_expenses`  | `AccountingPage.tsx` → `<DataGridPage gridKey="accounting_cash_expenses" ...>`   | `GET /api/grids/accounting_cash_expenses/data` → `get_grid_data`                                                             | Branch `grid_key == "accounting_cash_expenses"` → `_get_accounting_cash_expenses_data(...)` **(helper missing)**   | Same prefs endpoint with `grid_key=accounting_cash_expenses`; legacy layout: `/api/grids/accounting_cash_expenses/layout`                                                            |
| `accounting_transactions`   | `AccountingPage.tsx` → `<DataGridPage gridKey="accounting_transactions" ...>`    | `GET /api/grids/accounting_transactions/data` → `get_grid_data`                                                              | Branch `grid_key == "accounting_transactions"` → `_get_accounting_transactions_grid_data(...)`             | Same prefs endpoint with `grid_key=accounting_transactions`; legacy layout: `/api/grids/accounting_transactions/layout`                                                               |

Observations:

- All grids share the **same data endpoint shape** (`/api/grids/{grid_key}/data`), then branch to private helpers.
- Preferences & metadata are **centralized** (`/api/grid/preferences`) with a legacy layout endpoint under `/api/grids/{grid_key}/layout`.
- For the two accounting grids, the code references helpers that are **not implemented**; if those branches are hit in production, they would error.

---

## 2. Data Sources per Grid (Code-Level, Not DB-Level)

This section answers “which table(s) and columns back each grid” based on code only.

### 2.1 Helpers in `backend/app/routers/grids_data.py`

The generic router:

```python
router = APIRouter(prefix="/api/grids", tags=["grids_data"])

@router.get("/{grid_key}/data")
async def get_grid_data(...):
    ...
    if grid_key == "orders":
        return await _get_orders_data(...)
    elif grid_key == "transactions":
        return _get_transactions_data(...)
    ...
    elif grid_key == "accounting_bank_statements":
        db_sqla = next(get_db_sqla())
        try:
            return _get_accounting_bank_statements_data(...)
        finally:
            db_sqla.close()
    ...
```

Helpers `_get_accounting_bank_statements_data` and `_get_accounting_cash_expenses_data` are *referenced* but not defined anywhere.

### 2.2 Grid-by-grid data table & column summary

> Reminder: these are **inferred from code**, not confirmed against a live DB.

#### `orders` grid

- Helper: `_get_orders_data(db: Session, current_user, selected_cols, limit, offset, sort_column, sort_dir)`
- Query:

  ```python
  # Minimal Orders grid backed only by public.order_line_items.
  query = db.query(OrderLineItem)
  total = query.count()
  rows_db: List[OrderLineItem] = query.offset(offset).limit(limit).all()
  ```

- Tables (by code): `public.order_line_items` via ORM `OrderLineItem` (defined in `app.db_models`).
- Sort whitelist: `created_at, order_id, line_item_id, sku, title, quantity, total_value, currency`.
- Output columns: any subset of `selected_cols` that exist on `OrderLineItem`.

#### `transactions` grid

- Helper: `_get_transactions_data(db: Session, current_user, selected_cols, ...)`
- Query:

  ```python
  query = db.query(EbayLegacyTransaction)
  total = query.count()
  rows_db = query.offset(offset).limit(limit).all()
  ```

- Table: inferred from comment as `public.ebay_transactions` via `EbayLegacyTransaction` model.
- Sortable columns: `transaction_date, transaction_type, transaction_status, amount, currency, created_at, updated_at`.
- Output: any `selected_cols` present on `EbayLegacyTransaction`.

#### `finances` grid

- Helper: `_get_finances_data(db, current_user, selected_cols, limit, offset, sort_column, sort_dir, transaction_type, from_date, to_date)`
- Comment: “Finances ledger grid backed by ebay_finances_transactions + fees.”
- Uses raw SQL over two tables:

  - `ebay_finances_transactions` joined to `ebay_accounts` for org scoping.
  - `ebay_finances_fees` for per-transaction fee aggregates.

- Data query (abridged):

  ```sql
  SELECT
      t.ebay_account_id,
      t.ebay_user_id,
      t.transaction_id,
      t.transaction_type,
      t.transaction_status,
      t.booking_date,
      t.transaction_amount_value,
      t.transaction_amount_currency,
      t.order_id,
      t.order_line_item_id,
      t.payout_id,
      t.seller_reference,
      t.transaction_memo
  FROM ebay_finances_transactions t
  JOIN ebay_accounts a ON a.id = t.ebay_account_id
  WHERE a.org_id = :user_id AND [...]
  ORDER BY ...
  LIMIT :limit OFFSET :offset
  ```

- Fee aggregation from `ebay_finances_fees` produces:

  - `final_value_fee`
  - `promoted_listing_fee`
  - `shipping_label_fee`
  - `other_fees`
  - `total_fees`

#### `finances_fees` grid

- Helper: `_get_finances_fees_data(db, current_user, selected_cols, limit, offset, sort_column, sort_dir, from_date, to_date)`
- SQL over `ebay_finances_fees` joined to `ebay_accounts`:

  ```sql
  SELECT
      f.id,
      f.ebay_account_id,
      f.transaction_id,
      f.fee_type,
      f.amount_value,
      f.amount_currency,
      f.raw_payload,
      f.created_at,
      f.updated_at
  FROM ebay_finances_fees f
  JOIN ebay_accounts a ON a.id = f.ebay_account_id
  WHERE a.org_id = :user_id AND [...]
  ```

#### `buying` grid

- Helper: `_get_buying_data(db, current_user, selected_cols, limit, offset, sort_column, sort_dir)`
- Tables: `EbayBuyer`, `EbayStatusBuyer`, `EbayAccount` via SQLAlchemy:

  ```python
  query = (
      db.query(EbayBuyer, EbayStatusBuyer)
      .join(EbayAccount, EbayBuyer.ebay_account_id == EbayAccount.id)
      .outerjoin(EbayStatusBuyer, EbayBuyer.item_status_id == EbayStatusBuyer.id)
      .filter(EbayAccount.org_id == current_user.id)
  )
  ```

- Base values used for the grid:

  ```python
  base_values = {
      "id": buyer.id,
      "tracking_number": buyer.tracking_number,
      "refund_flag": buyer.refund_flag,
      "storage": buyer.storage,
      "profit": ...,
      "buyer_id": buyer.buyer_id,
      "seller_id": buyer.seller_id,
      "paid_time": buyer.paid_time,
      "amount_paid": ...,
      "days_since_paid": days_since_paid,
      "status_label": status.label if status else None,
      "record_created_at": buyer.record_created_at,
      "title": buyer.title,
      "comment": buyer.comment,
  }
  ```

#### `sku_catalog` grid

- Helper: `_get_sku_catalog_data(db, current_user, selected_cols, limit, offset, sort_column, sort_dir, search)`
- Table: `SqItem` (SQ catalog), comment “backed by the SQ catalog table (sq_items)”.
- Query: `db.query(SqItem)` with optional `ilike` filters on SKU/title/description/part_number/mpn/upc/part.
- `base_values` includes a wide set of SQ catalog fields; key ones:

  - IDs: `id, sku_code, sku, sku2, model_id, model, part, part_number`
  - Pricing: `price, previous_price, brutto`
  - Category/market: `market, use_ebay_id, category`
  - Description and condition: `description, condition_id, condition_description`
  - Shipping: `shipping_type, shipping_group, shipping_group_previous`
  - Alerts/status: `alert_flag, alert_message, record_status, record_status_flag, checked_status, checked, checked_by`
  - Images: `pic_url1, pic_url2, pic_url3, image_url`
  - App-specific: `title, brand, warehouse_id, storage_alias`
  - Audit: `record_created_by, record_created, record_updated_by, record_updated`

#### `inventory` grid

- Helper: `_get_inventory_data(db, current_user, selected_cols, limit, offset, sort_column, sort_dir, storage_id, ebay_status, search)`
- Table: reflected `TblPartsInventory.__table__` (Supabase `tbl_parts_inventory`).
- Behavior:

  - If `TblPartsInventory.__table__` is `None` or has no columns → returns empty result set.
  - Otherwise:
    - Builds `cols_by_key` and `cols_by_lower` maps for all reflected columns.
    - Filters:
      - `storage_id` across storage-related column names (`storageid, storage_id, storage, alternativestorage, alternative_storage, storagealias, storage_alias`).
      - `ebay_status` via `ebay_status/ebaystatus/ebay_status_id`.
      - `search` across all string-like columns.
    - Sorts by requested column or by PK/first column.
    - Serializes only `selected_cols` from the SQLAlchemy row mapping.

#### `active_inventory` grid

- Helper: `_get_active_inventory_data(db, current_user, selected_cols, ...)`
- Tables: `ActiveInventory` joined to `EbayAccount`:

  ```python
  query = (
      db.query(ActiveInventory)
      .join(EbayAccount, ActiveInventory.ebay_account_id == EbayAccount.id)
      .filter(EbayAccount.org_id == current_user.id)
  )
  ```

- Column set mirrors `ACTIVE_INVENTORY_COLUMNS_META`: `last_seen_at, sku, item_id, title, quantity_available, price, currency, listing_status, ebay_account_id`.

#### `cases` grid

- Helper: `_get_cases_data(db, current_user, selected_cols, limit, offset, sort_column, sort_dir, state, buyer, from_date, to_date)`
- Union over two tables via raw SQL: `ebay_disputes` and `ebay_cases`.
- Produces a unified logical row per dispute/case with fields like:

  - `kind` (payment_dispute/postorder_case), `external_id`, `order_id`, `status`, `reason`, `open_date`, `respond_by_date`, `ebay_account_id`, `ebay_user_id`, `buyer_username`, `amount`, `currency`, `issue_type`.

#### `offers` grid

- Helper: `_get_offers_data(db, current_user, selected_cols, limit, offset, sort_column, sort_dir, state, direction, buyer, item_id, sku, from_date, to_date)`
- Table: `Offer`/`OfferModel` with enums `OfferState`, `OfferDirection`.
- Query: `db.query(OfferModel).filter(OfferModel.user_id == current_user.id)` with filters on state, direction, buyer, item_id, sku, and created_at range.
- Column set matches `OFFERS_COLUMNS_META` and model fields: `created_at, offer_id, direction, state, item_id, sku, buyer_username, quantity, price_value, price_currency, original_price_value, original_price_currency, expires_at`.

#### `accounting_bank_statements`, `accounting_cash_expenses`

- `get_grid_data` branches for these keys but calls helpers that are **not implemented**:

  - `_get_accounting_bank_statements_data(...)`
  - `_get_accounting_cash_expenses_data(...)`

- Only column metadata is defined in `grid_layouts.py`:

  - `ACCOUNTING_BANK_STATEMENTS_COLUMNS_META` (id, statement_period_start, statement_period_end, bank_name, account_last4, currency, rows_count, status, created_at).
  - `ACCOUNTING_CASH_EXPENSES_COLUMNS_META` (id, date, amount, currency, expense_category_id, counterparty, description, storage_id, paid_by_user_id, created_by_user_id).

- Without those helpers, these grids do not have a runnable data query path.

#### `accounting_transactions` grid

- Helper: `_get_accounting_transactions_grid_data(db, current_user, selected_cols, limit, offset, sort_column, sort_dir, date_from, date_to, source_type, storage_id)`
- Table: `AccountingTxn`.
- Filters by date range, source_type, storage_id.
- Column set from `ACCOUNTING_TRANSACTIONS_COLUMNS_META`: `id, date, direction, amount, account_name, counterparty, expense_category_id, storage_id, source_type, is_personal, is_internal_transfer, description`.

---

## 3. Column Metadata (`available_columns`) – Source & Emptiness

### 3.1 How `available_columns` is produced (backend)

Endpoint: `GET /api/grid/preferences` → `backend/app/routers/grid_preferences.py:get_grid_preferences`:

```python
allowed_cols = _allowed_columns_for_grid(grid_key)
if not allowed_cols:
    raise HTTPException(status_code=404, detail="Unknown grid_key")

layout = (
    db.query(UserGridLayout)
    .filter(UserGridLayout.user_id == current_user.id, UserGridLayout.grid_key == grid_key)
    .first()
)

available_columns = _columns_meta_for_grid(grid_key)
columns_cfg = _build_columns_from_layout(grid_key, layout)
```

So `available_columns` is always `_columns_meta_for_grid(grid_key)`.

`_columns_meta_for_grid` is defined in `backend/app/routers/grid_layouts.py` and maps grid keys to `*_COLUMNS_META` lists or, for `inventory`, builds metadata by reflecting `TblPartsInventory`.

### 3.2 `_columns_meta_for_grid` behavior

Key mapping (simplified):

- `"orders"` → `ORDERS_COLUMNS_META`
- `"transactions"` → `TRANSACTIONS_COLUMNS_META`
- `"messages"` → `MESSAGES_COLUMNS_META`
- `"offers"` → `OFFERS_COLUMNS_META`
- `"sku_catalog"` → `SKU_CATALOG_COLUMNS_META`
- `"active_inventory"` → `ACTIVE_INVENTORY_COLUMNS_META`
- `"inventory"` → `_inventory_columns_meta_from_reflection()`
- `"cases"` → `CASES_COLUMNS_META`
- `"finances"` → `FINANCES_COLUMNS_META`
- `"finances_fees"` → `FINANCES_FEES_COLUMNS_META`
- `"buying"` → `BUYING_COLUMNS_META`
- `"accounting_bank_statements"` → `ACCOUNTING_BANK_STATEMENTS_COLUMNS_META`
- `"accounting_cash_expenses"` → `ACCOUNTING_CASH_EXPENSES_COLUMNS_META`
- `"accounting_transactions"` → `ACCOUNTING_TRANSACTIONS_COLUMNS_META`

For `inventory`, `_inventory_columns_meta_from_reflection()`:

- Returns an empty list **only** if `TblPartsInventory.__table__` is `None` or has zero columns.
- Otherwise, creates one `ColumnMeta` per real DB column (`name = col.key`).

Thus, from the backend’s POV:

- For all grid keys **except `inventory`**, `available_columns` is hard-coded and should be non-empty.
- For `inventory`, `available_columns` can be empty if and only if table reflection fails or the table has no columns.

### 3.3 Frontend `useGridPreferences` fallback behavior

`frontend/src/hooks/useGridPreferences.ts` resolves preferences like this:

1. **Primary**: `GET /api/grid/preferences?grid_key=...`
2. **Fallback 1**: `GET /api/grids/{gridKey}/layout`
3. **Fallback 2** (last resort): `GET /api/grids/{gridKey}/data?limit=1&offset=0` and infer columns from the first row’s keys.

If any of these steps succeeds with at least one column, the hook sets `availableColumns` and `columns` accordingly.

`availableColumns` on the frontend will only be empty if **all three** paths fail or return no usable rows, *or* if the backend metadata truly has zero columns (e.g. `inventory` when reflection fails).

### 3.4 Emptiness matrix

Backend-only:

- `orders, transactions, messages, offers, sku_catalog, active_inventory, cases, finances, finances_fees, buying, accounting_bank_statements, accounting_cash_expenses, accounting_transactions` → `available_columns` is expected to be **non-empty** (hard-coded lists).
- `inventory` → `available_columns` can be `[]` if `TblPartsInventory` reflection fails.

Combined backend + frontend:

`availableColumns` from `useGridPreferences` can be empty if:

- `/api/grid/preferences` fails, **and**
- `/api/grids/{gridKey}/layout` fails, **and**
- `/api/grids/{gridKey}/data?limit=1` either fails or returns 0 rows; **or**
- Backend truly has no metadata (e.g. broken `inventory` reflection) and the data sample also yields no keys.

---

## 4. Summary

- There is **no DB connectivity** in this environment; all database references are derived from the codebase, not from actual Supabase/Railway introspection.
- Every `gridKey` used by `DataGridPage` has a clear mapping to:
  - A shared data endpoint `/api/grids/{grid_key}/data` with a private helper in `grids_data.py` (except the two accounting grids whose helpers are missing), and
  - Centralized column metadata via `_columns_meta_for_grid(grid_key)`.
- Backend `available_columns` is:
  - Hard-coded and non-empty for all standard grids except `inventory`.
  - Dynamic and potentially empty only for `inventory` (if `TblPartsInventory` reflection fails).
- Frontend `useGridPreferences` layers multiple fallbacks (preferences, legacy layout, data sampling). `availableColumns` will only be truly empty when **all** backend routes and the data sample path fail or return no data, or when the backend exposes no metadata at all.

This audit should give a clear, code-based picture of where each grid’s data and columns come from, and where “NO COLUMNS CONFIGURED” could originate from backend vs. frontend behavior.
