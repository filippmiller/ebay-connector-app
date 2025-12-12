import { useCallback, useEffect, useState } from 'react';
import {
  getWatches,
  createWatch,
  updateWatch,
  deleteWatch,
  runWatchOnce,
  EbaySearchWatchBase,
  EbaySearchWatchResponse,
  RunOnceListing,
} from '@/api/ebaySearchWatches';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';

interface EditState extends Partial<EbaySearchWatchBase> {
  id?: string;
}

const DEFAULT_STATE: EditState = {
  name: '',
  keywords: '',
  max_total_price: undefined,
  category_hint: 'laptop',
  exclude_keywords: [],
  check_interval_sec: 60,
  enabled: true,
  notification_mode: 'task',
};

export const EbayRulesTab: React.FC = () => {
  const [watches, setWatches] = useState<EbaySearchWatchResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [editing, setEditing] = useState<EditState | null>(null);
  const [saving, setSaving] = useState(false);

  const [preview, setPreview] = useState<RunOnceListing[] | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getWatches();
      setWatches(data);
    } catch (e: any) {
      setError(e.message ?? String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const startCreate = () => {
    setEditing({ ...DEFAULT_STATE });
  };

  const startEdit = (w: EbaySearchWatchResponse) => {
    setEditing({
      id: w.id,
      name: w.name,
      keywords: w.keywords,
      max_total_price: w.max_total_price,
      category_hint: w.category_hint ?? 'laptop',
      exclude_keywords: w.exclude_keywords ?? [],
      check_interval_sec: w.check_interval_sec ?? 60,
      enabled: w.enabled,
      notification_mode: w.notification_mode ?? 'task',
    });
  };

  const handleSave = async () => {
    if (!editing) return;
    if (!editing.name?.trim() || !editing.keywords?.trim()) {
      setError('Название и ключевые слова обязательны');
      return;
    }

    setSaving(true);
    setError(null);
    try {
      const payload: EbaySearchWatchBase = {
        name: editing.name.trim(),
        keywords: editing.keywords.trim(),
        max_total_price: editing.max_total_price,
        category_hint: editing.category_hint ?? 'laptop',
        exclude_keywords: (editing.exclude_keywords ?? []).filter(Boolean),
        check_interval_sec: editing.check_interval_sec ?? 60,
        enabled: editing.enabled ?? true,
        notification_mode: editing.notification_mode ?? 'task',
      };

      let saved: EbaySearchWatchResponse;
      if (editing.id) {
        saved = await updateWatch(editing.id, payload);
      } else {
        saved = await createWatch(payload);
      }

      setEditing(null);
      setWatches((prev) => {
        const idx = prev.findIndex((x) => x.id === saved.id);
        if (idx === -1) return [saved, ...prev];
        const copy = [...prev];
        copy[idx] = saved;
        return copy;
      });
    } catch (e: any) {
      setError(e.message ?? String(e));
    } finally {
      setSaving(false);
    }
  };

  const handleToggleEnabled = async (w: EbaySearchWatchResponse) => {
    try {
      const updated = await updateWatch(w.id, { enabled: !w.enabled });
      setWatches((prev) => prev.map((x) => (x.id === w.id ? updated : x)));
    } catch (e: any) {
      setError(e.message ?? String(e));
    }
  };

  const handleDelete = async (w: EbaySearchWatchResponse) => {
    if (!window.confirm('Удалить это правило?')) return;
    try {
      await deleteWatch(w.id);
      setWatches((prev) => prev.filter((x) => x.id !== w.id));
    } catch (e: any) {
      setError(e.message ?? String(e));
    }
  };

  const handleRunOnce = async (w: EbaySearchWatchResponse) => {
    try {
      setPreviewError(null);
      const res = await runWatchOnce(w.id);
      setPreview(res);
    } catch (e: any) {
      setPreviewError(e.message ?? String(e));
      setPreview([]);
    }
  };

  return (
    <div className="flex flex-col gap-4 h-full">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Button size="sm" onClick={startCreate}>
            Создать правило
          </Button>
          {error && <span className="text-xs text-red-600">{error}</span>}
        </div>
      </div>

      <div className="flex-1 min-h-0 border rounded bg-white overflow-auto text-xs">
        {loading ? (
          <div className="p-4 text-gray-500">Загрузка правил…</div>
        ) : watches.length === 0 ? (
          <div className="p-4 text-gray-500">Правил пока нет. Создайте первое правило авто-поиска.</div>
        ) : (
          <table className="min-w-full text-left border-collapse">
            <thead className="bg-gray-100 text-[11px] uppercase tracking-wide text-gray-600">
              <tr>
                <th className="px-3 py-2 border-b">Название</th>
                <th className="px-3 py-2 border-b">Ключевые слова</th>
                <th className="px-3 py-2 border-b">Только ноутбуки</th>
                <th className="px-3 py-2 border-b">Макс. цена</th>
                <th className="px-3 py-2 border-b">Интервал (сек)</th>
                <th className="px-3 py-2 border-b">Вкл.</th>
                <th className="px-3 py-2 border-b">Последняя проверка</th>
                <th className="px-3 py-2 border-b">Действия</th>
              </tr>
            </thead>
            <tbody>
              {watches.map((w) => (
                <tr key={w.id} className="hover:bg-gray-50">
                  <td className="px-3 py-2 border-b align-top max-w-xs">
                    <div className="font-semibold text-gray-800 truncate" title={w.name}>
                      {w.name}
                    </div>
                  </td>
                  <td className="px-3 py-2 border-b align-top max-w-xs">
                    <div className="truncate" title={w.keywords}>
                      {w.keywords}
                    </div>
                  </td>
                  <td className="px-3 py-2 border-b align-top whitespace-nowrap">
                    {w.category_hint === 'laptop' ? 'Да' : 'Нет'}
                  </td>
                  <td className="px-3 py-2 border-b align-top whitespace-nowrap">
                    {w.max_total_price != null ? w.max_total_price.toFixed(2) : '—'}
                  </td>
                  <td className="px-3 py-2 border-b align-top whitespace-nowrap">
                    {w.check_interval_sec ?? 60}
                  </td>
                  <td className="px-3 py-2 border-b align-top whitespace-nowrap">
                    <input
                      type="checkbox"
                      checked={w.enabled}
                      onChange={() => void handleToggleEnabled(w)}
                    />
                  </td>
                  <td className="px-3 py-2 border-b align-top whitespace-nowrap text-[11px] text-gray-500">
                    {w.last_checked_at ? new Date(w.last_checked_at).toLocaleString() : '—'}
                  </td>
                  <td className="px-3 py-2 border-b align-top whitespace-nowrap space-x-2">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => startEdit(w)}
                    >
                      Правка
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => void handleRunOnce(w)}
                    >
                      Тест
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => void handleDelete(w)}
                    >
                      Удалить
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {editing && (
        <div className="fixed inset-0 bg-black bg-opacity-30 flex items-center justify-center z-50">
          <div className="bg-white rounded shadow-lg w-full max-w-xl max-h-[90vh] overflow-auto text-sm">
            <div className="px-4 py-3 border-b flex items-center justify-between">
              <div className="font-semibold text-sm">
                {editing.id ? 'Редактировать правило' : 'Создать правило'}
              </div>
              <button
                type="button"
                className="text-xs text-gray-500 hover:text-gray-700"
                onClick={() => setEditing(null)}
              >
                Закрыть
              </button>
            </div>
            <div className="p-4 space-y-3">
              <div className="space-y-1">
                <label className="block text-xs font-medium text-gray-600 mb-1">Название</label>
                <Input
                  value={editing.name ?? ''}
                  onChange={(e) => setEditing((f) => (f ? { ...f, name: e.target.value } : f))}
                />
              </div>
              <div className="space-y-1">
                <label className="block text-xs font-medium text-gray-600 mb-1">Ключевые слова</label>
                <Input
                  value={editing.keywords ?? ''}
                  onChange={(e) => setEditing((f) => (f ? { ...f, keywords: e.target.value } : f))}
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <label className="block text-xs font-medium text-gray-600 mb-1">
                    Макс. цена (товар + доставка)
                  </label>
                  <Input
                    type="number"
                    min={0}
                    step={1}
                    value={editing.max_total_price ?? ''}
                    onChange={(e) =>
                      setEditing((f) =>
                        f ? { ...f, max_total_price: e.target.value ? Number(e.target.value) : undefined } : f,
                      )
                    }
                  />
                </div>
                <div className="space-y-1">
                  <label className="block text-xs font-medium text-gray-600 mb-1">Интервал проверки (сек)</label>
                  <Input
                    type="number"
                    min={10}
                    max={3600}
                    value={editing.check_interval_sec ?? 60}
                    onChange={(e) =>
                      setEditing((f) =>
                        f ? { ...f, check_interval_sec: e.target.value ? Number(e.target.value) : 60 } : f,
                      )
                    }
                  />
                </div>
              </div>
              <div className="space-y-1">
                <label className="block text-xs font-medium text-gray-600 mb-1">Тип товара</label>
                <label className="flex items-center gap-2 text-xs">
                  <input
                    type="checkbox"
                    checked={(editing.category_hint ?? 'laptop') === 'laptop'}
                    onChange={(e) =>
                      setEditing((f) =>
                        f ? { ...f, category_hint: e.target.checked ? 'laptop' : 'all' } : f,
                      )
                    }
                  />
                  Только ноутбуки целиком
                </label>
              </div>
              <div className="space-y-1">
                <label className="block text-xs font-medium text-gray-600 mb-1">
                  Исключить слова (через запятую)
                </label>
                <Textarea
                  rows={2}
                  value={(editing.exclude_keywords ?? []).join(', ')}
                  onChange={(e) =>
                    setEditing((f) =>
                      f
                        ? {
                            ...f,
                            exclude_keywords: e.target.value
                              .split(',')
                              .map((s) => s.trim())
                              .filter(Boolean),
                          }
                        : f,
                    )
                  }
                />
              </div>
              <div className="space-y-1">
                <label className="block text-xs font-medium text-gray-600 mb-1">
                  Режим нотификаций
                </label>
                <select
                  className="border rounded px-2 py-1 text-xs"
                  value={editing.notification_mode ?? 'task'}
                  onChange={(e) =>
                    setEditing((f) => (f ? { ...f, notification_mode: e.target.value as 'task' | 'none' } : f))
                  }
                >
                  <option value="task">Создавать уведомление (Task + колокольчик)</option>
                  <option value="none">Не уведомлять, только для ручного просмотра</option>
                </select>
              </div>
              <div className="space-y-1">
                <label className="block text-xs font-medium text-gray-600 mb-1">Включено</label>
                <label className="flex items-center gap-2 text-xs">
                  <input
                    type="checkbox"
                    checked={editing.enabled ?? true}
                    onChange={(e) =>
                      setEditing((f) => (f ? { ...f, enabled: e.target.checked } : f))
                    }
                  />
                  Активировать правило
                </label>
              </div>
            </div>
            <div className="px-4 py-3 border-t flex items-center justify-end gap-3 text-sm">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setEditing(null)}
              >
                Отмена
              </Button>
              <Button size="sm" onClick={handleSave} disabled={saving}>
                {saving ? 'Сохранение…' : 'Сохранить'}
              </Button>
            </div>
          </div>
        </div>
      )}

      {preview && (
        <div className="fixed inset-0 bg-black bg-opacity-30 flex items-center justify-center z-40">
          <div className="bg-white rounded shadow-lg w-full max-w-2xl max-h-[80vh] overflow-auto text-xs">
            <div className="px-4 py-3 border-b flex items-center justify-between">
              <div className="font-semibold text-sm">Тестовый запуск правила</div>
              <button
                type="button"
                className="text-xs text-gray-500 hover:text-gray-700"
                onClick={() => setPreview(null)}
              >
                Закрыть
              </button>
            </div>
            {previewError && (
              <div className="px-4 py-2 text-xs text-red-600">{previewError}</div>
            )}
            <div className="p-4">
              {preview.length === 0 && !previewError ? (
                <div className="text-gray-500">Подходящих лотов не найдено.</div>
              ) : (
                <table className="min-w-full text-left border-collapse">
                  <thead className="bg-gray-100 text-[11px] uppercase tracking-wide text-gray-600">
                    <tr>
                      <th className="px-3 py-2 border-b">Title</th>
                      <th className="px-3 py-2 border-b">Total</th>
                      <th className="px-3 py-2 border-b">Condition</th>
                      <th className="px-3 py-2 border-b">Link</th>
                    </tr>
                  </thead>
                  <tbody>
                    {preview.map((r) => (
                      <tr key={r.item_id} className="hover:bg-gray-50">
                        <td className="px-3 py-2 border-b max-w-md">
                          <div className="font-semibold text-gray-800 truncate" title={r.title}>
                            {r.title}
                          </div>
                          {r.description && (
                            <div className="text-[11px] text-gray-500 truncate" title={r.description}>
                              {r.description}
                            </div>
                          )}
                        </td>
                        <td className="px-3 py-2 border-b whitespace-nowrap font-semibold">
                          {r.total_price.toFixed(2)}
                        </td>
                        <td className="px-3 py-2 border-b whitespace-nowrap">
                          {r.condition || '—'}
                        </td>
                        <td className="px-3 py-2 border-b whitespace-nowrap">
                          {r.ebay_url ? (
                            <a
                              href={r.ebay_url}
                              target="_blank"
                              rel="noreferrer"
                              className="text-blue-600 hover:underline"
                            >
                              Open
                            </a>
                          ) : (
                            '—'
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
