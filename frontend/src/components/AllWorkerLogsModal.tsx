import React, { useState, useEffect, useMemo } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ebayApi } from "@/api/ebay";
import { formatDateTimeLocal } from "@/lib/dateUtils";
import { Loader2, Trash2, Search, X } from "lucide-react";

interface WorkerRun {
  id: string;
  ebay_account_id: string;
  ebay_user_id: string;
  account_house_name: string | null;
  api_family: string;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  summary: any;
}

interface AllWorkerLogsModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const API_FAMILIES = [
  "orders",
  "transactions",
  "active_inventory",
  "offers",
  "messages",
  "cases",
  "finances",
  "buyer",
  "inquiries",
  "returns",
];

const STATUS_OPTIONS = ["running", "completed", "error", "cancelled", "stale"];

export const AllWorkerLogsModal: React.FC<AllWorkerLogsModalProps> = ({
  isOpen,
  onClose,
}) => {
  const [runs, setRuns] = useState<WorkerRun[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);

  // Filters
  const [accountSearch, setAccountSearch] = useState("");
  const [apiFamilyFilter, setApiFamilyFilter] = useState<string>("all");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [daysToKeep, setDaysToKeep] = useState<number>(3);

  // Pagination
  const [limit] = useState(500);
  const [offset, setOffset] = useState(0);

  const fetchRuns = async () => {
    setLoading(true);
    setError(null);
    try {
      const params: any = {
        limit,
        offset,
      };
      if (accountSearch.trim()) {
        params.ebay_account_id = accountSearch.trim();
      }
      if (apiFamilyFilter !== "all") {
        params.api_family = apiFamilyFilter;
      }
      if (statusFilter !== "all") {
        params.status_filter = statusFilter;
      }

      const data = await ebayApi.getAllWorkerRuns(params);
      setRuns(data.runs);
      setTotal(data.total);
    } catch (e: any) {
      console.error("Failed to fetch worker runs", e);
      setError(e?.response?.data?.detail || e.message || "Failed to fetch worker runs");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      fetchRuns();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, accountSearch, apiFamilyFilter, statusFilter, offset]);

  const handleCleanup = async () => {
    if (!confirm(`Are you sure you want to delete all worker logs older than ${daysToKeep} days? This action cannot be undone.`)) {
      return;
    }

    setDeleting(true);
    try {
      const result = await ebayApi.cleanupOldWorkerLogs(daysToKeep);
      alert(`Successfully deleted ${result.deleted_runs} runs and ${result.deleted_logs} log entries.`);
      // Refresh the list
      await fetchRuns();
    } catch (e: any) {
      console.error("Failed to cleanup logs", e);
      alert(`Failed to cleanup logs: ${e?.response?.data?.detail || e.message || "Unknown error"}`);
    } finally {
      setDeleting(false);
    }
  };

  const filteredRuns = useMemo(() => {
    return runs.filter((run) => {
      if (accountSearch.trim()) {
        const searchLower = accountSearch.toLowerCase();
        const matchesAccountId = run.ebay_account_id.toLowerCase().includes(searchLower);
        const matchesUserId = run.ebay_user_id?.toLowerCase().includes(searchLower);
        const matchesHouseName = run.account_house_name?.toLowerCase().includes(searchLower);
        if (!matchesAccountId && !matchesUserId && !matchesHouseName) {
          return false;
        }
      }
      return true;
    });
  }, [runs, accountSearch]);

  const getStatusColor = (status: string) => {
    switch (status) {
      case "completed":
        return "text-green-600 bg-green-50";
      case "error":
        return "text-red-600 bg-red-50";
      case "running":
        return "text-blue-600 bg-blue-50";
      case "cancelled":
        return "text-gray-600 bg-gray-50";
      case "stale":
        return "text-yellow-600 bg-yellow-50";
      default:
        return "text-gray-600 bg-gray-50";
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-7xl max-h-[90vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle>All Worker Logs</DialogTitle>
        </DialogHeader>

        <div className="flex-1 flex flex-col gap-4 overflow-hidden">
          {/* Filters */}
          <div className="flex flex-wrap gap-4 items-end border-b pb-4">
            <div className="flex-1 min-w-[200px]">
              <label className="text-sm font-medium mb-1 block">Search Account</label>
              <div className="relative">
                <Search className="absolute left-2 top-2.5 h-4 w-4 text-gray-400" />
                <Input
                  placeholder="Account ID, User ID, or House Name"
                  value={accountSearch}
                  onChange={(e) => setAccountSearch(e.target.value)}
                  className="pl-8"
                />
                {accountSearch && (
                  <button
                    onClick={() => setAccountSearch("")}
                    className="absolute right-2 top-2.5 text-gray-400 hover:text-gray-600"
                  >
                    <X className="h-4 w-4" />
                  </button>
                )}
              </div>
            </div>

            <div className="min-w-[150px]">
              <label className="text-sm font-medium mb-1 block">API Family</label>
              <Select value={apiFamilyFilter} onValueChange={setApiFamilyFilter}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All</SelectItem>
                  {API_FAMILIES.map((api) => (
                    <SelectItem key={api} value={api}>
                      {api}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="min-w-[150px]">
              <label className="text-sm font-medium mb-1 block">Status</label>
              <Select value={statusFilter} onValueChange={setStatusFilter}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All</SelectItem>
                  {STATUS_OPTIONS.map((status) => (
                    <SelectItem key={status} value={status}>
                      {status}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <Button onClick={fetchRuns} disabled={loading} variant="outline">
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Refresh"}
            </Button>
          </div>

          {/* Cleanup Section */}
          <div className="flex items-center gap-4 border-b pb-4">
            <div className="flex items-center gap-2">
              <label className="text-sm font-medium">Keep logs for:</label>
              <Select
                value={String(daysToKeep)}
                onValueChange={(v) => setDaysToKeep(Number(v))}
              >
                <SelectTrigger className="w-24">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="2">2 days</SelectItem>
                  <SelectItem value="3">3 days</SelectItem>
                  <SelectItem value="4">4 days</SelectItem>
                  <SelectItem value="5">5 days</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <Button
              onClick={handleCleanup}
              disabled={deleting}
              variant="destructive"
              size="sm"
            >
              {deleting ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin mr-2" />
                  Deleting...
                </>
              ) : (
                <>
                  <Trash2 className="h-4 w-4 mr-2" />
                  Delete Older Logs
                </>
              )}
            </Button>
            <span className="text-sm text-gray-500">
              This will delete all runs and logs older than {daysToKeep} days
            </span>
          </div>

          {/* Error Message */}
          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-2 rounded">
              {error}
            </div>
          )}

          {/* Grid */}
          <div className="flex-1 overflow-auto border rounded">
            <div className="min-w-full">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 sticky top-0">
                  <tr>
                    <th className="px-4 py-2 text-left font-medium">Started At</th>
                    <th className="px-4 py-2 text-left font-medium">Account</th>
                    <th className="px-4 py-2 text-left font-medium">API Family</th>
                    <th className="px-4 py-2 text-left font-medium">Status</th>
                    <th className="px-4 py-2 text-left font-medium">Finished At</th>
                    <th className="px-4 py-2 text-left font-medium">Duration</th>
                    <th className="px-4 py-2 text-left font-medium">Summary</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {loading && filteredRuns.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="px-4 py-8 text-center text-gray-500">
                        <Loader2 className="h-6 w-6 animate-spin mx-auto mb-2" />
                        Loading...
                      </td>
                    </tr>
                  ) : filteredRuns.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="px-4 py-8 text-center text-gray-500">
                        No worker runs found
                      </td>
                    </tr>
                  ) : (
                    filteredRuns.map((run) => {
                      const started = run.started_at ? new Date(run.started_at) : null;
                      const finished = run.finished_at ? new Date(run.finished_at) : null;
                      const duration =
                        started && finished
                          ? `${((finished.getTime() - started.getTime()) / 1000).toFixed(1)}s`
                          : run.status === "running"
                          ? "Running..."
                          : "-";

                      return (
                        <tr key={run.id} className="hover:bg-gray-50">
                          <td className="px-4 py-2">
                            {run.started_at ? formatDateTimeLocal(run.started_at) : "-"}
                          </td>
                          <td className="px-4 py-2">
                            <div className="flex flex-col">
                              <span className="font-medium">
                                {run.account_house_name || run.ebay_account_id}
                              </span>
                              <span className="text-xs text-gray-500">
                                {run.ebay_user_id}
                              </span>
                            </div>
                          </td>
                          <td className="px-4 py-2">
                            <span className="font-mono text-xs">{run.api_family}</span>
                          </td>
                          <td className="px-4 py-2">
                            <span
                              className={`inline-flex items-center px-2 py-1 rounded text-xs font-medium ${getStatusColor(
                                run.status
                              )}`}
                            >
                              {run.status}
                            </span>
                          </td>
                          <td className="px-4 py-2">
                            {run.finished_at ? formatDateTimeLocal(run.finished_at) : "-"}
                          </td>
                          <td className="px-4 py-2">{duration}</td>
                          <td className="px-4 py-2">
                            {run.summary ? (
                              <div className="text-xs text-gray-600 max-w-xs truncate">
                                {run.summary.total_fetched !== undefined && (
                                  <span>Fetched: {run.summary.total_fetched}</span>
                                )}
                                {run.summary.total_stored !== undefined && (
                                  <span className="ml-2">Stored: {run.summary.total_stored}</span>
                                )}
                              </div>
                            ) : (
                              "-"
                            )}
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* Pagination Info */}
          <div className="flex items-center justify-between text-sm text-gray-600 border-t pt-2">
            <div>
              Showing {filteredRuns.length} of {total} runs
            </div>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setOffset(Math.max(0, offset - limit))}
                disabled={offset === 0 || loading}
              >
                Previous
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setOffset(offset + limit)}
                disabled={offset + limit >= total || loading}
              >
                Next
              </Button>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};

