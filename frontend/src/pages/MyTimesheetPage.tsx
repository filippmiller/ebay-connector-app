import { useEffect, useState } from 'react';
import FixedHeader from '@/components/FixedHeader';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { startTimesheet, stopTimesheet, getMyTimesheets, TimesheetEntry } from '@/api/timesheets';

export default function MyTimesheetPage() {
  const [description, setDescription] = useState('');
  const [entries, setEntries] = useState<TimesheetEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [activeEntry, setActiveEntry] = useState<TimesheetEntry | null>(null);

  const loadData = async () => {
    setLoading(true);
    try {
      const resp = await getMyTimesheets({ page: 1, pageSize: 50 });
      if (resp.success && resp.data) {
        const items = resp.data.items || [];
        setEntries(items);
        const open = items.find((e) => e.endTime === null && !e.deleteFlag) || null;
        setActiveEntry(open || null);
      } else {
        setEntries([]);
        setActiveEntry(null);
      }
    } catch (e) {
      console.error('Failed to load timesheets', e);
      setEntries([]);
      setActiveEntry(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleStart = async () => {
    const resp = await startTimesheet(description || undefined);
    if (!resp.success) {
      console.error('Failed to start timer', resp.error);
      return;
    }
    setDescription('');
    await loadData();
  };

  const handleStop = async () => {
    const resp = await stopTimesheet(description || undefined);
    if (!resp.success) {
      console.error('Failed to stop timer', resp.error);
      return;
    }
    setDescription('');
    await loadData();
  };

  const formatDateTime = (iso: string | null) => {
    if (!iso) return '';
    return new Date(iso).toLocaleString();
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
      <div className="pt-16 p-4 max-w-5xl mx-auto">
        <h1 className="text-2xl font-bold mb-4">My Timesheet</h1>

        <Card className="p-4 mb-6 flex flex-col gap-3">
          <div className="flex flex-col md:flex-row md:items-center gap-3">
            <Input
              placeholder="What are you working on? (optional)"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
            <div className="flex gap-2">
              <Button onClick={handleStart} disabled={!!activeEntry || loading}>
                Start Time
              </Button>
              <Button
                variant="outline"
                onClick={handleStop}
                disabled={!activeEntry || loading}
              >
                Stop Time
              </Button>
            </div>
          </div>
          {activeEntry && (
            <div className="text-sm text-gray-600">
              Active since{' '}
              <span className="font-semibold">{formatDateTime(activeEntry.startTime)}</span>
              {activeEntry.description && (
                <>
                  {' '}– <span>{activeEntry.description}</span>
                </>
              )}
            </div>
          )}
        </Card>

        <Card className="p-4">
          <h2 className="text-lg font-semibold mb-2">Recent entries</h2>
          {loading ? (
            <div className="text-gray-500 text-sm">Loading…</div>
          ) : entries.length === 0 ? (
            <div className="text-gray-500 text-sm">No timesheet entries yet.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead>
                  <tr className="border-b bg-gray-100">
                    <th className="text-left py-2 px-2">Start Date</th>
                    <th className="text-left py-2 px-2">Start Time</th>
                    <th className="text-left py-2 px-2">End Date</th>
                    <th className="text-left py-2 px-2">End Time</th>
                    <th className="text-left py-2 px-2">Duration</th>
                    <th className="text-left py-2 px-2">Description</th>
                    <th className="text-left py-2 px-2">Rate</th>
                  </tr>
                </thead>
                <tbody>
                  {entries.map((e) => {
                    const start = e.startTime ? new Date(e.startTime) : null;
                    const end = e.endTime ? new Date(e.endTime) : null;
                    return (
                      <tr key={e.id} className="border-b">
                        <td className="py-1 px-2">
                          {start ? start.toLocaleDateString() : ''}
                        </td>
                        <td className="py-1 px-2">
                          {start ? start.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : ''}
                        </td>
                        <td className="py-1 px-2">
                          {end ? end.toLocaleDateString() : ''}
                        </td>
                        <td className="py-1 px-2">
                          {end ? end.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : ''}
                        </td>
                        <td className="py-1 px-2">{formatDuration(e.durationMinutes)}</td>
                        <td className="py-1 px-2 max-w-xs truncate" title={e.description || ''}>
                          {e.description}
                        </td>
                        <td className="py-1 px-2">{e.rate ?? ''}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
