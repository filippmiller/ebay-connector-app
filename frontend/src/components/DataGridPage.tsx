import React, { useEffect, useRef, useState, useMemo } from 'react';
import api from '@/lib/apiClient';

export interface GridColumnMeta {
  name: string;
  label: string;
  type?: 'string' | 'number' | 'datetime' | 'money' | 'boolean';
  width_default?: number;
  sortable?: boolean;
}

export interface GridLayoutResponse {
  grid_key: string;
  available_columns: GridColumnMeta[];
  visible_columns: string[];
  column_widths: Record<string, number>;
  sort?: {
    column: string;
    direction: 'asc' | 'desc';
  } | null;
  is_default: boolean;
}

export interface GridDataResponse {
  rows: Record<string, any>[];
  limit: number;
  offset: number;
  total: number;
  sort?: {
    column: string;
    direction: 'asc' | 'desc';
  } | null;
}

interface DataGridPageProps {
  gridKey: string;
  title?: string;
  /** Additional query params to pass to the backend /data endpoint (e.g. filters). */
  extraParams?: Record<string, any>;
}

interface ColumnState {
  name: string;
  label: string;
  width: number;
}

export const DataGridPage: React.FC<DataGridPageProps> = ({ gridKey, title, extraParams }) => {
  const [layout, setLayout] = useState<GridLayoutResponse | null>(null);
  const [columns, setColumns] = useState<ColumnState[]>([]);
  const [visibleColumns, setVisibleColumns] = useState<string[]>([]);
  const [rows, setRows] = useState<Record<string, any>[]>([]);
  const [limit, setLimit] = useState(50);
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const [loadingLayout, setLoadingLayout] = useState(false);
  const [loadingData, setLoadingData] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showColumnsPanel, setShowColumnsPanel] = useState(false);

  const [sort, setSort] = useState<{ column: string; direction: 'asc' | 'desc' } | null>(null);

  const resizingColRef = useRef<string | null>(null);
  const startXRef = useRef<number>(0);
  const startWidthRef = useRef<number>(0);
  const draggingColRef = useRef<string | null>(null);

  const extraParamsKey = useMemo(() => {
    if (!extraParams) return '';
    try {
      return JSON.stringify(extraParams);
    } catch {
      return '';
    }
  }, [extraParams]);

  // Reset pagination when grid key or filters change
  useEffect(() => {
    setOffset(0);
  }, [gridKey, extraParamsKey]);

  // Load layout
  useEffect(() => {
    const fetchLayout = async () => {
      setLoadingLayout(true);
      setError(null);
      try {
        const resp = await api.get<GridLayoutResponse>(`/api/grids/${gridKey}/layout`);
        const data = resp.data;
        setLayout(data);
        const colMap: Record<string, GridColumnMeta> = {};
        data.available_columns.forEach((c) => {
          colMap[c.name] = c;
        });
        const initialVisible = data.visible_columns.filter((c) => colMap[c]);
        setVisibleColumns(initialVisible);
        const cols: ColumnState[] = initialVisible.map((name) => {
          const meta = colMap[name];
          const width = data.column_widths[name] || meta.width_default || 150;
          return { name, label: meta.label || name, width };
        });
        setColumns(cols);
        setSort(data.sort || null);
      } catch (e: any) {
        console.error('Failed to load grid layout', e);
        setError(e?.response?.data?.detail || e.message || 'Failed to load grid layout');
      } finally {
        setLoadingLayout(false);
      }
    };

    fetchLayout();
  }, [gridKey]);

  // Recompute columns whenever visibleColumns or layout change
  useEffect(() => {
    if (!layout) return;
    if (!visibleColumns.length) {
      setColumns([]);
      return;
    }
    const nextCols: ColumnState[] = visibleColumns
      .map((name) => {
        const meta = availableColumnsMap[name];
        if (!meta) return null;
        const width = layout.column_widths[name] || meta.width_default || 150;
        return { name, label: meta.label || name, width };
      })
      .filter((c): c is ColumnState => c !== null);
    setColumns(nextCols);
  }, [layout, visibleColumns, layout?.column_widths, layout?.available_columns]);

  // Load data whenever layout/visibleColumns/sort/limit/offset change
  useEffect(() => {
    if (!layout) return;
    if (!visibleColumns.length) return;
    const fetchData = async () => {
      setLoadingData(true);
      setError(null);
      try {
        const params: any = {
          limit,
          offset,
          columns: visibleColumns.join(','),
        };
        if (sort && sort.column) {
          params.sort_by = sort.column;
          params.sort_dir = sort.direction;
        }
        if (extraParams) {
          Object.assign(params, extraParams);
        }
        const resp = await api.get<GridDataResponse>(`/api/grids/${gridKey}/data`, { params });
        const data = resp.data;
        setRows(data.rows || []);
        setTotal(data.total || 0);
      } catch (e: any) {
        console.error('Failed to load grid data', e);
        setError(e?.response?.data?.detail || e.message || 'Failed to load grid data');
      } finally {
        setLoadingData(false);
      }
    };

    fetchData();
  }, [layout, visibleColumns, sort, limit, offset, gridKey, extraParamsKey]);

  const availableColumnsMap: Record<string, GridColumnMeta> = {};
  layout?.available_columns.forEach((c) => {
    availableColumnsMap[c.name] = c;
  });

  const reorderColumns = (list: string[], fromName: string, toName: string): string[] => {
    if (fromName === toName) return list;
    const current = [...list];
    const fromIndex = current.indexOf(fromName);
    const toIndex = current.indexOf(toName);
    if (fromIndex === -1 || toIndex === -1) return list;
    current.splice(fromIndex, 1);
    current.splice(toIndex, 0, fromName);
    return current;
  };

  const toggleColumnVisibility = (name: string) => {
    setVisibleColumns((prev) => {
      if (prev.includes(name)) {
        return prev.filter((c) => c !== name);
      }
      return [...prev, name];
    });
  };

  const resetToDefaults = () => {
    if (!layout) return;
    const defaults = layout.visible_columns;
    setVisibleColumns(defaults);
    const cols: ColumnState[] = defaults.map((name) => {
      const meta = availableColumnsMap[name];
      const width = layout.column_widths[name] || meta?.width_default || 150;
      return { name, label: meta?.label || name, width };
    });
    setColumns(cols);
    setSort(layout.sort || null);
  };

  const persistLayout = async (nextVisible: string[], nextWidths: Record<string, number>, nextSort: typeof sort) => {
    try {
      const resp = await api.put<GridLayoutResponse>(`/api/grids/${gridKey}/layout`, {
        visible_columns: nextVisible,
        column_widths: nextWidths,
        sort: nextSort,
      });
      const data = resp.data;
      setLayout(data);
      const colMap: Record<string, GridColumnMeta> = {};
      data.available_columns.forEach((c) => {
        colMap[c.name] = c;
      });
      const updatedVisible = data.visible_columns.filter((c) => colMap[c]);
      setVisibleColumns(updatedVisible);
      setSort(data.sort || null);
    } catch (e) {
      console.error('Failed to save grid layout', e);
    }
  };

  const handleSaveColumns = () => {
    setShowColumnsPanel(false);
    const nextVisible = visibleColumns.filter((c) => availableColumnsMap[c]);
    const widths: Record<string, number> = {};
    columns.forEach((c) => {
      if (nextVisible.includes(c.name)) {
        widths[c.name] = c.width;
      }
    });
    persistLayout(nextVisible, widths, sort);
  };

  const handleHeaderClick = (colName: string) => {
    const meta = availableColumnsMap[colName];
    if (!meta || !meta.sortable) return;
    setSort((prev) => {
      if (prev && prev.column === colName) {
        const nextDir = prev.direction === 'asc' ? 'desc' : 'asc';
        const nextSort = { column: colName, direction: nextDir } as const;
        // Persist sort immediately
        const widths: Record<string, number> = {};
        columns.forEach((c) => {
          widths[c.name] = c.width;
        });
        persistLayout(visibleColumns, widths, nextSort);
        return nextSort;
      }
      const nextSort = { column: colName, direction: 'desc' } as const;
      const widths: Record<string, number> = {};
      columns.forEach((c) => {
        widths[c.name] = c.width;
      });
      persistLayout(visibleColumns, widths, nextSort);
      return nextSort;
    });
  };

  // Column resize handlers
  const onMouseDownResize = (e: React.MouseEvent, colName: string, currentWidth: number) => {
    e.preventDefault();
    resizingColRef.current = colName;
    startXRef.current = e.clientX;
    startWidthRef.current = currentWidth;
    window.addEventListener('mousemove', onMouseMoveResize);
    window.addEventListener('mouseup', onMouseUpResize);
  };

  const handleDragStart = (e: React.DragEvent, colName: string) => {
    draggingColRef.current = colName;
    try {
      e.dataTransfer.effectAllowed = 'move';
      e.dataTransfer.setData('text/plain', colName);
    } catch {
      // dataTransfer may not be available in some environments; ignore
    }
  };

  const handleDragOver = (e: React.DragEvent, _colName: string) => {
    e.preventDefault();
  };

  const handleDrop = (e: React.DragEvent, targetColName: string) => {
    e.preventDefault();
    const sourceColName = draggingColRef.current;
    draggingColRef.current = null;
    if (!sourceColName || sourceColName === targetColName) return;

    setVisibleColumns((prev) => {
      const nextVisible = reorderColumns(prev, sourceColName, targetColName);
      const widths: Record<string, number> = {};
      columns.forEach((c) => {
        widths[c.name] = c.width;
      });
      persistLayout(nextVisible, widths, sort);
      return nextVisible;
    });
  };

  const onMouseMoveResize = (e: MouseEvent) => {
    const colName = resizingColRef.current;
    if (!colName) return;
    const delta = e.clientX - startXRef.current;
    const newWidth = Math.max(60, startWidthRef.current + delta);
    setColumns((prev) => prev.map((c) => (c.name === colName ? { ...c, width: newWidth } : c)));
  };

  const onMouseUpResize = () => {
    const colName = resizingColRef.current;
    if (!colName) return;
    resizingColRef.current = null;
    window.removeEventListener('mousemove', onMouseMoveResize);
    window.removeEventListener('mouseup', onMouseUpResize);
    // Persist widths
    const widths: Record<string, number> = {};
    columns.forEach((c) => {
      widths[c.name] = c.width;
    });
    persistLayout(visibleColumns, widths, sort);
  };

  const gridTitle = title || layout?.grid_key || gridKey;

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between mb-2">
        <h2 className="text-xl font-semibold">{gridTitle}</h2>
        <div className="flex items-center gap-2 text-sm">
          <span className="text-xs text-gray-500">
            {loadingData ? 'Loading data…' : `${total} rows`}
          </span>
          <button
            className="px-2 py-1 border rounded text-xs bg-white hover:bg-gray-50"
            onClick={() => setShowColumnsPanel(true)}
          >
            Columns
          </button>
          <select
            className="px-2 py-1 border rounded text-xs"
            value={limit}
            onChange={(e) => {
              setOffset(0);
              setLimit(Number(e.target.value) || 50);
            }}
          >
            <option value={20}>20</option>
            <option value={50}>50</option>
            <option value={100}>100</option>
            <option value={200}>200</option>
          </select>
        </div>
      </div>

      {error && <div className="mb-2 text-xs text-red-600">{error}</div>}

      <div className="flex-1 min-h-0 border rounded bg-white overflow-auto">
        {loadingLayout ? (
          <div className="p-4 text-sm text-gray-500">Loading layout…</div>
        ) : !layout ? (
          <div className="p-4 text-sm text-gray-500">No layout available.</div>
        ) : (
          <table className="min-w-full text-xs border-collapse">
            <thead className="bg-gray-100">
              <tr>
                {columns.map((col) => {
                  const isSorted = sort && sort.column === col.name;
                  const meta = availableColumnsMap[col.name];
                  return (
                    <th
                      key={col.name}
                      style={{ width: col.width, minWidth: col.width }}
                      className="border-b border-r px-2 py-1 text-left font-mono text-[11px] relative select-none"
                      onDragOver={(e) => handleDragOver(e, col.name)}
                      onDrop={(e) => handleDrop(e, col.name)}
                    >
                      <div className="flex items-center gap-1">
                        <span
                          className="cursor-move select-none text-gray-400"
                          draggable
                          onDragStart={(e) => handleDragStart(e, col.name)}
                          onClick={(e) => e.stopPropagation()}
                        >
                          ⋮⋮
                        </span>
                        <div
                          className="flex items-center cursor-pointer flex-1"
                          onClick={() => handleHeaderClick(col.name)}
                        >
                          <span>{meta?.label || col.label}</span>
                          {isSorted && (
                            <span className="ml-1 text-[9px]">
                              {sort?.direction === 'asc' ? '▲' : '▼'}
                            </span>
                          )}
                        </div>
                      </div>
                      <div
                        className="absolute right-0 top-0 h-full w-1 cursor-col-resize"
                        onMouseDown={(e) => onMouseDownResize(e, col.name, col.width)}
                      />
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {loadingData ? (
                <tr>
                  <td colSpan={columns.length} className="p-4 text-center text-gray-500">
                    Loading data…
                  </td>
                </tr>
              ) : rows.length === 0 ? (
                <tr>
                  <td colSpan={columns.length} className="p-4 text-center text-gray-500">
                    No data.
                  </td>
                </tr>
              ) : (
                rows.map((row, idx) => (
                  <tr key={idx} className="border-t hover:bg-gray-50">
                    {columns.map((col) => {
                      const raw = row[col.name];
                      let value: any = raw;
                      const type = availableColumnsMap[col.name]?.type || 'string';
                      if (raw === null || raw === undefined) {
                        value = '';
                      } else if (type === 'datetime') {
                        try {
                          value = new Date(raw).toLocaleString();
                        } catch {
                          value = String(raw);
                        }
                      } else if (type === 'money' || type === 'number') {
                        value = String(raw);
                      } else if (typeof raw === 'object') {
                        value = JSON.stringify(raw);
                      }
                      return (
                        <td
                          key={col.name}
                          className="px-2 py-1 border-t border-r whitespace-nowrap max-w-xs overflow-hidden text-ellipsis"
                          style={{ width: col.width, minWidth: col.width }}
                        >
                          {value}
                        </td>
                      );
                    })}
                  </tr>
                ))
              )}
            </tbody>
          </table>
        )}
      </div>

      {/* Columns panel */}
      {showColumnsPanel && layout && (
        <div className="fixed inset-0 bg-black bg-opacity-30 flex items-center justify-center z-50">
          <div className="bg-white rounded shadow-lg w-full max-w-md max-h-[80vh] flex flex-col">
            <div className="px-4 py-2 border-b flex items-center justify-between">
              <div className="font-semibold text-sm">Columns for {gridKey}</div>
              <button
                className="text-xs text-gray-500"
                onClick={() => setShowColumnsPanel(false)}
              >
                Close
              </button>
            </div>
            <div className="p-3 flex-1 overflow-auto text-xs">
              <div className="flex items-center justify-between mb-2">
                <button
                  className="px-2 py-1 border rounded text-[11px] bg-gray-50 hover:bg-gray-100"
                  onClick={() => setVisibleColumns(layout.available_columns.map((c) => c.name))}
                >
                  Select all
                </button>
                <button
                  className="px-2 py-1 border rounded text-[11px] bg-gray-50 hover:bg-gray-100"
                  onClick={() => setVisibleColumns([])}
                >
                  Clear all
                </button>
                <button
                  className="px-2 py-1 border rounded text-[11px] bg-gray-50 hover:bg-gray-100"
                  onClick={resetToDefaults}
                >
                  Reset to defaults
                </button>
              </div>
              <div className="space-y-1">
                {layout.available_columns.map((col) => (
                  <label key={col.name} className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={visibleColumns.includes(col.name)}
                      onChange={() => toggleColumnVisibility(col.name)}
                    />
                    <span className="font-mono text-[11px]">{col.name}</span>
                    <span className="text-gray-500 text-[11px]">({col.label || col.name})</span>
                  </label>
                ))}
              </div>
            </div>
            <div className="px-4 py-2 border-t flex justify-end gap-2 text-xs">
              <button
                className="px-3 py-1 border rounded bg-gray-50 hover:bg-gray-100"
                onClick={() => setShowColumnsPanel(false)}
              >
                Cancel
              </button>
              <button
                className="px-3 py-1 border rounded bg-blue-600 text-white hover:bg-blue-700"
                onClick={handleSaveColumns}
              >
                Save
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};