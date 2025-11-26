import { useEffect, useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

import FixedHeader from '@/components/FixedHeader';
import { Card } from '@/components/ui/card';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import api from '@/lib/apiClient';

interface IntegrationAccountDto {
  id: string;
  provider_code: string;
  provider_name: string;
  owner_user_id: string | null;
  owner_email: string | null;
  external_account_id: string | null;
  display_name: string | null;
  status: string;
  last_sync_at: string | null;
  meta: Record<string, any> | null;
}

interface GmailSyncSummaryDto {
  account_id: string;
  messages_fetched: number;
  messages_upserted: number;
  pairs_created: number;
  pairs_skipped_existing: number;
  errors: string[];
  last_sync_at: string | null;
  meta: Record<string, any> | null;
}

interface IntegrationAccountsResponse {
  accounts: IntegrationAccountDto[];
  count: number;
}

type FlashKind = 'success' | 'error';

interface FlashMessage {
  kind: FlashKind;
  text: string;
}

const GMAIL_ERROR_REASONS: Record<string, string> = {
  missing_code: 'Google вернул callback без параметра code. Попробуйте ещё раз.',
  missing_state: 'В ответе Google отсутствует параметр state. Попробуйте ещё раз.',
  invalid_state: 'Не удалось распарсить state из Google OAuth. Попробуйте ещё раз.',
  missing_owner: 'В state не найден owner_user_id. Попросите администратора переподключить.',
  server_config: 'Gmail OAuth не настроен на сервере (client id/secret). Обратитесь к администратору.',
  token_http: 'Ошибка сети при обращении к Google token endpoint.',
  token_failed: 'Google вернул ошибку при обмене кода на токен.',
  missing_access_token: 'Google не вернул access_token. Попробуйте ещё раз.',
  profile_failed: 'Не удалось получить профиль Gmail (users.me.profile).',
  persist_failed: 'Сервер не смог сохранить интеграцию в БД. Попробуйте ещё раз или проверьте логи.',
};

export default function AdminIntegrationsPage() {
  const navigate = useNavigate();
  const location = useLocation();

  const [accounts, setAccounts] = useState<IntegrationAccountDto[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [flash, setFlash] = useState<FlashMessage | null>(null);
  const [gmailLoading, setGmailLoading] = useState(false);
  const [syncLoadingAccountId, setSyncLoadingAccountId] = useState<string | null>(null);
  const [syncResult, setSyncResult] = useState<GmailSyncSummaryDto | null>(null);
  const [syncModalOpen, setSyncModalOpen] = useState(false);

  // Handle ?gmail=connected|error&reason=... from backend callback
  useEffect(() => {
    const search = location.search;
    if (!search) return;

    const params = new URLSearchParams(search);
    const gmail = params.get('gmail');
    if (!gmail) return;

    if (gmail === 'connected') {
      setFlash({ kind: 'success', text: 'Gmail аккаунт успешно подключён.' });
    } else if (gmail === 'error') {
      const reason = params.get('reason') ?? 'unknown_error';
      const mapped = GMAIL_ERROR_REASONS[reason] ?? 'Не удалось подключить Gmail. Попробуйте ещё раз.';
      setFlash({ kind: 'error', text: mapped });
    }

    // Strip query params so message не повторяется при F5.
    navigate(location.pathname, { replace: true });
  }, [location.pathname, location.search, navigate]);

  const loadAccounts = async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await api.get<IntegrationAccountsResponse>('/api/integrations/accounts');
      setAccounts(resp.data?.accounts ?? []);
    } catch (e: any) {
      const msg = e?.response?.data?.detail || e?.message || 'Не удалось загрузить интеграции';
      setError(String(msg));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadAccounts();
  }, []);

  const formatDateTime = (value: string | null | undefined): string => {
    if (!value) return '—';
    try {
      return new Date(value).toLocaleString();
    } catch {
      return value;
    }
  };

  const formatShortDateTime = (value: string | null | undefined): string => {
    if (!value) return '—';
    try {
      const d = new Date(value);
      return d.toLocaleString(undefined, {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return value;
    }
  };

  const getLastSyncSummary = (acc: IntegrationAccountDto): GmailSyncSummaryDto | null => {
    const raw = acc.meta?.last_sync_summary;
    if (!raw || typeof raw !== 'object') return null;
    return {
      account_id: String(raw.account_id ?? acc.id),
      messages_fetched: Number(raw.messages_fetched ?? 0),
      messages_upserted: Number(raw.messages_upserted ?? 0),
      pairs_created: Number(raw.pairs_created ?? 0),
      pairs_skipped_existing: Number(raw.pairs_skipped_existing ?? 0),
      errors: Array.isArray(raw.errors) ? raw.errors.map(String) : [],
      last_sync_at: typeof raw.finished_at === 'string' ? raw.finished_at : acc.last_sync_at,
      meta: acc.meta ?? {},
    };
  };

  const hasGmailAccount = useMemo(
    () => accounts.some((a) => a.provider_code === 'gmail' && a.status === 'active'),
    [accounts],
  );

  const handleConnectGmail = async () => {
    setGmailLoading(true);
    setError(null);
    try {
      const resp = await api.post<{ auth_url: string }>('/api/integrations/gmail/auth-url');
      const url = resp.data?.auth_url;
      if (!url) {
        setError('Сервер вернул некорректный auth_url');
        return;
      }
      window.location.href = url;
    } catch (e: any) {
      const msg = e?.response?.data?.detail || e?.message || 'Не удалось получить Gmail OAuth URL';
      setError(String(msg));
    } finally {
      setGmailLoading(false);
    }
  };

  const updateAccountInState = (updated: IntegrationAccountDto) => {
    setAccounts((prev) => prev.map((acc) => (acc.id === updated.id ? updated : acc)));
  };

  const handleRunSyncNow = async (account: IntegrationAccountDto) => {
    setError(null);
    setSyncLoadingAccountId(account.id);
    try {
      const resp = await api.post<GmailSyncSummaryDto>(
        `/api/integrations/accounts/${account.id}/sync-now`,
      );
      const result = resp.data;
      setSyncResult(result);
      setSyncModalOpen(true);
      // Best-effort refresh of accounts to reflect new last_sync_at/meta.
      void loadAccounts();
      setFlash({ kind: 'success', text: 'Gmail sync completed.' });
    } catch (e: any) {
      const msg = e?.response?.data?.detail || e?.message || 'Не удалось выполнить синхронизацию';
      setError(String(msg));
    } finally {
      setSyncLoadingAccountId(null);
    }
  };

  const withAccountAction = async (
    account: IntegrationAccountDto,
    action: 'enable' | 'disable' | 'resync',
  ) => {
    setError(null);
    try {
      const resp = await api.post<IntegrationAccountDto>(
        `/api/integrations/accounts/${account.id}/${action}`,
      );
      updateAccountInState(resp.data);
      if (action === 'resync') {
        setFlash({ kind: 'success', text: 'Ручной ресинк запрошен, воркер обработает его в ближайший цикл.' });
      }
    } catch (e: any) {
      const msg = e?.response?.data?.detail || e?.message || 'Не удалось выполнить действие над интеграцией';
      setError(String(msg));
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      <FixedHeader />
      <div className="pt-16 px-4 py-6 max-w-6xl w-full mx-auto flex-1 flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold">Integrations</h1>
            <p className="text-sm text-gray-600 max-w-3xl">
              Подключение внешних провайдеров (сейчас: Gmail) и обзор всех интеграционных аккаунтов.
            </p>
          </div>
          {loading && <div className="text-xs text-gray-500">Loading…</div>}
        </div>

        {flash && (
          <div
            className={
              flash.kind === 'success'
                ? 'text-xs text-green-700 border border-green-200 bg-green-50 rounded px-2 py-1'
                : 'text-xs text-red-700 border border-red-200 bg-red-50 rounded px-2 py-1'
            }
            role="alert"
          >
            {flash.text}
          </div>
        )}

        {error && (
          <div className="text-xs text-red-700 border border-red-200 bg-red-50 rounded px-2 py-1" role="alert">
            {error}
          </div>
        )}

        <div className="grid grid-cols-2 gap-4">
          <Card className="p-4 flex flex-col justify-between">
            <div>
              <h2 className="text-lg font-semibold">Gmail</h2>
              <p className="text-sm text-gray-600 mt-1">
                Подключите Gmail аккаунт, чтобы забирать исторические письма и строить AI-тренировочные пары.
              </p>
              <p className="mt-1 text-[11px] text-gray-500">
                Gmail используется только для чтения входящих/исходящих писем и обучения AI.
                Отправка ответов клиентам будет происходить через раздел Messages.
              </p>
            </div>
            <div className="mt-3 flex items-center justify-between">
              <div className="text-xs text-gray-600">
                {hasGmailAccount ? 'Есть активные Gmail интеграции.' : 'Пока нет активных Gmail аккаунтов.'}
              </div>
              <button
                type="button"
                onClick={handleConnectGmail}
                disabled={gmailLoading}
                className="px-3 py-1.5 rounded bg-blue-600 text-white text-xs font-medium hover:bg-blue-700 disabled:opacity-60"
              >
                {gmailLoading ? 'Redirecting…' : 'Connect Gmail account'}
              </button>
            </div>
          </Card>
        </div>

        <Card className="p-4 mt-2">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold">Integration Accounts</h2>
            <button
              type="button"
              onClick={() => void loadAccounts()}
              className="px-3 py-1.5 rounded border border-gray-300 bg-white text-xs hover:bg-gray-50"
            >
              Refresh
            </button>
          </div>

          {accounts.length === 0 ? (
            <div className="text-xs text-gray-500">Интеграционные аккаунты пока не найдены.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full text-xs">
                <thead>
                  <tr className="border-b bg-gray-50 text-gray-600">
                    <th className="text-left px-2 py-1">Provider</th>
                    <th className="text-left px-2 py-1">Account</th>
                    <th className="text-left px-2 py-1">Owner</th>
                    <th className="text-left px-2 py-1">Status</th>
                    <th className="text-left px-2 py-1">Last Sync</th>
                    <th className="text-left px-2 py-1">Summary</th>
                    <th className="text-left px-2 py-1">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {accounts.map((acc) => (
                    <tr key={acc.id} className="border-b last:border-0">
                      <td className="px-2 py-1 align-top">
                        <div className="font-medium text-gray-900">{acc.provider_name}</div>
                        <div className="text-[10px] text-gray-500 font-mono">{acc.provider_code}</div>
                      </td>
                      <td className="px-2 py-1 align-top">
                        <div className="text-gray-900">
                          {acc.display_name || acc.external_account_id || '—'}
                        </div>
                        {acc.external_account_id && (
                          <div className="text-[11px] text-gray-500">{acc.external_account_id}</div>
                        )}
                      </td>
                      <td className="px-2 py-1 align-top">
                        <div className="text-gray-900">{acc.owner_email || '—'}</div>
                        {acc.owner_user_id && (
                          <div className="text-[10px] text-gray-500 font-mono">{acc.owner_user_id}</div>
                        )}
                      </td>
                      <td className="px-2 py-1 align-top">
                        <span
                          className={
                            acc.status === 'active'
                              ? 'inline-flex items-center px-2 py-0.5 rounded-full text-[10px] bg-green-100 text-green-800'
                              : 'inline-flex items-center px-2 py-0.5 rounded-full text-[10px] bg-gray-100 text-gray-700'
                          }
                        >
                          {acc.status}
                        </span>
                      </td>
                      <td className="px-2 py-1 align-top text-gray-700">
                        {formatDateTime(acc.last_sync_at)}
                      </td>
                      <td className="px-2 py-1 align-top text-gray-700">
                        {(() => {
                          const summary = getLastSyncSummary(acc);
                          if (!summary) return '—';
                          const parts: string[] = [];
                          parts.push(`msgs: ${summary.messages_upserted}`);
                          parts.push(`pairs: ${summary.pairs_created}`);
                          if ((summary.errors || []).length > 0) {
                            parts.push(`errors: ${summary.errors.length}`);
                          }
                          return (
                            <div>
                              <div>{parts.join(' · ')}</div>
                              <div className="text-[10px] text-gray-400">
                                {summary.last_sync_at ? `at ${formatShortDateTime(summary.last_sync_at)}` : ''}
                              </div>
                            </div>
                          );
                        })()}
                      </td>
                      <td className="px-2 py-1 align-top">
                        <div className="flex flex-wrap gap-1">
                          {acc.status === 'active' ? (
                            <button
                              type="button"
                              className="px-2 py-0.5 rounded border border-gray-300 bg-white text-[11px] hover:bg-gray-50"
                              onClick={() => void withAccountAction(acc, 'disable')}
                            >
                              Disable
                            </button>
                          ) : (
                            <button
                              type="button"
                              className="px-2 py-0.5 rounded border border-gray-300 bg-white text-[11px] hover:bg-gray-50"
                              onClick={() => void withAccountAction(acc, 'enable')}
                            >
                              Enable
                            </button>
                          )}
                          <button
                            type="button"
                            className="px-2 py-0.5 rounded border border-gray-300 bg-white text-[11px] hover:bg-gray-50"
                            onClick={() => void withAccountAction(acc, 'resync')}
                          >
                            Request resync
                          </button>
                          {acc.provider_code === 'gmail' && (
                            <button
                              type="button"
                              className="px-2 py-0.5 rounded border border-blue-300 bg-white text-[11px] text-blue-700 hover:bg-blue-50 disabled:opacity-60"
                              disabled={!!syncLoadingAccountId}
                              onClick={() => void handleRunSyncNow(acc)}
                            >
                              {syncLoadingAccountId === acc.id ? 'Running…' : 'Run sync now'}
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

      <Dialog open={syncModalOpen} onOpenChange={(open) => !open && setSyncModalOpen(false)}>
        <DialogContent className="max-w-lg text-sm">
          <DialogHeader>
            <DialogTitle>Gmail sync result</DialogTitle>
          </DialogHeader>
          {syncResult ? (
            <div className="space-y-2">
              <div className="text-xs text-gray-600">
                Для аккаунта <span className="font-mono">{syncResult.account_id}</span>:
              </div>
              <ul className="text-xs text-gray-800 list-disc list-inside space-y-0.5">
                <li>
                  Сообщений получено: <span className="font-semibold">{syncResult.messages_fetched}</span>
                </li>
                <li>
                  Сообщений записано/обновлено: <span className="font-semibold">{syncResult.messages_upserted}</span>
                </li>
                <li>
                  Пары создано: <span className="font-semibold">{syncResult.pairs_created}</span>
                  {syncResult.pairs_skipped_existing > 0 && (
                    <span className="text-gray-500">
                      {' '}
                      (пропущено существующих: {syncResult.pairs_skipped_existing})
                    </span>
                  )}
                </li>
              </ul>
              {Array.isArray(syncResult.errors) && syncResult.errors.length > 0 && (
                <div className="mt-2">
                  <div className="text-xs font-semibold text-red-700">Ошибки:</div>
                  <ul className="mt-1 text-xs text-red-700 list-disc list-inside space-y-0.5">
                    {syncResult.errors.map((err, idx) => (
                      <li key={idx}>{err}</li>
                    ))}
                  </ul>
                </div>
              )}
              <div className="mt-2 text-[11px] text-gray-500">
                Последний sync:{' '}
                {formatShortDateTime(syncResult.last_sync_at)}
              </div>
            </div>
          ) : (
            <div className="text-xs text-gray-500">Результат синхронизации недоступен.</div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
