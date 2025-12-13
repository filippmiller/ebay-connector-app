import { useEffect, useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import FixedHeader from '@/components/FixedHeader';
import { Card } from '@/components/ui/card';
import api from '@/lib/apiClient';

interface AiOverviewRulesDto {
  total: number;
  last_created_at: string | null;
}

interface AiOverviewQueriesDto {
  total: number;
  last_24h: number;
  last_executed_at: string | null;
}

interface AiOverviewModelsDto {
  profiles_total: number;
}

interface AiOverviewCandidatesDto {
  total: number;
  by_rule: Record<string, number>;
}

interface AiOverviewActionsDto {
  total: number;
  by_status: Record<string, number>;
}

interface AiOverviewConfigDto {
  MIN_PROFIT_MARGIN: number;
  AUTO_BUY_DRY_RUN: boolean;
  AUTO_BUY_MIN_ROI: number;
  AUTO_BUY_MIN_PROFIT: number;
}

interface AiOverviewDto {
  rules: AiOverviewRulesDto;
  queries: AiOverviewQueriesDto;
  models: AiOverviewModelsDto;
  candidates: AiOverviewCandidatesDto;
  actions: AiOverviewActionsDto;
  config: AiOverviewConfigDto;
}

export default function AdminAiCenterPage() {
  const navigate = useNavigate();
  const [overview, setOverview] = useState<AiOverviewDto | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const resp = await api.get<AiOverviewDto>('/api/admin/ai/overview');
        if (!cancelled) {
          setOverview(resp.data);
        }
      } catch (e: any) {
        if (!cancelled) {
          const msg = e?.response?.data?.detail || e.message || 'Failed to load AI overview';
          setError(String(msg));
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    load();

    return () => {
      cancelled = true;
    };
  }, []);

  const topRules = useMemo(() => {
    if (!overview) return [] as { name: string; count: number }[];
    const entries = Object.entries(overview.candidates.by_rule || {});
    return entries
      .map(([name, count]) => ({ name, count }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 3);
  }, [overview]);

  const actionsByStatus = useMemo(() => {
    if (!overview) return [] as { status: string; count: number }[];
    return Object.entries(overview.actions.by_status || {})
      .map(([status, count]) => ({ status, count }))
      .sort((a, b) => a.status.localeCompare(b.status));
  }, [overview]);

  const formatDateTime = (value: string | null | undefined): string => {
    if (!value) return '—';
    try {
      return new Date(value).toLocaleString();
    } catch {
      return value;
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      <FixedHeader />
      <div className="pt-16 px-4 py-6 max-w-6xl w-full mx-auto flex-1 flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold">AI & Automation Center</h1>
            <p className="text-sm text-gray-600 max-w-3xl">
              Обзор правил, AI-запросов, profitability-профилей, мониторинга кандидатов и авто-действий.
            </p>
          </div>
          {loading && <div className="text-xs text-gray-500">Loading…</div>}
        </div>

        {error && (
          <div className="text-xs text-red-600 border border-red-200 bg-red-50 rounded px-2 py-1" role="alert">
            {error}
          </div>
        )}

        <div className="grid grid-cols-3 gap-4">
          <Card className="p-4 space-y-1">
            <h2 className="text-sm font-semibold">Rules</h2>
            <div className="text-2xl font-bold">{overview?.rules.total ?? '—'}</div>
            <div className="text-xs text-gray-500">
              Last created: {formatDateTime(overview?.rules.last_created_at ?? null)}
            </div>
          </Card>

          <Card className="p-4 space-y-1">
            <h2 className="text-sm font-semibold">AI Queries</h2>
            <div className="text-2xl font-bold">{overview?.queries.total ?? '—'}</div>
            <div className="text-xs text-gray-500">Last 24h: {overview?.queries.last_24h ?? '—'}</div>
            <div className="text-xs text-gray-500">
              Last executed: {formatDateTime(overview?.queries.last_executed_at ?? null)}
            </div>
          </Card>

          <Card className="p-4 space-y-1">
            <h2 className="text-sm font-semibold">Model Profit Profiles</h2>
            <div className="text-2xl font-bold">{overview?.models.profiles_total ?? '—'}</div>
            <div className="text-xs text-gray-500">Rows in model_profit_profile</div>
          </Card>

          <Card className="p-4 space-y-2">
            <h2 className="text-sm font-semibold">Candidates</h2>
            <div className="text-2xl font-bold">{overview?.candidates.total ?? '—'}</div>
            <div className="text-xs text-gray-500">Top rules by candidate count:</div>
            <ul className="text-xs text-gray-700 list-disc list-inside space-y-0.5">
              {topRules.length === 0 && <li>Нет данных</li>}
              {topRules.map((r) => (
                <li key={r.name}>
                  <span className="font-mono">{r.name}</span>: {r.count}
                </li>
              ))}
            </ul>
          </Card>

          <Card className="p-4 space-y-2">
            <h2 className="text-sm font-semibold">Actions</h2>
            <div className="text-2xl font-bold">{overview?.actions.total ?? '—'}</div>
            <ul className="text-xs text-gray-700 list-disc list-inside space-y-0.5 mt-1">
              {actionsByStatus.length === 0 && <li>Нет данных</li>}
              {actionsByStatus.map((s) => (
                <li key={s.status}>
                  <span className="font-mono">{s.status}</span>: {s.count}
                </li>
              ))}
            </ul>
          </Card>

          <Card className="p-4 space-y-2">
            <h2 className="text-sm font-semibold">Config</h2>
            <table className="w-full text-xs text-gray-700">
              <tbody>
                <tr>
                  <td className="pr-2 text-gray-500">MIN_PROFIT_MARGIN</td>
                  <td>{overview?.config.MIN_PROFIT_MARGIN ?? '—'}</td>
                </tr>
                <tr>
                  <td className="pr-2 text-gray-500">AUTO_BUY_DRY_RUN</td>
                  <td>{overview?.config.AUTO_BUY_DRY_RUN ? 'true' : 'false'}</td>
                </tr>
                <tr>
                  <td className="pr-2 text-gray-500">AUTO_BUY_MIN_ROI</td>
                  <td>{overview?.config.AUTO_BUY_MIN_ROI ?? '—'}</td>
                </tr>
                <tr>
                  <td className="pr-2 text-gray-500">AUTO_BUY_MIN_PROFIT</td>
                  <td>{overview?.config.AUTO_BUY_MIN_PROFIT ?? '—'}</td>
                </tr>
              </tbody>
            </table>
          </Card>
        </div>

        <Card className="p-4 mt-2">
          <h2 className="text-sm font-semibold mb-2">Quick Links</h2>
          <div className="flex flex-wrap gap-2 text-xs">
            <button
              type="button"
              className="px-3 py-1.5 rounded border border-gray-300 bg-white hover:bg-gray-50"
              onClick={() => navigate('/admin/ai-grid')}
            >
              Open AI Grid
            </button>
            <button
              type="button"
              className="px-3 py-1.5 rounded border border-gray-300 bg-white hover:bg-gray-50"
              onClick={() => navigate('/admin/ai-rules')}
            >
              Open AI Rules
            </button>
            <button
              type="button"
              className="px-3 py-1.5 rounded border border-gray-300 bg-white hover:bg-gray-50"
              onClick={() => navigate('/admin/model-profit')}
            >
              Open Model Profit
            </button>
            <button
              type="button"
              className="px-3 py-1.5 rounded border border-gray-300 bg-white hover:bg-gray-50"
              onClick={() => navigate('/admin/monitor')}
            >
              Open Monitoring
            </button>
            <button
              type="button"
              className="px-3 py-1.5 rounded border border-gray-300 bg-white hover:bg-gray-50"
              onClick={() => navigate('/admin/actions')}
            >
              Open Actions
            </button>
          </div>
        </Card>
      </div>
    </div>
  );
}