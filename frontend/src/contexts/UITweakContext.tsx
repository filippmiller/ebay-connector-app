import React, { createContext, useContext, useEffect, useMemo, useState } from 'react';

export type GridDensityPreset = 'compact' | 'normal' | 'comfortable';

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
}

export const DEFAULT_UI_TWEAK: UITweakSettings = {
  fontScale: 1,
  navScale: 1,
  gridDensity: 'normal',
  navActiveBg: '#2563eb', // blue-600
  navActiveText: '#ffffff',
  navInactiveBg: 'transparent',
  navInactiveText: '#374151', // gray-700
};

const STORAGE_KEY = 'ui_tweak_v1';

interface UITweakContextValue {
  settings: UITweakSettings;
  update(partial: Partial<UITweakSettings>): void;
  reset(): void;
}

const UITweakContext = createContext<UITweakContextValue | undefined>(undefined);

function applySettingsToDocument(settings: UITweakSettings) {
  if (typeof document === 'undefined') return;
  const root = document.documentElement;

  root.style.setProperty('--ui-font-scale', String(settings.fontScale));
  root.style.setProperty('--ui-nav-scale', String(settings.navScale));

  root.style.setProperty('--ui-nav-active-bg', settings.navActiveBg);
  root.style.setProperty('--ui-nav-active-text', settings.navActiveText);
  root.style.setProperty('--ui-nav-inactive-bg', settings.navInactiveBg);
  root.style.setProperty('--ui-nav-inactive-text', settings.navInactiveText);

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
}

function loadInitialSettings(): UITweakSettings {
  if (typeof window === 'undefined') return DEFAULT_UI_TWEAK;

  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_UI_TWEAK;
    const parsed = JSON.parse(raw) as Partial<UITweakSettings>;
    return { ...DEFAULT_UI_TWEAK, ...parsed };
  } catch (e) {
    console.error('Failed to parse UITweak settings from localStorage', e);
    return DEFAULT_UI_TWEAK;
  }
}

export const UITweakProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [settings, setSettings] = useState<UITweakSettings>(() => loadInitialSettings());

  // Apply on mount + whenever settings change
  useEffect(() => {
    applySettingsToDocument(settings);
    try {
      if (typeof window !== 'undefined') {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
      }
    } catch (e) {
      console.error('Failed to persist UITweak settings', e);
    }
  }, [settings]);

  const value = useMemo<UITweakContextValue>(
    () => ({
      settings,
      update(partial) {
        setSettings((prev) => ({ ...prev, ...partial }));
      },
      reset() {
        setSettings(DEFAULT_UI_TWEAK);
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
