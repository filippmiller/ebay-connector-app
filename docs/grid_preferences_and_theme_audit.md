# Grid Preferences, Theme, and UI Tweak Audit (Production Behaviour)

## 1. Introduction & Scope

This report audits the current implementation of:

- Per-user grid preferences (columns, widths, theme) for AG Grid-based pages such as **Finances → Fees**.
- The new compact **legacy-style AG Grid theme** and how it is (or is not) wired to per-user theme preferences.
- The **`/api/ui-tweak`** endpoint and its backing `ui_tweak_settings` table.

This run is **audit-only**:

- No Alembic migrations were created or modified.
- No schema changes or data writes were performed beyond existing application behaviour.
- Observable grid behaviour was not intentionally changed.

## 2. Session Checklist (Environment & Connectivity)

### 2.1 Critical environment variables

Checked presence of required variables via PowerShell environment:

- Present: `DATABASE_URL`, `VITE_SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `RAILWAY_TOKEN`.
- **Missing:** `RAILWAY_PUBLIC_DOMAIN` is not set in the current shell (PowerShell reports `Env:\RAILWAY_PUBLIC_DOMAIN` not found).

Impact: API health checks against `https://$Env:RAILWAY_PUBLIC_DOMAIN` cannot be executed from this session. This does **not** affect code-level audit but should be corrected for full production verification.

### 2.2 Alembic connectivity to production database

Commands executed from `backend/` using the configured `DATABASE_URL`:

- `poetry -C backend run alembic heads -v`
  - Succeeds; shows multiple heads, including `ui_tweak_settings_20251121.py`, `user_grid_layouts_20251115.py`, and `user_grid_layouts_theme_20251118.py`.
- `poetry -C backend run alembic current -v`
  - **Fails** with `psycopg2.OperationalError: FATAL:  Tenant or user not found` when attempting to connect to `aws-1-us-east-1.pooler.supabase.com`.

Implications:

- Alembic cannot currently inspect the live production database revision from this environment.
- We therefore infer the state of `ui_tweak_settings` from application errors and the presence of migrations in the repo, not from `alembic current`.

### 2.3 Railway / API health

- HTTP health check against `https://$Env:RAILWAY_PUBLIC_DOMAIN` **not run** because `RAILWAY_PUBLIC_DOMAIN` is missing.
- This does not block the code audit, but it means we have no fresh confirmation of the production API root behaviour from this session.


## 3. Repo Orientation & Key Entry Points

Current repo root: `backend/` and `frontend/` folders present alongside `docs/`.

### 3.1 Backend: grid preferences and UI tweak

- Grid preferences router:
  - `backend/app/routers/grid_preferences.py`
  - Uses `UserGridLayout` model from `backend/app/models_sqlalchemy/models.py`.
- UI tweak router:
  - `backend/app/routers/ui_tweak.py`
  - Uses `UiTweakSettings` model from `backend/app/models_sqlalchemy/models.py`.
- SQLAlchemy models:
  - `backend/app/models_sqlalchemy/models.py`:
    - `UserGridLayout` (per-user grid layout + theme).
    - `UiTweakSettings` (global UI tweak singleton table).
- Alembic migrations of interest:
  - `backend/alembic/versions/user_grid_layouts_20251115.py` – creates `user_grid_layouts` table.
  - `backend/alembic/versions/user_grid_layouts_theme_20251118.py` – adds `theme` JSONB column to `user_grid_layouts`.
  - `backend/alembic/versions/ui_tweak_settings_20251121.py` – creates `ui_tweak_settings` table and seeds defaults.

### 3.2 Frontend: grid components, hooks, and UI tweak

- Shared grid page:
  - `frontend/src/components/DataGridPage.tsx` – generic wrapper for backend-driven data grids, now rendering **AG Grid via `AppDataGrid`**.
- AG Grid wrapper:
  - `frontend/src/components/datagrid/AppDataGrid.tsx` – single instantiation point of `AgGridReact`.
  - `frontend/src/components/datagrid/legacyGridTheme.ts` – defines AG Grid Theming API theme `legacyGridTheme`.
- Grid preferences hook:
  - `frontend/src/hooks/useGridPreferences.ts` – talks to `/api/grid/preferences` and fallbacks.
- UI tweak client context and admin page:
  - `frontend/src/contexts/UITweakContext.tsx` – global UI tweak provider; applies CSS custom properties.
  - `frontend/src/pages/AdminUITweakPage.tsx` – admin UI for editing UI tweak settings.
- Global styles & grid theme helpers:
  - `frontend/src/index.css` – CSS vars for UI tweak + `.app-grid` and `.app-grid__ag-root` styles + AG-legacy utility classes.
- Frontend entrypoint:
  - `frontend/src/main.tsx` – imports `./index.css` and **AG Grid base CSS only** (`ag-grid.css`), then wraps `<App />` in `UITweakProvider`.


## 4. Grid Preferences & Column Widths

### 4.1 Backend implementation

**Router:** `backend/app/routers/grid_preferences.py`

Key Pydantic models:

- `GridTheme` – density, fontSize, headerStyle, colorScheme, buttonLayout; `extra = "allow"` for forward compatibility.
- `GridColumnsConfig`:
  - `visible: List[str]`
  - `order: List[str]`
  - `widths: Dict[str, int] = {}` (mutable default, but functionally a map of `columnName -> widthPx`).
  - `sort: Optional[GridSort]`.
- `GridPreferencesResponse` – `grid_key`, `available_columns`, `columns`, `theme`.
- `GridPreferencesUpdate` – payload for `POST /api/grid/preferences`.

**Storage model:** `UserGridLayout` in `backend/app/models_sqlalchemy/models.py`:

- `__tablename__ = "user_grid_layouts"`.
- Fields relevant to grid layout:
  - `visible_columns` – JSONB list of column names.
  - `column_widths` – JSONB mapping of `columnName -> width`.
  - `sort` – JSONB sort config.
  - `theme` – JSONB theme object (density, font sizes, colors, etc.).

**Migrations:**

- `user_grid_layouts_20251115`:
  - Creates `user_grid_layouts` with `visible_columns`, `column_widths`, `sort` JSONB, timestamps, and `idx_user_grid_layouts_user_grid` unique index.
- `user_grid_layouts_theme_20251118`:
  - Adds `theme` JSONB column to `user_grid_layouts`.

**Read path (`GET /api/grid/preferences`)**:

- Loads the current user's `UserGridLayout` row (if any) for a given `grid_key`.
- Calls `_build_columns_from_layout(grid_key, layout)`:
  - When `layout is None`:
    - Returns `GridColumnsConfig` with defaults: `visible`, `order`, `widths={}`, `sort=GRID_DEFAULTS[grid_key].sort`.
  - When `layout` exists:
    - `visible_clean` derived from `layout.visible_columns` intersected with allowed columns, falling back to defaults.
    - `widths_raw = layout.column_widths or {}`.
    - `widths_clean` is constructed by iterating `widths_raw`, keeping only allowed columns and coercing values to `int`.
    - Returns `GridColumnsConfig(visible=visible_clean, order=visible_clean, widths=widths_clean, sort=layout.sort or default_sort)`.
- Calls `_build_theme_from_layout(layout)`:
  - Starts from `_DEFAULT_THEME` (density, fontSize, headerStyle, colorScheme, buttonLayout).
  - Merges `layout.theme` into it.

**Write path (`POST /api/grid/preferences`)**:

- `upsert_grid_preferences` receives `GridPreferencesUpdate`:
  - Validates `grid_key` and that all `payload.columns.order` values are allowed.
  - Builds `cleaned_widths` from `payload.columns.widths`:
    - Ignores keys not in allowed columns.
    - Coerces values to `int`, skipping invalid entries.
  - Validates `payload.columns.sort`.
  - Constructs `theme_payload = payload.theme.dict()`.
  - Computes `final_visible` (ordered visible columns) from `payload.columns.visible` and `payload.columns.order`.
  - Upserts `UserGridLayout`:
    - On update: sets `visible_columns = final_visible`, `column_widths = cleaned_widths`, `sort = sort_dict`, `theme = theme_payload`.
    - On insert: populates the same fields.
  - Commits and refreshes, then **rebuilds the response** using `_build_columns_from_layout` and `_build_theme_from_layout`.

**Conclusion (backend widths):**

- The backend **does support** persistence of column widths in `UserGridLayout.column_widths`.
- `columns.widths` in the response is directly derived from `UserGridLayout.column_widths`.
- If `columns.widths` is `{}` in responses, it means either:
  - No widths were ever stored (user has never saved widths), or
  - The incoming `payload.columns.widths` was empty or filtered to empty, or
  - The user layout row does not exist and we are still in the default path.

### 4.2 Frontend: useGridPreferences and DataGridPage

**Hook:** `frontend/src/hooks/useGridPreferences.ts`

- Fetch logic:
  - Primary call: `GET /api/grid/preferences?grid_key={gridKey}`.
  - On success:
    - Sets `availableColumns = resp.data.available_columns`.
    - Sets `columns = resp.data.columns` (including `widths` as provided).
    - Sets `theme = { ...DEFAULT_THEME, ...(resp.data.theme || {}) }`.
  - Fallbacks to legacy layout and even to inferring from data if the new endpoint fails.

- Local state:
  - `columns: GridColumnsConfig | null`.
  - `theme: GridThemeConfig`.

- `setColumns(partial)`:
  - Merges partial updates into the existing `columns` while maintaining a consistent `visible`/`order` relationship.

- `save(columnsOverride?)`:
  - Builds payload:
    - `grid_key: gridKey`.
    - `columns: cols` – whichever `GridColumnsConfig` is in state or override.
    - `theme: theme` – current theme config.
  - `POST /api/grid/preferences` with this payload.
  - Logs the payload and response to the console.

**Grid page:** `frontend/src/components/DataGridPage.tsx`

- Uses `const gridPrefs = useGridPreferences(gridKey);`.
- Computes `availableColumnsMap` by name for quick lookups.
- If `gridPrefs.columns` is null after load, initialises it to:
  - `visible: allNames`, `order: allNames`, `widths: {}`, `sort: null`.
- Builds **local column state** used by `AppDataGrid`:
  - `orderedVisibleColumns` from preferences.
  - For each visible column name:
    - Width is chosen as `cfg?.widths?.[name] || meta?.width_default || 150`.
  - Sets local `columns: { name, label, width }[]`.

- Handles runtime layout changes coming from AG Grid via `AppDataGrid`:

  ```ts
  const handleGridLayoutChange = (order: string[], widths: Record<string, number>) => {
    const cfg = gridPrefs.columns;
    if (!cfg) return;

    const visibleSet = new Set(cfg.visible);
    const hiddenColumns = cfg.order.filter(c => !visibleSet.has(c));

    const nextOrder = [...order, ...hiddenColumns];
    const nextWidths = { ...cfg.widths, ...widths };

    gridPrefs.setColumns({
      visible: cfg.visible,
      order: nextOrder,
      widths: nextWidths,
      sort: cfg.sort,
    });
  };
  ```

- Columns panel and "Save" button:
  - Columns visibility toggling updates `gridPrefs.columns` **in memory only** via `setColumns`.
  - `handleSaveColumns` calls `await gridPrefs.save();` then closes the panel.

**AG Grid wrapper:** `frontend/src/components/datagrid/AppDataGrid.tsx`

- Builds `columnDefs` (one per `columns` entry) with:
  - `colId` and `field` = column name.
  - `headerName` from metadata.
  - `width` from the passed `columns` list.
  - `resizable: true`.
  - `cellClass` / `cellClassRules` for numeric, money, ID, and status columns.
- Extracts layout from AG Grid column state:

  ```ts
  function extractLayout(columnStates: ColumnState[]): { order: string[]; widths: Record<string, number> } {
    const order: string[] = [];
    const widths: Record<string, number> = {};

    columnStates.forEach((col: ColumnState) => {
      const id = (col.colId as string) || '';
      if (!id) return;

      if (id.startsWith('ag-Grid-')) {
        return;
      }

      order.push(id);
      if (typeof col.width === 'number') {
        widths[id] = col.width;
      }
    });

    return { order, widths };
  }
  ```

- Debounced event handler:

  ```ts
  const handleColumnEvent = (event: any) => {
    if (!onLayoutChange || !event.api) return;

    if (layoutDebounceRef.current !== null) {
      window.clearTimeout(layoutDebounceRef.current);
    }

    layoutDebounceRef.current = window.setTimeout(() => {
      const model = (event.api as any).getColumnState?.() as ColumnState[] | undefined;
      if (!model) return;
      const { order, widths } = extractLayout(model);
      onLayoutChange({ order, widths });
    }, 500);
  };
  ```

- Wires layout events:
  - `onColumnResized={handleColumnEvent}`
  - `onColumnMoved={handleColumnEvent}`
  - `onColumnVisible={handleColumnEvent}`

- Passes layout changes to `DataGridPage` via `onLayoutChange` prop.

**End-to-end expectation:**

1. User resizes columns → AG Grid fires `onColumnResized` → `AppDataGrid` extracts `order` and `widths` → `DataGridPage.handleGridLayoutChange` merges `widths` into `gridPrefs.columns.widths`.
2. User clicks **Save** in Columns panel → `useGridPreferences.save()` sends the updated `columns` (including `widths`) to the backend.
3. Backend writes `column_widths` into `user_grid_layouts`.
4. On reload, `GET /api/grid/preferences` returns `columns.widths` filled, and `DataGridPage` applies those widths.

### 4.3 Why widths are not persisted in production

Given the code above and the production observation:

- `columns.widths` is always `{}` in responses for `grid_key=finances_fees`, even after resize + Save.

The most plausible root causes are:

1. **Frontend widths never make it into the request payload in production.**
   - Potential reasons:
     - `AppDataGrid` may not be emitting layout events for the Finances grid in the production build (e.g. due to AG Grid version mismatch, column IDs not matching, or event suppression).
     - The debounced `handleColumnEvent` could be prevented from running in some cases (e.g. errors in `window.setTimeout` context or TypeScript-only features not correctly transpiled).
     - The Finances grid might not actually be using `DataGridPage` + `AppDataGrid` in production (but given the shared implementation, this is less likely unless Finances still uses an older code path).

2. **Back-end receives widths but filters them out.**
   - If `payload.columns.widths` contains keys not present in `_allowed_columns_for_grid('finances_fees')`, `cleaned_widths` will end up empty.
   - This would happen if **column field names used by AG Grid differ from the `available_columns[].name`** defined in backend `grid_layouts` for `finances_fees` (e.g. using `amount_value` vs `amount`, or a mismatch in naming).
   - In that case, widths extracted by `AppDataGrid` would use `colId` values that do not exactly match the allowed backend column names, and the backend would silently drop them.

3. **Existing layouts stuck in default-state with no widths.**
   - If `UserGridLayout` rows exist for the user but `column_widths` remain null/empty, then `columns.widths` will stay `{}`.
   - However, the current code path clearly sets `layout.column_widths = cleaned_widths` on every save. This makes "never persisted" more likely than "persisted but not re-applied".

Given that:

- The backend clearly supports widths and would re-emit them.
- The user sees `columns.widths = {}` even after manual saves.

**Primary suspected root cause:**

> For `grid_key=finances_fees`, the **column identifiers used by AG Grid (`colId`/`field`) do not match the `allowed_cols`/`available_columns[].name` on the backend**, so when widths arrive at the server they are **filtered out**, resulting in `column_widths = {}` and therefore `columns.widths = {}` in the response.

A secondary contributing factor could be a missing or broken layout event path in production (i.e. widths never reach `useGridPreferences.save()`), but the backend filtering logic is the clearest potential explanation that fits _"widths always `{}`"_ while other column settings persist.


## 5. Grid Theme & AG Grid Error #239

### 5.1 Theme plumbing in code

**Backend theme storage:**

- `UserGridLayout.theme` (JSONB) stores per-grid theme settings.
- `GridTheme` Pydantic model exposes:
  - `density`, `fontSize`, `headerStyle`, `colorScheme`, `buttonLayout` with defaults.
- `GET /api/grid/preferences` merges stored theme over `_DEFAULT_THEME`.

**Frontend theme consumption:**

- `useGridPreferences`:
  - On successful response from `/api/grid/preferences`, sets `theme = { ...DEFAULT_THEME, ...(resp.data.theme || {}) }`.

- `DataGridPage`:
  - Computes:
    - `density = gridPrefs.theme?.density || 'normal'`.
    - `colorScheme = gridPrefs.theme?.colorScheme || 'default'`.
    - `buttonLayout = gridPrefs.theme?.buttonLayout || 'right'`.
    - `legacyBodyPreset = gridPrefs.theme?.fontSize || 'medium'`.
    - `bodyFontSizeLevel` from either `theme.bodyFontSizeLevel` or a heuristic based on `fontSize`.
    - `bodyFontSizePx = 10 + clampedBodyLevel`.
    - `gridBackgroundColor = theme.backgroundColor`.
  - Applies them to the outer grid wrapper:

    ```tsx
    <div
      className={`flex flex-col h-full app-grid grid-density-${density} grid-theme-${colorScheme}`}
      style={{ fontSize: bodyFontSizePx, backgroundColor: gridBackgroundColor || undefined }}
    >
      ...
      <div className="flex-1 min-h-0 border rounded-lg bg-white" style={gridBackgroundColor ? { backgroundColor: gridBackgroundColor } : undefined}>
        { ... <AppDataGrid ... /> }
      </div>
    </div>
    ```

- `index.css` defines how these classes and CSS variables affect grid appearance:
  - `.app-grid.grid-density-*` adjust `--grid-row-height`, `--grid-header-height`, `--grid-font-size`.
  - `.app-grid.grid-theme-*` adjust header background and text colors (and in the dark theme case, overall background and text for the grid area).
  - `.app-grid__ag-root` sets `font-size: var(--grid-font-size);` for the AG Grid container.

**AG Grid theme:**

- `legacyGridTheme` in `legacyGridTheme.ts` is created via **AG Grid Theming API** (`themeQuartz.withParams`):
  - Hardcodes compact row height, header height, font family, font size, and colors.
- `AppDataGrid` passes this theme into `AgGridReact`:

  ```tsx
  <AgGridReact
    theme={legacyGridTheme}
    columnDefs={columnDefs}
    defaultColDef={defaultColDef}
    rowData={rows}
    ...
  />
  ```

- Global CSS imports in `main.tsx`:

  ```ts
  import './index.css';
  import 'ag-grid-community/styles/ag-grid.css';
  ```

  Note: only the **base** AG Grid CSS is imported; no `ag-theme-*` CSS theme is imported here.

### 5.2 Where both Theming API and legacy CSS themes collide

The console error observed in the browser:

> `AG Grid: error #239 Theming API and Legacy Themes are both used in the same page. A Theming API theme definitions exist but the CSS file theme (ag-theme-*) is also included and will cause styling issues.`

Given the codebase:

- We **do** use the Theming API (`legacyGridTheme`).
- `index.css` does **not** define any `.ag-theme-*` classes; it only has `.app-grid` and `.app-grid__ag-root`.
- `main.tsx` only imports `ag-grid.css` base styles, not `ag-theme-quartz.css`.

Therefore, the #239 error must be triggered by **some legacy CSS theme still being loaded elsewhere in the production build**. Likely candidates (not visible in this truncated audit but consistent with the error):

- An `ag-theme-...` CSS file still imported in another entrypoint or older bundle.
- A static `ag-theme-...` class present in HTML or in an older wrapper component that was not fully removed.

### 5.3 Why the new “nice” theme isn’t clearly applied

Even ignoring error #239, users report that the Finances grid still looks like the older "dull" theme. Reasons:

1. **Per-user theme prefs are only partially wired to AG Grid.**
   - `GridTheme` (density, colorScheme, fontSize) is used to:
     - Toggle Tailwind utility classes: `grid-density-${density}`, `grid-theme-${colorScheme}` **on the `.app-grid` wrapper**.
     - Adjust a computed `fontSize` on the wrapper and grid container.
   - However, `legacyGridTheme` (AG Grid theme) is **static**:
     - It does not read per-user theme preferences or global UI tweak settings.
     - Row height, header height, background colors, etc. are fixed in `legacyGridTheme` parameters.

2. **Visual disconnect between wrapper and AG Grid internals.**
   - The `.app-grid` wrapper adjusts CSS variables and background colours, but AG Grid's internal styling is largely controlled by `legacyGridTheme`.
   - Without dynamic wiring from `GridTheme`/`UITweakSettings` into the Theming API params, changes in user theme prefs mostly affect the **outer container** (padding, background) rather than the grid's internal rows/headers.

3. **Possible interference from a legacy CSS theme (per #239).**
   - If a CSS theme like `ag-theme-quartz` is still included on the page, it can override borders, row backgrounds, and header styles defined by `legacyGridTheme`, leading to a "hybrid" look that still resembles the older AG Grid default themes.

**Net effect:**

> The backend correctly exposes `theme` in `/api/grid/preferences`, and the frontend reads it to decorate the wrapper, but the **core AG Grid styling is governed by a static `legacyGridTheme`** plus a likely conflicting legacy CSS theme. As a result, changes in per-user theme prefs do not visibly translate into the AG Grid internals, and the grid continues to look like the old, dull table.


## 6. `/api/ui-tweak` and `ui_tweak_settings`

### 6.1 Backend model and router

**Model:** `UiTweakSettings` in `backend/app/models_sqlalchemy/models.py`:

- `__tablename__ = "ui_tweak_settings"`.
- Columns:
  - `id` – `Integer`, primary key, autoincrement.
  - `settings` – `JSONB`, non-null, default `dict` (holds the full UITweak payload).
  - `created_at`, `updated_at` – `DateTime(timezone=True)` with `server_default=func.now()` and `onupdate=func.now()`.

**Migration:** `backend/alembic/versions/ui_tweak_settings_20251121.py`:

- `revision = "ui_tweak_settings_20251121"`.
- `down_revision = "shipping_tables_20251121"`.
- `upgrade()`:
  - Uses SQLAlchemy inspector to check for existence of `ui_tweak_settings`.
  - If missing, creates the table with `id`, `settings` (JSONB with `{}` default), `created_at`, `updated_at`.
  - Seeds a single row into the table if it is empty using `DEFAULT_SETTINGS` (fontScale, navScale, gridDensity, nav colors).
- `downgrade()` drops the table if it exists.

**Router:** `backend/app/routers/ui_tweak.py`:

- Defines `UiTweakSettingsPayload` Pydantic model mirroring frontend settings, with some extra dictionaries (`typography`, `colors`, `controls`) and `extra = "allow"`.
- `_DEFAULT_SETTINGS = UiTweakSettingsPayload().dict()` as backend default.
- `_get_or_create_settings_row(db)`:
  - Queries `UiTweakSettings` ordered by `id ASC`, gets first row.
  - If none exists, creates one with `settings=_DEFAULT_SETTINGS`, commits, refreshes, and returns it.
- Routes:
  - `GET /api/ui-tweak` (any authenticated user):
    - Calls `_get_or_create_settings_row(db)`.
    - Merges stored settings over `_DEFAULT_SETTINGS` and returns `UiTweakSettingsPayload`.
  - `GET /api/admin/ui-tweak` (admin only):
    - Same as above but requires `admin_required`.
  - `PUT /api/admin/ui-tweak` (admin only):
    - Calls `_get_or_create_settings_row(db)`.
    - Replaces `row.settings` with `payload.dict()`.
    - Commits and returns the payload.

### 6.2 Frontend UITweak context

**File:** `frontend/src/contexts/UITweakContext.tsx`

- Defines `UITweakSettings` interface with fontScale, navScale, gridDensity, nav colors, typography, colors, controls, and `gridTheme`.
- `DEFAULT_UI_TWEAK` matches the backend's conceptual shape.
- `applySettingsToDocument(settings)` writes many CSS custom properties:
  - `--ui-font-scale`, `--ui-nav-scale`, nav colours.
  - Typography scales and weights for titles, table header/cell, button text.
  - Text and button colours.
  - Grid density CSS vars: `--grid-row-height`, `--grid-header-height`, `--grid-font-size`.
  - Grid theme colours: `--grid-header-bg`, `--grid-header-text-color`, `--grid-row-hover-bg`, `--grid-row-selected-bg`, `--grid-row-bg`, `--grid-row-alt-bg`.
- Context state:
  - Reads from `localStorage['ui_tweak_v1']`.
  - On mount / changes, calls `applySettingsToDocument` and persists back to localStorage.
- **Important:** There is also integration with `/api/ui-tweak`:
  - (From lines beyond the truncated snippet, the provider fetches `/api/ui-tweak` on mount, merges with local storage/defaults, and calls `update` that also best-effort PUTs `/api/admin/ui-tweak` when admins change values.)

### 6.3 Why `/api/ui-tweak` returns 500 (UndefinedTable)

Production error payload from the user:

```json
{
  "error": "internal_error",
  "rid": "05982ec7",
  "message": "(psycopg2.errors.UndefinedTable) relation \"ui_tweak_settings\" does not exist\nLINE 2: FROM ui_tweak_settings ORDER BY ui_tweak_settings.id ASC \n             ^\n\n[SQL: SELECT ui_tweak_settings.id AS ui_tweak_settings_id, ui_tweak_settings.settings AS ui_tweak_settings_settings, ui_tweak_settings.created_at AS ui_tweak_settings_created_at, ui_tweak_settings.updated_at AS ui_tweak_settings_updated_at \nFROM ui_tweak_settings ORDER BY ui_tweak_settings.id ASC \n LIMIT %(param_1)s]\n[parameters: {'param_1': 1}]\n(Background on this error at: https://sqlalche.me/e/20/f405)",
  "type": "ProgrammingError"
}
```

This corresponds exactly to `_get_or_create_settings_row(db)` attempting:

```py
row = db.query(UiTweakSettings).order_by(UiTweakSettings.id.asc()).first()
```

Postgres reports that `ui_tweak_settings` does **not** exist in the current database.

Given that:

- The `UiTweakSettings` SQLAlchemy model exists and is imported at app startup.
- The `ui_tweak_settings_20251121` Alembic migration exists in the repo and is part of the current heads.
- `alembic current` cannot connect to the DB from this environment (tenant/user error), so we cannot definitively confirm the DB revision.

The most likely explanation is:

> The `ui_tweak_settings_20251121` migration **has not been applied** to the production Supabase Postgres that backs the running backend. The code assumes the table exists, but the database is behind at least that migration.

No evidence suggests that the table exists under a different name or schema – the error is a straightforward `UndefinedTable` on `ui_tweak_settings`.


## 7. Observed vs Expected Behaviour

### 7.1 Column width persistence

- **Expected:**
  - After resizing columns in the Finances Fees grid and clicking **Save** in the Columns panel:
    - `POST /api/grid/preferences` payload includes `columns.widths` with non-empty mappings.
    - Backend stores these widths in `user_grid_layouts.column_widths` and returns them in subsequent `GET /api/grid/preferences` calls.
    - On reload, columns render with the persisted widths.

- **Observed:**
  - For `grid_key=finances_fees`, `GET /api/grid/preferences` returns `columns.widths: {}` even after resize + Save.

- **Root cause (code-level reasoning):**
  - Backend path is implemented correctly and would round-trip widths if given valid names.
  - Frontend extracts widths from AG Grid and sends them in the payload.
  - The most plausible mismatch is **column naming** between AG Grid (`colId`/`field`) and backend `allowed_cols` / `available_columns[].name` for this specific grid, causing the backend to drop widths as invalid.

### 7.2 Theme application and AG Grid error #239

- **Expected:**
  - The new legacy-style AG Grid theme (`legacyGridTheme`) should make grids visually dense, crisp, and clearly themed.
  - Per-user theme prefs (`theme` in `/api/grid/preferences`) and global UITweak settings should influence row/header heights, font sizes, and colours.

- **Observed:**
  - Finances grid still looks like an older, dull table.
  - Browser logs `AG Grid: error #239 Theming API and Legacy Themes are both used in the same page.`

- **Root causes:**
  1. `legacyGridTheme` is static and **does not incorporate per-user or global theme settings**, so theme changes mainly affect the outer `.app-grid` wrapper, not AG Grid internals.
  2. A **legacy CSS theme (`ag-theme-*`) is still being loaded somewhere in the production bundle**, causing error #239 and likely overriding parts of the Theming API output.
  3. Together, these yield a hybrid appearance where the new theme is not clearly visible and user theme prefs appear to have little effect.

### 7.3 `/api/ui-tweak` 500 (UndefinedTable)

- **Expected:**
  - `GET /api/ui-tweak` should:
    - Create `ui_tweak_settings` row with defaults if missing.
    - Return merged global UITweak settings.

- **Observed:**
  - `GET /api/ui-tweak` returns 500 with `psycopg2.errors.UndefinedTable: relation "ui_tweak_settings" does not exist`.

- **Root cause:**
  - The `UiTweakSettings` model and router expect the `ui_tweak_settings` table to exist, but the production database does not have this table.
  - The corresponding Alembic migration `ui_tweak_settings_20251121` exists in the repo but evidently was **not applied** to the production database.


## 8. Summary, Fixes Applied & Proposed Follow-ups

### 8.1 Column width persistence

**Issues identified:**

- Backend persists widths in `user_grid_layouts.column_widths` and re-emits them, but responses for `finances_fees` show `columns.widths = {}`.
- Frontend logically collects widths from AG Grid and sends them in `columns.widths` when saving, but production behaviour suggests they are not stored.
- Backend filters width entries whose keys are not in `_allowed_columns_for_grid(grid_key)`, so any **name mismatch** between frontend and backend will result in widths being silently ignored.

**Proposed high-level steps to fix:**

1. **Instrument logging (temporarily) around width persistence path:**
   - In `upsert_grid_preferences`, log the keys of `payload.columns.widths` and `cleaned_widths` for `grid_key=finances_fees`.
   - Confirm whether widths arrive and which keys survive the filtering.
2. **Confirm column name alignment for `finances_fees`:**
   - Inspect `backend/app/routers/grid_layouts.py` for the `finances_fees` entry.
   - Verify that `available_columns[].name` matches exactly the field names used by AG Grid/rows.
3. **If mismatches exist:**
   - Align backend and frontend naming so that:
     - Backend `available_columns` names.
     - Grid row keys from `/api/grids/finances_fees/data`.
     - AG Grid `colId`/`field`.
     all use the same identifiers.
4. **After alignment:**
   - Re-test: resize columns, Save, reload, confirm `columns.widths` is populated and applied by `DataGridPage`.

### 8.2 Theme / layout (AG Grid and per-user theme prefs)

**Issues identified:**

- `legacyGridTheme` is static and not influenced by per-user `GridTheme` or global UITweak settings.
- `DataGridPage` applies theme classes only to the outer `.app-grid` wrapper, so most AG Grid internals (rows, headers, borders) are unaffected by user theme settings.
- AG Grid error #239 indicates that a legacy CSS theme (`ag-theme-*`) is still present alongside the Theming API theme, leading to conflicting styles.

**Proposed high-level steps to fix:**

1. **Eliminate legacy CSS theme usage:**
   - Search the codebase and build artefacts for any `ag-theme-` classes or theme CSS imports beyond `ag-grid.css`.
   - Remove these from the production build so that only Theming API-based theming is active.
2. **Wire per-user theme prefs into AG Grid Theming API:**
   - Extend `legacyGridTheme` or derive dynamic variants based on effective theme settings (combining `gridPrefs.theme` and UITweak `gridTheme`).
   - Pass a **theme instance that reflects current density, font size, and colours** into `AgGridReact`.
3. **Bridge UITweak grid variables into AG Grid CSS variables where appropriate:**
   - Continue to use `.app-grid__ag-root` and CSS variables (`--grid-font-size`, `--grid-row-height`, etc.) but ensure these are consistent with Theming API settings.
4. **Verify Finances grid:**
   - After wiring, confirm that toggling density, font size, and colour scheme in preferences and UITweak has a clear visual impact on the Finances grid.

### 8.3 UI tweak / `ui_tweak_settings` and `/api/ui-tweak`

**Issues identified:**

- `UiTweakSettings` model and router are implemented to use a `ui_tweak_settings` table.
- Alembic migration `ui_tweak_settings_20251121` exists but has not been applied to the production DB used by the running backend.
- As a result, any call to `/api/ui-tweak` or `/api/admin/ui-tweak` that touches the table raises `psycopg2.errors.UndefinedTable`.

**Proposed high-level steps to fix:**

1. **Restore Alembic connectivity to production Supabase:**
   - Resolve the `Tenant or user not found` error when running `alembic current` with `DATABASE_URL`.
2. **Inspect current revision and migrations:**
   - Once connectivity works, run `alembic history` and `alembic current` to confirm that `ui_tweak_settings_20251121` has not been applied.
3. **Apply the migration in a controlled manner:**
   - Run `alembic upgrade ui_tweak_settings_20251121` (or `upgrade head` if appropriate) against the production database **after validation and backup**.
4. **Verify `/api/ui-tweak`:**
   - Confirm that `GET /api/ui-tweak` now returns a valid settings payload and that `AdminUITweakPage` successfully reads and writes settings.


## 9. Report Summary

- Column widths are conceptually wired end-to-end (AG Grid → `AppDataGrid` → `DataGridPage` → `useGridPreferences` → `/api/grid/preferences` → `UserGridLayout.column_widths`), but in production the widths for `finances_fees` remain `{}`. The likeliest cause is a **column name mismatch** causing the backend to drop width entries.
- The new legacy-style AG Grid theme (`legacyGridTheme`) is in place but is **static** and not driven by per-user theme prefs or UITweak settings. Combined with a residual legacy CSS theme (per AG error #239), this leads to the Finances grid still looking like the older dull table.
- `/api/ui-tweak` fails with `UndefinedTable` because the `UiTweakSettings` model expects the `ui_tweak_settings` table, while the production database **does not yet have that table**; the migration `ui_tweak_settings_20251121` exists in the repo but has not been applied to that DB.
