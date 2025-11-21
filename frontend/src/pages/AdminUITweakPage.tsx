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

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      <FixedHeader />
      <div className="pt-16 px-4 py-6 max-w-5xl w-full mx-auto flex-1">
        <h1 className="text-2xl font-bold mb-4">UI Tweak</h1>
        <p className="text-sm text-gray-600 mb-6">
          Adjust global UI scale, navigation size, grid density, and header colors to make the
          application easier to read on your monitor. Changes are saved in this browser only and
          take effect immediately.
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
                onChange={(e) => update({ gridDensity: e.target.value as any })}
              >
                <option value="compact">Compact</option>
                <option value="normal">Normal</option>
                <option value="comfortable">Comfortable</option>
              </select>
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
