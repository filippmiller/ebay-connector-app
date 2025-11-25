import { useEffect, useMemo, useState } from 'react';
import FixedHeader from '@/components/FixedHeader';
import { DataGridPage } from '@/components/DataGridPage';
import { createSnipe, updateSnipe, cancelSnipe } from '@/api/sniper';
import { ebayApi } from '@/api/ebay';

interface EditFormState {
  id?: string;
  status?: string;
  ebay_account_id: string;
  item_id: string;
  max_bid_amount: string;
  seconds_before_end: string;
  comment: string;
}

const EMPTY_FORM: EditFormState = {
  id: undefined,
  status: undefined,
  ebay_account_id: '',
  item_id: '',
  max_bid_amount: '',
  seconds_before_end: '5',
  comment: '',
};

type EbayAccountOption = {
  id: string;
  username: string | null;
  house_name: string;
  marketplace_id?: string | null;
  site_id?: number | null;
  is_active?: boolean;
  status?: string;
  token?: {
    id: string;
    ebay_account_id: string;
    expires_at?: string | null;
    last_refreshed_at?: string | null;
    refresh_error?: string | null;
  } | null;
};

export default function SniperPage() {
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [accounts, setAccounts] = useState<EbayAccountOption[]>([]);
  const [accountsLoading, setAccountsLoading] = useState(false);
  const [accountsError, setAccountsError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [modalMode, setModalMode] = useState<'add' | 'edit'>('add');
  const [form, setForm] = useState<EditFormState>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [refreshToken, setRefreshToken] = useState(0);

  useEffect(() => {
    const loadAccounts = async () => {
      try {
        setAccountsLoading(true);
        setAccountsError(null);
        const data = await ebayApi.getAccounts(true);
        // Filter to accounts that are active and have a non-broken token.
        const usable = (data || []).filter((a: EbayAccountOption) => {
          const active = a.is_active !== false && a.status !== 'DISABLED';
          const hasToken = !!a.token && !a.token?.refresh_error;
          return active && hasToken;
        });
        setAccounts(usable);
      } catch (e) {
        setAccountsError('Failed to load eBay accounts for Sniper');
      } finally {
        setAccountsLoading(false);
      }
    };
    void loadAccounts();
  }, []);

  const extraParams = useMemo(() => {
    const params: Record<string, unknown> = { refreshToken };
    if (statusFilter) params.state = statusFilter;
    return params;
  }, [statusFilter, refreshToken]);

  const openAddModal = () => {
    setModalMode('add');
    setForm((prev) => ({
      ...EMPTY_FORM,
      ebay_account_id: accounts[0]?.id || '',
    }));
    setIsModalOpen(true);
  };

  const openEditModal = (row: Record<string, unknown>) => {
    const r = row as { [key: string]: unknown };
    setModalMode('edit');
    setForm({
      id: String(r.id ?? ''),
      status: typeof r.status === 'string' ? r.status : undefined,
      ebay_account_id: typeof r.ebay_account_id === 'string' ? r.ebay_account_id : '',
      item_id: typeof r.item_id === 'string' ? r.item_id : '',
      max_bid_amount:
        typeof r.max_bid_amount === 'number'
          ? String(r.max_bid_amount)
          : typeof r.max_bid_amount === 'string'
          ? r.max_bid_amount
          : '',
      seconds_before_end:
        typeof r.seconds_before_end === 'number'
          ? String(r.seconds_before_end)
          : typeof r.seconds_before_end === 'string'
          ? r.seconds_before_end
          : '5',
      comment: typeof r.comment === 'string' ? r.comment : '',
    });
    setIsModalOpen(true);
  };

  const handleSave = async () => {
    if (!form.ebay_account_id) {
      setError('eBay account is required');
      return;
    }
    if (!form.item_id || !form.max_bid_amount) {
      setError('Item ID and Max bid are required');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      if (modalMode === 'add') {
        await createSnipe({
          ebay_account_id: form.ebay_account_id,
          item_id: form.item_id,
          max_bid_amount: Number(form.max_bid_amount),
          seconds_before_end: form.seconds_before_end ? Number(form.seconds_before_end) : undefined,
          comment: form.comment || undefined,
        });
      } else if (modalMode === 'edit' && form.id) {
        await updateSnipe(form.id, {
          max_bid_amount: Number(form.max_bid_amount),
          seconds_before_end: form.seconds_before_end ? Number(form.seconds_before_end) : undefined,
          comment: form.comment || undefined,
        });
      }
      setIsModalOpen(false);
      setRefreshToken((x) => x + 1);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Failed to save snipe');
    } finally {
      setSaving(false);
    }
  };

  const handleCancelSnipeFromModal = async () => {
    if (modalMode !== 'edit' || !form.id) return;
    if (!window.confirm('Cancel this snipe?')) return;
    try {
      await cancelSnipe(form.id);
      setIsModalOpen(false);
      setRefreshToken((x) => x + 1);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Failed to cancel snipe');
    }
  };

  const canCancel = form.status === 'pending' || form.status === 'scheduled';

  return (
    <div className="h-screen flex flex-col bg-gray-50">
      <FixedHeader />
      <div className="pt-16 flex-1 px-4 py-6 overflow-hidden">
        <div className="w-full h-full flex flex-col">
          <div className="flex items-center justify-between mb-4">
            <h1 className="text-3xl font-bold">Sniper</h1>
            <button
              type="button"
              onClick={openAddModal}
              className="px-4 py-2 rounded-md bg-blue-600 text-white text-sm font-medium shadow-sm hover:bg-blue-700"
            >
              Add Snipe
            </button>
          </div>

          <div className="flex items-center gap-3 mb-3 text-sm">
            <select
              className="border rounded px-2 py-1 text-sm"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
            >
              <option value="">All statuses</option>
              <option value="pending">Pending</option>
              <option value="scheduled">Scheduled</option>
              <option value="executed_stub">Executed (stub)</option>
              <option value="won">Won</option>
              <option value="lost">Lost</option>
              <option value="cancelled">Cancelled</option>
              <option value="error">Error</option>
            </select>
          </div>

          {error && <div className="mb-2 text-xs text-red-600">{error}</div>}

          <div className="flex-1 min-h-0">
            <DataGridPage
              gridKey="sniper_snipes"
              title="Sniper snipes"
              extraParams={extraParams}
              onRowClick={openEditModal}
            />
          </div>
        </div>
      </div>

      {isModalOpen && (
        <div className="fixed inset-0 bg-black bg-opacity-30 flex items-center justify-center z-50">
          <div className="bg-white rounded shadow-lg w-full max-w-lg max-h-[90vh] overflow-auto">
            <div className="px-4 py-3 border-b flex items-center justify-between">
              <div className="font-semibold text-sm">{modalMode === 'add' ? 'Add snipe' : 'Edit snipe'}</div>
              <button
                type="button"
                className="text-xs text-gray-500 hover:text-gray-700"
                onClick={() => setIsModalOpen(false)}
              >
                Close
              </button>
            </div>
            <div className="p-4 space-y-3 text-sm">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">eBay account</label>
                  <select
                    className="border rounded px-2 py-1 w-full text-sm"
                    value={form.ebay_account_id}
                    onChange={(e) => setForm((f) => ({ ...f, ebay_account_id: e.target.value }))}
                    disabled={modalMode === 'edit'}
                  >
                    <option value="">Select account…</option>
                    {accounts.map((acc) => (
                      <option key={acc.id} value={acc.id}>
                        {acc.username || acc.house_name || acc.id}
                      </option>
                    ))}
                  </select>
                  {accountsLoading && (
                    <div className="mt-1 text-[10px] text-gray-500">Loading eBay accounts…</div>
                  )}
                  {accountsError && (
                    <div className="mt-1 text-[10px] text-red-600">{accountsError}</div>
                  )}
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Item ID</label>
                  <input
                    type="text"
                    className="border rounded px-2 py-1 w-full text-sm"
                    value={form.item_id}
                    onChange={(e) => setForm((f) => ({ ...f, item_id: e.target.value }))}
                    readOnly={modalMode === 'edit'}
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Max bid amount</label>
                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    className="border rounded px-2 py-1 w-full text-sm"
                    value={form.max_bid_amount}
                    onChange={(e) => setForm((f) => ({ ...f, max_bid_amount: e.target.value }))}
                    required
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Seconds before end</label>
                  <input
                    type="number"
                    min="0"
                    max="600"
                    className="border rounded px-2 py-1 w-full text-sm"
                    value={form.seconds_before_end}
                    onChange={(e) => setForm((f) => ({ ...f, seconds_before_end: e.target.value }))}
                  />
                </div>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Comment (optional)</label>
                <textarea
                  className="border rounded px-2 py-1 w-full text-sm resize-y min-h-[48px]"
                  value={form.comment}
                  onChange={(e) => setForm((f) => ({ ...f, comment: e.target.value }))}
                />
              </div>
              {modalMode === 'edit' && form.status && (
                <div className="text-xs text-gray-600">
                  Current status: <span className="font-semibold">{form.status}</span>
                </div>
              )}
            </div>
            <div className="px-4 py-3 border-t flex items-center justify-between gap-3 text-sm">
              {modalMode === 'edit' && canCancel && (
                <button
                  type="button"
                  className="px-3 py-1 rounded border border-red-300 text-red-700 bg-red-50 hover:bg-red-100"
                  onClick={handleCancelSnipeFromModal}
                >
                  Cancel snipe
                </button>
              )}
              <div className="flex items-center gap-3 ml-auto">
                <button
                  type="button"
                  className="px-3 py-1 rounded border text-gray-700 bg-gray-50 hover:bg-gray-100"
                  onClick={() => setIsModalOpen(false)}
                >
                  Close
                </button>
                <button
                  type="button"
                  className="px-4 py-1.5 rounded bg-blue-600 text-white font-medium hover:bg-blue-700 disabled:opacity-60"
                  onClick={handleSave}
                  disabled={saving}
                >
                  {saving ? 'Saving…' : 'Save'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
