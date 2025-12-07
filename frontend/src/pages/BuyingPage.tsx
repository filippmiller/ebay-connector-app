import { useEffect, useMemo, useState } from 'react';
import FixedHeader from '@/components/FixedHeader';
import { DataGridPage } from '@/components/DataGridPage';
import api from '@/lib/apiClient';
import { DraggableResizableDialog } from '@/components/ui/draggable-dialog';
import { ModelEditor } from '@/components/buying/ModelEditor';
import { useAuth } from '@/contexts/AuthContext';

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
            // Format comment with username and timestamp before saving
            const timestamp = new Date().toISOString();
            const username = user?.username || 'Unknown';
            const newCommentEntry = `[${timestamp}] ${username}: ${pendingComment}`;

            await api.patch(`/api/buying/${selectedId}/status`, {
                status_id: pendingStatusId,
                comment: newCommentEntry,
            });
            // Refresh detail so the panel stays in sync with DB/logs.
            const resp = await api.get<BuyingDetail>(`/api/buying/${selectedId}`);
            setDetail(resp.data);
            setPendingComment(resp.data.comment || '');
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
                col

Id: 'logs',
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
                    return null; // Placeholder
                },
            },
            {
                colId: 'model',
                field: 'model',
                headerName: 'Model',
                width: 200,
                sortable: true,
                filter: true,
                editable: true,
                cellEditor: ModelEditor,
                cellEditorPopup: true,
                cellEditorPopupPosition: 'under' as const,
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
            <div className="pt-16 flex-1 px-2 py-2 overflow-hidden flex flex-col gap-2">

                {/* Container 1: REMOVED - No header, no title */}

                <div className="flex-1 min-h-0 flex flex-col gap-2">
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
                                className="border rounded px-1.5 py-0.5 text-[10px] w-20"
                                placeholder="BuyerID"
                                value={filterBuyerId}
                                onChange={e => setFilterBuyerId(e.target.value)}
                            />
                            <select
                                className="border rounded px-1 py-0.5 text-[10px] w-24"
                                value={filterStatusId}
                                onChange={e => setFilterStatusId(e.target.value)}
                            >
                                <option value="">Status</option>
                                {statuses.map(s => <option key={s.id} value={s.id}>{s.label}</option>)}
                            </select>
                            <input
                                type="date"
                                className="border rounded px-1 py-0.5 text-[10px] w-28"
                                value={filterPaidFrom}
                                onChange={e => setFilterPaidFrom(e.target.value)}
                                title="Paid From"
                            />
                            <span className="text-[10px] text-gray-400">-</span>
                            <input
                                type="date"
                                className="border rounded px-1 py-0.5 text-[10px] w-28"
                                value={filterPaidTo}
                                onChange={e => setFilterPaidTo(e.target.value)}
                                title="Paid To"
                            />
                            <input
                                type="date"
                                className="border rounded px-1 py-0.5 text-[10px] w-28"
                                value={filterCreatedFrom}
                                onChange={e => setFilterCreatedFrom(e.target.value)}
                                title="Created From"
                            />
                            <span className="text-[10px] text-gray-400">-</span>
                            <input
                                type="date"
                                className="border rounded px-1 py-0.5 text-[10px] w-28"
                                value={filterCreatedTo}
                                onChange={e => setFilterCreatedTo(e.target.value)}
                                title="Created To"
                            />
                            <input
                                className="border rounded px-1.5 py-0.5 text-[10px] w-20"
                                placeholder="SellerID"
                                value={filterSellerId}
                                onChange={e => setFilterSellerId(e.target.value)}
                            />
                        </div>

                        {/* Row 2 */}
                        <div className="flex items-center gap-1.5">
                            <div className="flex items-center gap-0.5 border rounded px-1 py-0.5 bg-gray-50">
                                <span className="text-[9px] font-semibold mr-0.5">Str:</span>
                                <label className="flex items-center gap-0.5 cursor-pointer text-[9px]">
                                    <input type="radio" name="storage_mode" checked={filterStorageMode === 'any'} onChange={() => setFilterStorageMode('any')} className="w-2.5 h-2.5" />
                                    Any
                                </label>
                                <label className="flex items-center gap-0.5 cursor-pointer text-[9px] ml-0.5">
                                    <input type="radio" name="storage_mode" checked={filterStorageMode === 'exact'} onChange={() => setFilterStorageMode('exact')} className="w-2.5 h-2.5" />
                                    Exact
                                </label>
                                <label className="flex items-center gap-0.5 cursor-pointer text-[9px] ml-0.5">
                                    <input type="radio" name="storage_mode" checked={filterStorageMode === 'section'} onChange={() => setFilterStorageMode('section')} className="w-2.5 h-2.5" />
                                    Sect
                                </label>
                            </div>
                            <input
                                className="border rounded px-1.5 py-0.5 text-[10px] w-20"
                                placeholder="Storage"
                                value={filterStorageValue}
                                onChange={e => setFilterStorageValue(e.target.value)}
                            />
                            <input
                                className="border rounded px-1.5 py-0.5 text-[10px] flex-1"
                                placeholder="Title"
                                value={filterTitle}
                                onChange={e => setFilterTitle(e.target.value)}
                            />
                            <input
                                className="border rounded px-1.5 py-0.5 text-[10px] w-28"
                                placeholder="Tracking"
                                value={filterTracking}
                                onChange={e => setFilterTracking(e.target.value)}
                            />
                            <input
                                className="border rounded px-1.5 py-0.5 text-[10px] w-24"
                                placeholder="ItemID"
                                value={filterItemId}
                                onChange={e => setFilterItemId(e.target.value)}
                            />
                            <input
                                className="border rounded px-1.5 py-0.5 text-[10px] w-16"
                                placeholder="ID"
                                value={filterId}
                                onChange={e => setFilterId(e.target.value)}
                            />
                        </div>
                    </div>

                    {/* Container 3: Grid Section */}
                    <div className="flex-[2] min-h-0 border rounded-lg bg-white flex flex-col">
                        <div className="flex items-center justify-between px-3 py-1.5 border-b bg-gray-50 text-[10px]">
                            <div className="font-semibold">Buying Records</div>
                            <div className="text-gray-500">Click a row to see details below</div>
                        </div>
                        <div className="flex-1 min-h-0">
                            <DataGridPage
                                gridKey="buying"
                                hideTitle
                                extraColumns={extraColumns}
                                extraParams={extraParams}
                                onRowClick={(row: any) => {
                                    if (row && typeof row.id === 'number') {
                                        setSelectedId(row.id);
                                    }
                                }}
                            />
                        </div>
                    </div>

                    {/* Container 4: Detail Panel - 50% Info + 50% Comments */}
                    {detail ? (
                        <div className="flex-[1] min-h-[250px] border rounded-lg bg-white flex overflow-hidden">
                            {/* LEFT 50%: Transaction Details + Status */}
                            <div className="w-1/2 p-3 border-r flex gap-3 overflow-auto">
                                {/* Image */}
                                <div className="w-32 h-32 bg-gray-100 border flex items-center justify-center shrink-0">
                                    {detail.gallery_url || detail.picture_url ? (
                                        <img src={detail.gallery_url || detail.picture_url || ''} alt="Item" className="max-w-full max-h-full object-contain" />
                                    ) : (
                                        <span className="text-[10px] text-gray-400">No Image</span>
                                    )}
                                </div>

                                {/* Details */}
                                <div className="flex-1 space-y-1 text-[11px]">
                                    <div className="font-bold text-blue-800 text-xs mb-2">Transaction Details</div>

                                    <div className="flex gap-2">
                                        <span className="font-semibold w-20 text-gray-600">Seller:</span>
                                        <span className="text-purple-700">{detail.seller_id}</span>
                                    </div>
                                    <div className="flex gap-2">
                                        <span className="font-semibold w-20 text-gray-600">Tracking:</span>
                                        <span className="text-blue-600">{detail.tracking_number}</span>
                                    </div>
                                    <div className="flex gap-2">
                                        <span className="font-semibold w-20 text-gray-600">ItemID:</span>
                                        <span className="text-red-600 font-mono text-[10px]">{detail.item_id}</span>
                                    </div>
                                    <div className="flex gap-2">
                                        <span className="font-semibold w-20 text-gray-600">Title:</span>
                                        <span className="font-medium" title={detail.title || ''}>{detail.title}</span>
                                    </div>
                                    <div className="flex gap-2">
                                        <span className="font-semibold w-20 text-gray-600">Storage:</span>
                                        <span className="font-bold text-green-700">{detail.storage}</span>
                                    </div>
                                    <div className="flex gap-2">
                                        <span className="font-semibold w-20 text-gray-600">Qty:</span>
                                        <span>{detail.quantity_purchased}</span>
                                    </div>
                                    <div className="flex gap-2">
                                        <span className="font-semibold w-20 text-gray-600">Paid:</span>
                                        <span className="font-semibold">{detail.amount_paid ? `$${detail.amount_paid.toFixed(2)}` : '-'}</span>
                                    </div>
                                    <div className="flex gap-2">
                                        <span className="font-semibold w-20 text-gray-600">Paid Date:</span>
                                        <span>{detail.paid_time ? new Date(detail.paid_time).toLocaleDateString() : '-'}</span>
                                    </div>

                                    {/* Status Dropdown */}
                                    <div className="mt-3 pt-2 border-t">
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
                                                <option key={s.id} value={s.id} style={{ color: s.text_color_hex || '#000' }}>
                                                    {s.label}
                                                </option>
                                            ))}
                                        </select>
                                    </div>
                                </div>
                            </div>

                            {/* RIGHT 50%: Large Comments Section */}
                            <div className="w-1/2 p-3 flex flex-col">
                                <div className="font-bold text-blue-800 text-xs mb-2">Comments</div>

                                {/* Comments Display Area */}
                                <div className="flex-1 border rounded bg-yellow-50 p-2 overflow-auto mb-2 min-h-[120px]">
                                    {pendingComment ? (
                                        <div className="text-[11px] whitespace-pre-wrap font-mono">{pendingComment}</div>
                                    ) : (
                                        <div className="text-[10px] text-gray-400 italic">No comments yet</div>
                                    )}
                                </div>

                                {/* New Comment Input */}
                                <div className="mb-2">
                                    <label className="text-[10px] font-semibold text-gray-600 mb-1 block">Add New Comment:</label>
                                    <textarea
                                        className="border rounded px-2 py-1 text-xs w-full resize-none bg-white"
                                        rows={3}
                                        value={pendingComment}
                                        onChange={(e) => setPendingComment(e.target.value)}
                                        placeholder="Type your comment here..."
                                    />
                                </div>

                                {/* Action Buttons */}
                                <div className="flex gap-2">
                                    <button
                                        className="flex-1 px-3 py-1.5 rounded bg-blue-600 text-white text-xs hover:bg-blue-700 font-semibold disabled:opacity-50"
                                        onClick={handleSave}
                                        disabled={saving || !selectedId}
                                    >
                                        {saving ? 'Saving…' : '💾 Save Changes'}
                                    </button>
                                </div>

                                <div className="text-[9px] text-gray-500 mt-2 italic">
                                    Comments are saved with your username and timestamp
                                </div>
                            </div>
                        </div>
                    ) : (
                        <div className="flex-[1] min-h-[200px] border rounded-lg bg-white flex items-center justify-center text-xs text-gray-500">
                            Select a row in the Buying grid to see details and manage comments.
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
