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
  GridApi,
  ICellRendererParams,
} from 'ag-grid-community';

// Register AG Grid modules
ModuleRegistry.registerModules([AllCommunityModule]);
import type { GridColumnMeta } from '@/components/DataGridPage';
import { buildLegacyGridTheme } from '@/components/datagrid/legacyGridTheme';
import type { GridThemeConfig } from '@/hooks/useGridPreferences';

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
  /** Optional grid key used for targeted debug logging (e.g. finances_fees). */
  gridKey?: string;
  /** Per-grid theme configuration coming from /api/grid/preferences. */
  gridTheme?: GridThemeConfig | null;
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
  gridKey,
  gridTheme,
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

    return columns.map((col) => {
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
            v.includes('success')
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
  }, [columns, columnMetaByName, gridKey, sortConfig]);

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
    if (rows.length > 0 && columnDefs.length > 0) {
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
      className="w-full h-full app-grid__ag-root"
      style={{ position: 'relative', height: '100%', width: '100%' }}
    >
      {columnDefs.length === 0 ? (
        <div className="absolute inset-0 flex items-center justify-center text-sm text-gray-500">
          No columns configured
        </div>
      ) : (
        <AgGridReact
          theme={buildLegacyGridTheme(gridTheme)}
          columnDefs={columnDefs}
          defaultColDef={defaultColDef}
          rowData={rows}
          rowSelection={{ mode: 'singleRow' }}
          suppressMultiSort
          suppressScrollOnNewData
          suppressAggFuncInHeader
          animateRows
          onGridReady={(params) => {
            gridApiRef.current = params.api as GridApi;
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
      )}
      {loading && rows.length === 0 && columnDefs.length > 0 && (
        <div className="absolute inset-0 flex items-center justify-center text-sm text-gray-500 bg-white/60 z-10">
          Loading data…
        </div>
      )}
    </div>
  );
});
