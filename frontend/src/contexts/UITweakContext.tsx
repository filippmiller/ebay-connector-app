import React, { createContext, useContext, useEffect, useMemo, useState } from 'react';
import api from '@/lib/apiClient';

export type GridDensityPreset = 'compact' | 'normal' | 'comfortable';

export type UiTypographyRole =
  | 'pageTitle'
  | 'sectionTitle'
  | 'fieldLabel'
  | 'microLabel'
  | 'tableHeader'
  | 'tableCell'
  | 'buttonText';

export type UiFontWeight = 'normal' | 'medium' | 'semibold' | 'bold';

export interface UiTypographySettings {
  /** Per-role font scale multiplier on top of the global fontScale. */
  fontScale: Record<UiTypographyRole, number>;
  /** Optional per-role font weight overrides. */
  fontWeight: Partial<Record<UiTypographyRole, UiFontWeight>>;
  /** Micro-label presentation options. */
  microLabelUppercase: boolean;
  microLabelItalic: boolean;
}

export interface UiColorSettings {
  textPrimary: string;
  textSecondary: string;
  textMuted: string;
  textHeading: string;
  textLink: string;
  buttonPrimaryBg: string;
  buttonPrimaryText: string;
  buttonSecondaryBg: string;
  buttonSecondaryText: string;
}

export interface UiControlSizeSettings {
  /** Extra multiplier for button & input vertical padding/height, on top of global fontScale. */
  buttonAndInputScale: number; // e.g. 0.8–1.4
}

export interface UiGridThemeSettings {
  headerBg: string;
  headerText: string;
  rowBg: string;
  rowAltBg: string;
  rowHoverBg: string;
  rowSelectedBg: string;
}

export interface UITweakSettings {
  /** Global multiplier for root font size; affects all rem-based Tailwind sizing. */
  fontScale: number; // e.g. 0.8 – 2.0
  /** Additional scale factor for top navigation tabs and tab headers. */
  navScale: number; // e.g. 0.8 – 2.0
  /** Optional global grid density preset mapped to CSS vars. */
  gridDensity: GridDensityPreset;
  /** Colors for top nav active/inactive states (CSS color strings). */
  navActiveBg: string;
  navActiveText: string;
  navInactiveBg: string;
  navInactiveText: string;

  /** Fine-grained typography controls for dense forms & tables. */
  typography: UiTypographySettings;
  /** Global text + button color roles (separate from nav colors). */
  colors: UiColorSettings;
  /** Extra control over button/input sizing. */
  controls: UiControlSizeSettings;
  /** Global default grid theme (header/row colors). */
  gridTheme: UiGridThemeSettings;
}

const DEFAULT_TYPOGRAPHY: UiTypographySettings = {
  fontScale: {
    pageTitle: 1,
    sectionTitle: 1,
    fieldLabel: 1,
    microLabel: 1,
    tableHeader: 1,
    tableCell: 1,
    buttonText: 1,
  },
  fontWeight: {
    pageTitle: 'bold',
    sectionTitle: 'semibold',
    fieldLabel: 'medium',
    tableHeader: 'medium',
    tableCell: 'normal',
    buttonText: 'medium',
  },
  microLabelUppercase: false,
  microLabelItalic: false,
};

const DEFAULT_COLORS: UiColorSettings = {
  // Roughly match Tailwind gray palette & current design.
  textPrimary: '#111827', // gray-900
  textSecondary: '#374151', // gray-700
  textMuted: '#6b7280', // gray-500
  textHeading: '#111827',
  textLink: '#2563eb', // blue-600
  buttonPrimaryBg: '#18181b', // zinc-900 (default button)
  buttonPrimaryText: '#f9fafb', // gray-50
  buttonSecondaryBg: '#e5e7eb', // gray-200
  buttonSecondaryText: '#111827',
};

const DEFAULT_CONTROLS: UiControlSizeSettings = {
  buttonAndInputScale: 1,
};

const DEFAULT_GRID_THEME: UiGridThemeSettings = {
  headerBg: '#f3f4f6', // gray-100
  headerText: '#4b5563', // gray-600
  rowBg: '#ffffff',
  rowAltBg: '#f9fafb', // gray-50
  rowHoverBg: '#eef2ff', // indigo-50
  rowSelectedBg: '#e0f2fe', // sky-100
};

export const DEFAULT_UI_TWEAK: UITweakSettings = {
  fontScale: 1,
  navScale: 1,
  gridDensity: 'normal',
  navActiveBg: '#2563eb', // blue-600
  navActiveText: '#ffffff',
  navInactiveBg: 'transparent',
  navInactiveText: '#374151', // gray-700
  typography: DEFAULT_TYPOGRAPHY,
  colors: DEFAULT_COLORS,
  controls: DEFAULT_CONTROLS,
  gridTheme: DEFAULT_GRID_THEME,
};

const STORAGE_KEY = 'ui_tweak_v1';

interface UITweakContextValue {
  settings: UITweakSettings;
  update(partial: Partial<UITweakSettings>): void;
  reset(): void;
}

const UITweakContext = createContext<UITweakContextValue | undefined>(undefined);

const FONT_WEIGHT_MAP: Record<UiFontWeight, string> = {
  normal: '400',
  medium: '500',
  semibold: '600',
  bold: '700',
};

function applySettingsToDocument(settings: UITweakSettings) {
  if (typeof document === 'undefined') return;
  const root = document.documentElement;

  // Global scale + nav
  root.style.setProperty('--ui-font-scale', String(settings.fontScale));
  root.style.setProperty('--ui-nav-scale', String(settings.navScale));

  // Nav colors
  root.style.setProperty('--ui-nav-active-bg', settings.navActiveBg);
  root.style.setProperty('--ui-nav-active-text', settings.navActiveText);
  root.style.setProperty('--ui-nav-inactive-bg', settings.navInactiveBg);
  root.style.setProperty('--ui-nav-inactive-text', settings.navInactiveText);

  // Typography roles
  const t = settings.typography;
  const fs = t.fontScale;
  const fw = t.fontWeight;

  root.style.setProperty('--ui-font-scale-page-title', String(fs.pageTitle ?? 1));
  root.style.setProperty('--ui-font-scale-section-title', String(fs.sectionTitle ?? 1));
  root.style.setProperty('--ui-font-scale-field-label', String(fs.fieldLabel ?? 1));
  root.style.setProperty('--ui-font-scale-micro-label', String(fs.microLabel ?? 1));
  root.style.setProperty('--ui-font-scale-table-header', String(fs.tableHeader ?? 1));
  root.style.setProperty('--ui-font-scale-table-cell', String(fs.tableCell ?? 1));
  root.style.setProperty('--ui-font-scale-button-text', String(fs.buttonText ?? 1));

  const pageTitleWeight = fw.pageTitle ?? DEFAULT_TYPOGRAPHY.fontWeight.pageTitle ?? 'bold';
  const sectionTitleWeight = fw.sectionTitle ?? DEFAULT_TYPOGRAPHY.fontWeight.sectionTitle ?? 'semibold';
  const fieldLabelWeight = fw.fieldLabel ?? DEFAULT_TYPOGRAPHY.fontWeight.fieldLabel ?? 'medium';
  const tableHeaderWeight = fw.tableHeader ?? DEFAULT_TYPOGRAPHY.fontWeight.tableHeader ?? 'medium';
  const tableCellWeight = fw.tableCell ?? DEFAULT_TYPOGRAPHY.fontWeight.tableCell ?? 'normal';
  const buttonTextWeight = fw.buttonText ?? DEFAULT_TYPOGRAPHY.fontWeight.buttonText ?? 'medium';

  root.style.setProperty('--ui-font-weight-page-title', FONT_WEIGHT_MAP[pageTitleWeight]);
  root.style.setProperty('--ui-font-weight-section-title', FONT_WEIGHT_MAP[sectionTitleWeight]);
  root.style.setProperty('--ui-font-weight-field-label', FONT_WEIGHT_MAP[fieldLabelWeight]);
  root.style.setProperty('--ui-font-weight-table-header', FONT_WEIGHT_MAP[tableHeaderWeight]);
  root.style.setProperty('--ui-font-weight-table-cell', FONT_WEIGHT_MAP[tableCellWeight]);
  root.style.setProperty('--ui-font-weight-button-text', FONT_WEIGHT_MAP[buttonTextWeight]);

  root.style.setProperty('--ui-micro-label-transform', t.microLabelUppercase ? 'uppercase' : 'none');
  root.style.setProperty('--ui-micro-label-style', t.microLabelItalic ? 'italic' : 'normal');

  // Text colors
  const c = settings.colors;
  root.style.setProperty('--ui-color-text-primary', c.textPrimary);
  root.style.setProperty('--ui-color-text-secondary', c.textSecondary);
  root.style.setProperty('--ui-color-text-muted', c.textMuted);
  root.style.setProperty('--ui-color-text-heading', c.textHeading);
  root.style.setProperty('--ui-color-text-link', c.textLink);

  // Button colors
  root.style.setProperty('--ui-color-button-primary-bg', c.buttonPrimaryBg);
  root.style.setProperty('--ui-color-button-primary-text', c.buttonPrimaryText);
  root.style.setProperty('--ui-color-button-secondary-bg', c.buttonSecondaryBg);
  root.style.setProperty('--ui-color-button-secondary-text', c.buttonSecondaryText);

  // Controls size
  root.style.setProperty('--ui-scale-button-input', String(settings.controls.buttonAndInputScale));

  // Map grid density to base CSS custom properties used by .app-grid.
  // These values are chosen to roughly match the existing density presets.
  if (settings.gridDensity === 'compact') {
    root.style.setProperty('--grid-row-height', '24px');
    root.style.setProperty('--grid-header-height', '26px');
    root.style.setProperty('--grid-font-size', '11px');
  } else if (settings.gridDensity === 'comfortable') {
    root.style.setProperty('--grid-row-height', '40px');
    root.style.setProperty('--grid-header-height', '40px');
    root.style.setProperty('--grid-font-size', '14px');
  } else {
    root.style.setProperty('--grid-row-height', '32px');
    root.style.setProperty('--grid-header-height', '32px');
    root.style.setProperty('--grid-font-size', '13px');
  }

  // Grid theme colors
  const g = settings.gridTheme;
  root.style.setProperty('--grid-header-bg', g.headerBg);
  root.style.setProperty('--grid-header-text-color', g.headerText);
  root.style.setProperty('--grid-row-hover-bg', g.rowHoverBg);
  root.style.setProperty('--grid-row-selected-bg', g.rowSelectedBg);
  root.style.setProperty('--grid-row-bg', g.rowBg);
  root.style.setProperty('--grid-row-alt-bg', g.rowAltBg);
}

function mergeSettings(base: UITweakSettings, partial?: Partial<UITweakSettings> | null): UITweakSettings {
  if (!partial) return base;

  const next: UITweakSettings = {
    ...base,
    ...partial,
    typography: {
      ...base.typography,
      ...(partial.typography || {}),
      fontScale: {
        ...base.typography.fontScale,
        ...(partial.typography?.fontScale || {}),
      },
      fontWeight: {
        ...base.typography.fontWeight,
        ...(partial.typography?.fontWeight || {}),
      },
    },
    colors: {
      ...base.colors,
      ...(partial.colors || {}),
    },
    controls: {
      ...base.controls,
      ...(partial.controls || {}),
    },
  };

  return next;
}

function loadInitialSettings(): UITweakSettings {
  if (typeof window === 'undefined') return DEFAULT_UI_TWEAK;

  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_UI_TWEAK;
    const parsed = JSON.parse(raw) as Partial<UITweakSettings>;
    return mergeSettings(DEFAULT_UI_TWEAK, parsed);
  } catch (e) {
    console.error('Failed to parse UITweak settings from localStorage', e);
    return DEFAULT_UI_TWEAK;
  }
}

async function fetchServerSettings(): Promise<UITweakSettings | null> {
  try {
    const resp = await api.get<UITweakSettings>('/api/ui-tweak');
    return mergeSettings(DEFAULT_UI_TWEAK, resp.data);
  } catch (e) {
    console.error('Failed to load UITweak settings from backend', e);
    return null;
  }
}

async function persistServerSettings(next: UITweakSettings): Promise<void> {
  try {
    await api.put<UITweakSettings>('/api/admin/ui-tweak', next);
  } catch (e) {
    // Non-admin users will typically receive 403 here; this is expected.
    console.warn('Failed to persist UITweak settings to backend (likely non-admin user)', e);
  }
}

export const UITweakProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [settings, setSettings] = useState<UITweakSettings>(() => loadInitialSettings());

  // On mount, reconcile local cache with server-backed settings.
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const server = await fetchServerSettings();
      if (!cancelled && server) {
        setSettings(server);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Apply on mount + whenever settings change, and keep localStorage cache in sync.
  useEffect(() => {
    applySettingsToDocument(settings);
    try {
      if (typeof window !== 'undefined') {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
      }
    } catch (e) {
      console.error('Failed to persist UITweak settings to localStorage', e);
    }
  }, [settings]);

  const value = useMemo<UITweakContextValue>(
    () => ({
      settings,
      update(partial) {
        setSettings((prev) => {
          const next = mergeSettings(prev, partial);
          void persistServerSettings(next);
          return next;
        });
      },
      reset() {
        const next = DEFAULT_UI_TWEAK;
        setSettings(next);
        void persistServerSettings(next);
      },
    }),
    [settings],
  );

  return <UITweakContext.Provider value={value}>{children}</UITweakContext.Provider>;
};

export function useUITweak(): UITweakContextValue {
  const ctx = useContext(UITweakContext);
  if (!ctx) {
    throw new Error('useUITweak must be used within a UITweakProvider');
  }
  return ctx;
}
