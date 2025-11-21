import React, { useEffect, useRef, useState, useMemo } from 'react';
import api from '@/lib/apiClient';
import { useGridPreferences } from '@/hooks/useGridPreferences';

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
  /** Optional row click handler (e.g. for detail panels). */
  onRowClick?: (row: Record<string, any>) => void;
}

interface ColumnState {
  name: string;
  label: string;
  width: number;
}

export const DataGridPage: React.FC<DataGridPageProps> = ({ gridKey, title, extraParams, onRowClick }) => {
  const [columns, setColumns] = useState<ColumnState[]>([]);
  const [rows, setRows] = useState<Record<string, any>[]>([]);
  const [limit, setLimit] = useState(50);
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const [loadingData, setLoadingData] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showColumnsPanel, setShowColumnsPanel] = useState(false);
  const [search, setSearch] = useState('');

  const gridPrefs = useGridPreferences(gridKey);

  const resizingColRef = useRef<string | null>(null);
  const startXRef = useRef<number>(0);
  const startWidthRef = useRef<number>(0);
  const draggingColRef = useRef<string | null>(null);
  const columnsRef = useRef<ColumnState[]>([]);

  useEffect(() => {
    columnsRef.current = columns;
  }, [columns]);

  const extraParamsKey = useMemo(() => {
    if (!extraParams) return '';
    try {
      return JSON.stringify(extraParams);
    } catch {
      return '';
    }
  }, [extraParams]);

  // Reset pagination when grid key, filters, or search change
  useEffect(() => {
    setOffset(0);
  }, [gridKey, extraParamsKey, search]);

  const availableColumnsMap = useMemo(() => {
    const map: Record<string, GridColumnMeta> = {};
    gridPrefs.availableColumns.forEach((c) => {
      map[c.name] = c;
    });
    return map;
  }, [gridPrefs.availableColumns]);

  // Ensure we have a columns config once preferences are loaded.
  useEffect(() => {
    if (gridPrefs.loading) return;
    if (gridPrefs.columns || gridPrefs.availableColumns.length === 0) return;

    const allNames = gridPrefs.availableColumns.map((c) => c.name);
    gridPrefs.setColumns({
      visible: allNames,
      order: allNames,
      widths: {},
      sort: null,
    });
  }, [gridPrefs.loading, gridPrefs.columns, gridPrefs.availableColumns, gridPrefs.setColumns]);

  const orderedVisibleColumns = useMemo(() => {
    const cfg = gridPrefs.columns;
    if (!cfg) return [] as string[];

    const baseOrder = (cfg.order && cfg.order.length ? cfg.order : gridPrefs.availableColumns.map((c) => c.name));
    return baseOrder.filter((name) => cfg.visible.includes(name) && !!availableColumnsMap[name]);
  }, [gridPrefs.columns, gridPrefs.availableColumns, availableColumnsMap]);

  // Recompute renderable columns whenever preferences or metadata change
  useEffect(() => {
    const cfg = gridPrefs.columns;
    if (!cfg || orderedVisibleColumns.length === 0) {
      setColumns([]);
      return;
    }

    const nextCols: ColumnState[] = orderedVisibleColumns.map((name) => {
      const meta = availableColumnsMap[name];
      const width = cfg.widths[name] || meta?.width_default || 150;
      return { name, label: meta?.label || name, width };
    });
    setColumns(nextCols);
  }, [gridPrefs.columns, orderedVisibleColumns, availableColumnsMap]);

  // Load data whenever preferences / pagination / filters change
  useEffect(() => {
    if (gridPrefs.loading) return;
    const cfg = gridPrefs.columns;
    if (!cfg || orderedVisibleColumns.length === 0) {
      setRows([]);
      setTotal(0);
      return;
    }

    const fetchData = async () => {
      setLoadingData(true);
      setError(null);
      try {
        const params: any = {
          limit,
          offset,
          columns: orderedVisibleColumns.join(','),
        };
        if (search && search.trim()) {
          params.search = search.trim();
        }
        if (cfg.sort && cfg.sort.column) {
          params.sort_by = cfg.sort.column;
          params.sort_dir = cfg.sort.direction;
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
  }, [gridPrefs.loading, gridPrefs.columns, orderedVisibleColumns, limit, offset, gridKey, extraParamsKey, extraParams, search]);

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
    const cfg = gridPrefs.columns;
    if (!cfg) return;
    const alreadyVisible = cfg.visible.includes(name);
    const nextVisible = alreadyVisible
      ? cfg.visible.filter((c) => c !== name)
      : [...cfg.visible, name];
    gridPrefs.setColumns({ visible: nextVisible });
  };

  const handleSelectAllColumns = () => {
    const allNames = gridPrefs.availableColumns.map((c) => c.name);
    if (!allNames.length) return;
    gridPrefs.setColumns({
      visible: allNames,
      order: allNames,
    });
  };

  const handleClearAllColumns = () => {
    if (!gridPrefs.columns) return;
    gridPrefs.setColumns({ visible: [] });
  };

  const handleResetToDefaults = async () => {
    await gridPrefs.clearServerPreferences();
  };

  const handleSaveColumns = async () => {
    await gridPrefs.save();
    setShowColumnsPanel(false);
  };

  const handleHeaderClick = (colName: string) => {
    const meta = availableColumnsMap[colName];
    if (!meta || !meta.sortable || !gridPrefs.columns) return;
    const prevSort = gridPrefs.columns.sort;
    let nextDirection: 'asc' | 'desc' = 'desc';
    if (prevSort && prevSort.column === colName) {
      nextDirection = prevSort.direction === 'asc' ? 'desc' : 'asc';
    }
    gridPrefs.setColumns({
      sort: { column: colName, direction: nextDirection },
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
    if (!gridPrefs.columns) return;

    const currentOrder = gridPrefs.columns.order && gridPrefs.columns.order.length
      ? gridPrefs.columns.order
      : gridPrefs.columns.visible;
    const nextOrder = reorderColumns(currentOrder, sourceColName, targetColName);
    gridPrefs.setColumns({ order: nextOrder });
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
    if (!gridPrefs.columns) return;
    // Persist widths into preferences based on the *latest* rendered columns and
    // immediately save to the backend so column sizes survive page reloads
    // without requiring an explicit Save.
    const widths: Record<string, number> = { ...gridPrefs.columns.widths };
    columnsRef.current.forEach((c) => {
      widths[c.name] = c.width;
    });
    gridPrefs.setColumns({ widths });
    void gridPrefs.save();
  };

  const gridTitle = title || gridKey;

  const density = gridPrefs.theme?.density || 'normal';
  const colorScheme = gridPrefs.theme?.colorScheme || 'default';
  const buttonLayout = gridPrefs.theme?.buttonLayout || 'right';
  const currentSort = gridPrefs.columns?.sort || null;

  // Theme-driven visual customisation
  // Body font sizing: use numeric level 1-10 if present, otherwise map legacy preset.
  const legacyBodyPreset = gridPrefs.theme?.fontSize || 'medium';
  const bodyLevelFromPreset = legacyBodyPreset === 'small' ? 3 : legacyBodyPreset === 'large' ? 8 : 5;
  const bodyFontSizeLevel =
    typeof gridPrefs.theme?.bodyFontSizeLevel === 'number'
      ? gridPrefs.theme.bodyFontSizeLevel
      : bodyLevelFromPreset;
  // Map level 1-10 to a readable px size (~11px to 20px).
  const clampedBodyLevel = Math.min(10, Math.max(1, bodyFontSizeLevel));
  const bodyFontSizePx = 10 + clampedBodyLevel; // 11-20px
  const bodyFontWeight =
    (gridPrefs.theme?.bodyFontWeight as string | undefined) === 'bold' ? 'bold' : 'normal';
  const bodyFontStyle =
    (gridPrefs.theme?.bodyFontStyle as string | undefined) === 'italic' ? 'italic' : 'normal';

  // Header font sizing & color
  const headerFontSizeSetting = gridPrefs.theme?.headerFontSize || legacyBodyPreset;
  const headerFontSizePx = headerFontSizeSetting === 'small' ? 11 : headerFontSizeSetting === 'large' ? 15 : 13;
  const headerTextColor = gridPrefs.theme?.headerTextColor as string | undefined;
  const gridBackgroundColor = gridPrefs.theme?.backgroundColor as string | undefined;

  return (
    <div
      className={`flex flex-col h-full app-grid grid-density-${density} grid-theme-${colorScheme}`}
      style={{ fontSize: bodyFontSizePx, backgroundColor: gridBackgroundColor || undefined }}
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-semibold tracking-tight">{gridTitle}</h2>
          {(buttonLayout === 'left' || buttonLayout === 'split') && (
            <button
              className="px-3 py-2 border rounded-md text-xs bg-white hover:bg-gray-50 shadow-sm"
              onClick={() => setShowColumnsPanel(true)}
            >
              Columns
            </button>
          )}
        </div>
        <div className="flex items-center gap-3 text-sm">
          <input
            className="px-2 py-1 border rounded-md text-xs bg-white placeholder:text-gray-400"
            placeholder="Search all columns"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <div className="flex items-center gap-1 text-xs text-gray-600">
            <span>Sort:</span>
            <select
              className="px-2 py-1 border rounded-md bg-white"
              value={currentSort?.column || ''}
              onChange={(e) => {
                const newCol = e.target.value;
                if (!newCol) {
                  gridPrefs.setColumns({ sort: null });
                  return;
                }
                const prevSort = gridPrefs.columns?.sort;
                const nextDirection: 'asc' | 'desc' =
                  prevSort && prevSort.column === newCol ? prevSort.direction : 'desc';
                gridPrefs.setColumns({
                  sort: { column: newCol, direction: nextDirection },
                });
              }}
            >
              <option value="">Default</option>
              {orderedVisibleColumns
                .filter((name) => availableColumnsMap[name]?.sortable !== false)
                .map((name) => (
                  <option key={name} value={name}>
                    {availableColumnsMap[name]?.label || name}
                  </option>
                ))}
            </select>
            <button
              type="button"
              className="px-2 py-1 border rounded-md bg-white disabled:opacity-50"
              disabled={!currentSort}
              onClick={() => {
                if (!currentSort) return;
                gridPrefs.setColumns({
                  sort: {
                    column: currentSort.column,
                    direction: currentSort.direction === 'asc' ? 'desc' : 'asc',
                  },
                });
              }}
            >
              {currentSort?.direction === 'asc' ? 'Asc ▲' : 'Desc ▼'}
            </button>
          </div>
          {buttonLayout === 'right' && (
            <button
              className="px-3 py-2 border rounded-md text-xs bg-white hover:bg-gray-50 shadow-sm"
              onClick={() => setShowColumnsPanel(true)}
            >
              Columns
            </button>
          )}
          <span className="text-xs text-gray-500">
            {loadingData ? 'Loading data…' : `${total} rows`}
          </span>
          <select
            className="px-3 py-2 border rounded-md text-xs bg-white hover:bg-gray-50"
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

      <div
        className="flex-1 min-h-0 border rounded-lg bg-white overflow-auto"
        style={gridBackgroundColor ? { backgroundColor: gridBackgroundColor } : undefined}
      >
        {gridPrefs.loading ? (
          <div className="p-4 text-sm text-gray-500">Loading layout…</div>
        ) : orderedVisibleColumns.length === 0 ? (
          <div className="p-4 text-sm text-gray-500">No columns configured.</div>
        ) : (
          <table className="min-w-full text-[13px] border-collapse">
            <thead className="bg-gray-100">
              <tr>
                {columns.map((col) => {
                  const isSorted = currentSort && currentSort.column === col.name;
                  const meta = availableColumnsMap[col.name];
                  return (
                    <th
                      key={col.name}
                      style={{
                        width: col.width,
                        minWidth: col.width,
                        fontSize: headerFontSizePx,
                        color: headerTextColor || undefined,
                      }}
                      className="border-b border-r px-3 py-2 text-left font-mono text-[11px] uppercase tracking-wide text-gray-600 sticky top-0 bg-gray-100 z-10 relative select-none"
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
                              {currentSort?.direction === 'asc' ? '▲' : '▼'}
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
                  <tr
                    key={idx}
                    className="border-t odd:bg-white even:bg-gray-50 hover:bg-indigo-50 transition-colors cursor-pointer"
                    style={gridBackgroundColor ? { backgroundColor: gridBackgroundColor } : undefined}
                    onClick={() => {
                      if (onRowClick) {
                        onRowClick(row);
                      }
                    }}
                  >
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
                          className="px-3 py-2 border-t border-r whitespace-nowrap max-w-xs overflow-hidden text-ellipsis align-middle"
                          style={{
                            width: col.width,
                            minWidth: col.width,
                            fontSize: bodyFontSizePx,
                            fontWeight: bodyFontWeight,
                            fontStyle: bodyFontStyle,
                            backgroundColor: gridBackgroundColor || undefined,
                          }}
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

      {/* Columns / Layout & Theme panel */}
      {showColumnsPanel && (
        <div className="fixed inset-0 bg-black bg-opacity-30 flex items-center justify-center z-50">
          <div className="bg-white rounded shadow-lg w-full max-w-md max-h-[80vh] flex flex-col">
            <div className="px-4 py-2 border-b flex items-center justify-between">
              <div className="font-semibold text-sm">Columns & layout for {gridKey}</div>
              <button
                className="text-xs text-gray-500"
                onClick={() => setShowColumnsPanel(false)}
              >
                Close
              </button>
            </div>
            <div className="p-3 flex-1 overflow-auto text-xs space-y-3">
              {/* Columns section */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <div className="font-semibold text-[11px] uppercase tracking-wide text-gray-600">
                    Columns
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      className="px-2 py-1 border rounded text-[11px] bg-gray-50 hover:bg-gray-100"
                      onClick={handleSelectAllColumns}
                    >
                      Select all
                    </button>
                    <button
                      className="px-2 py-1 border rounded text-[11px] bg-gray-50 hover:bg-gray-100"
                      onClick={handleClearAllColumns}
                    >
                      Clear all
                    </button>
                    <button
                      className="px-2 py-1 border rounded text-[11px] bg-gray-50 hover:bg-gray-100"
                      onClick={handleResetToDefaults}
                    >
                      Reset
                    </button>
                  </div>
                </div>
                <div className="space-y-1">
                  {gridPrefs.availableColumns.map((col) => (
                    <label key={col.name} className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={!!gridPrefs.columns?.visible.includes(col.name)}
                        onChange={() => toggleColumnVisibility(col.name)}
                      />
                      <span className="font-mono text-[11px]">{col.name}</span>
                      <span className="text-gray-500 text-[11px]">({col.label || col.name})</span>
                    </label>
                  ))}
                  {gridPrefs.availableColumns.length === 0 && (
                    <div className="text-[11px] text-gray-500">No columns metadata.</div>
                  )}
                </div>
              </div>

              {/* Layout & Theme section */}
              <div className="border-t pt-3 mt-2 space-y-2">
                <div className="font-semibold text-[11px] uppercase tracking-wide text-gray-600">
                  Layout & theme
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <label className="flex flex-col gap-1">
                    <span className="text-[11px] text-gray-600">Density</span>
                    <select
                      className="border rounded px-2 py-1 text-[11px] bg-white"
                      value={gridPrefs.theme.density}
                      onChange={(e) => gridPrefs.setTheme({ density: e.target.value as any })}
                    >
                      <option value="compact">Compact</option>
                      <option value="normal">Normal</option>
                      <option value="comfortable">Comfortable</option>
                    </select>
                  </label>
                  <label className="flex flex-col gap-1">
                    <span className="text-[11px] text-gray-600">Body font size</span>
                    <select
                      className="border rounded px-2 py-1 text-[11px] bg-white"
                      value={
                        typeof gridPrefs.theme.bodyFontSizeLevel === 'number'
                          ? (gridPrefs.theme.bodyFontSizeLevel as number)
                          : 5
                      }
                      onChange={(e) =>
                        gridPrefs.setTheme({ bodyFontSizeLevel: Number(e.target.value) || 5 })
                      }
                    >
                      {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((lvl) => (
                        <option key={lvl} value={lvl}>
                          Size {lvl}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="flex flex-col gap-1">
                    <span className="text-[11px] text-gray-600">Color scheme</span>
                    <select
                      className="border rounded px-2 py-1 text-[11px] bg-white"
                      value={gridPrefs.theme.colorScheme}
                      onChange={(e) => gridPrefs.setTheme({ colorScheme: e.target.value as any })}
                    >
                      <option value="default">Default</option>
                      <option value="blue">Blue</option>
                      <option value="dark">Dark</option>
                      <option value="highContrast">High contrast</option>
                    </select>
                  </label>
                  <label className="flex flex-col gap-1">
                    <span className="text-[11px] text-gray-600">Toolbar layout</span>
                    <select
                      className="border rounded px-2 py-1 text-[11px] bg-white"
                      value={gridPrefs.theme.buttonLayout}
                      onChange={(e) => gridPrefs.setTheme({ buttonLayout: e.target.value as any })}
                    >
                      <option value="left">Buttons left</option>
                      <option value="right">Buttons right</option>
                      <option value="split">Title left, buttons right</option>
                    </select>
                  </label>
                  <label className="flex flex-col gap-1">
                    <span className="text-[11px] text-gray-600">Grid background</span>
                    <input
                      type="color"
                      className="border rounded px-1 py-1 h-7 w-full bg-white"
                      value={
                        typeof gridPrefs.theme.backgroundColor === 'string' && gridPrefs.theme.backgroundColor
                          ? (gridPrefs.theme.backgroundColor as string)
                          : '#ffffff'
                      }
                      onChange={(e) => gridPrefs.setTheme({ backgroundColor: e.target.value })}
                    />
                  </label>
                  <label className="flex flex-col gap-1">
                    <span className="text-[11px] text-gray-600">Header font size</span>
                    <select
                      className="border rounded px-2 py-1 text-[11px] bg-white"
                      value={(gridPrefs.theme.headerFontSize as any) || gridPrefs.theme.fontSize}
                      onChange={(e) => gridPrefs.setTheme({ headerFontSize: e.target.value as any })}
                    >
                      <option value="small">Small</option>
                      <option value="medium">Medium</option>
                      <option value="large">Large</option>
                    </select>
                  </label>
                  <label className="flex flex-col gap-1">
                    <span className="text-[11px] text-gray-600">Body font weight</span>
                    <select
                      className="border rounded px-2 py-1 text-[11px] bg-white"
                      value={(gridPrefs.theme.bodyFontWeight as any) || 'normal'}
                      onChange={(e) => gridPrefs.setTheme({ bodyFontWeight: e.target.value as any })}
                    >
                      <option value="normal">Normal</option>
                      <option value="bold">Bold</option>
                    </select>
                  </label>
                  <label className="flex flex-col gap-1">
                    <span className="text-[11px] text-gray-600">Body font style</span>
                    <select
                      className="border rounded px-2 py-1 text-[11px] bg-white"
                      value={(gridPrefs.theme.bodyFontStyle as any) || 'normal'}
                      onChange={(e) => gridPrefs.setTheme({ bodyFontStyle: e.target.value as any })}
                    >
                      <option value="normal">Normal</option>
                      <option value="italic">Italic (cursive)</option>
                    </select>
                  </label>
                  <label className="flex flex-col gap-1 col-span-2">
                    <span className="text-[11px] text-gray-600">Header text color</span>
                    <div className="flex items-center gap-2">
                      <input
                        type="color"
                        className="border rounded px-1 py-1 h-7 w-16 bg-white"
                        value={
                          typeof gridPrefs.theme.headerTextColor === 'string' && gridPrefs.theme.headerTextColor
                            ? (gridPrefs.theme.headerTextColor as string)
                            : '#4b5563'
                        }
                        onChange={(e) => gridPrefs.setTheme({ headerTextColor: e.target.value })}
                      />
                      <span className="text-[11px] text-gray-500">
                        Choose a custom color for column names. Leave as default to use the theme colors.
                      </span>
                    </div>
                  </label>
                </div>
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