import { themeQuartz } from 'ag-grid-community';

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