import React, { useEffect, useState } from 'react';
import FixedHeader from '@/components/FixedHeader';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { ebayApi, TestListingConfigDto, TestListingLogSummaryDto, TestListingLogDetailDto } from '@/api/ebay';
import { WorkerDebugTerminalModal } from '@/components/WorkerDebugTerminalModal';
import type { WorkerDebugTrace } from '@/api/ebayListingWorker';
import { formatDateTimeLocal } from '@/lib/dateUtils';

const INVENTORY_STATUS_OPTIONS = [
  'PENDING_LISTING',
  'AVAILABLE',
  'LISTED',
  'SOLD',
  'FROZEN',
  'REPAIR',
  'RETURNED',
];

const AdminTestListingPage: React.FC = () => {
  const [config, setConfig] = useState<TestListingConfigDto | null>(null);
  const [configLoading, setConfigLoading] = useState(false);
  const [configError, setConfigError] = useState<string | null>(null);

  const [logs, setLogs] = useState<TestListingLogSummaryDto[]>([]);
  const [logsTotal, setLogsTotal] = useState(0);
  const [logsLoading, setLogsLoading] = useState(false);
  const [logsError, setLogsError] = useState<string | null>(null);

  const [runLoading, setRunLoading] = useState(false);
  const [runMessage, setRunMessage] = useState<string | null>(null);

  const [selectedLogDetail, setSelectedLogDetail] = useState<TestListingLogDetailDto | null>(null);
  const [terminalOpen, setTerminalOpen] = useState(false);

  const loadConfig = async () => {
    try {
      setConfigLoading(true);
      setConfigError(null);
      const data = await ebayApi.getTestListingConfig();
      setConfig(data);
    } catch (e: any) {
      // eslint-disable-next-line no-console
      console.error('Failed to load test-listing config', e);
      setConfigError(e?.response?.data?.detail || e.message || 'Failed to load config');
    } finally {
      setConfigLoading(false);
    }
  };

  const loadLogs = async () => {
    try {
      setLogsLoading(true);
      setLogsError(null);
      const resp = await ebayApi.getTestListingLogs({ limit: 50, offset: 0 });
      setLogs(resp.items || []);
      setLogsTotal(resp.total || 0);
    } catch (e: any) {
      // eslint-disable-next-line no-console
      console.error('Failed to load test-listing logs', e);
      setLogsError(e?.response?.data?.detail || e.message || 'Failed to load logs');
    } finally {
      setLogsLoading(false);
    }
  };

  useEffect(() => {
    void loadConfig();
    void loadLogs();
  }, []);

  const handleToggleDebug = async () => {
    if (!config) return;
    try {
      const next = await ebayApi.updateTestListingConfig({
        debug_enabled: !config.debug_enabled,
      });
      setConfig(next);
    } catch (e: any) {
      // eslint-disable-next-line no-console
      console.error('Failed to update debug flag', e);
      setConfigError(e?.response?.data?.detail || e.message || 'Failed to update debug flag');
    }
  };

  const handleChangeStatus = async (value: string) => {
    try {
      const next = await ebayApi.updateTestListingConfig({
        test_inventory_status: value,
      });
      setConfig(next);
    } catch (e: any) {
      // eslint-disable-next-line no-console
      console.error('Failed to update test status', e);
      setConfigError(e?.response?.data?.detail || e.message || 'Failed to update test status');
    }
  };

  const handleChangeMaxItems = async (value: string) => {
    if (!config) return;
    const parsed = parseInt(value || '0', 10);
    if (!Number.isFinite(parsed) || parsed <= 0) return;
    try {
      const next = await ebayApi.updateTestListingConfig({
        max_items_per_run: parsed,
      } as any);
      setConfig(next);
    } catch (e: any) {
      // eslint-disable-next-line no-console
      console.error('Failed to update max_items_per_run', e);
      setConfigError(e?.response?.data?.detail || e.message || 'Failed to update max items');
    }
  };

  const handleRunOnce = async () => {
    try {
      setRunLoading(true);
      setRunMessage(null);
      const resp = await ebayApi.runTestListingOnce();
      setRunMessage(
        `Run complete: selected=${resp.items_selected}, processed=${resp.items_processed}, success=${resp.items_success}, failed=${resp.items_failed}`,
      );
      await loadLogs();
    } catch (e: any) {
      // eslint-disable-next-line no-console
      console.error('Failed to run test-listing once', e);
      setRunMessage(e?.response?.data?.detail || e.message || 'Failed to run test-listing');
    } finally {
      setRunLoading(false);
    }
  };

  const handleOpenLog = async (logId: number) => {
    try {
      const detail = await ebayApi.getTestListingLogDetail(logId);
      setSelectedLogDetail(detail);
      setTerminalOpen(true);
    } catch (e: any) {
      // eslint-disable-next-line no-console
      console.error('Failed to load test-listing log detail', e);
      setLogsError(e?.response?.data?.detail || e.message || 'Failed to load log detail');
    }
  };

  const trace: WorkerDebugTrace | null = (selectedLogDetail?.trace || null) as WorkerDebugTrace | null;

  return (
    <div className="min-h-screen bg-gray-50">
      <FixedHeader />
      <main className="w-full pt-14 px-4 sm:px-6 lg:px-10 py-4">
        <div className="w-full mx-auto space-y-4">
          <h1 className="text-xl font-semibold mb-1">eBay Test Listing</h1>
          <p className="text-xs text-gray-600 max-w-3xl mb-2">
            Интерфейс для тестового листинга через существующий eBay listing worker. Здесь можно включить глубокий
            debug, выбрать статус Inventory для теста и запускать тест-листинг с сохранением полного HTTP-трейса.
          </p>

          <Card className="p-0">
            <CardHeader className="py-2 px-3 pb-1 flex items-center justify-between">
              <CardTitle className="text-sm font-semibold">Configuration</CardTitle>
            </CardHeader>
            <CardContent className="py-2 px-3 space-y-2 text-xs">
              {configLoading && <div className="text-gray-600">Loading config…</div>}
              {configError && <div className="text-red-600">{configError}</div>}
              {config && (
                <div className="flex flex-wrap items-center gap-4">
                  <div className="flex items-center gap-2">
                    <span className="text-gray-700">Debug mode</span>
                    <button
                      type="button"
                      className="relative inline-flex h-5 w-10 items-center rounded-full border border-gray-300 bg-white transition-colors"
                      onClick={handleToggleDebug}
                    >
                      <span
                        className={`inline-block h-4 w-4 transform rounded-full bg-gray-400 shadow transition-transform ${
                          config.debug_enabled ? 'translate-x-5 bg-green-500' : 'translate-x-1'
                        }`}
                      />
                    </button>
                    <span className="text-[11px] text-gray-500">
                      {config.debug_enabled
                        ? 'Full WorkerDebugTrace (headers + JSON body) will be persisted for each run.'
                        : 'Only summary will be returned; heavy HTTP trace is not stored.'}
                    </span>
                  </div>

                  <div className="flex items-center gap-2">
                    <span className="text-gray-700">Test Inventory status</span>
                    <select
                      className="border rounded px-2 py-1 text-[11px]"
                      value={config.test_inventory_status || ''}
                      onChange={(e) => handleChangeStatus(e.target.value)}
                    >
                      <option value="">— not configured —</option>
                      {INVENTORY_STATUS_OPTIONS.map((opt) => (
                        <option key={opt} value={opt}>
                          {opt}
                        </option>
                      ))}
                    </select>
                    <span className="text-[11px] text-gray-500">
                      Inventory.rows с этим статусом и пустым ebay_listing_id будут кандидатами для тест-листинга.
                    </span>
                  </div>

                  <div className="flex items-center gap-2">
                    <span className="text-gray-700">Max items per run</span>
                    <input
                      type="number"
                      min={1}
                      max={200}
                      className="border rounded px-2 py-1 text-[11px] w-20"
                      value={config.max_items_per_run}
                      onChange={(e) => handleChangeMaxItems(e.target.value)}
                    />
                  </div>

                  <div className="flex items-center gap-3">
                    <button
                      type="button"
                      className="px-3 py-1 rounded bg-blue-600 text-white text-[11px] font-medium hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed"
                      onClick={handleRunOnce}
                      disabled={runLoading}
                    >
                      {runLoading ? 'Running…' : 'Run test-listing once'}
                    </button>
                    {runMessage && (
                      <span className="text-[11px] text-gray-700">{runMessage}</span>
                    )}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          <Card className="p-0">
            <CardHeader className="py-2 px-3 pb-1 flex items-center justify-between">
              <CardTitle className="text-sm font-semibold">Recent test-listing runs</CardTitle>
            </CardHeader>
            <CardContent className="py-2 px-3 text-xs">
              {logsLoading && <div className="text-gray-600 mb-1">Loading logs…</div>}
              {logsError && <div className="text-red-600 mb-1">{logsError}</div>}
              {!logsLoading && logs.length === 0 && (
                <div className="text-gray-600">No test-listing logs yet.</div>
              )}
              {logs.length > 0 && (
                <div className="overflow-x-auto">
                  <table className="min-w-full text-[11px] border">
                    <thead className="bg-gray-100">
                      <tr>
                        <th className="px-2 py-1 text-left">ID</th>
                        <th className="px-2 py-1 text-left">Created at</th>
                        <th className="px-2 py-1 text-left">Status</th>
                        <th className="px-2 py-1 text-left">Mode</th>
                        <th className="px-2 py-1 text-left">Account</th>
                        <th className="px-2 py-1 text-left">Error</th>
                        <th className="px-2 py-1 text-left">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {logs.map((row) => (
                        <tr key={row.id} className="border-t hover:bg-gray-50">
                          <td className="px-2 py-1 whitespace-nowrap">{row.id}</td>
                          <td className="px-2 py-1 whitespace-nowrap">
                            {formatDateTimeLocal(row.created_at)}
                          </td>
                          <td className="px-2 py-1 whitespace-nowrap">
                            <span
                              className={`px-2 py-0.5 rounded text-[11px] font-semibold ${
                                row.status === 'SUCCESS'
                                  ? 'bg-green-100 text-green-800'
                                  : 'bg-red-100 text-red-800'
                              }`}
                            >
                              {row.status}
                            </span>
                          </td>
                          <td className="px-2 py-1 whitespace-nowrap">{row.mode}</td>
                          <td className="px-2 py-1 whitespace-nowrap max-w-xs truncate">
                            {row.account_label || '—'}
                          </td>
                          <td className="px-2 py-1 whitespace-nowrap max-w-xs truncate">
                            {row.error_message || '—'}
                          </td>
                          <td className="px-2 py-1 whitespace-nowrap">
                            <button
                              type="button"
                              className="px-2 py-0.5 border rounded text-[11px] bg-white hover:bg-gray-50"
                              onClick={() => void handleOpenLog(row.id)}
                            >
                              Open terminal
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <div className="mt-1 text-[11px] text-gray-500">Total: {logsTotal}</div>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </main>

      <WorkerDebugTerminalModal
        isOpen={terminalOpen && !!trace}
        onClose={() => {
          setTerminalOpen(false);
          setSelectedLogDetail(null);
        }}
        trace={trace}
      />
    </div>
  );
};

export default AdminTestListingPage;
