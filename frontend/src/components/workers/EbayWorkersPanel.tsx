import React, { useEffect, useState } from "react";
import api from "../../lib/apiClient";
import { SyncTerminal } from "../SyncTerminal";
import { formatDateTimeLocal, formatRelativeTime } from "../../lib/dateUtils";
import { useToast } from "@/hooks/use-toast";

interface WorkerConfigItem {
  api_family: string;
  enabled: boolean;
  primary_dedup_key?: string | null;
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

interface RunAllWorkersResult {
  api_family: string;
  status: string;
  run_id?: string | null;
  reason?: string | null;
}

interface RunAllWorkersResponse {
  account: {
    id: string;
    ebay_user_id?: string;
    username?: string;
    house_name?: string;
  };
  workers_enabled: boolean;
  results: RunAllWorkersResult[];
}

// Frontend-only representation of a single worker inside a "run-all" batch
// with live status updated from /ebay/workers/logs/{run_id}.
interface RunAllWorkerLiveStatus {
  api_family: string;
  run_id?: string | null;
  phase: "pending" | "running" | "completed" | "error" | "skipped";
  reason?: string | null;
  summary?: {
    total_fetched?: number | null;
    total_stored?: number | null;
  } | null;
}

interface EbayWorkersPanelProps {
  accountId: string;
  accountLabel: string;
  ebayUserId?: string;
}

const API_INFO: Record<string, { source: string; endpoint: string; destination: string; keys: string }> = {
  orders: {
    source: "Orders – Fulfillment API",
    endpoint: "GET /sell/fulfillment/v1/order",
    destination: "ebay_orders (+ ebay_order_line_items)",
    keys: "(order_id, user_id); line items keyed by (order_id, line_item_id)",
  },
  transactions: {
    source: "Transactions – Finances API",
    endpoint: "GET /sell/finances/v1/transaction",
    destination: "ebay_transactions",
    keys: "(transaction_id, user_id)",
  },
  finances: {
    source: "Finances – Finances API",
    endpoint: "GET /sell/finances/v1/transaction",
    destination: "ebay_finances_transactions (+ ebay_finances_fees)",
    keys: "(ebay_account_id, transaction_id)",
  },
  messages: {
    source: "Messages – Trading API",
    endpoint: "GetMyMessages",
    destination: "ebay_messages",
    keys: "message_id (per ebay_account_id, user_id)",
  },
  cases: {
    source: "Post-Order – Case Management API",
    endpoint: "GET /post-order/v2/casemanagement/search",
    destination: "ebay_cases",
    keys: "(case_id, user_id)",
  },
  inquiries: {
    source: "Post-Order – Inquiry API",
    endpoint: "GET /post-order/v2/inquiry/search",
    destination: "ebay_inquiries",
    keys: "(inquiry_id, user_id)",
  },
  offers: {
    source: "Offers – Inventory API",
    endpoint: "GET /sell/inventory/v1/offer?sku=...",
    destination: "ebay_offers (+ inventory)",
    keys: "(offer_id, user_id); inventory keyed by sku_code",
  },
  buyer: {
    source: "Buying – Trading API",
    endpoint: "GetMyeBayBuying",
    destination: "ebay_buyer",
    keys: "(ebay_account_id, item_id, transaction_id, order_line_item_id)",
  },
  active_inventory: {
    source: "Active inventory – Trading API",
    endpoint: "GetMyeBaySelling (ActiveList)",
    destination: "ebay_active_inventory",
    keys: "(ebay_account_id, sku, item_id)",
  },
};

export const EbayWorkersPanel: React.FC<EbayWorkersPanelProps> = ({ accountId, accountLabel, ebayUserId }) => {
  const { toast } = useToast();

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
  // Run-all modal state
  const [runAllOpen, setRunAllOpen] = useState(false);
  const [runAllLoading, setRunAllLoading] = useState(false);
  const [runAllResult, setRunAllResult] = useState<RunAllWorkersResponse | null>(null);
  const [runAllSessionWorkers, setRunAllSessionWorkers] = useState<RunAllWorkerLiveStatus[] | null>(null);
  const [runAllSessionCompleted, setRunAllSessionCompleted] = useState(false);
  const [hoveredApi, setHoveredApi] = useState<string | null>(null);

  const deriveSyncRunId = (run: { id: string; api_family: string } | null | undefined): string | null => {
    if (!run || !run.id || !run.api_family) return null;
    return `worker_${run.api_family}_${run.id}`;
  };

  const attachTerminalToRun = async (run: { id: string; api_family: string } | null | undefined) => {
    if (!run) return;
    let syncRunId: string | null = deriveSyncRunId(run);
    try {
      const logsResp = await api.get(`/ebay/workers/logs/${run.id}`);
      const summary = logsResp.data?.run?.summary as any;
      syncRunId = summary?.sync_run_id || summary?.run_id || syncRunId;
      if (syncRunId) {
        setActiveSyncRunId(syncRunId);
        setActiveApiFamily(logsResp.data?.run?.api_family || run.api_family || null);
      }
    } catch (err) {
      // Best-effort: if logs are not yet available, keep the terminal detached.
      // eslint-disable-next-line no-console
      console.error("Failed to attach workers terminal to run", err);
    }
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

  const getNextRunForApi = (apiFamily: string): WorkerScheduleRun | null => {
    if (!schedule) return null;
    const worker = schedule.workers.find((w) => w.api_family === apiFamily);
    if (!worker || !worker.runs || worker.runs.length === 0) return null;
    return worker.runs[0];
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
          // Attach the terminal to the latest run so logs stream immediately.
          await attachTerminalToRun(latest);
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
        const runMeta = { id: runId, api_family: apiFamily };
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
        // Attach the terminal so live progress is visible immediately.
        await attachTerminalToRun(runMeta);
      } else if (resp.data?.status === "skipped" && resp.data?.run_id) {
        // Already running; attach terminal to the active run.
        const runId = resp.data.run_id as string;
        setActiveApiFamily(apiFamily);
        setSelectedRunId(runId);
        await attachTerminalToRun({ id: runId, api_family: apiFamily });
      }
      // Refresh config + recent runs to pick up the latest state.
      fetchConfig();
      fetchRecentRuns();
    } catch (e: any) {
      // eslint-disable-next-line no-console
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
        await attachTerminalToRun({ id: lastRun.id, api_family: apiFamily });
      }
    } catch (e: any) {
      console.error("Failed to load run details", e);
      setDetailsData({ error: e?.response?.data?.detail || e.message });
    } finally {
      setDetailsLoading(false);
    }
  };

  const handleRunAllConfirm = async () => {
    if (!accountId) return;
    setRunAllLoading(true);
    setError(null);
    setRunAllSessionWorkers(null);
    setRunAllSessionCompleted(false);
    try {
      const resp = await api.post<RunAllWorkersResponse>(
        `/ebay/workers/run-all`,
        null,
        {
          params: { account_id: accountId },
        },
      );
      const data = resp.data;
      setRunAllResult(data);

      // Build a live session model for enabled workers only so the modal can
      // track their status in real time.
      if (config) {
        const enabledApis = config.workers.filter((w) => w.enabled).map((w) => w.api_family);
        const sessionWorkers: RunAllWorkerLiveStatus[] = enabledApis.map((apiFamily) => {
          const r = data.results.find((res) => res.api_family === apiFamily);
          if (!r) {
            return {
              api_family: apiFamily,
              run_id: null,
              phase: "pending",
              reason: null,
              summary: null,
            };
          }
          let phase: RunAllWorkerLiveStatus["phase"] = "pending";
          if (r.status === "started") {
            phase = "running";
          } else if (r.status === "error") {
            phase = "error";
          } else if (r.status === "skipped") {
            // If we have a run_id but reason=already_running, treat as running; otherwise as skipped.
            if (r.run_id && r.reason === "already_running") {
              phase = "running";
            } else {
              phase = "skipped";
            }
          }
          return {
            api_family: apiFamily,
            run_id: r.run_id ?? null,
            phase,
            reason: r.reason ?? null,
            summary: null,
          };
        });
        setRunAllSessionWorkers(sessionWorkers);

        // Optimistically inject started runs into recentRuns so the dropdown and
        // terminal see them immediately, without waiting for the next poll.
        const startedRuns = (data.results || []).filter((r) => r.status === "started" && r.run_id);
        if (startedRuns.length > 0) {
          setRecentRuns((prev) => {
            const existingIds = new Set((prev || []).map((r: any) => r.id));
            const synthetic = startedRuns
              .filter((r) => !existingIds.has(r.run_id as string))
              .map((r) => ({
                id: r.run_id as string,
                api_family: r.api_family,
                status: "running",
                started_at: new Date().toISOString(),
                finished_at: null,
                summary: null,
              }));
            return synthetic.length > 0 ? [...synthetic, ...prev] : prev;
          });
        }

        // Attach terminal to the first started worker in the batch so logs are
        // immediately visible in the bottom terminal.
        const firstStarted = sessionWorkers.find((w) => w.phase === "running" && w.run_id);
        if (firstStarted && firstStarted.run_id) {
          void attachTerminalToRun({ id: firstStarted.run_id, api_family: firstStarted.api_family });
          setSelectedRunId(firstStarted.run_id);
          setActiveApiFamily(firstStarted.api_family);
        }
      }

      // Refresh worker config, recent runs and schedule to pick up new state.
      fetchConfig();
      fetchRecentRuns();
      fetchSchedule();
    } catch (e: any) {
      // eslint-disable-next-line no-console
      console.error("Failed to run all workers", e);
      const message = e?.response?.data?.detail || e.message || "Failed to run all workers";
      setError(message);
      toast({ title: "Run-all request failed", description: message, variant: "destructive" });
    } finally {
      setRunAllLoading(false);
    }
  };

  // Poll worker run status for the current run-all session while the modal is
  // open. This keeps the live modal in sync without requiring a full page
  // reload.
  useEffect(() => {
    if (!runAllOpen || !runAllSessionWorkers || runAllSessionWorkers.length === 0) {
      return;
    }

    let cancelled = false;

    const hasActive = runAllSessionWorkers.some((w) => w.phase === "running" || w.phase === "pending");
    if (!hasActive) {
      setRunAllSessionCompleted(true);
      return;
    }

    const pollOnce = async () => {
      if (cancelled) return;
      try {
        const nextState: RunAllWorkerLiveStatus[] = [...runAllSessionWorkers];
        for (const worker of runAllSessionWorkers) {
          if (!worker.run_id || (worker.phase !== "running" && worker.phase !== "pending")) {
            continue;
          }
          try {
            const logsResp = await api.get(`/ebay/workers/logs/${worker.run_id}`);
            const run = logsResp.data?.run;
            const summary = run?.summary as any;
            const idx = nextState.findIndex((w) => w.api_family === worker.api_family);
            if (idx === -1) continue;
            const updated: RunAllWorkerLiveStatus = { ...nextState[idx] };
            if (run?.status === "completed") {
              updated.phase = "completed";
            } else if (run?.status === "error") {
              updated.phase = "error";
            } else if (run?.status === "running") {
              updated.phase = "running";
            }
            if (summary) {
              updated.summary = {
                total_fetched: summary.total_fetched ?? null,
                total_stored: summary.total_stored ?? null,
              };
            }
            nextState[idx] = updated;
          } catch (err) {
            // eslint-disable-next-line no-console
            console.error("Failed to poll worker run status", err);
          }
        }
        if (!cancelled) {
          setRunAllSessionWorkers(nextState);
          const allDone = nextState.every((w) =>
            w.phase === "completed" ||
            w.phase === "error" ||
            w.phase === "skipped" ||
            !w.run_id,
          );
          if (allDone) {
            setRunAllSessionCompleted(true);
          }
        }
      } catch (err) {
        // eslint-disable-next-line no-console
        console.error("Run-all status polling failed", err);
      }
    };

    void pollOnce();
    const id = window.setInterval(() => {
      void pollOnce();
    }, 3000);

    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [runAllOpen, runAllSessionWorkers]);

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
              <div className="mt-1 flex flex-wrap items-center gap-3 text-[11px] text-gray-500">
                <span className="flex items-center gap-1">
                  <span className="inline-block h-2 w-2 rounded-full bg-green-500" />
                  Last run OK
                </span>
                <span className="flex items-center gap-1">
                  <span className="inline-block h-2 w-2 rounded-full bg-yellow-400" />
                  Running
                </span>
                <span className="flex items-center gap-1">
                  <span className="inline-block h-2 w-2 rounded-full bg-red-500" />
                  Last run error
                </span>
                <span className="flex items-center gap-1">
                  <span className="inline-block h-2 w-2 rounded-full bg-gray-300" />
                  Disabled / no runs
                </span>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={toggleGlobal}
                className={`px-4 py-2 font-semibold rounded shadow text-white ${
                  config.workers_enabled ? "bg-red-600" : "bg-green-600"
                }`}
              >
                {config.workers_enabled ? "BIG RED BUTTON: TURN OFF ALL JOBS" : "Enable all workers"}
              </button>
              <button
                onClick={() => {
                  setRunAllOpen(true);
                  setRunAllResult(null);
                }}
                className="px-4 py-2 font-semibold rounded shadow text-white bg-blue-600 text-xs"
                disabled={!config.workers_enabled}
              >
                Run ALL workers
              </button>
            </div>
          </div>

          <div className="mt-4 overflow-x-auto">
            <table className="min-w-full text-sm border">
              <thead>
                <tr className="bg-gray-100">
                  <th className="px-3 py-2 text-left">API</th>
                  <th className="px-3 py-2 text-left">Status</th>
                  <th className="px-3 py-2 text-left">Last run</th>
                  <th className="px-3 py-2 text-left">Cursor</th>
                  <th className="px-3 py-2 text-left">Primary key</th>
                  <th className="px-3 py-2 text-left">Actions</th>
                </tr>
              </thead>
              <tbody>
                {config.workers.map((w) => (
                <tr key={w.api_family} className="border-t">
                  <td className="px-3 py-2 font-medium align-top">
                    <div className="flex items-center gap-1">
                      <div className="font-medium capitalize">{w.api_family}</div>
                      {API_INFO[w.api_family] && (
                        <div
                          className="relative inline-flex items-center justify-center h-4 w-4 rounded-full border text-[10px] cursor-default group"
                          onMouseEnter={() => setHoveredApi(w.api_family)}
                          onMouseLeave={() => setHoveredApi((current) => (current === w.api_family ? null : current))}
                        >
                          <span className="leading-none text-gray-600">i</span>
                          {hoveredApi === w.api_family && (
                            <div className="absolute z-20 mt-1 left-0 transform translate-y-full min-w-[260px] max-w-md border bg-white shadow-lg rounded p-2 text-[11px] text-gray-700">
                              <div className="font-semibold mb-1">{API_INFO[w.api_family].source}</div>
                              <div className="font-mono text-[10px] text-gray-500 mb-1">
                                {API_INFO[w.api_family].endpoint}
                              </div>
                              <div className="mb-1">
                                <span className="font-semibold">Destination:</span>{" "}
                                <span className="font-mono">{API_INFO[w.api_family].destination}</span>
                              </div>
                              <div>
                                <span className="font-semibold">Key columns:</span>{" "}
                                {API_INFO[w.api_family].keys}
                              </div>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex items-center gap-1 mb-1">
                      {(() => {
                        let statusLabel = "";
                        if (!w.enabled) {
                          statusLabel = "Disabled: worker will not run on schedule.";
                        } else if (w.last_error || w.last_run_status === "error") {
                          statusLabel = "Error: last run failed; see 'Last error' for details.";
                        } else if (w.last_run_status === "running") {
                          statusLabel = "Running: worker is currently in progress.";
                        } else if (!w.last_run_status) {
                          statusLabel = "Idle: worker is enabled but has not run yet.";
                        } else {
                          statusLabel = "Healthy: last run completed without errors.";
                        }
                        const dotClass = w.enabled && !w.last_error && w.last_run_status === "completed"
                          ? "bg-green-500"
                          : w.last_error || w.last_run_status === "error"
                          ? "bg-red-500"
                          : w.last_run_status === "running"
                          ? "bg-yellow-400"
                          : "bg-gray-300";
                        return (
                          <span
                            className={`inline-block h-2 w-2 rounded-full ${dotClass}`}
                            title={statusLabel}
                          />
                        );
                      })()}
                      <span
                        className={`inline-flex items-center px-2 py-1 rounded text-xs font-semibold ${
                          w.enabled ? "bg-green-100 text-green-800" : "bg-gray-100 text-gray-600"
                        }`}
                      >
                        {w.enabled ? "Enabled" : "Disabled"}
                      </span>
                    </div>
                    {(() => {
                      const nextRun = getNextRunForApi(w.api_family);
                      if (!nextRun || !w.enabled) return null;
                      return (
                        <div className="text-[11px] text-gray-500 mb-1">
                          Next run: {formatDateTimeLocal(nextRun.run_at)}
                        </div>
                      );
                    })()}
                    {w.last_run_summary && (
                      <div className="text-[11px] text-gray-600 max-w-xs">
                        Last run: fetched {w.last_run_summary?.total_fetched ?? "–"}, stored {" "}
                        {w.last_run_summary?.total_stored ?? "–"}
                      </div>
                    )}
                    {w.last_error && (
                      <div className="text-xs text-red-600 mt-1 max-w-xs truncate">
                        Last error: {w.last_error}
                      </div>
                    )}
                  </td>
                  <td className="px-3 py-2">
                    <div className="text-xs text-gray-700 space-y-0.5">
                      <div>
                        Started: {formatDateTimeLocal(w.last_run_started_at)}
                        {formatRelativeTime(w.last_run_started_at) && (
                          <span className="ml-1 text-[11px] text-gray-500">
                            ({formatRelativeTime(w.last_run_started_at)})
                          </span>
                        )}
                      </div>
                      <div>
                        Finished: {formatDateTimeLocal(w.last_run_finished_at)}
                        {formatRelativeTime(w.last_run_finished_at) && (
                          <span className="ml-1 text-[11px] text-gray-500">
                            ({formatRelativeTime(w.last_run_finished_at)})
                          </span>
                        )}
                      </div>
                      <div>Status: {w.last_run_status || "–"}</div>
                    </div>
                  </td>
                  <td className="px-3 py-2">
                    <div>Type: {w.cursor_type || "–"}</div>
                    <div>Value: {w.cursor_value || "–"}</div>
                  </td>
                  <td className="px-3 py-2 text-xs text-gray-700 align-top max-w-xs">
                    {w.primary_dedup_key ? (
                      <>
                        <div className="font-mono text-[11px]">{w.primary_dedup_key}</div>
                        <div className="text-[11px] text-gray-500 mt-1">
                          Natural key from eBay data used to avoid duplicates when windows overlap.
                        </div>
                      </>
                    ) : (
                      <span className="text-gray-400 text-[11px]">n/a</span>
                    )}
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
                      className={`px-2 py-1 border rounded text-xs text-white ${
                        runningApiFamily === w.api_family ? "bg-blue-400" : "bg-blue-600"
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
          </div>
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
                <div className="overflow-x-auto">
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
                          <td className="px-2 py-1 whitespace-nowrap">
                            {formatDateTimeLocal(r.run_at)}
                            {formatRelativeTime(r.run_at) && (
                              <span className="ml-1 text-[10px] text-gray-500">
                                ({formatRelativeTime(r.run_at)})
                              </span>
                            )}
                          </td>
                          <td className="px-2 py-1 whitespace-nowrap">{r.window_from ? formatDateTimeLocal(r.window_from) : "–"}</td>
                          <td className="px-2 py-1 whitespace-nowrap">{r.window_to ? formatDateTimeLocal(r.window_to) : "–"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
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
                      await attachTerminalToRun(latest);
                      setSelectedRunId(latest.id);
                    }
                  } else {
                    setSelectedRunId(val);
                    // Try to find the run in the local recentRuns list so we can
                    // derive a sync_run_id even if summary is still null.
                    const run = recentRuns.find((r) => r.id === val) || null;
                    await attachTerminalToRun(run);
                  }
                }}
              >
                <option value="latest">Latest run (all APIs)</option>
                {recentRuns.map((run) => {
                  let label = `${run.api_family}`;
                  if (run.started_at) {
                    label += ` – ${formatDateTimeLocal(run.started_at)}`;
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
              onComplete={() => {}}
              onStop={() => {}}
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
              <>
                {detailsData?.run?.summary && (
                  <div className="mb-2 text-xs text-gray-700 border rounded p-2 bg-gray-50">
                    <div>
                      <span className="font-semibold">API:</span> {detailsData.run.api_family}
                    </div>
                    <div>
                      <span className="font-semibold">Status:</span> {detailsData.run.status}
                    </div>
                    <div>
                      <span className="font-semibold">Window:</span>{' '}
                      {detailsData.run.summary.window_from || "–"} .. {detailsData.run.summary.window_to || "–"}
                    </div>
                    <div>
                      <span className="font-semibold">Fetched / stored:</span>{' '}
                      {detailsData.run.summary.total_fetched ?? "–"} /{' '}
                      {detailsData.run.summary.total_stored ?? "–"}
                    </div>
                  </div>
                )}
                <pre className="text-xs bg-gray-50 p-2 rounded overflow-x-auto whitespace-pre-wrap">
                  {JSON.stringify(detailsData, null, 2)}
                </pre>
              </>
            )}
          </div>
        </div>
      )}

      {runAllOpen && config && (
        <div className="fixed inset-0 bg-black bg-opacity-40 flex items-center justify-center z-50">
          <div className="bg-white rounded shadow-lg max-w-3xl w-full max-h-[80vh] overflow-auto p-4">
            <div className="flex items-center justify-between mb-2">
              <div className="font-semibold">Run ALL workers for this account</div>
              <button
                onClick={() => {
                  setRunAllOpen(false);
                  setRunAllResult(null);
                  setRunAllSessionWorkers(null);
                  setRunAllSessionCompleted(false);
                }}
                className="text-sm text-gray-600"
              >
                Close
              </button>
            </div>
            <div className="text-xs text-gray-700 mb-3">
              Account: {accountLabel || config.account.username || config.account.house_name || config.account.id}
              {ebayUserId && <span className="ml-2">(eBay user id: {ebayUserId})</span>}
            </div>
            <div className="text-xs text-gray-600 mb-2">
              Будут последовательно запущены все включённые воркеры для этого аккаунта.
              Уже запущенные воркеры будут помечены как <span className="font-semibold">already_running</span> и не будут дублироваться.
            </div>
            <div className="mb-3">
              <div className="font-semibold text-xs mb-1">Enabled workers</div>
              <div className="flex flex-wrap gap-1 text-xs">
                {config.workers
                  .filter((w) => w.enabled)
                  .map((w) => (
                    <span key={w.api_family} className="px-2 py-0.5 rounded border bg-gray-50">
                      {w.api_family}
                    </span>
                  ))}
                {config.workers.filter((w) => w.enabled).length === 0 && (
                  <span className="text-gray-500">No enabled workers for this account.</span>
                )}
              </div>
            </div>
            <div className="flex items-center justify-between mb-3">
              <button
                onClick={handleRunAllConfirm}
                disabled={
                  runAllLoading ||
                  !config.workers_enabled ||
                  config.workers.filter((w) => w.enabled).length === 0 ||
                  !!runAllSessionWorkers
                }
                className={`px-3 py-1 rounded text-xs font-semibold text-white ${
                  runAllLoading || runAllSessionWorkers ? "bg-blue-400" : "bg-blue-600"
                }`}
              >
                {runAllLoading
                  ? "Starting…"
                  : runAllSessionWorkers
                  ? "Run in progress…"
                  : "Run ALL workers now"}
              </button>
              {!config.workers_enabled && (
                <div className="text-[11px] text-red-600">Global workers toggle is OFF. Turn it on to start workers.</div>
              )}
            </div>
            {runAllSessionWorkers && (
              <div className="mt-2 border-t pt-2">
                <div className="flex items-center justify-between mb-1">
                  <div className="font-semibold text-xs">Run-all live status</div>
                  {runAllSessionCompleted ? (
                    <span className="text-[11px] text-green-700">Done</span>
                  ) : (
                    <span className="text-[11px] text-gray-500">Updating every 3 seconds…</span>
                  )}
                </div>
                <table className="min-w-full text-[11px]">
                  <thead>
                    <tr className="bg-gray-50">
                      <th className="px-2 py-1 text-left">API</th>
                      <th className="px-2 py-1 text-left">Status</th>
                      <th className="px-2 py-1 text-left">Summary</th>
                      <th className="px-2 py-1 text-left">Details</th>
                    </tr>
                  </thead>
                  <tbody>
                    {runAllSessionWorkers.map((w) => {
                      let label = "Pending";
                      let pillClass = "bg-gray-100 text-gray-800";
                      if (w.phase === "running") {
                        label = "Running";
                        pillClass = "bg-blue-100 text-blue-800";
                      } else if (w.phase === "completed") {
                        label = "Completed";
                        pillClass = "bg-green-100 text-green-800";
                      } else if (w.phase === "error") {
                        label = "Error";
                        pillClass = "bg-red-100 text-red-800";
                      } else if (w.phase === "skipped") {
                        label = "Skipped";
                        pillClass = "bg-gray-100 text-gray-700";
                      }

                      const summaryText = w.summary
                        ? `fetched ${w.summary.total_fetched ?? "–"}, stored ${w.summary.total_stored ?? "–"}`
                        : "";

                      let details = "";
                      if (w.phase === "error" && w.reason) {
                        details = `Last error: ${w.reason}`;
                      } else if (w.phase === "skipped" && w.reason) {
                        if (w.reason === "disabled") {
                          details = "Worker disabled in config";
                        } else if (w.reason === "already_running") {
                          details = "Already running – attached to existing run";
                        } else if (w.reason === "workers_disabled") {
                          details = "Global workers toggle is OFF";
                        } else {
                          details = w.reason;
                        }
                      }

                      return (
                        <tr key={w.api_family} className="border-t">
                          <td className="px-2 py-1 whitespace-nowrap">{w.api_family}</td>
                          <td className="px-2 py-1 whitespace-nowrap">
                            <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold ${pillClass}`}>
                              {label}
                              {w.phase === "running" && (
                                <span className="ml-1 inline-block h-2 w-2 rounded-full bg-blue-500 animate-pulse" />
                              )}
                            </span>
                          </td>
                          <td className="px-2 py-1 whitespace-nowrap text-gray-700">
                            {summaryText || "—"}
                          </td>
                          <td className="px-2 py-1 whitespace-nowrap text-gray-600 max-w-xs truncate" title={details}>
                            {details || (w.run_id ? `run_id: ${w.run_id}` : "—")}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
            {!runAllSessionWorkers && runAllResult && (
              <div className="mt-2 border-t pt-2">
                <div className="font-semibold text-xs mb-1">Run-all result</div>
                <table className="min-w-full text-[11px]">
                  <thead>
                    <tr className="bg-gray-50">
                      <th className="px-2 py-1 text-left">API</th>
                      <th className="px-2 py-1 text-left">Status</th>
                      <th className="px-2 py-1 text-left">Run ID / Reason</th>
                    </tr>
                  </thead>
                  <tbody>
                    {runAllResult.results.map((r) => (
                      <tr key={r.api_family} className="border-t">
                        <td className="px-2 py-1 whitespace-nowrap">{r.api_family}</td>
                        <td className="px-2 py-1 whitespace-nowrap">{r.status}</td>
                        <td className="px-2 py-1 whitespace-nowrap">
                          {r.run_id ? (
                            <span className="text-gray-700">run_id: {r.run_id}</span>
                          ) : r.reason ? (
                            <span className="text-gray-500">{r.reason}</span>
                          ) : (
                            <span className="text-gray-400">–</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
