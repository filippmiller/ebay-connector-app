import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import FixedHeader from '@/components/FixedHeader';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { ebayApi, type AdminEbayEvent } from '../api/ebay';
import { useAuth } from '@/auth/AuthContext';

function formatDate(value: string | null | undefined) {
  if (!value) return '';
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

export default function EbayNotificationsPage() {
  const { user } = useAuth();
  const navigate = useNavigate();

  const [events, setEvents] = useState<AdminEbayEvent[]>([]);
  const [selected, setSelected] = useState<AdminEbayEvent | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [topic, setTopic] = useState('');
  const [source, setSource] = useState('');
  const [channel, setChannel] = useState('');
  const [status, setStatus] = useState('');
  const [ebayAccount, setEbayAccount] = useState('');
  const [entityType, setEntityType] = useState('');
  const [entityId, setEntityId] = useState('');
  const [fromLocal, setFromLocal] = useState('');
  const [toLocal, setToLocal] = useState('');

  const [limit, setLimit] = useState(50);
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const [sortBy, setSortBy] = useState<'event_time' | 'created_at'>('event_time');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');

  useEffect(() => {
    if (!user) return;
    if (user.role !== 'admin') {
      navigate('/dashboard');
      return;
    }
    // Initial load
    void fetchEvents(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user]);

  const fetchEvents = async (newOffset: number) => {
    setLoading(true);
    setError(null);
    try {
      const params: Parameters<typeof ebayApi.getAdminEbayEvents>[0] = {
        topic: topic || undefined,
        entityType: entityType || undefined,
        entityId: entityId || undefined,
        ebayAccount: ebayAccount || undefined,
        source: source || undefined,
        channel: channel || undefined,
        status: status || undefined,
        from: fromLocal ? new Date(fromLocal).toISOString() : undefined,
        to: toLocal ? new Date(toLocal).toISOString() : undefined,
        limit,
        offset: newOffset,
        sortBy,
        sortDir,
      };
      const data = await ebayApi.getAdminEbayEvents(params);
      setEvents(data.items || []);
      setTotal(data.total || 0);
      setOffset(data.offset ?? newOffset);
      if (!selected && data.items && data.items.length > 0) {
        setSelected(data.items[0]);
      } else if (selected) {
        const stillExists = data.items.find((e) => e.id === selected.id);
        if (!stillExists) {
          setSelected(data.items[0] || null);
        }
      }
    } catch (e: any) {
      // eslint-disable-next-line no-console
      console.error('Failed to load eBay events', e);
      const detail = e?.response?.data?.detail || e?.message || 'Failed to load eBay events';
      setError(detail);
      setEvents([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  };

  const handleApplyFilters = () => {
    void fetchEvents(0);
  };

  const canPrev = offset > 0;
  const canNext = offset + limit < total;
  const fromRow = total === 0 ? 0 : offset + 1;
  const toRow = Math.min(offset + limit, total);

  return (
    <div className="min-h-screen bg-gray-50">
      <FixedHeader />
      <div className="pt-12 px-4 py-6">
        <div className="max-w-7xl mx-auto flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold">eBay Notifications Center</h1>
              <p className="text-sm text-gray-600">
                Unified inbox of eBay webhook and polling events from the ebay_events table.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" onClick={() => void fetchEvents(0)} disabled={loading}>
                Refresh
              </Button>
            </div>
          </div>

          {error && (
            <Alert variant="destructive">
              <AlertDescription className="text-sm">{error}</AlertDescription>
            </Alert>
          )}

          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Filters</CardTitle>
              <CardDescription className="text-sm text-gray-600">
                Filter by topic, source, account, entity, and time range. Times are applied against event_time
                when available, otherwise created_at.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
                <div>
                  <Label className="block text-xs mb-1">Topic</Label>
                  <Input
                    value={topic}
                    onChange={(e) => setTopic(e.target.value)}
                    placeholder="e.g. ORDER_UPDATED, FEEDBACK_RECEIVED"
                  />
                </div>
                <div>
                  <Label className="block text-xs mb-1">Status</Label>
                  <Input
                    value={status}
                    onChange={(e) => setStatus(e.target.value)}
                    placeholder="RECEIVED/PROCESSED/FAILED"
                  />
                </div>
                <div>
                  <Label className="block text-xs mb-1">Source</Label>
                  <Input
                    value={source}
                    onChange={(e) => setSource(e.target.value)}
                    placeholder="notification/rest_poll/..."
                  />
                </div>
                <div>
                  <Label className="block text-xs mb-1">Channel</Label>
                  <Input
                    value={channel}
                    onChange={(e) => setChannel(e.target.value)}
                    placeholder="commerce_notification/sell_fulfillment_api/..."
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
                <div>
                  <Label className="block text-xs mb-1">eBay account</Label>
                  <Input
                    value={ebayAccount}
                    onChange={(e) => setEbayAccount(e.target.value)}
                    placeholder="username or account key"
                  />
                </div>
                <div>
                  <Label className="block text-xs mb-1">Entity type</Label>
                  <Input
                    value={entityType}
                    onChange={(e) => setEntityType(e.target.value)}
                    placeholder="ORDER/MESSAGE/OFFER/..."
                  />
                </div>
                <div>
                  <Label className="block text-xs mb-1">Entity ID</Label>
                  <Input
                    value={entityId}
                    onChange={(e) => setEntityId(e.target.value)}
                    placeholder="orderId, messageId, ..."
                  />
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <Label className="block text-xs mb-1">From</Label>
                    <Input
                      type="datetime-local"
                      value={fromLocal}
                      onChange={(e) => setFromLocal(e.target.value)}
                    />
                  </div>
                  <div>
                    <Label className="block text-xs mb-1">To</Label>
                    <Input
                      type="datetime-local"
                      value={toLocal}
                      onChange={(e) => setToLocal(e.target.value)}
                    />
                  </div>
                </div>
              </div>

              <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t mt-2">
                <div className="flex items-center gap-2 text-xs">
                  <Label className="text-xs">Sort by</Label>
                  <select
                    className="border rounded px-2 py-1 text-xs bg-white"
                    value={sortBy}
                    onChange={(e) => setSortBy(e.target.value as 'event_time' | 'created_at')}
                  >
                    <option value="event_time">Event time</option>
                    <option value="created_at">Stored at</option>
                  </select>
                  <select
                    className="border rounded px-2 py-1 text-xs bg-white"
                    value={sortDir}
                    onChange={(e) => setSortDir(e.target.value as 'asc' | 'desc')}
                  >
                    <option value="desc">Desc</option>
                    <option value="asc">Asc</option>
                  </select>
                </div>
                <div className="flex items-center gap-2">
                  <Label className="text-xs">Page size</Label>
                  <select
                    className="border rounded px-2 py-1 text-xs bg-white"
                    value={limit}
                    onChange={(e) => setLimit(Number(e.target.value) || 50)}
                  >
                    <option value={20}>20</option>
                    <option value={50}>50</option>
                    <option value={100}>100</option>
                  </select>
                  <Button size="sm" onClick={handleApplyFilters} disabled={loading}>
                    Apply
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="mt-2">
            <CardContent className="p-0">
              <div className="flex flex-col md:flex-row md:divide-x">
                <div className="md:w-2/3 p-4 border-b md:border-b-0">
                  <div className="flex items-center justify-between mb-2 text-xs text-gray-600">
                    <span>
                      {loading ? 'Loading events…' : `Showing ${fromRow}-${toRow} of ${total}`}
                    </span>
                    <div className="flex items-center gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={!canPrev || loading}
                        onClick={() => canPrev && fetchEvents(Math.max(offset - limit, 0))}
                      >
                        Previous
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={!canNext || loading}
                        onClick={() => canNext && fetchEvents(offset + limit)}
                      >
                        Next
                      </Button>
                    </div>
                  </div>
                  <div className="border rounded bg-white overflow-auto max-h-[60vh]">
                    <table className="min-w-full text-xs">
                      <thead className="bg-gray-100 sticky top-0 z-10">
                        <tr>
                          <th className="px-2 py-1 text-left">Event time</th>
                          <th className="px-2 py-1 text-left">Topic</th>
                          <th className="px-2 py-1 text-left">Source</th>
                          <th className="px-2 py-1 text-left">Channel</th>
                          <th className="px-2 py-1 text-left">Account</th>
                          <th className="px-2 py-1 text-left">Entity</th>
                          <th className="px-2 py-1 text-left">Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {loading && events.length === 0 ? (
                          <tr>
                            <td colSpan={7} className="px-3 py-4 text-center text-gray-500">
                              Loading…
                            </td>
                          </tr>
                        ) : events.length === 0 ? (
                          <tr>
                            <td colSpan={7} className="px-3 py-4 text-center text-gray-500">
                              No events match the current filters.
                            </td>
                          </tr>
                        ) : (
                          events.map((ev) => {
                            const isSelected = selected && selected.id === ev.id;
                            return (
                              <tr
                                key={ev.id}
                                className={`border-t cursor-pointer hover:bg-indigo-50 ${
                                  isSelected ? 'bg-indigo-50' : ''
                                }`}
                                onClick={() => setSelected(ev)}
                              >
                                <td className="px-2 py-1 whitespace-nowrap">
                                  {formatDate(ev.event_time || ev.created_at)}
                                </td>
                                <td className="px-2 py-1 max-w-[14rem] truncate" title={ev.topic || ''}>
                                  {ev.topic || '—'}
                                </td>
                                <td className="px-2 py-1 whitespace-nowrap">{ev.source}</td>
                                <td className="px-2 py-1 whitespace-nowrap">{ev.channel}</td>
                                <td className="px-2 py-1 whitespace-nowrap">{ev.ebay_account || '—'}</td>
                                <td className="px-2 py-1 whitespace-nowrap">
                                  {ev.entity_type && ev.entity_id ? `${ev.entity_type}:${ev.entity_id}` : '—'}
                                </td>
                                <td className="px-2 py-1 whitespace-nowrap">{ev.status}</td>
                              </tr>
                            );
                          })
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>

                <div className="md:w-1/3 p-4 bg-gray-50 min-h-[16rem]">
                  <h2 className="text-sm font-semibold mb-2">Event detail</h2>
                  {!selected ? (
                    <p className="text-xs text-gray-500">Select an event from the table to inspect its payload.</p>
                  ) : (
                    <div className="flex flex-col gap-2 text-xs">
                      <div>
                        <div className="font-semibold text-gray-700">Meta</div>
                        <dl className="mt-1 grid grid-cols-[auto,1fr] gap-x-2 gap-y-1">
                          <dt className="text-gray-500">ID</dt>
                          <dd className="font-mono break-all">{selected.id}</dd>
                          <dt className="text-gray-500">Time</dt>
                          <dd>{formatDate(selected.event_time || selected.created_at)}</dd>
                          <dt className="text-gray-500">Topic</dt>
                          <dd>{selected.topic || '—'}</dd>
                          <dt className="text-gray-500">Source</dt>
                          <dd>{selected.source}</dd>
                          <dt className="text-gray-500">Channel</dt>
                          <dd>{selected.channel}</dd>
                          <dt className="text-gray-500">Account</dt>
                          <dd>{selected.ebay_account || '—'}</dd>
                          <dt className="text-gray-500">Entity</dt>
                          <dd>
                            {selected.entity_type && selected.entity_id
                              ? `${selected.entity_type}:${selected.entity_id}`
                              : '—'}
                          </dd>
                          <dt className="text-gray-500">Status</dt>
                          <dd>{selected.status}</dd>
                          {selected.error && (
                            <>
                              <dt className="text-gray-500">Error</dt>
                              <dd className="text-red-600 break-words">{selected.error}</dd>
                            </>
                          )}
                          <dt className="text-gray-500">Signature</dt>
                          <dd>
                            {selected.signature_valid === null && !selected.signature_kid && 'n/a'}
                            {selected.signature_valid === null && selected.signature_kid &&
                              `kid=${selected.signature_kid}`}
                            {selected.signature_valid === true && 'valid'}
                            {selected.signature_valid === false && 'invalid'}
                          </dd>
                        </dl>
                      </div>

                      <div className="mt-2">
                        <div className="font-semibold text-gray-700 mb-1">Payload preview</div>
                        <ScrollArea className="max-h-[40vh] rounded border bg-gray-900 text-gray-100 p-2 text-[11px]">
                          <pre className="whitespace-pre-wrap break-words font-mono">
                            {JSON.stringify(selected.payload_preview, null, 2)}
                          </pre>
                        </ScrollArea>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
