import { useEffect, useMemo, useState } from 'react';

import FixedHeader from '@/components/FixedHeader';
import { Card } from '@/components/ui/card';
import api from '@/lib/apiClient';
import { AppDataGrid, type AppDataGridColumnState } from '@/components/datagrid/AppDataGrid';
import type { GridColumnMeta } from '@/components/DataGridPage';

interface AiEbayCandidateDto {
  ebay_item_id: string;
  model_id: string;
  title: string | null;
  price: number | null;
  shipping: number | null;
  condition: string | null;
  description: string | null;
  predicted_profit: number | null;
  roi: number | null;
  matched_rule: boolean | null;
  rule_name: string | null;
  created_at: string;
  updated_at: string;
}

const GRID_KEY = 'admin_monitor';
const LAYOUT_STORAGE_KEY = `grid_layout_${GRID_KEY}`;

type StoredLayout = {
  order: string[];
  widths: Record<string, number>;
};

export default function AdminMonitoringPage() {
  const [rows, setRows] = useState<AiEbayCandidateDto[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const resp = await api.get<AiEbayCandidateDto[]>(
          '/api/admin/ai/monitor/candidates',
          { params: { limit: 500, offset: 0 } },
        );
        if (!cancelled) {
          setRows(resp.data || []);
        }
      } catch (e: any) {
        if (!cancelled) {
          const msg = e?.response?.data?.detail || e?.message || 'Failed to load monitoring candidates';
          setError(String(msg));
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    load();

    return () => {
      cancelled = true;
    };
  }, []);

  const baseColumns: AppDataGridColumnState[] = useMemo(
    () => [
      { name: 'ebay_item_id', label: 'eBay Item ID', width: 160 },
      { name: 'model_id', label: 'Model ID', width: 130 },
      { name: 'title', label: 'Title', width: 260 },
      { name: 'price', label: 'Price', width: 110 },
      { name: 'shipping', label: 'Shipping', width: 110 },
      { name: 'predicted_profit', label: 'Predicted Profit', width: 150 },
      { name: 'roi', label: 'ROI', width: 110 },
      { name: 'matched_rule', label: 'Matched Rule', width: 130 },
      { name: 'rule_name', label: 'Rule Name', width: 200 },
      { name: 'created_at', label: 'Created At', width: 180 },
    ],
    [],
  );

  const [columns, columnMetaByName] = useMemo(() => {
    let stored: StoredLayout | null = null;
    try {
      const raw = window.localStorage.getItem(LAYOUT_STORAGE_KEY);
      if (raw) {
        stored = JSON.parse(raw) as StoredLayout;
      }
    } catch {
      stored = null;
    }

    const order = stored?.order && stored.order.length
      ? stored.order
      : baseColumns.map((c) => c.name);

    const widthByName = stored?.widths || {};

    const cols: AppDataGridColumnState[] = order
      .map((name) => baseColumns.find((c) => c.name === name))
      .filter((c): c is AppDataGridColumnState => !!c)
      .map((c) => ({ ...c, width: widthByName[c.name] ?? c.width }));

    const meta: Record<string, GridColumnMeta> = {
      ebay_item_id: { name: 'ebay_item_id', label: 'eBay Item ID', type: 'string', width_default: 160 },
      model_id: { name: 'model_id', label: 'Model ID', type: 'string', width_default: 130 },
      title: { name: 'title', label: 'Title', type: 'string', width_default: 260 },
      price: { name: 'price', label: 'Price', type: 'number', width_default: 110 },
      shipping: { name: 'shipping', label: 'Shipping', type: 'number', width_default: 110 },
      predicted_profit: { name: 'predicted_profit', label: 'Predicted Profit', type: 'number', width_default: 150 },
      roi: { name: 'roi', label: 'ROI', type: 'number', width_default: 110 },
      matched_rule: { name: 'matched_rule', label: 'Matched Rule', type: 'string', width_default: 130 },
      rule_name: { name: 'rule_name', label: 'Rule Name', type: 'string', width_default: 200 },
      created_at: { name: 'created_at', label: 'Created At', type: 'datetime', width_default: 180 },
    };

    return [cols, meta] as const;
  }, [baseColumns]);

  const filteredRows = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter((row) => {
      const haystack = [
        row.ebay_item_id,
        row.model_id,
        row.title ?? '',
        row.rule_name ?? '',
      ]
        .join(' ')
        .toLowerCase();
      return haystack.includes(q);
    });
  }, [rows, search]);

  const handleLayoutChange = (state: { order: string[]; widths: Record<string, number> }) => {
    const payload: StoredLayout = {
      order: state.order,
      widths: state.widths,
    };
    try {
      window.localStorage.setItem(LAYOUT_STORAGE_KEY, JSON.stringify(payload));
    } catch {
      // best-effort only
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      <FixedHeader />
      <div className="pt-16 px-4 py-6 max-w-7xl w-full mx-auto flex-1 flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold">Monitoring Candidates</h1>
            <p className="text-sm text-gray-600 max-w-3xl">
              eBay listings that look potentially profitable relative to the model profitability profile
              (max_buy_price, expected_profit, AI rules).
            </p>
          </div>
          <div className="flex items-center gap-2">
            <input
              className="px-2 py-1 border rounded-md text-xs bg-white placeholder:text-gray-400"
              placeholder="Search by item, model, title or rule"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
        </div>

        {error && (
          <div className="text-xs text-red-600 border border-red-200 bg-red-50 rounded px-2 py-1" role="alert">
            {error}
          </div>
        )}

        <Card className="flex-1 min-h-[400px] p-3 flex flex-col">
          <div className="flex-1 min-h-[320px]">
            <AppDataGrid
              columns={columns}
              rows={filteredRows as any}
              columnMetaByName={columnMetaByName}
              loading={loading}
              gridKey={GRID_KEY}
              gridTheme={null}
              onLayoutChange={({ order, widths }) => handleLayoutChange({ order, widths })}
            />
          </div>
        </Card>
      </div>
    </div>
  );
}
