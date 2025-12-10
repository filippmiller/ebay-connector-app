import React, { useEffect, useMemo, useState } from 'react';
import FixedHeader from '@/components/FixedHeader';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import api from '@/lib/apiClient';
import { AppDataGrid } from '@/components/datagrid/AppDataGrid';
import type { GridColumnMeta } from '@/components/DataGridPage';

interface GraphNodeConfig {
  label?: string;
  table?: string;
  storageColumns?: string[];
  skuColumns?: string[];
  matchFrom?: Record<string, string[]>;
  emit?: Record<string, string[]>;
}

interface GraphConfig {
  nodes: Record<string, GraphNodeConfig>;
  order: string[];
}

interface AnalyticsContainer {
  key: string;
  label: string;
  table: string;
  rows_key: string;
  rows: Record<string, any>[];
}

interface GraphAnalyticsResponse {
  storage_id: string;
  graph: GraphConfig;
  containers: AnalyticsContainer[];
  sections: Record<string, Record<string, any>[]>;
}

const GRAPH_HELP = `Test Computer Analytics (Graph beta)

Этот режим позволяет не только выбирать таблицы для каждого контейнера,
но и настраивать ключевые колонки, которые связывают контейнеры между собой.

Базовая идея:
- Buying фильтруется по Storage ID и может "излучать" storage-ключи.
- Legacy / modern inventory фильтруются по Storage ID и излучают SKU.
- Transactions можно линковать по SKU, ItemID или другим колонкам.
- Finances / Returns можно линковать по order_id / transaction_id и т.д.

Сейчас backend всё ещё использует классическую цепочку (storage → SKU → order →
finances), но этот Graph-конфиг уже хранится отдельно и вскоре будет
использоваться для генерации SQL-переходов.`;

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

const AdminTestComputerAnalyticsGraphPage: React.FC = () => {
  const [storageId, setStorageId] = useState('A331');
  const [pendingStorageId, setPendingStorageId] = useState('A331');
  const [data, setData] = useState<GraphAnalyticsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [graphDraft, setGraphDraft] = useState<GraphConfig | null>(null);
  const [savingGraph, setSavingGraph] = useState(false);

  const [showHelp, setShowHelp] = useState(false);

  const containers = useMemo<AnalyticsContainer[]>(() => data?.containers ?? [], [data]);

  useEffect(() => {
    const loadGraph = async () => {
      try {
        const resp = await api.get<GraphConfig>('/api/admin/test-computer-analytics-graph/sources');
        const cfg = resp.data || { nodes: {}, order: [] };
        setGraphDraft(cfg);
      } catch (e) {
        // eslint-disable-next-line no-console
        console.error('Failed to load graph sources', e);
      }
    };
    void loadGraph();
  }, []);

  const handleSearch = async () => {
    const trimmed = pendingStorageId.trim();
    if (!trimmed) return;
    setLoading(true);
    setError(null);
    try {
      const resp = await api.get<GraphAnalyticsResponse>('/api/admin/test-computer-analytics-graph', {
        params: { storage_id: trimmed },
      });
      setData(resp.data);
      setStorageId(trimmed);
      if (resp.data.graph) {
        setGraphDraft(resp.data.graph);
      }
    } catch (e: any) {
      // eslint-disable-next-line no-console
      console.error('Failed to load graph analytics', e);
      const message = e?.response?.data?.detail || e?.message || 'Failed to load analytics (graph)';
      setError(String(message));
      setData(null);
    } finally {
      setLoading(false);
    }
  };

  const handleSaveGraph = async () => {
    if (!graphDraft) return;
    setSavingGraph(true);
    try {
      const payload = {
        nodes: graphDraft.nodes,
        order: graphDraft.order,
      };
      const resp = await api.put<GraphConfig>('/api/admin/test-computer-analytics-graph/sources', payload);
      const cfg = resp.data || { nodes: {}, order: [] };
      setGraphDraft(cfg);
    } catch (e: any) {
      // eslint-disable-next-line no-alert
      alert(e?.response?.data?.detail || e?.message || 'Failed to save graph mapping');
    } finally {
      setSavingGraph(false);
    }
  };

  const orderedNodes = useMemo(() => {
    if (!graphDraft) return [] as string[];
    const order = graphDraft.order && graphDraft.order.length > 0
      ? graphDraft.order
      : Object.keys(graphDraft.nodes || {});
    return order.filter((k) => graphDraft.nodes[k]);
  }, [graphDraft]);

  const handleNodeFieldChange = (key: string, field: keyof GraphNodeConfig, value: string) => {
    setGraphDraft((prev) => {
      if (!prev) return prev;
      const existing = prev.nodes[key] || {};
      const next: GraphNodeConfig = { ...existing };
      if (field === 'storageColumns' || field === 'skuColumns') {
        const arr = value.split(',').map((s) => s.trim()).filter(Boolean);
        (next as any)[field] = arr;
      } else {
        (next as any)[field] = value || undefined;
      }
      return {
        ...prev,
        nodes: {
          ...prev.nodes,
          [key]: next,
        },
      };
    });
  };

  const handleMatchFromChange = (key: string, logicalKey: string, value: string) => {
    setGraphDraft((prev) => {
      if (!prev) return prev;
      const existing = prev.nodes[key] || {};
      const matchFrom = { ...(existing.matchFrom || {}) };
      const arr = value.split(',').map((s) => s.trim()).filter(Boolean);
      if (arr.length === 0) {
        delete matchFrom[logicalKey];
      } else {
        matchFrom[logicalKey] = arr;
      }
      const next: GraphNodeConfig = { ...existing, matchFrom };
      return {
        ...prev,
        nodes: {
          ...prev.nodes,
          [key]: next,
        },
      };
    });
  };

  const handleEmitChange = (key: string, logicalKey: string, value: string) => {
    setGraphDraft((prev) => {
      if (!prev) return prev;
      const existing = prev.nodes[key] || {};
      const emit = { ...(existing.emit || {}) };
      const arr = value.split(',').map((s) => s.trim()).filter(Boolean);
      if (arr.length === 0) {
        delete emit[logicalKey];
      } else {
        emit[logicalKey] = arr;
      }
      const next: GraphNodeConfig = { ...existing, emit };
      return {
        ...prev,
        nodes: {
          ...prev.nodes,
          [key]: next,
        },
      };
    });
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <FixedHeader />
      <div className="pt-16 px-4 pb-6 max-w-7xl mx-auto">
        <div className="flex items-start justify-between gap-4 mb-4">
          <div>
            <h1 className="text-2xl font-bold">Test Computer Analytics (Graph beta)</h1>
            <p className="text-sm text-gray-600 mt-1">
              Экспериментальный графовый режим: таблицы + ключи связей между Buying → Inventory → Transactions → Finances → Returns.
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
                Введите Storage ID и нажмите Search, чтобы увидеть цепочку (graph).
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
                      gridKey={`${container.key}_graph`}
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
                <div className="font-semibold text-sm">Graph mapping</div>
              </div>
              <p className="text-xs text-gray-600 mb-3">
                Настройка таблиц и ключей для графа Buying → Inventory → Transactions → Finances → Returns.
                Изменения влияют только на Graph beta, классический режим не трогается.
              </p>
              {!graphDraft && (
                <div className="text-xs text-gray-500">Loading graph config…</div>
              )}
              {graphDraft && (
                <div className="space-y-3 max-h-[60vh] overflow-auto pr-1">
                  {orderedNodes.map((key) => {
                    const node = graphDraft.nodes[key] || {};
                    const label = node.label || key;
                    const table = node.table || '';
                    const storageCols = (node.storageColumns || []).join(', ');
                    const skuCols = (node.skuColumns || []).join(', ');
                    const matchSku = (node.matchFrom?.sku || []).join(', ');
                    const matchOrderId = (node.matchFrom?.order_id || []).join(', ');
                    const matchTxnId = (node.matchFrom?.transaction_id || []).join(', ');
                    const emitSku = (node.emit?.sku || []).join(', ');
                    const emitOrderId = (node.emit?.order_id || []).join(', ');
                    const emitTxnId = (node.emit?.transaction_id || []).join(', ');
                    return (
                      <div key={key} className="border rounded px-2 py-1.5 bg-gray-50">
                        <div className="text-xs font-semibold text-gray-800 mb-1">{label}</div>
                        <div className="space-y-1">
                          <label className="text-[11px] text-gray-600">
                            Table name
                            <Input
                              className="mt-0.5 h-7 text-xs font-mono"
                              value={table}
                              onChange={(e) => handleNodeFieldChange(key, 'table', e.target.value)}
                            />
                          </label>
                          <label className="text-[11px] text-gray-600">
                            Storage columns (for Storage ID)
                            <Input
                              className="mt-0.5 h-7 text-xs font-mono"
                              value={storageCols}
                              onChange={(e) => handleNodeFieldChange(key, 'storageColumns', e.target.value)}
                              placeholder="storage, storage_id"
                            />
                          </label>
                          <label className="text-[11px] text-gray-600">
                            SKU columns
                            <Input
                              className="mt-0.5 h-7 text-xs font-mono"
                              value={skuCols}
                              onChange={(e) => handleNodeFieldChange(key, 'skuColumns', e.target.value)}
                              placeholder="SKU, OverrideSKU"
                            />
                          </label>

                          <div className="mt-1 border-t pt-1.5 space-y-1">
                            <div className="text-[11px] font-semibold text-gray-700">Match from</div>
                            <label className="text-[11px] text-gray-600">
                              From SKU keys → columns
                              <Input
                                className="mt-0.5 h-7 text-xs font-mono"
                                value={matchSku}
                                onChange={(e) => handleMatchFromChange(key, 'sku', e.target.value)}
                                placeholder="sku"
                              />
                            </label>
                            <label className="text-[11px] text-gray-600">
                              From order_id keys → columns
                              <Input
                                className="mt-0.5 h-7 text-xs font-mono"
                                value={matchOrderId}
                                onChange={(e) => handleMatchFromChange(key, 'order_id', e.target.value)}
                                placeholder="order_id, order_line_item_id"
                              />
                            </label>
                            <label className="text-[11px] text-gray-600">
                              From transaction_id keys → columns
                              <Input
                                className="mt-0.5 h-7 text-xs font-mono"
                                value={matchTxnId}
                                onChange={(e) => handleMatchFromChange(key, 'transaction_id', e.target.value)}
                                placeholder="transaction_id"
                              />
                            </label>
                          </div>

                          <div className="mt-1 border-t pt-1.5 space-y-1">
                            <div className="text-[11px] font-semibold text-gray-700">Emit keys</div>
                            <label className="text-[11px] text-gray-600">
                              Emit sku columns
                              <Input
                                className="mt-0.5 h-7 text-xs font-mono"
                                value={emitSku}
                                onChange={(e) => handleEmitChange(key, 'sku', e.target.value)}
                                placeholder="sku"
                              />
                            </label>
                            <label className="text-[11px] text-gray-600">
                              Emit order_id columns
                              <Input
                                className="mt-0.5 h-7 text-xs font-mono"
                                value={emitOrderId}
                                onChange={(e) => handleEmitChange(key, 'order_id', e.target.value)}
                                placeholder="order_id"
                              />
                            </label>
                            <label className="text-[11px] text-gray-600">
                              Emit transaction_id columns
                              <Input
                                className="mt-0.5 h-7 text-xs font-mono"
                                value={emitTxnId}
                                onChange={(e) => handleEmitChange(key, 'transaction_id', e.target.value)}
                                placeholder="transaction_id"
                              />
                            </label>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                  <Button
                    size="sm"
                    className="w-full mt-1"
                    onClick={() => void handleSaveGraph()}
                    disabled={savingGraph}
                  >
                    {savingGraph ? 'Saving…' : 'Save graph mapping'}
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
                <div className="font-semibold text-sm">Test Computer Analytics (Graph beta) — help</div>
                <button
                  type="button"
                  className="text-xs text-gray-500 hover:text-gray-700"
                  onClick={() => setShowHelp(false)}
                >
                  Close
                </button>
              </div>
              <div className="p-4 overflow-auto text-xs whitespace-pre-wrap leading-relaxed">
                {GRAPH_HELP}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default AdminTestComputerAnalyticsGraphPage;
