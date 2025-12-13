import FixedHeader from '@/components/FixedHeader';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useUITweak } from '@/contexts/UITweakContext';

const normalizeColorForPicker = (value: string) => {
  const trimmed = value.trim();
  // <input type="color"> only accepts full #rrggbb values.
  if (/^#([0-9a-fA-F]{6})$/.test(trimmed)) return trimmed;
  // Fallback to white for non-hex values like "transparent" so the picker still works.
  return '#ffffff';
};

export default function AdminUITweakPage() {
  const { settings, update, reset } = useUITweak();

  const handleNumberChange = (key: 'fontScale' | 'navScale', value: string) => {
    const parsed = Number(value);
    if (!Number.isNaN(parsed) && parsed > 0) {
      update({ [key]: parsed } as any);
    }
  };

  const applyGridDensityPreset = (preset: 'compact' | 'normal' | 'comfortable') => {
    const map = {
      compact: { gridSpacingPx: 4, gridRowHeightPx: 22, gridHeaderHeightPx: 24, gridFontSizePx: 12 },
      normal: { gridSpacingPx: 6, gridRowHeightPx: 28, gridHeaderHeightPx: 30, gridFontSizePx: 12 },
      comfortable: { gridSpacingPx: 10, gridRowHeightPx: 34, gridHeaderHeightPx: 34, gridFontSizePx: 13 },
    } as const;
    const d = map[preset];
    update({ gridDensity: preset as any, ...d } as any);
  };

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      <FixedHeader />
      <div className="pt-16 px-4 py-6 max-w-5xl w-full mx-auto flex-1">
        <h1 className="text-2xl font-bold mb-4">UI Tweak</h1>
        <p className="text-sm text-gray-600 mb-6">
          Adjust global UI scale, navigation size, grid density, and header colors to make the
          application easier to read on your monitor. Changes are applied globally for your
          account (admin-controlled) and take effect for all users after a page refresh.
        </p>

        <div className="grid gap-4 md:grid-cols-2">
          <Card className="p-4 space-y-4">
            <h2 className="text-lg font-semibold">Global scale</h2>
            <div className="space-y-2">
              <label className="block text-xs font-medium text-gray-600">Global font / UI scale</label>
              <input
                type="range"
                min={0.8}
                max={2.0}
                step={0.1}
                value={settings.fontScale}
                onChange={(e) => handleNumberChange('fontScale', e.target.value)}
                className="w-full"
                aria-label="Global font / UI scale"
              />
              <div className="flex items-center justify-between text-xs text-gray-600">
                <span>Smaller</span>
                <span className="font-mono">{settings.fontScale.toFixed(1)}×</span>
                <span>Bigger</span>
              </div>
            </div>

            <div className="space-y-2">
              <label className="block text-xs font-medium text-gray-600">Top navigation size</label>
              <input
                type="range"
                min={1.0}
                max={2.0}
                step={0.1}
                value={settings.navScale}
                onChange={(e) => handleNumberChange('navScale', e.target.value)}
                className="w-full"
                aria-label="Top navigation size"
              />
              <div className="flex items-center justify-between text-xs text-gray-600">
                <span>Current</span>
                <span className="font-mono">{settings.navScale.toFixed(1)}×</span>
                <span>Very large</span>
              </div>
            </div>

            <div className="space-y-2">
              <label className="block text-xs font-medium text-gray-600">Grid density</label>
              <select
                className="border rounded px-2 py-1 text-sm bg-white"
                value={settings.gridDensity}
                onChange={(e) => applyGridDensityPreset(e.target.value as any)}
                aria-label="Grid density"
              >
                <option value="compact">Compact</option>
                <option value="normal">Normal</option>
                <option value="comfortable">Comfortable</option>
              </select>
              <div className="text-[11px] text-gray-500">
                Controls row height, header height, padding (spacing) and base grid font size.
              </div>
            </div>

            <div className="space-y-2">
              <label className="block text-xs font-medium text-gray-600">Grid padding (spacing)</label>
              <input
                type="range"
                min={2}
                max={14}
                step={1}
                value={settings.gridSpacingPx}
                onChange={(e) => update({ gridSpacingPx: Number(e.target.value) } as any)}
                className="w-full"
                aria-label="Grid padding (spacing)"
              />
              <div className="flex items-center justify-between text-xs text-gray-600">
                <span>Tight</span>
                <span className="font-mono">{settings.gridSpacingPx}px</span>
                <span>Loose</span>
              </div>
            </div>

            <div className="space-y-2">
              <label className="block text-xs font-medium text-gray-600">Grid font size</label>
              <input
                type="range"
                min={10}
                max={18}
                step={1}
                value={settings.gridFontSizePx}
                onChange={(e) => update({ gridFontSizePx: Number(e.target.value) } as any)}
                className="w-full"
                aria-label="Grid font size"
              />
              <div className="flex items-center justify-between text-xs text-gray-600">
                <span>Small</span>
                <span className="font-mono">{settings.gridFontSizePx}px</span>
                <span>Large</span>
              </div>
            </div>

            <div className="space-y-2">
              <label className="block text-xs font-medium text-gray-600">Grid row & header heights</label>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <div className="flex items-center justify-between text-[11px] text-gray-600">
                    <span>Row height</span>
                    <span className="font-mono">{settings.gridRowHeightPx}px</span>
                  </div>
                  <input
                    type="range"
                    min={18}
                    max={44}
                    step={1}
                    value={settings.gridRowHeightPx}
                    onChange={(e) => update({ gridRowHeightPx: Number(e.target.value) } as any)}
                    className="w-full"
                    aria-label="Grid row height"
                  />
                </div>
                <div className="space-y-1">
                  <div className="flex items-center justify-between text-[11px] text-gray-600">
                    <span>Header height</span>
                    <span className="font-mono">{settings.gridHeaderHeightPx}px</span>
                  </div>
                  <input
                    type="range"
                    min={18}
                    max={52}
                    step={1}
                    value={settings.gridHeaderHeightPx}
                    onChange={(e) => update({ gridHeaderHeightPx: Number(e.target.value) } as any)}
                    className="w-full"
                    aria-label="Grid header height"
                  />
                </div>
              </div>
            </div>

            <div className="space-y-2">
              <label className="block text-xs font-medium text-gray-600">Grid font family</label>
              <select
                className="border rounded px-2 py-1 text-sm bg-white w-full"
                value={settings.gridFontFamily}
                onChange={(e) => update({ gridFontFamily: e.target.value })}
                aria-label="Grid font family"
              >
                <option value={'"Tahoma","Segoe UI",Arial,sans-serif'}>Tahoma / Segoe UI (Legacy-like)</option>
                <option value={'"Segoe UI",system-ui,-apple-system,BlinkMacSystemFont,"Helvetica Neue",Arial,sans-serif'}>
                  System UI
                </option>
                <option value={'"IBM Plex Sans",system-ui,-apple-system,BlinkMacSystemFont,"Helvetica Neue",Arial,sans-serif'}>
                  IBM Plex Sans
                </option>
              </select>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2">
                <label className="block text-xs font-medium text-gray-600">Grid header weight</label>
                <select
                  className="border rounded px-2 py-1 text-sm bg-white w-full"
                  value={settings.typography?.fontWeight?.tableHeader || 'bold'}
                  onChange={(e) =>
                    update({
                      typography: {
                        ...settings.typography,
                        fontWeight: { ...(settings.typography?.fontWeight || {}), tableHeader: e.target.value as any },
                      },
                    })
                  }
                  aria-label="Grid header font weight"
                >
                  <option value="normal">Normal</option>
                  <option value="medium">Medium</option>
                  <option value="semibold">Semibold</option>
                  <option value="bold">Bold</option>
                </select>
              </div>
              <div className="space-y-2">
                <label className="block text-xs font-medium text-gray-600">Grid cell weight</label>
                <select
                  className="border rounded px-2 py-1 text-sm bg-white w-full"
                  value={settings.typography?.fontWeight?.tableCell || 'medium'}
                  onChange={(e) =>
                    update({
                      typography: {
                        ...settings.typography,
                        fontWeight: { ...(settings.typography?.fontWeight || {}), tableCell: e.target.value as any },
                      },
                    })
                  }
                  aria-label="Grid cell font weight"
                >
                  <option value="normal">Normal</option>
                  <option value="medium">Medium</option>
                  <option value="semibold">Semibold</option>
                  <option value="bold">Bold</option>
                </select>
              </div>
            </div>
          </Card>

          <Card className="p-4 space-y-4">
            <h2 className="text-lg font-semibold">Top menu colors</h2>
            <div className="grid grid-cols-2 gap-4 text-xs">
              <div className="space-y-1">
                <label className="block font-medium text-gray-600">Active background</label>
                <div className="flex items-center gap-2">
                  <input
                    type="color"
                    className="h-8 w-10 rounded border border-gray-200 p-0"
                    value={normalizeColorForPicker(settings.navActiveBg)}
                    onChange={(e) => update({ navActiveBg: e.target.value })}
                    aria-label="Nav active background color"
                  />
                  <Input
                    type="text"
                    value={settings.navActiveBg}
                    onChange={(e) => update({ navActiveBg: e.target.value })}
                    className="text-xs flex-1"
                  />
                </div>
              </div>
              <div className="space-y-1">
                <label className="block font-medium text-gray-600">Active text</label>
                <div className="flex items-center gap-2">
                  <input
                    type="color"
                    className="h-8 w-10 rounded border border-gray-200 p-0"
                    value={normalizeColorForPicker(settings.navActiveText)}
                    onChange={(e) => update({ navActiveText: e.target.value })}
                    aria-label="Nav active text color"
                  />
                  <Input
                    type="text"
                    value={settings.navActiveText}
                    onChange={(e) => update({ navActiveText: e.target.value })}
                    className="text-xs flex-1"
                  />
                </div>
              </div>
              <div className="space-y-1">
                <label className="block font-medium text-gray-600">Inactive background</label>
                <div className="flex items-center gap-2">
                  <input
                    type="color"
                    className="h-8 w-10 rounded border border-gray-200 p-0"
                    value={normalizeColorForPicker(settings.navInactiveBg)}
                    onChange={(e) => update({ navInactiveBg: e.target.value })}
                    aria-label="Nav inactive background color"
                  />
                  <Input
                    type="text"
                    value={settings.navInactiveBg}
                    onChange={(e) => update({ navInactiveBg: e.target.value })}
                    className="text-xs flex-1"
                  />
                </div>
              </div>
              <div className="space-y-1">
                <label className="block font-medium text-gray-600">Inactive text</label>
                <div className="flex items-center gap-2">
                  <input
                    type="color"
                    className="h-8 w-10 rounded border border-gray-200 p-0"
                    value={normalizeColorForPicker(settings.navInactiveText)}
                    onChange={(e) => update({ navInactiveText: e.target.value })}
                    aria-label="Nav inactive text color"
                  />
                  <Input
                    type="text"
                    value={settings.navInactiveText}
                    onChange={(e) => update({ navInactiveText: e.target.value })}
                    className="text-xs flex-1"
                  />
                </div>
              </div>
            </div>

            <div className="pt-2 border-t mt-4 flex items-center justify-between gap-2">
              <div className="text-xs text-gray-500">
                You can paste any valid CSS color here (e.g. #2563eb, rgb(37,99,235), or blue).
              </div>
              <Button variant="outline" size="sm" onClick={reset}>
                Reset to defaults
              </Button>
            </div>
          </Card>
        </div>

        <Card className="mt-4 p-4 space-y-4">
          <h2 className="text-lg font-semibold">Data grid theme</h2>
          <div className="grid grid-cols-2 gap-4 text-xs">
            <div className="space-y-1">
              <label className="block font-medium text-gray-600">Header background</label>
              <div className="flex items-center gap-2">
                <input
                  type="color"
                  className="h-8 w-10 rounded border border-gray-200 p-0"
                  value={normalizeColorForPicker(settings.gridTheme.headerBg)}
                  onChange={(e) => update({ gridTheme: { ...settings.gridTheme, headerBg: e.target.value } })}
                  aria-label="Grid header background color"
                />
                <Input
                  type="text"
                  value={settings.gridTheme.headerBg}
                  onChange={(e) => update({ gridTheme: { ...settings.gridTheme, headerBg: e.target.value } })}
                  className="text-xs flex-1"
                />
              </div>
            </div>
            <div className="space-y-1">
              <label className="block font-medium text-gray-600">Header text</label>
              <div className="flex items-center gap-2">
                <input
                  type="color"
                  className="h-8 w-10 rounded border border-gray-200 p-0"
                  value={normalizeColorForPicker(settings.gridTheme.headerText)}
                  onChange={(e) => update({ gridTheme: { ...settings.gridTheme, headerText: e.target.value } })}
                  aria-label="Grid header text color"
                />
                <Input
                  type="text"
                  value={settings.gridTheme.headerText}
                  onChange={(e) => update({ gridTheme: { ...settings.gridTheme, headerText: e.target.value } })}
                  className="text-xs flex-1"
                />
              </div>
            </div>
            <div className="space-y-1">
              <label className="block font-medium text-gray-600">Row background</label>
              <div className="flex items-center gap-2">
                <input
                  type="color"
                  className="h-8 w-10 rounded border border-gray-200 p-0"
                  value={normalizeColorForPicker(settings.gridTheme.rowBg)}
                  onChange={(e) => update({ gridTheme: { ...settings.gridTheme, rowBg: e.target.value } })}
                  aria-label="Grid row background color"
                />
                <Input
                  type="text"
                  value={settings.gridTheme.rowBg}
                  onChange={(e) => update({ gridTheme: { ...settings.gridTheme, rowBg: e.target.value } })}
                  className="text-xs flex-1"
                />
              </div>
            </div>
            <div className="space-y-1">
              <label className="block font-medium text-gray-600">Alternate row background</label>
              <div className="flex items-center gap-2">
                <input
                  type="color"
                  className="h-8 w-10 rounded border border-gray-200 p-0"
                  value={normalizeColorForPicker(settings.gridTheme.rowAltBg)}
                  onChange={(e) => update({ gridTheme: { ...settings.gridTheme, rowAltBg: e.target.value } })}
                  aria-label="Grid alternate row background color"
                />
                <Input
                  type="text"
                  value={settings.gridTheme.rowAltBg}
                  onChange={(e) => update({ gridTheme: { ...settings.gridTheme, rowAltBg: e.target.value } })}
                  className="text-xs flex-1"
                />
              </div>
            </div>
            <div className="space-y-1">
              <label className="block font-medium text-gray-600">Row hover background</label>
              <div className="flex items-center gap-2">
                <input
                  type="color"
                  className="h-8 w-10 rounded border border-gray-200 p-0"
                  value={normalizeColorForPicker(settings.gridTheme.rowHoverBg)}
                  onChange={(e) => update({ gridTheme: { ...settings.gridTheme, rowHoverBg: e.target.value } })}
                  aria-label="Grid row hover background color"
                />
                <Input
                  type="text"
                  value={settings.gridTheme.rowHoverBg}
                  onChange={(e) => update({ gridTheme: { ...settings.gridTheme, rowHoverBg: e.target.value } })}
                  className="text-xs flex-1"
                />
              </div>
            </div>
            <div className="space-y-1">
              <label className="block font-medium text-gray-600">Selected row background</label>
              <div className="flex items-center gap-2">
                <input
                  type="color"
                  className="h-8 w-10 rounded border border-gray-200 p-0"
                  value={normalizeColorForPicker(settings.gridTheme.rowSelectedBg)}
                  onChange={(e) => update({ gridTheme: { ...settings.gridTheme, rowSelectedBg: e.target.value } })}
                  aria-label="Grid selected row background color"
                />
                <Input
                  type="text"
                  value={settings.gridTheme.rowSelectedBg}
                  onChange={(e) => update({ gridTheme: { ...settings.gridTheme, rowSelectedBg: e.target.value } })}
                  className="text-xs flex-1"
                />
              </div>
            </div>
          </div>
        </Card>

        <Card className="mt-4 p-4 text-sm text-gray-600 space-y-2">
          <h2 className="text-base font-semibold">How this works</h2>
          <p>
            UITweak controls a few CSS variables on the &lt;html&gt; element: the base font size, a global
            scale factor, navigation scale, and grid density. Because Tailwind uses rem units,
            increasing the global scale makes almost everything (text, buttons, tabs) larger.
          </p>
        </Card>
      </div>
    </div>
  );
}
