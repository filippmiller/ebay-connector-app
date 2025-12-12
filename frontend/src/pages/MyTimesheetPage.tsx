import { useEffect, useState } from 'react';
import FixedHeader from '@/components/FixedHeader';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { startTimesheet, stopTimesheet, getMyTimesheets, TimesheetEntry } from '@/api/timesheets';

export default function MyTimesheetPage() {
  const [description, setDescription] = useState('');
  const [allEntries, setAllEntries] = useState<TimesheetEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [activeEntry, setActiveEntry] = useState<TimesheetEntry | null>(null);

  const startOfWeekMonday = (date: Date) => {
    const d = new Date(date);
    const day = d.getDay(); // 0 = Sun, 1 = Mon
    const diff = day === 0 ? -6 : 1 - day;
    d.setDate(d.getDate() + diff);
    d.setHours(0, 0, 0, 0);
    return d;
  };

  const formatDateInput = (date: Date) => date.toISOString().slice(0, 10);
  const [weekStart, setWeekStart] = useState(() => formatDateInput(startOfWeekMonday(new Date())));

  const { startDate: weekStartDate, endDate: weekEndDate } = (() => {
    const startDate = new Date(`${weekStart}T00:00:00`);
    startDate.setHours(0, 0, 0, 0);
    const endDate = new Date(startDate);
    endDate.setDate(startDate.getDate() + 7);
    return { startDate, endDate };
  })();

  const weekEntries = allEntries.filter((e) => {
    if (!e.startTime) return false;
    const d = new Date(e.startTime);
    return d >= weekStartDate && d < weekEndDate;
  });

  const weekEntriesSorted = [...weekEntries].sort((a, b) => {
    const aTime = a.startTime ? new Date(a.startTime).getTime() : 0;
    const bTime = b.startTime ? new Date(b.startTime).getTime() : 0;
    return bTime - aTime;
  });

  const totalMinutes = weekEntries.reduce((sum, e) => sum + (e.durationMinutes ?? 0), 0);
  const totalHours = Math.floor(totalMinutes / 60);
  const totalMinutesRemainder = totalMinutes % 60;

  const loadData = async () => {
    setLoading(true);
    try {
      const resp = await getMyTimesheets({});
      if (resp.success && resp.data) {
        const items = resp.data.items || [];
        setAllEntries(items);
        const open = items.find((e) => e.endTime === null && !e.deleteFlag) || null;
        setActiveEntry(open || null);
      } else {
        setAllEntries([]);
        setActiveEntry(null);
      }
    } catch (e) {
      console.error('Failed to load timesheets', e);
      setAllEntries([]);
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

  const shiftWeek = (deltaWeeks: number) => {
    const base = new Date(`${weekStart}T00:00:00`);
    base.setDate(base.getDate() + deltaWeeks * 7);
    const monday = startOfWeekMonday(base);
    setWeekStart(formatDateInput(monday));
  };

  const handleWeekInputChange = (value: string) => {
    if (!value) return;
    const target = startOfWeekMonday(new Date(`${value}T00:00:00`));
    setWeekStart(formatDateInput(target));
  };

  const toCsvValue = (val: string | number | null | undefined) => {
    if (val === null || val === undefined) return '""';
    const str = String(val).replace(/"/g, '""');
    return `"${str}"`;
  };

  const exportWeekCsv = () => {
    const header = ['Start', 'End', 'Duration (min)', 'Description', 'Rate'];
    const rows = weekEntriesSorted.map((e) => [
      e.startTime ? new Date(e.startTime).toISOString() : '',
      e.endTime ? new Date(e.endTime).toISOString() : '',
      e.durationMinutes ?? '',
      e.description ?? '',
      e.rate ?? '',
    ]);
    const csv = [header, ...rows]
      .map((r) => r.map((c) => toCsvValue(c as string | number | null | undefined)).join(','))
      .join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `timesheet_week_${weekStart}.csv`;
    link.click();
    URL.revokeObjectURL(url);
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

  const dayCards = Array.from({ length: 7 }).map((_, idx) => {
    const currentDay = new Date(weekStartDate);
    currentDay.setDate(weekStartDate.getDate() + idx);
    const currentKey = formatDateInput(currentDay);
    const dayEntries = weekEntries
      .filter((e) => e.startTime && formatDateInput(new Date(e.startTime)) === currentKey)
      .sort((a, b) => {
        const aTime = a.startTime ? new Date(a.startTime).getTime() : 0;
        const bTime = b.startTime ? new Date(b.startTime).getTime() : 0;
        return aTime - bTime;
      });

    return (
      <div key={currentKey} className="border rounded p-3 bg-white shadow-sm">
        <div className="font-semibold text-sm mb-2">
          {currentDay.toLocaleDateString(undefined, { weekday: 'long', month: 'short', day: 'numeric' })}
        </div>
        {dayEntries.length === 0 ? (
          <div className="text-xs text-gray-500">No sessions</div>
        ) : (
          <div className="flex flex-col gap-2">
            {dayEntries.map((e) => (
              <div key={e.id} className="text-xs leading-snug">
                <div className="font-medium">
                  {e.startTime
                    ? new Date(e.startTime).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                    : ''}
                  {' – '}
                  {e.endTime
                    ? new Date(e.endTime).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                    : '…'}
                </div>
                <div>{formatDuration(e.durationMinutes)}</div>
                {e.description && <div className="text-gray-600">{e.description}</div>}
              </div>
            ))}
          </div>
        )}
      </div>
    );
  });

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

        <Card className="p-4 mb-4">
          <div className="flex flex-col gap-3">
            <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
              <div className="flex flex-col">
                <h2 className="text-lg font-semibold">Weekly calendar (Mon-Sun)</h2>
                <div className="text-sm text-gray-600">
                  Total: {totalHours} h {totalMinutesRemainder} min
                </div>
              </div>
              <div className="flex flex-wrap gap-2 items-center">
                <Button variant="outline" size="sm" onClick={() => shiftWeek(-1)} disabled={loading}>
                  Previous week
                </Button>
                <Button variant="outline" size="sm" onClick={() => shiftWeek(1)} disabled={loading}>
                  Next week
                </Button>
                <Input
                  type="date"
                  value={weekStart}
                  onChange={(e) => handleWeekInputChange(e.target.value)}
                  className="w-40"
                />
                <Button variant="outline" size="sm" onClick={exportWeekCsv} disabled={weekEntriesSorted.length === 0}>
                  Export CSV
                </Button>
              </div>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {dayCards}
            </div>
          </div>
        </Card>

        <Card className="p-4">
          <h2 className="text-lg font-semibold mb-2">
            Entries for week of {weekStartDate.toLocaleDateString()} –{' '}
            {new Date(weekEndDate.getTime() - 1).toLocaleDateString()}
          </h2>
          {loading ? (
            <div className="text-gray-500 text-sm">Loading…</div>
          ) : weekEntriesSorted.length === 0 ? (
            <div className="text-gray-500 text-sm">No timesheet entries for this week.</div>
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
                  {weekEntriesSorted.map((e) => {
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
