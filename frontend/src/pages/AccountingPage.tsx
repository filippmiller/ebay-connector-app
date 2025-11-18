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

function BankStatementsList() {
  const navigate = useNavigate();
  const [bankName, setBankName] = useState('');
  const [status, setStatus] = useState('');
  const [periodFrom, setPeriodFrom] = useState('');
  const [periodTo, setPeriodTo] = useState('');

  const [bankNameUpload, setBankNameUpload] = useState('');
  const [accountLast4, setAccountLast4] = useState('');
  const [currency, setCurrency] = useState('USD');
  const [periodStartUpload, setPeriodStartUpload] = useState('');
  const [periodEndUpload, setPeriodEndUpload] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
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

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file || !bankNameUpload) return;
    setUploading(true);
    try {
      const form = new FormData();
      form.append('bank_name', bankNameUpload);
      if (accountLast4) form.append('account_last4', accountLast4);
      if (currency) form.append('currency', currency);
      if (periodStartUpload) form.append('statement_period_start', periodStartUpload);
      if (periodEndUpload) form.append('statement_period_end', periodEndUpload);
      form.append('file', file);
      await api.post('/api/accounting/bank-statements', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setRefreshKey((v) => v + 1);
      setFile(null);
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="flex-1 flex flex-col gap-4">
      <Card className="p-4">
        <h2 className="text-lg font-semibold mb-2">Upload Statement</h2>
        <form className="grid grid-cols-1 md:grid-cols-3 gap-3 items-end" onSubmit={handleUpload}>
          <div>
            <Label className="block text-xs mb-1">Bank name</Label>
            <Input value={bankNameUpload} onChange={(e) => setBankNameUpload(e.target.value)} required />
          </div>
          <div>
            <Label className="block text-xs mb-1">Account last4</Label>
            <Input value={accountLast4} onChange={(e) => setAccountLast4(e.target.value)} />
          </div>
          <div>
            <Label className="block text-xs mb-1">Currency</Label>
            <Input value={currency} onChange={(e) => setCurrency(e.target.value)} />
          </div>
          <div>
            <Label className="block text-xs mb-1">Period start</Label>
            <Input type="date" value={periodStartUpload} onChange={(e) => setPeriodStartUpload(e.target.value)} />
          </div>
          <div>
            <Label className="block text-xs mb-1">Period end</Label>
            <Input type="date" value={periodEndUpload} onChange={(e) => setPeriodEndUpload(e.target.value)} />
          </div>
          <div>
            <Label className="block text-xs mb-1">File (CSV/PDF)</Label>
            <Input type="file" accept=".csv,.txt,.pdf" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          </div>
          <div className="md:col-span-3 flex justify-end mt-2">
            <Button type="submit" disabled={uploading || !file || !bankNameUpload}>
              {uploading ? 'Uploading...' : 'Upload Statement'}
            </Button>
          </div>
        </form>
      </Card>

      <div className="flex flex-col gap-3 flex-1 min-h-0">
        <div className="flex flex-wrap gap-3 items-end">
          <div>
            <Label className="block text-xs mb-1">Bank</Label>
            <Input value={bankName} onChange={(e) => setBankName(e.target.value)} />
          </div>
          <div>
            <Label className="block text-xs mb-1">Status</Label>
            <Input value={status} onChange={(e) => setStatus(e.target.value)} placeholder="uploaded/parsed/review_in_progress/approved" />
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
    </div>
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
        api.get(`/api/accounting/bank-statements/${id}`),
        api.get(`/api/accounting/bank-statements/${id}/rows`, { params: { limit: 1000, search: search || undefined } }),
        api.get('/api/accounting/categories', { params: { is_active: true } }),
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
      await api.put(`/api/accounting/bank-rows/${rowId}`, { parsed_status: 'ignored' });
    }
    await loadData();
  };

  const commitSelected = async () => {
    if (!id || selectedIds.size === 0) return;
    const params = new URLSearchParams();
    Array.from(selectedIds).forEach((rid) => params.append('row_ids', String(rid)));
    await api.post(`/api/accounting/bank-statements/${id}/commit-rows?${params.toString()}`);
    await loadData();
  };

  const commitAll = async () => {
    if (!id) return;
    await api.post(`/api/accounting/bank-statements/${id}/commit-rows`, {
      commit_all_non_ignored: true,
    });
    await loadData();
  };

  const updateRow = async (rowId: number, patch: any) => {
    await api.put(`/api/accounting/bank-rows/${rowId}`, patch);
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
        <Card className="p-4 flex flex-wrap gap-6 text-sm">
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
            <div>{summary.status}</div>
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
      const { data } = await api.get('/api/accounting/categories', { params: { is_active: true } });
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
      await api.post('/api/accounting/cash-expenses', {
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
  const [isPersonal, setIsPersonal] = useState<boolean | null>(null);
  const [isInternal, setIsInternal] = useState<boolean | null>(null);
  const [categories, setCategories] = useState<AccountingCategory[]>([]);
  const [selectedRow, setSelectedRow] = useState<any | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    const load = async () => {
      const { data } = await api.get('/api/accounting/categories', { params: { is_active: true } });
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
    if (isPersonal !== null) params.is_personal = isPersonal;
    if (isInternal !== null) params.is_internal_transfer = isInternal;
    return params;
  }, [dateFrom, dateTo, sourceType, storageId, categoryId, isPersonal, isInternal, refreshKey]);

  const handleSaveSelected = async () => {
    if (!selectedRow) return;
    const payload: any = {};
    if (selectedRow.expense_category_id !== undefined) payload.expense_category_id = selectedRow.expense_category_id;
    if (selectedRow.storage_id !== undefined) payload.storage_id = selectedRow.storage_id;
    if (selectedRow.is_personal !== undefined) payload.is_personal = selectedRow.is_personal;
    if (selectedRow.is_internal_transfer !== undefined) payload.is_internal_transfer = selectedRow.is_internal_transfer;
    await api.put(`/api/accounting/transactions/${selectedRow.id}`, payload);
    setRefreshKey((v) => v + 1);
  };

  return (
    <div className="flex-1 flex flex-col gap-4">
      <Card className="p-4 flex flex-col gap-3">
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
          gridKey="accounting_transactions"
          title="Accounting Transactions"
          extraParams={extraParams}
          onRowClick={(row) => setSelectedRow(row)}
        />
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
    : 'bank-statements';

  const handleTabChange = (val: string) => {
    if (val === 'cash') navigate('/accounting/cash');
    else if (val === 'transactions') navigate('/accounting/transactions');
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
            <TabsTrigger value="bank-statements">Bank Statements</TabsTrigger>
            <TabsTrigger value="cash">Cash Expenses</TabsTrigger>
            <TabsTrigger value="transactions">Transactions</TabsTrigger>
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
        </Tabs>
      </div>
    </div>
  );
}
