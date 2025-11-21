import { useCallback, useEffect, useState } from 'react';
import api from '@/lib/apiClient';
import type { GridColumnMeta, GridLayoutResponse, GridDataResponse } from '@/components/DataGridPage';

export type GridDensity = 'compact' | 'normal' | 'comfortable';
export type GridFontSize = 'small' | 'medium' | 'large';
export type GridColorScheme = 'default' | 'blue' | 'dark' | 'highContrast';
export type GridHeaderStyle = 'default' | 'bold' | 'accent';
export type GridButtonLayout = 'left' | 'right' | 'split';

export interface GridThemeConfig {
  density: GridDensity;
  fontSize: GridFontSize;
  headerStyle: GridHeaderStyle;
  colorScheme: GridColorScheme;
  buttonLayout: GridButtonLayout;
  /** Optional custom background color for the grid body (e.g. #ffffff). */
  backgroundColor?: string;
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
    setLoading(true);
    setError(null);
    try {
      // Primary: new unified grid preferences endpoint
      const resp = await api.get<GridPreferencesResponse>('/api/grid/preferences', {
        params: { grid_key: gridKey },
      });
      setAvailableColumns(resp.data.available_columns || []);
      setColumnsState(resp.data.columns || null);
      setThemeState({ ...DEFAULT_THEME, ...(resp.data.theme || {}) });
    } catch (e: any) {
      console.error('Failed to load grid preferences', e);

      // Fallback: try legacy /api/grids/{gridKey}/layout to keep existing grids working
      try {
        const legacyResp = await api.get<GridLayoutResponse>(`/api/grids/${gridKey}/layout`);
        const layout = legacyResp.data;
        const colsMeta = layout.available_columns || [];
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
          } else {
            setError(e?.response?.data?.detail || e.message || 'Failed to load grid preferences');
            setAvailableColumns([]);
            setColumnsState(null);
            setThemeState(DEFAULT_THEME);
          }
        } catch (dataErr: any) {
          console.error('Fallback to sample grid data failed', dataErr);
          setError(e?.response?.data?.detail || e.message || 'Failed to load grid preferences');
          // On error, fall back to defaults but keep going so the grid still renders.
          setAvailableColumns([]);
          setColumnsState(null);
          setThemeState(DEFAULT_THEME);
        }
      }
    } finally {
      setLoading(false);
    }
  }, [gridKey]);

  useEffect(() => {
    void fetchPrefs();
  }, [fetchPrefs]);

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
}
