# Legacy-style dense grid theme for AG Grid

This document explains the design, implementation and usage of the **legacy-style dense theme** for AG Grid in the eBay Connector frontend. The goal is to make all admin data grids (Inventory, Finances, Transactions, Cases/Disputes, etc.) visually closer to the old Windows desktop inventory client: very high information density, clear borders, and strong color cues for statuses and prices.

## 1. High-level goals

The legacy desktop grid (reference screenshots) has several key characteristics:

- **Very high row density** – many rows per screen, minimal vertical padding.
- **Small, sharp font** – ~10–11 px, office-style (Tahoma / Segoe UI).
- **Strong grid lines** – clear separation of rows and columns.
- **Color-coded semantics**:
  - IDs / SKUs are blue and behave like links.
  - Problematic statuses are red; good statuses are blue/green.
  - Prices are green for positive amounts, red for negative.
- **Clear selection / hover states** – selected row is obvious; hover lightly highlighted.

The web grids should **keep current behavior and data** but adopt this visual language.

## 2. Architecture overview

All admin grids share a small set of components and styles:

- `src/components/DataGridPage.tsx` – generic page wrapper for paginated backend grids.
- `src/components/datagrid/AppDataGrid.tsx` – thin React wrapper around `AgGridReact`.
- `src/index.css` – global CSS, including grid-related variables and utility classes.
- `src/main.tsx` – global imports for AG Grid base styles.

The legacy-style theme is implemented as:

1. A **Theming API** theme object for AG Grid (`legacyGridTheme`), based on the Quartz theme.
2. A set of **CSS utility classes** applied via `cellClass` / `cellClassRules` to individual cells.
3. Minimal glue styles on the grid container to ensure correct font sizing.

We intentionally avoid mixing **CSS themes** (`ag-theme-*` classes) with the **Theming API** to prevent configuration conflicts.

## 3. Files and responsibilities

### 3.1 `src/components/datagrid/legacyGridTheme.ts`

Defines the `legacyGridTheme` object using AG Grid's Theming API:

- **Base theme:** `themeQuartz` from `ag-grid-community`.
- **Typography:**
  - `fontFamily`: `Tahoma, "Segoe UI", system-ui, -apple-system, BlinkMacSystemFont, sans-serif`.
  - `fontSize`: `11` (applies to body cells).
  - `headerFontSize`: `11` (headers visually align with body).
- **Density:**
  - `rowHeight`: `22` px – compact data rows.
  - `headerHeight`: `24` px – slightly taller header for readability.
  - `spacing`: `2` – reduces internal padding in cells.
- **Colors:**
  - `backgroundColor`: `#ffffff`.
  - `foregroundColor`: `#111111` (almost black text, high contrast).
- **Header:**
  - `headerBackgroundColor`: `#f0f0f0` (light gray, similar to Win32 listviews).
  - `headerTextColor`: `#111111`.
- **Borders and grid lines:**
  - `borderColor`: `#d0d0d0` for cell and grid borders.
- **Row backgrounds and interaction states:**
  - `oddRowBackgroundColor`: `#fafafa` (subtle zebra striping).
  - `rowHoverColor`: `#f5f5ff` (very light blue).
  - `selectedRowBackgroundColor`: `#fff8c5` (light yellow, clearly visible).

This theme is purely visual; it does not change sorting, selection logic, or any data behavior.

### 3.2 `src/components/datagrid/AppDataGrid.tsx`

`AppDataGrid` is the single place where `AgGridReact` is instantiated for admin grids. The key responsibilities related to theming and density are:

1. **Using the Theming API theme**

   - Imports `legacyGridTheme` and passes it into `<AgGridReact theme={legacyGridTheme} />`.
   - The outer div no longer uses `ag-theme-quartz`; instead it uses the app-specific class `app-grid__ag-root` for minor font tweaks.

2. **Column definitions and semantic styling**

   For each column, we derive `ColDef` and attach semantic classes:

   - `type` is taken from backend metadata (`GridColumnMeta.type`): `string | number | datetime | money | boolean`.
   - `lowerName` is the lowercased column name (e.g. `status`, `sku`, `ebay_id`).

   The following rules are applied:

   #### Numeric and money columns

   - If `type === 'number'` or `type === 'money'`:
     - `cellClass` includes `ag-legacy-number`.
     - This right-aligns content and enables tabular numerals.

   - If `type === 'money'`:
     - `cellClass` includes `ag-legacy-price`.
     - `cellClassRules` define:
       - `ag-legacy-price-positive` – applied when parsed numeric value `> 0`.
       - `ag-legacy-price-negative` – applied when parsed numeric value `< 0`.

   - Parsing uses helper `coerceNumeric(value)`:
     - Accepts `number` or `string`.
     - Strips non-numeric characters, normalises comma/point, and `parseFloat`s.
     - Returns `null` when value cannot be parsed (no coloring applied in this case).

   #### ID / link-like columns

   - If column name matches common ID patterns:
     - Exactly `id`.
     - Contains `sku`.
     - Ends with `_id` or `id`.
     - Contains `ebayid` or `ebay_id`.
   - Then `cellClass` includes `ag-legacy-id-link`.
   - This is rendered as blue text with pointer cursor; on hover it is underlined.
   - The actual click behavior is unchanged; these are still plain cells (not `<a>` tags).

   #### Status columns

   - If column name includes `status`:
     - Two `cellClassRules` are attached:
       - `ag-legacy-status-error` – applied when the lowercase string value contains:
         - `await`, `error`, `fail`, `hold`, `inactive`, `cancel`, or `blocked`.
       - `ag-legacy-status-ok` – applied when the value contains:
         - `active`, `checked`, `ok`, `complete`, `resolved`, or `success`.
   - These rules are heuristics and can be expanded as we discover more status variants.

3. **Default column definition**

The shared `defaultColDef` now only sets header class and disables client-side sort:

- `headerClass: 'ui-table-header'` – aligns styling with global UI typography.
- `sortable: false` – sorting is still delegated to the backend.

### 3.3 `src/index.css`

This file already defined CSS variables for grid density (`--grid-row-height`, etc.). We added:

1. `app-grid__ag-root`

   - Applied to the container around `AgGridReact`.
   - Ensures font size for the grid matches the current density settings:
     - `font-size: var(--grid-font-size);`

2. Legacy semantic classes for AG Grid cells

   - `.ag-legacy-number`
     - `text-align: right;`
     - `font-variant-numeric: tabular-nums;`
   - `.ag-legacy-id-link`
     - `color: #0000ee;`
     - `cursor: pointer;`
     - `white-space: nowrap;`
   - `.ag-legacy-id-link:hover`
     - `text-decoration: underline;`
   - `.ag-legacy-status-error`
     - `color: #b91c1c;`
     - `font-weight: 600;`
   - `.ag-legacy-status-ok`
     - `color: #166534;`
     - `font-weight: 600;`
   - `.ag-legacy-price-positive`
     - `color: #15803d;`
     - `text-align: right;`
   - `.ag-legacy-price-negative`
     - `color: #b91c1c;`
     - `text-align: right;`
   - `.ag-legacy-price`
     - `text-align: right;`

These classes are **purely presentational** and applied through `cellClass` / `cellClassRules` in `AppDataGrid`.

### 3.4 `src/main.tsx`

`main.tsx` now imports only the **base AG Grid styles**:

- `import 'ag-grid-community/styles/ag-grid.css';`

We intentionally removed `ag-theme-quartz.css` because the new theme uses the **Theming API** (`themeQuartz.withParams`) instead of CSS theme classes (`ag-theme-quartz`). Mixing them can cause style conflicts and console warnings.

## 4. How the new theme affects existing pages

Any page that uses `DataGridPage` (for example, `InventoryPage`, `FinancesPage`, etc.) automatically benefits from the new theme because:

- `DataGridPage` internally renders `AppDataGrid`.
- `AppDataGrid` always uses `legacyGridTheme` as its `theme` prop.
- No page-level changes are required.

In particular, the **Inventory grid** (`InventoryPage`) should now resemble the legacy desktop application:

- Noticeably more rows per viewport.
- Smaller, “office-like” font.
- Clear header band with gray background.
- Right-aligned numeric/price columns.
- Blue IDs/SKUs, colored statuses, and prices.
- Subtle zebra striping and clear selection background.

## 5. Design decisions and trade-offs

### 5.1 Using Theming API instead of CSS themes

- **Pros:**
  - Single source of truth for AG Grid visual parameters.
  - Type-checked params via `ThemeDefaultParams` – build fails if we use an unknown property.
  - Easier to derive multiple presets (`legacy`, `compact-dark`, etc.) from the same base.
- **Cons:**
  - Slightly more code (importing and exporting theme object).
  - Requires AG Grid v33+ (already used by the project).

We removed the Quartz CSS theme to avoid conflicting border/background definitions and to comply with AG Grid’s recommendation **not to mix CSS themes and Theming API in the same grid instance**.

### 5.2 Heuristics for semantic coloring

We deliberately kept the semantic rules **heuristic and name-based**:

- Column types and names are controlled by the backend; introducing dedicated flags (e.g. `is_id`, `is_status`) would require API changes.
- The heuristics are conservative: they only color when confident (e.g. when column name contains `status` and the value clearly resembles a problem word like `error` or `inactive`).
- When a value does not match any known pattern, the cell falls back to the default text color.

If, in the future, we want exact control, we can:

- Extend `GridColumnMeta` with optional fields like `semantic_role: 'id' | 'status' | 'price' | ...`.
- Map those roles to `cellClass` directly instead of relying on string matching.

### 5.3 Density vs. accessibility

- The chosen density and font size (11 px) match the legacy desktop look and significantly increase information density.
- For users who require larger text, the existing **UI tweak system** (`gridPrefs.theme.fontSize`, density presets, etc.) can be extended to:
  - Switch to a slightly larger `theme` variant.
  - Adjust CSS variables `--grid-row-height`, `--grid-font-size` while keeping the same semantic coloring.

## 6. Extending or modifying the theme

### 6.1 Adding new semantic roles

To introduce a new semantic class (e.g. `warning`, `pending`, `discount`):

1. Add a CSS rule in `index.css` next to the existing `.ag-legacy-*` classes, for example:

   ```css
   .ag-legacy-status-warning {
     color: #92400e; /* amber-700 */
     font-weight: 600;
   }
   ```

2. Update the `cellClassRules` section in `AppDataGrid`:

   ```ts
   cellClassRules['ag-legacy-status-warning'] = (params) => {
     if (typeof params.value !== 'string') return false;
     const v = params.value.toLowerCase();
     return v.includes('pending') || v.includes('waiting');
   };
   ```

3. Rebuild the frontend and verify that the new statuses render as expected.

### 6.2 Adjusting density

To globally change density for all grids in legacy mode, update `legacyGridTheme`:

- Increase `rowHeight` / `headerHeight` for more breathing room.
- Increase `fontSize` / `headerFontSize` for readability.

If you want **per-user** density control:

- Extend `UITweakContext` / grid preferences to store a `themeVariant`.
- Map that variant to different theme exports, e.g.:
  - `legacyGridThemeCompact` – 20 px rows.
  - `legacyGridThemeNormal` – 24 px rows.

### 6.3 Dark or high-contrast variants

The existing `index.css` already has `.app-grid.grid-theme-dark` / `.grid-theme-highContrast`. For AG Grid, you can define separate themes:

```ts
export const legacyGridThemeDark = themeQuartz.withParams({
  ...commonParams,
  backgroundColor: '#020617',
  foregroundColor: '#e5e7eb',
  headerBackgroundColor: '#111827',
  headerTextColor: '#e5e7eb',
  borderColor: '#374151',
  oddRowBackgroundColor: '#020617',
  rowHoverColor: '#1f2937',
  selectedRowBackgroundColor: '#1e293b',
});
```

Then wire it in `AppDataGrid` based on user preference:

- Use `gridPrefs.theme.colorScheme` or a new flag to select which theme object to pass to `AgGridReact`.

## 7. Testing and verification

After implementing the changes, we verified:

- `npm run build` completes successfully (TypeScript + Vite build).
- No AG Grid console warnings about conflicting themes.
- Visual inspection (Inventory grid):
  - Row height decreased; примерно в 1.5–2 раза больше строк на экран.
  - Заголовок серого цвета с чёткой границей.
  - Синие SKU/ID, красные/зелёные статусы и цены.
  - Зебра, hover и выделение заметны, но не агрессивны.

## 8. Summary

- Все админские гриды теперь используют единый **legacy-style dense** AG Grid theme.
- Вся логика по данным (колонки, сортировка, фильтры) осталась прежней; изменения касаются только отображения.
- Семантическое окрашивание и выравнивание реализованы централизованно в `AppDataGrid` и `index.css`, поэтому любые новые гриды автоматически наследуют этот стиль.

При необходимости можно быстро откатить к стандартному виду, заменив `legacyGridTheme` на дефолтный `themeQuartz` или создав новый, менее плотный пресет, не трогая сами страницы и API.