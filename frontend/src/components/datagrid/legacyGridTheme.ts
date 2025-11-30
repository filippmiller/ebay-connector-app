import { themeQuartz } from 'ag-grid-community';
import type { GridThemeConfig } from '@/hooks/useGridPreferences';

// Legacy-style dense AG Grid theme inspired by the Windows desktop inventory grid.
// Compact rows, small font, clear borders, and subtle zebra + selection colors.
export const legacyGridTheme = themeQuartz.withParams({
  // Typography
  fontFamily:
    'Tahoma, "Segoe UI", system-ui, -apple-system, BlinkMacSystemFont, sans-serif',
  fontSize: 11,
  headerFontSize: 11,

  // Layout / density
  rowHeight: 22,
  headerHeight: 24,
  spacing: 2,

  // Base colors
  backgroundColor: '#ffffff',
  foregroundColor: '#111111',

  // Header styling
  headerBackgroundColor: '#f0f0f0',
  headerTextColor: '#111111',

  // Grid lines
  borderColor: '#d0d0d0',

  // Row backgrounds
  oddRowBackgroundColor: '#fafafa',
  rowHoverColor: '#f5f5ff',
  selectedRowBackgroundColor: '#fff8c5',
});

/**
 * Build a dynamic AG Grid theme variant from per-grid theme config.
 *
 * This keeps the compact legacy defaults but lets density, fontSize and
 * colorScheme influence row heights, font sizes and header colors.
 */
export function buildLegacyGridTheme(themeConfig: GridThemeConfig | null | undefined) {
  const cfg = themeConfig ?? {
    density: 'normal',
    fontSize: 'medium',
    headerStyle: 'default',
    colorScheme: 'default',
    buttonLayout: 'right',
  };

  // Map density to row / header heights
  let rowHeight = 22;
  let headerHeight = 24;
  if (cfg.density === 'compact') {
    rowHeight = 20;
    headerHeight = 22;
  } else if (cfg.density === 'comfortable') {
    rowHeight = 26;
    headerHeight = 28;
  }

  // Map fontSize preset to base font sizes
  let fontSize = 11;
  let headerFontSize = 11;
  if (cfg.fontSize === 'small') {
    fontSize = 10;
    headerFontSize = 10;
  } else if (cfg.fontSize === 'large') {
    fontSize = 12;
    headerFontSize = 12;
  }

  // Map colorScheme to header / selection colors
  let headerBackgroundColor = '#f0f0f0';
  let headerTextColor = '#111111';
  let selectedRowBackgroundColor = '#fff8c5';
  if (cfg.colorScheme === 'blue') {
    headerBackgroundColor = '#e0f2fe';
    headerTextColor = '#1d4ed8';
  } else if (cfg.colorScheme === 'dark') {
    headerBackgroundColor = '#111827';
    headerTextColor = '#e5e7eb';
    selectedRowBackgroundColor = '#1f2937';
  } else if (cfg.colorScheme === 'highContrast') {
    headerBackgroundColor = '#000000';
    headerTextColor = '#ffffff';
  }

  return themeQuartz.withParams({
    fontFamily:
      'Tahoma, "Segoe UI", system-ui, -apple-system, BlinkMacSystemFont, sans-serif',
    fontSize,
    headerFontSize,
    rowHeight,
    headerHeight,
    spacing: 2,
    backgroundColor: '#ffffff',
    foregroundColor: '#111111',
    headerBackgroundColor,
    headerTextColor,
    borderColor: '#d0d0d0',
    oddRowBackgroundColor: '#fafafa',
    rowHoverColor: '#f5f5ff',
    selectedRowBackgroundColor,
  });
}
