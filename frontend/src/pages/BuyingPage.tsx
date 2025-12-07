import { useEffect, useMemo, useState } from 'react';
import FixedHeader from '@/components/FixedHeader';
import { DataGridPage } from '@/components/DataGridPage';
import api from '@/lib/apiClient';
import { DraggableResizableDialog } from '@/components/ui/draggable-dialog';
import { ModelEditor } from '@/components/buying/ModelEditor';

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
        const resp = await api.get<BuyingStatus[]>('/buying/statuses');
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
        const resp = await api.get<BuyingDetail>(`/buying/${selectedId}`);
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
      await api.patch(`/buying/${selectedId}/status`, {
        status_id: pendingStatusId,
        comment: pendingComment,
      });
      // Refresh detail so the panel stays in sync with DB/logs.
      const resp = await api.get<BuyingDetail>(`/buying/${selectedId}`);
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
      const resp = await api.get<{ logs: BuyingLogEntry[] }>(`/grids/buying/${buyerId}/logs`);
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
        cellRenderer: () => {
          // Grid usually doesn't return full details, just safe fields. 
          // If we had image in grid row we could show a thumbnail.
          return null; // Placeholder
        },
      },
      {
        colId: 'model',
        field: 'model', // Matches backend field
        headerName: 'Model',
        width: 200,
        sortable: true,
        filter: true,
        editable: true,
        cellEditor: ModelEditor,
        cellEditorPopup: true,
        cellEditorPopupPosition: 'under' as const, // Show under the cell
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
    <div className="h-screen flex flex-col bg-gray-50">
      <FixedHeader />
      <div className="pt-16 flex-1 px-4 py-4 overflow-hidden flex flex-col gap-4">

        {/* Header Section - Like SKU Page */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold">Buying</h1>
            <p className="text-xs text-gray-500">
              Track and manage buying transactions
            </p>
          </div>
        </div>

        <div className="flex-1 min-h-0 flex flex-col gap-3">
          {/* Container 2: Ultra-Dense Filter Bar (2 lines max) */}
          <div className="p-1.5 bg-white border rounded shadow-sm">
            {/* Row 1 */}
            <div className="flex items-center gap-1.5 mb-1">
              <button
                onClick={handleClearFilters}
                className="text-red-600 text-[10px] hover:bg-red-50 px-2 py-1 rounded whitespace-nowrap"
              >
                ✖ Clear
              </button>
              <input
                className="border rounded px-2 py-1 h-8 text-xs w-24"
                placeholder="BuyerID"
                value={filterBuyerId}
                onChange={e => setFilterBuyerId(e.target.value)}
              />
              <select
                className="border rounded px-2 py-1 h-8 text-xs w-32"
                value={filterStatusId}
                onChange={e => setFilterStatusId(e.target.value)}
              >
                <option value="">Status</option>
                {statuses.map(s => <option key={s.id} value={s.id}>{s.label}</option>)}
              </select>
              <input
                type="date"
                className="border rounded px-2 py-1 h-8 text-xs w-32"
                value={filterPaidFrom}
                onChange={e => setFilterPaidFrom(e.target.value)}
                title="Paid From"
              />
              <span className="text-gray-400">-</span>
              <input
                type="date"
                className="border rounded px-2 py-1 h-8 text-xs w-32"
                value={filterPaidTo}
                onChange={e => setFilterPaidTo(e.target.value)}
                title="Paid To"
              />
              <input
                type="date"
                className="border rounded px-2 py-1 h-8 text-xs w-32"
                value={filterCreatedFrom}
                onChange={e => setFilterCreatedFrom(e.target.value)}
                title="Created From"
              />
              <span className="text-gray-400">-</span>
              <input
                type="date"
                className="border rounded px-2 py-1 h-8 text-xs w-32"
                value={filterCreatedTo}
                onChange={e => setFilterCreatedTo(e.target.value)}
                title="Created To"
              />
              <input
                className="border rounded px-2 py-1 h-8 text-xs w-24"
                placeholder="SellerID"
                value={filterSellerId}
                onChange={e => setFilterSellerId(e.target.value)}
              />

              {/* Storage filters */}
              <div className="flex items-center gap-1 border rounded px-2 py-1 h-8 bg-gray-50">
                <label className="flex items-center gap-1 text-xs cursor-pointer">
                  <input type="radio" name="storage_mode" checked={filterStorageMode === 'any'} onChange={() => setFilterStorageMode('any')} className="w-3 h-3" />
                  <span>Any</span>
                </label>
                <label className="flex items-center gap-1 text-xs cursor-pointer">
                  <input type="radio" name="storage_mode" checked={filterStorageMode === 'exact'} onChange={() => setFilterStorageMode('exact')} className="w-3 h-3" />
                  <span>Exact</span>
                </label>
                <label className="flex items-center gap-1 text-xs cursor-pointer">
                  <input type="radio" name="storage_mode" checked={filterStorageMode === 'section'} onChange={() => setFilterStorageMode('section')} className="w-3 h-3" />
                  <span>Sect</span>
                </label>
              </div>
              <input
                className="border rounded px-2 py-1 h-8 text-xs w-28"
                placeholder="Storage"
                value={filterStorageValue}
                onChange={e => setFilterStorageValue(e.target.value)}
              />
              <input
                className="border rounded px-2 py-1 h-8 text-xs flex-1"
                placeholder="Title"
                value={filterTitle}
                onChange={e => setFilterTitle(e.target.value)}
              />
              <input
                className="border rounded px-2 py-1 h-8 text-xs w-32"
                placeholder="Tracking"
                value={filterTracking}
                onChange={e => setFilterTracking(e.target.value)}
              />
              <input
                className="border rounded px-2 py-1 h-8 text-xs w-28"
                placeholder="ItemID"
                value={filterItemId}
                onChange={e => setFilterItemId(e.target.value)}
              />
              <input
                className="border rounded px-2 py-1 h-8 text-xs w-20"
                placeholder="ID"
                value={filterId}
                onChange={e => setFilterId(e.target.value)}
              />
            </div>
          </div>

          {/* Grid Section */}
          <div className="flex-[2] min-h-0 border rounded-lg bg-white flex flex-col">
            <div className="flex items-center justify-between px-3 py-2 border-b bg-gray-50 text-xs">
              <div className="font-semibold">Buying grid</div>
              <div className="text-gray-500">Click a row to see details below.</div>
            </div>
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
          </div>

          {/* Detail Panel - Like SKU Page */}
          {detail ? (
            <div className="flex-[1] min-h-[200px] border rounded-lg bg-white flex flex-col overflow-hidden">
              <div className="bg-blue-100 px-3 py-1 border-b border-blue-200 flex justify-between items-center">
                <span className="text-xs font-bold text-blue-800 uppercase">Detailed Information for Buying</span>
              </div>

              <div className="flex-1 p-3 flex gap-4 text-xs overflow-auto">
                {/* Left: Image */}
                <div className="w-48 h-32 bg-gray-100 border flex items-center justify-center text-gray-400 shrink-0">
                  {detail.gallery_url || detail.picture_url ? (
                    <img src={detail.gallery_url || detail.picture_url || ''} alt="Item" className="max-w-full max-h-full object-contain" />
                  ) : (
                    <div className="text-center p-2">
                      <span className="block text-xs">Click to enlarge</span>
                      <span className="text-[10px]">(No Image)</span>
                    </div>
                  )}
                </div>

                {/* Middle: Details Column 1 */}
                <div className="flex-1 space-y-1 min-w-[200px]">
                  <div className="flex gap-2">
                    <span className="font-bold text-gray-700 w-24">Seller:</span>
                    <span className="text-purple-700 truncate">{detail.seller_id}</span>
                  </div>
                  <div className="flex gap-2">
                    <span className="font-bold text-gray-700 w-24">Tracking:</span>
                    <span className="text-blue-600 truncate">{detail.tracking_number}</span>
                  </div>
                  <div className="flex gap-2">
                    <span className="font-bold text-gray-700 w-24">Title:</span>
                    <span className="font-bold text-blue-900 truncate" title={detail.title || ''}>{detail.title}</span>
                  </div>
                  <div className="flex gap-2">
                    <span className="font-bold text-gray-700 w-24 text-red-600">ItemID:</span>
                    <span className="text-red-600">{detail.item_id}</span>
                  </div>
                  <div className="flex gap-2">
                    <span className="font-bold text-gray-700 w-24">Transaction:</span>
                    <span>{detail.transaction_id || '0'}</span>
                  </div>
                  <div className="flex gap-2">
                    <span className="font-bold text-gray-700 w-24 text-green-700">Storage:</span>
                    <span className="font-bold text-green-700">{detail.storage}</span>
                  </div>
                  <div className="flex gap-2">
                    <span className="font-bold text-gray-700 w-24">Quantity:</span>
                    <span className="font-bold">{detail.quantity_purchased}</span>
                  </div>
                  <div className="flex gap-2">
                    <span className="font-bold text-gray-700 w-24">BuyerID:</span>
                    <span>{detail.buyer_id}</span>
                  </div>
                </div>

                {/* Right Column: More Details */}
                <div className="flex-1 space-y-1 min-w-[200px]">
                  <div className="flex gap-2">
                    <span className="font-bold text-gray-700 w-28">Location:</span>
                    <span>{detail.seller_location}</span>
                  </div>
                  <div className="flex gap-2">
                    <span className="font-bold text-gray-700 w-28">Condition:</span>
                    <span>{detail.condition_display_name}</span>
                  </div>
                  <div className="flex gap-2">
                    <span className="font-bold text-gray-700 w-28">Carrier:</span>
                    <span>{detail.shipping_carrier}</span>
                  </div>
                  <div className="flex gap-2">
                    <span className="font-bold text-gray-700 w-28">Paid:</span>
                    <span>{detail.amount_paid ? `$${detail.amount_paid.toFixed(2)}` : ''}</span>
                  </div>
                  <div className="flex gap-2">
                    <span className="font-bold text-gray-700 w-28">Paid Date:</span>
                    <span>{detail.paid_time ? new Date(detail.paid_time).toLocaleDateString() : ''}</span>
                  </div>
                </div>

                {/* Far Right: Status & Comment */}
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
            </div>
          ) : (
            <div className="flex-[1] min-h-[160px] border rounded-lg bg-white flex items-center justify-center text-xs text-gray-500">
              Select a row in the Buying grid to see details.
            </div>
          )}
        </div>
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

