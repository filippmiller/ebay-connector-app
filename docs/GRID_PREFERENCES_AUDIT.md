# Grid Preferences Audit (AG Grid / AppDataGrid)

## 1. Overview

The eBay Connector App implements a shared grid preference system that is **per-user, per-grid** and persisted in Postgres via the `user_grid_layouts` table. All AG Grid-based pages that use `DataGridPage` and `AppDataGrid` share the same backend contracts and preference model.

**Backend layers:**
- `backend/app/models_sqlalchemy/models.py`
  - `UserGridLayout` ORM model
    - Columns:
      - `id: String(36)` – primary key
      - `user_id: String(36)` – FK to `users.id`
      - `grid_key: String(100)` – logical grid identifier (e.g. `finances`, `cases`, `finances_fees`, `messages`, etc.)
      - `visible_columns: JSONB` – ordered list of visible column names
      - `column_widths: JSONB` – mapping `column_name -> width_in_pixels`
      - `sort: JSONB` – optional `{ column, direction }`
      - `theme: JSONB` – layout/theme config (density, font sizes, color scheme, etc.)
      - `created_at`, `updated_at`
    - Unique index `idx_user_grid_layouts_user_grid(user_id, grid_key)` guarantees **one layout per user+grid**.
- Alembic migrations:
  - `backend/alembic/versions/user_grid_layouts_20251115.py` – creates `user_grid_layouts` with `visible_columns`, `column_widths`, `sort`.
  - `backend/alembic/versions/user_grid_layouts_theme_20251118.py` – adds `theme` JSONB column.
- `backend/app/routers/grid_layouts.py`
  - Defines `ColumnMeta` and a series of `*_COLUMNS_META` lists for each grid (including `CASES_COLUMNS_META`, `FINANCES_COLUMNS_META`, `FINANCES_FEES_COLUMNS_META`, `MESSAGES_COLUMNS_META`).
  - `GRID_DEFAULTS` specifies default `visible_columns` and `sort` per `grid_key`.
  - `/api/grids/{grid_key}/layout` (GET/PUT) is the **legacy** per-grid layout endpoint using `visible_columns` + `column_widths` + `sort` only (no theme).
- `backend/app/routers/grid_preferences.py`
  - New unified preferences API under `/api/grid/preferences`.
  - Types:
    - `GridTheme` – density, fontSize, headerStyle, colorScheme, buttonLayout (+extra allowed).
    - `GridColumnsConfig` – `visible: string[]`, `order: string[]`, `widths: Dict[str,int>`, `sort?: GridSort`.
    - `GridPreferencesResponse` – `{ grid_key, available_columns: ColumnMeta[], columns: GridColumnsConfig, theme: GridTheme }`.
    - `GridPreferencesUpdate` – payload used by POST.
  - `GET /api/grid/preferences?grid_key=...`:
    - Looks up `UserGridLayout` for `current_user` and `grid_key`.
    - Uses `_allowed_columns_for_grid` + `GRID_DEFAULTS` to build a complete `GridColumnsConfig` via `_build_columns_from_layout`:
      - Derives `visible`/`order` from layout or defaults.
      - Cleans `widths` from `layout.column_widths` (filter to allowed cols, cast to `int`).
      - Uses `layout.sort` or default sort.
    - Builds `theme` via `_build_theme_from_layout`, merging `_DEFAULT_THEME` with any saved JSON.
  - `POST /api/grid/preferences` (`upsert_grid_preferences`):
    - Validates `payload.columns.order` against allowed columns.
    - Filters `payload.columns.widths` to allowed columns and coerces widths to `int`.
    - Validates `sort.column`.
    - Upserts `UserGridLayout` for `(user_id, grid_key)` using:
      - `visible_columns = payload.columns.order` (order is persisted as the canonical visible list).
      - `column_widths = cleaned_widths`.
      - `sort = sort_dict`.
      - `theme = payload.theme.dict()`.
    - Returns a normalized `GridPreferencesResponse` (recomputes `columns` + `theme`).
  - `DELETE /api/grid/preferences?grid_key=...`:
    - Deletes the `UserGridLayout` row so that subsequent reads fall back to `GRID_DEFAULTS`.

**Frontend layers:**
- `frontend/src/hooks/useGridPreferences.ts`
  - Defines the frontend mirror of the preference types:
    - `GridThemeConfig` – matches `GridTheme` shape plus a few extra optional fields (bodyFontSizeLevel, bodyFontWeight, etc.).
    - `GridColumnsConfig` – `{ visible: string[]; order: string[]; widths: Record<string, number>; sort: GridSortConfig | null; }`.
    - `GridPreferencesResponse` – `{ grid_key, available_columns: GridColumnMeta[], columns: GridColumnsConfig, theme: GridThemeConfig }`.
  - Hook `useGridPreferences(gridKey)`:
    - Primary fetch: `GET /api/grid/preferences?grid_key=gridKey`.
      - Populates `availableColumns`, `columns`, and `theme`.
    - Fallback 1 (legacy): `GET /api/grids/{gridKey}/layout`.
      - Constructs `columns` from `visible_columns`, `column_widths`, and `sort`.
    - Fallback 2 (data inference): `GET /api/grids/{gridKey}/data?limit=1` and infers columns from the first row.
    - State exposed to callers:
      - `availableColumns: GridColumnMeta[]` (server-provided metadata).
      - `columns: GridColumnsConfig | null`.
      - `theme: GridThemeConfig`.
      - `setColumns(partial)`, `setTheme(partial)`.
      - `save(columnsOverride?)` → `POST /api/grid/preferences` with `{ grid_key, columns, theme }`.
      - `reload()` → re-fetch preferences.
      - `clearServerPreferences()` → `DELETE /api/grid/preferences` then reload.
- `frontend/src/components/DataGridPage.tsx`
  - Shared page-level component for all AG Grid-based grids.
  - Responsibilities:
    - Calls `useGridPreferences(gridKey)` to load/save layout + theme.
    - Derives `ColumnState[]` (`name`, `label`, `width`) from `gridPrefs.columns` + `availableColumnsMap`.
    - Fetches data rows from `/api/grids/{gridKey}/data` based on visible columns, sort, pagination, search, and extra filters.
    - Renders toolbar (title, search, sort dropdown, row count, page size selector).
    - Renders `AppDataGrid` with computed columns + rows.
    - Houses the **Columns & Layout / Theme** panel, including the **Save** button.
- `frontend/src/components/datagrid/AppDataGrid.tsx`
  - Thin wrapper around `AgGridReact`.
  - Props:
    - `columns: { name; label; width }[]` – render-time column state owned by `DataGridPage`.
    - `rows: Record<string, any>[]` – row data from `/api/grids/{gridKey}/data`.
    - `columnMetaByName: Record<string, GridColumnMeta>` – metadata map.
    - `loading?: boolean`.
    - `onRowClick?(row)`.
    - `onLayoutChange?(state: { order: string[]; widths: Record<string, number> })` – layout callback.
  - For each column it builds a `ColDef` with:
    - `colId` and `field` = column `name`.
    - `headerName` from metadata label.
    - `width` from the `columns` prop.
    - `resizable: true`, `sortable: false`, no filter.
    - `valueFormatter` based on column `type`.
  - Listens to AG Grid events:
    - `onColumnResized`, `onColumnMoved`, `onColumnVisible` → `handleColumnEvent`.
    - Debounces for 500ms, then calls `event.api.getColumnState()` and passes `{ order, widths }` (extracted from `ColumnState`) to `onLayoutChange`.

**Summary:**
- Preferences are already **persisted in Postgres**, not localStorage.
- Per-user, per-grid layout includes **column visibility, order, widths, and sort**, plus theme.
- AG Grid’s column state (including widths) is observed via `getColumnState()` and written back to the same `UserGridLayout` records.

## 2. Per-Grid Summary

This section focuses on the main grids requested: finances, disputes/cases, messages.

### 2.1 Finances grids (ledger + fees)

- **Frontend components**
  - `frontend/src/pages/FinancialsPage.tsx`
    - Uses `DataGridPage` twice:
      - Ledger tab: `<DataGridPage gridKey="finances" title="Finances ledger" extraParams={financesExtraParams} />`.
      - Fees tab: `<DataGridPage gridKey="finances_fees" title="Finances fees" extraParams={financesExtraParams} />`.
  - `frontend/src/components/DataGridPage.tsx` and `frontend/src/components/datagrid/AppDataGrid.tsx` provide the shared grid behavior.

- **Grid keys / identifiers**
  - Ledger grid: `gridKey = "finances"`.
  - Fees grid: `gridKey = "finances_fees"`.

- **Backend column metadata / defaults**
  - `backend/app/routers/grid_layouts.py`:
    - `FINANCES_COLUMNS_META` and `GRID_DEFAULTS['finances']`.
    - `FINANCES_FEES_COLUMNS_META` and `GRID_DEFAULTS['finances_fees']`.
  - These define the server-side list of allowed columns, type hints, and default widths (`width_default`) and default `visible_columns` + `sort`.

- **Preferences loaded and applied**
  - `DataGridPage` calls `const gridPrefs = useGridPreferences(gridKey);`.
  - After preferences load, an effect ensures there is at least a basic `GridColumnsConfig`:
    - If `gridPrefs.columns` is `null` but `availableColumns` exist, it initializes columns with all available names in both `visible` and `order` and `widths = {}`.
  - `orderedVisibleColumns` is computed using:
    - `columns.order` (preferred) or `columns.visible` or fallback to all metadata.
    - Filtering by `columns.visible` if provided.
  - `ColumnState[]` for `AppDataGrid` is built via:
    - `width = cfg?.widths[name] || meta?.width_default || 150`.
    - This is where persisted **column widths** influence the rendered grid.
  - Data fetch (`/api/grids/{gridKey}/data`) uses:
    - `columnsToFetch` derived from `orderedVisibleColumns` or all available columns.
    - Optional `search` param from toolbar.
    - Optional `sort_by`/`sort_dir` from `gridPrefs.columns.sort`.

- **Column widths**
  - **Persisted?** Yes:
    - `GridColumnsConfig.widths` is read from `GridPreferencesResponse.columns.widths` (ultimately from `UserGridLayout.column_widths`).
    - `DataGridPage` uses `cfg?.widths[name]` to set each `ColumnState.width`.
    - `AppDataGrid` consumes that width in the ColDefs.
  - **Updated when user resizes?** Yes:
    - AG Grid emits `ColumnResizedEvent` → `AppDataGrid.handleColumnEvent`.
    - `handleColumnEvent` calls `event.api.getColumnState()` and extracts `width` per column.
    - `onLayoutChange({ order, widths })` is passed back to `DataGridPage`.
    - `DataGridPage.handleGridLayoutChange(order, widths)`:
      - Merges new `order` and `widths` into `gridPrefs.columns` via `gridPrefs.setColumns({ order: nextOrder, widths: nextWidths })`.
      - Immediately calls `gridPrefs.save({ ...cfg, order: nextOrder, widths: nextWidths })`.
    - This means column widths (and column order) are persisted **as soon as the user resizes/moves columns**, without waiting for the Columns dialog.

- **Other preference fields**
  - Sort: `gridPrefs.columns.sort` is modified via the toolbar sort dropdown and toggler; persisted via `gridPrefs.save()` when invoked.
  - Theme: `gridPrefs.theme` (density, font size, color scheme, toolbar button layout, background, header font size/weight/style, etc.) is edited in the Columns panel and persisted via `gridPrefs.save()`.

### 2.2 Disputes / Cases grid

- **Frontend components**
  - `frontend/src/pages/CasesPage.tsx`:
    - Renders a single grid:
      - `<DataGridPage gridKey="cases" title="Cases & Disputes" />`.
  - As above, `DataGridPage` + `AppDataGrid` implement the shared grid and preference logic.

- **Grid key / identifier**
  - `gridKey = "cases"`.

- **Backend column metadata / defaults**
  - `backend/app/routers/grid_layouts.py`:
    - `CASES_COLUMNS_META` enumerates columns like `open_date`, `external_id`, `kind`, `issue_type`, `status`, etc.
    - `GRID_DEFAULTS['cases']` defines default `visible_columns` and `sort` (by `open_date desc`).

- **Preferences loaded and applied**
  - Same flow as finances:
    - `useGridPreferences('cases')` to get `availableColumns`, `columns`, `theme` from `/api/grid/preferences`.
    - `orderedVisibleColumns` derived from `columns.order`/`columns.visible`/metadata.
    - Column widths computed from `columns.widths[name]` or metadata default.
    - Data loaded from `/api/grids/cases/data` using visible columns and sort state.

- **Column widths**
  - **Persisted?** Yes, identical to finances:
    - `UserGridLayout.column_widths` ↔ `GridColumnsConfig.widths` ↔ `ColumnState.width` ↔ `AppDataGrid` ColDef width.
  - **Updated on resize?** Yes:
    - Same `onColumnResized` → `AppDataGrid.handleColumnEvent` → `DataGridPage.handleGridLayoutChange` → `gridPrefs.save(...)` path.

### 2.3 Messages

There are *two* relevant pieces for messages:

1. A **backend grid definition** for `grid_key = "messages"` (used by generic grid APIs).
2. A dedicated **Messages UI page** that currently does **not** use the generic `DataGridPage` / grid preferences system.

- **Backend metadata for messages grid**
  - `backend/app/routers/grid_layouts.py`:
    - `MESSAGES_COLUMNS_META` defines a grid over the `messages` dataset with columns like `created_at`, `message_date`, `direction`, `message_type`, `sender_username`, `recipient_username`, `subject`, and Boolean flags.
    - `GRID_DEFAULTS['messages']` sets default visible columns and default sort (`message_date desc`).
  - `GET /api/grids/messages/layout` and `GET /api/grid/preferences?grid_key=messages` would both work and would produce `visible_columns`, `column_widths`, and theme for a hypothetical messages grid.

- **Frontend Messages page**
  - `frontend/src/pages/MessagesPage.tsx` implements a Gmail-like split view UI:
    - Custom sidebar with folders/buckets.
    - Top list of messages in the right pane.
    - Bottom detail + reply panel.
  - Data loading and state:
    - Uses `getMessages`, `updateMessage`, `getMessageStats` from `frontend/src/api/messages.ts`.
    - Classifies messages into buckets (`offers`, `cases`, `ebay`, `other`) using `classifyBucket()`.
    - Uses a variety of local React state for filters, view mode, drag-and-drop, etc.
    - Persists only **custom folder definitions and message-folder assignments** to `localStorage` keys (`messages.customFolders`, `messages.messageFolders`).

- **Grid preferences usage for messages**
  - The current `MessagesPage` **does not render `DataGridPage` or `AppDataGrid` at all**, and does not call `useGridPreferences`.
  - As a result, **column visibility/order/widths for messages are not managed by the shared grid preference system**.
  - The backend `messages` grid/metadata exists and could be wired up to a grid in the future, but today messages layout/widths are controlled only by the bespoke layout in `MessagesPage.tsx` and browser CSS, not by `user_grid_layouts`.

- **Column widths**
  - No AG Grid is used for messages today, so **no column width persistence** is in place for this UI.
  - The only persisted preferences for messages are the `localStorage`-backed custom folder structures.

## 3. Column Chooser & Save Button

The Column Chooser ("Columns" UI) is implemented **inline inside `DataGridPage`**, not as a separate component file.

- **Location**
  - `frontend/src/components/DataGridPage.tsx`
    - The panel is rendered conditionally when `showColumnsPanel` is `true`.
    - It is labeled in the markup with:
      - Header: `Columns & layout for {gridKey}`.
      - Sections: `Columns` and `Layout & theme`.

- **How the Columns UI works**
  1. **Opening the dialog**
     - Toolbar has a `Columns` button (either on left or right, depending on `gridPrefs.theme.buttonLayout`).
     - Clicking it sets `showColumnsPanel = true`, showing a modal overlay.
  2. **Columns section**
     - Renders one checkbox per `gridPrefs.availableColumns` entry.
     - Checkbox `checked` state is `gridPrefs.columns?.visible.includes(col.name)`.
     - Toggling a checkbox calls `toggleColumnVisibility(name)`:
       - Reads existing `gridPrefs.columns`.
       - Computes `nextVisible` by adding/removing the column.
       - Calls `gridPrefs.setColumns({ visible: nextVisible })`.
       - `setColumns` in the hook merges this partial with existing `GridColumnsConfig`, and if `visible` is updated without `order`, it filters `order` down to the new visible set.
     - There are helper buttons:
       - **Select all** – sets `visible` and `order` to all available column names.
       - **Clear all** – sets `visible` to an empty array (order is left intact, but `orderedVisibleColumns` logic later hides them).
       - **Reset** – calls `gridPrefs.clearServerPreferences()` which performs `DELETE /api/grid/preferences` and reloads preferences (back to `GRID_DEFAULTS`).
  3. **Layout & Theme section**
     - Edits properties of `gridPrefs.theme` via dropdowns, color pickers, and numeric level selectors.
     - Each control calls `gridPrefs.setTheme({ ... })`, which merges directly into the theme state.
     - Themes are not saved until the Save button is pressed.

- **Save button behavior (from click to DB)**
  - Save button:
    ```tsx
    <button
      className="px-3 py-1 border rounded bg-blue-600 text-white hover:bg-blue-700"
      onClick={handleSaveColumns}
    >
      Save
    </button>
    ```
  - `handleSaveColumns` in `DataGridPage.tsx`:
    - `await gridPrefs.save();`
    - `setShowColumnsPanel(false);` (closes the dialog).
  - `gridPrefs.save` in `useGridPreferences.ts`:
    - Accepts an optional `columnsOverride?: GridColumnsConfig`.
    - If no override is passed, it uses the current in-memory `columns` and `theme`:
      - `api.post('/api/grid/preferences', { grid_key: gridKey, columns: cols, theme })`.
  - Backend `upsert_grid_preferences` in `grid_preferences.py`:
    1. Validates that all `columns.order` entries are allowed for `grid_key`.
    2. Filters and coerces `columns.widths`.
    3. Validates `columns.sort.column` if present.
    4. Upserts `UserGridLayout` for `(user_id, grid_key)`:
       - `visible_columns = payload.columns.order` (this is the saved order/visibility list).
       - `column_widths = cleaned_widths` (persisting widths captured earlier by AG Grid events).
       - `sort = sort_dict`.
       - `theme = payload.theme.dict()`.
    5. Commits the transaction, logs a short hash for audit, and recomputes a `GridPreferencesResponse` from the updated layout.

- **Does Save itself capture column widths?**
  - **Indirectly, yes.** However, the **actual capture of widths and order is done earlier** via `AppDataGrid`’s `onLayoutChange` handler when the user resizes or reorders columns:
    - `AppDataGrid` → `handleColumnEvent` → `onLayoutChange({ order, widths })`.
    - `DataGridPage.handleGridLayoutChange` then:
      - Updates local `gridPrefs.columns` with the new `order` + `widths`.
      - Immediately calls `gridPrefs.save({...})` with those layout changes.
  - When the user later opens the Columns dialog and clicks **Save**, `gridPrefs.save()` is called **again** with the then-current `columns` and `theme`:
    - If no resizing/moving happened after the last automatic save, widths are already stored and Save is effectively a no-op for widths.
    - If the user changed visibility/order via the Columns dialog (without resizing), Save will persist those changes and reuse the last known widths.

## 4. Column Widths & AG Grid Events

This section focuses specifically on how column widths are handled today.

- **Where widths are tracked in frontend state**
  - `useGridPreferences.ts`:
    - `GridColumnsConfig.widths: Record<string, number>` holds the current known widths for each column.
    - Loaded from `GridPreferencesResponse.columns.widths` (or derived from legacy /api/grids layout).
    - Updated via `setColumns(partial)` calls, e.g. from `DataGridPage.handleGridLayoutChange`.
  - `DataGridPage.tsx`:
    - Builds `ColumnState[]` with:
      - `width = cfg?.widths[name] || meta?.width_default || 150`.
    - This state is the **single source of truth** for `AppDataGrid` column widths.
  - `AppDataGrid.tsx`:
    - Receives `columns: AppDataGridColumnState[]` where each entry includes `width: number`.
    - Binds `ColDef.width = col.width` so AG Grid starts from the persisted width on each render.

- **AG Grid events that capture widths**
  - `AppDataGrid.tsx` hooks these events on `<AgGridReact>`:
    - `onColumnResized={handleColumnEvent}`.
    - `onColumnMoved={handleColumnEvent}`.
    - `onColumnVisible={handleColumnEvent}`.
  - `handleColumnEvent(event)`:
    - Debounces with a 500ms timeout using `layoutDebounceRef`.
    - On timeout, calls `event.api.getColumnState()`.
    - `extractLayout(columnStates)` then:
      - Builds `order: string[]` from `col.colId`.
      - Builds `widths: Record<string, number>` from `col.width` when numeric.
    - Calls `onLayoutChange({ order, widths })`.
  - `DataGridPage.tsx` passes:
    - `onLayoutChange={({ order, widths }) => handleGridLayoutChange(order, widths)}`.
  - `handleGridLayoutChange(order, widths)`:
    - Reads the existing `cfg = gridPrefs.columns`.
    - Filters `order` down to names already known in `cfg.order`.
    - Merges new widths into `cfg.widths`:
      - `const nextWidths = { ...cfg.widths, ...widths }`.
    - Calls:
      - `gridPrefs.setColumns({ order: nextOrder, widths: nextWidths })` to update local state.
      - `gridPrefs.save({ ...cfg, order: nextOrder, widths: nextWidths })` to persist immediately.

- **Where widths are stored in the database**
  - `UserGridLayout.column_widths` (JSONB) in `models_sqlalchemy.models`.
  - `grid_preferences.py`:
    - `_build_columns_from_layout` reads `layout.column_widths` as `widths_raw` and cleans it to `widths_clean: Dict[str, int]`.
    - This becomes `GridColumnsConfig.widths` in the response.
    - `upsert_grid_preferences` cleans `payload.columns.widths` and writes them back to `layout.column_widths`.
  - `grid_layouts.py` (legacy layout endpoint) also reads/writes `column_widths` for older clients/grids.

- **Current behavior summary for widths**
  - AG Grid column widths are **fully integrated into the preference system today** for all grids that use `DataGridPage` + `AppDataGrid` (including `finances`, `finances_fees`, `cases`, and many others like `orders`, `transactions`, etc.).
  - Width changes are persisted **immediately on resize or on column move/visibility change**, not only when the user clicks the Columns dialog Save button.
  - On next page load, widths from the DB flow back through `/api/grid/preferences` → `useGridPreferences` → `DataGridPage` → `AppDataGrid` and restore the previous layout.
  - The **messages UI** is an exception: it does not use this system at all, so messages have no persisted column widths.

## 5. Extension Points for Future Work (Column Widths)

Although widths are already persisted to the database for DataGridPage-based grids, we may want to:
- Adjust **when** persistence happens (e.g., only on explicit Save instead of on every resize), or
- Add width persistence to new or non-DataGridPage grids (e.g., if we introduce a `messages` grid view using AG Grid).

Key extension points:

1. **Frontend: capture current column widths from AG Grid**
   - `frontend/src/components/datagrid/AppDataGrid.tsx`
     - `handleColumnEvent` and `extractLayout` already compute `order` and `widths` from `getColumnState()`.
     - To change behavior, we could:
       - Wrap `onLayoutChange` calls behind a feature flag (e.g. only call when a `persistOnResize` prop is true).
       - Emit more detail (e.g. pinned state) by extending `extractLayout` to inspect additional `ColumnState` fields.

2. **Frontend: integrate widths into the preference object**
   - `frontend/src/components/DataGridPage.tsx`
     - `handleGridLayoutChange(order, widths)` is the central bridge between AG Grid events and `useGridPreferences`.
     - Options for future adjustments:
       - If we want widths only persisted on explicit Save:
         - Change `handleGridLayoutChange` to **only** call `gridPrefs.setColumns({ order, widths })` (local state) and **not** call `gridPrefs.save()`.
         - Leave `columns.widths` as in-memory state until the user presses Save; then `handleSaveColumns` would automatically send the latest `columns.widths` when calling `gridPrefs.save()`.
       - If we add new layout aspects (pinned columns, group state, etc.), we could extend the shape passed via `onLayoutChange` and merge it into `GridColumnsConfig` here.

3. **Frontend: Save button behavior**
   - `DataGridPage.handleSaveColumns` + `useGridPreferences.save`:
     - `save(columnsOverride?: GridColumnsConfig)` already supports overriding the exact columns payload used for persistence.
     - Future options:
       - Compute a `finalColumns` object at Save time, possibly merging:
         - Latest `columns` state.
         - Any transient state captured by AG Grid but not yet stored in `columns.widths`.
       - Attach additional layout metadata (e.g. pinned state) before sending to `/api/grid/preferences`.

4. **Backend: preference schema / DB storage**
   - `backend/app/routers/grid_preferences.py` and `UserGridLayout` already support arbitrary `widths` via `column_widths` JSONB.
   - Extension options:
     - Add new JSON keys inside `column_widths` or new JSONB columns (e.g. `column_state`) if we decide to store full AG Grid column state server-side.
     - Extend `GridColumnsConfig` and `_build_columns_from_layout` to preserve additional layout elements (e.g. pinned columns, column groups) if needed.

5. **Adding grid preferences to new grids (e.g. messages)**
   - To bring messages into the same system in the future:
     - Create a messages-specific page or refactor `MessagesPage` to include a `DataGridPage` for certain views (e.g. a compact list grid of messages).
     - Use `gridKey="messages"`, which already has `MESSAGES_COLUMNS_META` and `GRID_DEFAULTS['messages']` defined.
     - Wire that view through `useGridPreferences` and `AppDataGrid`, after which column widths will be persisted automatically via the existing plumbing.

---

**Summary (short):**
- Grid preferences are centralized around `/api/grid/preferences` and `UserGridLayout`, with `GridColumnsConfig.widths` and `UserGridLayout.column_widths` already storing **per-user, per-grid column widths**.
- `DataGridPage` + `AppDataGrid` use AG Grid events and `getColumnState()` to capture widths and order on resize/move and persist them via `useGridPreferences.save()`.
- The Columns dialog Save button re-saves the current layout and theme but does not itself compute widths; widths are already part of the columns config by the time Save is clicked.
- The main AG Grid-based pages for this audit (`finances`, `finances_fees`, `cases`) all use this system; the dedicated `MessagesPage` currently does **not**.
