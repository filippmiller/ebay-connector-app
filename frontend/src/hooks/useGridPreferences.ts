import { useCallback, useEffect, useState, useMemo } from 'react';
import api from '@/lib/apiClient';
import type { GridColumnMeta, GridLayoutResponse, GridDataResponse } from '@/components/DataGridPage';

export type GridDensity = 'compact' | 'normal' | 'comfortable';
export type GridFontSize = 'small' | 'medium' | 'large';
export type GridColorScheme = 'default' | 'blue' | 'dark' | 'highContrast';
export type GridHeaderStyle = 'default' | 'bold' | 'accent';
export type GridButtonLayout = 'left' | 'right' | 'split';

export interface GridThemeConfig {
  density: GridDensity;
  /** Legacy body font size preset (small/medium/large). Still used as a fallback. */
  fontSize: GridFontSize;
  headerStyle: GridHeaderStyle;
  colorScheme: GridColorScheme;
  buttonLayout: GridButtonLayout;
  /** Optional custom background color for the grid body (e.g. #ffffff). */
  backgroundColor?: string;
  /** Optional numeric body font size level (1-10). */
  bodyFontSizeLevel?: number;
  /** Optional font weight for body cells. */
  bodyFontWeight?: 'normal' | 'bold';
  /** Optional font style for body cells (normal or italic/cursive). */
  bodyFontStyle?: 'normal' | 'italic';
  /** Optional font size override specifically for column headers. */
  headerFontSize?: GridFontSize;
  /** Optional text color for column headers (e.g. #111827). */
  headerTextColor?: string;
  // Allow forward-compatible flags without tightening the type too much
  [key: string]: unknown;
}

export interface GridSortConfig {
  column: string;
  direction: 'asc' | 'desc';
}

export interface GridColumnsConfig {
  visible: string[];
  order: string[];
  widths: Record<string, number>;
  sort: GridSortConfig | null;
}

export interface GridPreferencesResponse {
  grid_key: string;
  available_columns: GridColumnMeta[];
  columns: GridColumnsConfig;
  theme: GridThemeConfig;
}

interface UseGridPreferencesResult {
  loading: boolean;
  error: string | null;
  availableColumns: GridColumnMeta[];
  columns: GridColumnsConfig | null;
  theme: GridThemeConfig;
  setColumns(partial: Partial<GridColumnsConfig>): void;
  setTheme(partial: Partial<GridThemeConfig>): void;
  /** Persist the current columns + theme (or an override) to the backend. */
  save(columnsOverride?: GridColumnsConfig): Promise<void>;
  /** Reload preferences from the backend, discarding local-only changes. */
  reload(): Promise<void>;
  /** Delete preferences on the server and reload (returns to GRID_DEFAULTS + default theme). */
  clearServerPreferences(): Promise<void>;
}

const DEFAULT_THEME: GridThemeConfig = {
  density: 'normal',
  fontSize: 'medium',
  headerStyle: 'default',
  colorScheme: 'default',
  buttonLayout: 'right',
};

export function useGridPreferences(gridKey: string): UseGridPreferencesResult {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [availableColumns, setAvailableColumns] = useState<GridColumnMeta[]>([]);
  const [columns, setColumnsState] = useState<GridColumnsConfig | null>(null);
  const [theme, setThemeState] = useState<GridThemeConfig>(DEFAULT_THEME);

  const fetchPrefs = useCallback(async (): Promise<void> => {
    console.log(`[useGridPreferences] ${gridKey}: fetchPrefs called, setting loading=true`);
    setLoading(true);
    setError(null);
    try {
      // Primary: new unified grid preferences endpoint
      const resp = await api.get<GridPreferencesResponse>('/api/grid/preferences', {
        params: { grid_key: gridKey },
      });
      const availableCols = resp.data.available_columns || [];
      const colsCfg = resp.data.columns || null;

      // Ensure we have at least some columns
      if (availableCols.length === 0) {
        console.warn(`Grid ${gridKey}: available_columns is empty from /api/grid/preferences`);
        // Don't set error yet - try fallbacks
      } else {
        setAvailableColumns(availableCols);
        setColumnsState(colsCfg);
        setThemeState({ ...DEFAULT_THEME, ...(resp.data.theme || {}) });
        setError(null);
        console.log(`[useGridPreferences] ${gridKey}: SUCCESS - ${availableCols.length} columns loaded`);
        return; // Success, exit early
      }
    } catch (e: any) {
      console.error('Failed to load grid preferences', e);
      // Continue to fallbacks
    }

    // Fallback: try legacy /api/grids/{gridKey}/layout to keep existing grids working
    try {
      const legacyResp = await api.get<GridLayoutResponse>(`/api/grids/${gridKey}/layout`);
      const layout = legacyResp.data;
      const colsMeta = layout.available_columns || [];

      if (colsMeta.length === 0) {
        console.warn(`Grid ${gridKey}: available_columns is empty from legacy layout endpoint`);
        throw new Error('Empty columns from legacy endpoint');
      }

      const allowedNames = colsMeta.map((c) => c.name);
      const visible = (layout.visible_columns || allowedNames).filter((name) => allowedNames.includes(name));
      const colsCfg: GridColumnsConfig = {
        visible,
        order: visible,
        widths: layout.column_widths || {},
        sort: layout.sort || null,
      };
      setAvailableColumns(colsMeta);
      setColumnsState(colsCfg);
      // Legacy layout has no theme concept – use default theme locally
      setThemeState(DEFAULT_THEME);
      setError(null);
      return; // Success, exit early
    } catch (fallbackErr: any) {
      console.error('Fallback to legacy grid layout failed', fallbackErr);

      // Last-resort fallback: try to infer columns from a sample of grid data.
      try {
        const dataResp = await api.get<GridDataResponse>(`/api/grids/${gridKey}/data`, {
          params: { limit: 1, offset: 0 },
        });
        const data = dataResp.data;
        const firstRow = (data.rows && data.rows[0]) || {};
        const keys = Object.keys(firstRow);

        if (keys.length > 0) {
          const colsMeta: GridColumnMeta[] = keys.map((name) => ({
            name,
            label: name,
            type: 'string',
            width_default: 150,
            sortable: true,
          }));
          const colsCfg: GridColumnsConfig = {
            visible: keys,
            order: keys,
            widths: {},
            sort: data.sort || null,
          };
          setAvailableColumns(colsMeta);
          setColumnsState(colsCfg);
          setThemeState(DEFAULT_THEME);
          setError(null);
          return; // Success, exit early
        } else {
          // No data rows - this might be OK if table is empty, but we still need columns
          console.warn(`Grid ${gridKey}: data endpoint returned no rows, cannot infer columns`);
          setError('Grid has no data and no column metadata available');
          setAvailableColumns([]);
          setColumnsState(null);
          setThemeState(DEFAULT_THEME);
        }
      } catch (dataErr: any) {
        console.error('Fallback to sample grid data failed', dataErr);
        const errorMsg = dataErr?.response?.data?.detail || dataErr.message || 'Failed to load grid preferences';
        setError(errorMsg);
        // On error, set empty state but don't block - let DataGridPage handle it
        setAvailableColumns([]);
        setColumnsState(null);
        setThemeState(DEFAULT_THEME);
      }
    } finally {
      console.log(`[useGridPreferences] ${gridKey}: finally block - setting loading=false`);
      setLoading(false);
    }
  }, [gridKey]);

  useEffect(() => {
    void fetchPrefs();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const setColumns = useCallback((partial: Partial<GridColumnsConfig>) => {
    setColumnsState((prev) => {
      const base: GridColumnsConfig = prev || {
        visible: [],
        order: [],
        widths: {},
        sort: null,
      };

      // Start from base and apply partial, but keep order consistent with visible.
      let nextVisible = partial.visible ?? base.visible;
      let nextOrder = partial.order ?? base.order;

      // If visible was updated without an explicit order, drop hidden columns from order
      // while preserving existing relative order for the remaining ones.
      if (partial.visible && !partial.order) {
        const visibleSet = new Set(partial.visible);
        nextOrder = base.order.filter((name) => visibleSet.has(name));
      }

      return {
        ...base,
        ...partial,
        visible: nextVisible,
        order: nextOrder,
      };
    });
  }, []);

  const setTheme = useCallback((partial: Partial<GridThemeConfig>) => {
    setThemeState((prev) => ({ ...prev, ...partial }));
  }, []);

  const save = useCallback(
    async (columnsOverride?: GridColumnsConfig) => {
      if (!columns && !columnsOverride) return;
      const cols = columnsOverride || columns!;
      try {
        await api.post<GridPreferencesResponse>('/api/grid/preferences', {
          grid_key: gridKey,
          columns: cols,
          theme,
        });
      } catch (e) {
        console.error('Failed to save grid preferences', e);
      }
    },
    [columns, gridKey, theme],
  );

  const reload = useCallback(async (): Promise<void> => {
    await fetchPrefs();
  }, [fetchPrefs]);

  const clearServerPreferences = useCallback(async (): Promise<void> => {
    try {
      await api.delete('/api/grid/preferences', { params: { grid_key: gridKey } });
    } catch (e) {
      console.error('Failed to clear grid preferences', e);
    }
    await fetchPrefs();
  }, [fetchPrefs, gridKey]);

  return {
    loading,
    error,
    availableColumns,
    columns,
    theme,
    setColumns,
    setTheme,
    save,
    reload,
    clearServerPreferences,
  };

  // Memoize the return object to prevent infinite re-renders
  // Only create a new object when the actual state values change
  return useMemo(() => {
    // DEBUG: Log what we're actually returning
    console.log(`[useGridPreferences] ${gridKey}: Returning state`, {
      loading,
      availableColumnsCount: availableColumns.length,
      hasColumns: !!columns,
      columnsVisibleCount: columns?.visible.length || 0
    });

    return {
      loading,
      error,
      availableColumns,
      columns,
      theme,
      setColumns,
      setTheme,
      save,
      reload,
      clearServerPreferences,
    };
  }, [loading, error, availableColumns.length, columns?.visible.length]);
}
