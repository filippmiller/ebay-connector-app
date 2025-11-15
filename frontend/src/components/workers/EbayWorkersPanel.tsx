import React, { useEffect, useState } from "react";
import api from "../../lib/apiClient";
import { SyncTerminal } from "../SyncTerminal";

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
  account: {
    id: string;
    ebay_user_id?: string;
    username?: string;
    house_name?: string;
  };
  workers: WorkerConfigItem[];
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
  const [detailsRunId, setDetailsRunId] = useState<string | null>(null);
  const [detailsData, setDetailsData] = useState<any | null>(null);
  const [detailsLoading, setDetailsLoading] = useState(false);
  // Sync terminal for underlying sync_event logs (full HTTP detail)
  const [activeSyncRunId, setActiveSyncRunId] = useState<string | null>(null);
  const [activeApiFamily, setActiveApiFamily] = useState<string | null>(null);

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
      // If we have a recent run with a sync_run_id in its summary, pre-select
      // it for the terminal so the bottom half shows something useful.
      const firstWorker = data.workers[0];
      const summary = firstWorker?.last_run_summary as any;
      if (summary && (summary.sync_run_id || summary.run_id)) {
        setActiveSyncRunId(summary.sync_run_id || summary.run_id);
        setActiveApiFamily(firstWorker.api_family);
      }
    } catch (e: any) {
      console.error("Failed to load worker config", e);
      setError(e?.response?.data?.detail || e.message || "Failed to load workers");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchConfig();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accountId]);

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
      const resp = await api.post(
        `/ebay/workers/run`,
        null,
        {
          params: { account_id: accountId, api: apiFamily },
        }
      );
      // When a worker run is started, clear any previous sync terminal so the
      // user knows we are waiting for fresh logs.
      if (resp.data?.status === "started") {
        setActiveSyncRunId(null);
        setActiveApiFamily(apiFamily);
      }
      // Refresh config to pick up latest run info (including summary with sync_run_id once available)
      fetchConfig();
    } catch (e: any) {
      console.error("Failed to trigger run", e);
      setError(e?.response?.data?.detail || e.message || "Failed to trigger run");
    }
  };

  const openDetails = async (apiFamily: string) => {
    if (!accountId) return;
    setDetailsRunId(null);
    setDetailsData(null);
    setDetailsLoading(true);
    try {
      const runsResp = await api.get<{ runs: any[]}>(
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
            <button
              onClick={toggleGlobal}
              className={`px-4 py-2 font-semibold rounded shadow text-white ${
                config.workers_enabled ? "bg-red-600" : "bg-green-600"
              }`}
            >
              {config.workers_enabled ? "BIG RED BUTTON: TURN OFF ALL JOBS" : "Enable all workers"}
            </button>
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
                  </td>
                  <td className="px-3 py-2">
                    <span
                      className={`inline-flex items-center px-2 py-1 rounded text-xs font-semibold ${
                        w.enabled ? "bg-green-100 text-green-800" : "bg-gray-100 text-gray-600"
                      }`}
                    >
                      {w.enabled ? "Enabled" : "Disabled"}
                    </span>
                    {w.last_error && (
                      <div className="text-xs text-red-600 mt-1 max-w-xs truncate">
                        Last error: {w.last_error}
                      </div>
                    )}
                  </td>
                  <td className="px-3 py-2">
                    <div>
                      <div>Started: {w.last_run_started_at || "–"}</div>
                      <div>Finished: {w.last_run_finished_at || "–"}</div>
                      <div>Status: {w.last_run_status || "–"}</div>
                    </div>
                  </td>
                  <td className="px-3 py-2">
                    <div>Type: {w.cursor_type || "–"}</div>
                    <div>Value: {w.cursor_value || "–"}</div>
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
                      className="px-2 py-1 border rounded text-xs bg-blue-600 text-white"
                    >
                      Run now
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

      {/* Workers sync terminal occupying lower half of the tab */}
      {activeSyncRunId && (
        <div className="mt-6">
          <div className="flex items-center justify-between mb-2">
            <div className="text-sm text-gray-700">
              Terminal for {activeApiFamily || "orders"} worker (run_id: {activeSyncRunId})
            </div>
          </div>
          <SyncTerminal
            runId={activeSyncRunId}
            onComplete={() => {}}
            onStop={() => {}}
          />
        </div>
      )}

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
    </div>
  );
};
