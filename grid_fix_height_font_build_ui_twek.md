## Grid: fix height + unify font/density + build UI Tweak controls

### Context / symptoms
We had a recurring issue where **Ledger 2 showed row count but the AG Grid looked empty** (no headers/rows visible) and there were no blocking JS errors.

We also wanted **all grids to look like the legacy system**:
- more rows visible (denser rows)
- darker/crisper font (legacy Windows/table feel)
- consistent behavior across all pages
- **do not break** column resize / saved layouts (Columns → save)

---

## Root causes

### 1) AG Grid requires a *definite height*
AG Grid (virtualized layout) needs its container to have a **real height** (not just `min-height` or a flex chain that collapses).
If the container height resolves to ~0px, the grid initializes but its internal wrappers collapse and the grid appears blank.

**Fix pattern:** wrap grids in a reusable container that guarantees a height.

Implemented component:
- `frontend/src/components/datagrid/GridSection.tsx`

Usage example (Ledger 2):
- `frontend/src/pages/Accounting2Page.tsx` uses `<GridSection mode="fixed">...` which applies:
  - `height: var(--ui-grid-default-height, 60vh)`
  - `minHeight: var(--ui-grid-min-height, 360px)`

This keeps AG Grid renderable even if the page layout does not provide an explicit height.

### 2) UI Tweak did not fully control AG Grid density before
We already had UI Tweak setting `--grid-*` CSS variables, but AG Grid was effectively using **hardcoded** AG variables in CSS for row/header heights.

Outcome: the UI Tweak “Grid density” selector didn’t actually control the AG grid’s row height/padding/feel.

---

## Current architecture (after fix)

### A) Central styling contract: `--grid-*` → `--ag-*`
We use `--grid-*` variables as our app-level contract and map them into AG Grid CSS variables.

Key variables:
- `--grid-font-family`
- `--grid-font-size`
- `--grid-spacing`
- `--grid-row-height`
- `--grid-header-height`

Mapped in `frontend/src/index.css` under `.app-grid__ag-root`:
- `--ag-font-family: var(--grid-font-family)`
- `--ag-font-size: var(--grid-font-size)`
- `--ag-spacing: var(--grid-spacing)`
- `--ag-row-height: var(--grid-row-height)`
- `--ag-header-height: var(--grid-header-height)`

Also mapped to keep legacy contrast:
- `--ag-foreground-color` uses `--ui-color-text-primary`
- header text uses `--grid-header-text-color`

This means **one place** controls the visuals for all AG grids.

### B) `DataGridPage` applies global density class
All grids using `DataGridPage` now apply density from global UI Tweak:
- `grid-density-${uiTweak.gridDensity}`

Per-grid column layout persistence is unchanged:
- Column widths/order/visibility are stored via `/grid/preferences` and saved via the existing “Columns” flow.
- Our changes do NOT touch the column model or persistence logic.

---

## UI Tweak controls

UI Tweak is applied globally by `UITweakContext` which writes CSS custom properties onto `document.documentElement`.

### Controls added / fixed

**Existing:**
- Global font scale
- Navigation scale
- Grid density preset (compact/normal/comfortable)
- Grid theme colors

**Added to support legacy-like grids:**
1) **Grid padding (spacing)**
   - `gridSpacingPx` → sets `--grid-spacing`
2) **Grid row & header heights**
   - `gridRowHeightPx` → sets `--grid-row-height`
   - `gridHeaderHeightPx` → sets `--grid-header-height`
3) **Grid font size**
   - `gridFontSizePx` → sets `--grid-font-size` (and therefore AG Grid `--ag-font-size`)

Also previously added:
- `gridFontFamily`
- `typography.fontWeight.tableHeader`
- `typography.fontWeight.tableCell`

### Presets behavior
Grid density selector acts like a preset and updates:
- `gridSpacingPx`
- `gridRowHeightPx`
- `gridHeaderHeightPx`

So you can:
- choose a preset (legacy-like default is `compact`)
- then fine-tune spacing/heights manually

---

## Backend persistence

UI Tweak settings are persisted as a single JSON document in `ui_tweak_settings.settings`.

Updated schema (JSON fields):
- `gridFontFamily`
- `gridSpacingPx`
- `gridRowHeightPx`
- `gridHeaderHeightPx`
- `gridFontSizePx`

Backend endpoints:
- `GET /api/ui-tweak` (user)
- `GET /api/admin/ui-tweak` (admin)
- `PUT /api/admin/ui-tweak` (admin)

Code:
- `backend/app/routers/ui_tweak.py`

Seed defaults updated in:
- `backend/alembic/versions/ui_tweak_settings_20251121.py`
- `supabase/migrations/20251211090000_ui_tweak_settings.sql`

---

## Default “legacy-like” values

Defaults chosen to match the legacy feel:
- `gridDensity = compact`
- `gridFontFamily = Tahoma/Segoe UI` (crisper, more "Windows table" feel)
- `gridSpacingPx = 4`
- `gridRowHeightPx = 22`
- `gridHeaderHeightPx = 24`
- Header text color = `#111827`
- Header weight = bold, cell weight = medium

---

## How to verify

### Visual
1) Open any `DataGridPage` (Inventory / Ledger / Orders).
2) Confirm rows are denser and text is darker/crisper.

### Functional
1) Resize a column → open **Columns** → Save.
2) Refresh page → confirm saved widths/order/visibility remain.

### Admin UI Tweak
1) Open Admin → UI Tweak.
2) Change:
   - Grid density preset
   - Grid padding (spacing)
   - Row height / header height
   - Grid font family
3) Refresh and confirm values persisted (admin-only persistence; non-admin may see local-only behavior).

---

## Notes / guardrails
- Avoid writing CSS rules that override `position/overflow` on AG Grid internals. Use `--ag-*` variables for row/header heights and spacing.
- If a new page uses a grid inside a flex layout, ensure the height chain is correct. If not, wrap with `GridSection mode="fixed"`.
