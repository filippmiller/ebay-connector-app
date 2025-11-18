import { useCallback, useEffect, useState } from 'react';
import api from '@/lib/apiClient';
import type { GridColumnMeta, GridLayoutResponse } from '@/components/DataGridPage';

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
        setError(e?.response?.data?.detail || e.message || 'Failed to load grid preferences');
        // On error, fall back to defaults but keep going so the grid still renders.
        setAvailableColumns([]);
        setColumnsState(null);
        setThemeState(DEFAULT_THEME);
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
      return { ...base, ...partial };
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
