import React from 'react';
import { Routes, Route, Navigate, useLocation, useNavigate } from 'react-router-dom';
import FixedHeader from '@/components/FixedHeader';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useAuth } from '@/auth/AuthContext';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import api from '@/lib/apiClient';
import { DataGridPage } from '@/components/DataGridPage';
import { parseManualRawText, saveManualStatementImpl } from './Accounting2ManualHelpers';

const TD_SUMMARY_FIELD_CONFIG: { key: string; label: string }[] = [
  { key: 'beginning_balance', label: 'Beginning balance (Начальный баланс)' },
  { key: 'ending_balance', label: 'Ending balance (Конечный баланс)' },
  { key: 'electronic_deposits_total', label: 'Electronic deposits total (Электронные зачисления всего)' },
  { key: 'other_credits_total', label: 'Other credits total (Прочие кредиты всего)' },
  { key: 'checks_paid_total', label: 'Checks paid total (Чеки оплачены всего)' },
  { key: 'electronic_payments_total', label: 'Electronic payments total (Электронные списания всего)' },
  { key: 'other_withdrawals_total', label: 'Other withdrawals total (Прочие списания всего)' },
  { key: 'service_charges_fees_total', label: 'Service charges fees total (Комиссии банка всего)' },
  { key: 'interest_earned_total', label: 'Interest earned total (Проценты за период)' },
  { key: 'grace_period_balance', label: 'Grace period balance (Грейс-баланс)' },
  { key: 'grace_period_start', label: 'Grace period start (Начало грейс‑периода)' },
  { key: 'grace_period_end', label: 'Grace period end (Конец грейс‑периода)' },
];

interface Accounting2StatementSummary {
  id: number;
  bank_name: string | null;
  account_last4: string | null;
  currency: string | null;
  statement_period_start: string | null;
  statement_period_end: string | null;
  opening_balance?: number | string | null;
  closing_balance?: number | string | null;
  account_summary?: Record<string, any> | null;
  status: string;
  rows_count: number | null;
  created_at?: string;
}

interface Accounting2PreviewRow {
  id: number;
  operation_date: string | null;
  description_raw: string | null;
  description_clean: string | null;
  amount: number;
  balance_after: number | null;
}

interface Accounting2StatementUploadResult {
  id: number;
  bank_name?: string;
  account_last4?: string;
  currency?: string;
  period_start?: string;
  period_end?: string;
  rows_count?: number;
  message?: string;
}

export interface ManualParsedRow {
  id: number;
  date: string; // YYYY-MM-DD
  description: string;
  amount: string; // as typed, will be converted
  direction: 'debit' | 'credit';
  duplicate?: boolean;
}

function StatementsTab2() {
  const navigate = useNavigate();
  const [bankName, setBankName] = React.useState('');
  const [status, setStatus] = React.useState('');
  const [periodFrom, setPeriodFrom] = React.useState('');
  const [periodTo, setPeriodTo] = React.useState('');
  const [selectedIds, setSelectedIds] = React.useState<number[]>([]);
  const [deleting, setDeleting] = React.useState(false);

  const [file, setFile] = React.useState<File | null>(null);
  const [uploading, setUploading] = React.useState(false);
  const [uploadResult, setUploadResult] = React.useState<Accounting2StatementUploadResult | null>(null);
  const [uploadError, setUploadError] = React.useState<string | null>(null);

  // Manual pasted statement state
  const [manualOpen, setManualOpen] = React.useState(false);
  const [manualBankName, setManualBankName] = React.useState('TD Bank');
  const [manualBankCode, setManualBankCode] = React.useState('TD');
  const [manualAccountLast4, setManualAccountLast4] = React.useState('');
  const [manualCurrency, setManualCurrency] = React.useState('USD');
  const [manualPeriodStart, setManualPeriodStart] = React.useState('');
  const [manualPeriodEnd, setManualPeriodEnd] = React.useState('');
  const [manualOpening, setManualOpening] = React.useState('');
  const [manualClosing, setManualClosing] = React.useState('');
  const [manualRawText, setManualRawText] = React.useState('');
  const [manualRows, setManualRows] = React.useState<ManualParsedRow[]>([]);
  const [manualParsingError, setManualParsingError] = React.useState<string | null>(null);
  const [manualSaving, setManualSaving] = React.useState(false);

  const saveManualStatement = async (commit: boolean) => {
    try {
      setManualSaving(true);
      const id = await saveManualStatementImpl(manualRows, {
        bankName: manualBankName,
        bankCode: manualBankCode,
        accountLast4: manualAccountLast4,
        currency: manualCurrency,
        periodStart: manualPeriodStart,
        periodEnd: manualPeriodEnd,
        opening: manualOpening,
        closing: manualClosing,
        commit,
      });
      setManualOpen(false);
      setManualRows([]);
      setManualRawText('');
      await loadStatements();
      if (id && !commit) {
        // optionally open preview in future
      }
    } catch (err: any) {
      alert(err?.response?.data?.detail || err?.message || 'Failed to save manual statement');
    } finally {
      setManualSaving(false);
    }
  };

  const [statements, setStatements] = React.useState<Accounting2StatementSummary[]>([]);
  const [loadingList, setLoadingList] = React.useState(false);
  const [listError, setListError] = React.useState<string | null>(null);
  const [page, setPage] = React.useState(1);
  const [pageSize] = React.useState(50);
  const [total, setTotal] = React.useState(0);

  // Preview modal state for freshly uploaded / selected statement
  const [previewOpen, setPreviewOpen] = React.useState(false);
  const [previewLoading, setPreviewLoading] = React.useState(false);
  const [previewError, setPreviewError] = React.useState<string | null>(null);
  const [previewStatement, setPreviewStatement] = React.useState<Accounting2StatementSummary | null>(null);
  const [previewRows, setPreviewRows] = React.useState<Accounting2PreviewRow[]>([]);
  const [previewCommitting, setPreviewCommitting] = React.useState(false);

  const loadStatements = React.useCallback(async () => {
    setLoadingList(true);
    setListError(null);
    try {
      const params: Record<string, any> = {
        limit: pageSize,
        offset: (page - 1) * pageSize,
      };
      if (bankName) params.bank_name = bankName;
      if (status) params.status = status;
      if (periodFrom) params.period_from = periodFrom;
      if (periodTo) params.period_to = periodTo;

      const resp = await api.get<{ rows: Accounting2StatementSummary[]; total: number }>('/accounting/bank-statements', {
        params,
      });
      const payload: any = resp.data as any;
      const rows = Array.isArray(payload.rows) ? payload.rows : Array.isArray(payload.items) ? payload.items : [];
      setStatements(rows);
      setTotal(typeof payload.total === 'number' ? payload.total : rows.length);
      setSelectedIds([]);
    } catch (err: any) {
      setListError(err?.message || 'Failed to load statements');
    } finally {
      setLoadingList(false);
    }
  }, [bankName, status, periodFrom, periodTo, page, pageSize]);

  React.useEffect(() => {
    void loadStatements();
  }, [loadStatements]);

  const openPreviewForStatement = async (id: number) => {
    setPreviewOpen(true);
    setPreviewLoading(true);
    setPreviewError(null);
    setPreviewRows([]);
    try {
      const [summaryResp, rowsResp] = await Promise.all([
        api.get<Accounting2StatementSummary>(`/accounting2/bank-statements/${id}`),
        api.get<{ rows: Accounting2PreviewRow[] }>(`/accounting2/bank-statements/${id}/rows`, {
          params: { limit: 1000 },
        }),
      ]);
      setPreviewStatement(summaryResp.data);
      const payload: any = rowsResp.data as any;
      const rows = Array.isArray(payload.rows) ? payload.rows : Array.isArray(payload.items) ? payload.items : [];
      setPreviewRows(rows);
    } catch (err: any) {
      setPreviewError(err?.message || 'Failed to load statement preview');
    } finally {
      setPreviewLoading(false);
    }
  };

  const handlePreviewAcceptAll = async () => {
    if (!previewStatement) return;
    setPreviewCommitting(true);
    try {
      // 1) Accounting 2: перенести строки из transaction_spending в accounting_bank_row
      await api.post(`/accounting2/bank-statements/${previewStatement.id}/approve`);

      // 2) Сразу же закоммитить все неигнорированные строки в Ledger (accounting_transaction)
      await api.post(`/accounting/bank-statements/${previewStatement.id}/commit-rows`, {
        commit_all_non_ignored: true,
      });

      setPreviewOpen(false);
      await loadStatements();
    } catch (err: any) {
      alert(err?.response?.data?.detail || err?.message || 'Failed to approve and commit transactions');
    } finally {
      setPreviewCommitting(false);
    }
  };

  const handlePreviewCancel = () => {
    // Просто закрываем окно; никакого удаления или reject.
    setPreviewOpen(false);
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

      // Новая версия: используем Accounting 2 endpoint (PDF → transaction_spending → staged statement)
      const response = await api.post<Accounting2StatementUploadResult>('/accounting2/bank-statements/upload', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });

      setUploadResult(response.data);
      setFile(null);
      // После успешной загрузки обновляем список и открываем предпросмотр
      await loadStatements();
      if (response.data.id) {
        void openPreviewForStatement(response.data.id);
      }
    } catch (err: any) {
      const errorMsg = err?.response?.data?.detail || err?.message || 'Upload failed';
      setUploadError(errorMsg);
    } finally {
      setUploading(false);
    }
  };

  const [deleteStep, setDeleteStep] = React.useState<1 | 2>(1);
  const [deleteText, setDeleteText] = React.useState('');
  const [showDeleteModal, setShowDeleteModal] = React.useState(false);

  const openDeleteFlow = () => {
    if (!selectedIds.length) return;
    setDeleteStep(1);
    setDeleteText('');
    setShowDeleteModal(true);
  };

  const handleDeleteConfirm = async () => {
    if (deleteStep === 1) {
      setDeleteStep(2);
      return;
    }
    if (deleteText !== 'Delete') {
      alert('Чтобы удалить, нужно ввести слово Delete точно так, как показано.');
      return;
    }
    setDeleting(true);
    try {
      for (const id of selectedIds) {
        await api.delete(`/accounting/bank-statements/${id}`);
      }
      setSelectedIds([]);
      setShowDeleteModal(false);
      await loadStatements();
    } catch (e: any) {
      alert(`Delete failed: ${e?.message || e}`);
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="flex-1 flex flex-col gap-4">
      {/* Upload card */}
      <Card className="p-5 border-2 border-dashed border-gray-200">
        <form onSubmit={handleUpload}>
          <div className="flex flex-col gap-4">
            <div>
              <h2 className="text-lg font-semibold">Upload Bank Statement (Accounting 2)</h2>
              <p className="text-sm text-gray-500 mt-1">
                Загрузите PDF/CSV/XLSX банковского стейтмента. После парсинга вы увидите модальное окно с транзакциями.
              </p>
            </div>
            <div className="flex items-center gap-4 max-w-xl">
              <Input
                type="file"
                accept=".csv,.txt,.pdf,.xlsx,.xls"
                onChange={(e) => {
                  setFile(e.target.files?.[0] ?? null);
                  setUploadResult(null);
                  setUploadError(null);
                }}
              />
              <Button type="submit" disabled={uploading || !file} className="min-w-[140px]">
                {uploading ? 'Parsing…' : 'Upload & Parse'}
              </Button>
            </div>
            {uploadResult && (
              <div className="max-w-xl p-4 bg-emerald-50 border border-emerald-200 rounded-lg text-sm">
                <div className="font-semibold text-emerald-800 mb-1">{uploadResult.message || 'Upload successful'}</div>
                <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-emerald-700">
                  {uploadResult.bank_name && <span><strong>Bank:</strong> {uploadResult.bank_name}</span>}
                  {uploadResult.account_last4 && <span><strong>Account:</strong> ****{uploadResult.account_last4}</span>}
                  {uploadResult.currency && <span><strong>Currency:</strong> {uploadResult.currency}</span>}
                  {uploadResult.rows_count !== undefined && (
                    <span><strong>Transactions:</strong> {uploadResult.rows_count}</span>
                  )}
                  {uploadResult.period_start && uploadResult.period_end && (
                    <span className="col-span-2">
                      <strong>Period:</strong> {uploadResult.period_start} – {uploadResult.period_end}
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
              </div>
            )}
            {uploadError && (
              <div className="max-w-xl p-4 bg-red-50 border-red-200 rounded-lg text-sm text-red-700">
                {uploadError}
              </div>
            )}
            <div>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="mt-2"
                onClick={() => setManualOpen(true)}
              >
                New manual statement (paste from PDF)
              </Button>
            </div>
          </div>
        </form>
      </Card>

      {/* Filters + custom grid (no reuse of old DataGridPage) */}
      <div className="flex flex-col gap-3 flex-1 min-h-0">
        <div className="flex flex-wrap gap-3 items-end">
          <div>
            <Label className="block text-xs mb-1">Bank</Label>
            <Input
              value={bankName}
              onChange={(e) => {
                setBankName(e.target.value);
                setPage(1);
              }}
              placeholder="Filter by bank…"
            />
          </div>
          <div>
            <Label className="block text-xs mb-1">Status</Label>
            <select
              className="border rounded px-2 py-1.5 text-sm"
              value={status}
              onChange={(e) => {
                setStatus(e.target.value);
                setPage(1);
              }}
            >
              <option value="">All</option>
              <option value="uploaded">Uploaded</option>
              <option value="processing">Processing</option>
              <option value="parsed">Parsed</option>
              <option value="review_in_progress">In Review</option>
              <option value="error_parsing_failed">Error</option>
            </select>
          </div>
          <div>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => {
                setBankName('');
                setStatus('');
                setPeriodFrom('');
                setPeriodTo('');
                setPage(1);
              }}
            >
              Reset filters
            </Button>
          </div>
          <div>
            <Label className="block text-xs mb-1">From</Label>
            <Input
              type="date"
              value={periodFrom}
              onChange={(e) => {
                setPeriodFrom(e.target.value);
                setPage(1);
              }}
            />
          </div>
          <div>
            <Label className="block text-xs mb-1">To</Label>
            <Input
              type="date"
              value={periodTo}
              onChange={(e) => {
                setPeriodTo(e.target.value);
                setPage(1);
              }}
            />
          </div>
          <div className="flex items-center gap-2 ml-auto">
            <Button
              variant="destructive"
              size="sm"
              disabled={!selectedIds.length || deleting}
              onClick={openDeleteFlow}
            >
              {deleting ? 'Deleting…' : `Delete selected (${selectedIds.length || 0})`}
            </Button>
          </div>
        </div>
        <div className="flex-1 min-h-0 overflow-auto border rounded bg-white">
          {listError && (
            <div className="p-3 text-sm text-red-600 border-b">{listError}</div>
          )}
          <table className="min-w-full text-xs">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-2 py-2 w-8 text-center">
                  <Checkbox
                    checked={statements.length > 0 && selectedIds.length === statements.length}
                    onCheckedChange={(v) => {
                      if (v) setSelectedIds(statements.map((s) => s.id));
                      else setSelectedIds([]);
                    }}
                  />
                </th>
                <th className="px-2 py-2 text-left">Bank / Account</th>
                <th className="px-2 py-2 text-left">Period</th>
                <th className="px-2 py-2 text-left">Currency</th>
                <th className="px-2 py-2 text-right">Opening</th>
                <th className="px-2 py-2 text-right">Closing</th>
                <th className="px-2 py-2 text-right">Rows</th>
                <th className="px-2 py-2 text-left">Status</th>
                <th className="px-2 py-2 text-left">Created</th>
              </tr>
            </thead>
            <tbody>
              {loadingList ? (
                <tr>
                  <td colSpan={7} className="px-3 py-3 text-sm text-gray-600">
                    Loading statements…
                  </td>
                </tr>
              ) : statements.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-3 py-3 text-sm text-gray-600">
                    No statements found.
                  </td>
                </tr>
              ) : (
                statements.map((s) => {
                  const checked = selectedIds.includes(s.id);
                  const period = s.statement_period_start && s.statement_period_end
                    ? `${s.statement_period_start} – ${s.statement_period_end}`
                    : '—';
                  const created = s.created_at
                    ? new Date(s.created_at).toLocaleString()
                    : '';
                  return (
                    <tr
                      key={s.id}
                      className="border-t hover:bg-gray-50 cursor-pointer"
                      onClick={(e) => {
                        // не триггерим переход, если клик по чекбоксу
                        const target = e.target as HTMLElement;
                        if (target.closest('input[type="checkbox"]')) return;
                        void openPreviewForStatement(s.id);
                      }}
                    >
                      <td className="px-2 py-1 text-center">
                        <Checkbox
                          checked={checked}
                          onCheckedChange={(v) => {
                            setSelectedIds((prev) => (
                              v
                                ? [...prev, s.id].filter((id, idx, arr) => arr.indexOf(id) === idx)
                                : prev.filter((id) => id !== s.id)
                            ));
                          }}
                        />
                      </td>
                      <td className="px-2 py-1 whitespace-nowrap">
                        <div className="font-medium text-gray-900">{s.bank_name || '—'}</div>
                        <div className="text-[11px] text-gray-500">{s.account_last4 ? `****${s.account_last4}` : ''}</div>
                      </td>
                      <td className="px-2 py-1 whitespace-nowrap">{period}</td>
                      <td className="px-2 py-1 whitespace-nowrap">{s.currency || '—'}</td>
                      <td className="px-2 py-1 text-right">
                        {s.opening_balance != null ? Number(s.opening_balance).toFixed(2) : '—'}
                      </td>
                      <td className="px-2 py-1 text-right">
                        {s.closing_balance != null ? Number(s.closing_balance).toFixed(2) : '—'}
                      </td>
                      <td className="px-2 py-1 text-right">{s.rows_count ?? '—'}</td>
                      <td className="px-2 py-1 whitespace-nowrap">{s.status}</td>
                      <td className="px-2 py-1 whitespace-nowrap text-gray-500">{created}</td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
          {/* simple pagination */}
          <div className="flex items-center justify-between px-3 py-2 text-xs text-gray-600 border-t bg-gray-50">
            <span>
              {total > 0
                ? `Showing ${(page - 1) * pageSize + 1}–${Math.min(total, page * pageSize)} of ${total}`
                : 'No rows'}
            </span>
            <div className="flex items-center gap-1">
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={page <= 1}
                onClick={() => setPage(1)}
              >
                « First
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
              >
                ‹ Prev
              </Button>
              <span className="px-2">Page {page}</span>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={page * pageSize >= total}
                onClick={() => setPage((p) => p + 1)}
              >
                Next ›
              </Button>
            </div>
          </div>
        </div>
      </div>

      {/* Delete confirmation modal (two-step) */}
      {showDeleteModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 max-w-md w-full mx-4 shadow-xl text-sm">
            {deleteStep === 1 ? (
              <>
                <h3 className="text-lg font-semibold mb-2">Удалить банковские стейтменты?</h3>
                <p className="text-gray-700 mb-2">
                  Вы собираетесь удалить {selectedIds.length} стейтмент(ов). Будут удалены:
                </p>
                <ul className="list-disc list-inside text-gray-700 mb-3">
                  <li>Все транзакции, привязанные к этим стейтментам</li>
                  <li>Все лог-записи обработки</li>
                  <li>Оригинальные файлы стейтментов (PDF/CSV/XLSX)</li>
                </ul>
                <p className="text-red-600 font-semibold mb-4">Это действие нельзя будет отменить.</p>
                <div className="flex justify-end gap-2">
                  <Button variant="outline" onClick={() => setShowDeleteModal(false)}>Cancel</Button>
                  <Button variant="destructive" onClick={handleDeleteConfirm}>Continue</Button>
                </div>
              </>
            ) : (
              <>
                <h3 className="text-lg font-semibold mb-2">Финальное подтверждение</h3>
                <p className="text-gray-700 mb-3">
                  Чтобы подтвердить удаление, введите слово <span className="font-mono font-bold">Delete</span> ниже.
                </p>
                <Input
                  value={deleteText}
                  onChange={(e) => setDeleteText(e.target.value)}
                  placeholder="Type Delete to confirm"
                  autoFocus
                  className="mb-4"
                />
                <div className="flex justify-end gap-2">
                  <Button variant="outline" onClick={() => setShowDeleteModal(false)} disabled={deleting}>Cancel</Button>
                  <Button
                    variant="destructive"
                    onClick={handleDeleteConfirm}
                    disabled={deleting || deleteText !== 'Delete'}
                  >
                    {deleting ? 'Deleting…' : 'Delete permanently'}
                  </Button>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {/* Preview modal for uploaded/selected statement */}
      {previewOpen && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl max-w-5xl w-full max-h-[90vh] mx-4 flex flex-col text-sm">
            <div className="px-5 py-3 border-b flex items-center justify-between">
              <div>
                <div className="text-base font-semibold">Statement preview</div>
                {previewStatement && (
                  <div className="text-xs text-gray-600 mt-1">
                    {previewStatement.bank_name || '—'}{' '}
                    {previewStatement.account_last4 ? `****${previewStatement.account_last4}` : ''}{' '}
                    {previewStatement.statement_period_start && previewStatement.statement_period_end && (
                      <>
                        · {previewStatement.statement_period_start} – {previewStatement.statement_period_end}
                      </>
                    )}
                    {previewRows.length > 0 && ` · ${previewRows.length} transactions`}
                  </div>
                )}
              </div>
              <div className="flex items-center gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={handlePreviewCancel}
                >
                  Close
                </Button>
                <Button
                  type="button"
                  size="sm"
                  onClick={handlePreviewAcceptAll}
                  disabled={previewCommitting || previewRows.length === 0}
                >
                  {previewCommitting ? 'Saving…' : 'Accept all transactions'}
                </Button>
              </div>
            </div>
            <div className="px-5 py-2 border-b flex items-center justify-between text-xs text-gray-600">
              <span>
                В этом окне вы видите все распарсенные транзакции до того, как они попадут в Ledger.
              </span>
              <div className="flex items-center gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={async () => {
                    if (!previewStatement) return;
                    try {
                      const { data } = await api.get<{ url: string }>(`/accounting2/bank-statements/${previewStatement.id}/pdf-url`);
                      if (data.url) {
                        window.open(data.url, '_blank');
                      } else {
                        alert('PDF URL is empty');
                      }
                    } catch (err: any) {
                      alert(err?.response?.data?.detail || err?.message || 'Failed to open PDF');
                    }
                  }}
                >
                  View PDF
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={async () => {
                    if (!previewStatement) return;
                    try {
                      const { data } = await api.get<any>(`/accounting/bank-statements/${previewStatement.id}`);
                      const payload = data?.raw_json ?? data;
                      const jsonStr = JSON.stringify(payload, null, 2);
                      const blob = new Blob([jsonStr], { type: 'application/json' });
                      const url = URL.createObjectURL(blob);
                      window.open(url, '_blank');
                    } catch (err: any) {
                      alert(err?.response?.data?.detail || err?.message || 'Failed to open JSON');
                    }
                  }}
                >
                  View JSON
                </Button>
              </div>
            </div>

            {previewStatement?.account_summary && (
              <div className="px-5 py-2 border-b text-xs text-gray-700 bg-gray-50/60">
                {(() => {
                  const summary = previewStatement.account_summary as Record<string, any>;
                  const fmt = (v: any) =>
                    typeof v === 'number' ? v.toFixed(2) : v ?? '—';

                  const knownItems = TD_SUMMARY_FIELD_CONFIG.filter((f) => summary[f.key] !== undefined);
                  const knownKeys = new Set(knownItems.map((f) => f.key));

                  return (
                    <>
                      {knownItems.length > 0 && (
                        <div className="grid grid-cols-2 gap-x-8 gap-y-1 mb-2">
                          {knownItems.map((f) => (
                            <div key={f.key}>
                              <span className="font-semibold">{f.label}:</span>{' '}
                              {String(fmt(summary[f.key]))}
                            </div>
                          ))}
                        </div>
                      )}
                      {/* Показываем любые дополнительные поля, которые парсер вернул, но мы не знаем заранее */}
                      {Object.entries(summary)
                        .filter(([key]) => !knownKeys.has(key))
                        .length > 0 && (
                        <div className="mt-1 grid grid-cols-2 gap-x-8 gap-y-1 border-t border-gray-200 pt-2">
                          {Object.entries(summary)
                            .filter(([key]) => !knownKeys.has(key))
                            .map(([key, value]) => {
                              const prettyKey = key
                                .replace(/_/g, ' ')
                                .replace(/\b\w/g, (ch) => ch.toUpperCase());
                              return (
                                <div key={key}>
                                  <span className="font-semibold">{prettyKey}:</span>{' '}
                                  {String(fmt(value))}
                                </div>
                              );
                            })}
                        </div>
                      )}
                    </>
                  );
                })()}
              </div>
            )}

            <div className="flex-1 min-h-0 overflow-auto">
              {previewLoading ? (
                <div className="p-4 text-gray-600">Loading transactions…</div>
              ) : previewError ? (
                <div className="p-4 text-red-600">{previewError}</div>
              ) : previewRows.length === 0 ? (
                <div className="p-4 text-gray-600">No transactions parsed for this statement.</div>
              ) : (
                <table className="min-w-full text-xs">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-2 py-2 text-left">Date</th>
                      <th className="px-2 py-2 text-left">Section</th>
                      <th className="px-2 py-2 text-left">Description</th>
                      <th className="px-2 py-2 text-right">Amount</th>
                      <th className="px-2 py-2 text-right">Balance after</th>
                    </tr>
                  </thead>
                  <tbody>
                    {previewRows.map((r) => (
                      <tr key={r.id} className="border-t hover:bg-gray-50">
                        <td className="px-2 py-1 whitespace-nowrap">{r.operation_date || '—'}</td>
                        <td className="px-2 py-1 whitespace-nowrap">
                          <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
                            r.bank_section === 'ELECTRONIC_DEPOSIT' ? 'bg-green-100 text-green-800' :
                            r.bank_section === 'OTHER_CREDIT' ? 'bg-emerald-100 text-emerald-800' :
                            r.bank_section === 'CHECKS_PAID' ? 'bg-red-100 text-red-800' :
                            r.bank_section === 'ELECTRONIC_PAYMENT' ? 'bg-orange-100 text-orange-800' :
                            r.bank_section === 'OTHER_WITHDRAWAL' ? 'bg-amber-100 text-amber-800' :
                            r.bank_section === 'SERVICE_CHARGE' ? 'bg-rose-100 text-rose-800' :
                            r.bank_section === 'INTEREST_EARNED' ? 'bg-blue-100 text-blue-800' :
                            'bg-gray-100 text-gray-600'
                          }`}>
                            {r.bank_section?.replace(/_/g, ' ') || 'UNKNOWN'}
                          </span>
                        </td>
                        <td className="px-2 py-1">
                          <div className="font-medium text-gray-900" title={r.description_raw || undefined}>
                            {r.description_clean || r.description_raw || '—'}
                          </div>
                        </td>
                        <td className={`px-2 py-1 text-right font-medium ${
                          (typeof r.amount === 'number' ? r.amount : parseFloat(r.amount || '0')) >= 0 
                            ? 'text-green-700' 
                            : 'text-red-700'
                        }`}>
                          {typeof r.amount === 'number' ? r.amount.toFixed(2) : r.amount}
                        </td>
                        <td className="px-2 py-1 text-right">
                          {r.balance_after != null ? (typeof r.balance_after === 'number' ? r.balance_after.toFixed(2) : String(r.balance_after)) : '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Manual pasted statement modal */}
      {manualOpen && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl max-w-5xl w-full max-h-[90vh] mx-4 p-4 text-sm flex flex-col gap-3">
            <div className="flex items-center justify-between mb-1">
              <h3 className="text-base font-semibold">New manual statement</h3>
              <Button variant="outline" size="sm" onClick={() => setManualOpen(false)}>
                Close
              </Button>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              <div>
                <Label className="block text-xs mb-1">Bank name</Label>
                <Input value={manualBankName} onChange={(e) => setManualBankName(e.target.value)} />
              </div>
              <div>
                <Label className="block text-xs mb-1">Bank code</Label>
                <Input value={manualBankCode} onChange={(e) => setManualBankCode(e.target.value)} />
              </div>
              <div>
                <Label className="block text-xs mb-1">Account last 4</Label>
                <Input value={manualAccountLast4} onChange={(e) => setManualAccountLast4(e.target.value)} />
              </div>
              <div>
                <Label className="block text-xs mb-1">Currency</Label>
                <Input value={manualCurrency} onChange={(e) => setManualCurrency(e.target.value)} />
              </div>
              <div>
                <Label className="block text-xs mb-1">Period start</Label>
                <Input type="date" value={manualPeriodStart} onChange={(e) => setManualPeriodStart(e.target.value)} />
              </div>
              <div>
                <Label className="block text-xs mb-1">Period end</Label>
                <Input type="date" value={manualPeriodEnd} onChange={(e) => setManualPeriodEnd(e.target.value)} />
              </div>
              <div>
                <Label className="block text-xs mb-1">Opening balance</Label>
                <Input
                  type="number"
                  value={manualOpening}
                  onChange={(e) => setManualOpening(e.target.value)}
                />
              </div>
              <div>
                <Label className="block text-xs mb-1">Closing balance</Label>
                <Input
                  type="number"
                  value={manualClosing}
                  onChange={(e) => setManualClosing(e.target.value)}
                />
              </div>
            </div>
            <div className="flex flex-col gap-2 flex-1 min-h-0">
              <Label className="block text-xs">Paste raw lines from PDF</Label>
              <textarea
                className="border rounded p-2 text-xs font-mono flex-1 min-h-[120px]"
                value={manualRawText}
                onChange={(e) => {
                  setManualRawText(e.target.value);
                  setManualParsingError(null);
                }}
                placeholder="Paste lines like:\n01/15 CCD DEPOSIT, EBAY ... 415.91"
              />
              <div className="flex items-center justify-between text-xs text-gray-600">
                <div>
                  {manualParsingError && <span className="text-red-600">{manualParsingError}</span>}
                  {!manualParsingError && manualRows.length > 0 && (
                    <span>{manualRows.length} parsed rows{manualRows.some((r) => r.duplicate) ? ' (duplicates skipped)' : ''}</span>
                  )}
                </div>
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => parseManualRawText(manualRawText, setManualRows, setManualParsingError)}
              >
                Parse text
              </Button>
              </div>
              {manualRows.length > 0 && (
                <div className="border rounded max-h-64 overflow-auto bg-white mt-1">
                  <table className="min-w-full text-[11px]">
                    <thead className="bg-gray-50">
                      <tr>
                        <th className="px-2 py-1 text-left">Date</th>
                        <th className="px-2 py-1 text-left">Description</th>
                        <th className="px-2 py-1 text-right">Amount</th>
                        <th className="px-2 py-1 text-left">Direction</th>
                        <th className="px-2 py-1 text-left">Duplicate</th>
                      </tr>
                    </thead>
                    <tbody>
                      {manualRows.map((row, idx) => (
                        <tr key={row.id} className="border-t">
                          <td className="px-2 py-1">
                            <Input
                              type="date"
                              className="h-6 px-1 text-[11px]"
                              value={row.date}
                              onChange={(e) => {
                                const v = e.target.value;
                                setManualRows((prev) => {
                                  const copy = [...prev];
                                  copy[idx] = { ...copy[idx], date: v };
                                  return copy;
                                });
                              }}
                            />
                          </td>
                          <td className="px-2 py-1">
                            <Input
                              className="h-6 px-1 text-[11px]"
                              value={row.description}
                              onChange={(e) => {
                                const v = e.target.value;
                                setManualRows((prev) => {
                                  const copy = [...prev];
                                  copy[idx] = { ...copy[idx], description: v };
                                  return copy;
                                });
                              }}
                            />
                          </td>
                          <td className="px-2 py-1">
                            <Input
                              className="h-6 px-1 text-[11px] text-right"
                              type="number"
                              value={row.amount}
                              onChange={(e) => {
                                const v = e.target.value;
                                setManualRows((prev) => {
                                  const copy = [...prev];
                                  copy[idx] = { ...copy[idx], amount: v };
                                  return copy;
                                });
                              }}
                            />
                          </td>
                          <td className="px-2 py-1">
                            <select
                              className="border rounded px-1 py-0.5 text-[11px]"
                              value={row.direction}
                              onChange={(e) => {
                                const v = e.target.value as 'debit' | 'credit';
                                setManualRows((prev) => {
                                  const copy = [...prev];
                                  copy[idx] = { ...copy[idx], direction: v };
                                  return copy;
                                });
                              }}
                            >
                              <option value="credit">Credit</option>
                              <option value="debit">Debit</option>
                            </select>
                          </td>
                          <td className="px-2 py-1 text-xs text-red-600">
                            {row.duplicate ? 'DUPLICATE' : ''}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
            <div className="flex justify-end gap-2 pt-2 border-t border-gray-200 text-xs">
              <Button variant="outline" size="sm" onClick={() => setManualOpen(false)} disabled={manualSaving}>
                Cancel
              </Button>
              <Button
                size="sm"
                disabled={manualSaving || manualRows.length === 0}
                onClick={() => saveManualStatement(false)}
              >
                {manualSaving ? 'Saving…' : 'Save statement'}
              </Button>
              <Button
                size="sm"
                disabled={manualSaving || manualRows.length === 0}
                onClick={() => saveManualStatement(true)}
              >
                {manualSaving ? 'Saving…' : 'Save & Commit to Ledger'}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

interface Accounting2LedgerTotals {
  total_in: number;
  total_out: number;
  net: number;
}

function LedgerTab2() {
  const [dateFrom, setDateFrom] = React.useState('');
  const [dateTo, setDateTo] = React.useState('');
  const [sourceType, setSourceType] = React.useState('');
  const [storageId, setStorageId] = React.useState('');
  const [direction, setDirection] = React.useState('');
  const [accountName, setAccountName] = React.useState('');
  const [categoryId, setCategoryId] = React.useState('');
  const [minAmount, setMinAmount] = React.useState('');
  const [maxAmount, setMaxAmount] = React.useState('');
  const [searchText, setSearchText] = React.useState('');
  const [isPersonal, setIsPersonal] = React.useState<string>(''); // '', 'true', 'false'
  const [isInternal, setIsInternal] = React.useState<string>('');

  const [totals, setTotals] = React.useState<Accounting2LedgerTotals | null>(null);

  const [categories, setCategories] = React.useState<Accounting2Category[]>([]);
  const [selectedIds, setSelectedIds] = React.useState<number[]>([]);
  const [savingSelection, setSavingSelection] = React.useState(false);
  const [stmtModalOpen] = React.useState(false);
  const [stmtModalLoading] = React.useState(false);
  const [stmtModalError] = React.useState<string | null>(null);
  const [stmtMeta] = React.useState<any | null>(null);
  const [stmtSampleRows] = React.useState<any[]>([]);

  React.useEffect(() => {
    const loadCategories = async () => {
      try {
        const { data } = await api.get<Accounting2Category[]>('/accounting/categories', { params: { is_active: true } });
        setCategories(data || []);
      } catch {
        // ignore
      }
    };
    void loadCategories();
  }, []);

  const buildFilterParams = React.useCallback(() => {
    const params: Record<string, any> = {};
    if (dateFrom) params.date_from = dateFrom;
    if (dateTo) params.date_to = dateTo;
    if (sourceType) params.source_type = sourceType;
    if (storageId) params.storage_id = storageId;
    if (direction) params.direction = direction;
    if (accountName) params.account_name = accountName;
    if (categoryId) params.category_id = Number(categoryId);
    if (minAmount) params.min_amount = Number(minAmount);
    if (maxAmount) params.max_amount = Number(maxAmount);
    if (searchText) params.search = searchText;
    if (isPersonal === 'true') params.is_personal = true;
    if (isPersonal === 'false') params.is_personal = false;
    if (isInternal === 'true') params.is_internal_transfer = true;
    if (isInternal === 'false') params.is_internal_transfer = false;
    return params;
  }, [dateFrom, dateTo, sourceType, storageId, direction, accountName, categoryId, minAmount, maxAmount, searchText, isPersonal, isInternal]);

  // Note: rows and layout now come from DataGridPage; we only need totals and selection.
  const loadRows = React.useCallback(async () => {
    try {
      const params: Record<string, any> = {
        limit: 1,
        offset: 0,
        ...buildFilterParams(),
      };
      await api.get('/grids/ledger_transactions/data', { params });
    } catch {
      // ignore; DataGridPage will surface any errors
    }
  }, [buildFilterParams]);

  const loadTotals = React.useCallback(async () => {
    try {
      const params = buildFilterParams();
      const { data } = await api.get<Accounting2LedgerTotals>('/accounting/transactions', { params });
      setTotals(data);
    } catch {
      setTotals(null);
    }
  }, [buildFilterParams]);

  React.useEffect(() => {
    void loadRows();
    void loadTotals();
  }, [loadRows, loadTotals]);

  const resetFilters = () => {
    setDateFrom('');
    setDateTo('');
    setSourceType('');
    setStorageId('');
    setDirection('');
    setAccountName('');
    setCategoryId('');
    setMinAmount('');
    setMaxAmount('');
    setSearchText('');
    setIsPersonal('');
    setIsInternal('');
  };


  const handleApplyCategoryToSelection = async () => {
    if (!selectedIds.length || !categoryId) return;
    setSavingSelection(true);
    try {
      // We don't need rule_id semantics here; call the generic transaction update per-row.
      const targetCategoryId = Number(categoryId);
      await Promise.all(
        selectedIds.map((id) =>
          api.put(`/accounting/transactions/${id}`, {
            expense_category_id: targetCategoryId,
          }),
        ),
      );
      await loadRows();
      await loadTotals();
    } catch (err: any) {
      alert(err?.response?.data?.detail || err?.message || 'Failed to apply category to selected');
    } finally {
      setSavingSelection(false);
    }
  };

  return (
    <div className="flex-1 flex flex-col gap-4">
      {totals && (
        <Card className="p-4 flex flex-wrap gap-4 text-sm">
          <div>
            <div className="text-gray-500 text-xs">Total In</div>
            <div className="font-semibold text-emerald-700">{totals.total_in.toFixed(2)}</div>
          </div>
          <div>
            <div className="text-gray-500 text-xs">Total Out</div>
            <div className="font-semibold text-red-700">{totals.total_out.toFixed(2)}</div>
          </div>
          <div>
            <div className="text-gray-500 text-xs">Net</div>
            <div className={totals.net >= 0 ? 'font-semibold text-emerald-700' : 'font-semibold text-red-700'}>
              {totals.net.toFixed(2)}
            </div>
          </div>
        </Card>
      )}

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
            <Input
              value={sourceType}
              onChange={(e) => setSourceType(e.target.value)}
              placeholder="bank_statement / cash_manual"
            />
          </div>
          <div>
            <Label className="block text-xs mb-1">Search in text</Label>
            <Input
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
              placeholder="Search in description / account / counterparty"
            />
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
            <Label className="block text-xs mb-1">Account name contains</Label>
            <Input
              value={accountName}
              onChange={(e) => setAccountName(e.target.value)}
            />
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
          <div>
            <Label className="block text-xs mb-1">Amount from</Label>
            <Input
              type="number"
              value={minAmount}
              onChange={(e) => setMinAmount(e.target.value)}
            />
          </div>
          <div>
            <Label className="block text-xs mb-1">Amount to</Label>
            <Input
              type="number"
              value={maxAmount}
              onChange={(e) => setMaxAmount(e.target.value)}
            />
          </div>
          <div />
          <div>
            <Label className="block text-xs mb-1">Personal</Label>
            <select
              className="border rounded px-2 py-1 text-sm w-full"
              value={isPersonal}
              onChange={(e) => setIsPersonal(e.target.value)}
            >
              <option value="">All</option>
              <option value="true">Personal only</option>
              <option value="false">Business only</option>
            </select>
          </div>
          <div>
            <Label className="block text-xs mb-1">Internal transfer</Label>
            <select
              className="border rounded px-2 py-1 text-sm w-full"
              value={isInternal}
              onChange={(e) => setIsInternal(e.target.value)}
            >
              <option value="">All</option>
              <option value="true">Internal only</option>
              <option value="false">Exclude internal</option>
            </select>
          </div>
        </div>
        <div className="flex justify-between items-center mt-2 text-xs">
          <div className="flex items-center gap-2">
            <Button type="button" variant="outline" size="sm" onClick={resetFilters}>
              Reset filters
            </Button>
            {selectedIds.length > 0 && (
              <>
                <span className="text-gray-500">Selected: {selectedIds.length}</span>
                <Button
                  type="button"
                  size="sm"
                  disabled={savingSelection || !categoryId}
                  onClick={handleApplyCategoryToSelection}
                >
                  {savingSelection ? 'Applying…' : 'Apply category to selected'}
                </Button>
              </>
            )}
          </div>
          <span className="text-gray-500">
            {totals ? `Total in: ${totals.total_in.toFixed(2)} · Total out: ${totals.total_out.toFixed(2)} · Net: ${totals.net.toFixed(2)}` : 'Totals unavailable'}
          </span>
        </div>
      </Card>

      <div className="flex-1 min-h-0 overflow-hidden border rounded bg-white">
        <DataGridPage
          gridKey="ledger_transactions"
          title="Ledger 2"
          extraParams={buildFilterParams()}
          selectionMode="multiRow"
          onSelectionChange={(rows) => setSelectedIds(rows.map((r: any) => r.id))}
        />
      </div>

      {stmtModalOpen && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
            <div className="bg-white rounded-lg shadow-xl max-w-3xl w-full mx-4 p-4 text-sm">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-base font-semibold">Bank statement</h3>
                <div className="flex items-center gap-2">
                  {stmtMeta && stmtMeta.id && (
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        // открыть старую детальную страницу в новом табе для пока ещё существующего Accounting 1
                        window.open(`/accounting/bank-statements/${stmtMeta.id}`, '_blank');
                      }}
                    >
                      Open in Accounting
                    </Button>
                  )}
                </div>
              </div>
              {stmtModalLoading ? (
                <div className="text-gray-600">Loading statement…</div>
              ) : stmtModalError ? (
                <div className="text-red-600">{stmtModalError}</div>
              ) : !stmtMeta ? (
                <div className="text-gray-600">No data.</div>
              ) : (
                <div className="space-y-3 text-xs text-gray-700">
                  <div className="space-y-1">
                    <div>
                      <span className="font-semibold">ID:</span> {stmtMeta.id}
                    </div>
                    <div>
                      <span className="font-semibold">Bank:</span> {stmtMeta.bank_name || '—'}
                    </div>
                    <div>
                      <span className="font-semibold">Account:</span>{' '}
                      {stmtMeta.account_last4 ? `****${stmtMeta.account_last4}` : '—'}
                    </div>
                    <div>
                      <span className="font-semibold">Currency:</span> {stmtMeta.currency || '—'}
                    </div>
                    <div>
                      <span className="font-semibold">Period:</span>{' '}
                      {stmtMeta.statement_period_start && stmtMeta.statement_period_end
                        ? `${stmtMeta.statement_period_start} – ${stmtMeta.statement_period_end}`
                        : '—'}
                    </div>
                    <div>
                      <span className="font-semibold">Opening balance:</span>{' '}
                      {typeof stmtMeta.opening_balance === 'number'
                        ? stmtMeta.opening_balance.toFixed(2)
                        : stmtMeta.opening_balance ?? '—'}
                    </div>
                    <div>
                      <span className="font-semibold">Closing balance:</span>{' '}
                      {typeof stmtMeta.closing_balance === 'number'
                        ? stmtMeta.closing_balance.toFixed(2)
                        : stmtMeta.closing_balance ?? '—'}
                    </div>
                    <div>
                      <span className="font-semibold">Rows:</span> {stmtMeta.rows_count ?? '—'}
                    </div>
                    <div>
                      <span className="font-semibold">Status:</span> {stmtMeta.status || '—'}
                    </div>
                  </div>

                  <div>
                    <div className="font-semibold mb-1">Sample rows</div>
                    {stmtSampleRows.length === 0 ? (
                      <div className="text-gray-500">No rows loaded.</div>
                    ) : (
                      <div className="border rounded max-h-48 overflow-auto bg-white">
                        <table className="min-w-full text-[11px]">
                          <thead className="bg-gray-50">
                            <tr>
                              <th className="px-2 py-1 text-left">Date</th>
                              <th className="px-2 py-1 text-left">Description</th>
                              <th className="px-2 py-1 text-right">Amount</th>
                            </tr>
                          </thead>
                          <tbody>
                            {stmtSampleRows.map((row: any) => (
                              <tr key={row.id} className="border-t">
                                <td className="px-2 py-1 whitespace-nowrap">{row.operation_date || row.posting_date || '—'}</td>
                                <td className="px-2 py-1 truncate max-w-xs" title={row.description_clean || row.description_raw || undefined}>
                                  {row.description_clean || row.description_raw || '—'}
                                </td>
                                <td className="px-2 py-1 text-right">
                                  {typeof row.amount === 'number' ? row.amount.toFixed(2) : row.amount}
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
          </div>
        )}
      </div>
  );
}

interface Accounting2Category {
  id: number;
  code: string;
  name: string;
}

interface Accounting2CashExpenseRow {
  id: number;
  date: string;
  amount: number;
  currency: string | null;
  expense_category_id: number;
  counterparty: string | null;
  description: string | null;
  storage_id: string | null;
  paid_by_user_id: string;
  created_at?: string;
}

function CashExpensesTab2() {
  const [dateValue, setDateValue] = React.useState('');
  const [amount, setAmount] = React.useState('');
  const [currency, setCurrency] = React.useState('USD');
  const [counterparty, setCounterparty] = React.useState('');
  const [description, setDescription] = React.useState('');
  const [storageId, setStorageId] = React.useState('');
  const [categoryId, setCategoryId] = React.useState('');
  const [categories, setCategories] = React.useState<Accounting2Category[]>([]);
  const [submitting, setSubmitting] = React.useState(false);

  const [rows, setRows] = React.useState<Accounting2CashExpenseRow[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [page, setPage] = React.useState(1);
  const [pageSize] = React.useState(50);
  const [total, setTotal] = React.useState(0);

  const [dateFrom, setDateFrom] = React.useState('');
  const [dateTo, setDateTo] = React.useState('');
  const [filterCategoryId, setFilterCategoryId] = React.useState('');
  const [filterStorage, setFilterStorage] = React.useState('');

  React.useEffect(() => {
    const loadCategories = async () => {
      try {
        const { data } = await api.get<Accounting2Category[]>('/accounting/categories', { params: { is_active: true } });
        setCategories(data || []);
      } catch {
        // ignore
      }
    };
    void loadCategories();
  }, []);

  const loadRows = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params: Record<string, any> = {
        limit: pageSize,
        offset: (page - 1) * pageSize,
      };
      if (dateFrom) params.from = dateFrom;
      if (dateTo) params.to = dateTo;
      if (filterCategoryId) params.category_id = Number(filterCategoryId);
      if (filterStorage) params.storageID = filterStorage;

      const { data } = await api.get<{ rows: Accounting2CashExpenseRow[]; total: number }>(
        '/grids/accounting_cash_expenses/data',
        { params },
      );
      const payload: any = data as any;
      const rowsData = Array.isArray(payload.rows) ? payload.rows : Array.isArray(payload.items) ? payload.items : [];
      setRows(rowsData);
      setTotal(typeof payload.total === 'number' ? payload.total : rowsData.length);
    } catch (err: any) {
      setError(err?.message || 'Failed to load cash expenses');
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, dateFrom, dateTo, filterCategoryId, filterStorage]);

  React.useEffect(() => {
    void loadRows();
  }, [loadRows]);

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
      setAmount('');
      setCounterparty('');
      setDescription('');
      setStorageId('');
      await loadRows();
    } catch (err: any) {
      alert(err?.response?.data?.detail || err?.message || 'Failed to create cash expense');
    } finally {
      setSubmitting(false);
    }
  };

  const resetFilters = () => {
    setDateFrom('');
    setDateTo('');
    setFilterCategoryId('');
    setFilterStorage('');
    setPage(1);
  };

  const pageCount = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div className="flex-1 flex flex-col gap-4">
      <Card className="p-4">
        <h2 className="text-lg font-semibold mb-2">New Cash Expense (Accounting 2)</h2>
        <form className="grid grid-cols-1 md:grid-cols-4 gap-3 items-end" onSubmit={handleSubmit}>
          <div>
            <Label className="block text-xs mb-1">Date</Label>
            <Input type="date" value={dateValue} onChange={(e) => setDateValue(e.target.value)} required />
          </div>
          <div>
            <Label className="block text-xs mb-1">Amount</Label>
            <Input
              type="number"
              step="0.01"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              required
            />
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
              {submitting ? 'Saving…' : 'Add Expense'}
            </Button>
          </div>
        </form>
      </Card>

      <Card className="p-4 flex flex-col gap-3 flex-1 min-h-0">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3 items-end">
          <div>
            <Label className="block text-xs mb-1">From</Label>
            <Input type="date" value={dateFrom} onChange={(e) => { setDateFrom(e.target.value); setPage(1); }} />
          </div>
          <div>
            <Label className="block text-xs mb-1">To</Label>
            <Input type="date" value={dateTo} onChange={(e) => { setDateTo(e.target.value); setPage(1); }} />
          </div>
          <div>
            <Label className="block text-xs mb-1">Category</Label>
            <select
              className="border rounded px-2 py-1 text-sm w-full"
              value={filterCategoryId}
              onChange={(e) => { setFilterCategoryId(e.target.value); setPage(1); }}
            >
              <option value="">All</option>
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
              value={filterStorage}
              onChange={(e) => { setFilterStorage(e.target.value); setPage(1); }}
            />
          </div>
        </div>
        <div className="flex justify-between items-center mt-2 text-xs">
          <Button type="button" variant="outline" size="sm" onClick={resetFilters}>
            Reset filters
          </Button>
          <span className="text-gray-500">
            {total > 0 ? `Showing ${(page - 1) * pageSize + 1}-${Math.min(total, page * pageSize)} of ${total}` : 'No rows'}
          </span>
        </div>

        <div className="flex-1 min-h-0 overflow-auto border rounded bg-white mt-2">
          {error && (
            <div className="p-3 text-sm text-red-600 border-b">{error}</div>
          )}
          <table className="min-w-full text-xs">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-2 py-2 text-left">Date</th>
                <th className="px-2 py-2 text-right">Amount</th>
                <th className="px-2 py-2 text-left">Currency</th>
                <th className="px-2 py-2 text-left">Category</th>
                <th className="px-2 py-2 text-left">Counterparty</th>
                <th className="px-2 py-2 text-left">Description</th>
                <th className="px-2 py-2 text-left">Storage</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={7} className="px-3 py-3 text-sm text-gray-600">Loading cash expenses…</td>
                </tr>
              ) : rows.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-3 py-3 text-sm text-gray-600">No cash expenses found.</td>
                </tr>
              ) : (
                rows.map((r) => (
                  <tr key={r.id} className="border-t hover:bg-gray-50">
                    <td className="px-2 py-1 whitespace-nowrap">{r.date}</td>
                    <td className="px-2 py-1 text-right">
                      {typeof r.amount === 'number' ? r.amount.toFixed(2) : r.amount}
                    </td>
                    <td className="px-2 py-1 whitespace-nowrap">{r.currency || '—'}</td>
                    <td className="px-2 py-1 whitespace-nowrap text-[11px] text-gray-600">
                      {r.expense_category_id ?? '—'}
                    </td>
                    <td className="px-2 py-1 whitespace-nowrap">
                      <div className="truncate max-w-[160px]" title={r.counterparty || undefined}>
                        {r.counterparty || '—'}
                      </div>
                    </td>
                    <td className="px-2 py-1">
                      <div className="truncate max-w-xs" title={r.description || undefined}>
                        {r.description || '—'}
                      </div>
                    </td>
                    <td className="px-2 py-1 whitespace-nowrap text-[11px] text-gray-600">
                      {r.storage_id || ''}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
          {total > pageSize && (
            <div className="flex items-center justify-between px-3 py-2 text-xs text-gray-600 border-t bg-gray-50">
              <div>
                Page {page} of {pageCount}
              </div>
              <div className="flex items-center gap-1">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={page <= 1}
                  onClick={() => setPage(1)}
                >
                  « First
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={page <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                >
                  ‹ Prev
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={page >= pageCount}
                  onClick={() => setPage((p) => Math.min(pageCount, p + 1))}
                >
                  Next ›
                </Button>
              </div>
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}

interface Accounting2Rule {
  id: number;
  pattern_type: string;
  pattern_value: string;
  expense_category_id: number;
  priority: number;
  is_active: boolean;
}

interface Accounting2RulePreviewRow {
  id: number;
  date: string;
  amount: number;
  direction: 'in' | 'out';
  account_name: string | null;
  description: string | null;
  expense_category_id: number | null;
}

function RulesTab2() {
  const [rules, setRules] = React.useState<Accounting2Rule[]>([]);
  const [categories, setCategories] = React.useState<Accounting2Category[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [refreshKey, setRefreshKey] = React.useState(0);

  const [patternType, setPatternType] = React.useState('contains');
  const [patternValue, setPatternValue] = React.useState('');
  const [categoryId, setCategoryId] = React.useState('');
  const [priority, setPriority] = React.useState('10');
  const [submitting, setSubmitting] = React.useState(false);

  const [previewOpen, setPreviewOpen] = React.useState(false);
  const [previewLoading, setPreviewLoading] = React.useState(false);
  const [previewError, setPreviewError] = React.useState<string | null>(null);
  const [previewRows, setPreviewRows] = React.useState<Accounting2RulePreviewRow[]>([]);
  const [previewSelectedIds, setPreviewSelectedIds] = React.useState<number[]>([]);
  const [previewApplying, setPreviewApplying] = React.useState(false);

  React.useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const [rulesResp, catsResp] = await Promise.all([
          api.get<Accounting2Rule[]>('/accounting/rules', { params: { is_active: true } }),
          api.get<Accounting2Category[]>('/accounting/categories', { params: { is_active: true } }),
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
        priority: Number(priority) || 10,
        is_active: true,
      });
      setPatternValue('');
      setCategoryId('');
      setPriority('10');
      setRefreshKey((v) => v + 1);
    } catch (err: any) {
      alert(err?.response?.data?.detail || err?.message || 'Failed to create rule');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm('Delete this rule?')) return;
    await api.delete(`/accounting/rules/${id}`);
    setRefreshKey((v) => v + 1);
  };

  const openPreview = async (rule: Accounting2Rule) => {
    if (!rule.pattern_value) return;
    setPreviewOpen(true);
    setPreviewLoading(true);
    setPreviewError(null);
    setPreviewRows([]);
    setPreviewSelectedIds([]);
    try {
      const params: Record<string, any> = {
        limit: 20,
        offset: 0,
        search: rule.pattern_value,
      };
      const { data } = await api.get<{ rows: Accounting2RulePreviewRow[]; total: number }>(
        '/grids/ledger_transactions/data',
        { params },
      );
      const payload: any = data as any;
      const rows = Array.isArray(payload.rows) ? payload.rows : Array.isArray(payload.items) ? payload.items : [];
      setPreviewRows(rows);
    } catch (err: any) {
      setPreviewError(err?.message || 'Failed to load preview');
    } finally {
      setPreviewLoading(false);
    }
  };

  const resolveCategoryName = (id: number) => {
    const c = categories.find((x) => x.id === id);
    return c ? `${c.code} — ${c.name}` : id;
  };

  const togglePreviewSelected = (id: number) => {
    setPreviewSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  };

  const handleApplyRuleToPreviewSelection = async (rule: Accounting2Rule) => {
    if (!previewSelectedIds.length) return;
    setPreviewApplying(true);
    try {
      await api.post(`/accounting/rules/${rule.id}/apply`, {
        transaction_ids: previewSelectedIds,
      });
      // Reload preview rows to reflect updated categories
      await openPreview(rule);
    } catch (err: any) {
      alert(err?.response?.data?.detail || err?.message || 'Failed to apply rule to selected transactions');
    } finally {
      setPreviewApplying(false);
    }
  };

  return (
    <div className="flex-1 flex flex-col gap-4">
      <Card className="p-4">
        <h2 className="text-lg font-semibold mb-2">New Auto-Categorization Rule (Accounting 2)</h2>
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
              placeholder="Text fragment or regex pattern"
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
            <Label className="block text-xs mb-1">Priority</Label>
            <Input
              type="number"
              value={priority}
              onChange={(e) => setPriority(e.target.value)}
              placeholder="10"
            />
          </div>
          <div className="md:col-span-5 flex justify-end mt-2">
            <Button type="submit" disabled={submitting || !patternValue || !categoryId}>
              {submitting ? 'Saving…' : 'Create Rule'}
            </Button>
          </div>
        </form>
      </Card>

      <Card className="p-4 flex-1 min-h-0 flex flex-col">
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-sm font-semibold text-gray-800">Active Rules</h2>
        </div>
        <div className="flex-1 min-h-0 overflow-auto border rounded bg-white">
          {loading ? (
            <div className="p-4 text-sm text-gray-600">Loading rules…</div>
          ) : rules.length === 0 ? (
            <div className="p-4 text-sm text-gray-600">No rules yet.</div>
          ) : (
            <table className="min-w-full text-xs">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-2 py-2 text-left">Pattern</th>
                  <th className="px-2 py-2 text-left">Category</th>
                  <th className="px-2 py-2 text-left">Priority</th>
                  <th className="px-2 py-2 text-left">Type</th>
                  <th className="px-2 py-2 text-left">Actions</th>
                </tr>
              </thead>
              <tbody>
                {rules.map((r) => (
                  <tr key={r.id} className="border-t hover:bg-gray-50">
                    <td className="px-2 py-1">
                      <div className="truncate max-w-xs" title={r.pattern_value}>
                        {r.pattern_value}
                      </div>
                    </td>
                    <td className="px-2 py-1 whitespace-nowrap text-[11px] text-gray-700">
                      {resolveCategoryName(r.expense_category_id)}
                    </td>
                    <td className="px-2 py-1 whitespace-nowrap">{r.priority}</td>
                    <td className="px-2 py-1 whitespace-nowrap text-[11px] text-gray-600">{r.pattern_type}</td>
                    <td className="px-2 py-1 whitespace-nowrap text-[11px]">
                      <div className="flex gap-2">
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          className="h-auto px-2 py-0 text-[11px]"
                          onClick={() => void openPreview(r)}
                        >
                          Preview
                        </Button>
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          className="h-auto px-2 py-0 text-[11px] text-red-700 border-red-200"
                          onClick={() => void handleDelete(r.id)}
                        >
                          Delete
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </Card>

      {previewOpen && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl max-w-3xl w-full mx-4 p-4 text-sm flex flex-col max-h-[80vh]">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-base font-semibold">Rule preview</h3>
          <div className="flex items-center gap-2 text-xs">
            {previewRows.length > 0 && (
              <>
                <span className="text-gray-500">Selected: {previewSelectedIds.length}</span>
                <Button
                  type="button"
                  size="sm"
                  disabled={previewApplying || previewSelectedIds.length === 0}
                  onClick={() => {
                    const rule = rules.find((r) => r.pattern_value === patternValue && r.expense_category_id === Number(categoryId));
                    // Fallback: just pick any rule with same pattern if direct match not found
                    const effectiveRule = rule || rules[0];
                    if (!effectiveRule) return;
                    void handleApplyRuleToPreviewSelection(effectiveRule);
                  }}
                >
                  {previewApplying ? 'Applying…' : 'Apply rule to selected'}
                </Button>
              </>
            )}
            <Button type="button" variant="outline" size="sm" onClick={() => setPreviewOpen(false)}>
              Close
            </Button>
          </div>
        </div>
            {previewLoading ? (
              <div className="text-gray-600">Loading matching transactions…</div>
            ) : previewError ? (
              <div className="text-red-600">{previewError}</div>
            ) : previewRows.length === 0 ? (
              <div className="text-gray-600">No matching transactions found for current ledger.</div>
            ) : (
              <div className="flex-1 min-h-0 overflow-auto border rounded bg-white">
                <table className="min-w-full text-xs">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-2 py-2 w-8 text-center">
                        <Checkbox
                          checked={previewRows.length > 0 && previewSelectedIds.length === previewRows.length}
                          onCheckedChange={(v) => {
                            if (v) setPreviewSelectedIds(previewRows.map((r) => r.id));
                            else setPreviewSelectedIds([]);
                          }}
                        />
                      </th>
                      <th className="px-2 py-2 text-left">Date</th>
                      <th className="px-2 py-2 text-left">Account</th>
                      <th className="px-2 py-2 text-left">Description</th>
                      <th className="px-2 py-2 text-left">Category</th>
                      <th className="px-2 py-2 text-right">Amount</th>
                    </tr>
                  </thead>
                  <tbody>
                    {previewRows.map((r) => {
                      const signed = typeof r.amount === 'number' ? r.amount * (r.direction === 'out' ? -1 : 1) : r.amount;
                      return (
                        <tr key={r.id} className="border-t">
                          <td className="px-2 py-1 text-center">
                            <Checkbox
                              checked={previewSelectedIds.includes(r.id)}
                              onCheckedChange={() => togglePreviewSelected(r.id)}
                            />
                          </td>
                          <td className="px-2 py-1 whitespace-nowrap">{r.date}</td>
                          <td className="px-2 py-1 whitespace-nowrap text-[11px] text-gray-700">{r.account_name || '—'}</td>
                          <td className="px-2 py-1">
                            <div className="truncate max-w-xs" title={r.description || undefined}>
                              {r.description || '—'}
                            </div>
                          </td>
                          <td className="px-2 py-1 whitespace-nowrap text-[11px] text-gray-700">
                            {r.expense_category_id != null ? String(r.expense_category_id) : ''}
                          </td>
                          <td className="px-2 py-1 text-right">
                            {typeof signed === 'number' ? signed.toFixed(2) : signed}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default function Accounting2Page() {
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

  const basePath = '/accounting2';
  const currentPath = location.pathname.startsWith(basePath)
    ? location.pathname.substring(basePath.length) || '/statements'
    : '/statements';

  const activeTab = currentPath.startsWith('/ledger')
    ? 'ledger'
    : currentPath.startsWith('/cash')
      ? 'cash'
      : currentPath.startsWith('/rules')
        ? 'rules'
        : 'statements';

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      <FixedHeader />
      <div className="pt-16 px-4 pb-4 flex-1 flex flex-col">
        <h1 className="text-3xl font-bold mb-4">Accounting 2</h1>

        <Tabs value={activeTab} className="w-full">
          <TabsList>
            <TabsTrigger value="statements" onClick={() => navigate('/accounting2/statements')}>Statements 2</TabsTrigger>
            <TabsTrigger value="ledger" onClick={() => navigate('/accounting2/ledger')}>Ledger 2</TabsTrigger>
            <TabsTrigger value="cash" onClick={() => navigate('/accounting2/cash')}>Cash Expenses 2</TabsTrigger>
            <TabsTrigger value="rules" onClick={() => navigate('/accounting2/rules')}>Rules 2</TabsTrigger>
          </TabsList>
        </Tabs>

        <div className="flex-1 flex flex-col mt-4">
          <Routes>
            <Route path="statements" element={<StatementsTab2 />} />
            <Route path="ledger" element={<LedgerTab2 />} />
            <Route path="cash" element={<CashExpensesTab2 />} />
            <Route path="rules" element={<RulesTab2 />} />
            <Route path="*" element={<Navigate to="statements" replace />} />
          </Routes>
        </div>
      </div>
    </div>
  );
}
