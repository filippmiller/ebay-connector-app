import React, { useMemo, useRef } from 'react';
import { AgGridReact } from 'ag-grid-react';
import type {
  ColDef,
  ColumnResizedEvent,
  ColumnMovedEvent,
  ColumnPinnedEvent,
  ColumnVisibleEvent,
  ColumnState,
} from 'ag-grid-community';
import type { GridColumnMeta } from '@/components/DataGridPage';

export interface AppDataGridColumnState {
  name: string;
  label: string;
  width: number;
}

export interface AppDataGridProps {
  columns: AppDataGridColumnState[];
  rows: Record<string, any>[];
  columnMetaByName: Record<string, GridColumnMeta>;
  loading?: boolean;
  onRowClick?: (row: Record<string, any>) => void;
  onLayoutChange?: (state: { order: string[]; widths: Record<string, number> }) => void;
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

function extractLayout(columnStates: ColumnState[]): { order: string[]; widths: Record<string, number> } {
  const order: string[] = [];
  const widths: Record<string, number> = {};

  columnStates.forEach((col: ColumnState) => {
    const id = (col.colId as string) || '';
    if (!id) return;
    order.push(id);
    if (typeof col.width === 'number') {
      widths[id] = col.width;
    }
  });

  return { order, widths };
}

export const AppDataGrid: React.FC<AppDataGridProps> = ({
  columns,
  rows,
  columnMetaByName,
  loading,
  onRowClick,
  onLayoutChange,
}) => {
  const layoutDebounceRef = useRef<number | null>(null);
  const columnDefs = useMemo<ColDef[]>(
    () =>
      columns.map((col) => {
        const meta = columnMetaByName[col.name];
        const type = meta?.type;

        return {
          field: col.name,
          headerName: meta?.label || col.label || col.name,
          width: col.width,
          resizable: false,
          sortable: false,
          filter: false,
          suppressMenu: true,
          valueFormatter: (params) => formatCellValue(params.value, type),
        } as ColDef;
      }),
    [columns, columnMetaByName],
  );

  const defaultColDef = useMemo<ColDef>(
    () => ({
      cellClass: 'ui-table-cell',
      headerClass: 'ui-table-header',
      sortable: false,
    }),
    [],
  );

  const handleColumnEvent = (
    event: ColumnResizedEvent | ColumnMovedEvent | ColumnPinnedEvent | ColumnVisibleEvent,
  ) => {
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

  return (
    <div className="w-full h-full ag-theme-sq">
      <AgGridReact
        columnDefs={columnDefs}
        defaultColDef={defaultColDef}
        rowData={rows}
        rowSelection="single"
        suppressMultiSort
        suppressScrollOnNewData
        suppressAggFuncInHeader
        animateRows
        onColumnResized={handleColumnEvent}
        onColumnMoved={handleColumnEvent}
        onColumnVisible={handleColumnEvent}
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
      {loading && rows.length === 0 && (
        <div className="absolute inset-0 flex items-center justify-center text-sm text-gray-500 bg-white/60">
          Loading data…
        </div>
      )}
    </div>
  );
};
