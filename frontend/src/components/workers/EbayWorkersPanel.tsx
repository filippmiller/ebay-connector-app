import React, { useEffect, useState } from "react";
import api from "../../lib/apiClient";
import { SyncTerminal } from "../SyncTerminal";
import { ebayApi, TokenRefreshPreviewResponse } from "../../api/ebay";
import { formatDateTimeLocal } from "@/lib/dateUtils";

interface WorkerConfigItem {
  api_family: string;
  enabled: boolean;
  cursor_type?: string | null;
  cursor_value?: string | null;
  last_run_at?: string | null;
  last_error?: string | null;
  last_run_status?: string | null;
  last_run_started_at?: string | null;
  last_run_finished_at?: string | null;
  last_run_summary?: Record<string, any> | null;
}

interface WorkerConfigResponse {
  workers_enabled: boolean;
  worker_notifications_enabled?: boolean;
  account: {
    id: string;
    ebay_user_id?: string;
    username?: string;
    house_name?: string;
  };
  workers: WorkerConfigItem[];
}

interface WorkerScheduleRun {
  run_at: string;
  window_from: string | null;
  window_to: string | null;
}

interface WorkerScheduleItem {
  api_family: string;
  enabled: boolean;
  overlap_minutes?: number | null;
  initial_backfill_days?: number | null;
  runs: WorkerScheduleRun[];
}

interface WorkerScheduleResponse {
  account: {
    id: string;
    ebay_user_id?: string;
    username?: string;
    house_name?: string;
  };
  interval_minutes: number;
  hours: number;
  workers: WorkerScheduleItem[];
}

interface EbayWorkersPanelProps {
  accountId: string;
  accountLabel: string;
  ebayUserId?: string;
}

export const EbayWorkersPanel: React.FC<EbayWorkersPanelProps> = ({ accountId, accountLabel, ebayUserId }) => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [config, setConfig] = useState<WorkerConfigResponse | null>(null);
  const [schedule, setSchedule] = useState<WorkerScheduleResponse | null>(null);
  const [scheduleError, setScheduleError] = useState<string | null>(null);
  const [detailsRunId, setDetailsRunId] = useState<string | null>(null);
  const [detailsData, setDetailsData] = useState<any | null>(null);
  const [detailsLoading, setDetailsLoading] = useState(false);
  // Sync terminal for underlying sync_event logs (full HTTP detail)
  const [activeSyncRunId, setActiveSyncRunId] = useState<string | null>(null);
  const [activeApiFamily, setActiveApiFamily] = useState<string | null>(null);
  const [runningApiFamily, setRunningApiFamily] = useState<string | null>(null);
  const [recentRuns, setRecentRuns] = useState<any[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | "latest" | null>("latest");
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewData, setPreviewData] = useState<TokenRefreshPreviewResponse | null>(null);

  const deriveSyncRunId = (run: { id: string; api_family: string } | null | undefined): string | null => {
    if (!run || !run.id || !run.api_family) return null;
    return `worker_${run.api_family}_${run.id}`;
  };

  const fetchConfig = async () => {
    if (!accountId) return;
    setLoading(true);
    setError(null);
    try {
      const resp = await api.get<WorkerConfigResponse>(
        `/ebay/workers/config`,
        {
          params: { account_id: accountId },
        }
      );
      const data = resp.data;
      setConfig(data);
      // Also refresh recent worker runs so the terminal can attach to the
      // latest activity across all APIs.
      fetchRecentRuns();
      // Refresh schedule projection for this account.
      fetchSchedule();
    } catch (e: any) {
      console.error("Failed to load worker config", e);
      setError(e?.response?.data?.detail || e.message || "Failed to load workers");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchConfig();
    fetchRecentRuns();
    fetchSchedule();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accountId]);

  const fetchSchedule = async () => {
    if (!accountId) return;
    try {
      const resp = await api.get<WorkerScheduleResponse>(
        `/ebay/workers/schedule`,
        {
          params: { account_id: accountId, hours: 5 },
        }
      );
      setSchedule(resp.data);
      setScheduleError(null);
    } catch (e: any) {
      console.error("Failed to load worker schedule", e);
      setSchedule(null);
      setScheduleError(e?.response?.data?.detail || e.message || "Failed to load schedule");
    }
  };

  const fetchRecentRuns = async () => {
    if (!accountId) return;
    try {
      const resp = await api.get<{ runs: any[] }>(
        `/ebay/workers/runs`,
        {
          params: { account_id: accountId, limit: 20 },
        }
      );
      const runs = resp.data.runs || [];
      setRecentRuns(runs);
      // Auto-select and attach to the most recent run for the terminal if we
      // don't already have an active sync run.
      if (runs.length > 0 && (!selectedRunId || selectedRunId === "latest")) {
        const latest = runs[0];
        setSelectedRunId(latest.id);
        if (!activeSyncRunId) {
          // Derive a deterministic sync_run_id so we can attach even while the
          // worker run is still in progress.
          let syncRunId: string | null = deriveSyncRunId(latest);
          try {
            const logsResp = await api.get(`/ebay/workers/logs/${latest.id}`);
            const summary = logsResp.data?.run?.summary as any;
            syncRunId = summary?.sync_run_id || summary?.run_id || syncRunId;
          } catch (err) {
            console.error("Failed to auto-attach workers terminal to latest run", err);
          }
          if (syncRunId) {
            setActiveSyncRunId(syncRunId);
            setActiveApiFamily(latest.api_family);
          }
        }
      }
    } catch (e) {
      // Swallow errors here; the main error surface is the config fetch.
      console.error("Failed to load recent worker runs", e);
    }
  };

  const toggleGlobal = async () => {
    if (!config) return;
    try {
      const resp = await api.post(
        `/ebay/workers/global-toggle`,
        { workers_enabled: !config.workers_enabled },
      );
      setConfig((prev) =>
        prev ? { ...prev, workers_enabled: resp.data.workers_enabled } : prev
      );
    } catch (e: any) {
      console.error("Failed to toggle global workers", e);
      setError(e?.response?.data?.detail || e.message || "Failed to toggle workers");
    }
  };

  const toggleNotifications = async () => {
    if (!config) return;
    // Default to true if undefined, so we toggle to false
    const current = config.worker_notifications_enabled !== false;
    try {
      const resp = await api.post(
        `/ebay/workers/global-notifications-toggle`,
        { worker_notifications_enabled: !current },
      );
      setConfig((prev) =>
        prev ? { ...prev, worker_notifications_enabled: resp.data.worker_notifications_enabled } : prev
      );
    } catch (e: any) {
      console.error("Failed to toggle notifications", e);
      setError(e?.response?.data?.detail || e.message || "Failed to toggle notifications");
    }
  };

  const toggleWorker = async (apiFamily: string, enabled: boolean) => {
    try {
      await api.post(
        `/ebay/workers/config`,
        { api_family: apiFamily, enabled },
        {
          params: { account_id: accountId },
        }
      );
      setConfig((prev) =>
        prev
          ? {
            ...prev,
            workers: prev.workers.map((w) =>
              w.api_family === apiFamily ? { ...w, enabled } : w
            ),
          }
          : prev
      );
    } catch (e: any) {
      console.error("Failed to toggle worker", e);
      setError(e?.response?.data?.detail || e.message || "Failed to toggle worker");
    }
  };

  const triggerRun = async (apiFamily: string) => {
    try {
      setRunningApiFamily(apiFamily);
      const resp = await api.post(
        `/ebay/workers/run`,
        null,
        {
          params: { account_id: accountId, api: apiFamily },
        }
      );
      if (resp.data?.status === "error") {
        setError(resp.data?.error_message || `Worker ${apiFamily} failed to start`);
        return;
      }
      if (resp.data?.status === "started" && resp.data?.run_id) {
        const runId = resp.data.run_id as string;
        setActiveApiFamily(apiFamily);
        setSelectedRunId(runId);
        // Optimistically add this run to the recentRuns list so the dropdown
        // immediately reflects the new run without waiting for the next
        // polling/refresh cycle.
        setRecentRuns((prev) => [
          {
            id: runId,
            api_family: apiFamily,
            status: "running",
            started_at: new Date().toISOString(),
            finished_at: null,
            summary: null,
          },
          ...prev,
        ]);
        // Immediately attach the terminal to the deterministic sync_run_id so
        // live progress is visible even before the worker finishes.
        let syncRunId: string | null = deriveSyncRunId({ id: runId, api_family: apiFamily });
        try {
          const logsResp = await api.get(`/ebay/workers/logs/${runId}`);
          const summary = logsResp.data?.run?.summary as any;
          syncRunId = summary?.sync_run_id || summary?.run_id || syncRunId;
        } catch (err) {
          console.error("Failed to load logs for new worker run", err);
        }
        if (syncRunId) {
          setActiveSyncRunId(syncRunId);
        } else {
          setActiveSyncRunId(null);
        }
      } else if (resp.data?.status === "skipped" && resp.data?.run_id) {
        // Already running; attach terminal to the active run.
        const runId = resp.data.run_id as string;
        setActiveApiFamily(apiFamily);
        setSelectedRunId(runId);
        let syncRunId: string | null = deriveSyncRunId({ id: runId, api_family: apiFamily });
        try {
          const logsResp = await api.get(`/ebay/workers/logs/${runId}`);
          const summary = logsResp.data?.run?.summary as any;
          syncRunId = summary?.sync_run_id || summary?.run_id || syncRunId;
        } catch (err) {
          console.error("Failed to load logs for existing worker run", err);
        }
        if (syncRunId) {
          setActiveSyncRunId(syncRunId);
        }
      }
      // Refresh config + recent runs to pick up the latest state.
      fetchConfig();
      fetchRecentRuns();
    } catch (e: any) {
      console.error("Failed to trigger run", e);
      setError(e?.response?.data?.detail || e.message || "Failed to trigger run");
    } finally {
      setRunningApiFamily(null);
    }
  };

  const openDetails = async (apiFamily: string) => {
    if (!accountId) return;
    setDetailsRunId(null);
    setDetailsData(null);
    setDetailsLoading(true);
    try {
      const runsResp = await api.get<{ runs: any[] }>(
        `/ebay/workers/runs`,
        {
          params: { account_id: accountId, api: apiFamily, limit: 1 },
        }
      );
      const lastRun = runsResp.data.runs[0];
      if (!lastRun) {
        setDetailsData({ message: "No runs yet for this worker" });
      } else {
        setDetailsRunId(lastRun.id);
        const logsResp = await api.get(`/ebay/workers/logs/${lastRun.id}`);
        setDetailsData(logsResp.data);
        // Pick up sync_run_id from worker run summary and wire terminal to
        // the existing SyncTerminal which streams /ebay/sync/events/{run_id}.
        const summary = logsResp.data?.run?.summary as any;
        const syncRunId = summary?.sync_run_id || summary?.run_id || null;
        if (syncRunId) {
          setActiveSyncRunId(syncRunId);
          setActiveApiFamily(apiFamily);
        }
      }
    } catch (e: any) {
      console.error("Failed to load run details", e);
      setDetailsData({ error: e?.response?.data?.detail || e.message });
    } finally {
      setDetailsLoading(false);
    }
  };

  const openPreview = async () => {
    if (!accountId) return;
    setPreviewLoading(true);
    setPreviewData(null);
    setPreviewOpen(true);
    try {
      const data = await ebayApi.getTokenRefreshPreview(accountId);
      setPreviewData(data);
    } catch (e: any) {
      console.error("Failed to load token refresh preview", e);
      setPreviewData({
        error: "load_failed",
        message: e?.response?.data?.detail || e.message || "Failed to load preview",
        method: "",
        url: "",
        headers: {},
        body_form: {
          grant_type: "refresh_token",
          refresh_token: {
            prefix: null,
            suffix: null,
            length: 0,
            starts_with_v: false,
            contains_enc_prefix: false,
          },
        },
      } as any);
    } finally {
      setPreviewLoading(false);
    }
  };

  if (!accountId) {
    return <div className="mt-4 text-gray-500">Select an eBay account to see workers.</div>;
  }

  if (loading && !config) {
    return <div className="mt-4">Loading worker configuration...</div>;
  }

  return (
    <div className="mt-4 space-y-4">
      {error && (
        <div className="text-red-600 text-sm">{error}</div>
      )}

      {config && (
        <>
          <div className="flex items-center justify-between">
            <div>
              <div className="font-semibold text-lg">Workers command control</div>
              <div className="text-sm text-gray-600">
                Account: {accountLabel || config.account.username || config.account.house_name || config.account.id}
              </div>
              {ebayUserId && (
                <div className="text-xs text-gray-500">eBay user id: {ebayUserId}</div>
              )}
            </div>
            <div className="flex items-center space-x-2">
              <button
                onClick={toggleNotifications}
                className={`px-3 py-2 text-xs font-semibold rounded border ${config.worker_notifications_enabled !== false
                  ? "bg-blue-50 text-blue-700 border-blue-200 hover:bg-blue-100"
                  : "bg-gray-50 text-gray-600 border-gray-200 hover:bg-gray-100"
                  }`}
                title="Toggle system notifications for worker runs"
              >
                {config.worker_notifications_enabled !== false ? "🔔 System Notifications: ON" : "🔕 System Notifications: OFF"}
              </button>
              <button
                onClick={openPreview}
                className="px-3 py-2 text-xs font-semibold rounded border bg-white text-gray-700"
              >
                Inspect token format
              </button>
              <button
                onClick={toggleGlobal}
                className={`px-4 py-2 font-semibold rounded shadow text-white ${config.workers_enabled ? "bg-red-600" : "bg-green-600"
                  }`}
              >
                {config.workers_enabled ? "BIG RED BUTTON: TURN OFF ALL JOBS" : "Enable all workers"}
              </button>
            </div>
          </div>

          <table className="min-w-full text-sm border mt-4">
            <thead>
              <tr className="bg-gray-100">
                <th className="px-3 py-2 text-left">API</th>
                <th className="px-3 py-2 text-left">Status</th>
                <th className="px-3 py-2 text-left">Last run</th>
                <th className="px-3 py-2 text-left">Cursor</th>
                <th className="px-3 py-2 text-left">Actions</th>
              </tr>
            </thead>
            <tbody>
              {config.workers.map((w) => (
                <tr key={w.api_family} className="border-t">
                  <td className="px-3 py-2 font-medium align-top">
                    <div className="font-medium capitalize">{w.api_family}</div>
                    {w.api_family === 'orders' && (
                      <div className="mt-1 text-xs text-gray-600 max-w-xs">
                        <div>Source: Orders – Fulfillment API</div>
                        <div className="font-mono text-[11px] text-gray-500">GET /sell/fulfillment/v1/order</div>
                        <div className="mt-1">
                          Destination: <span className="font-mono">ebay_orders</span>
                          <span className="text-gray-500"> (+ </span>
                          <span className="font-mono">ebay_order_line_items</span>
                          <span className="text-gray-500">)</span>
                        </div>
                        <div className="mt-1 text-[11px] text-gray-500">
                          Key columns: order_id, user_id, creation_date, last_modified_date, order_payment_status,
                          order_fulfillment_status, buyer_username, total_amount, total_currency, ship_to_*, line_items_count.
                        </div>
                      </div>
                    )}
                    {w.api_family === 'transactions' && (
                      <div className="mt-1 text-xs text-gray-600 max-w-xs">
                        <div>Source: Transactions – Finances API</div>
                        <div className="font-mono text-[11px] text-gray-500">GET /sell/finances/v1/transaction</div>
                        <div className="mt-1">
                          Destination: <span className="font-mono">ebay_transactions</span>
                        </div>
                        <div className="mt-1 text-[11px] text-gray-500">
                          Key columns: transaction_id, user_id, order_id, transaction_date, transaction_type,
                          transaction_status, amount, currency. All rows are tagged with ebay_account_id and ebay_user_id
                          (e.g. mil_243) for precise account-level tracking.
                        </div>
                      </div>
                    )}
                    {w.api_family === 'offers' && (
                      <div className="mt-1 text-xs text-gray-600 max-w-xs">
                        <div>Source: Inventory Offers – Inventory API</div>
                        <div className="font-mono text-[11px] text-gray-500">GET /sell/inventory/v1/offer</div>
                        <div className="mt-1">
                          Destination: <span className="font-mono">ebay_inventory_offers</span>
                        </div>
                        <div className="mt-1 text-[11px] text-gray-500">
                          Tracks price, quantity, and status changes over time.
                        </div>
                      </div>
                    )}
                    {w.api_family === 'messages' && (
                      <div className="mt-1 text-xs text-gray-600 max-w-xs">
                        <div>Source: Messages – Trading API</div>
                        <div className="font-mono text-[11px] text-gray-500">GetMyMessages</div>
                        <div className="mt-1">
                          Destination: <span className="font-mono">ebay_messages</span>
                        </div>
                        <div className="mt-1 text-[11px] text-gray-500">
                          Syncs member-to-member messages.
                        </div>
                      </div>
                    )}
                    {w.api_family === 'active_inventory' && (
                      <div className="mt-1 text-xs text-gray-600 max-w-xs">
                        <div>Source: Active Inventory – Trading API</div>
                        <div className="font-mono text-[11px] text-gray-500">GetMyeBaySelling</div>
                        <div className="mt-1">
                          Destination: <span className="font-mono">ebay_active_inventory</span>
                        </div>
                        <div className="mt-1 text-[11px] text-gray-500">
                          Snapshot of currently active listings.
                        </div>
                      </div>
                    )}
                    {w.api_family === 'cases' && (
                      <div className="mt-1 text-xs text-gray-600 max-w-xs">
                        <div>Source: Post-Order Cases – Post-Order API</div>
                        <div className="font-mono text-[11px] text-gray-500">GET /post-order/v2/casemanagement/case</div>
                        <div className="mt-1">
                          Destination: <span className="font-mono">ebay_cases</span>
                        </div>
                        <div className="mt-1 text-[11px] text-gray-500">
                          Syncs INR and SNAD cases.
                        </div>
                      </div>
                    )}
                    {w.api_family === 'inquiries' && (
                      <div className="mt-1 text-xs text-gray-600 max-w-xs">
                        <div>Source: Post-Order Inquiries – Post-Order API</div>
                        <div className="font-mono text-[11px] text-gray-500">GET /post-order/v2/inquiry</div>
                        <div className="mt-1">
                          Destination: <span className="font-mono">ebay_inquiries</span>
                        </div>
                        <div className="mt-1 text-[11px] text-gray-500">
                          Syncs buyer inquiries (pre-case disputes).
                        </div>
                      </div>
                    )}
                    {w.api_family === 'finances' && (
                      <div className="mt-1 text-xs text-gray-600 max-w-xs">
                        <div>Source: Finances – Finances API</div>
                        <div className="font-mono text-[11px] text-gray-500">GET /sell/finances/v1/transaction</div>
                        <div className="mt-1">
                          Destination: <span className="font-mono">ebay_finances_transactions</span>
                        </div>
                        <div className="mt-1 text-[11px] text-gray-500">
                          Dedicated finances sync for fees and transactions.
                        </div>
                      </div>
                    )}
                    {w.api_family === 'buyer' && (
                      <div className="mt-1 text-xs text-gray-600 max-w-xs">
                        <div>Source: Purchases – Trading API</div>
                        <div className="font-mono text-[11px] text-gray-500">GetMyeBayBuying</div>
                        <div className="mt-1">
                          Destination: <span className="font-mono">ebay_buyer</span>
                        </div>
                        <div className="mt-1 text-[11px] text-gray-500">
                          Syncs items purchased by this account.
                        </div>
                      </div>
                    )}
                    {w.api_family === 'returns' && (
                      <div className="mt-1 text-xs text-gray-600 max-w-xs">
                        <div>Source: Post-Order Returns – Post-Order API</div>
                        <div className="font-mono text-[11px] text-gray-500">GET /post-order/v2/return</div>
                        <div className="mt-1">
                          Destination: <span className="font-mono">ebay_returns</span>
                        </div>
                        <div className="mt-1 text-[11px] text-gray-500">
                          Syncs return requests.
                        </div>
                      </div>
                    )}
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex items-center space-x-2">
                      {/* Traffic Light Indicator */}
                      <div
                        className={`w-3 h-3 rounded-full shadow-sm ${!w.enabled
                          ? "bg-gray-400"
                          : w.last_run_status === "running"
                            ? "bg-yellow-400 animate-pulse"
                            : w.last_run_status === "error"
                              ? "bg-red-500"
                              : "bg-green-500"
                          }`}
                        title={
                          !w.enabled
                            ? "Worker Disabled"
                            : w.last_run_status === "running"
                              ? "Running..."
                              : w.last_run_status === "error"
                                ? "Last Run Failed"
                                : "Healthy"
                        }
                      />
                      <span
                        className={`inline-flex items-center px-2 py-1 rounded text-xs font-semibold ${w.enabled ? "bg-green-50 text-green-700" : "bg-gray-100 text-gray-600"
                          }`}
                      >
                        {w.enabled ? "Enabled" : "Disabled"}
                      </span>
                    </div>
                    {w.last_error && (
                      <div className="text-xs text-red-600 mt-1 max-w-xs truncate" title={w.last_error}>
                        Error: {w.last_error}
                      </div>
                    )}
                  </td>
                  <td className="px-3 py-2">
                    <div className="text-xs space-y-0.5">
                      <div>
                        <span className="text-gray-500">Started:</span>{" "}
                        {w.last_run_started_at ? formatDateTimeLocal(w.last_run_started_at) : "–"}
                      </div>
                      <div>
                        <span className="text-gray-500">Finished:</span>{" "}
                        {w.last_run_finished_at ? formatDateTimeLocal(w.last_run_finished_at) : "–"}
                      </div>
                      <div className="flex items-center space-x-1">
                        <span className="text-gray-500">Status:</span>
                        <span
                          className={`font-medium ${w.last_run_status === "error"
                            ? "text-red-600"
                            : w.last_run_status === "running"
                              ? "text-yellow-600"
                              : "text-gray-900"
                            }`}
                        >
                          {w.last_run_status || "–"}
                        </span>
                      </div>
                      {/* Detailed Run Stats */}
                      {w.last_run_summary && (
                        <div className="mt-1 pt-1 border-t border-gray-100 text-gray-600 text-[11px]">
                          <div className="flex items-center space-x-2">
                            <span title="Records fetched from API">
                              ⬇ {w.last_run_summary.total_fetched ?? 0}
                            </span>
                            <span className="text-gray-300">|</span>
                            <span title="Records stored to DB">
                              💾 {w.last_run_summary.total_stored ?? 0}
                            </span>
                            {w.last_run_summary.duration_ms !== undefined && (
                              <>
                                <span className="text-gray-300">|</span>
                                <span title="Duration">
                                  ⏱ {(w.last_run_summary.duration_ms / 1000).toFixed(1)}s
                                </span>
                              </>
                            )}
                          </div>
                          {w.last_run_summary.window_from && w.last_run_summary.window_to && (
                            <div className="mt-0.5 text-gray-400" title="Sync Window">
                              📅 {formatDateTimeLocal(w.last_run_summary.window_from).split(',')[1]} - {formatDateTimeLocal(w.last_run_summary.window_to).split(',')[1]}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  </td>
                  <td className="px-3 py-2">
                    <div>Type: {w.cursor_type || "–"}</div>
                    <div>
                      Value:{" "}
                      {w.cursor_value ? formatDateTimeLocal(w.cursor_value) : "–"}
                    </div>
                  </td>
                  <td className="px-3 py-2 space-x-2">
                    <button
                      onClick={() => toggleWorker(w.api_family, !w.enabled)}
                      className="px-2 py-1 border rounded text-xs"
                    >
                      {w.enabled ? "Turn off" : "Turn on"}
                    </button>
                    <button
                      onClick={() => triggerRun(w.api_family)}
                      className={`px-2 py-1 border rounded text-xs text-white ${runningApiFamily === w.api_family ? "bg-blue-400" : "bg-blue-600"
                        }`}
                      disabled={runningApiFamily === w.api_family}
                    >
                      {runningApiFamily === w.api_family ? "Starting..." : "Run now"}
                    </button>
                    <button
                      onClick={() => openDetails(w.api_family)}
                      className="px-2 py-1 border rounded text-xs"
                    >
                      Details
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {/* Schedule projection for the next 5 hours */}
      {schedule && (
        <div className="mt-6 border rounded p-3 bg-gray-50">
          <div className="flex items-center justify-between mb-2">
            <div className="text-sm font-semibold">Schedule (next {schedule.hours} hours)</div>
            <button
              className="text-xs border rounded px-2 py-1 bg-white"
              onClick={fetchSchedule}
            >
              Refresh schedule
            </button>
          </div>
          {scheduleError && (
            <div className="text-xs text-red-600 mb-2">{scheduleError}</div>
          )}
          <div className="text-xs text-gray-600 mb-2">
            Interval: every {schedule.interval_minutes} minutes. Windows are computed from the last cursor with overlap.
          </div>
          <div className="space-y-3 max-h-80 overflow-auto">
            {schedule.workers.map((w) => (
              <div key={w.api_family} className="border rounded bg-white">
                <div className="px-3 py-2 flex items-center justify-between border-b bg-gray-100">
                  <div>
                    <span className="font-semibold mr-2 capitalize">{w.api_family}</span>
                    <span className="text-xs text-gray-600">
                      {w.enabled ? "Enabled" : "Disabled"}
                    </span>
                  </div>
                  {w.overlap_minutes != null && (
                    <div className="text-[11px] text-gray-500">
                      overlap {w.overlap_minutes} min · backfill {w.initial_backfill_days} days
                    </div>
                  )}
                </div>
                <table className="min-w-full text-[11px]">
                  <thead>
                    <tr className="bg-gray-50">
                      <th className="px-2 py-1 text-left">Run at</th>
                      <th className="px-2 py-1 text-left">Window from</th>
                      <th className="px-2 py-1 text-left">Window to</th>
                    </tr>
                  </thead>
                  <tbody>
                    {w.runs.map((r, idx) => (
                      <tr key={idx} className="border-t">
                        <td className="px-2 py-1 whitespace-nowrap">{formatDateTimeLocal(r.run_at)}</td>
                        <td className="px-2 py-1 whitespace-nowrap">{r.window_from ? formatDateTimeLocal(r.window_from) : "–"}</td>
                        <td className="px-2 py-1 whitespace-nowrap">{r.window_to ? formatDateTimeLocal(r.window_to) : "–"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Workers sync terminal occupying lower half of the tab */}
      <div className="mt-6">
        <div className="flex items-center justify-between mb-2">
          <div className="text-sm text-gray-700">
            eBay workers terminal for this account – showing {activeApiFamily || "latest"} run
          </div>
          <div className="flex items-center space-x-2 text-xs text-gray-600">
            <span>Select worker run:</span>
            <select
              className="border rounded px-1 py-0.5 text-xs"
              value={selectedRunId || "latest"}
              onChange={async (e) => {
                const val = e.target.value;
                if (val === "latest") {
                  setSelectedRunId("latest");
                  // Re-resolve latest run from recentRuns
                  if (recentRuns.length > 0) {
                    const latest = recentRuns[0];
                    let syncRunId: string | null = deriveSyncRunId(latest);
                    try {
                      const logsResp = await api.get(`/ebay/workers/logs/${latest.id}`);
                      const summary = logsResp.data?.run?.summary as any;
                      syncRunId = summary?.sync_run_id || summary?.run_id || syncRunId;
                    } catch (err) {
                      console.error("Failed to load logs for latest worker run", err);
                    }
                    if (syncRunId) {
                      setActiveSyncRunId(syncRunId);
                      setActiveApiFamily(latest.api_family);
                      setSelectedRunId(latest.id);
                    }
                  }
                } else {
                  setSelectedRunId(val);
                  // Try to find the run in the local recentRuns list so we can
                  // derive a sync_run_id even if summary is still null.
                  const run = recentRuns.find((r) => r.id === val);
                  let syncRunId: string | null = deriveSyncRunId(run);
                  try {
                    const logsResp = await api.get(`/ebay/workers/logs/${val}`);
                    const summary = logsResp.data?.run?.summary as any;
                    syncRunId = summary?.sync_run_id || summary?.run_id || syncRunId;
                    if (syncRunId) {
                      setActiveSyncRunId(syncRunId);
                      setActiveApiFamily(logsResp.data?.run?.api_family || null);
                    }
                  } catch (err) {
                    console.error("Failed to load logs for selected worker run", err);
                  }
                }
              }}
            >
              <option value="latest">Latest run (all APIs)</option>
              {recentRuns.map((run) => {
                let label = `${run.api_family}`;
                if (run.started_at) {
                  try {
                    const d = new Date(run.started_at);
                    const datePart = d.toISOString().slice(0, 10); // YYYY-MM-DD
                    const timePart = d.toTimeString().slice(0, 8); // HH:MM:SS
                    label += ` – ${datePart} ${timePart}`;
                  } catch {
                    label += ` – ${run.started_at}`;
                  }
                }
                if (run.status) {
                  label += ` – ${run.status}`;
                }
                return (
                  <option key={run.id} value={run.id}>
                    {label}
                  </option>
                );
              })}
            </select>
          </div>
        </div>
        {activeSyncRunId ? (
          <SyncTerminal
            runId={activeSyncRunId}
            onComplete={() => { }}
            onStop={() => { }}
          />
        ) : (
          <div className="text-xs text-gray-500 border rounded p-2 bg-gray-50">
            No worker run selected yet. Trigger a worker (e.g. "Run now" on Orders or Transactions)
            or choose a run from the dropdown above to see detailed logs.
          </div>
        )}
      </div>

      {detailsRunId && detailsData && (
        <div className="fixed inset-0 bg-black bg-opacity-40 flex items-center justify-center z-50">
          <div className="bg-white rounded shadow-lg max-w-2xl w-full max-h-[80vh] overflow-auto p-4">
            <div className="flex items-center justify-between mb-2">
              <div className="font-semibold">Worker run details</div>
              <button
                onClick={() => {
                  setDetailsRunId(null);
                  setDetailsData(null);
                }}
                className="text-sm text-gray-600"
              >
                Close
              </button>
            </div>
            {detailsLoading ? (
              <div>Loading...</div>
            ) : (
              <pre className="text-xs bg-gray-50 p-2 rounded overflow-x-auto whitespace-pre-wrap">
                {JSON.stringify(detailsData, null, 2)}
              </pre>
            )}
          </div>
        </div>
      )}

      {previewOpen && (
        <div className="fixed inset-0 bg-black bg-opacity-40 flex items-center justify-center z-50">
          <div className="bg-white rounded shadow-lg max-w-lg w-full max-h-[80vh] overflow-auto p-4 text-sm">
            <div className="flex items-center justify-between mb-2">
              <div className="font-semibold">Token refresh request preview</div>
              <button
                onClick={() => setPreviewOpen(false)}
                className="text-xs text-gray-600"
              >
                Close
              </button>
            </div>
            {previewLoading && <div>Loading preview...</div>}
            {!previewLoading && previewData && (
              <div className="space-y-2">
                {previewData.error && (
                  <div className="text-xs text-red-600">
                    {previewData.message || previewData.error}
                  </div>
                )}
                {previewData.account && (
                  <div className="text-xs text-gray-700">
                    Account: {previewData.account.house_name || previewData.account.username || previewData.account.id}
                  </div>
                )}
                <div>
                  <div><span className="font-semibold">Method:</span> {previewData.method}</div>
                  <div className="break-all"><span className="font-semibold">URL:</span> {previewData.url}</div>
                  <div><span className="font-semibold">grant_type:</span> {previewData.body_form?.grant_type}</div>
                </div>
                <div>
                  <div className="font-semibold text-xs mb-1">Headers (sanitized)</div>
                  <pre className="text-[11px] bg-gray-50 p-2 rounded overflow-x-auto whitespace-pre-wrap">
                    {JSON.stringify(previewData.headers || {}, null, 2)}
                  </pre>
                </div>
                <div>
                  <div className="font-semibold text-xs mb-1">refresh_token (masked)</div>
                  <pre className="text-[11px] bg-gray-50 p-2 rounded overflow-x-auto whitespace-pre-wrap">
                    {JSON.stringify(previewData.body_form?.refresh_token || {}, null, 2)}
                  </pre>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
