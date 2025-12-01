import { useEffect, useMemo, useState } from 'react';
import FixedHeader from '@/components/FixedHeader';
import { ebayApi, EbayReturnRow, EbayReturnDetailResponse, EbayReturnMessage } from '@/api/ebay';

interface EbayAccountSummary {
  id: string;
  username?: string | null;
  ebay_user_id?: string | null;
  house_name?: string | null;
}

const ALL_COLUMNS = [
  { key: 'return_id', label: 'Return ID' },
  { key: 'order_id', label: 'Order ID' },
  { key: 'item_id', label: 'Item ID' },
  { key: 'transaction_id', label: 'Transaction ID' },
  { key: 'return_state', label: 'State' },
  { key: 'return_type', label: 'Type' },
  { key: 'buyer_username', label: 'Buyer' },
  { key: 'seller_username', label: 'Seller' },
  { key: 'amount', label: 'Amount' },
  { key: 'creation_date', label: 'Created' },
  { key: 'last_modified_date', label: 'Last modified' },
  { key: 'closed_date', label: 'Closed' },
] as const;

type ColumnKey = (typeof ALL_COLUMNS)[number]['key'];

export default function ReturnsPage() {
  const [accounts, setAccounts] = useState<EbayAccountSummary[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState<string | null>(null);
  const [rows, setRows] = useState<EbayReturnRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [showColumnsPanel, setShowColumnsPanel] = useState(false);
  const [visibleColumns, setVisibleColumns] = useState<ColumnKey[]>(
    ALL_COLUMNS.map((c) => c.key)
  );

  // Detail modal state
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [detailRow, setDetailRow] = useState<EbayReturnRow | null>(null);
  const [detailMessages, setDetailMessages] = useState<EbayReturnMessage[]>([]);
  const [detailRaw, setDetailRaw] = useState<any | null>(null);

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
        const resp = await ebayApi.getReturns({ accountId: selectedAccountId, limit: 500, offset: 0 });
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

  const searchLower = search.trim().toLowerCase();
  const filteredRows = useMemo(() => {
    if (!searchLower) return rows;
    return rows.filter((r) => {
      const values: string[] = [];
      Object.values(r).forEach((v) => {
        if (v === null || v === undefined) return;
        values.push(String(v));
      });
      return values.join(' ').toLowerCase().includes(searchLower);
    });
  }, [rows, searchLower]);

  const handleOpenDetail = async (row: EbayReturnRow) => {
    if (!selectedAccountId) return;
    setDetailRow(row);
    setDetailOpen(true);
    setDetailLoading(true);
    setDetailError(null);
    setDetailMessages([]);
    setDetailRaw(null);
    try {
      const resp: EbayReturnDetailResponse = await ebayApi.getReturnDetail({
        accountId: selectedAccountId,
        returnId: row.return_id,
      });
      setDetailMessages(resp.messages || []);
      setDetailRaw(resp.raw ?? null);
    } catch (e: any) {
      const message = e?.response?.data?.detail || e?.message || 'Failed to load return details';
      setDetailError(message);
    } finally {
      setDetailLoading(false);
    }
  };

  const toggleColumn = (key: ColumnKey) => {
    setVisibleColumns((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]
    );
  };

  const isColVisible = (key: ColumnKey) => visibleColumns.includes(key);

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

          {/* Toolbar: search + columns, Transactions-style */}
          <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
            <div className="flex items-center gap-3">
              <span className="text-xs text-gray-500">
                {filteredRows.length} returns
              </span>
            </div>
            <div className="flex items-center gap-2">
              <input
                className="px-2 py-1 border rounded-md text-xs bg-white placeholder:text-gray-400 w-64"
                placeholder="Search all columns"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
              <div className="relative">
                <button
                  type="button"
                  className="px-3 py-2 border rounded-md text-xs bg-white hover:bg-gray-50 shadow-sm"
                  onClick={() => setShowColumnsPanel((v) => !v)}
                >
                  Columns
                </button>
                {showColumnsPanel && (
                  <div className="absolute right-0 mt-1 w-56 bg-white border rounded-md shadow-lg z-20 max-h-72 overflow-auto text-xs">
                    <div className="px-3 py-2 border-b flex items-center justify-between">
                      <span className="font-semibold text-[11px] uppercase tracking-wide text-gray-600">
                        Visible columns
                      </span>
                      <button
                        type="button"
                        className="text-[11px] text-blue-600 hover:underline"
                        onClick={() =>
                          setVisibleColumns((prev) =>
                            prev.length === ALL_COLUMNS.length
                              ? ([] as ColumnKey[])
                              : (ALL_COLUMNS.map((c) => c.key) as ColumnKey[])
                          )
                        }
                      >
                        {visibleColumns.length === ALL_COLUMNS.length ? 'Hide all' : 'Show all'}
                      </button>
                    </div>
                    <div className="px-3 py-2 space-y-1">
                      {ALL_COLUMNS.map((col) => (
                        <label key={col.key} className="flex items-center gap-2 cursor-pointer">
                          <input
                            type="checkbox"
                            className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                            checked={isColVisible(col.key)}
                            onChange={() => toggleColumn(col.key)}
                          />
                          <span>{col.label}</span>
                        </label>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
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
                  {isColVisible('return_id') && (
                    <th className="px-2 py-1 font-semibold">Return ID</th>
                  )}
                  {isColVisible('order_id') && (
                    <th className="px-2 py-1 font-semibold">Order ID</th>
                  )}
                  {isColVisible('item_id') && (
                    <th className="px-2 py-1 font-semibold">Item ID</th>
                  )}
                  {isColVisible('transaction_id') && (
                    <th className="px-2 py-1 font-semibold">Transaction ID</th>
                  )}
                  {isColVisible('return_state') && (
                    <th className="px-2 py-1 font-semibold">State</th>
                  )}
                  {isColVisible('return_type') && (
                    <th className="px-2 py-1 font-semibold">Type</th>
                  )}
                  {isColVisible('buyer_username') && (
                    <th className="px-2 py-1 font-semibold">Buyer</th>
                  )}
                  {isColVisible('seller_username') && (
                    <th className="px-2 py-1 font-semibold">Seller</th>
                  )}
                  {isColVisible('amount') && (
                    <th className="px-2 py-1 font-semibold">Amount</th>
                  )}
                  {isColVisible('creation_date') && (
                    <th className="px-2 py-1 font-semibold">Created</th>
                  )}
                  {isColVisible('last_modified_date') && (
                    <th className="px-2 py-1 font-semibold">Last modified</th>
                  )}
                  {isColVisible('closed_date') && (
                    <th className="px-2 py-1 font-semibold">Closed</th>
                  )}
                  <th className="px-2 py-1 font-semibold">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredRows.length === 0 && !loading && !error && (
                  <tr>
                    <td colSpan={13} className="px-3 py-6 text-center text-gray-500 text-sm">
                      No returns found for this account.
                    </td>
                  </tr>
                )}
                {filteredRows.map((r) => (
                  <tr key={r.return_id} className="border-b last:border-b-0 hover:bg-gray-50">
                    {isColVisible('return_id') && (
                      <td className="px-2 py-1 font-mono text-[11px]">{r.return_id}</td>
                    )}
                    {isColVisible('order_id') && (
                      <td className="px-2 py-1 text-[11px]">{r.order_id ?? '—'}</td>
                    )}
                    {isColVisible('item_id') && (
                      <td className="px-2 py-1 text-[11px]">{r.item_id ?? '—'}</td>
                    )}
                    {isColVisible('transaction_id') && (
                      <td className="px-2 py-1 text-[11px]">{r.transaction_id ?? '—'}</td>
                    )}
                    {isColVisible('return_state') && (
                      <td className="px-2 py-1 text-[11px]">{r.return_state ?? '—'}</td>
                    )}
                    {isColVisible('return_type') && (
                      <td className="px-2 py-1 text-[11px]">{r.return_type ?? '—'}</td>
                    )}
                    {isColVisible('buyer_username') && (
                      <td className="px-2 py-1 text-[11px]">{r.buyer_username ?? '—'}</td>
                    )}
                    {isColVisible('seller_username') && (
                      <td className="px-2 py-1 text-[11px]">{r.seller_username ?? '—'}</td>
                    )}
                    {isColVisible('amount') && (
                      <td className="px-2 py-1 text-[11px]">
                        {r.total_amount_value != null
                          ? `${r.total_amount_value} ${r.total_amount_currency || ''}`
                          : '—'}
                      </td>
                    )}
                    {isColVisible('creation_date') && (
                      <td className="px-2 py-1 text-[11px]">{r.creation_date ?? '—'}</td>
                    )}
                    {isColVisible('last_modified_date') && (
                      <td className="px-2 py-1 text-[11px]">{r.last_modified_date ?? '—'}</td>
                    )}
                    {isColVisible('closed_date') && (
                      <td className="px-2 py-1 text-[11px]">{r.closed_date ?? '—'}</td>
                    )}
                    <td className="px-2 py-1 text-[11px]">
                      <button
                        type="button"
                        className="px-2 py-1 border rounded-md text-[11px] bg-white hover:bg-gray-50"
                        onClick={() => handleOpenDetail(r)}
                      >
                        Details
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Detail modal */}
      {detailOpen && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-lg w-full max-w-4xl max-h-[80vh] flex flex-col">
            <div className="px-4 py-2 border-b flex items-center justify-between">
              <div className="text-sm font-semibold">
                Return details{detailRow ? ` – ${detailRow.return_id}` : ''}
              </div>
              <button
                type="button"
                className="text-xs text-gray-500 hover:text-gray-800"
                onClick={() => {
                  setDetailOpen(false);
                  setDetailError(null);
                }}
              >
                Close
              </button>
            </div>
            <div className="flex-1 overflow-auto p-4 text-xs space-y-4">
              {detailLoading && (
                <div className="text-gray-600">Loading details…</div>
              )}
              {detailError && (
                <div className="text-red-600 border border-red-200 bg-red-50 px-3 py-2 rounded">
                  {detailError}
                </div>
              )}
              {detailRow && !detailLoading && !detailError && (
                <>
                  <div>
                    <h2 className="font-semibold mb-1">Summary</h2>
                    <div className="grid grid-cols-2 md:grid-cols-3 gap-y-1 gap-x-4">
                      <div>
                        <span className="font-medium">Return ID:</span> {detailRow.return_id}
                      </div>
                      <div>
                        <span className="font-medium">Order ID:</span> {detailRow.order_id ?? '—'}
                      </div>
                      <div>
                        <span className="font-medium">Item ID:</span> {detailRow.item_id ?? '—'}
                      </div>
                      <div>
                        <span className="font-medium">Transaction:</span> {detailRow.transaction_id ?? '—'}
                      </div>
                      <div>
                        <span className="font-medium">State:</span> {detailRow.return_state ?? '—'}
                      </div>
                      <div>
                        <span className="font-medium">Type:</span> {detailRow.return_type ?? '—'}
                      </div>
                      <div>
                        <span className="font-medium">Buyer:</span> {detailRow.buyer_username ?? '—'}
                      </div>
                      <div>
                        <span className="font-medium">Seller:</span> {detailRow.seller_username ?? '—'}
                      </div>
                      <div>
                        <span className="font-medium">Amount:</span>{' '}
                        {detailRow.total_amount_value != null
                          ? `${detailRow.total_amount_value} ${detailRow.total_amount_currency || ''}`
                          : '—'}
                      </div>
                      <div>
                        <span className="font-medium">Created:</span> {detailRow.creation_date ?? '—'}
                      </div>
                      <div>
                        <span className="font-medium">Last modified:</span>{' '}
                        {detailRow.last_modified_date ?? '—'}
                      </div>
                      <div>
                        <span className="font-medium">Closed:</span> {detailRow.closed_date ?? '—'}
                      </div>
                      <div className="col-span-2 md:col-span-3">
                        <span className="font-medium">Reason:</span> {detailRow.reason ?? '—'}
                      </div>
                    </div>
                  </div>

                  <div>
                    <h2 className="font-semibold mb-1">Messages</h2>
                    {detailMessages.length === 0 ? (
                      <div className="text-gray-500">No messages found for this return.</div>
                    ) : (
                      <ul className="space-y-2">
                        {detailMessages.map((m, idx) => (
                          <li
                            key={idx}
                            className="border rounded-md px-3 py-2 bg-gray-50 flex flex-col gap-1"
                          >
                            <div className="flex flex-wrap items-center gap-2 text-[11px] text-gray-600">
                              <span className="font-semibold">{m.author || 'Unknown'}</span>
                              {m.activity && <span>• {m.activity}</span>}
                              {m.created_at && <span>• {m.created_at}</span>}
                              {m.from_state && m.to_state && (
                                <span>
                                  • {m.from_state} → {m.to_state}
                                </span>
                              )}
                            </div>
                            <div className="text-[12px] whitespace-pre-wrap">{m.text}</div>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>

                  {detailRaw && (
                    <div>
                      <h2 className="font-semibold mb-1">Raw payload (debug)</h2>
                      <pre className="bg-gray-900 text-gray-100 p-3 rounded text-[11px] overflow-auto max-h-64">
                        {JSON.stringify(detailRaw, null, 2)}
                      </pre>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
