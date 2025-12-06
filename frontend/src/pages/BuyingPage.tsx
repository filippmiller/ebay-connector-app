import { useEffect, useMemo, useState } from 'react';
import FixedHeader from '@/components/FixedHeader';
import { DataGridPage } from '@/components/DataGridPage';
import api from '@/lib/apiClient';
import { DraggableResizableDialog } from '@/components/ui/draggable-dialog';

interface BuyingStatus {
  id: number;
  code: string;
  label: string;
  sort_order: number;
  color_hex?: string | null;
  text_color_hex?: string | null;
}

interface BuyingDetail {
  id: number;
  item_id?: string | null;
  transaction_id?: string | null;
  order_line_item_id?: string | null;
  title?: string | null;
  tracking_number?: string | null;
  storage?: string | null;
  quantity_purchased?: number | null;
  buyer_id?: string | null;
  seller_id?: string | null;
  seller_location?: string | null;
  condition_display_name?: string | null;
  shipping_carrier?: string | null;
  amount_paid?: number | null;
  paid_time?: string | null;
  item_status_id?: number | null;
  item_status_label?: string | null;
  comment?: string | null;
  gallery_url?: string | null;
  picture_url?: string | null;
}

interface BuyingLogEntry {
  id: number;
  change_type?: string | null;
  old_status_id?: number | null;
  new_status_id?: number | null;
  old_status_label?: string | null;
  new_status_label?: string | null;
  old_comment?: string | null;
  new_comment?: string | null;
  changed_by_username?: string | null;
  changed_at?: string | null;
}

export default function BuyingPage() {
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<BuyingDetail | null>(null);
  const [statuses, setStatuses] = useState<BuyingStatus[]>([]);
  const [pendingStatusId, setPendingStatusId] = useState<number | null | undefined>(undefined);
  const [pendingComment, setPendingComment] = useState<string>('');
  const [saving, setSaving] = useState(false);
  const [logsOpen, setLogsOpen] = useState(false);
  const [logsLoading, setLogsLoading] = useState(false);
  const [logs, setLogs] = useState<BuyingLogEntry[]>([]);
  const [logsBuyerId, setLogsBuyerId] = useState<number | null>(null);

  // Filters State
  const [filterBuyerId, setFilterBuyerId] = useState('');
  const [filterStatusId, setFilterStatusId] = useState<string>('');
  const [filterPaidFrom, setFilterPaidFrom] = useState('');
  const [filterPaidTo, setFilterPaidTo] = useState('');
  const [filterCreatedFrom, setFilterCreatedFrom] = useState('');
  const [filterCreatedTo, setFilterCreatedTo] = useState('');
  const [filterSellerId, setFilterSellerId] = useState('');
  const [filterStorageMode, setFilterStorageMode] = useState('any'); // any, exact, section
  const [filterStorageValue, setFilterStorageValue] = useState('');
  const [filterTitle, setFilterTitle] = useState('');
  const [filterTracking, setFilterTracking] = useState('');
  const [filterItemId, setFilterItemId] = useState('');
  const [filterId, setFilterId] = useState('');

  useEffect(() => {
    const loadStatuses = async () => {
      try {
        const resp = await api.get<BuyingStatus[]>('/api/buying/statuses');
        setStatuses(resp.data || []);
      } catch (e) {
        console.error('Failed to load BUYING statuses', e);
      }
    };
    loadStatuses();
  }, []);

  useEffect(() => {
    const loadDetail = async () => {
      if (!selectedId) {
        setDetail(null);
        return;
      }
      try {
        const resp = await api.get<BuyingDetail>(`/api/buying/${selectedId}`);
        setDetail(resp.data);
        setPendingStatusId(resp.data.item_status_id);
        setPendingComment(resp.data.comment || '');
      } catch (e) {
        console.error('Failed to load BUYING detail', e);
      }
    };
    loadDetail();
  }, [selectedId]);

  const handleSave = async () => {
    if (!selectedId) return;
    setSaving(true);
    try {
      await api.patch(`/api/buying/${selectedId}/status`, {
        status_id: pendingStatusId,
        comment: pendingComment,
      });
      // Refresh detail so the panel stays in sync with DB/logs.
      const resp = await api.get<BuyingDetail>(`/api/buying/${selectedId}`);
      setDetail(resp.data);
      alert('Saved successfully!');
    } catch (e) {
      console.error('Failed to update BUYING status/comment', e);
      alert('Failed to save.');
    } finally {
      setSaving(false);
    }
  };

  const loadLogs = async (buyerId: number) => {
    setLogsBuyerId(buyerId);
    setLogsOpen(true);
    setLogsLoading(true);
    try {
      const resp = await api.get<{ logs: BuyingLogEntry[] }>(`/api/grids/buying/${buyerId}/logs`);
      setLogs(resp.data?.logs || []);
    } catch (e) {
      console.error('Failed to load BUYING logs', e);
      setLogs([]);
    } finally {
      setLogsLoading(false);
    }
  };

  const extraColumns = useMemo(() => {
    return [
      {
        colId: 'logs',
        field: 'logs',
        headerName: 'Logs',
        width: 70,
        sortable: false,
        filter: false,
        cellRenderer: (params: any) => {
          const id = params?.data?.id;
          return (
            <button
              type="button"
              className="px-2 py-0.5 text-[10px] border rounded bg-white hover:bg-gray-50"
              onClick={(e) => {
                e.stopPropagation();
                if (typeof id === 'number') {
                  void loadLogs(id);
                }
              }}
            >
              Log
            </button>
          );
        },
      },
      {
        colId: 'img',
        field: 'img',
        headerName: 'Img',
        width: 50,
        sortable: false,
        filter: false,
        cellRenderer: (params: any) => {
          // Grid usually doesn't return full details, just safe fields. 
          // If we had image in grid row we could show a thumbnail.
          return null; // Placeholder
        },
      }
    ];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const currentStatusColor = (statusId: number | null | undefined) => {
    const s = statuses.find((st) => st.id === statusId);
    return {
      backgroundColor: s?.color_hex || 'white',
      color: s?.text_color_hex || '#111827',
    };
  };

  const extraParams = useMemo(() => {
    const p: Record<string, any> = {};
    if (filterBuyerId) p.buyer_id = filterBuyerId;
    if (filterStatusId) p.status_id = filterStatusId;
    if (filterPaidFrom) p.paid_from = filterPaidFrom;
    if (filterPaidTo) p.paid_to = filterPaidTo;
    if (filterCreatedFrom) p.created_from = filterCreatedFrom;
    if (filterCreatedTo) p.created_to = filterCreatedTo;
    if (filterSellerId) p.seller_id = filterSellerId;
    if (filterStorageValue) {
      p.storage_mode = filterStorageMode;
      p.storage_value = filterStorageValue;
    }
    if (filterTitle) p.title = filterTitle;
    if (filterTracking) p.tracking_number = filterTracking;
    if (filterItemId) p.item_id = filterItemId;
    if (filterId) p.id = filterId;
    return p;
  }, [
    filterBuyerId, filterStatusId, filterPaidFrom, filterPaidTo,
    filterCreatedFrom, filterCreatedTo, filterSellerId, filterStorageMode,
    filterStorageValue, filterTitle, filterTracking, filterItemId, filterId
  ]);

  const handleClearFilters = () => {
    setFilterBuyerId('');
    setFilterStatusId('');
    setFilterPaidFrom('');
    setFilterPaidTo('');
    setFilterCreatedFrom('');
    setFilterCreatedTo('');
    setFilterSellerId('');
    setFilterStorageMode('any');
    setFilterStorageValue('');
    setFilterTitle('');
    setFilterTracking('');
    setFilterItemId('');
    setFilterId('');
  };

  return (
    <div className="h-screen flex flex-col bg-gray-50 text-xs">
      <FixedHeader />
      <div className="pt-14 flex-1 flex flex-col overflow-hidden">

        {/* Filters Section */}
        <div className="p-2 bg-white border-b shadow-sm space-y-2">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-2">
            <div className="flex items-center gap-2">
              <label className="w-16 text-right font-medium">BuyerID:</label>
              <input className="border rounded px-2 py-1 flex-1" placeholder="< Select ALL >" value={filterBuyerId} onChange={e => setFilterBuyerId(e.target.value)} />
            </div>
            <div className="flex items-center gap-2">
              <label className="w-16 text-right font-medium">Status:</label>
              <select className="border rounded px-2 py-1 flex-1" value={filterStatusId} onChange={e => setFilterStatusId(e.target.value)}>
                <option value="">&lt; Select ALL &gt;</option>
                {statuses.map(s => <option key={s.id} value={s.id}>{s.label}</option>)}
              </select>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-2">
            <div className="flex items-center gap-2">
              <label className="w-16 text-right font-medium">Paid Date:</label>
              <input type="date" className="border rounded px-1 py-1 w-28" value={filterPaidFrom} onChange={e => setFilterPaidFrom(e.target.value)} />
              <span>-</span>
              <input type="date" className="border rounded px-1 py-1 w-28" value={filterPaidTo} onChange={e => setFilterPaidTo(e.target.value)} />
            </div>
            <div className="flex items-center gap-2">
              <label className="w-16 text-right font-medium">RecCreated:</label>
              <input type="date" className="border rounded px-1 py-1 w-28" value={filterCreatedFrom} onChange={e => setFilterCreatedFrom(e.target.value)} />
              <span>-</span>
              <input type="date" className="border rounded px-1 py-1 w-28" value={filterCreatedTo} onChange={e => setFilterCreatedTo(e.target.value)} />
            </div>
            <div className="flex items-center gap-2">
              <label className="w-16 text-right font-medium">SellerID:</label>
              <input className="border rounded px-2 py-1 flex-1" placeholder="SellerID..." value={filterSellerId} onChange={e => setFilterSellerId(e.target.value)} />
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-2">
            <div className="col-span-1 md:col-span-2 flex items-center gap-2 border rounded p-1">
              <span className="font-medium px-2">Storage</span>
              <div className="flex flex-col gap-1 flex-1">
                <div className="flex items-center gap-2">
                  <input type="radio" name="storage_mode" id="st_any" checked={filterStorageMode === 'any'} onChange={() => setFilterStorageMode('any')} />
                  <label htmlFor="st_any">Any Matches:</label>
                </div>
                <div className="flex items-center gap-2">
                  <input type="radio" name="storage_mode" id="st_exact" checked={filterStorageMode === 'exact'} onChange={() => setFilterStorageMode('exact')} />
                  <label htmlFor="st_exact">Exact Matching:</label>
                </div>
                <div className="flex items-center gap-2">
                  <input type="radio" name="storage_mode" id="st_section" checked={filterStorageMode === 'section'} onChange={() => setFilterStorageMode('section')} />
                  <label htmlFor="st_section">Use Section:</label>
                </div>
              </div>
              <div className="flex flex-col gap-1 w-1/2">
                <input className="border rounded px-2 py-1" placeholder="Storage..." value={filterStorageValue} onChange={e => setFilterStorageValue(e.target.value)} />
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-2">
            <div className="flex flex-col">
              <label className="font-medium">Title:</label>
              <input className="border rounded px-2 py-1" placeholder="Title... (enter for search)" value={filterTitle} onChange={e => setFilterTitle(e.target.value)} />
            </div>
            <div className="flex flex-col">
              <label className="font-medium">Tracking Number:</label>
              <input className="border rounded px-2 py-1" placeholder="TrackingNumber... (enter for search)" value={filterTracking} onChange={e => setFilterTracking(e.target.value)} />
            </div>
            <div className="flex flex-col">
              <label className="font-medium">ItemID:</label>
              <input className="border rounded px-2 py-1" placeholder="ItemID... (enter for search)" value={filterItemId} onChange={e => setFilterItemId(e.target.value)} />
            </div>
            <div className="flex flex-col">
              <label className="font-medium">ID:</label>
              <input className="border rounded px-2 py-1" placeholder="ID... (enter for search)" value={filterId} onChange={e => setFilterId(e.target.value)} />
            </div>
          </div>

          <div className="flex gap-2 justify-start mt-2">
            <button onClick={handleClearFilters} className="px-4 py-1 bg-red-100 border border-red-300 text-red-700 rounded hover:bg-red-200 flex items-center gap-1 font-bold">
              <span>✖</span> Clear
            </button>
            <button className="px-4 py-1 bg-gray-100 border border-gray-300 text-gray-700 rounded hover:bg-gray-200 flex items-center gap-1 font-bold">
              <span>💾</span> Save
            </button>
          </div>
        </div>


        {/* Grid Section */}
        <div className="flex-1 min-h-0">
          <DataGridPage
            gridKey="buying"
            hideTitle
            extraColumns={extraColumns}
            extraParams={extraParams}
            // Simple row click: rows are plain objects with an "id" field from the grid backend
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            onRowClick={(row: any) => {
              if (row && typeof row.id === 'number') {
                setSelectedId(row.id);
              }
            }}
          />
        </div>

        {/* Detail Bottom Panel */}
        {detail && (
          <div className="h-64 border-t-4 border-red-500 bg-white p-2 flex gap-4 shadow-inner text-sm overflow-hidden">

            {/* Left: Image */}
            <div className="w-56 h-full flex-shrink-0 bg-gray-100 border flex items-center justify-center relative group cursor-pointer">
              {detail.gallery_url || detail.picture_url ? (
                <img src={detail.gallery_url || detail.picture_url || ''} alt="Item" className="max-w-full max-h-full object-contain" />
              ) : (
                <div className="text-gray-400">No Image</div>
              )}
              <div className="absolute inset-0 bg-black bg-opacity-0 group-hover:bg-opacity-20 flex items-center justify-center transition-all">
                <span className="text-white opacity-0 group-hover:opacity-100 font-bold drop-shadow-md">Click to enlarge</span>
              </div>
            </div>

            {/* Middle: Details */}
            <div className="flex-1 grid grid-cols-2 gap-x-8 gap-y-1 overflow-auto">
              <div className="text-center col-span-2 font-bold text-blue-700 mb-2 border-b uppercase">Detailed Information for Buying</div>

              {/* Column 1 */}
              <div className="space-y-1">
                <div className="flex gap-1">
                  <span className="font-bold text-right w-24">Seller:</span>
                  <span className="text-purple-700 truncate">{detail.seller_id}</span>
                </div>
                <div className="flex gap-1">
                  <span className="font-bold text-right w-24">TrackingNumber:</span>
                  <span className="text-blue-600 truncate">{detail.tracking_number}</span>
                </div>
                <div className="flex gap-1">
                  <span className="font-bold text-right w-24">Title:</span>
                  <span className="font-bold text-blue-900 truncate" title={detail.title || ''}>{detail.title}</span>
                </div>
                <div className="flex gap-1">
                  <span className="font-bold text-right w-24 text-red-600">ItemID:</span>
                  <span className="text-red-600">{detail.item_id}</span>
                </div>
                <div className="flex gap-1">
                  <span className="font-bold text-right w-24">TransactionID:</span>
                  <span>{detail.transaction_id || '0'}</span>
                </div>
                <div className="flex gap-1">
                  <span className="font-bold text-right w-24 text-green-700">Storage:</span>
                  <span className="font-bold text-green-700">{detail.storage}</span>
                </div>
                <div className="flex gap-1">
                  <span className="font-bold text-right w-24">Quantity:</span>
                  <span className="font-bold">{detail.quantity_purchased}</span>
                </div>
                <div className="flex gap-1">
                  <span className="font-bold text-right w-24">BuyerID:</span>
                  <span>{detail.buyer_id}</span>
                </div>
              </div>

              {/* Column 2 */}
              <div className="space-y-1">
                <div className="flex gap-1">
                  <span className="font-bold text-right w-32">Seller location:</span>
                  <span>{detail.seller_location}</span>
                </div>
                <div className="flex gap-1">
                  <span className="font-bold text-right w-32">ItemCondition:</span>
                  <span>{detail.condition_display_name}</span>
                </div>
                <div className="flex gap-1">
                  <span className="font-bold text-right w-32">ShippingCarrier:</span>
                  <span>{detail.shipping_carrier}</span>
                </div>
                <div className="flex gap-1">
                  <span className="font-bold text-right w-32">AmountPaid:</span>
                  <span>{detail.amount_paid ? `$${detail.amount_paid.toFixed(2)}` : ''}</span>
                </div>
                <div className="flex gap-1">
                  <span className="font-bold text-right w-32">PaidOnDate:</span>
                  <span>{detail.paid_time ? new Date(detail.paid_time).toLocaleDateString() : ''}</span>
                </div>
              </div>
            </div>

            {/* Right: Status & Comment */}
            <div className="w-64 flex flex-col gap-2 border-l pl-2">
              <div>
                <label className="font-bold block text-xs mb-1">Status:</label>
                <select
                  className="border rounded px-2 py-1 text-xs w-full font-medium"
                  value={pendingStatusId ?? ''}
                  onChange={(e) => {
                    const v = e.target.value;
                    setPendingStatusId(v === '' ? null : Number(v));
                  }}
                  style={currentStatusColor(pendingStatusId)}
                >
                  <option value="">(no status)</option>
                  {statuses.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex-1 flex flex-col">
                <label className="font-bold block text-xs mb-1">Comment:</label>
                <textarea
                  className="border rounded px-2 py-1 text-xs w-full flex-1 resize-none bg-yellow-50"
                  value={pendingComment}
                  onChange={(e) => setPendingComment(e.target.value)}
                />
              </div>
              <div>
                <button
                  className="w-full px-3 py-1 rounded bg-gray-200 border border-gray-400 text-gray-800 text-xs hover:bg-gray-300 flex items-center justify-center gap-1 font-bold"
                  onClick={handleSave}
                  disabled={saving || !selectedId}
                >
                  <span>💾</span> {saving ? 'Saving…' : 'Save'}
                </button>
              </div>

            </div>
          </div>
        )}
      </div>

      <DraggableResizableDialog
        open={logsOpen}
        onOpenChange={(open) => setLogsOpen(open)}
        title={`Logs ${logsBuyerId ? `for #${logsBuyerId}` : ''}`}
        defaultWidth="60%"
        defaultHeight="60%"
      >
        <div className="h-full p-3 text-sm overflow-auto">
          {logsLoading ? (
            <div className="text-gray-600">Loading logs…</div>
          ) : logs.length === 0 ? (
            <div className="text-gray-600">No logs found.</div>
          ) : (
            <div className="space-y-2">
              {logs.map((log) => (
                <div key={log.id} className="border rounded p-2 bg-gray-50">
                  <div className="flex flex-wrap gap-2 text-xs text-gray-600">
                    <span>ID: {log.id}</span>
                    <span>Type: {log.change_type || '-'}</span>
                    <span>Changed by: {log.changed_by_username || '-'}</span>
                    <span>
                      At:{' '}
                      {log.changed_at ? new Date(log.changed_at).toLocaleString() : '-'}
                    </span>
                  </div>
                  <div className="mt-1 text-xs">
                    <div>
                      Status: {log.old_status_label || '(none)'} → {log.new_status_label || '(none)'}
                    </div>
                    <div className="mt-1">
                      Comment: {(log.old_comment || '').trim() || '—'} → {(log.new_comment || '').trim() || '—'}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </DraggableResizableDialog>
    </div>
  );
}
