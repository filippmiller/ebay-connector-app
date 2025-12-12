# Grid System and Recent Updates

_Last updated: 2025-11-21_

This document is a single, hands-off reference for how **all data grids** work today, how they were modernized, and where to hook in future changes (including a potential migration to AG Grid).

It consolidates information that was previously scattered between `grid-layout-notes.md`, session notes, and inline comments.

---

## 1. Current grid architecture (high level)

### 1.1 Backend pieces

**Core files**

- `backend/app/routers/grid_layouts.py`
  - Declares per-grid column metadata (`*_COLUMNS_META`) and `GRID_DEFAULTS`.
  - Knows which `grid_key` values exist (e.g. `transactions`, `orders`, `offers`, `finances`, `cases`, `active_inventory`, `buying`, `accounting_*`, etc.).
- `backend/app/routers/grids_data.py`
  - Implements `GET /api/grids/{grid_key}/data`.
  - Responsible for turning requested columns + filters into SQL queries and returning a generic grid payload:
    - `rows: List[Dict[str, Any]]`
    - `limit`, `offset`, `total`
    - optional `sort` info.
- `backend/app/models_sqlalchemy/models.py`
  - Defines `UserGridLayout`, which stores per-user preferences:
    - `visible_columns`
    - `column_widths`
    - `sort`
    - `theme` JSON (see below).
- `backend/app/routers/grid_preferences.py`
  - Newer, unified endpoint: `GET/POST/DELETE /api/grid/preferences`.
  - Wraps `UserGridLayout` + `GRID_DEFAULTS` and exposes a fully-computed per-user configuration for each `grid_key`.

**Key models**

```text
GridTheme (backend)
- density: "compact" | "normal" | "comfortable"
- fontSize: "small" | "medium" | "large" (legacy preset)
- headerStyle: "default" | "bold" | "accent"
- colorScheme: "default" | "blue" | "dark" | "highContrast"
- buttonLayout: "left" | "right" | "split"
- ...extra forward-compatible flags allowed (JSON field)

GridColumnsConfig
- visible: [column names]
- order: [column names, canonical order]
- widths: { [column]: width_px }
- sort: { column: string; direction: "asc" | "desc" } | null

GridPreferencesResponse
- grid_key: string
- available_columns: ColumnMeta[] (from grid_layouts)
- columns: GridColumnsConfig
- theme: GridTheme
```

The `theme` JSON is stored per-user per-grid in `user_grid_layouts.theme` and is **round-tripped** through `/api/grid/preferences`.

### 1.2 Frontend pieces

**Shared React hook**

- `frontend/src/hooks/useGridPreferences.ts`
  - Talks to `/api/grid/preferences` (new) and falls back to legacy `/api/grids/{grid_key}/layout` and `/api/grids/{grid_key}/data` if needed.
  - Returns:
    - `availableColumns`
    - `columns` (layout: visible, order, widths, sort)
    - `theme` (density, font size, color scheme, etc.)
    - `setColumns(partial)` and `setTheme(partial)` for local state
    - `save()` → persists to `/api/grid/preferences` (columns + theme).

**Shared grid component**

- `frontend/src/components/DataGridPage.tsx`
  - The **only** grid engine currently used for all generic data tables.
  - Responsibilities:
    - Load grid layout & theme via `useGridPreferences(gridKey)`.
    - Automatically infer an initial layout if the user has no saved preferences.
    - Fetch data via `/api/grids/{grid_key}/data` with:
      - `limit`, `offset`
      - `columns` (visible columns, comma-separated)
      - `sort_by`, `sort_dir`
      - extra filters from `extraParams` prop
    - Render a flexible toolbar with:
      - Search box (client-side addition to query params).
      - Sort selector (maps to grid sort state + API params).
      - Rows-per-page selector.
      - Columns button to open layout & theme panel.
    - Render the table markup (header + body) with:
      - Column dragging to reorder.
      - Column visibility toggles.
      - Column resizing (drag handle on header cells, persisted automatically).
      - Row click handling via `onRowClick(row)` prop.
    - Render a modal **Columns & layout** panel to edit:
      - Which columns are visible.
      - Column order.
      - Grid theme (density, font size, color scheme, toolbar layout, background, header text color, etc.).

**Grid theming helpers**

- `frontend/src/index.css`
  - Declares CSS variables and helper classes for grids:
    - Global defaults:
      - `--grid-row-height`, `--grid-header-height`, `--grid-font-size` (used by `.app-grid`).
      - `--grid-header-bg`, `--grid-header-text-color`, `--grid-row-hover-bg`, etc.
    - `.app-grid` wrapper + density classes:
      - `.app-grid` uses `font-size: var(--grid-font-size)`.
      - `.app-grid thead th` & `tbody tr` use the header/row height variables.
      - `.app-grid.grid-density-compact|normal|comfortable` override heights & font size.
    - Color themes:
      - `.app-grid.grid-theme-default|blue|dark|highContrast` set header background/text colors and full dark theme overrides.
    - Typography helpers:
      - `.ui-table-header`, `.ui-table-cell` – used by grid headers/body cells.
  - UITweak also sets root-level grid variables (`--grid-row-height`, `--grid-header-height`, `--grid-font-size`) so **both** TweakUI and per-grid theme can influence appearance.

---

## 2. How DataGridPage works end‑to‑end

### 2.1 Props and responsibilities

```ts
<DataGridPage
  gridKey="orders"               // required – matches backend grid_key
  title="Orders"                 // optional toolbar title
  extraParams={extraFilters}      // optional query params (filters)
  onRowClick={(row) => {...}}     // optional row click callback
/>
```

Internally it:

1. Calls `useGridPreferences(gridKey)`.
2. Ensures an initial `GridColumnsConfig` exists (all allowed columns visible) if user has no saved layout.
3. Derives `orderedVisibleColumns` from `columns.order` ∩ `columns.visible`.
4. Recomputes `columns` state with labels + widths using `availableColumns` metadata.
5. Fetches data from `/api/grids/{grid_key}/data` whenever:
   - grid key, filters, search, pagination, or sort changes;
   - the columns configuration changes (e.g. visible columns).
6. Renders:
   - Toolbar (title, search, sort, page size, Columns button, total rows counter).
   - Error banner (if data fetch failed).
   - Scrollable table area (`.app-grid` wrapper + `table` markup).
   - Columns & layout modal.

### 2.2 Layout and resizing

- Column metadata comes from backend `available_columns`:
  - `name`, `label`, `type`, `width_default`, `sortable`.
- User can:
  - Reorder columns via drag handle in header.
  - Resize columns via drag handle at the right edge of each header cell.
  - Toggle column visibility in the Columns panel.
- `useGridPreferences.setColumns(...)` is used to mutate `GridColumnsConfig` and is persisted using `save()`.
- After each resize drag finishes, `DataGridPage`:
  - Collects latest widths into `columns.widths`.
  - Calls `setColumns({ widths })`.
  - Immediately calls `gridPrefs.save()` so the new widths persist without an extra click.

### 2.3 Theming inside DataGridPage

`DataGridPage` reads `gridPrefs.theme` and maps it to concrete visual properties:

- Density
  - `theme.density` → `className="app-grid grid-density-{density} ..."`.
  - CSS sets row/header height + base font size per density.
- Color scheme
  - `theme.colorScheme` → `className="... grid-theme-{colorScheme}"`.
  - CSS theme classes adjust header/bg colors, especially for `blue` and `dark`.
- Body font size
  - `theme.bodyFontSizeLevel` (1–10) maps to ~11–20px.
  - If missing, we fall back to legacy `theme.fontSize` (small/medium/large) and convert that to a numeric level.
  - Applied via inline `style={{ fontSize: bodyFontSizePx }}` on `.app-grid`.
- Body font weight/style
  - `theme.bodyFontWeight` → `normal | bold`.
  - `theme.bodyFontStyle` → `normal | italic`.
- Header font size
  - `theme.headerFontSize` (small/medium/large) is mapped to ~11/13/15px.
  - Applied inline on `<th>` elements.
- Header text color
  - `theme.headerTextColor` (hex string) overrides header color if present; otherwise theme CSS controls it.
- Grid background
  - `theme.backgroundColor` optional hex; used as `backgroundColor` on wrapper and body cells.

The **Columns & layout modal** exposes these theme properties via small selects, sliders, and a color picker. Saving the modal commits theme changes to `/api/grid/preferences`.

---

## 3. TweakUI integration for grids

While grid theme is per-grid and per-user, there is also a **global** UITweak system that influences grids alongside the rest of the UI.

**Key files**

- `frontend/src/contexts/UITweakContext.tsx`
  - Holds `UITweakSettings` with:
    - global `fontScale` and `navScale`.
    - `gridDensity` preset (compact / normal / comfortable).
    - fine-grained typography + color roles and control sizes.
  - `applySettingsToDocument(settings)` writes CSS variables onto `<html>`:
    - `--ui-font-scale`, `--ui-nav-scale`.
    - Text and button colors.
    - `--ui-scale-button-input` etc.
    - **Grid-specific:** sets `--grid-row-height`, `--grid-header-height`, `--grid-font-size` based on `settings.gridDensity`.
- `frontend/src/index.css`
  - Uses those variables in `.app-grid` and in typography helpers `.ui-table-header` and `.ui-table-cell`.
- `frontend/src/pages/AdminUITweakPage.tsx`
  - Provides a UI to adjust global `fontScale`, `navScale`, `gridDensity`, nav colors, and (recently) color pickers for nav state colors.

**Effect on grids**

- Changing **global font scale** makes almost all Tailwind `rem`-based text and spacing bigger, including grid toolbars and cells.
- Changing **UI grid density** from UITweak adjusts the base `--grid-row-height`, `--grid-header-height`, `--grid-font-size` that `.app-grid` uses.
- The per-grid **theme density** still exists; if both are set, they are layered:
  - UITweak sets global defaults.
  - `.app-grid.grid-density-*` classes from `gridPrefs.theme` can override them on a per-grid basis.

In other words, UITweak is the global knob; per-grid theme is the fine-tuning knob stored per user.

---

## 4. Where grids are used today

All the following pages use `DataGridPage` as their engine:

- `frontend/src/pages/TransactionsPage.tsx`
  - `gridKey="transactions"` – sales transactions.
- `frontend/src/pages/OrdersPage.tsx`
  - `gridKey="orders"`.
- `frontend/src/pages/InventoryPage.tsx`
  - `gridKey="active_inventory"` – active eBay listings.
- `frontend/src/pages/InventoryPageV3.tsx`
  - `gridKey="inventory"` with additional filters for storage and eBay status.
- `frontend/src/pages/SKUPage.tsx`
  - `gridKey="sku_catalog"` – main SKU catalog grid used with a details panel and SKU edit modal.
- `frontend/src/pages/ListingPage.tsx`
  - Top grid: `gridKey="sku_catalog"` used as SKU picker for draft listing builder.
  - Bottom grid: custom table (not `DataGridPage`) for draft rows.
- `frontend/src/pages/OffersPageV2.tsx`
  - `gridKey="offers"` + filters and refresh key, plus CSV export.
- `frontend/src/pages/CasesPage.tsx`
  - `gridKey="cases"` for disputes/cases.
- `frontend/src/pages/BuyingPage.tsx`
  - `gridKey="buying"` with on-row-click detail panel.
- `frontend/src/pages/FinancialsPage.tsx`
  - Ledger tab: `gridKey="finances"` with date/type/search filters.
  - Fees tab: `gridKey="finances_fees"`.
- `frontend/src/pages/AccountingPage.tsx`
  - Bank statements tab:
    - `gridKey="accounting_bank_statements"` with filters.
  - Cash expenses tab:
    - `gridKey="accounting_cash_expenses"`.
  - Transactions tab:
    - `gridKey="accounting_transactions"` with richer filters and a side panel editing selected rows.

Other table-like layouts (e.g., some admin detail tables, draft listing bottom grid, bank-statement rows detail table) still use bespoke markup and **do not** go through `DataGridPage` yet.

---

## 5. What changed compared to the original grid system

Historically, grids were wired like this:

- Frontend components called `/api/grids/{grid_key}/layout` directly.
- There was no unified `GridTheme`; all theming was hard-coded in CSS.
- Several pages had custom local grids instead of using a shared abstraction.

Recent work introduced the following improvements:

1. **Unified grid preferences endpoint**
   - Added `backend/app/routers/grid_preferences.py` and `frontend/src/hooks/useGridPreferences.ts`.
   - All grids now fetch a single `GridPreferencesResponse` per `grid_key` that contains both:
     - `columns` (layout) and
     - `theme` (appearance).
   - Legacy `/api/grids/{grid_key}/layout` is still supported as a fallback but should be considered deprecated.

2. **Per-user grid theme**
   - Introduced `GridTheme` JSON stored alongside layout in `UserGridLayout`.
   - Frontend can adjust density, color scheme, header style, font sizes, etc. and persist them.
   - These settings are surfaced to users via the **Columns & layout** panel in `DataGridPage`.

3. **Grid theming CSS & UITweak integration**
   - Added `.app-grid` wrapper and density/theme classes in `index.css`.
   - Introduced typography helpers `.ui-table-header` / `.ui-table-cell` used across grid headers/body.
   - Extended UITweak to own `gridDensity` and map it onto `--grid-row-height`, `--grid-header-height`, and `--grid-font-size`, making grid readability controllable from the Admin → UI Tweak screen.

4. **Broader adoption of `DataGridPage`**
   - Newer pages such as `BuyingPage`, `AccountingPage`, the Finances ledger/fees tabs, the SKU catalog in `ListingPage`, and the V3 Inventory screen were all built directly on top of `DataGridPage`.
   - This replaces several one-off grids and ensures per-user layouts, sorting, and theming work consistently.

5. **Quality-of-life fixes**
   - Auto-saving column widths on resize.
   - Better fallback behavior if preferences are missing or corrupted:
     - Attempt new endpoint → legacy layout → infer columns from sample data.
   - More explicit typing of numeric font size levels for future AG Grid/other engine usage.

---

## 6. How to add or change a grid today

### 6.1 Backend steps

1. Define column metadata in `grid_layouts.py`:
   - Add a `*_COLUMNS_META` list of `ColumnMeta` entries with `name`, `label`, `type`, `width_default`, `sortable`.
   - Add an entry in `GRID_DEFAULTS` specifying visible columns and default sort.
2. Wire the grid key into `grids_data.py`:
   - Add a branch in `get_grid_data` for your `grid_key`.
   - Implement a helper like `_get_{grid_key}_data(...)` that returns the standard grid payload.
3. Ensure `grid_layouts._allowed_columns_for_grid` and `_columns_meta_for_grid` know about the new `grid_key`.

### 6.2 Frontend steps

1. Create or update a page component to use `DataGridPage`:
   - Import: `import { DataGridPage } from '@/components/DataGridPage';`.
   - Render it with `gridKey` matching backend and optional filters via `extraParams`.
2. If you need row click behavior (detail panels, edit forms):
   - Pass `onRowClick={(row) => ...}`; the row is the raw object returned from the backend for that grid.
3. If the grid should follow special global UX rules (e.g. always compact):
   - Consider adjusting `GRID_DEFAULTS` or initial `GridTheme` for that `grid_key`.

---

## 7. Notes on the planned AG Grid migration

There is a separate design proposal to **replace the current hand-rolled `<table>` rendering in `DataGridPage` with AG Grid Community** while keeping the same backend contract and user-facing behavior.

The high-level idea is:

- Introduce a new `AppDataGrid` component that wraps `AgGridReact` and:
  - Uses existing `/api/grids/{grid_key}/data` and `/api/grid/preferences` infrastructure.
  - Maps `GridTheme` + UITweak settings into custom AG Grid theme CSS variables.
- Gradually replace the internals of `DataGridPage` with `AppDataGrid` without changing any call sites.
- Keep the per-user `GridTheme` + UITweak knobs as the single source of truth for visual behavior.

**Important:** this migration has **not** been implemented yet; this document describes the **current** system and is the starting point for that migration.

---

## 8. Summary

- All main operational data tables are now unified behind `DataGridPage`, `useGridPreferences`, and the `/api/grid/preferences` + `/api/grids/{grid_key}/data` backend.
- Grid **layout** (columns, order, widths, sort) and **theme** (density, colors, font sizes) are stored per user in `user_grid_layouts` and editable via the UI.
- The global **UITweak** system provides higher-level control over font scaling, grid density, and typography, which feed into grid CSS variables.
- Future engine swaps (e.g., AG Grid) can be implemented inside `AppDataGrid`/`DataGridPage` without changing any backend APIs or page-level usage.
