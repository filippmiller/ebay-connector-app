import { useEffect, useState } from 'react';
import FixedHeader from '@/components/FixedHeader';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { adminListTimesheets, adminAddTimesheet, adminPatchTimesheet, TimesheetEntry } from '@/api/timesheets';

const PAGE_SIZE = 100;

export default function AdminTimesheetsPage() {
  const [entries, setEntries] = useState<TimesheetEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);
  const [userFilter, setUserFilter] = useState('');
  const [usernameFilter, setUsernameFilter] = useState('');
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');

  const [addUserId, setAddUserId] = useState('');
  const [addStart, setAddStart] = useState('');
  const [addEnd, setAddEnd] = useState('');
  const [addRate, setAddRate] = useState('');
  const [addDescription, setAddDescription] = useState('');

  const [editingId, setEditingId] = useState<number | null>(null);
  const [editStart, setEditStart] = useState('');
  const [editEnd, setEditEnd] = useState('');
  const [editRate, setEditRate] = useState('');
  const [editDescription, setEditDescription] = useState('');

  const fetchPage = async (targetPage: number, append: boolean) => {
    if (append) {
      setLoadingMore(true);
    } else {
      setLoading(true);
    }
    try {
      const resp = await adminListTimesheets({
        userId: userFilter || undefined,
        username: usernameFilter || undefined,
        from: from || undefined,
        to: to || undefined,
        page: targetPage,
        pageSize: PAGE_SIZE,
      });
      if (resp.success && resp.data) {
        const items = resp.data.items || [];
        setEntries((prev) => (append ? [...prev, ...items] : items));
        const totalPages = resp.data.totalPages || 1;
        setPage(targetPage);
        setHasMore(targetPage < totalPages);
      } else {
        setPage(1);
        setHasMore(false);
        setEntries([]);
      }
    } catch (e) {
      console.error('Failed to load admin timesheets', e);
      setPage(1);
      setHasMore(false);
      setEntries([]);
    } finally {
      if (append) {
        setLoadingMore(false);
      } else {
        setLoading(false);
      }
    }
  };

  const loadData = async () => fetchPage(1, false);
  const loadMore = async () => fetchPage(page + 1, true);

  useEffect(() => {
    loadData();
  }, []);

  const handleAdd = async () => {
    if (!addUserId || !addStart || !addEnd) return;
    try {
      const resp = await adminAddTimesheet({
        userId: addUserId,
        startTime: addStart,
        endTime: addEnd,
        rate: addRate || undefined,
        description: addDescription || undefined,
      });
      if (!resp.success) {
        console.error('Failed to add timesheet', resp.error);
      }
      setAddDescription('');
      await loadData();
    } catch (e) {
      console.error('Failed to add timesheet', e);
    }
  };

  const startEdit = (entry: TimesheetEntry) => {
    setEditingId(entry.id);
    setEditStart(entry.startTime || '');
    setEditEnd(entry.endTime || '');
    setEditRate(entry.rate || '');
    setEditDescription(entry.description || '');
  };

  const handleSaveEdit = async (id: number) => {
    try {
      const resp = await adminPatchTimesheet(id, {
        startTime: editStart || undefined,
        endTime: editEnd || undefined,
        rate: editRate || undefined,
        description: editDescription || undefined,
      });
      if (!resp.success) {
        console.error('Failed to update timesheet', resp.error);
      }
      setEditingId(null);
      await loadData();
    } catch (e) {
      console.error('Failed to update timesheet', e);
    }
  };

  const handleSoftDelete = async (id: number) => {
    try {
      const resp = await adminPatchTimesheet(id, { deleteFlag: true });
      if (!resp.success) {
        console.error('Failed to delete timesheet', resp.error);
      }
      await loadData();
    } catch (e) {
      console.error('Failed to delete timesheet', e);
    }
  };

  const formatDatePart = (iso: string | null) => {
    if (!iso) return '';
    const d = new Date(iso);
    return d.toLocaleDateString();
  };

  const formatTimePart = (iso: string | null) => {
    if (!iso) return '';
    const d = new Date(iso);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  const formatDuration = (minutes: number | null) => {
    if (minutes == null) return '';
    const h = Math.floor(minutes / 60);
    const m = minutes % 60;
    if (h === 0) return `${m} min`;
    return `${h} h ${m} min`;
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <FixedHeader />
      <div className="pt-16 p-4 max-w-7xl mx-auto">
        <h1 className="text-2xl font-bold mb-4">Timesheets (Admin)</h1>

        <Card className="p-4 mb-4 flex flex-col gap-3">
          <div className="grid grid-cols-1 md:grid-cols-5 gap-3 items-end">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">User ID</label>
              <Input value={userFilter} onChange={(e) => setUserFilter(e.target.value)} placeholder="Filter by userId" />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Username contains</label>
              <Input value={usernameFilter} onChange={(e) => setUsernameFilter(e.target.value)} placeholder="Filter by username" />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">From</label>
              <Input type="datetime-local" value={from} onChange={(e) => setFrom(e.target.value)} />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">To</label>
              <Input type="datetime-local" value={to} onChange={(e) => setTo(e.target.value)} />
            </div>
            <div className="flex gap-2">
              <Button onClick={loadData} disabled={loading} className="w-full">
                Apply Filters
              </Button>
            </div>
          </div>
        </Card>

        <Card className="p-4 mb-4 flex flex-col gap-3">
          <h2 className="text-lg font-semibold">Add Time</h2>
          <div className="grid grid-cols-1 md:grid-cols-5 gap-3 items-end">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">User ID</label>
              <Input value={addUserId} onChange={(e) => setAddUserId(e.target.value)} placeholder="users.id" />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Start</label>
              <Input type="datetime-local" value={addStart} onChange={(e) => setAddStart(e.target.value)} />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">End</label>
              <Input type="datetime-local" value={addEnd} onChange={(e) => setAddEnd(e.target.value)} />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Rate (optional)</label>
              <Input value={addRate} onChange={(e) => setAddRate(e.target.value)} placeholder="e.g. 23.50" />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Description</label>
              <Input value={addDescription} onChange={(e) => setAddDescription(e.target.value)} placeholder="Manual entry reason" />
            </div>
          </div>
          <div className="flex justify-end mt-2">
            <Button onClick={handleAdd} disabled={loading || !addUserId || !addStart || !addEnd}>
              Add Time
            </Button>
          </div>
        </Card>

        <Card className="p-4">
          <h2 className="text-lg font-semibold mb-2">Entries</h2>
          {loading ? (
            <div className="text-gray-500 text-sm">Loading…</div>
          ) : entries.length === 0 ? (
            <div className="text-gray-500 text-sm">No entries for current filters.</div>
          ) : (
            <div className="overflow-x-auto flex flex-col gap-3">
              <table className="min-w-full text-sm">
                <thead>
                  <tr className="border-b bg-gray-100">
                    <th className="text-left py-2 px-2">User</th>
                    <th className="text-left py-2 px-2">Start Date</th>
                    <th className="text-left py-2 px-2">Start Time</th>
                    <th className="text-left py-2 px-2">End Date</th>
                    <th className="text-left py-2 px-2">End Time</th>
                    <th className="text-left py-2 px-2">Duration</th>
                    <th className="text-left py-2 px-2">Description</th>
                    <th className="text-left py-2 px-2">Rate</th>
                    <th className="text-left py-2 px-2">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {entries.map((e) => {
                    const isEditing = editingId === e.id;
                    return (
                      <tr key={e.id} className={e.deleteFlag ? 'bg-red-50 border-b' : 'border-b'}>
                        <td className="py-1 px-2 whitespace-nowrap">{e.username}</td>
                        <td className="py-1 px-2">
                          {isEditing ? (
                            <Input
                              type="datetime-local"
                              value={editStart}
                              onChange={(ev) => setEditStart(ev.target.value)}
                              className="h-8 text-xs"
                            />
                          ) : (
                            formatDatePart(e.startTime)
                          )}
                        </td>
                        <td className="py-1 px-2">{isEditing ? '' : formatTimePart(e.startTime)}</td>
                        <td className="py-1 px-2">
                          {isEditing ? (
                            <Input
                              type="datetime-local"
                              value={editEnd}
                              onChange={(ev) => setEditEnd(ev.target.value)}
                              className="h-8 text-xs"
                            />
                          ) : (
                            formatDatePart(e.endTime)
                          )}
                        </td>
                        <td className="py-1 px-2">{isEditing ? '' : formatTimePart(e.endTime)}</td>
                        <td className="py-1 px-2">{formatDuration(e.durationMinutes)}</td>
                        <td className="py-1 px-2 max-w-xs">
                          {isEditing ? (
                            <Input
                              value={editDescription}
                              onChange={(ev) => setEditDescription(ev.target.value)}
                              className="h-8 text-xs"
                            />
                          ) : (
                            <span title={e.description || ''}>{e.description}</span>
                          )}
                        </td>
                        <td className="py-1 px-2">
                          {isEditing ? (
                            <Input
                              value={editRate}
                              onChange={(ev) => setEditRate(ev.target.value)}
                              className="h-8 text-xs w-20"
                            />
                          ) : (
                            e.rate ?? ''
                          )}
                        </td>
                        <td className="py-1 px-2 whitespace-nowrap flex gap-2">
                          {isEditing ? (
                            <>
                              <Button
                                size="sm"
                                variant="outline"
                                className="h-7 text-xs px-2"
                                onClick={() => handleSaveEdit(e.id)}
                              >
                                Save
                              </Button>
                              <Button
                                size="sm"
                                variant="ghost"
                                className="h-7 text-xs px-2"
                                onClick={() => setEditingId(null)}
                              >
                                Cancel
                              </Button>
                            </>
                          ) : (
                            <>
                              <Button
                                size="sm"
                                variant="outline"
                                className="h-7 text-xs px-2"
                                onClick={() => startEdit(e)}
                                disabled={e.deleteFlag}
                              >
                                Edit
                              </Button>
                              <Button
                                size="sm"
                                variant="ghost"
                                className="h-7 text-xs px-2 text-red-600"
                                onClick={() => handleSoftDelete(e.id)}
                                disabled={e.deleteFlag}
                              >
                                Delete
                              </Button>
                            </>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              {hasMore && (
                <div className="flex justify-center">
                  <Button onClick={loadMore} disabled={loadingMore} variant="outline" className="w-40">
                    {loadingMore ? 'Loading…' : 'Load more'}
                  </Button>
                </div>
              )}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
