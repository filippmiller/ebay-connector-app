import { useEffect, useMemo, useState } from 'react';

import FixedHeader from '@/components/FixedHeader';
import { Card } from '@/components/ui/card';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import api from '@/lib/apiClient';

interface AiEmailPairDto {
  id: string;
  provider_code: string;
  integration_account_id: string;
  integration_display_name: string;
  thread_id: string | null;
  status: string;
  client_text: string;
  our_reply_text: string;
  created_at: string | null;
  updated_at: string | null;
}

interface AiEmailPairsResponse {
  items: AiEmailPairDto[];
  count: number;
  limit: number;
  offset: number;
}

const STATUS_OPTIONS = ['new', 'approved', 'rejected'] as const;
const PROVIDER_OPTIONS = ['all', 'gmail'] as const;

type StatusFilter = (typeof STATUS_OPTIONS)[number];
type ProviderFilter = (typeof PROVIDER_OPTIONS)[number];

export default function AdminAiEmailTrainingPage() {
  const [items, setItems] = useState<AiEmailPairDto[]>([]);
  const [status, setStatus] = useState<StatusFilter>('new');
  const [provider, setProvider] = useState<ProviderFilter>('gmail');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [selected, setSelected] = useState<AiEmailPairDto | null>(null);
  const [modalOpen, setModalOpen] = useState(false);

  const loadPairs = async () => {
    setLoading(true);
    setError(null);
    try {
      const params: Record<string, string | number> = {
        status,
        limit: 200,
        offset: 0,
      };
      if (provider !== 'all') {
        params.provider = provider;
      }
      const resp = await api.get<AiEmailPairsResponse>('/api/integrations/ai-email-pairs', {
        params,
      });
      setItems(resp.data?.items ?? []);
    } catch (e: any) {
      const msg = e?.response?.data?.detail || e?.message || 'Не удалось загрузить AI email pairs';
      setError(String(msg));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadPairs();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status, provider]);

  const shortText = (value: string, maxLen: number): string => {
    if (!value) return '';
    if (value.length <= maxLen) return value;
    return value.slice(0, maxLen) + '…';
  };

  const onRowClick = (pair: AiEmailPairDto) => {
    setSelected(pair);
    setModalOpen(true);
  };

  const updatePairStatus = async (pair: AiEmailPairDto, nextStatus: StatusFilter) => {
    setError(null);
    try {
      const resp = await api.post<AiEmailPairDto>(
        `/api/integrations/ai-email-pairs/${pair.id}/status`,
        { status: nextStatus },
      );
      const updated = resp.data;
      setItems((prev) => prev.map((p) => (p.id === updated.id ? updated : p)));
      if (selected && selected.id === updated.id) {
        setSelected(updated);
      }
    } catch (e: any) {
      const msg = e?.response?.data?.detail || e?.message || 'Не удалось изменить статус пары';
      setError(String(msg));
    }
  };

  const filteredItems = useMemo(() => items, [items]);

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      <FixedHeader />
      <div className="pt-16 px-4 py-6 max-w-6xl w-full mx-auto flex-1 flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold">AI Email Training</h1>
            <p className="text-sm text-gray-600 max-w-3xl">
              Пары «клиентский вопрос → наш ответ» из Gmail, которые используются как база
              знаний для будущих AI-подсказок. Админ может утвердить или отклонить каждую пару.
            </p>
          </div>
          {loading && <div className="text-xs text-gray-500">Loading…</div>}
        </div>

        {error && (
          <div className="text-xs text-red-700 border border-red-200 bg-red-50 rounded px-2 py-1" role="alert">
            {error}
          </div>
        )}

        <Card className="p-3 flex items-center justify-between text-xs">
          <div className="flex items-center gap-3">
            <label className="flex items-center gap-1">
              <span className="text-gray-600">Status:</span>
              <select
                className="border rounded px-1 py-0.5 bg-white"
                value={status}
                onChange={(e) => setStatus(e.target.value as StatusFilter)}
              >
                {STATUS_OPTIONS.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex items-center gap-1">
              <span className="text-gray-600">Provider:</span>
              <select
                className="border rounded px-1 py-0.5 bg-white"
                value={provider}
                onChange={(e) => setProvider(e.target.value as ProviderFilter)}
              >
                <option value="all">All</option>
                <option value="gmail">Gmail</option>
              </select>
            </label>
          </div>
          <button
            type="button"
            className="px-3 py-1.5 rounded border border-gray-300 bg-white hover:bg-gray-50"
            onClick={() => void loadPairs()}
          >
            Refresh
          </button>
        </Card>

        <Card className="p-3 flex-1">
          {filteredItems.length === 0 ? (
            <div className="text-xs text-gray-500">Нет пар для отображения (попробуйте другой статус).</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full text-xs">
                <thead>
                  <tr className="border-b bg-gray-50 text-gray-600">
                    <th className="text-left px-2 py-1">Provider</th>
                    <th className="text-left px-2 py-1">Integration</th>
                    <th className="text-left px-2 py-1">Thread ID</th>
                    <th className="text-left px-2 py-1">Client</th>
                    <th className="text-left px-2 py-1">Reply</th>
                    <th className="text-left px-2 py-1">Status</th>
                    <th className="text-left px-2 py-1">Created</th>
                    <th className="text-left px-2 py-1">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredItems.map((pair) => (
                    <tr
                      key={pair.id}
                      className="border-b last:border-0 hover:bg-gray-50 cursor-pointer"
                      onClick={() => onRowClick(pair)}
                    >
                      <td className="px-2 py-1 align-top text-gray-700">{pair.provider_code}</td>
                      <td className="px-2 py-1 align-top">
                        <div className="text-gray-900">{pair.integration_display_name}</div>
                        <div className="text-[10px] text-gray-500 font-mono">{pair.integration_account_id}</div>
                      </td>
                      <td className="px-2 py-1 align-top text-[11px] text-gray-600">
                        {pair.thread_id || '—'}
                      </td>
                      <td className="px-2 py-1 align-top text-gray-800 max-w-xs">
                        {shortText(pair.client_text, 120)}
                      </td>
                      <td className="px-2 py-1 align-top text-gray-800 max-w-xs">
                        {shortText(pair.our_reply_text, 120)}
                      </td>
                      <td className="px-2 py-1 align-top">
                        <span
                          className={
                            pair.status === 'approved'
                              ? 'inline-flex items-center px-2 py-0.5 rounded-full text-[10px] bg-green-100 text-green-800'
                              : pair.status === 'rejected'
                                ? 'inline-flex items-center px-2 py-0.5 rounded-full text-[10px] bg-red-100 text-red-800'
                                : 'inline-flex items-center px-2 py-0.5 rounded-full text-[10px] bg-yellow-100 text-yellow-800'
                          }
                        >
                          {pair.status}
                        </span>
                      </td>
                      <td className="px-2 py-1 align-top text-gray-600">
                        {pair.created_at ? new Date(pair.created_at).toLocaleString() : '—'}
                      </td>
                      <td
                        className="px-2 py-1 align-top"
                        onClick={(e) => {
                          e.stopPropagation();
                        }}
                      >
                        <div className="flex flex-wrap gap-1">
                          {pair.status !== 'approved' && (
                            <button
                              type="button"
                              className="px-2 py-0.5 rounded border border-green-300 bg-white text-[11px] text-green-700 hover:bg-green-50"
                              onClick={() => void updatePairStatus(pair, 'approved')}
                            >
                              Approve
                            </button>
                          )}
                          {pair.status !== 'rejected' && (
                            <button
                              type="button"
                              className="px-2 py-0.5 rounded border border-red-300 bg-white text-[11px] text-red-700 hover:bg-red-50"
                              onClick={() => void updatePairStatus(pair, 'rejected')}
                            >
                              Reject
                            </button>
                          )}
                          {pair.status !== 'new' && (
                            <button
                              type="button"
                              className="px-2 py-0.5 rounded border border-gray-300 bg-white text-[11px] text-gray-700 hover:bg-gray-50"
                              onClick={() => void updatePairStatus(pair, 'new')}
                            >
                              Reset
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>

      <Dialog open={modalOpen} onOpenChange={(open) => !open && setModalOpen(false)}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle>AI Email Pair</DialogTitle>
          </DialogHeader>
          {selected ? (
            <div className="space-y-3 text-xs">
              <div className="flex flex-wrap gap-3 text-gray-600">
                <span>
                  Provider: <span className="font-mono text-gray-800">{selected.provider_code}</span>
                </span>
                <span>
                  Integration: <span className="font-mono text-gray-800">{selected.integration_display_name}</span>
                </span>
                {selected.thread_id && (
                  <span>
                    Thread: <span className="font-mono text-gray-800">{selected.thread_id}</span>
                  </span>
                )}
                <span>
                  Status: <span className="font-semibold text-gray-800">{selected.status}</span>
                </span>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="border rounded p-2 bg-gray-50">
                  <div className="font-semibold text-gray-700 mb-1">Client message</div>
                  <pre className="whitespace-pre-wrap break-words text-[11px] text-gray-800">
                    {selected.client_text}
                  </pre>
                </div>
                <div className="border rounded p-2 bg-gray-50">
                  <div className="font-semibold text-gray-700 mb-1">Our reply</div>
                  <pre className="whitespace-pre-wrap break-words text-[11px] text-gray-800">
                    {selected.our_reply_text}
                  </pre>
                </div>
              </div>
            </div>
          ) : (
            <div className="text-xs text-gray-500">Пара не выбрана.</div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}