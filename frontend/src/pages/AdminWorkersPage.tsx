import React, { useEffect, useState } from "react";
import FixedHeader from "@/components/FixedHeader";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ebayApi, EbayTokenStatusAccount, TokenRefreshWorkerStatus, EbayTokenRefreshLogResponse } from "../api/ebay";
import { EbayWorkersPanel } from "../components/workers/EbayWorkersPanel";

interface EbayAccountWithToken {
  id: string;
  org_id: string;
  ebay_user_id: string;
  username: string | null;
  house_name: string;
  purpose: string;
  connected_at: string;
  is_active: boolean;
}

const AdminWorkersPage: React.FC = () => {
  const [accounts, setAccounts] = useState<EbayAccountWithToken[]>([]);
  const [accountsLoading, setAccountsLoading] = useState(false);
  const [accountsError, setAccountsError] = useState<string | null>(null);
  const [selectedAccountId, setSelectedAccountId] = useState<string | null>(null);

  // Token refresh visibility state
  const [tokenStatus, setTokenStatus] = useState<EbayTokenStatusAccount[] | null>(null);
  const [tokenStatusError, setTokenStatusError] = useState<string | null>(null);
  const [tokenStatusLoading, setTokenStatusLoading] = useState(false);
  const [workerStatus, setWorkerStatus] = useState<TokenRefreshWorkerStatus | null>(null);

  // Per-account refresh log modal state
  const [logModalOpen, setLogModalOpen] = useState(false);
  const [logModalLoading, setLogModalLoading] = useState(false);
  const [logModalError, setLogModalError] = useState<string | null>(null);
  const [logModalData, setLogModalData] = useState<EbayTokenRefreshLogResponse | null>(null);

  useEffect(() => {
    const loadAccountsAndTokens = async () => {
      try {
        setAccountsLoading(true);
        setAccountsError(null);
        const data = await ebayApi.getAccounts(true);
        setAccounts(data || []);
        if (!selectedAccountId && data && data.length > 0) {
          setSelectedAccountId(data[0].id);
        }
      } catch (e: any) {
        console.error("Failed to load eBay accounts for workers", e);
        setAccountsError(e?.response?.data?.detail || "Failed to load eBay accounts");
      } finally {
        setAccountsLoading(false);
      }

      try {
        setTokenStatusLoading(true);
        setTokenStatusError(null);
        const [statusResp, workerResp] = await Promise.all([
          ebayApi.getEbayTokenStatus(),
          ebayApi.getTokenRefreshWorkerStatus(),
        ]);
        setTokenStatus(statusResp.accounts || []);
        setWorkerStatus(workerResp);
      } catch (e: any) {
        console.error("Failed to load token/worker status", e);
        setTokenStatusError(e?.response?.data?.detail || e.message || "Failed to load token status");
      } finally {
        setTokenStatusLoading(false);
      }
    };

    loadAccountsAndTokens();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const selectedAccount = selectedAccountId
    ? accounts.find((a) => a.id === selectedAccountId) || null
    : null;

  const accountLabel = selectedAccount
    ? selectedAccount.house_name || selectedAccount.username || selectedAccount.id
    : "";

  return (
    <div className="min-h-screen bg-gray-50">
      <FixedHeader />
      {/* Reduce top padding so the header block "sticks" closer to the nav bar */}
      <main className="w-full pt-14 px-4 sm:px-6 lg:px-10 py-6">
        <div className="w-full mx-auto space-y-3">
          {/* Top row: title (2) + compact account selector (3) + compact token worker summary (4,5) */}
          <div className="flex flex-col xl:flex-row xl:items-start xl:justify-between gap-3">
            <div className="flex-1 min-w-0 flex items-center gap-2">
              <h1 className="text-2xl font-semibold tracking-tight">eBay Workers</h1>
              <span
                className="inline-flex items-center justify-center h-5 w-5 rounded-full border border-gray-300 text-[11px] font-semibold text-gray-600 cursor-default"
                title={
                  'Централизованный интерфейс управления фоновыми воркерами eBay. Здесь можно включать/выключать воркеры по аккаунту, запускать их вручную и смотреть подробные логи выполнения.'
                }
              >
                i
              </span>
            </div>

            <div className="flex flex-col md:flex-row gap-3 w-full xl:w-auto">
              {/* Compact account selection (3) */}
              <Card className="flex-1 min-w-[260px] p-0">
                <CardHeader className="py-2 px-3 pb-1">
                  <CardTitle className="text-sm font-semibold">Account selection</CardTitle>
                </CardHeader>
                <CardContent className="py-1 px-3">
                  {accountsLoading && (
                    <div className="text-xs text-gray-600">Loading eBay accounts...</div>
                  )}
                  {accountsError && (
                    <div className="text-xs text-red-600 mb-1">{accountsError}</div>
                  )}
                  {accounts.length === 0 && !accountsLoading && !accountsError && (
                    <div className="text-xs text-gray-600">
                      Нет подключённых eBay аккаунтов. Сначала подключите аккаунт в разделе
                      <span className="font-semibold"> Admin → eBay Connection</span>.
                    </div>
                  )}
                  {accounts.length > 0 && (
                    <div className="flex items-center gap-2">
                      <Label className="text-[11px] text-gray-700">eBay account</Label>
                      <Select
                        value={selectedAccountId || accounts[0]?.id}
                        onValueChange={(val) => setSelectedAccountId(val)}
                      >
                        <SelectTrigger className="h-8 w-48 text-[11px]">
                          <SelectValue placeholder="Select eBay account" />
                        </SelectTrigger>
                        <SelectContent>
                          {accounts.map((acc) => (
                            <SelectItem key={acc.id} value={acc.id}>
                              {acc.house_name || acc.username || acc.id} ({acc.ebay_user_id})
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  )}
                </CardContent>
              </Card>
n              {/* Compact token refresh worker summary (4,5) */}
              <Card className="flex-1 min-w-[260px] p-0">
                <CardHeader className="py-2 px-3 pb-1">
                  <CardTitle className="text-sm font-semibold">Token refresh status</CardTitle>
                  <CardDescription className="text-[11px] text-gray-600">
                    Состояние воркера, который обновляет eBay OAuth токены.
                  </CardDescription>
                </CardHeader>
                <CardContent className="py-1 px-3">
                  {workerStatus ? (
                    <div className="text-[11px] space-y-0.5">
                      <div>
                        <span className="font-semibold">Interval:</span> every {workerStatus.interval_seconds} seconds
                      </div>
                      <div>
                        <span className="font-semibold">Last started:</span> {workerStatus.last_started_at || '–'}
                      </div>
                      <div>
                        <span className="font-semibold">Last finished:</span> {workerStatus.last_finished_at || '–'}
                      </div>
                      <div>
                        <span className="font-semibold">Status:</span> {workerStatus.last_status || '–'}
                      </div>
                      {workerStatus.next_run_estimated_at && (
                        <div>
                          <span className="font-semibold">Next run:</span> {workerStatus.next_run_estimated_at}
                        </div>
                      )}
                      {workerStatus.last_error_message && (
                        <div className="text-red-600">
                          Last error: {workerStatus.last_error_message}
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="text-[11px] text-gray-600">No worker heartbeat yet.</div>
                  )}
                </CardContent>
              </Card>
            </div>
          </div>

          {/* Token refresh visibility block – per-account table (6) */}
          <Card>
            <CardHeader className="py-2 px-3 pb-1">
              <CardTitle className="text-sm font-semibold">Per-account token status</CardTitle>
              <CardDescription className="text-[11px] text-gray-600">
                Для каждого eBay аккаунта показывается срок жизни токена и последние попытки refresh.
              </CardDescription>
            </CardHeader>
            <CardContent className="py-2 px-3">
              {tokenStatusLoading && (
                <div className="text-xs text-gray-600 mb-2">Loading token status...</div>
              )}
              {tokenStatusError && (
                <div className="text-xs text-red-600 mb-2">{tokenStatusError}</div>
              )}
              {tokenStatus && tokenStatus.length > 0 && (
                <div className="mt-1 overflow-x-auto">
                  <table className="min-w-full text-xs border">
                    <thead>
                      <tr className="bg-gray-100">
                        <th className="px-2 py-1 text-left">Account</th>
                        <th className="px-2 py-1 text-left">eBay user</th>
                        <th className="px-2 py-1 text-left">Status</th>
                        <th className="px-2 py-1 text-left">Expires in</th>
                        <th className="px-2 py-1 text-left">Last refresh</th>
                        <th className="px-2 py-1 text-left">Failures in row</th>
                        <th className="px-2 py-1 text-left">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {tokenStatus.map((row) => {
                        const ttl = row.expires_in_seconds;
                        let ttlLabel = '–';
                        if (typeof ttl === 'number') {
                          if (ttl <= 0) ttlLabel = `${ttl} s`; else {
                            const mins = Math.floor(ttl / 60);
                            const secs = ttl % 60;
                            ttlLabel = `${mins}m ${secs}s`;
                          }
                        }
                        const colorByStatus: Record<string, string> = {
                          ok: 'bg-green-100 text-green-800',
                          expiring_soon: 'bg-yellow-100 text-yellow-800',
                          expired: 'bg-red-100 text-red-800',
                          error: 'bg-red-100 text-red-800',
                          not_connected: 'bg-gray-100 text-gray-700',
                          unknown: 'bg-gray-100 text-gray-700',
                        };
                        const statusLabelMap: Record<string, string> = {
                          ok: 'OK',
                          expiring_soon: 'Expiring soon',
                          expired: 'Expired',
                          error: 'Error',
                          not_connected: 'Not connected',
                          unknown: 'Unknown',
                        };
                        const statusClass = colorByStatus[row.status] || 'bg-gray-100 text-gray-700';
                        return (
                          <tr key={row.account_id} className="border-t">
                            <td className="px-2 py-1 whitespace-nowrap">
                              {row.account_name || row.account_id}
                            </td>
                            <td className="px-2 py-1 whitespace-nowrap">{row.ebay_user_id || '–'}</td>
                            <td className="px-2 py-1 whitespace-nowrap">
                              <span className={`px-2 py-0.5 rounded text-[11px] font-semibold ${statusClass}`}>
                                {statusLabelMap[row.status] || row.status}
                              </span>
                            </td>
                            <td className="px-2 py-1 whitespace-nowrap">{ttlLabel}</td>
                            <td className="px-2 py-1 whitespace-nowrap">
                              {row.last_refresh_at || '–'}
                              {row.last_refresh_error && (
                                <div className="text-[10px] text-red-600 max-w-xs truncate">
                                  {row.last_refresh_error}
                                </div>
                              )}
                            </td>
                            <td className="px-2 py-1 whitespace-nowrap text-center">
                              {row.refresh_failures_in_row}
                            </td>
                            <td className="px-2 py-1 whitespace-nowrap">
                              <button
                                className="px-2 py-0.5 border rounded text-[11px] bg-white hover:bg-gray-50"
                                onClick={async () => {
                                  try {
                                    setLogModalError(null);
                                    setLogModalLoading(true);
                                    setLogModalOpen(true);
                                    const data = await ebayApi.getEbayTokenRefreshLog(row.account_id, 50);
                                    setLogModalData(data);
                                  } catch (e: any) {
                                    console.error("Failed to load token refresh log", e);
                                    setLogModalError(e?.response?.data?.detail || e.message || "Failed to load refresh log");
                                  } finally {
                                    setLogModalLoading(false);
                                  }
                                }}
                              >
                                View log
                              </button>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
              {tokenStatus && tokenStatus.length === 0 && !tokenStatusLoading && !tokenStatusError && (
                <div className="text-xs text-gray-600">No eBay accounts found for token status.</div>
              )}
            </CardContent>
          </Card>

          {/* Token refresh log modal */}
          {logModalOpen && (
            <div className="fixed inset-0 bg-black bg-opacity-40 flex items-center justify-center z-50">
              <div className="bg-white rounded shadow-lg max-w-3xl w-full max-h-[80vh] overflow-auto p-4 text-xs">
                <div className="flex items-center justify-between mb-2">
                  <div className="font-semibold">Token refresh log</div>
                  <button
                    className="text-gray-600 text-sm"
                    onClick={() => {
                      setLogModalOpen(false);
                      setLogModalData(null);
                      setLogModalError(null);
                    }}
                  >
                    Close
                  </button>
                </div>
                {logModalLoading && <div className="mb-2">Loading...</div>}
                {logModalError && (
                  <div className="mb-2 text-red-600">{logModalError}</div>
                )}
                {logModalData && (
                  <>
                    <div className="mb-3 text-gray-700">
                      Account: {logModalData.account.house_name || logModalData.account.id}{' '}
                      {logModalData.account.ebay_user_id && (
                        <span className="text-gray-500">(eBay user: {logModalData.account.ebay_user_id})</span>
                      )}
                    </div>
                    {logModalData.logs.length === 0 && !logModalLoading && (
                      <div className="text-gray-600">No refresh attempts recorded yet.</div>
                    )}
                    {logModalData.logs.length > 0 && (
                      <table className="min-w-full text-[11px] border">
                        <thead>
                          <tr className="bg-gray-100">
                            <th className="px-2 py-1 text-left">Started at</th>
                            <th className="px-2 py-1 text-left">Finished at</th>
                            <th className="px-2 py-1 text-left">Result</th>
                            <th className="px-2 py-1 text-left">Error</th>
                            <th className="px-2 py-1 text-left">Old expires</th>
                            <th className="px-2 py-1 text-left">New expires</th>
                            <th className="px-2 py-1 text-left">Triggered by</th>
                          </tr>
                        </thead>
                        <tbody>
                          {logModalData.logs.map((log) => (
                            <tr key={log.id} className="border-t align-top">
                              <td className="px-2 py-1 whitespace-nowrap">{log.started_at || '–'}</td>
                              <td className="px-2 py-1 whitespace-nowrap">{log.finished_at || '–'}</td>
                              <td className="px-2 py-1 whitespace-nowrap">
                                {log.success === null ? 'n/a' : log.success ? 'success' : 'error'}
                                {log.error_code && (
                                  <span className="ml-1 text-gray-500">[{log.error_code}]</span>
                                )}
                              </td>
                              <td className="px-2 py-1 whitespace-pre-wrap max-w-xs">
                                {log.error_message || '–'}
                              </td>
                              <td className="px-2 py-1 whitespace-nowrap">{log.old_expires_at || '–'}</td>
                              <td className="px-2 py-1 whitespace-nowrap">{log.new_expires_at || '–'}</td>
                              <td className="px-2 py-1 whitespace-nowrap">{log.triggered_by}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                  </>
                )}
              </div>
            </div>
          )}

          {selectedAccountId && selectedAccount && (
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Workers for {accountLabel}</CardTitle>
                <CardDescription className="text-sm text-gray-600">
                  Управление отдельными воркерами (Orders, Transactions, Messages и т.д.) для выбранного
                  eBay аккаунта.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <EbayWorkersPanel
                  accountId={selectedAccountId}
                  accountLabel={accountLabel}
                  ebayUserId={selectedAccount.ebay_user_id}
                />
              </CardContent>
            </Card>
          )}
        </div>
      </main>
    </div>
  );
};

export default AdminWorkersPage;
