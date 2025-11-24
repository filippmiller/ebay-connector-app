# Grid Preferences Audit (excerpt)

This document summarizes how the shared grid preference system works for AG Grid / AppDataGrid based pages.

For a full description of the grid architecture, see `docs/GRIDS_SYSTEM_AND_UPDATES.md`.

## Behavior update (column widths persistence)

**Previous behavior (before this change)**

- `AppDataGrid` listened to AG Grid events (`onColumnResized`, `onColumnMoved`, `onColumnVisible`) and reported the latest layout `{ order, widths }` back to `DataGridPage` via `onLayoutChange`.
- `DataGridPage.handleGridLayoutChange`:
  - Merged the new order and widths into `gridPrefs.columns`.
  - Immediately called `gridPrefs.save({...})`, which POSTed to `/api/grid/preferences`.
- Result: **any column resize, move, or visibility change was auto-persisted** to the `user_grid_layouts` row for that `grid_key`, even if the user never clicked the Columns dialog Save button.

**New behavior (after this change)**

- `AppDataGrid` still reports layout changes (`{ order, widths }`) via `onLayoutChange` whenever the user resizes, moves, or hides/shows columns.
- `DataGridPage.handleGridLayoutChange` now:
  - Updates the in-memory `GridColumnsConfig` via `gridPrefs.setColumns({...})`.
  - **Does not call `gridPrefs.save` anymore.**
- The Columns panel actions (`Select all`, `Clear all`, individual column checkboxes) also:
  - Update `gridPrefs.columns` in memory.
  - **Do not auto-save to the backend.**
- The only place that persists layout + theme to the database is the **Save** button in the "Columns & layout" panel:
  - `handleSaveColumns` calls `gridPrefs.save()` once, sending the current `columns` (including `widths`, `visible`, `order`, `sort`) and `theme` to `/api/grid/preferences`.

**Implications for users**

- Resizing or reordering columns updates the grid immediately, but those changes are **temporary** until you open **Columns & layout** and click **Save**.
- Toggling column visibility also updates the grid in real time, but the new layout only becomes permanent after clicking **Save**.
- After reloading the page:
  - If you resized/moved/toggled columns **without** saving, the grid falls back to the last saved layout (or defaults).
  - If you resized/moved/toggled columns **and then clicked Save**, the new layout (including widths) is restored from the database.

The backend schema and APIs remain unchanged: `UserGridLayout.visible_columns`, `UserGridLayout.column_widths`, `UserGridLayout.sort`, and `UserGridLayout.theme` are still written via `/api/grid/preferences`; only the **timing** of those writes has changed.