import React, { useEffect, useState } from "react";
import FixedHeader from "@/components/FixedHeader";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  ebayApi,
  EbayTokenStatusAccount,
  TokenRefreshWorkerStatus,
  EbayTokenRefreshLogResponse,
  EbayTokenRefreshDebugResponse,
  WorkersLoopStatusItem,
  AdminWorkerDto,
} from "../api/ebay";
import { EbayWorkersPanel } from "../components/workers/EbayWorkersPanel";
import { AllWorkerLogsModal } from "../components/AllWorkerLogsModal";
import { formatDateTimeLocal, formatRelativeTime } from "../lib/dateUtils";

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
  const [loopStatus, setLoopStatus] = useState<WorkersLoopStatusItem[] | null>(null);
  const [loopStatusError, setLoopStatusError] = useState<string | null>(null);
  const [loopStatusLoading, setLoopStatusLoading] = useState(false);

  // Per-account refresh log modal state
  const [logModalOpen, setLogModalOpen] = useState(false);
  const [logModalLoading, setLogModalLoading] = useState(false);
  const [logModalError, setLogModalError] = useState<string | null>(null);
  const [logModalData, setLogModalData] = useState<EbayTokenRefreshLogResponse | null>(null);

  // Per-account on-demand debug refresh modal (full HTTP request/response)
  const [debugModalOpen, setDebugModalOpen] = useState(false);
  const [debugModalLoading, setDebugModalLoading] = useState(false);
  const [debugModalError, setDebugModalError] = useState<string | null>(null);
  const [debugModalData, setDebugModalData] = useState<EbayTokenRefreshDebugResponse | null>(null);

  // HTTP-level token request/response logs (from EbayConnectLog via /api/admin/ebay/tokens/logs)
  const [httpLogsModalOpen, setHttpLogsModalOpen] = useState(false);
  const [httpLogsLoading, setHttpLogsLoading] = useState(false);
  const [httpLogsError, setHttpLogsError] = useState<string | null>(null);
  const [httpLogs, setHttpLogs] = useState<any[]>([]);

  // Unified token refresh terminal (scheduled + debug) backed by /api/admin/ebay/tokens/terminal-logs
  const [terminalModalOpen, setTerminalModalOpen] = useState(false);
  const [terminalLoading, setTerminalLoading] = useState(false);
  const [terminalError, setTerminalError] = useState<string | null>(null);
  const [terminalEntries, setTerminalEntries] = useState<any[]>([]);

  // All worker logs modal
  const [allLogsModalOpen, setAllLogsModalOpen] = useState(false);

  // Global background workers (Inventory MV Refresh and future workers)
  const [inventoryWorker, setInventoryWorker] = useState<AdminWorkerDto | null>(null);
  const [inventoryWorkerLoading, setInventoryWorkerLoading] = useState(false);
  const [inventoryWorkerError, setInventoryWorkerError] = useState<string | null>(null);

  const loadTokenStatusAndWorker = async () => {
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

  const loadWorkersLoopStatus = async () => {
    try {
      setLoopStatusLoading(true);
      setLoopStatusError(null);
      const resp = await ebayApi.getWorkersLoopStatus();
      setLoopStatus(resp.loops || []);
    } catch (e: any) {
      console.error("Failed to load workers loop status", e);
      setLoopStatusError(e?.response?.data?.detail || e.message || "Failed to load workers loop status");
    } finally {
      setLoopStatusLoading(false);
    }
  };

  const loadInventoryWorker = async () => {
    try {
      setInventoryWorkerLoading(true);
      setInventoryWorkerError(null);
      const data = await ebayApi.getInventoryMvWorker();
      setInventoryWorker(data);
    } catch (e: any) {
      console.error("Failed to load inventory MV worker status", e);
      setInventoryWorkerError(
        e?.response?.data?.detail || e.message || "Failed to load inventory MV worker status",
      );
    } finally {
      setInventoryWorkerLoading(false);
    }
  };

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

      await Promise.all([
        loadTokenStatusAndWorker(),
        loadWorkersLoopStatus(),
        loadInventoryWorker(),
      ]);
    };

    void loadAccountsAndTokens();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const selectedAccount = selectedAccountId
    ? accounts.find((a) => a.id === selectedAccountId) || null
    : null;

  const accountLabel = selectedAccount
    ? selectedAccount.house_name || selectedAccount.username || selectedAccount.id
    : "";

  const openHttpLogsModal = async () => {
    try {
      setHttpLogsModalOpen(true);
      setHttpLogsLoading(true);
      setHttpLogsError(null);
      // For production tokens, env must be "production"; endpoint is guarded by FEATURE_TOKEN_INFO on backend.
      const resp = await ebayApi.getAdminTokenHttpLogs("production", 100);
      setHttpLogs(resp.logs || []);
    } catch (e: any) {
      console.error("Failed to load token HTTP logs", e);
      setHttpLogsError(e?.response?.data?.detail || e.message || "Failed to load token HTTP logs");
    } finally {
      setHttpLogsLoading(false);
    }
  };

  const openTokenTerminalModal = async () => {
    try {
      setTerminalModalOpen(true);
      setTerminalLoading(true);
      setTerminalError(null);
      const resp = await ebayApi.getAdminTokenTerminalLogs('production', 100);
      const entries = Array.isArray(resp.entries) ? [...resp.entries] : [];
      entries.sort((a: any, b: any) => {
        const ad = a?.created_at ? Date.parse(a.created_at) : 0;
        const bd = b?.created_at ? Date.parse(b.created_at) : 0;
        return bd - ad; // newest first
      });
      setTerminalEntries(entries);
    } catch (e: any) {
      console.error('Failed to load token terminal logs', e);
      setTerminalError(
        e?.response?.data?.detail || e.message || 'Failed to load token terminal logs',
      );
    } finally {
      setTerminalLoading(false);
    }
  };

  const openTokenRefreshDebug = async (accountId: string) => {
    try {
      setDebugModalError(null);
      setDebugModalData(null);
      setDebugModalLoading(true);
      setDebugModalOpen(true);
      const data = await ebayApi.debugRefreshToken(accountId);
      setDebugModalData(data);
      // After a successful debug refresh (which also persists tokens),
      // refresh token status so the UI reflects the new TTL immediately.
      void loadTokenStatusAndWorker();
    } catch (e: any) {
      console.error("Failed to run token refresh debug", e);
      setDebugModalError(
        e?.response?.data?.detail || e.message || "Failed to run token refresh debug",
      );
    } finally {
      setDebugModalLoading(false);
    }
  };

  const buildDebugTerminalText = (payload: EbayTokenRefreshDebugResponse): string => {
    const parts: string[] = [];
    const req = payload.request;
    const res = payload.response;

    parts.push("=== HTTP REQUEST ===");
    if (req) {
      const statusLine = `${req.method || "POST"} ${req.url || ""}`;
      parts.push(statusLine);
      if (req.headers) {
        Object.entries(req.headers).forEach(([k, v]) => {
          parts.push(`${k}: ${String(v)}`);
        });
      }
      parts.push("");
      if (req.body) {
        parts.push(req.body);
      }
    } else {
      parts.push("<no request captured>");
    }

    parts.push("");
    parts.push("=== HTTP RESPONSE ===");
    if (res) {
      const statusLine = `HTTP/1.1 ${res.status_code ?? "?"}${res.reason ? ` ${res.reason}` : ""}`;
      parts.push(statusLine);
      if (res.headers) {
        Object.entries(res.headers).forEach(([k, v]) => {
          parts.push(`${k}: ${String(v)}`);
        });
      }
      parts.push("");
      if (res.body != null) {
        parts.push(res.body);
      }
    } else {
      parts.push("<no response captured>");
    }

    return parts.join("\n");
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <FixedHeader />
      {/* Reduce top padding so the header block "sticks" closer to the nav bar */}
      <main className="w-full pt-14 px-4 sm:px-6 lg:px-10 py-4">
        <div className="w-full mx-auto space-y-3">
          {/* Ultra-compact header row: title + account selection + token worker summary + per-account token status */}
          <div className="flex flex-col gap-2">
            <div className="flex items-center gap-2 text-sm">
              <h1 className="text-lg font-semibold tracking-tight">eBay Workers</h1>
              <span
                className="inline-flex items-center justify-center h-4 w-4 rounded-full border border-gray-300 text-[10px] font-semibold text-gray-600 cursor-default"
                title={
                  'Централизованный интерфейс управления фоновыми воркерами eBay. Здесь можно включать/выключать воркеры по аккаунту, запускать их вручную и смотреть подробные логи выполнения.'
                }
              >
                i
              </span>
            </div>

            <div className="flex flex-col lg:flex-row gap-2 items-stretch">
              {/* Workers loop + token-refresh heartbeat */}
              <Card className="flex-1 min-w-[260px] p-0">
                <CardHeader className="py-1 px-3 pb-0">
                  <CardTitle className="text-[12px] font-semibold">Background loops</CardTitle>
                </CardHeader>
                <CardContent className="py-1 px-3 space-y-1">
                  {loopStatusLoading && (
                    <div className="text-[11px] text-gray-600">Checking loop status...</div>
                  )}
                  {loopStatusError && (
                    <div className="text-[11px] text-red-600">{loopStatusError}</div>
                  )}
                  {!loopStatusLoading && !loopStatusError && loopStatus && (
                    <>
                      {loopStatus.map((loop) => {
                        const isOk = loop.last_status === 'ok' && !loop.stale && !loop.last_error_message;
                        const isError = !!loop.last_error_message || (loop.last_status && loop.last_status !== 'ok');
                        const colorClass = isOk
                          ? 'bg-green-100 text-green-800 border-green-200'
                          : loop.stale
                            ? 'bg-yellow-100 text-yellow-800 border-yellow-200'
                            : isError
                              ? 'bg-red-100 text-red-800 border-red-200'
                              : 'bg-gray-100 text-gray-700 border-gray-200';
                        const label = loop.loop_name === 'ebay_workers'
                          ? 'eBay workers loop'
                          : loop.loop_name === 'token_refresh'
                            ? 'Token refresh loop'
                            : loop.loop_name;
                        const lastFinished = loop.last_finished_at;
                        const rel = lastFinished ? formatRelativeTime(lastFinished) : null;
                        return (
                          <div
                            key={loop.loop_name}
                            className={`flex items-center justify-between text-[11px] border rounded px-2 py-1 ${colorClass}`}
                          >
                            <div className="flex flex-col">
                              <span className="font-semibold">{label}</span>
                              <span className="text-[10px] text-gray-700">
                                Interval: {loop.interval_seconds ? `${Math.round(loop.interval_seconds / 60)} min` : 'n/a'}
                              </span>
                              <span className="text-[10px] text-gray-700">
                                Last run:{' '}
                                {lastFinished ? formatDateTimeLocal(lastFinished) : 'never'}
                                {rel && (
                                  <span className="ml-1 text-gray-500">({rel})</span>
                                )}
                              </span>
                              {loop.last_error_message && (
                                <span className="text-[10px] text-red-700 truncate max-w-xs">
                                  Error: {loop.last_error_message}
                                </span>
                              )}
                            </div>
                            <div className="ml-2 flex flex-col items-end gap-1">
                              <span className="text-[10px] uppercase tracking-wide">
                                {loop.stale ? 'STALE' : isOk ? 'OK' : isError ? 'ERROR' : (loop.last_status || 'UNKNOWN')}
                              </span>
                              {loop.loop_name === 'ebay_workers' && (
                                <button
                                  type="button"
                                  className="px-2 py-0.5 border rounded text-[10px] bg-white hover:bg-gray-50"
                                  onClick={async () => {
                                    try {
                                      await ebayApi
                                        .runEbayWorkersOnce?.();
                                    } catch (e) {
                                      console.error('Failed to trigger workers run-once', e);
                                    } finally {
                                      void loadWorkersLoopStatus();
                                    }
                                  }}
                                >
                                  Run one cycle
                                </button>
                              )}
                              {loop.loop_name === 'token_refresh' && (
                                <button
                                  type="button"
                                  className="px-2 py-0.5 border rounded text-[10px] bg-white hover:bg-gray-50"
                                  onClick={async () => {
                                    try {
                                      await ebayApi.runTokenRefreshWorkerOnce();
                                    } catch (e) {
                                      console.error('Failed to trigger token refresh run-once', e);
                                    } finally {
                                      void loadWorkersLoopStatus();
                                      void loadTokenStatusAndWorker();
                                    }
                                  }}
                                >
                                  Run one cycle
                                </button>
                              )}
                            </div>
                          </div>
                        );
                      })}
                    </>
                  )}
                </CardContent>
              </Card>

              {/* Compact account selection */}
              <Card className="flex-1 min-w-[220px] p-0">
                <CardHeader className="py-1 px-3 pb-0">
                  <CardTitle className="text-[12px] font-semibold">Account selection</CardTitle>
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
              {/* Compact token refresh worker summary (4,5) */}
              <Card className="flex-1 min-w-[220px] p-0">
                <CardHeader className="py-1 px-3 pb-0 flex items-center justify-between">
                  <CardTitle className="text-[12px] font-semibold">Token refresh status</CardTitle>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      className="text-[11px] text-blue-700 hover:underline"
                      onClick={openHttpLogsModal}
                    >
                      View token HTTP logs (JSON)
                    </button>
                    <button
                      type="button"
                      className="text-[11px] text-blue-700 hover:underline"
                      onClick={openTokenTerminalModal}
                    >
                      Open token refresh terminal
                    </button>
                  </div>
                </CardHeader>
                <CardContent className="py-1 px-3">
                  {workerStatus ? (
                    <div className="text-[11px] space-y-0.5">
                      <div>
                        <span className="font-semibold">Interval:</span> every {workerStatus.interval_seconds} seconds
                      </div>
                      <div>
                        <span className="font-semibold">Last started:</span>{' '}
                        {formatDateTimeLocal(workerStatus.last_started_at)}
                        {workerStatus.last_started_at && formatRelativeTime(workerStatus.last_started_at) && (
                          <span className="ml-1 text-[10px] text-gray-500">
                            ({formatRelativeTime(workerStatus.last_started_at)})
                          </span>
                        )}
                      </div>
                      <div>
                        <span className="font-semibold">Last finished:</span>{' '}
                        {formatDateTimeLocal(workerStatus.last_finished_at)}
                        {workerStatus.last_finished_at && formatRelativeTime(workerStatus.last_finished_at) && (
                          <span className="ml-1 text-[10px] text-gray-500">
                            ({formatRelativeTime(workerStatus.last_finished_at)})
                          </span>
                        )}
                      </div>
                      <div>
                        <span className="font-semibold">Status:</span> {workerStatus.last_status || '–'}
                      </div>
                      {workerStatus.next_run_estimated_at && (
                        <div>
                          <span className="font-semibold">Next run:</span>{' '}
                          {formatDateTimeLocal(workerStatus.next_run_estimated_at)}
                          {formatRelativeTime(workerStatus.next_run_estimated_at) && (
                            <span className="ml-1 text-[10px] text-gray-500">
                              ({formatRelativeTime(workerStatus.next_run_estimated_at)})
                            </span>
                          )}
                        </div>
                      )}
                      {workerStatus.last_error_message && (
                        <div className="text-red-600">
                          Last error: {workerStatus.last_error_message}
                        </div>
                      )}
                      <button
                        type="button"
                        className="mt-1 inline-flex items-center text-[11px] text-blue-600 hover:text-blue-800 underline"
                        onClick={openHttpLogsModal}
                      >
                        View raw HTTP token logs
                      </button>
                    </div>
                  ) : (
                    <div className="text-[11px] text-gray-600">No worker heartbeat yet.</div>
                  )}
                </CardContent>
              </Card>
            </div>
          </div>

          {/* Global background workers (Inventory MV Refresh etc.) */}
          <Card className="p-0">
            <CardHeader className="py-1 px-3 pb-0 flex items-center justify-between">
              <CardTitle className="text-[12px] font-semibold">Global Background Workers</CardTitle>
            </CardHeader>
            <CardContent className="py-2 px-3 space-y-2">
              {inventoryWorkerLoading && (
                <div className="text-xs text-gray-600">Loading workers...</div>
              )}
              {inventoryWorkerError && (
                <div className="text-xs text-red-600">{inventoryWorkerError}</div>
              )}
              {inventoryWorker && (
                <div className="border rounded p-2 flex flex-col gap-2 text-xs">
                  <div className="flex items-center justify-between">
                    <div className="flex flex-col">
                      <span className="font-semibold text-sm">
                        {inventoryWorker.display_name || "Inventory MV Refresh"}
                      </span>
                      {inventoryWorker.description && (
                        <span className="text-[11px] text-gray-600">
                          {inventoryWorker.description}
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-[11px] text-gray-600">Disabled</span>
                      <button
                        type="button"
                        className="relative inline-flex h-5 w-10 items-center rounded-full border border-gray-300 bg-white transition-colors"
                        onClick={async () => {
                          const nextEnabled = !inventoryWorker.enabled;
                          try {
                            const updated = await ebayApi.updateInventoryMvWorker({
                              enabled: nextEnabled,
                            });
                            setInventoryWorker(updated);
                            setInventoryWorkerError(null);
                          } catch (e: any) {
                            console.error("Failed to update inventory MV worker", e);
                            setInventoryWorkerError(
                              e?.response?.data?.detail ||
                              e.message ||
                              "Failed to update inventory MV worker",
                            );
                          }
                        }}
                      >
                        <span
                          className={`inline-block h-4 w-4 transform rounded-full bg-gray-400 shadow transition-transform ${
                            inventoryWorker.enabled ? 'translate-x-5 bg-green-500' : 'translate-x-1'
                          }`}
                        />
                      </button>
                      <span className="text-[11px] text-gray-600">Enabled</span>
                    </div>
                  </div>

                  <div className="flex flex-wrap items-center gap-3">
                    <div className="flex items-center gap-2">
                      <Label className="text-[11px] text-gray-700">Interval (seconds)</Label>
                      <input
                        type="number"
                        className="h-7 w-24 rounded border border-gray-300 px-2 text-[11px] focus:outline-none focus:ring-1 focus:ring-blue-500"
                        value={inventoryWorker.interval_seconds}
                        onChange={(e) => {
                          const v = parseInt(e.target.value || '0', 10);
                          setInventoryWorker((prev) =>
                            prev ? { ...prev, interval_seconds: v } : prev,
                          );
                        }}
                        onBlur={async (e) => {
                          const v = parseInt(e.target.value || '0', 10);
                          if (!Number.isFinite(v) || v <= 0) return;
                          try {
                            const updated = await ebayApi.updateInventoryMvWorker({
                              interval_seconds: v,
                            });
                            setInventoryWorker(updated);
                            setInventoryWorkerError(null);
                          } catch (err: any) {
                            console.error("Failed to update inventory MV worker interval", err);
                            setInventoryWorkerError(
                              err?.response?.data?.detail ||
                              err.message ||
                              "Failed to update inventory MV worker interval",
                            );
                          }
                        }}
                      />
                      <span className="text-[10px] text-gray-500">
                        ≈ {Math.round(inventoryWorker.interval_seconds / 60)} min
                      </span>
                    </div>

                    <div className="flex items-center gap-2">
                      <span className="text-[11px] text-gray-700">Last run:</span>
                      <span className="text-[11px] text-gray-800">
                        {inventoryWorker.last_run_at
                          ? formatDateTimeLocal(inventoryWorker.last_run_at)
                          : 'never'}
                      </span>
                      {inventoryWorker.last_run_status && (
                        <span className="text-[11px] text-gray-600">
                          status: {inventoryWorker.last_run_status}
                        </span>
                      )}
                    </div>
                  </div>

                  {inventoryWorker.last_run_error && (
                    <div className="text-[11px] text-red-700 truncate">
                      Last error: {inventoryWorker.last_run_error}
                    </div>
                  )}

                  <div className="flex items-center justify-between mt-1">
                    <div className="text-[11px] text-gray-600">
                      Uses the same REFRESH MATERIALIZED VIEW logic as the dedicated
                      worker process. The toggle only affects the automatic loop;
                      you can still trigger "Run now" manually.
                    </div>
                    <button
                      type="button"
                      className="inline-flex h-7 items-center rounded bg-blue-600 px-3 text-[11px] font-medium text-white hover:bg-blue-700"
                      onClick={async () => {
                        try {
                          const resp = await ebayApi.runInventoryMvWorkerOnce();
                          if (resp.status === 'error') {
                            setInventoryWorkerError(
                              resp.message || 'Inventory MV run failed',
                            );
                          } else {
                            setInventoryWorkerError(null);
                          }
                        } catch (e: any) {
                          console.error("Failed to run inventory MV worker once", e);
                          setInventoryWorkerError(
                            e?.response?.data?.detail ||
                            e.message ||
                            "Failed to run inventory MV worker once",
                          );
                        } finally {
                          void loadInventoryWorker();
                        }
                      }}
                    >
                      Run now
                    </button>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Per-account token status – now kept compact and aligned with the header row */}
          <Card className="p-0">
            <CardHeader className="py-1 px-3 pb-0 flex items-center justify-between">
              <CardTitle className="text-[12px] font-semibold">Per-account token status</CardTitle>
            </CardHeader>
            <CardContent className="py-1 px-3">
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
                              {formatDateTimeLocal(row.last_refresh_at)}
                              {row.last_refresh_at && formatRelativeTime(row.last_refresh_at) && (
                                <span className="ml-1 text-[10px] text-gray-500">
                                  ({formatRelativeTime(row.last_refresh_at)})
                                </span>
                              )}
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
                                    const data = await ebayApi.getEbayTokenRefreshLog(
                                      row.account_id,
                                      50,
                                    );
                                    setLogModalData(data);
                                  } catch (e: any) {
                                    console.error("Failed to load token refresh log", e);
                                    setLogModalError(
                                      e?.response?.data?.detail ||
                                      e.message ||
                                      "Failed to load refresh log",
                                    );
                                  } finally {
                                    setLogModalLoading(false);
                                  }
                                }}
                              >
                                View log
                              </button>
                              <button
                                className="ml-1 px-2 py-0.5 border rounded text-[11px] bg-white hover:bg-gray-50"
                                onClick={() => void openTokenRefreshDebug(row.account_id)}
                              >
                                Refresh (debug)
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
              <div className="bg-white rounded shadow-lg w-[95vw] max-w-[1400px] max-h-[90vh] min-h-[60vh] overflow-auto p-4 text-xs resize">
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
                              <td className="px-2 py-1 whitespace-nowrap">{formatDateTimeLocal(log.started_at)}</td>
                              <td className="px-2 py-1 whitespace-nowrap">{formatDateTimeLocal(log.finished_at)}</td>
                              <td className="px-2 py-1 whitespace-nowrap">
                                {log.success === null ? 'n/a' : log.success ? 'success' : 'error'}
                                {log.error_code && (
                                  <span className="ml-1 text-gray-500">[{log.error_code}]</span>
                                )}
                              </td>
                              <td className="px-2 py-1 whitespace-pre-wrap max-w-xs">
                                {log.error_message || '–'}
                              </td>
                              <td className="px-2 py-1 whitespace-nowrap">{formatDateTimeLocal(log.old_expires_at)}</td>
                              <td className="px-2 py-1 whitespace-nowrap">{formatDateTimeLocal(log.new_expires_at)}</td>
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

          {debugModalOpen && (
            <div className="fixed inset-0 bg-black bg-opacity-40 flex items-center justify-center z-50">
              <div className="bg-white rounded shadow-lg max-w-5xl w-[95vw] max-h-[90vh] min-h-[60vh] overflow-auto p-4 text-xs">
                <div className="flex items-center justify-between mb-2">
                  <div>
                    <div className="font-semibold text-sm">Token refresh (debug)</div>
                    <div className="text-[11px] text-gray-600">
                      This debug view shows full headers and tokens exactly as sent to eBay. Do not share this
                      output outside the trusted team.
                    </div>
                  </div>
                  <button
                    type="button"
                    className="text-xs text-gray-600 hover:text-black"
                    onClick={() => {
                      setDebugModalOpen(false);
                      setDebugModalData(null);
                      setDebugModalError(null);
                    }}
                  >
                    Close
                  </button>
                </div>
                {debugModalLoading && (
                  <div className="mb-2 text-xs text-gray-600">Running refresh against eBay...</div>
                )}
                {debugModalError && <div className="mb-2 text-xs text-red-600">{debugModalError}</div>}
                {debugModalData && (
                  (() => {
                    const text = buildDebugTerminalText(debugModalData);
                    const accountName =
                      debugModalData.account.house_name || debugModalData.account.id;
                    return (
                      <>
                        <div className="mb-2 text-[11px] text-gray-700 flex items-center justify-between">
                          <div>
                            <span className="font-semibold">Account:</span>{" "}
                            <span>
                              {accountName}
                              {debugModalData.account.ebay_user_id && (
                                <span className="text-gray-500">
                                  {" "}
                                  (eBay user: {debugModalData.account.ebay_user_id})
                                </span>
                              )}
                            </span>
                            <span className="ml-2 text-gray-500">
                              env: {debugModalData.environment}
                            </span>
                            <span className="ml-2">
                              Result:{" "}
                              {debugModalData.success ? (
                                <span className="text-green-700 font-semibold">SUCCESS</span>
                              ) : (
                                <span className="text-red-700 font-semibold">ERROR</span>
                              )}
                              {debugModalData.error && (
                                <span className="ml-1 text-gray-700">
                                  [{debugModalData.error}]
                                </span>
                              )}
                              {debugModalData.error_description && (
                                <span className="ml-1 text-gray-600">
                                  {" - "}
                                  {debugModalData.error_description}
                                </span>
                              )}
                            </span>
                          </div>
                          <button
                            type="button"
                            className="px-2 py-0.5 border rounded text-[11px] bg-white hover:bg-gray-50"
                            onClick={() => {
                              if (navigator?.clipboard?.writeText) {
                                void navigator.clipboard.writeText(text);
                              }
                            }}
                          >
                            Copy all
                          </button>
                        </div>
                        <pre className="bg-black text-green-100 font-mono text-[11px] p-3 rounded h-[60vh] overflow-auto whitespace-pre-wrap">
                          {text}
                        </pre>
                      </>
                    );
                  })()
                )}
              </div>
            </div>
          )}

          {httpLogsModalOpen && (
            <div className="fixed inset-0 bg-black bg-opacity-40 flex items-center justify-center z-50">
              <div className="bg-white rounded shadow-lg max-w-5xl w-[90vw] max-h-[80vh] overflow-auto p-4 text-xs">
                <div className="flex items-center justify-between mb-2">
                  <h2 className="font-semibold text-sm">Token HTTP logs (request &amp; response)</h2>
                  <button
                    type="button"
                    className="text-xs text-gray-600 hover:text-black"
                    onClick={() => setHttpLogsModalOpen(false)}
                  >
                    Close
                  </button>
                </div>
                {httpLogsLoading && (
                  <div className="text-xs text-gray-600">Loading HTTP logs...</div>
                )}
                {httpLogsError && (
                  <div className="text-xs text-red-600 mb-2">{httpLogsError}</div>
                )}
                {!httpLogsLoading && !httpLogsError && httpLogs.length === 0 && (
                  <div className="text-xs text-gray-600">No token HTTP logs found.</div>
                )}
                {!httpLogsLoading && httpLogs.length > 0 && (
                  <div className="space-y-3">
                    {httpLogs.map((log, idx) => (
                      <div key={log.id || idx} className="border rounded p-2 bg-gray-50">
                        <div className="text-[11px] mb-1">
                          <span className="font-semibold">{log.action}</span>{" "}
                          {log.environment && (
                            <span className="text-gray-600">· {log.environment}</span>
                          )}
                          {log.created_at && (
                            <span className="text-gray-500">
                              {" "}· {formatDateTimeLocal(log.created_at)}
                            </span>
                          )}
                          {log.error && (
                            <span className="ml-2 text-red-600">
                              error: {String(log.error).slice(0, 200)}
                            </span>
                          )}
                        </div>
                        <pre className="text-[11px] bg-white p-2 rounded overflow-x-auto whitespace-pre-wrap">
                          {JSON.stringify(log.request, null, 2)}
                        </pre>
                        {log.response && (
                          <pre className="mt-1 text-[11px] bg-white p-2 rounded overflow-x-auto whitespace-pre-wrap">
                            {JSON.stringify(log.response, null, 2)}
                          </pre>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {terminalModalOpen && (
            <div className="fixed inset-0 bg-black bg-opacity-60 flex items-center justify-center z-50">
              <div className="bg-gray-900 rounded shadow-lg max-w-5xl w-[95vw] max-h-[90vh] overflow-auto p-4 text-xs text-green-100 font-mono">
                <div className="flex items-center justify-between mb-2 text-gray-200">
                  <div className="flex flex-col">
                    <span className="font-semibold text-sm">Token refresh terminal (worker + debug)</span>
                    <span className="text-[11px] text-gray-400">
                      Shows recent token refresh HTTP calls from both the scheduled worker (source="scheduled")
                      and manual debug runs (source="debug").
                    </span>
                  </div>
                  <button
                    type="button"
                    className="text-xs text-gray-300 hover:text-white"
                    onClick={() => {
                      setTerminalModalOpen(false);
                      setTerminalEntries([]);
                      setTerminalError(null);
                    }}
                  >
                    Close
                  </button>
                </div>
                {terminalLoading && (
                  <div className="text-[11px] text-gray-300">Loading token refresh terminal logs...</div>
                )}
                {terminalError && (
                  <div className="text-[11px] text-red-400 mb-2">{terminalError}</div>
                )}
                {!terminalLoading && !terminalError && terminalEntries.length === 0 && (
                  <div className="text-[11px] text-gray-300">No token refresh terminal logs found.</div>
                )}
                {!terminalLoading && terminalEntries.length > 0 && (
                  <>
                    <button
                      type="button"
                      className="mb-2 px-2 py-0.5 border rounded text-[11px] bg-gray-800 hover:bg-gray-700 text-gray-100"
                      onClick={() => {
                        const text = terminalEntries
                          .map((entry: any, idx: number) => {
                            const lines: string[] = [];
                            lines.push(`=== ENTRY #${idx + 1} ===`);
                            lines.push(`time: ${entry.created_at || 'n/a'}`);
                            lines.push(`source: ${entry.source || 'unknown'}`);
                            lines.push(`action: ${entry.action || 'n/a'}`);
                            if (entry.response && typeof entry.response.status === 'number') {
                              lines.push(`status: ${entry.response.status}`);
                            } else if (entry.response && typeof entry.response.status_code === 'number') {
                              lines.push(`status: ${entry.response.status_code}`);
                            } else if (entry.error) {
                              lines.push(`status: error (${String(entry.error).slice(0, 80)})`);
                            }
                            lines.push('');
                            lines.push('--- HTTP REQUEST ---');
                            const req = entry.request || {};
                            if (req.method || req.url || req.headers || req.body) {
                              lines.push(`${req.method || 'POST'} ${req.url || ''}`.trim());
                              if (req.headers) {
                                Object.entries(req.headers).forEach(([k, v]) => {
                                  lines.push(`${k}: ${String(v)}`);
                                });
                              }
                              lines.push('');
                              if (req.body != null) {
                                if (typeof req.body === 'string') {
                                  lines.push(req.body);
                                } else {
                                  try {
                                    lines.push(JSON.stringify(req.body, null, 2));
                                  } catch {
                                    lines.push(String(req.body));
                                  }
                                }
                              }
                            } else {
                              lines.push('<no request captured>');
                            }
                            lines.push('');
                            lines.push('--- HTTP RESPONSE ---');
                            const res = entry.response;
                            if (res) {
                              const status = (res.status_code ?? res.status ?? '?') as any;
                              const reason = (res.reason || '') as any;
                              lines.push(`HTTP/1.1 ${status}${reason ? ` ${reason}` : ''}`);
                              if (res.headers) {
                                Object.entries(res.headers).forEach(([k, v]) => {
                                  lines.push(`${k}: ${String(v)}`);
                                });
                              }
                              lines.push('');
                              if (res.body != null) {
                                if (typeof res.body === 'string') {
                                  lines.push(res.body);
                                } else {
                                  try {
                                    lines.push(JSON.stringify(res.body, null, 2));
                                  } catch {
                                    lines.push(String(res.body));
                                  }
                                }
                              }
                            } else {
                              lines.push('<no response captured>');
                            }
                            lines.push('');
                            return lines.join('\n');
                          })
                          .join('\n----------------------------------------\n');
                        if (navigator?.clipboard?.writeText) {
                          void navigator.clipboard.writeText(text);
                        }
                      }}
                    >
                      Copy all
                    </button>
                    <pre className="bg-black text-green-100 font-mono text-[11px] p-3 rounded h-[60vh] overflow-auto whitespace-pre-wrap">
                      {terminalEntries
                        .map((entry: any, idx: number) => {
                          const lines: string[] = [];
                          lines.push(`=== ENTRY #${idx + 1} ===`);
                          lines.push(`time: ${entry.created_at || 'n/a'}`);
                          lines.push(`source: ${entry.source || 'unknown'}`);
                          lines.push(`action: ${entry.action || 'n/a'}`);
                          if (entry.response && typeof entry.response.status === 'number') {
                            lines.push(`status: ${entry.response.status}`);
                          } else if (entry.response && typeof entry.response.status_code === 'number') {
                            lines.push(`status: ${entry.response.status_code}`);
                          } else if (entry.error) {
                            lines.push(`status: error (${String(entry.error).slice(0, 80)})`);
                          }
                          lines.push('');
                          lines.push('--- HTTP REQUEST ---');
                          const req = entry.request || {};
                          if (req.method || req.url || req.headers || req.body) {
                            lines.push(`${req.method || 'POST'} ${req.url || ''}`.trim());
                            if (req.headers) {
                              Object.entries(req.headers).forEach(([k, v]) => {
                                lines.push(`${k}: ${String(v)}`);
                              });
                            }
                            lines.push('');
                            if (req.body != null) {
                              if (typeof req.body === 'string') {
                                lines.push(req.body);
                              } else {
                                try {
                                  lines.push(JSON.stringify(req.body, null, 2));
                                } catch {
                                  lines.push(String(req.body));
                                }
                              }
                            }
                          } else {
                            lines.push('<no request captured>');
                          }
                          lines.push('');
                          lines.push('--- HTTP RESPONSE ---');
                          const res = entry.response;
                          if (res) {
                            const status = (res.status_code ?? res.status ?? '?') as any;
                            const reason = (res.reason || '') as any;
                            lines.push(`HTTP/1.1 ${status}${reason ? ` ${reason}` : ''}`);
                            if (res.headers) {
                              Object.entries(res.headers).forEach(([k, v]) => {
                                lines.push(`${k}: ${String(v)}`);
                              });
                            }
                            lines.push('');
                            if (res.body != null) {
                              if (typeof res.body === 'string') {
                                lines.push(res.body);
                              } else {
                                try {
                                  lines.push(JSON.stringify(res.body, null, 2));
                                } catch {
                                  lines.push(String(res.body));
                                }
                              }
                            }
                          } else {
                            lines.push('<no response captured>');
                          }
                          lines.push('');
                          return lines.join('\n');
                        })
                        .join('\n----------------------------------------\n')}
                    </pre>
                  </>
                )}
              </div>
            </div>
          )}

          {selectedAccountId && selectedAccount && (
            <div className="mt-2">
              <div className="flex items-center gap-2 mb-1 text-sm">
                <span className="font-semibold">Workers for {accountLabel}</span>
                <span
                  className="inline-flex items-center justify-center h-4 w-4 rounded-full border border-gray-300 text-[10px] font-semibold text-gray-600 cursor-default"
                  title={
                    'Управление отдельными воркерами (Orders, Transactions, Messages и т.д.) для выбранного eBay аккаунта.'
                  }
                >
                  i
                </span>
              </div>
              <EbayWorkersPanel
                accountId={selectedAccountId}
                accountLabel={accountLabel}
                ebayUserId={selectedAccount.ebay_user_id}
                onViewAllLogs={() => setAllLogsModalOpen(true)}
              />
            </div>
          )}
        </div>
      </main>

      {/* All Worker Logs Modal */}
      <AllWorkerLogsModal
        isOpen={allLogsModalOpen}
        onClose={() => setAllLogsModalOpen(false)}
      />
    </div>
  );
};

export default AdminWorkersPage;
