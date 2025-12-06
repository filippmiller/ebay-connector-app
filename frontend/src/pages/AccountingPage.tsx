import { useState, useMemo, useEffect } from 'react';
import { Routes, Route, Navigate, useLocation, useNavigate, useParams } from 'react-router-dom';
import FixedHeader from '@/components/FixedHeader';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useAuth } from '@/auth/AuthContext';
import { DataGridPage } from '@/components/DataGridPage';
import api from '@/lib/apiClient';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';

interface AccountingCategory {
  id: number;
  code: string;
  name: string;
}

interface AccountingRule {
  id: number;
  pattern_type: string;
  pattern_value: string;
  expense_category_id: number;
  priority: number;
  is_active: boolean;
}

interface UploadResult {
  id: number;
  status: string;
  bank_name?: string;
  account_last4?: string;
  currency?: string;
  period_start?: string;
  period_end?: string;
  rows_count?: number;
  message?: string;

  logs?: ProcessLog[];
}

interface ProcessLog {
  timestamp: string;
  level: string;
  message: string;
}

function BankStatementsList() {
  const navigate = useNavigate();
  const [bankName, setBankName] = useState('');
  const [status, setStatus] = useState('');
  const [periodFrom, setPeriodFrom] = useState('');
  const [periodTo, setPeriodTo] = useState('');

  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<UploadResult | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const extraParams = useMemo(() => {
    const params: Record<string, string> = {};
    if (bankName) params.bank_name = bankName;
    if (status) params.status = status;
    if (periodFrom) params.period_from = periodFrom;
    if (periodTo) params.period_to = periodTo;
    params._refresh = String(refreshKey);
    return params;
  }, [bankName, status, periodFrom, periodTo, refreshKey]);

  const [testingOpenAI, setTestingOpenAI] = useState(false);
  const handleTestOpenAI = async () => {
    setTestingOpenAI(true);
    try {
      const resp = await api.post('/accounting/test-openai');
      alert(`OpenAI Test: ${resp.data.success ? 'SUCCESS' : 'FAILED'}\n${resp.data.message}\nLatency: ${resp.data.latency_ms}ms`);
    } catch (e: any) {
      alert(`Test Failed: ${e.message}`);
    } finally {
      setTestingOpenAI(false);
    }
  };

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) return;

    setUploading(true);
    setUploadResult(null);
    setUploadError(null);

    try {
      const form = new FormData();
      form.append('file', file);

      const response = await api.post<UploadResult>('/accounting/bank-statements', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });

      setUploadResult(response.data);
      setRefreshKey((v) => v + 1);
      setFile(null);

      // Reset file input
      const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
      if (fileInput) fileInput.value = '';
    } catch (err: any) {
      const errorMsg = err?.response?.data?.detail || err?.message || 'Upload failed';
      setUploadError(errorMsg);
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="flex-1 flex flex-col gap-4">
      {/* Simple Upload Card */}
      <Card className="p-5 border-2 border-dashed border-gray-200 hover:border-blue-300 transition-colors">
        <form onSubmit={handleUpload}>
          <div className="flex flex-col items-center gap-4">
            <div className="text-center">
              <h2 className="text-lg font-semibold text-gray-800">Upload Bank Statement</h2>
              <p className="text-sm text-gray-500 mt-1">
                PDF, CSV, or Excel files • AI will extract bank info and transactions automatically
              </p>

              <div className="mt-2">
                <Button variant="outline" size="sm" onClick={handleTestOpenAI} disabled={testingOpenAI}>
                  {testingOpenAI ? 'Testing...' : 'Test OpenAI Connection'}
                </Button>
              </div>
            </div>

            <div className="flex items-center gap-4 w-full max-w-xl">
              <div className="flex-1">
                <Input
                  type="file"
                  accept=".csv,.txt,.pdf,.xlsx,.xls"
                  onChange={(e) => {
                    setFile(e.target.files?.[0] ?? null);
                    setUploadResult(null);
                    setUploadError(null);
                  }}
                  className="cursor-pointer"
                />
              </div>
              <Button
                type="submit"
                disabled={uploading || !file}
                className="min-w-[140px]"
              >
                {uploading ? (
                  <span className="flex items-center gap-2">
                    <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                    </svg>
                    Parsing...
                  </span>
                ) : 'Upload & Parse'}
              </Button>
            </div>

            {/* Upload Result */}
            {uploadResult && (
              <div className="w-full max-w-xl p-4 bg-emerald-50 border border-emerald-200 rounded-lg">
                <div className="flex items-start gap-3">
                  <svg className="w-5 h-5 text-emerald-600 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  <div className="flex-1">
                    <p className="font-medium text-emerald-800">{uploadResult.message || 'Upload successful'}</p>
                    <div className="mt-2 text-sm text-emerald-700 grid grid-cols-2 gap-x-4 gap-y-1">
                      {uploadResult.bank_name && (
                        <span><strong>Bank:</strong> {uploadResult.bank_name}</span>
                      )}
                      {uploadResult.account_last4 && (
                        <span><strong>Account:</strong> ****{uploadResult.account_last4}</span>
                      )}
                      {uploadResult.currency && (
                        <span><strong>Currency:</strong> {uploadResult.currency}</span>
                      )}
                      {uploadResult.rows_count !== undefined && (
                        <span><strong>Transactions:</strong> {uploadResult.rows_count}</span>
                      )}
                      {uploadResult.period_start && uploadResult.period_end && (
                        <span className="col-span-2">
                          <strong>Period:</strong> {uploadResult.period_start} to {uploadResult.period_end}
                        </span>
                      )}
                    </div>
                    {uploadResult.id && (
                      <Button
                        variant="link"
                        className="p-0 h-auto mt-2 text-emerald-700"
                        onClick={() => navigate(`/accounting/bank-statements/${uploadResult.id}`)}
                      >
                        View Statement →
                      </Button>
                    )}

                    {uploadResult.logs && uploadResult.logs.length > 0 && (
                      <div className="mt-3 pt-3 border-t border-emerald-200/50">
                        <div className="text-xs font-semibold text-emerald-800 mb-1">Process Logs</div>
                        <div className="max-h-32 overflow-auto text-[10px] font-mono flex flex-col gap-0.5 text-emerald-900/80">
                          {uploadResult.logs.map((log, i) => (
                            <div key={i}>[{new Date(log.timestamp).toLocaleTimeString()}] {log.message}</div>
                          ))}
                        </div>
                      </div>
                    )}

                  </div>
                </div>
              </div>
            )}

            {/* Upload Error */}
            {uploadError && (
              <div className="w-full max-w-xl p-4 bg-red-50 border border-red-200 rounded-lg">
                <div className="flex items-start gap-3">
                  <svg className="w-5 h-5 text-red-600 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  <div>
                    <p className="font-medium text-red-800">Upload failed</p>
                    <p className="text-sm text-red-700 mt-1">{uploadError}</p>
                  </div>
                </div>
              </div>
            )}
          </div>
        </form>
      </Card>

      {/* Filters and Grid */}
      <div className="flex flex-col gap-3 flex-1 min-h-0">
        <div className="flex flex-wrap gap-3 items-end">
          <div>
            <Label className="block text-xs mb-1">Bank</Label>
            <Input value={bankName} onChange={(e) => setBankName(e.target.value)} placeholder="Filter by bank..." />
          </div>
          <div>
            <Label className="block text-xs mb-1">Status</Label>
            <select
              className="border rounded px-2 py-1.5 text-sm"
              value={status}
              onChange={(e) => setStatus(e.target.value)}
            >
              <option value="">All statuses</option>
              <option value="uploaded">Uploaded</option>
              <option value="processing">Processing (Pending)</option>
              <option value="parsed">Parsed</option>
              <option value="review_in_progress">In Review</option>
              <option value="error_parsing_failed">Error</option>
            </select>
          </div>
          <div>
            <Label className="block text-xs mb-1">From</Label>
            <Input type="date" value={periodFrom} onChange={(e) => setPeriodFrom(e.target.value)} />
          </div>
          <div>
            <Label className="block text-xs mb-1">To</Label>
            <Input type="date" value={periodTo} onChange={(e) => setPeriodTo(e.target.value)} />
          </div>
        </div>
        <div className="flex-1 min-h-0">
          <DataGridPage
            gridKey="accounting_bank_statements"
            title="Bank Statements"
            extraParams={extraParams}
            onRowClick={(row) => {
              if (row.id) navigate(`/accounting/bank-statements/${row.id}`);
            }}
          />
        </div>
      </div>
    </div >
  );
}

function BankStatementDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [summary, setSummary] = useState<any | null>(null);
  const [rows, setRows] = useState<any[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [categories, setCategories] = useState<AccountingCategory[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');

  const loadData = async () => {
    if (!id) return;
    setLoading(true);
    try {
      const [summaryResp, rowsResp, catsResp] = await Promise.all([
        api.get(`/accounting/bank-statements/${id}`),
        api.get(`/accounting/bank-statements/${id}/rows`, { params: { limit: 1000, search: search || undefined } }),
        api.get('/accounting/categories', { params: { is_active: true } }),
      ]);
      setSummary(summaryResp.data);
      setRows(rowsResp.data.rows || []);
      setCategories(catsResp.data || []);
      setSelectedIds(new Set());
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, search]);

  const toggleSelected = (rowId: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(rowId)) next.delete(rowId);
      else next.add(rowId);
      return next;
    });
  };

  const markIgnored = async () => {
    const ids = Array.from(selectedIds);
    for (const rowId of ids) {
      await api.put(`/accounting/bank-rows/${rowId}`, { parsed_status: 'ignored' });
    }
    await loadData();
  };

  const commitSelected = async () => {
    if (!id || selectedIds.size === 0) return;
    const params = new URLSearchParams();
    Array.from(selectedIds).forEach((rid) => params.append('row_ids', String(rid)));
    await api.post(`/accounting/bank-statements/${id}/commit-rows?${params.toString()}`);
    await loadData();
  };

  const commitAll = async () => {
    if (!id) return;
    await api.post(`/accounting/bank-statements/${id}/commit-rows`, {
      commit_all_non_ignored: true,
    });
    await loadData();
  };

  const updateRow = async (rowId: number, patch: any) => {
    await api.put(`/accounting/bank-rows/${rowId}`, patch);
    setRows((prev) => prev.map((r) => (r.id === rowId ? { ...r, ...patch } : r)));
  };

  if (!id) return null;

  return (
    <div className="flex-1 flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <Button variant="ghost" size="sm" onClick={() => navigate('/accounting/bank-statements')}>
          ← Back to list
        </Button>
      </div>

      {summary && (
        <Card className="p-4 flex flex-col gap-4">
          <div className="flex flex-wrap gap-6 text-sm">
            <div>
              <div className="font-semibold">Bank</div>
              <div>{summary.bank_name} ****{summary.account_last4}</div>
            </div>
            <div>
              <div className="font-semibold">Period</div>
              <div>
                {summary.statement_period_start} – {summary.statement_period_end}
              </div>
            </div>
            <div>
              <div className="font-semibold">Status</div>
              <div className={
                summary.status === 'processing' ? 'text-amber-600 font-bold' :
                  summary.status === 'error_parsing_failed' ? 'text-red-600 font-bold' :
                    'text-gray-900'
              }>
                {summary.status?.toUpperCase()}
              </div>
            </div>
            <div>
              <div className="font-semibold">Rows</div>
              <div>{summary.rows_count}</div>
            </div>
            <div>
              <div className="font-semibold">Total credit</div>
              <div>{summary.total_credit}</div>
            </div>
            <div>
              <div className="font-semibold">Total debit</div>
              <div>{summary.total_debit}</div>
            </div>
          </div>

          <div className="flex gap-2">
            {summary.raw_response && (
              <Button variant="outline" size="sm" onClick={() => {
                const newWindow = window.open('', '_blank');
                if (newWindow) {
                  newWindow.document.write('<pre>' + JSON.stringify(summary.raw_response, null, 2) + '</pre>');
                  newWindow.document.title = `Raw Response - Statement ${id}`;
                } else {
                  alert('Pop-up blocked. ' + JSON.stringify(summary.raw_response));
                }
              }}>
                View Raw AI Response
              </Button>
            )}
          </div>
        </Card>
      )}

      {summary?.logs && summary.logs.length > 0 && (
        <Card className="p-4 bg-slate-50">
          <h3 className="text-sm font-semibold mb-2">Process Logs</h3>
          <div className="max-h-60 overflow-auto text-xs font-mono flex flex-col gap-1">
            {summary.logs.map((log: ProcessLog, i: number) => (
              <div key={i} className={log.level === 'ERROR' ? 'text-red-600' : 'text-slate-600'}>
                [{new Date(log.timestamp).toLocaleTimeString()}] {log.level}: {log.message}
              </div>
            ))}
          </div>
        </Card>
      )}

      <div className="flex flex-col gap-3 flex-1 min-h-0">
        <div className="flex flex-wrap gap-3 items-end justify-between">
          <div className="flex gap-3 items-end">
            <div>
              <Label className="block text-xs mb-1">Search</Label>
              <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search description..." />
            </div>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" disabled={selectedIds.size === 0} onClick={markIgnored}>
              Mark as ignored
            </Button>
            <Button variant="outline" size="sm" disabled={selectedIds.size === 0} onClick={commitSelected}>
              Commit selected
            </Button>
            <Button size="sm" onClick={commitAll}>
              Commit all non-ignored
            </Button>
          </div>
        </div>

        <div className="flex-1 min-h-0 overflow-auto border rounded bg-white">
          {loading ? (
            <div className="p-4 text-sm text-gray-600">Loading rows...</div>
          ) : (
            <table className="min-w-full text-xs">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-2 py-1">
                    <Checkbox
                      checked={rows.length > 0 && selectedIds.size === rows.length}
                      onCheckedChange={(val) => {
                        if (val) setSelectedIds(new Set(rows.map((r) => r.id)));
                        else setSelectedIds(new Set());
                      }}
                    />
                  </th>
                  <th className="px-2 py-1 text-left">Date</th>
                  <th className="px-2 py-1 text-left">Description (raw)</th>
                  <th className="px-2 py-1 text-left">Description (clean)</th>
                  <th className="px-2 py-1 text-right">Amount</th>
                  <th className="px-2 py-1 text-right">Balance</th>
                  <th className="px-2 py-1 text-left">Parsed</th>
                  <th className="px-2 py-1 text-left">Match</th>
                  <th className="px-2 py-1 text-left">Category</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id} className="border-t">
                    <td className="px-2 py-1">
                      <Checkbox
                        checked={selectedIds.has(row.id)}
                        onCheckedChange={() => toggleSelected(row.id)}
                      />
                    </td>
                    <td className="px-2 py-1 whitespace-nowrap">{row.operation_date}</td>
                    <td className="px-2 py-1 max-w-xs truncate" title={row.description_raw}>
                      {row.description_raw}
                    </td>
                    <td className="px-2 py-1">
                      <Input
                        className="h-7 text-xs"
                        value={row.description_clean ?? ''}
                        onChange={(e) => {
                          const value = e.target.value;
                          setRows((prev) => prev.map((r) => (r.id === row.id ? { ...r, description_clean: value } : r)));
                        }}
                        onBlur={async (e) => {
                          await updateRow(row.id, { description_clean: e.target.value });
                        }}
                      />
                    </td>
                    <td className="px-2 py-1 text-right">{row.amount}</td>
                    <td className="px-2 py-1 text-right">{row.balance_after}</td>
                    <td className="px-2 py-1">{row.parsed_status}</td>
                    <td className="px-2 py-1">{row.match_status}</td>
                    <td className="px-2 py-1">
                      <select
                        className="border rounded px-1 py-0.5 text-xs"
                        value={row.expense_category_id ?? ''}
                        onChange={async (e) => {
                          const val = e.target.value ? Number(e.target.value) : null;
                          await updateRow(row.id, { expense_category_id: val });
                        }}
                      >
                        <option value="">—</option>
                        {categories.map((c) => (
                          <option key={c.id} value={c.id}>
                            {c.code} — {c.name}
                          </option>
                        ))}
                      </select>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}

function CashExpensesTab() {
  const [dateValue, setDateValue] = useState('');
  const [amount, setAmount] = useState('');
  const [currency, setCurrency] = useState('USD');
  const [counterparty, setCounterparty] = useState('');
  const [description, setDescription] = useState('');
  const [storageId, setStorageId] = useState('');
  const [categoryId, setCategoryId] = useState('');
  const [categories, setCategories] = useState<AccountingCategory[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    const load = async () => {
      const { data } = await api.get('/accounting/categories', { params: { is_active: true } });
      setCategories(data || []);
    };
    void load();
  }, []);

  const extraParams = useMemo(() => ({ _refresh: String(refreshKey) }), [refreshKey]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!dateValue || !amount || !categoryId) return;
    setSubmitting(true);
    try {
      await api.post('/accounting/cash-expenses', {
        date_value: dateValue,
        amount: Number(amount),
        currency,
        counterparty,
        description,
        expense_category_id: Number(categoryId),
        storage_id: storageId || undefined,
      });
      setRefreshKey((v) => v + 1);
      setAmount('');
      setCounterparty('');
      setDescription('');
      setStorageId('');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="flex-1 flex flex-col gap-4">
      <Card className="p-4">
        <h2 className="text-lg font-semibold mb-2">New Cash Expense</h2>
        <form className="grid grid-cols-1 md:grid-cols-4 gap-3 items-end" onSubmit={handleSubmit}>
          <div>
            <Label className="block text-xs mb-1">Date</Label>
            <Input type="date" value={dateValue} onChange={(e) => setDateValue(e.target.value)} required />
          </div>
          <div>
            <Label className="block text-xs mb-1">Amount</Label>
            <Input type="number" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} required />
          </div>
          <div>
            <Label className="block text-xs mb-1">Currency</Label>
            <Input value={currency} onChange={(e) => setCurrency(e.target.value)} />
          </div>
          <div>
            <Label className="block text-xs mb-1">Category</Label>
            <select
              className="border rounded px-2 py-1 text-sm w-full"
              value={categoryId}
              onChange={(e) => setCategoryId(e.target.value)}
              required
            >
              <option value="">Select category</option>
              {categories.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.code} — {c.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <Label className="block text-xs mb-1">Counterparty</Label>
            <Input value={counterparty} onChange={(e) => setCounterparty(e.target.value)} />
          </div>
          <div className="md:col-span-2">
            <Label className="block text-xs mb-1">Description</Label>
            <Input value={description} onChange={(e) => setDescription(e.target.value)} />
          </div>
          <div>
            <Label className="block text-xs mb-1">Storage ID</Label>
            <Input value={storageId} onChange={(e) => setStorageId(e.target.value)} />
          </div>
          <div className="md:col-span-4 flex justify-end mt-2">
            <Button type="submit" disabled={submitting || !dateValue || !amount || !categoryId}>
              {submitting ? 'Saving...' : 'Add Expense'}
            </Button>
          </div>
        </form>
      </Card>

      <div className="flex-1 min-h-0">
        <DataGridPage
          gridKey="accounting_cash_expenses"
          title="Cash Expenses"
          extraParams={extraParams}
        />
      </div>
    </div>
  );
}

function TransactionsTab() {
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [sourceType, setSourceType] = useState('');
  const [storageId, setStorageId] = useState('');
  const [categoryId, setCategoryId] = useState('');
  const [direction, setDirection] = useState('');
  const [minAmount, setMinAmount] = useState('');
  const [maxAmount, setMaxAmount] = useState('');
  const [accountName, setAccountName] = useState('');
  const [isPersonal, setIsPersonal] = useState<boolean | null>(null);
  const [isInternal, setIsInternal] = useState<boolean | null>(null);
  const [categories, setCategories] = useState<AccountingCategory[]>([]);
  const [selectedRow, setSelectedRow] = useState<any | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [totals, setTotals] = useState<{ total_in: number; total_out: number; net: number } | null>(null);

  useEffect(() => {
    const load = async () => {
      const { data } = await api.get('/accounting/categories', { params: { is_active: true } });
      setCategories(data || []);
    };
    void load();
  }, []);

  const extraParams = useMemo(() => {
    const params: Record<string, any> = { _refresh: String(refreshKey) };
    if (dateFrom) params.date_from = dateFrom;
    if (dateTo) params.date_to = dateTo;
    if (sourceType) params.source_type = sourceType;
    if (storageId) params.storage_id = storageId;
    if (categoryId) params.category_id = Number(categoryId);
    if (direction) params.direction = direction;
    if (minAmount) params.min_amount = Number(minAmount);
    if (maxAmount) params.max_amount = Number(maxAmount);
    if (accountName) params.account_name = accountName;
    if (isPersonal !== null) params.is_personal = isPersonal;
    if (isInternal !== null) params.is_internal_transfer = isInternal;
    return params;
  }, [dateFrom, dateTo, sourceType, storageId, categoryId, direction, minAmount, maxAmount, accountName, isPersonal, isInternal, refreshKey]);

  // Fetch aggregated totals for the current filter so the tab behaves like a Ledger view.
  useEffect(() => {
    const fetchTotals = async () => {
      try {
        const { data } = await api.get('/accounting/transactions', { params: { ...extraParams, limit: 1, offset: 0 } });
        if (typeof data.total_in === 'number' && typeof data.total_out === 'number' && typeof data.net === 'number') {
          setTotals({ total_in: data.total_in, total_out: data.total_out, net: data.net });
        } else {
          setTotals(null);
        }
      } catch {
        setTotals(null);
      }
    };
    void fetchTotals();
  }, [extraParams]);

  const handleSaveSelected = async () => {
    if (!selectedRow) return;
    const payload: any = {};
    if (selectedRow.expense_category_id !== undefined) payload.expense_category_id = selectedRow.expense_category_id;
    if (selectedRow.storage_id !== undefined) payload.storage_id = selectedRow.storage_id;
    if (selectedRow.is_personal !== undefined) payload.is_personal = selectedRow.is_personal;
    if (selectedRow.is_internal_transfer !== undefined) payload.is_internal_transfer = selectedRow.is_internal_transfer;
    await api.put(`/accounting/transactions/${selectedRow.id}`, payload);
    setRefreshKey((v) => v + 1);
  };

  return (
    <div className="flex-1 flex flex-col gap-4">
      <Card className="p-4 flex flex-col gap-3">
        {totals && (
          <div className="grid grid-cols-3 gap-4 text-xs mb-2">
            <div>
              <div className="text-gray-500">Total In</div>
              <div className="font-semibold text-emerald-700">{totals.total_in.toFixed(2)}</div>
            </div>
            <div>
              <div className="text-gray-500">Total Out</div>
              <div className="font-semibold text-red-700">{totals.total_out.toFixed(2)}</div>
            </div>
            <div>
              <div className="text-gray-500">Net</div>
              <div className={totals.net >= 0 ? 'font-semibold text-emerald-700' : 'font-semibold text-red-700'}>
                {totals.net.toFixed(2)}
              </div>
            </div>
          </div>
        )}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3 items-end">
          <div>
            <Label className="block text-xs mb-1">From</Label>
            <Input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
          </div>
          <div>
            <Label className="block text-xs mb-1">To</Label>
            <Input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
          </div>
          <div>
            <Label className="block text-xs mb-1">Source type</Label>
            <Input value={sourceType} onChange={(e) => setSourceType(e.target.value)} placeholder="bank_statement/cash_manual" />
          </div>
          <div>
            <Label className="block text-xs mb-1">Storage ID</Label>
            <Input value={storageId} onChange={(e) => setStorageId(e.target.value)} />
          </div>
          <div>
            <Label className="block text-xs mb-1">Direction</Label>
            <select
              className="border rounded px-2 py-1 text-sm w-full"
              value={direction}
              onChange={(e) => setDirection(e.target.value)}
            >
              <option value="">All</option>
              <option value="in">In</option>
              <option value="out">Out</option>
            </select>
          </div>
          <div>
            <Label className="block text-xs mb-1">Amount range</Label>
            <div className="flex gap-1">
              <Input
                className="w-1/2"
                type="number"
                step="0.01"
                placeholder="Min"
                value={minAmount}
                onChange={(e) => setMinAmount(e.target.value)}
              />
              <Input
                className="w-1/2"
                type="number"
                step="0.01"
                placeholder="Max"
                value={maxAmount}
                onChange={(e) => setMaxAmount(e.target.value)}
              />
            </div>
          </div>
          <div>
            <Label className="block text-xs mb-1">Account</Label>
            <Input value={accountName} onChange={(e) => setAccountName(e.target.value)} placeholder="Account name contains..." />
          </div>
          <div>
            <Label className="block text-xs mb-1">Category</Label>
            <select
              className="border rounded px-2 py-1 text-sm w-full"
              value={categoryId}
              onChange={(e) => setCategoryId(e.target.value)}
            >
              <option value="">All</option>
              {categories.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.code} — {c.name}
                </option>
              ))}
            </select>
          </div>
          <div className="flex items-center gap-2 mt-4">
            <Checkbox
              checked={isPersonal === true}
              onCheckedChange={(val) => setIsPersonal(val ? true : null)}
            />
            <span className="text-xs">Personal only</span>
          </div>
          <div className="flex items-center gap-2 mt-4">
            <Checkbox
              checked={isInternal === true}
              onCheckedChange={(val) => setIsInternal(val ? true : null)}
            />
            <span className="text-xs">Internal transfers only</span>
          </div>
        </div>

        {selectedRow && (
          <div className="mt-4 border-t pt-3 grid grid-cols-1 md:grid-cols-4 gap-3 items-end">
            <div className="md:col-span-4 text-xs font-semibold text-gray-600">Selected transaction #{selectedRow.id}</div>
            <div>
              <Label className="block text-xs mb-1">Category</Label>
              <select
                className="border rounded px-2 py-1 text-sm w-full"
                value={selectedRow.expense_category_id ?? ''}
                onChange={(e) =>
                  setSelectedRow((prev: any) =>
                    prev ? { ...prev, expense_category_id: e.target.value ? Number(e.target.value) : null } : prev,
                  )
                }
              >
                <option value="">—</option>
                {categories.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.code} — {c.name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <Label className="block text-xs mb-1">Storage ID</Label>
              <Input
                value={selectedRow.storage_id ?? ''}
                onChange={(e) =>
                  setSelectedRow((prev: any) => (prev ? { ...prev, storage_id: e.target.value } : prev))
                }
              />
            </div>
            <div className="flex items-center gap-2 mt-4">
              <Checkbox
                checked={selectedRow.is_personal === true}
                onCheckedChange={(val) =>
                  setSelectedRow((prev: any) => (prev ? { ...prev, is_personal: !!val } : prev))
                }
              />
              <span className="text-xs">Personal</span>
            </div>
            <div className="flex items-center gap-2 mt-4">
              <Checkbox
                checked={selectedRow.is_internal_transfer === true}
                onCheckedChange={(val) =>
                  setSelectedRow((prev: any) => (prev ? { ...prev, is_internal_transfer: !!val } : prev))
                }
              />
              <span className="text-xs">Internal transfer</span>
            </div>
            <div className="md:col-span-4 flex justify-end mt-2">
              <Button size="sm" onClick={handleSaveSelected}>
                Save changes
              </Button>
            </div>
          </div>
        )}
      </Card>

      <div className="flex-1 min-h-0">
        <DataGridPage
          gridKey="ledger_transactions"
          title="Ledger Transactions"
          extraParams={extraParams}
          onRowClick={(row) => setSelectedRow(row)}
        />
      </div>
    </div>
  );
}

function RulesTab() {
  const [rules, setRules] = useState<AccountingRule[]>([]);
  const [categories, setCategories] = useState<AccountingCategory[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshKey, setRefreshKey] = useState(0);

  // New rule form
  const [patternType, setPatternType] = useState('contains');
  const [patternValue, setPatternValue] = useState('');
  const [categoryId, setCategoryId] = useState('');
  const [priority, setPriority] = useState('10');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const [rulesResp, catsResp] = await Promise.all([
          api.get('/accounting/rules', { params: { is_active: true } }),
          api.get('/accounting/categories', { params: { is_active: true } }),
        ]);
        setRules(rulesResp.data || []);
        setCategories(catsResp.data || []);
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, [refreshKey]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!patternValue || !categoryId) return;
    setSubmitting(true);
    try {
      await api.post('/accounting/rules', {
        pattern_type: patternType,
        pattern_value: patternValue,
        expense_category_id: Number(categoryId),
        priority: Number(priority),
        is_active: true,
      });
      setRefreshKey((v) => v + 1);
      setPatternValue('');
      setCategoryId('');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm('Delete this rule?')) return;
    await api.delete(`/accounting/rules/${id}`);
    setRefreshKey((v) => v + 1);
  };

  return (
    <div className="flex-1 flex flex-col gap-4">
      <Card className="p-4">
        <h2 className="text-lg font-semibold mb-2">New Auto-Categorization Rule</h2>
        <form className="grid grid-cols-1 md:grid-cols-5 gap-3 items-end" onSubmit={handleCreate}>
          <div>
            <Label className="block text-xs mb-1">Pattern Type</Label>
            <select
              className="border rounded px-2 py-1 text-sm w-full"
              value={patternType}
              onChange={(e) => setPatternType(e.target.value)}
            >
              <option value="contains">Contains text</option>
              <option value="regex">Regex</option>
              <option value="counterparty">Counterparty</option>
            </select>
          </div>
          <div className="md:col-span-2">
            <Label className="block text-xs mb-1">Pattern Value</Label>
            <Input
              value={patternValue}
              onChange={(e) => setPatternValue(e.target.value)}
              placeholder="e.g. 'UBER' or 'AMZN MKTPLACE'"
              required
            />
          </div>
          <div>
            <Label className="block text-xs mb-1">Category</Label>
            <select
              className="border rounded px-2 py-1 text-sm w-full"
              value={categoryId}
              onChange={(e) => setCategoryId(e.target.value)}
              required
            >
              <option value="">Select category</option>
              {categories.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.code} — {c.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <Label className="block text-xs mb-1">Priority (lower=first)</Label>
            <Input
              type="number"
              value={priority}
              onChange={(e) => setPriority(e.target.value)}
              required
            />
          </div>
          <div className="md:col-span-5 flex justify-end mt-2">
            <Button type="submit" disabled={submitting || !patternValue || !categoryId}>
              {submitting ? 'Creating...' : 'Create Rule'}
            </Button>
          </div>
        </form>
      </Card>

      <div className="flex-1 min-h-0 overflow-auto border rounded bg-white">
        <table className="min-w-full text-sm">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-3 py-2 text-left">Priority</th>
              <th className="px-3 py-2 text-left">Type</th>
              <th className="px-3 py-2 text-left">Pattern</th>
              <th className="px-3 py-2 text-left">Category</th>
              <th className="px-3 py-2 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {rules.map((r) => {
              const cat = categories.find((c) => c.id === r.expense_category_id);
              return (
                <tr key={r.id} className="border-t hover:bg-gray-50">
                  <td className="px-3 py-2">{r.priority}</td>
                  <td className="px-3 py-2">{r.pattern_type}</td>
                  <td className="px-3 py-2 font-mono text-xs">{r.pattern_value}</td>
                  <td className="px-3 py-2">
                    {cat ? `${cat.code} — ${cat.name}` : r.expense_category_id}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-red-600 hover:text-red-800"
                      onClick={() => handleDelete(r.id)}
                    >
                      Delete
                    </Button>
                  </td>
                </tr>
              );
            })}
            {!loading && rules.length === 0 && (
              <tr>
                <td colSpan={5} className="px-3 py-4 text-center text-gray-500">
                  No rules defined.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function AccountingPage() {
  const { user } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();

  if (!user || user.role !== 'admin') {
    return (
      <div className="min-h-screen bg-gray-50">
        <FixedHeader />
        <div className="pt-16 p-4">
          <h1 className="text-2xl font-bold mb-2">Нет доступа</h1>
          <p className="text-gray-600 text-sm">Этот раздел доступен только администраторам.</p>
        </div>
      </div>
    );
  }

  const basePath = '/accounting';
  const currentPath = location.pathname.startsWith(basePath)
    ? location.pathname.substring(basePath.length) || '/bank-statements'
    : '/bank-statements';

  const activeTab = currentPath.startsWith('/cash')
    ? 'cash'
    : currentPath.startsWith('/transactions')
      ? 'transactions'
      : currentPath.startsWith('/rules')
        ? 'rules'
        : 'bank-statements';

  const handleTabChange = (val: string) => {
    if (val === 'cash') navigate('/accounting/cash');
    else if (val === 'transactions') navigate('/accounting/transactions');
    else if (val === 'rules') navigate('/accounting/rules');
    else navigate('/accounting/bank-statements');
  };

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      <FixedHeader />
      <div className="pt-16 px-4 pb-4 flex-1 flex flex-col">
        <h1 className="text-3xl font-bold mb-4">Accounting</h1>
        <Tabs
          defaultValue="bank-statements"
          value={activeTab}
          onValueChange={handleTabChange}
          className="flex-1 flex flex-col"
        >
          <TabsList>
            <TabsTrigger value="bank-statements">Statements</TabsTrigger>
            <TabsTrigger value="cash">Cash Expenses</TabsTrigger>
            <TabsTrigger value="transactions">Ledger</TabsTrigger>
            <TabsTrigger value="rules">Rules</TabsTrigger>
          </TabsList>

          <TabsContent value="bank-statements" className="flex-1 flex flex-col">
            <Routes>
              <Route path="bank-statements" element={<BankStatementsList />} />
              <Route path="bank-statements/:id" element={<BankStatementDetail />} />
              <Route path="*" element={<Navigate to="bank-statements" replace />} />
            </Routes>
          </TabsContent>

          <TabsContent value="cash" className="flex-1 flex flex-col">
            <Routes>
              <Route path="cash" element={<CashExpensesTab />} />
              <Route path="*" element={<Navigate to="cash" replace />} />
            </Routes>
          </TabsContent>

          <TabsContent value="transactions" className="flex-1 flex flex-col">
            <Routes>
              <Route path="transactions" element={<TransactionsTab />} />
              <Route path="*" element={<Navigate to="transactions" replace />} />
            </Routes>
          </TabsContent>

          <TabsContent value="rules" className="flex-1 flex flex-col">
            <Routes>
              <Route path="rules" element={<RulesTab />} />
              <Route path="*" element={<Navigate to="rules" replace />} />
            </Routes>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
