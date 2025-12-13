import React, { useEffect, useState, useMemo } from 'react';
import FixedHeader from '@/components/FixedHeader';
import { AppDataGrid } from '@/components/datagrid/AppDataGrid';
import type { GridColumnMeta } from '@/components/DataGridPage';
import { Card } from '@/components/ui/card';

export interface AiEbayActionDto {
  id: number;
  ebay_item_id: string;
  model_id?: string | null;
  action_type: string;
  offer_amount?: number | null;
  original_price?: number | null;
  shipping?: number | null;
  predicted_profit?: number | null;
  roi?: number | null;
  rule_name?: string | null;
  status: string;
  error_message?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

const GRID_KEY = 'admin_actions';

const AdminActionsPage: React.FC = () => {
  const [rows, setRows] = useState<AiEbayActionDto[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      setError(null);
      try {
        const resp = await fetch('/api/admin/ai/actions');
        if (!resp.ok) {
          throw new Error(`Failed to load actions: ${resp.status}`);
        }
        const data: AiEbayActionDto[] = await resp.json();
        setRows(data || []);
      } catch (err: any) {
        setError(err.message || 'Failed to load actions');
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, []);

  const filteredRows = useMemo(() => {
    if (!search.trim()) return rows;
    const q = search.toLowerCase();
    return rows.filter((row) => {
      return (
        row.ebay_item_id.toLowerCase().includes(q) ||
        (row.model_id && row.model_id.toLowerCase().includes(q)) ||
        (row.action_type && row.action_type.toLowerCase().includes(q)) ||
        (row.rule_name && row.rule_name.toLowerCase().includes(q)) ||
        (row.status && row.status.toLowerCase().includes(q))
      );
    });
  }, [rows, search]);

  const columnMeta: GridColumnMeta[] = [
    { name: 'ebay_item_id', label: 'Item ID', width_default: 160 },
    { name: 'model_id', label: 'Model ID', width_default: 140 },
    { name: 'action_type', label: 'Action', width_default: 120 },
    { name: 'offer_amount', label: 'Offer Amount', type: 'number', width_default: 130 },
    { name: 'original_price', label: 'Original Price', type: 'number', width_default: 130 },
    { name: 'shipping', label: 'Shipping', type: 'number', width_default: 110 },
    { name: 'predicted_profit', label: 'Predicted Profit', type: 'number', width_default: 150 },
    { name: 'roi', label: 'ROI', type: 'number', width_default: 100 },
    { name: 'rule_name', label: 'Rule', width_default: 160 },
    { name: 'status', label: 'Status', width_default: 120 },
    { name: 'error_message', label: 'Error', width_default: 200 },
    { name: 'created_at', label: 'Created At', type: 'datetime', width_default: 180 },
  ];

  const columns = useMemo(
    () =>
      columnMeta.map((c) => ({
        name: c.name,
        label: c.label,
        width: c.width_default ?? 150,
      })),
    [],
  );

  const columnMetaByName: Record<string, GridColumnMeta> = useMemo(() => {
    const map: Record<string, GridColumnMeta> = {};
    columnMeta.forEach((m) => {
      map[m.name] = m;
    });
    return map;
  }, []);

  return (
    <div className="min-h-screen bg-gray-50">
      <FixedHeader />
      <div className="pt-12 p-4 space-y-4">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold">Auto-Offer / Auto-Buy Actions</h1>
        </div>

        <Card className="p-4 mb-4">
          <div className="flex items-center gap-4">
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by item, model, rule, or status..."
              className="border rounded px-3 py-2 w-80 text-sm"
            />
            {loading && <span className="text-sm text-gray-600">Loading...</span>}
            {error && <span className="text-sm text-red-600">{error}</span>}
          </div>
        </Card>

        <div className="bg-white rounded shadow">
          <AppDataGrid
            columns={columns}
            rows={filteredRows as unknown as Record<string, any>[]}
            columnMetaByName={columnMetaByName}
            gridKey={GRID_KEY}
          />
        </div>
      </div>
    </div>
  );
};

export default AdminActionsPage;
