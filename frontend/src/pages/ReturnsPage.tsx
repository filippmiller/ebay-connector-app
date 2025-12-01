import { useEffect, useState } from 'react';
import FixedHeader from '@/components/FixedHeader';
import { ebayApi, EbayReturnRow } from '@/api/ebay';

interface EbayAccountSummary {
  id: string;
  username?: string | null;
  ebay_user_id?: string | null;
  house_name?: string | null;
}

export default function ReturnsPage() {
  const [accounts, setAccounts] = useState<EbayAccountSummary[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState<string | null>(null);
  const [rows, setRows] = useState<EbayReturnRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load active ebay accounts on mount
  useEffect(() => {
    void (async () => {
      try {
        const data = await ebayApi.getAccounts(true);
        const mapped: EbayAccountSummary[] = (data || []).map((a: any) => ({
          id: a.id,
          username: a.username ?? null,
          ebay_user_id: a.ebay_user_id ?? null,
          house_name: a.house_name ?? null,
        }));
        setAccounts(mapped);
        if (mapped.length > 0) {
          setSelectedAccountId(mapped[0].id);
        }
      } catch (e: any) {
        setError(e?.message || 'Failed to load eBay accounts');
      }
    })();
  }, []);

  // Fetch returns whenever selected account changes
  useEffect(() => {
    if (!selectedAccountId) return;
    setLoading(true);
    setError(null);
    void (async () => {
      try {
        const resp = await ebayApi.getReturns({ accountId: selectedAccountId, limit: 200, offset: 0 });
        setRows(resp.items || []);
      } catch (e: any) {
        const message =
          e?.response?.data?.detail || e?.message || 'Failed to load eBay returns';
        setError(message);
        setRows([]);
      } finally {
        setLoading(false);
      }
    })();
  }, [selectedAccountId]);

  const selectedAccount =
    selectedAccountId && accounts.find((a) => a.id === selectedAccountId);

  return (
    <div className="h-screen flex flex-col bg-gray-50">
      <FixedHeader />
      <div className="pt-16 flex-1 px-4 py-6 overflow-hidden">
        <div className="w-full h-full flex flex-col gap-4">
          <div>
            <h1 className="text-3xl font-bold">Returns</h1>
            <p className="text-gray-600 mt-2 text-sm max-w-3xl">
              Normalized Post-Order returns fetched from eBay and stored in the <code>ebay_returns</code>{' '}
              table. Each row corresponds to a single return_id per account.
            </p>
          </div>

          {/* Account selector */}
          <div className="flex items-center gap-3">
            <label className="text-sm font-medium text-gray-700">eBay account:</label>
            <select
              className="border rounded-md px-2 py-1 text-sm bg-white"
              value={selectedAccountId ?? ''}
              onChange={(e) => setSelectedAccountId(e.target.value || null)}
            >
              {accounts.length === 0 && <option value="">No active eBay accounts</option>}
              {accounts.map((acc) => (
                <option key={acc.id} value={acc.id}>
                  {acc.house_name || acc.username || acc.id}
                </option>
              ))}
            </select>
            {selectedAccount && (
              <span className="text-xs text-gray-500">
                eBay UserID: {selectedAccount.ebay_user_id || '—'}
              </span>
            )}
          </div>

          {/* Status */}
          {error && (
            <div className="text-sm text-red-600 border border-red-200 bg-red-50 px-3 py-2 rounded">
              {error}
            </div>
          )}
          {loading && !error && (
            <div className="text-sm text-gray-600">Loading returns…</div>
          )}

          {/* Data table */}
          <div className="flex-1 overflow-auto border rounded-lg bg-white">
            <table className="min-w-full text-xs text-left">
              <thead className="bg-gray-100 border-b">
                <tr>
                  <th className="px-2 py-1 font-semibold">Return ID</th>
                  <th className="px-2 py-1 font-semibold">Order ID</th>
                  <th className="px-2 py-1 font-semibold">Item ID</th>
                  <th className="px-2 py-1 font-semibold">Transaction ID</th>
                  <th className="px-2 py-1 font-semibold">State</th>
                  <th className="px-2 py-1 font-semibold">Type</th>
                  <th className="px-2 py-1 font-semibold">Buyer</th>
                  <th className="px-2 py-1 font-semibold">Seller</th>
                  <th className="px-2 py-1 font-semibold">Amount</th>
                  <th className="px-2 py-1 font-semibold">Created</th>
                  <th className="px-2 py-1 font-semibold">Last modified</th>
                  <th className="px-2 py-1 font-semibold">Closed</th>
                </tr>
              </thead>
              <tbody>
                {rows.length === 0 && !loading && !error && (
                  <tr>
                    <td colSpan={12} className="px-3 py-6 text-center text-gray-500 text-sm">
                      No returns found for this account.
                    </td>
                  </tr>
                )}
                {rows.map((r) => (
                  <tr key={r.return_id} className="border-b last:border-b-0 hover:bg-gray-50">
                    <td className="px-2 py-1 font-mono text-[11px]">{r.return_id}</td>
                    <td className="px-2 py-1 text-[11px]">{r.order_id ?? '—'}</td>
                    <td className="px-2 py-1 text-[11px]">{r.item_id ?? '—'}</td>
                    <td className="px-2 py-1 text-[11px]">{r.transaction_id ?? '—'}</td>
                    <td className="px-2 py-1 text-[11px]">{r.return_state ?? '—'}</td>
                    <td className="px-2 py-1 text-[11px]">{r.return_type ?? '—'}</td>
                    <td className="px-2 py-1 text-[11px]">{r.buyer_username ?? '—'}</td>
                    <td className="px-2 py-1 text-[11px]">{r.seller_username ?? '—'}</td>
                    <td className="px-2 py-1 text-[11px]">
                      {r.total_amount_value != null
                        ? `${r.total_amount_value} ${r.total_amount_currency || ''}`
                        : '—'}
                    </td>
                    <td className="px-2 py-1 text-[11px]">{r.creation_date ?? '—'}</td>
                    <td className="px-2 py-1 text-[11px]">{r.last_modified_date ?? '—'}</td>
                    <td className="px-2 py-1 text-[11px]">{r.closed_date ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
