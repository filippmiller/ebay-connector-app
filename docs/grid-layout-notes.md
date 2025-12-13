# Grid Layout Infrastructure Notes

_Last updated: 2025-11-18_

This document summarizes the current grid infrastructure and where the shared `DataGridPage` component is used vs. legacy/custom tables.

## 1. Shared grid infrastructure

### Backend

Generic grid layout + data are handled via FastAPI routers:

- `backend/app/routers/grid_layouts.py`
  - Defines per-grid column metadata (`*_COLUMNS_META`) and `GRID_DEFAULTS`.
  - Exposes per-user layout endpoints under `/api/grids/{grid_key}/layout`.
- `backend/app/routers/grids_data.py`
  - Exposes data endpoints under `/api/grids/{grid_key}/data`.
  - Supports grid keys:
    - `orders`
    - `transactions`
    - `messages`
    - `offers`
    - `active_inventory`
    - `cases`
    - `finances`
    - `finances_fees`

Per-user layouts are stored in `user_grid_layouts` (SQLAlchemy: `UserGridLayout`).

### Frontend

The shared React grid wrapper lives in:

- `frontend/src/components/DataGridPage.tsx`

It is responsible for:

- Fetching layout from `/api/grids/{grid_key}/layout`.
- Managing visible columns, widths, and sort order.
- Fetching data from `/api/grids/{grid_key}/data`.
- Rendering the table with column drag-to-reorder, visibility toggles, and resizable columns.

## 2. Pages currently using `DataGridPage`

These pages already use the shared grid infrastructure with the indicated `gridKey` / `grid_key` values.

- `frontend/src/pages/TransactionsPage.tsx`
  - `gridKey="transactions"`
  - Grid title: "Transactions".

- `frontend/src/pages/OrdersPage.tsx`
  - `gridKey="orders"`
  - Grid title: "Orders".

- `frontend/src/pages/InventoryPage.tsx`
  - `gridKey="active_inventory"`
  - Grid title: "Active Inventory".

- `frontend/src/pages/CasesPage.tsx`
  - `gridKey="cases"`
  - Grid title: "Cases & Disputes".

- `frontend/src/pages/FinancialsPage.tsx`
  - Ledger tab:
    - `gridKey="finances"`
    - Grid title: "Finances ledger".
    - Passes filter params via `extraParams`.
  - Fees tab:
    - `gridKey="finances_fees"`
    - Grid title: "Finances fees".

- `frontend/src/pages/OffersPageV2.tsx`
  - `gridKey="offers"`
  - Grid title: "Offers".
  - Passes filter params via `extraParams`.

## 3. Grids defined on the backend but not yet using `DataGridPage`

- Grid key: `messages`
  - Backend:
    - Column metadata and defaults in `backend/app/routers/grid_layouts.py` (`MESSAGES_COLUMNS_META`, `GRID_DEFAULTS["messages"]`).
    - Data implementation in `backend/app/routers/grids_data.py` (`_get_messages_data`).
  - Frontend:
    - `frontend/src/pages/MessagesPage.tsx` uses a custom Gmail-style list/detail layout (no `DataGridPage` yet).

## 4. Legacy/custom tables and list views (not using `DataGridPage`)

These screens render their own tables or card lists and do not go through the shared grid system yet.

- `frontend/src/pages/MessagesPage.tsx`
  - Custom master/detail view with a scrollable list and message detail pane.
  - No integration with `/api/grids/messages/*` or `DataGridPage`.

- `frontend/src/pages/InventoryPageV2.tsx`
  - Custom `<table>` for production inventory with bulk actions.
  - Fetches data from `/api/inventory/search` directly.

- `frontend/src/pages/InventoryPageV3.tsx`
  - Another custom `<table>` implementation for inventory, optimized for density/keyboard-like usage.
  - Also fetches from `/api/inventory/search` directly.

- `frontend/src/pages/OrdersViewPage.tsx`
  - Card-based list of orders and line-items.
  - Uses `/ebay/orders` and `/ebay/orders/filter` endpoints.

- `frontend/src/pages/OffersPage.tsx`
  - Card/grid layout of offers (older offers UI).
  - Uses legacy `offers` API helpers instead of the generic grids API.

Other pages like `BuyingPage`, `ReturnsPage`, `ShippingPage`, `SKUPage`, and various admin pages either do not render tabular data yet or use bespoke layouts that are not wired into `DataGridPage`.

## 5. Standardization plan (high level)

- Treat `DataGridPage` + `/api/grids/{grid_key}/layout` + `/api/grids/{grid_key}/data` as the single source of truth for all primary data grids.
- Ensure all main operational grids (Transactions, Orders, Inventory, Offers, Cases/Disputes, Finances) continue to use this shared system.
- Migrate remaining table-like UIs (e.g., Messages, legacy inventory views, legacy offers view) onto `DataGridPage` over time so they benefit from:
  - Per-user column layout persistence.
  - Column resizing and reordering.
  - Global theming and density controls (to be implemented).
