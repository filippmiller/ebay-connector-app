import { useEffect, useMemo, useState } from 'react';
import FixedHeader from '@/components/FixedHeader';
import { DataGridPage } from '@/components/DataGridPage';
import api from '@/lib/apiClient';
import { DraggableResizableDialog } from '@/components/ui/draggable-dialog';
import { ModelEditor } from '@/components/buying/ModelEditor';
import { useAuth } from '@/auth/AuthContext';

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
  picture_url0?: string | null;
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
  const { user } = useAuth();
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
  const [filterSellerId, setFilterSellerId] = useState('');
  const [filterStorageMode, setFilterStorageMode] = useState('any'); // any, exact, section
  const [filterStorageValue, setFilterStorageValue] = useState('');
  const [filterTitle, setFilterTitle] = useState('');
  const [filterTracking, setFilterTracking] = useState('');
  const [filterItemId, setFilterItemId] = useState('');
  const [filterId, setFilterId] = useState('');

  // Resizable panel state (will be fully used when resizable divider is implemented)
  const [gridHeight, _setGridHeight] = useState(60); // Grid takes 60% by default

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
      // Format comment with [timestamp] username: text
      const timestamp = new Date().toISOString().replace('T', ' ').substring(0, 19);
      const username = user?.username || 'Unknown';
      const formattedComment = `[${timestamp}] ${username}: ${pendingComment}`;

      await api.patch(`/buying/${selectedId}/status`, {
        status_id: pendingStatusId,
        comment: formattedComment,
      });

      // Refresh and keep formatted comment visible
      const resp = await api.get<BuyingDetail>(`/buying/${selectedId}`);
      setDetail(resp.data);
      setPendingComment(resp.data.comment || ''); // Keep formatted comment showing

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
    filterSellerId, filterStorageMode, filterStorageValue, filterTitle,
    filterTracking, filterItemId, filterId
  ]);

  const handleClearFilters = () => {
    setFilterBuyerId('');
    setFilterStatusId('');
    setFilterPaidFrom('');
    setFilterPaidTo('');
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
      <div className="pt-16 flex-1 overflow-hidden flex flex-col">

        <div className="flex-1 min-h-0 flex flex-col gap-1">
          {/* Container 2: Ultra-Dense Filter Bar (2 lines max) */}
          <div className="p-1 bg-white border rounded shadow-sm">
            {/* Single Ultra-Compact Filter Row */}
            <div className="flex items-center gap-1">
              <button
                onClick={handleClearFilters}
                className="text-red-600 text-[9px] hover:bg-red-50 px-1.5 py-0.5 rounded whitespace-nowrap"
              >
                ✖ Clear
              </button>
              <input
                className="border rounded px-1.5 py-0.5 h-7 text-[10px] w-20"
                placeholder="BuyerID"
                value={filterBuyerId}
                onChange={e => setFilterBuyerId(e.target.value)}
              />
              <select
                className="border rounded px-1 py-0.5 h-7 text-[10px] w-24"
                value={filterStatusId}
                onChange={e => setFilterStatusId(e.target.value)}
              >
                <option value="">Status</option>
                {statuses.map(s => <option key={s.id} value={s.id}>{s.label}</option>)}
              </select>
              <span className="text-[10px] text-gray-500 font-semibold">Paid:</span>
              <input
                type="date"
                className="border rounded px-1 py-0.5 h-7 text-[10px] w-28"
                value={filterPaidFrom}
                onChange={e => setFilterPaidFrom(e.target.value)}
                title="Paid From"
                placeholder="From"
              />
              <span className="text-[10px] text-gray-400">-</span>
              <input
                type="date"
                className="border rounded px-1 py-0.5 h-7 text-[10px] w-28"
                value={filterPaidTo}
                onChange={e => setFilterPaidTo(e.target.value)}
                title="Paid To"
                placeholder="To"
              />
              <input
                className="border rounded px-1.5 py-0.5 h-7 text-[10px] w-20"
                placeholder="SellerID"
                value={filterSellerId}
                onChange={e => setFilterSellerId(e.target.value)}
              />

              {/* Storage filters */}
              <div className="flex items-center gap-0.5 border rounded px-1 py-0.5 h-7 bg-gray-50">
                <label className="flex items-center gap-0.5 text-[9px] cursor-pointer">
                  <input type="radio" name="storage_mode" checked={filterStorageMode === 'any'} onChange={() => setFilterStorageMode('any')} className="w-2.5 h-2.5" />
                  <span>Any</span>
                </label>
                <label className="flex items-center gap-0.5 text-[9px] cursor-pointer">
                  <input type="radio" name="storage_mode" checked={filterStorageMode === 'exact'} onChange={() => setFilterStorageMode('exact')} className="w-2.5 h-2.5" />
                  <span>Exact</span>
                </label>
                <label className="flex items-center gap-0.5 text-[9px] cursor-pointer">
                  <input type="radio" name="storage_mode" checked={filterStorageMode === 'section'} onChange={() => setFilterStorageMode('section')} className="w-2.5 h-2.5" />
                  <span>Sect</span>
                </label>
              </div>
              <input
                className="border rounded px-1.5 py-0.5 h-7 text-[10px] w-20"
                placeholder="Storage"
                value={filterStorageValue}
                onChange={e => setFilterStorageValue(e.target.value)}
              />
              <input
                className="border rounded px-1.5 py-0.5 h-7 text-[10px] w-32"
                placeholder="Title"
                value={filterTitle}
                onChange={e => setFilterTitle(e.target.value)}
              />
              <input
                className="border rounded px-1.5 py-0.5 h-7 text-[10px] w-24"
                placeholder="Tracking"
                value={filterTracking}
                onChange={e => setFilterTracking(e.target.value)}
              />
              <input
                className="border rounded px-1.5 py-0.5 h-7 text-[10px] w-20"
                placeholder="ItemID"
                value={filterItemId}
                onChange={e => setFilterItemId(e.target.value)}
              />
              <input
                className="border rounded px-1.5 py-0.5 h-7 text-[10px] w-16"
                placeholder="ID"
                value={filterId}
                onChange={e => setFilterId(e.target.value)}
              />
            </div>
          </div>

          {/* Grid Section - with dynamic height */}
          <div className="min-h-0 border rounded-lg bg-white flex flex-col" style={{ height: `${gridHeight}%` }}>
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

          {/* RESIZABLE DIVIDER */}
          <div
            className="h-1.5 bg-gray-300 hover:bg-blue-500 cursor-row-resize transition-colors flex items-center justify-center group relative"
            onMouseDown={(e) => {
              e.preventDefault();
              const startY = e.clientY;
              const startHeight = gridHeight;

              const handleMouseMove = (moveE: MouseEvent) => {
                const container = (e.target as HTMLElement).closest('.flex-1.min-h-0.flex.flex-col.gap-3');
                if (!container) return;

                const containerHeight = container.clientHeight;
                const deltaY = moveE.clientY - startY;
                const deltaPercent = (deltaY / containerHeight) * 100;
                const newHeight = Math.min(Math.max(startHeight + deltaPercent, 30), 70);
                _setGridHeight(newHeight);
              };

              const handleMouseUp = () => {
                document.removeEventListener('mousemove', handleMouseMove);
                document.removeEventListener('mouseup', handleMouseUp);
              };

              document.addEventListener('mousemove', handleMouseMove);
              document.addEventListener('mouseup', handleMouseUp);
            }}
          >
            <div className="w-20 h-1 bg-gray-400 rounded-full group-hover:bg-blue-600 group-hover:h-1.5 transition-all" />
          </div>

          {/* Detail Panel - Like SKU Page */}
          {detail ? (
            <div className="flex-[1] min-h-[200px] border rounded-lg bg-white flex flex-col overflow-hidden">
              {/* Header - LARGER */}
              <div className="bg-blue-100 px-4 py-3 border-b border-blue-200">
                <span className="text-xl font-bold text-blue-900">📦 Transaction #{detail.id}</span>
              </div>

              <div className="flex-1 p-4 flex gap-4 overflow-auto text-base">
                {/* Left: LARGER CLICKABLE Image */}
                <div className="w-64 h-48 bg-gray-50 border-2 border-gray-300 rounded-lg flex items-center justify-center shrink-0 overflow-hidden hover:border-blue-500 transition-colors">
                  {detail.gallery_url || detail.picture_url0 ? (
                    <img
                      src={detail.gallery_url || detail.picture_url0 || ''}
                      alt="Item"
                      className="w-full h-full object-cover cursor-pointer hover:scale-105 transition-transform"
                      onClick={() => {
                        const url = detail.gallery_url || detail.picture_url0;
                        if (url) window.open(url, '_blank');
                      }}
                    />
                  ) : (
                    <div className="text-center p-4 text-gray-400">
                      <div className="text-5xl mb-2">📷</div>
                      <span className="text-sm">No Image</span>
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

                {/* Far Right: Status & LARGE Comment Section - 50% WIDTH */}
                <div className="flex-1 flex flex-col gap-3 border-l-2 border-gray-200 pl-4">
                  <div>
                    <label className="font-bold block text-base mb-2">Status:</label>
                    <select
                      className="border-2 rounded px-3 py-2 text-base w-full font-medium"
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

                  {/* MUCH LARGER Comment Section */}
                  <div className="flex-1 flex flex-col">
                    <label className="font-bold block text-lg mb-2">📝 Comments:</label>
                    <textarea
                      className="border-2 rounded px-3 py-2 text-base w-full flex-1 resize-none bg-yellow-50 min-h-[200px] font-mono"
                      value={pendingComment}
                      onChange={(e) => setPendingComment(e.target.value)}
                      placeholder="Enter your comments here..."
                    />
                  </div>

                  <div>
                    <button
                      className="w-full px-4 py-3 rounded-lg bg-blue-600 text-white text-base hover:bg-blue-700 flex items-center justify-center gap-2 font-bold disabled:opacity-50 transition-colors"
                      onClick={handleSave}
                      disabled={saving || !selectedId}
                    >
                      <span className="text-xl">💾</span>
                      <span>{saving ? 'Saving…' : 'Save Changes'}</span>
                    </button>
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div className="border rounded-lg bg-gradient-to-br from-blue-50 to-gray-50 flex items-center justify-center" style={{ minHeight: `${100 - gridHeight}%` }}>
              <div className="text-center p-8">
                <div className="text-5xl mb-4">👆</div>
                <div className="text-3xl font-bold text-gray-700 mb-3">Select a Buying Record</div>
                <div className="text-xl text-gray-500">Click on any row in the grid above to view transaction details</div>
              </div>
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

