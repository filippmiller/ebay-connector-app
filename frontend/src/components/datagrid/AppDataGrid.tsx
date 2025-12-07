import { useMemo, useRef, forwardRef, useImperativeHandle } from 'react';
import { AgGridReact } from 'ag-grid-react';
import {
  ModuleRegistry,
  AllCommunityModule,
} from 'ag-grid-community';
import type {
  ColDef,
  ColumnState,
  CellClassRules,
  CellStyle,
  GridApi,
  ICellRendererParams,
  CellStyleFunc,
} from 'ag-grid-community';
import 'ag-grid-community/styles/ag-grid.css';
import 'ag-grid-community/styles/ag-theme-quartz.css';

// Register AG Grid modules
ModuleRegistry.registerModules([AllCommunityModule]);
import type { GridColumnMeta } from '@/components/DataGridPage';

import type { GridThemeConfig, ColumnStyle } from '@/hooks/useGridPreferences';

export interface AppDataGridColumnState {
  name: string;
  label: string;
  width: number;
}

export type GridLayoutSnapshot = {
  order: string[];
  widths: Record<string, number>;
};

export type AppDataGridHandle = {
  /**
   * Returns the current column order and widths as reported by AG Grid,
   * or null when the grid API is not yet ready.
   */
  getCurrentLayout: () => GridLayoutSnapshot | null;
};

export interface AppDataGridProps {
  columns: AppDataGridColumnState[];
  rows: Record<string, any>[];
  columnMetaByName: Record<string, GridColumnMeta>;
  loading?: boolean;
  onRowClick?: (row: Record<string, any>) => void;
  onLayoutChange?: (state: { order: string[]; widths: Record<string, number> }) => void;
  /** Server-side sort config; drives header sort indicators. */
  sortConfig?: { column: string; direction: 'asc' | 'desc' } | null;
  /** Callback when sort model changes via header clicks. */
  onSortChange?: (sort: { column: string; direction: 'asc' | 'desc' } | null) => void;
  /** Checkbox selection mode: 'singleRow' or 'multiRow'. Default is 'singleRow'. */
  selectionMode?: 'singleRow' | 'multiRow';
  /** Callback when selection changes. */
  onSelectionChange?: (selectedRows: Record<string, any>[]) => void;
  /** Optional grid key used for targeted debug logging (e.g. finances_fees). */
  gridKey?: string;
  /** Per-grid theme configuration coming from /api/grid/preferences. */
  gridTheme?: GridThemeConfig | null;
  /** Extra column definitions to append (e.g. action buttons). */
  extraColumns?: ColDef[];
}

function formatCellValue(raw: any, type: GridColumnMeta['type'] | undefined): string {
  if (raw === null || raw === undefined) return '';

  const t = type || 'string';

  if (t === 'datetime') {
    try {
      return new Date(raw).toLocaleString();
    } catch {
      return String(raw);
    }
  }

  if (t === 'money' || t === 'number') {
    return String(raw);
  }

  if (typeof raw === 'object') {
    try {
      return JSON.stringify(raw);
    } catch {
      return String(raw);
    }
  }

  return String(raw);
}

function coerceNumeric(value: unknown): number | null {
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : null;
  }
  if (typeof value === 'string') {
    const cleaned = value.replace(/[^0-9+\-.,]/g, '').replace(',', '.');
    const n = Number.parseFloat(cleaned);
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

function extractLayout(columnStates: ColumnState[]): { order: string[]; widths: Record<string, number> } {
  const order: string[] = [];
  const widths: Record<string, number> = {};

  columnStates.forEach((col: ColumnState) => {
    const id = (col.colId as string) || '';
    if (!id) return;

    // Filter out AG Grid's internal columns (checkbox selection, etc.)
    if (id.startsWith('ag-Grid-')) {
      return;
    }

    order.push(id);
    if (typeof col.width === 'number' && Number.isFinite(col.width)) {
      // Normalise to an integer pixel width. AG Grid can emit fractional widths,
      // but the backend expects Dict[str, int] in columns.widths.
      const rounded = Math.round(col.width);
      // Clamp to a sane range to avoid pathological values.
      const clamped = Math.min(4000, Math.max(40, rounded));
      widths[id] = clamped;
    }
  });

  return { order, widths };
}

export const AppDataGrid = forwardRef<AppDataGridHandle, AppDataGridProps>(({
  columns,
  rows,
  columnMetaByName,
  loading,
  onRowClick,
  onLayoutChange,
  sortConfig,
  onSortChange,
  selectionMode = 'singleRow',
  onSelectionChange,
  gridKey,
  gridTheme,
  extraColumns,
}, ref) => {
  const layoutDebounceRef = useRef<number | null>(null);
  const gridApiRef = useRef<GridApi | null>(null);

  useImperativeHandle(ref, () => ({
    getCurrentLayout: () => {
      const api = gridApiRef.current;
      if (!api) return null;
      const model = (api as any).getColumnState?.() as ColumnState[] | undefined;
      if (!model) return null;
      return extractLayout(model);
    },
  }), []);
  const columnDefs = useMemo<ColDef[]>(() => {
    if (!columns || columns.length === 0) {
      return [];
    }

    const columnStyles: Record<string, ColumnStyle> | undefined = gridTheme?.columnStyles as
      | Record<string, ColumnStyle>
      | undefined;

    const defs = columns.map((col) => {
      const meta = columnMetaByName[col.name];
      const type = meta?.type;
      const lowerName = col.name.toLowerCase();

      const cellClasses: string[] = ['ui-table-cell'];
      const cellClassRules: CellClassRules = {};

      // Right-align numeric and money columns
      if (type === 'number' || type === 'money') {
        cellClasses.push('ag-legacy-number');
      }

      // Money columns: color positive/negative amounts
      if (type === 'money') {
        cellClasses.push('ag-legacy-price');
        cellClassRules['ag-legacy-price-positive'] = (params) => {
          const n = coerceNumeric(params.value);
          return n !== null && n > 0;
        };
        cellClassRules['ag-legacy-price-negative'] = (params) => {
          const n = coerceNumeric(params.value);
          return n !== null && n < 0;
        };
      }

      // ID / key style: SKU, ItemID, eBayID, generic *id
      if (
        lowerName === 'id' ||
        lowerName.includes('sku') ||
        lowerName.endsWith('_id') ||
        lowerName.endsWith('id') ||
        lowerName.includes('ebayid') ||
        lowerName.includes('ebay_id')
      ) {
        cellClasses.push('ag-legacy-id-link');
      }

      // Status-style coloring based on common keywords
      if (lowerName.includes('status')) {
        cellClassRules['ag-legacy-status-error'] = (params) => {
          if (typeof params.value !== 'string') return false;
          const v = params.value.toLowerCase();
          return (
            v.includes('await') ||
            v.includes('error') ||
            v.includes('fail') ||
            v.includes('hold') ||
            v.includes('inactive') ||
            v.includes('cancel') ||
            v.includes('blocked')
          );
        };
        cellClassRules['ag-legacy-status-ok'] = (params) => {
          if (typeof params.value !== 'string') return false;
          const v = params.value.toLowerCase();
          return (
            v.includes('active') ||
            v.includes('checked') ||
            v.includes('ok') ||
            v.includes('complete') ||
            v.includes('resolved') ||
            v.includes('success') ||
            v.includes('parsed') ||
            v.includes('uploaded')
          );
        };
        cellClassRules['ag-legacy-status-warning'] = (params) => {
          if (typeof params.value !== 'string') return false;
          const v = params.value.toLowerCase();
          return (
            v.includes('processing') ||
            v.includes('pending') ||
            v.includes('wait') ||
            v.includes('review')
          );
        };
      }

      const colDef: ColDef = {
        colId: col.name, // Explicit colId for AG Grid
        field: col.name, // Field name must match row data keys
        headerName: meta?.label || col.label || col.name,
        width: col.width,
        resizable: true, // Enable resizing
        sortable: meta?.sortable !== false, // Enable header click sorting when allowed
        filter: false,
        valueFormatter: (params) => formatCellValue(params.value, type),
        // Ensure column is visible
        hide: false,
        cellClass: cellClasses,
      };

      // Apply optional per-column style overrides (font size / weight / color).
      const styleOverride = columnStyles?.[col.name];
      if (styleOverride) {
        const fontSizePx =
          typeof styleOverride.fontSizeLevel === 'number'
            ? 10 + Math.min(10, Math.max(1, styleOverride.fontSizeLevel))
            : undefined;
        const styleFn: CellStyleFunc<any, any, any> = () => {
          const base: CellStyle = {};
          if (fontSizePx) (base as any).fontSize = `${fontSizePx}px`;
          if (styleOverride.fontWeight) (base as any).fontWeight = styleOverride.fontWeight;
          if (styleOverride.textColor) (base as any).color = styleOverride.textColor;
          return base;
        };
        colDef.cellStyle = styleFn;
      }

      // Special case: inventory StatusSKU should render with dynamic color from lookup.
      if (gridKey === 'inventory' && col.name === 'StatusSKU') {
        colDef.valueFormatter = undefined;
        colDef.cellRenderer = (params: ICellRendererParams) => {
          const raw = params.value;
          const color = (params.data as any)?.StatusSKU_color as string | undefined;
          const value = formatCellValue(raw, type);
          if (!value) return '';
          return (
            <span style={color ? { color } : undefined}>
              {value}
            </span>
          );
        };
      }

      // Special case: make sniper_snipes.item_id clickable to open the eBay page.
      if (gridKey === 'sniper_snipes' && col.name === 'item_id') {
        colDef.valueFormatter = undefined;
        colDef.cellRenderer = (params: ICellRendererParams) => {
          const raw = params.value;
          const value = formatCellValue(raw, type);
          if (!value) return '';
          const href = `https://www.ebay.com/itm/${encodeURIComponent(value)}`;
          return (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="text-blue-600 hover:underline"
            >
              {value}
            </a>
          );
        };
      }

      if (Object.keys(cellClassRules).length > 0) {
        colDef.cellClassRules = cellClassRules;
      }

      // Mark current sort column for header indicators.
      if (sortConfig && sortConfig.column === col.name) {
        (colDef as any).sort = sortConfig.direction;
      }

      return colDef;
    });

    if (extraColumns && extraColumns.length) {
      const extraMap = new Map(extraColumns.map(c => [c.colId, c]));
      // Replace existing columns if they are defined in extraColumns
      const mergedDefs = defs.map(col => {
        if (col.colId && extraMap.has(col.colId)) {
          const extra = extraMap.get(col.colId)!;
          extraMap.delete(col.colId);
          // Merge generic props, but let extra overwrite
          return { ...col, ...extra };
        }
        return col;
      });
      // Append remaining extra columns
      mergedDefs.push(...Array.from(extraMap.values()));
      return mergedDefs;
    }
    return defs;
  }, [columns, columnMetaByName, gridKey, sortConfig, gridTheme, extraColumns]);

  const defaultColDef = useMemo<ColDef>(
    () => ({
      headerClass: 'ui-table-header',
      sortable: false,
    }),
    [],
  );

  const handleColumnEvent = (event: any) => {
    if (!onLayoutChange || !event.api) return;

    if (layoutDebounceRef.current !== null) {
      window.clearTimeout(layoutDebounceRef.current);
    }

    layoutDebounceRef.current = window.setTimeout(() => {
      const model = (event.api as any).getColumnState?.() as ColumnState[] | undefined;
      if (!model) return;
      const { order, widths } = extractLayout(model);
      if (gridKey === 'finances_fees') {
        // Temporary targeted debug for width persistence investigation
        // eslint-disable-next-line no-console
        console.log('[AppDataGrid] finances_fees layout changed:', { order, widths });
      }
      onLayoutChange({ order, widths });
    }, 500);
  };

  const handleSortChanged = (event: any) => {
    if (!onSortChange || !event.api) return;
    const model = event.api.getSortModel?.() as { colId: string; sort: 'asc' | 'desc' }[] | undefined;
    if (!model || model.length === 0) {
      onSortChange(null);
      return;
    }
    const first = model[0];
    if (!first.colId || !first.sort) {
      onSortChange(null);
      return;
    }
    onSortChange({ column: first.colId, direction: first.sort });
  };

  // Debug logging (remove in production)
  if (process.env.NODE_ENV === 'development') {
    if (columnDefs.length === 0 && columns.length > 0) {
      console.warn('[AppDataGrid] columnDefs is empty but columns prop has', columns.length, 'items');
    }
    console.log(`[AppDataGrid] ${gridKey || 'unknown'}: rows type=${Array.isArray(rows) ? 'array' : typeof rows}, rows.length=${rows?.length || 0}, columnDefs.length=${columnDefs.length}`);
    if (!Array.isArray(rows)) {
      console.error('[AppDataGrid] rows prop is not an array!', rows);
    }
    if (rows && rows.length > 0) {
      console.log(`[AppDataGrid] ${gridKey || 'unknown'}: First row:`, rows[0]);
      console.log(`[AppDataGrid] ${gridKey || 'unknown'}: First row keys:`, Object.keys(rows[0]));
    }
    if (columnDefs.length > 0) {
      console.log(`[AppDataGrid] ${gridKey || 'unknown'}: Column defs:`, columnDefs.slice(0, 3));
      console.log(`[AppDataGrid] ${gridKey || 'unknown'}: Column fields:`, columnDefs.map(d => d.field));
    }
    if (rows && rows.length > 0 && columnDefs.length > 0) {
      const firstRowKeys = Object.keys(rows[0] || {});
      const columnFields = columnDefs.map((d) => d.field).filter((f): f is string => !!f);
      const missingFields = columnFields.filter((f) => !firstRowKeys.includes(f));
      if (missingFields.length > 0) {
        console.warn('[AppDataGrid] Column fields not in row data:', missingFields);
        console.warn('[AppDataGrid] Row data keys:', firstRowKeys.slice(0, 10));
        console.warn('[AppDataGrid] Column fields:', columnFields.slice(0, 10));
      }
    }
  }

  return (
    <div
      className="w-full h-full app-grid__ag-root ag-theme-quartz flex flex-col"
      style={{ position: 'relative', minHeight: '500px' }}
    >
      {columnDefs.length === 0 ? (
        <div className="flex-1 flex items-center justify-center text-sm text-gray-500">
          No columns configured
        </div>
      ) : (
        <div className="flex-1 min-h-0">
          <AgGridReact
            rowModelType="clientSide"
            columnDefs={columnDefs}
            defaultColDef={defaultColDef}
            rowData={rows}
            getRowId={(params) => {
              // Use 'id' field if available, otherwise generate a stable ID from data
              if (params.data?.id != null) {
                return String(params.data.id);
              }
              // Fallback: use a hash of the first few fields to create a stable ID
              const keys = Object.keys(params.data || {}).slice(0, 3);
              const values = keys.map(k => params.data?.[k]).join('-');
              return `row-${values}` || `row-${Math.random()}`;
            }}
            rowSelection={{
              mode: selectionMode,
              checkboxes: selectionMode === 'multiRow',
              headerCheckbox: selectionMode === 'multiRow',
            }}
            suppressMultiSort
            suppressScrollOnNewData
            suppressAggFuncInHeader
            animateRows
            onGridReady={(params) => {
              gridApiRef.current = params.api as GridApi;
            }}
            onSelectionChanged={(event) => {
              if (onSelectionChange && event.api) {
                onSelectionChange(event.api.getSelectedRows());
              }
            }}
            onColumnResized={handleColumnEvent}
            onColumnMoved={handleColumnEvent}
            onColumnVisible={handleColumnEvent}
            onSortChanged={handleSortChanged}
            onRowClicked={
              onRowClick
                ? (event) => {
                  if (event.data) {
                    onRowClick(event.data as Record<string, any>);
                  }
                }
                : undefined
            }
          />
        </div>
      )}
      {loading && rows.length === 0 && columnDefs.length > 0 && (
        <div className="absolute inset-0 flex items-center justify-center text-sm text-gray-500 bg-white/60 z-10">
          Loading data…
        </div>
      )}
    </div>
  );
});
