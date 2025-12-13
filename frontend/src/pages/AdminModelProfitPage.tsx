import { useEffect, useMemo, useState } from "react";

import FixedHeader from '@/components/FixedHeader';
import { Card } from '@/components/ui/card';
import api from '@/lib/apiClient';
import { AppDataGrid, type AppDataGridColumnState } from '@/components/datagrid/AppDataGrid';
import type { GridColumnMeta } from '@/components/DataGridPage';

interface ModelProfitProfileDto {
  model_id: string;
  sample_size: number;
  expected_profit: number | null;
  max_buy_price: number | null;
  refund_rate: number | null;
  avg_sale_time_days: number | null;
  matched_rule: boolean | null;
  rule_name: string | null;
  updated_at: string;
}

export default function AdminModelProfitPage() {
  const [rows, setRows] = useState<ModelProfitProfileDto[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const response = await api.get<ModelProfitProfileDto[]>(
          "/api/admin/ai/profit/models"
        );
        if (!cancelled) {
          setRows(response.data);
        }
      } catch (err: any) {
        if (!cancelled) {
          const message = err?.response?.data?.detail || err?.message || "Failed to load profitability profiles";
          setError(message);
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

  const columnDefs: AppDataGridColumnState[] = useMemo(
    () => [
      { name: 'model_id', label: 'Model ID', width: 150 },
      { name: 'sample_size', label: 'Samples', width: 110 },
      { name: 'expected_profit', label: 'Expected Profit', width: 150 },
      { name: 'max_buy_price', label: 'Max Buy Price', width: 150 },
      { name: 'refund_rate', label: 'Refund Rate', width: 130 },
      { name: 'avg_sale_time_days', label: 'Avg Sale Time (days)', width: 170 },
      { name: 'matched_rule', label: 'Matched Rule', width: 130 },
      { name: 'rule_name', label: 'Rule Name', width: 200 },
      { name: 'updated_at', label: 'Updated At', width: 180 },
    ],
    []
  );

  const columnMetaByName = useMemo<Record<string, GridColumnMeta>>(
    () => ({
      model_id: {
        name: 'model_id',
        label: 'Model ID',
        type: 'string',
        width_default: 150,
      },
      sample_size: {
        name: 'sample_size',
        label: 'Samples',
        type: 'number',
        width_default: 110,
        aggFunc: 'sum',
      },
      expected_profit: {
        name: 'expected_profit',
        label: 'Expected Profit',
        type: 'number',
        width_default: 150,
        aggFunc: 'avg',
      },
      max_buy_price: {
        name: 'max_buy_price',
        label: 'Max Buy Price',
        type: 'number',
        width_default: 150,
        aggFunc: 'avg',
      },
      refund_rate: {
        name: 'refund_rate',
        label: 'Refund Rate',
        type: 'number',
        width_default: 130,
        aggFunc: 'avg',
      },
      avg_sale_time_days: {
        name: 'avg_sale_time_days',
        label: 'Avg Sale Time (days)',
        type: 'number',
        width_default: 170,
        aggFunc: 'avg',
      },
      matched_rule: {
        name: 'matched_rule',
        label: 'Matched Rule',
        type: 'string',
        width_default: 130,
      },
      rule_name: {
        name: 'rule_name',
        label: 'Rule Name',
        type: 'string',
        width_default: 200,
      },
      updated_at: {
        name: 'updated_at',
        label: 'Updated At',
        type: 'datetime',
        width_default: 180,
      },
    }),
    []
  );

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      <FixedHeader />
      <div className="pt-16 px-4 py-6 max-w-6xl w-full mx-auto flex-1 flex flex-col gap-4">
        <h1 className="text-2xl font-bold">Model Profitability Profiles</h1>
        <p className="text-sm text-gray-600 max-w-3xl">
          Aggregated profitability metrics per laptop model for AI monitoring, auto-offer, auto-buy and sniper logic.
        </p>
        {error && (
          <div className="text-red-600 text-sm" role="alert">
            {error}
          </div>
        )}
        <Card>
          <div className="h-[600px]">
            <AppDataGrid
              loading={loading}
              rows={rows as any}
              columns={columnDefs}
              columnMetaByName={columnMetaByName}
              gridKey="admin_model_profit"
              gridTheme={null}
            />
          </div>
        </Card>
      </div>
    </div>
  );
}
