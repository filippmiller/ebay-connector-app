import { useEffect, useState } from 'react';
import FixedHeader from '@/components/FixedHeader';
import { DataGridPage } from '@/components/DataGridPage';
import api from '@/lib/apiClient';

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
}

export default function BuyingPage() {
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<BuyingDetail | null>(null);
  const [statuses, setStatuses] = useState<BuyingStatus[]>([]);
  const [pendingStatusId, setPendingStatusId] = useState<number | null | undefined>(undefined);
  const [pendingComment, setPendingComment] = useState<string>('');
  const [saving, setSaving] = useState(false);

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
    } catch (e) {
      console.error('Failed to update BUYING status/comment', e);
    } finally {
      setSaving(false);
    }
  };

  const currentStatusColor = (statusId: number | null | undefined) => {
    const s = statuses.find((st) => st.id === statusId);
    return {
      backgroundColor: s?.color_hex || 'transparent',
      color: s?.text_color_hex || '#111827',
    };
  };

  return (
    <div className="h-screen flex flex-col bg-gray-50">
      <FixedHeader />
      <div className="pt-16 flex-1 px-4 py-6 overflow-hidden">
        <div className="w-full h-full flex flex-col">
          <h1 className="text-3xl font-bold mb-4">Buying (Purchases)</h1>
          <div className="flex-1 min-h-0 flex flex-col gap-3">
            <div className="flex-1 min-h-0">
              <DataGridPage
                gridKey="buying"
                title="Buying (Purchases)"
                // Simple row click: rows are plain objects with an "id" field from the grid backend
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                onRowClick={(row: any) => {
                  if (row && typeof row.id === 'number') {
                    setSelectedId(row.id);
                  }
                }}
              />
            </div>

            {/* Detail panel */}
            {detail && (
              <div className="border rounded-lg bg-white p-4 grid grid-cols-3 gap-4 text-sm">
                <div className="space-y-1">
                  <div>
                    <span className="font-semibold">Title:</span> {detail.title || '(no title)'}
                  </div>
                  <div>
                    <span className="font-semibold">Item ID:</span> {detail.item_id || '-'}
                  </div>
                  <div>
                    <span className="font-semibold">Transaction ID:</span> {detail.transaction_id || '-'}
                  </div>
                  <div>
                    <span className="font-semibold">Order line item:</span> {detail.order_line_item_id || '-'}
                  </div>
                  <div>
                    <span className="font-semibold">Buyer:</span> {detail.buyer_id || '-'}
                  </div>
                  <div>
                    <span className="font-semibold">Seller:</span> {detail.seller_id || '-'}
                  </div>
                </div>

                <div className="space-y-1">
                  <div>
                    <span className="font-semibold">Tracking #:</span> {detail.tracking_number || '-'}
                  </div>
                  <div>
                    <span className="font-semibold">Storage:</span> {detail.storage || '-'}
                  </div>
                  <div>
                    <span className="font-semibold">Qty:</span> {detail.quantity_purchased ?? '-'}
                  </div>
                  <div>
                    <span className="font-semibold">Condition:</span> {detail.condition_display_name || '-'}
                  </div>
                  <div>
                    <span className="font-semibold">Shipping carrier:</span> {detail.shipping_carrier || '-'}
                  </div>
                  <div>
                    <span className="font-semibold">Seller location:</span> {detail.seller_location || '-'}
                  </div>
                </div>

                <div className="space-y-2 border-l pl-4">
                  <div>
                    <span className="font-semibold">Paid on:</span>{' '}
                    {detail.paid_time ? new Date(detail.paid_time).toLocaleString() : '-'}
                  </div>
                  <div>
                    <span className="font-semibold">Amount paid:</span>{' '}
                    {detail.amount_paid != null ? `$${detail.amount_paid.toFixed(2)}` : '-'}
                  </div>
                  <div className="mt-3">
                    <div className="font-semibold mb-1">Status:</div>
                    <select
                      className="border rounded px-2 py-1 text-sm w-full"
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
                  <div className="mt-3">
                    <div className="font-semibold mb-1">Comment:</div>
                    <textarea
                      className="border rounded px-2 py-1 text-sm w-full h-20 resize-none"
                      value={pendingComment}
                      onChange={(e) => setPendingComment(e.target.value)}
                    />
                  </div>
                  <div className="mt-2 flex justify-end">
                    <button
                      className="px-3 py-1 rounded bg-blue-600 text-white text-xs hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed"
                      onClick={handleSave}
                      disabled={saving || !selectedId}
                    >
                      {saving ? 'Saving…' : 'Save'}
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
