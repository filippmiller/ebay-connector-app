// DataGridPage component – fixed implementation
import React, { useEffect, useState, useMemo } from 'react';
import api from '@/lib/apiClient';
import { useGridPreferences } from '@/hooks/useGridPreferences';
import { AppDataGrid } from '@/components/datagrid/AppDataGrid';

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
  sort?: { column: string; direction: 'asc' | 'desc' } | null;
  is_default: boolean;
}

export interface GridDataResponse {
  rows: Record<string, any>[];
  limit: number;
  offset: number;
  total: number;
  sort?: { column: string; direction: 'asc' | 'desc' } | null;
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

  // Helper to stringify extraParams for memoization
  const extraParamsKey = useMemo(() => {
    if (!extraParams) return '';
    try {
      return JSON.stringify(extraParams);
    } catch {
      return '';
    }
  }, [extraParams]);

  // Reset pagination when key/filters/search change
  useEffect(() => {
    setOffset(0);
  }, [gridKey, extraParamsKey, search]);

  // Map of column meta by name
  const availableColumnsMap = useMemo(() => {
    const map: Record<string, GridColumnMeta> = {};
    gridPrefs.availableColumns.forEach(c => {
      map[c.name] = c;
    });
    return map;
  }, [gridPrefs.availableColumns]);

  // Initialise column config if missing
  useEffect(() => {
    if (gridPrefs.loading) return;
    if (gridPrefs.columns) return;
    if (gridPrefs.availableColumns.length === 0) return;
    const allNames = gridPrefs.availableColumns.map(c => c.name);
    gridPrefs.setColumns({ visible: allNames, order: allNames, widths: {}, sort: null });
  }, [gridPrefs.loading, gridPrefs.columns, gridPrefs.availableColumns, gridPrefs.setColumns]);

  // Determine ordered visible columns based on preferences
  const orderedVisibleColumns = useMemo(() => {
    const cfg = gridPrefs.columns;
    if (!cfg) {
      // fallback to all available
      return gridPrefs.availableColumns.map(c => c.name).filter(name => !!availableColumnsMap[name]);
    }
    const baseOrder = cfg.order && cfg.order.length ? cfg.order : cfg.visible && cfg.visible.length ? cfg.visible : gridPrefs.availableColumns.map(c => c.name);
    const result = baseOrder.filter(name => {
      const isVisible = !cfg.visible || cfg.visible.length === 0 || cfg.visible.includes(name);
      return isVisible && !!availableColumnsMap[name];
    });
    if (result.length === 0 && gridPrefs.availableColumns.length > 0) {
      return gridPrefs.availableColumns.map(c => c.name).filter(name => !!availableColumnsMap[name]);
    }
    return result;
  }, [gridPrefs.columns, gridPrefs.availableColumns, availableColumnsMap]);

  // Build column definitions for the grid
  useEffect(() => {
    if (orderedVisibleColumns.length === 0) {
      setColumns([]);
      return;
    }
    const cfg = gridPrefs.columns;
    const nextCols: ColumnState[] = orderedVisibleColumns.map(name => {
      const meta = availableColumnsMap[name];
      const width = cfg?.widths?.[name] || meta?.width_default || 150;
      return { name, label: meta?.label || name, width };
    });
    setColumns(nextCols);
  }, [orderedVisibleColumns, availableColumnsMap, gridPrefs.columns]);

  // Fetch data rows from backend
  useEffect(() => {
    const fetchData = async () => {
      setLoadingData(true);
      setError(null);
      try {
        const params = new URLSearchParams({ limit: limit.toString(), offset: offset.toString() });
        if (search) params.append('search', search);
        if (extraParams) {
          Object.entries(extraParams).forEach(([k, v]) => params.append(k, String(v)));
        }
        const resp = await api.get<GridDataResponse>(`/api/grids/${gridKey}/data?${params.toString()}`);
        setRows(resp.data.rows);
        setTotal(resp.data.total);
      } catch (e: any) {
        setError(e.message || 'Failed to load data');
      } finally {
        setLoadingData(false);
      }
    };
    fetchData();
  }, [gridKey, limit, offset, search, extraParams]);

  // Handle layout changes from the grid (order & widths)
  const handleGridLayoutChange = (order: string[], widths: Record<string, number>) => {
    const cfg = gridPrefs.columns;
    if (!cfg) return;

    // 'order' contains only visible columns (from AG Grid).
    // We want to update cfg.order to match 'order' for the visible items,
    // but keep hidden items in their relative places or at least present.
    const visibleSet = new Set(cfg.visible);
    const hiddenColumns = cfg.order.filter(c => !visibleSet.has(c));

    // New order is the visible order from grid + any hidden columns we had.
    const nextOrder = [...order, ...hiddenColumns];
    const nextWidths = { ...cfg.widths, ...widths };

    console.log('[DataGridPage] Saving layout:', { visible: cfg.visible, order: nextOrder, widths: nextWidths });
    gridPrefs.setColumns({ visible: cfg.visible, order: nextOrder, widths: nextWidths, sort: cfg.sort });
    void gridPrefs.save({ visible: cfg.visible, order: nextOrder, widths: nextWidths, sort: cfg.sort });
  };

  const handleSelectAllColumns = () => {
    const allNames = gridPrefs.availableColumns.map(c => c.name);
    if (!allNames.length) return;
    const cfg = gridPrefs.columns;
    const nextConfig = {
      visible: allNames,
      order: cfg?.order || allNames,
      widths: cfg?.widths || {},
      sort: cfg?.sort || null
    };
    gridPrefs.setColumns(nextConfig);
    void gridPrefs.save(nextConfig);
  };

  const handleClearAllColumns = () => {
    if (!gridPrefs.columns) return;
    const cfg = gridPrefs.columns;
    const nextConfig = {
      visible: [],
      order: cfg.order,
      widths: cfg.widths,
      sort: cfg.sort
    };
    gridPrefs.setColumns(nextConfig);
    void gridPrefs.save(nextConfig);
  };

  const handleResetToDefaults = async () => {
    await gridPrefs.clearServerPreferences();
  };

  const handleSaveColumns = async () => {
    await gridPrefs.save();
    setShowColumnsPanel(false);
  };

  const gridTitle = title || gridKey;
  const density = gridPrefs.theme?.density || 'normal';
  const colorScheme = gridPrefs.theme?.colorScheme || 'default';
  const buttonLayout = gridPrefs.theme?.buttonLayout || 'right';
  const currentSort = gridPrefs.columns?.sort || null;

  // Theme styling
  const legacyBodyPreset = gridPrefs.theme?.fontSize || 'medium';
  const bodyLevelFromPreset = legacyBodyPreset === 'small' ? 3 : legacyBodyPreset === 'large' ? 8 : 5;
  const bodyFontSizeLevel = typeof gridPrefs.theme?.bodyFontSizeLevel === 'number' ? gridPrefs.theme.bodyFontSizeLevel : bodyLevelFromPreset;
  const clampedBodyLevel = Math.min(10, Math.max(1, bodyFontSizeLevel));
  const bodyFontSizePx = 10 + clampedBodyLevel;
  const gridBackgroundColor = gridPrefs.theme?.backgroundColor as string | undefined;

  return (
    <div className={`flex flex-col h-full app-grid grid-density-${density} grid-theme-${colorScheme}`} style={{ fontSize: bodyFontSizePx, backgroundColor: gridBackgroundColor || undefined }}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-semibold tracking-tight">{gridTitle}</h2>
          {(buttonLayout === 'left' || buttonLayout === 'split') && (
            <button className="px-3 py-2 border rounded-md text-xs bg-white hover:bg-gray-50 shadow-sm" onClick={() => setShowColumnsPanel(true)}>
              Columns
            </button>
          )}
        </div>
        <div className="flex items-center gap-3 text-sm">
          <input className="px-2 py-1 border rounded-md text-xs bg-white placeholder:text-gray-400" placeholder="Search all columns" value={search} onChange={e => setSearch(e.target.value)} />
          <div className="flex items-center gap-1 text-xs text-gray-600">
            <span>Sort:</span>
            <select className="px-2 py-1 border rounded-md bg-white" value={currentSort?.column || ''} onChange={e => {
              const newCol = e.target.value;
              if (!newCol) {
                const cfg = gridPrefs.columns;
                if (cfg) gridPrefs.setColumns({ sort: null, visible: cfg.visible, order: cfg.order, widths: cfg.widths });
                return;
              }
              const prev = gridPrefs.columns?.sort;
              const dir: 'asc' | 'desc' = prev && prev.column === newCol ? prev.direction : 'desc';
              const cfg = gridPrefs.columns;
              if (cfg) gridPrefs.setColumns({ sort: { column: newCol, direction: dir }, visible: cfg.visible, order: cfg.order, widths: cfg.widths });
            }}>
              <option value="">Default</option>
              {orderedVisibleColumns.filter(name => availableColumnsMap[name]?.sortable !== false).map(name => (
                <option key={name} value={name}>{availableColumnsMap[name]?.label || name}</option>
              ))}
            </select>
            <button type="button" className="px-2 py-1 border rounded-md bg-white disabled:opacity-50" disabled={!currentSort} onClick={() => {
              if (!currentSort) return;
              const cfg = gridPrefs.columns;
              if (cfg) gridPrefs.setColumns({ sort: { column: currentSort.column, direction: currentSort.direction === 'asc' ? 'desc' : 'asc' }, visible: cfg.visible, order: cfg.order, widths: cfg.widths });
            }}>
              {currentSort?.direction === 'asc' ? 'Asc ▲' : 'Desc ▼'}
            </button>
          </div>
          {buttonLayout === 'right' && (
            <button className="px-3 py-2 border rounded-md text-xs bg-white hover:bg-gray-50 shadow-sm" onClick={() => setShowColumnsPanel(true)}>
              Columns
            </button>
          )}
          <span className="text-xs text-gray-500">{loadingData ? 'Loading data…' : `${total} rows`}</span>
          <select className="px-3 py-2 border rounded-md text-xs bg-white hover:bg-gray-50" value={limit} onChange={e => { setOffset(0); setLimit(Number(e.target.value) || 50); }}>
            <option value={20}>20</option>
            <option value={50}>50</option>
            <option value={100}>100</option>
            <option value={200}>200</option>
          </select>
        </div>
      </div>

      {error && <div className="mb-2 text-xs text-red-600">{error}</div>}

      <div className="flex-1 min-h-0 border rounded-lg bg-white" style={gridBackgroundColor ? { backgroundColor: gridBackgroundColor } : undefined}>
        {gridPrefs.loading ? (
          <div className="p-4 text-sm text-gray-500">Loading layout…</div>
        ) : columns.length === 0 && gridPrefs.availableColumns.length === 0 ? (
          <div className="p-4 text-sm text-gray-500">No columns configured.</div>
        ) : columns.length === 0 ? (
          <div className="p-4 text-sm text-gray-500">Initializing columns…</div>
        ) : (
          <AppDataGrid
            columns={columns}
            rows={rows ?? []}
            columnMetaByName={availableColumnsMap}
            loading={loadingData}
            onRowClick={onRowClick}
            onLayoutChange={({ order, widths }) => handleGridLayoutChange(order, widths)}
          />
        )}
      </div>

      {/* Columns / Layout & Theme panel */}
      {showColumnsPanel && (
        <div className="fixed inset-0 bg-black bg-opacity-30 flex items-center justify-center z-50">
          <div className="bg-white rounded shadow-lg w-full max-w-md max-h-[80vh] flex flex-col">
            <div className="px-4 py-2 border-b flex items-center justify-between">
              <div className="font-semibold text-sm">Columns & layout for {gridKey}</div>
              <button className="text-xs text-gray-500" onClick={() => setShowColumnsPanel(false)}>Close</button>
            </div>
            <div className="p-3 flex-1 overflow-auto text-xs space-y-3">
              <div>
                <div className="flex items-center justify-between mb-2">
                  <div className="font-semibold text-[11px] uppercase tracking-wide text-gray-600">Columns</div>
                  <div className="flex items-center gap-2">
                    <button className="px-2 py-1 border rounded text-[11px] bg-gray-50 hover:bg-gray-100" onClick={handleSelectAllColumns}>Select all</button>
                    <button className="px-2 py-1 border rounded text-[11px] bg-gray-50 hover:bg-gray-100" onClick={handleClearAllColumns}>Clear all</button>
                  </div>
                </div>
                <div className="space-y-1">
                  {gridPrefs.availableColumns.map((col) => {
                    const isVisible = !gridPrefs.columns?.visible || gridPrefs.columns.visible.includes(col.name);
                    return (
                      <label key={col.name} className="flex items-center gap-2 p-1 hover:bg-gray-50 rounded cursor-pointer">
                        <input
                          type="checkbox"
                          className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                          checked={isVisible}
                          onChange={(e) => {
                            const checked = e.target.checked;
                            const currentVisible = gridPrefs.columns?.visible || gridPrefs.availableColumns.map(c => c.name);
                            const currentOrder = gridPrefs.columns?.order || gridPrefs.availableColumns.map(c => c.name);

                            let nextVisible = [...currentVisible];
                            let nextOrder = [...currentOrder];

                            if (checked) {
                              if (!nextVisible.includes(col.name)) {
                                nextVisible.push(col.name);
                                if (!nextOrder.includes(col.name)) {
                                  nextOrder.push(col.name);
                                }
                              }
                            } else {
                              nextVisible = nextVisible.filter(n => n !== col.name);
                            }

                            const cfg = gridPrefs.columns;
                            const nextConfig = {
                              visible: nextVisible,
                              order: nextOrder,
                              widths: cfg?.widths || {},
                              sort: cfg?.sort || null
                            };
                            gridPrefs.setColumns(nextConfig);
                            void gridPrefs.save(nextConfig);
                          }}
                        />
                        <span className="text-sm text-gray-700">{col.label || col.name}</span>
                      </label>
                    );
                  })}
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button className="px-2 py-1 border rounded bg-gray-100" onClick={handleResetToDefaults}>Reset to defaults</button>
                <button className="px-2 py-1 border rounded bg-blue-500 text-white" onClick={handleSaveColumns}>Save</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};