import { useCallback, useState } from 'react';
import FixedHeader from '@/components/FixedHeader';
import { DataGridPage } from '@/components/DataGridPage';
import api from '@/lib/apiClient';

type CaseKind = 'inquiry' | 'postorder_case' | 'payment_dispute';

interface CaseDetailResponse {
  entity: Record<string, any>;
  messages: Record<string, any>[];
  events: Record<string, any>[];
}

export default function CasesPage() {
  const [selected, setSelected] = useState<{ kind: CaseKind; id: string } | null>(null);
  const [detail, setDetail] = useState<CaseDetailResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isOpen, setIsOpen] = useState(false);

  const closePanel = useCallback(() => {
    setIsOpen(false);
    setDetail(null);
    setError(null);
  }, []);

  const fetchDetail = useCallback(async (kind: CaseKind, id: string) => {
    setLoading(true);
    setError(null);
    try {
      const resp = await api.get<CaseDetailResponse>('/api/grids/cases/detail', {
        params: { kind, id },
      });
      setDetail(resp.data);
    } catch (e: any) {
      const message =
        e?.response?.data?.detail || e?.message || 'Failed to load case detail';
      setError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  const handleRowClick = useCallback(
    (row: Record<string, any>) => {
      const kind = row.kind as CaseKind | undefined;
      const externalId = row.external_id as string | undefined;
      if (!kind || !externalId) return;

      const id = String(externalId);
      setSelected({ kind, id });
      setIsOpen(true);
      void fetchDetail(kind, id);
    },
    [fetchDetail],
  );

  const entity = detail?.entity ?? null;
  const messages = detail?.messages ?? [];
  const events = detail?.events ?? [];

  return (
    <div className="h-screen flex flex-col bg-gray-50">
      <FixedHeader />
      {/* Main content area under fixed header: full width, grid fills all available space */}
      <div className="pt-16 flex-1 px-4 py-6 overflow-hidden">
        <div className="w-full h-full flex flex-col">
          <div className="mb-4">
            <h1 className="text-3xl font-bold">Cases &amp; Disputes</h1>
            <p className="text-gray-600 mt-2 text-sm max-w-3xl">
              Unified view of Item Not Received (INR) and Significantly Not As Described (SNAD)
              payment disputes, Post-Order cases, and buyer inquiries from eBay. Grid layout and
              column visibility are saved per user.
            </p>
          </div>
          <div className="flex-1">
            <DataGridPage
              gridKey="cases"
              title="Cases &amp; Disputes"
              onRowClick={handleRowClick}
            />
          </div>
        </div>
      </div>

      {/* Right-side detail panel */}
      {isOpen && selected && (
        <div className="fixed inset-0 z-40 flex">
          {/* Backdrop */}
          <button
            type="button"
            className="flex-1 bg-black/30"
            onClick={closePanel}
            aria-label="Close case detail"
          />
          {/* Panel */}
          <div className="w-full max-w-2xl h-full bg-white shadow-xl flex flex-col">
            <div className="px-4 py-3 border-b flex items-center justify-between">
              <div>
                <div className="text-xs uppercase tracking-wide text-gray-500">
                  {selected.kind === 'inquiry'
                    ? 'Inquiry'
                    : selected.kind === 'postorder_case'
                    ? 'Post-Order Case'
                    : 'Payment Dispute'}
                </div>
                <div className="text-sm font-semibold text-gray-900">
                  ID: {selected.id}
                </div>
              </div>
              <button
                type="button"
                className="text-gray-500 hover:text-gray-700 text-sm"
                onClick={closePanel}
              >
                Close
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-4 space-y-4 text-sm">
              {loading && (
                <div className="text-gray-500 text-sm">Loading case detail…</div>
              )}
              {error && !loading && (
                <div className="text-red-600 text-sm">{error}</div>
              )}

              {!loading && !error && entity && (
                <>
                  {/* Summary */}
                  <section className="space-y-1">
                    <h2 className="text-base font-semibold">Summary</h2>
                    <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-gray-700">
                      <span className="font-medium">Status:</span>
                      <span>{entity.status ?? '—'}</span>
                      <span className="font-medium">Issue type:</span>
                      <span>{entity.issue_type ?? '—'}</span>
                      <span className="font-medium">Order ID:</span>
                      <span>{entity.order_id ?? '—'}</span>
                      <span className="font-medium">Buyer:</span>
                      <span>{entity.buyer_username ?? '—'}</span>
                      <span className="font-medium">Amount:</span>
                      <span>
                        {entity.amount != null
                          ? `${entity.amount} ${entity.currency || ''}`
                          : '—'}
                      </span>
                      <span className="font-medium">Opened at:</span>
                      <span>{entity.open_date ?? '—'}</span>
                      <span className="font-medium">Respond by:</span>
                      <span>{entity.respond_by_date ?? '—'}</span>
                    </div>
                  </section>

                  {/* Messages */}
                  <section className="space-y-2">
                    <h2 className="text-base font-semibold">Messages</h2>
                    {messages.length === 0 ? (
                      <div className="text-xs text-gray-500">No related messages.</div>
                    ) : (
                      <div className="space-y-2 max-h-64 overflow-y-auto border rounded-md p-2 bg-gray-50">
                        {messages.map((m, idx) => (
                          <div
                            key={m.id ?? idx}
                            className="border-b last:border-b-0 pb-2 last:pb-0 text-xs text-gray-800"
                          >
                            <div className="flex items-center justify-between mb-1">
                              <div className="font-medium">
                                {m.sender_username ?? 'Unknown sender'}
                              </div>
                              <div className="text-[11px] text-gray-500">
                                {m.message_date ?? m.message_at ?? '—'}
                              </div>
                            </div>
                            {m.subject && (
                              <div className="text-[11px] text-gray-600 mb-0.5">
                                {m.subject}
                              </div>
                            )}
                            {m.preview_text && (
                              <div className="text-[11px] text-gray-700 line-clamp-3">
                                {m.preview_text}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </section>

                  {/* Events */}
                  <section className="space-y-2">
                    <h2 className="text-base font-semibold">Events</h2>
                    {events.length === 0 ? (
                      <div className="text-xs text-gray-500">No related events.</div>
                    ) : (
                      <div className="space-y-2 max-h-64 overflow-y-auto border rounded-md p-2 bg-gray-50">
                        {events.map((ev, idx) => (
                          <div
                            key={ev.id ?? idx}
                            className="border-b last:border-b-0 pb-2 last:pb-0 text-xs text-gray-800"
                          >
                            <div className="flex items-center justify-between mb-1">
                              <div className="font-medium">
                                {ev.topic ?? ev.entity_type ?? 'Event'}
                              </div>
                              <div className="text-[11px] text-gray-500">
                                {ev.event_time ?? ev.publish_time ?? ev.created_at ?? '—'}
                              </div>
                            </div>
                            <div className="text-[11px] text-gray-600">
                              Status: {ev.status ?? '—'}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </section>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
