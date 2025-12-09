import React, { useEffect, useMemo, useState } from 'react';
import FixedHeader from '@/components/FixedHeader';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import api from '@/lib/apiClient';
import { AppDataGrid } from '@/components/datagrid/AppDataGrid';
import type { GridColumnMeta } from '@/components/DataGridPage';

interface AnalyticsContainer {
  key: string;
  label: string;
  table: string;
  rows_key: string;
  rows: Record<string, any>[];
}

interface AnalyticsResponse {
  storage_id: string;
  containers: AnalyticsContainer[];
  // plus raw sections like buying, inventory, etc. which we don't type strictly here
  [key: string]: any;
}

interface SourcesContainerMeta {
  key: string;
  table: string;
  default_table?: string;
  label: string;
  description: string;
}

interface SourcesResponse {
  containers: SourcesContainerMeta[];
}

const HELP_TEXT = `Test Computer Analytics

Этот экран показывает полный жизненный цикл одного компьютера (по Storage ID) через все таблицы:

1. VB / BUYING — исходная покупка компьютера (buying.storage = A127, A331 и т.п.).
2. Legacy Inventory (tbl_parts_inventory) — старый инвентарь деталей, привязанных через Storage / AlternativeStorage / StorageAlias.
3. Inventory (modern) — современная таблица inventory + parts_detail, где каждая деталь знает свой SKU и родительский storage_id.
4. Sales Transactions — продажи этих SKU (таблица transactions).
5. Finances Transactions — записи Sell Finances API (ebay_finances_transactions) по тем же order_id / order_line_item_id.
6. Finances Fees — детализированные fee-строки (ebay_finances_fees) по связанным finances-транзакциям.
7. Invoices (CVFII) — счета/инвойсы (любая таблица CVFII-стиля), которую можно связать по storage или order_id.
8. Returns / Refunds — возвраты и рефанды (ebay_returns или совместимое представление) по order_id / transaction_id.

Важное правило: все контейнеры для одного Storage ID связаны между собой через цепочку
Storage → Inventory/Parts → SKU → Transactions → Orders → Finances / Fees → Returns / Invoices.

Секция "Data source mapping" позволяет быстро переключать физические таблицы
для каждого логического контейнера. Это удобно при миграции с MSSQL/legacy-таблиц
на новые Supabase/Postgres-вью:

- root_purchase — можно направить на другую buying/VB-таблицу.
- inventory_legacy — любая mirror-таблица tbl_parts_inventory.
- inventory — текущая inventory-таблица или новая вьюшка.
- transactions — основная таблица продаж.
- finances_transactions / finances_fees — финансы по продажам.
- invoices — любая CVFII-таблица или вью.
- returns_refunds — таблица/вью с возвратами и рефандами.

Эта страница не кэширует данные: каждый поиск по Storage ID делает прямой запрос
к базе через backend-эндпоинт /api/admin/test-computer-analytics.`;

function buildColumnsFromRows(rows: Record<string, any>[]): { columns: { name: string; label: string; width: number }[]; meta: Record<string, GridColumnMeta> } {
  if (!rows || rows.length === 0) {
    return { columns: [], meta: {} };
  }
  const first = rows[0] || {};
  const keys = Object.keys(first);
  const columns = keys.map((name) => {
    let width = 140;
    const lower = name.toLowerCase();
    if (lower === 'id' || lower.endsWith('_id') || lower.includes('order') || lower.includes('transaction')) {
      width = 160;
    } else if (lower.includes('status')) {
      width = 140;
    } else if (lower.includes('amount') || lower.includes('price') || lower.includes('fee')) {
      width = 120;
    } else if (lower.includes('time') || lower.includes('date')) {
      width = 180;
    }
    return { name, label: name, width };
  });

  const meta: Record<string, GridColumnMeta> = {};
  keys.forEach((name) => {
    const value = first[name];
    let type: GridColumnMeta['type'] = 'string';
    if (typeof value === 'number') {
      type = 'number';
    } else if (typeof value === 'boolean') {
      type = 'boolean';
    } else if (typeof value === 'string') {
      if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(value)) {
        type = 'datetime';
      } else if (/^-?\d+(\.\d+)?$/.test(value)) {
        type = 'number';
      }
    }
    meta[name] = { name, label: name, type };
  });

  return { columns, meta };
}

const AdminTestComputerAnalyticsPage: React.FC = () => {
  const [storageId, setStorageId] = useState('A331');
  const [pendingStorageId, setPendingStorageId] = useState('A331');
  const [data, setData] = useState<AnalyticsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [sources, setSources] = useState<SourcesContainerMeta[] | null>(null);
  const [sourcesDraft, setSourcesDraft] = useState<Record<string, string>>({});
  const [savingSources, setSavingSources] = useState(false);

  const [showHelp, setShowHelp] = useState(false);

  const containers = useMemo<AnalyticsContainer[]>(() => data?.containers ?? [], [data]);

  useEffect(() => {
    // Load current sources mapping for the settings panel.
    const loadSources = async () => {
      try {
        const resp = await api.get<SourcesResponse>('/api/admin/test-computer-analytics/sources');
        const items = resp.data?.containers ?? [];
        setSources(items);
        const draft: Record<string, string> = {};
        items.forEach((c) => {
          draft[c.key] = c.table;
        });
        setSourcesDraft(draft);
      } catch (e) {
        // Best-effort; leave mapping panel empty on error.
        // eslint-disable-next-line no-console
        console.error('Failed to load computer analytics sources', e);
      }
    };
    void loadSources();
  }, []);

  const handleSearch = async () => {
    const trimmed = pendingStorageId.trim();
    if (!trimmed) return;
    setLoading(true);
    setError(null);
    try {
      const resp = await api.get<AnalyticsResponse>('/api/admin/test-computer-analytics', {
        params: { storage_id: trimmed },
      });
      setData(resp.data);
      setStorageId(trimmed);
    } catch (e: any) {
      // eslint-disable-next-line no-console
      console.error('Failed to load test computer analytics', e);
      const message = e?.response?.data?.detail || e?.message || 'Failed to load analytics';
      setError(String(message));
      setData(null);
    } finally {
      setLoading(false);
    }
  };

  const handleSaveSources = async () => {
    if (!sourcesDraft || Object.keys(sourcesDraft).length === 0) return;
    setSavingSources(true);
    try {
      const payload = {
        sources: Object.fromEntries(
          Object.entries(sourcesDraft).map(([key, table]) => [key, { table }]),
        ),
      };
      const resp = await api.put<SourcesResponse>('/api/admin/test-computer-analytics/sources', payload);
      const items = resp.data?.containers ?? [];
      setSources(items);
      const draft: Record<string, string> = {};
      items.forEach((c) => {
        draft[c.key] = c.table;
      });
      setSourcesDraft(draft);
    } catch (e: any) {
      // eslint-disable-next-line no-alert
      alert(e?.response?.data?.detail || e?.message || 'Failed to save sources');
    } finally {
      setSavingSources(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <FixedHeader />
      <div className="pt-16 px-4 pb-6 max-w-7xl mx-auto">
        <div className="flex items-start justify-between gap-4 mb-4">
          <div>
            <h1 className="text-2xl font-bold">Test Computer Analytics</h1>
            <p className="text-sm text-gray-600 mt-1">
              Полный путь одного компьютера по Storage ID: покупка → инвентарь → продажи → финансы → инвойсы → возвраты.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => setShowHelp(true)}>
              i
            </Button>
          </div>
        </div>

        <Card className="p-4 mb-4 flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2">
            <span className="text-sm text-gray-700">Storage ID:</span>
            <Input
              className="w-32 text-sm"
              value={pendingStorageId}
              onChange={(e) => setPendingStorageId(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  void handleSearch();
                }
              }}
              placeholder="A127"
            />
            <Button size="sm" onClick={() => void handleSearch()} disabled={loading}>
              {loading ? 'Loading…' : 'Search'}
            </Button>
          </div>
          {storageId && !loading && (
            <div className="text-xs text-gray-600">
              Current Storage ID: <span className="font-mono">{storageId}</span>
            </div>
          )}
          {error && (
            <div className="text-xs text-red-600">{error}</div>
          )}
        </Card>

        <div className="grid grid-cols-1 lg:grid-cols-4 gap-4 items-start">
          <div className="lg:col-span-3 flex flex-col gap-4">
            {containers.length === 0 && !loading && (
              <Card className="p-4 text-sm text-gray-500">
                Введите Storage ID и нажмите Search, чтобы увидеть цепочку.
              </Card>
            )}

            {containers.map((container) => {
              const { columns, meta } = buildColumnsFromRows(container.rows || []);
              return (
                <Card key={container.key} className="p-3 flex flex-col h-80">
                  <div className="flex items-center justify-between mb-2">
                    <div>
                      <div className="text-sm font-semibold">{container.label}</div>
                      <div className="text-xs text-gray-500">
                        Table: <span className="font-mono">{container.table}</span> · Rows:{' '}
                        <span className="font-mono">{container.rows?.length ?? 0}</span>
                      </div>
                    </div>
                  </div>
                  <div className="flex-1 min-h-0">
                    <AppDataGrid
                      columns={columns}
                      rows={container.rows || []}
                      columnMetaByName={meta}
                      loading={loading && !!storageId}
                      gridKey={container.key}
                      gridTheme={null}
                    />
                  </div>
                </Card>
              );
            })}
          </div>

          <div className="lg:col-span-1 flex flex-col gap-4">
            <Card className="p-3 text-sm">
              <div className="flex items-center justify-between mb-2">
                <div className="font-semibold text-sm">Data source mapping</div>
              </div>
              <p className="text-xs text-gray-600 mb-3">
                Быстрый способ сменить физические таблицы для каждого логического контейнера (для миграций MSSQL → Supabase/Postgres).
              </p>
              {!sources && (
                <div className="text-xs text-gray-500">Loading mapping…</div>
              )}
              {sources && (
                <div className="space-y-3">
                  {sources.map((c) => (
                    <div key={c.key} className="border rounded px-2 py-1.5 bg-gray-50">
                      <div className="text-xs font-semibold text-gray-800">{c.label}</div>
                      <div className="text-[11px] text-gray-500 mb-1">{c.description}</div>
                      <div className="flex flex-col gap-1">
                        <label className="text-[11px] text-gray-600">
                          Table name
                          <Input
                            className="mt-0.5 h-7 text-xs font-mono"
                            value={sourcesDraft[c.key] ?? c.table}
                            onChange={(e) => {
                              const value = e.target.value;
                              setSourcesDraft((prev) => ({ ...prev, [c.key]: value }));
                            }}
                          />
                        </label>
                        {c.default_table && (
                          <div className="text-[11px] text-gray-500">
                            Default: <span className="font-mono">{c.default_table}</span>
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                  <Button
                    size="sm"
                    className="w-full mt-1"
                    onClick={() => void handleSaveSources()}
                    disabled={savingSources}
                  >
                    {savingSources ? 'Saving…' : 'Save mapping'}
                  </Button>
                </div>
              )}
            </Card>
          </div>
        </div>

        {showHelp && (
          <div className="fixed inset-0 bg-black bg-opacity-40 flex items-center justify-center z-50">
            <div className="bg-white rounded shadow-lg max-w-3xl w-full max-h-[80vh] flex flex-col">
              <div className="px-4 py-2 border-b flex items-center justify-between">
                <div className="font-semibold text-sm">Test Computer Analytics — help</div>
                <button
                  type="button"
                  className="text-xs text-gray-500 hover:text-gray-700"
                  onClick={() => setShowHelp(false)}
                >
                  Close
                </button>
              </div>
              <div className="p-4 overflow-auto text-xs whitespace-pre-wrap leading-relaxed">
                {HELP_TEXT}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default AdminTestComputerAnalyticsPage;
