import { useEffect, useMemo, useState } from 'react';
import FixedHeader from '@/components/FixedHeader';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { securityApi, type SecurityEventDto, type SecurityOverviewResponse, type SecuritySettingsResponse } from '@/api/security';
import { useAuth } from '@/auth/AuthContext';
import { useToast } from '@/hooks/use-toast';
import { useNavigate } from 'react-router-dom';

function formatDate(value: string | null | undefined) {
  if (!value) return '';
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

export default function SecurityCenterPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const { toast } = useToast();

  const [activeTab, setActiveTab] = useState<'overview' | 'events' | 'settings'>('overview');

  // Overview state
  const [overview, setOverview] = useState<SecurityOverviewResponse | null>(null);
  const [overviewWindowHours, setOverviewWindowHours] = useState(24);
  const [overviewLoading, setOverviewLoading] = useState(false);
  const [overviewError, setOverviewError] = useState<string | null>(null);

  // Events state
  const [events, setEvents] = useState<SecurityEventDto[]>([]);
  const [eventsTotal, setEventsTotal] = useState(0);
  const [eventsLimit, setEventsLimit] = useState(50);
  const [eventsOffset, setEventsOffset] = useState(0);
  const [eventsLoading, setEventsLoading] = useState(false);
  const [eventsError, setEventsError] = useState<string | null>(null);

  const [filterEventType, setFilterEventType] = useState('');
  const [filterUserId, setFilterUserId] = useState('');
  const [filterIp, setFilterIp] = useState('');
  const [filterFromLocal, setFilterFromLocal] = useState('');
  const [filterToLocal, setFilterToLocal] = useState('');

  // Terminal-style log for events
  const [terminalEvents, setTerminalEvents] = useState<SecurityEventDto[]>([]);

  // Settings state
  const [settings, setSettings] = useState<SecuritySettingsResponse | null>(null);
  const [settingsLoading, setSettingsLoading] = useState(false);
  const [settingsSaving, setSettingsSaving] = useState(false);
  const [settingsError, setSettingsError] = useState<string | null>(null);

  // Redirect non-admins away
  useEffect(() => {
    if (!user) return;
    if (user.role !== 'admin') {
      navigate('/dashboard');
    }
  }, [user, navigate]);

  // -------- Overview --------

  const loadOverview = async (windowHours: number) => {
    setOverviewLoading(true);
    setOverviewError(null);
    try {
      const resp = await securityApi.getOverview(windowHours);
      setOverview(resp);
    } catch (e: any) {
      // eslint-disable-next-line no-console
      console.error('Failed to load security overview', e);
      const msg = e?.response?.data?.detail || e?.message || 'Failed to load security overview';
      setOverviewError(msg);
      setOverview(null);
    } finally {
      setOverviewLoading(false);
    }
  };

  // -------- Events --------

  const loadEvents = async (newOffset: number) => {
    setEventsLoading(true);
    setEventsError(null);
    try {
      const params = {
        event_type: filterEventType || undefined,
        user_id: filterUserId || undefined,
        ip: filterIp || undefined,
        from: filterFromLocal ? new Date(filterFromLocal).toISOString() : undefined,
        to: filterToLocal ? new Date(filterToLocal).toISOString() : undefined,
        limit: eventsLimit,
        offset: newOffset,
      };
      const resp = await securityApi.getEvents(params);
      setEvents(resp.items || []);
      setEventsTotal(resp.total || 0);
      setEventsOffset(resp.offset ?? newOffset);
    } catch (e: any) {
      // eslint-disable-next-line no-console
      console.error('Failed to load security events', e);
      const msg = e?.response?.data?.detail || e?.message || 'Failed to load security events';
      setEventsError(msg);
      setEvents([]);
      setEventsTotal(0);
    } finally {
      setEventsLoading(false);
    }
  };

  // Live polling for terminal view: always last 100 events, independent of filters
  useEffect(() => {
    let cancelled = false;

    const poll = async () => {
      try {
        const resp = await securityApi.getEvents({ limit: 100, offset: 0 });
        if (cancelled) return;
        setTerminalEvents(resp.items || []);
      } catch (e) {
        // best-effort; do not surface in UI
      }
    };

    void poll();
    const id = window.setInterval(poll, 8000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  // -------- Settings --------

  const loadSettings = async () => {
    setSettingsLoading(true);
    setSettingsError(null);
    try {
      const s = await securityApi.getSettings();
      setSettings(s);
    } catch (e: any) {
      // eslint-disable-next-line no-console
      console.error('Failed to load security settings', e);
      const msg = e?.response?.data?.detail || e?.message || 'Failed to load security settings';
      setSettingsError(msg);
      setSettings(null);
    } finally {
      setSettingsLoading(false);
    }
  };

  const handleSaveSettings = async () => {
    if (!settings) return;
    setSettingsSaving(true);
    setSettingsError(null);
    try {
      const payload = {
        max_failed_attempts: settings.max_failed_attempts,
        initial_block_minutes: settings.initial_block_minutes,
        progressive_delay_step_minutes: settings.progressive_delay_step_minutes,
        max_delay_minutes: settings.max_delay_minutes,
        enable_captcha: settings.enable_captcha,
        captcha_after_failures: settings.captcha_after_failures,
        session_ttl_minutes: settings.session_ttl_minutes,
        session_idle_timeout_minutes: settings.session_idle_timeout_minutes,
        bruteforce_alert_threshold_per_ip: settings.bruteforce_alert_threshold_per_ip,
        bruteforce_alert_threshold_per_user: settings.bruteforce_alert_threshold_per_user,
        alert_email_enabled: settings.alert_email_enabled,
        alert_channel: settings.alert_channel,
      };

      const resp = await securityApi.updateSettings(payload);
      setSettings(resp.settings);
      toast({
        title: 'Security settings saved',
        description: 'New settings will apply to future login attempts and sessions.',
      });
    } catch (e: any) {
      // eslint-disable-next-line no-console
      console.error('Failed to save security settings', e);
      const msg = e?.response?.data?.detail || e?.message || 'Failed to save security settings';
      setSettingsError(msg);
      toast({ title: 'Failed to save settings', description: msg, variant: 'destructive' });
    } finally {
      setSettingsSaving(false);
    }
  };

  // Initial loads when user is admin and page mounts
  useEffect(() => {
    if (!user || user.role !== 'admin') return;
    void loadOverview(overviewWindowHours);
    void loadEvents(0);
    void loadSettings();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user]);

  const eventsCanPrev = eventsOffset > 0;
  const eventsCanNext = eventsOffset + eventsLimit < eventsTotal;
  const eventsFromRow = eventsTotal === 0 ? 0 : eventsOffset + 1;
  const eventsToRow = Math.min(eventsOffset + eventsLimit, eventsTotal);

  const terminalLines = useMemo(() => {
    return (terminalEvents || []).map((ev) => {
      const time = ev.created_at ? new Date(ev.created_at).toLocaleTimeString('en-US', {
        hour12: false,
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      }) : '??:??:??';
      const label = `${ev.event_type}`;
      const ip = ev.ip_address || '-';
      return `[${time}] ${label} ip=${ip}`;
    });
  }, [terminalEvents]);

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      <FixedHeader />
      <main className="flex-1 min-h-0 px-4 py-6 overflow-auto">
        <div className="max-w-7xl mx-auto flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold">Security Center</h1>
              <p className="text-sm text-gray-600">
                Centralized view of login attempts, security events, and protection policies.
              </p>
            </div>
          </div>

          <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as any)} className="w-full">
            <TabsList>
              <TabsTrigger value="overview">Overview</TabsTrigger>
              <TabsTrigger value="events">Events / Logs</TabsTrigger>
              <TabsTrigger value="settings">Settings</TabsTrigger>
            </TabsList>

            {/* Overview tab */}
            <TabsContent value="overview" className="mt-4 space-y-4">
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm">Summary</CardTitle>
                  <CardDescription className="text-xs text-gray-600">
                    Key security metrics over a recent time window.
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-3 text-sm">
                  <div className="flex items-center gap-3 flex-wrap">
                    <Label className="text-xs">Window (hours)</Label>
                    <Input
                      type="number"
                      min={1}
                      max={24 * 7}
                      value={overviewWindowHours}
                      onChange={(e) => setOverviewWindowHours(Number(e.target.value) || 24)}
                      className="w-24 h-8 text-xs"
                    />
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => void loadOverview(overviewWindowHours)}
                      disabled={overviewLoading}
                    >
                      Refresh
                    </Button>
                  </div>
                  {overviewLoading && (
                    <div className="text-xs text-gray-500">Loading overview…</div>
                  )}
                  {overviewError && (
                    <Alert variant="destructive">
                      <AlertDescription className="text-xs">{overviewError}</AlertDescription>
                    </Alert>
                  )}
                  {overview && !overviewError && (
                    <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mt-2">
                      <Card className="p-3">
                        <div className="text-[11px] text-gray-500">Successful logins</div>
                        <div className="text-xl font-semibold">{overview.metrics.login_success}</div>
                      </Card>
                      <Card className="p-3">
                        <div className="text-[11px] text-gray-500">Failed logins</div>
                        <div className="text-xl font-semibold">{overview.metrics.login_failed}</div>
                      </Card>
                      <Card className="p-3">
                        <div className="text-[11px] text-gray-500">Blocked attempts</div>
                        <div className="text-xl font-semibold">{overview.metrics.login_blocked}</div>
                      </Card>
                      <Card className="p-3">
                        <div className="text-[11px] text-gray-500">Settings changes</div>
                        <div className="text-xl font-semibold">{overview.metrics.settings_changed}</div>
                      </Card>
                      <Card className="p-3">
                        <div className="text-[11px] text-gray-500">Security alerts</div>
                        <div className="text-xl font-semibold">{overview.metrics.security_alert}</div>
                      </Card>
                    </div>
                  )}
                </CardContent>
              </Card>

              {overview && overview.top_failed_ips.length > 0 && (
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm">Top IPs by failed/blocked attempts</CardTitle>
                    <CardDescription className="text-xs text-gray-600">
                      Last {overview.window_hours} hours.
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="text-xs">
                    <table className="w-full text-xs">
                      <thead className="bg-gray-50 border-b">
                        <tr>
                          <th className="px-2 py-1 text-left">IP address</th>
                          <th className="px-2 py-1 text-left">Events</th>
                        </tr>
                      </thead>
                      <tbody>
                        {overview.top_failed_ips.map((row) => (
                          <tr key={row.ip_address} className="border-b last:border-b-0">
                            <td className="px-2 py-1 font-mono text-[11px]">{row.ip_address}</td>
                            <td className="px-2 py-1">{row.count}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </CardContent>
                </Card>
              )}
            </TabsContent>

            {/* Events tab */}
            <TabsContent value="events" className="mt-4 space-y-4">
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm">Filters</CardTitle>
                  <CardDescription className="text-xs text-gray-600">
                    Filter security events by type, user, IP, and time range.
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="grid grid-cols-1 md:grid-cols-4 gap-3 text-xs">
                    <div>
                      <Label className="block text-xs mb-1">Event type</Label>
                      <Input
                        value={filterEventType}
                        onChange={(e) => setFilterEventType(e.target.value)}
                        placeholder="login_failed, login_blocked, …"
                      />
                    </div>
                    <div>
                      <Label className="block text-xs mb-1">User id</Label>
                      <Input
                        value={filterUserId}
                        onChange={(e) => setFilterUserId(e.target.value)}
                        placeholder="UUID"
                      />
                    </div>
                    <div>
                      <Label className="block text-xs mb-1">IP address</Label>
                      <Input
                        value={filterIp}
                        onChange={(e) => setFilterIp(e.target.value)}
                        placeholder="1.2.3.4"
                      />
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                      <div>
                        <Label className="block text-xs mb-1">From</Label>
                        <Input
                          type="datetime-local"
                          value={filterFromLocal}
                          onChange={(e) => setFilterFromLocal(e.target.value)}
                        />
                      </div>
                      <div>
                        <Label className="block text-xs mb-1">To</Label>
                        <Input
                          type="datetime-local"
                          value={filterToLocal}
                          onChange={(e) => setFilterToLocal(e.target.value)}
                        />
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center justify-between gap-3 pt-2 border-t mt-2">
                    <div className="flex items-center gap-2 text-xs">
                      <Label className="text-xs">Page size</Label>
                      <select
                        className="border rounded px-2 py-1 text-xs bg-white"
                        value={eventsLimit}
                        onChange={(e) => setEventsLimit(Number(e.target.value) || 50)}
                      >
                        <option value={20}>20</option>
                        <option value={50}>50</option>
                        <option value={100}>100</option>
                      </select>
                    </div>
                    <div className="flex items-center gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => void loadEvents(0)}
                        disabled={eventsLoading}
                      >
                        Apply
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={async () => {
                          try {
                            const data = await securityApi.exportEvents({
                              event_type: filterEventType || undefined,
                              user_id: filterUserId || undefined,
                              ip: filterIp || undefined,
                              from: filterFromLocal ? new Date(filterFromLocal).toISOString() : undefined,
                              to: filterToLocal ? new Date(filterToLocal).toISOString() : undefined,
                            });
                            const blob = new Blob([JSON.stringify(data.rows, null, 2)], {
                              type: 'application/json',
                            });
                            const url = URL.createObjectURL(blob);
                            const a = document.createElement('a');
                            a.href = url;
                            a.download = 'security-events.json';
                            a.click();
                            URL.revokeObjectURL(url);
                          } catch (e: any) {
                            // eslint-disable-next-line no-console
                            console.error('Failed to export security events', e);
                            const msg = e?.response?.data?.detail || e?.message || 'Failed to export events';
                            toast({ title: 'Export failed', description: msg, variant: 'destructive' });
                          }
                        }}
                        disabled={eventsLoading}
                      >
                        Export JSON
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>

              {eventsError && (
                <Alert variant="destructive">
                  <AlertDescription className="text-xs">{eventsError}</AlertDescription>
                </Alert>
              )}

              <Card>
                <CardContent className="p-0 flex flex-col md:flex-row md:divide-x">
                  <div className="md:w-2/3 p-4 border-b md:border-b-0">
                    <div className="flex items-center justify-between mb-2 text-xs text-gray-600">
                      <span>
                        {eventsLoading
                          ? 'Loading events…'
                          : `Showing ${eventsFromRow}-${eventsToRow} of ${eventsTotal}`}
                      </span>
                      <div className="flex items-center gap-2">
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={!eventsCanPrev || eventsLoading}
                          onClick={() => eventsCanPrev && loadEvents(Math.max(eventsOffset - eventsLimit, 0))}
                        >
                          Previous
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={!eventsCanNext || eventsLoading}
                          onClick={() => eventsCanNext && loadEvents(eventsOffset + eventsLimit)}
                        >
                          Next
                        </Button>
                      </div>
                    </div>
                    <div className="border rounded bg-white overflow-auto max-h-[60vh]">
                      <table className="min-w-full text-xs">
                        <thead className="bg-gray-100 sticky top-0 z-10">
                          <tr>
                            <th className="px-2 py-1 text-left">Time</th>
                            <th className="px-2 py-1 text-left">Event</th>
                            <th className="px-2 py-1 text-left">User</th>
                            <th className="px-2 py-1 text-left">IP</th>
                            <th className="px-2 py-1 text-left">User agent</th>
                            <th className="px-2 py-1 text-left">Description</th>
                          </tr>
                        </thead>
                        <tbody>
                          {eventsLoading && events.length === 0 ? (
                            <tr>
                              <td colSpan={6} className="px-3 py-4 text-center text-gray-500">
                                Loading…
                              </td>
                            </tr>
                          ) : events.length === 0 ? (
                            <tr>
                              <td colSpan={6} className="px-3 py-4 text-center text-gray-500">
                                No events match the current filters.
                              </td>
                            </tr>
                          ) : (
                            events.map((ev) => (
                              <tr key={ev.id} className="border-t hover:bg-indigo-50">
                                <td className="px-2 py-1 whitespace-nowrap">{formatDate(ev.created_at)}</td>
                                <td className="px-2 py-1 whitespace-nowrap font-mono text-[11px]">
                                  {ev.event_type}
                                </td>
                                <td className="px-2 py-1 whitespace-nowrap font-mono text-[11px]">
                                  {ev.user_id || '—'}
                                </td>
                                <td className="px-2 py-1 whitespace-nowrap font-mono text-[11px]">
                                  {ev.ip_address || '—'}
                                </td>
                                <td className="px-2 py-1 max-w-[12rem] truncate" title={ev.user_agent || ''}>
                                  {ev.user_agent || '—'}
                                </td>
                                <td className="px-2 py-1 max-w-[20rem] truncate" title={ev.description || ''}>
                                  {ev.description || '—'}
                                </td>
                              </tr>
                            ))
                          )}
                        </tbody>
                      </table>
                    </div>
                  </div>

                  <div className="md:w-1/3 p-4 bg-gray-50 min-h-[16rem] flex flex-col gap-3">
                    <h2 className="text-sm font-semibold">Terminal view (recent events)</h2>
                    <Card className="flex-1 min-h-0">
                      <CardContent className="p-0">
                        <ScrollArea className="h-72 w-full rounded border bg-black text-gray-100 p-2 font-mono text-[11px]">
                          {terminalLines.length === 0 ? (
                            <div className="text-gray-500 text-xs">No events yet.</div>
                          ) : (
                            <pre className="whitespace-pre-wrap break-words">{terminalLines.join('\n')}</pre>
                          )}
                        </ScrollArea>
                      </CardContent>
                    </Card>
                  </div>
                </CardContent>
              </Card>
            </TabsContent>

            {/* Settings tab */}
            <TabsContent value="settings" className="mt-4 space-y-4">
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm">Security settings</CardTitle>
                  <CardDescription className="text-xs text-gray-600">
                    Configure brute-force limits, session lifetime, and high-level alert thresholds.
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4 text-sm">
                  {settingsLoading && <div className="text-xs text-gray-500">Loading settings…</div>}
                  {settingsError && (
                    <Alert variant="destructive">
                      <AlertDescription className="text-xs">{settingsError}</AlertDescription>
                    </Alert>
                  )}
                  {settings && (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div className="space-y-3">
                        <div>
                          <Label className="block text-xs mb-1">Max failed attempts per series</Label>
                          <Input
                            type="number"
                            min={1}
                            value={settings.max_failed_attempts}
                            onChange={(e) =>
                              setSettings({ ...settings, max_failed_attempts: Number(e.target.value) || 1 })
                            }
                          />
                        </div>
                        <div>
                          <Label className="block text-xs mb-1">Initial block (minutes)</Label>
                          <Input
                            type="number"
                            min={0}
                            value={settings.initial_block_minutes}
                            onChange={(e) =>
                              setSettings({ ...settings, initial_block_minutes: Number(e.target.value) || 0 })
                            }
                          />
                        </div>
                        <div>
                          <Label className="block text-xs mb-1">Progressive delay step (minutes)</Label>
                          <Input
                            type="number"
                            min={0}
                            value={settings.progressive_delay_step_minutes}
                            onChange={(e) =>
                              setSettings({
                                ...settings,
                                progressive_delay_step_minutes: Number(e.target.value) || 0,
                              })
                            }
                          />
                        </div>
                        <div>
                          <Label className="block text-xs mb-1">Max block duration (minutes)</Label>
                          <Input
                            type="number"
                            min={0}
                            value={settings.max_delay_minutes}
                            onChange={(e) =>
                              setSettings({ ...settings, max_delay_minutes: Number(e.target.value) || 0 })
                            }
                          />
                        </div>
                      </div>

                      <div className="space-y-3">
                        <div>
                          <Label className="block text-xs mb-1">Session TTL (minutes)</Label>
                          <Input
                            type="number"
                            min={5}
                            value={settings.session_ttl_minutes}
                            onChange={(e) =>
                              setSettings({ ...settings, session_ttl_minutes: Number(e.target.value) || 60 })
                            }
                          />
                          <p className="text-[11px] text-gray-500 mt-1">
                            Controls the JWT access token expiry for new logins.
                          </p>
                        </div>
                        <div>
                          <Label className="block text-xs mb-1">Idle timeout (minutes)</Label>
                          <Input
                            type="number"
                            min={5}
                            value={settings.session_idle_timeout_minutes}
                            onChange={(e) =>
                              setSettings({
                                ...settings,
                                session_idle_timeout_minutes: Number(e.target.value) || 60,
                              })
                            }
                          />
                        </div>
                        <div>
                          <Label className="block text-xs mb-1">Alert: brute-force threshold per IP</Label>
                          <Input
                            type="number"
                            min={0}
                            value={settings.bruteforce_alert_threshold_per_ip}
                            onChange={(e) =>
                              setSettings({
                                ...settings,
                                bruteforce_alert_threshold_per_ip: Number(e.target.value) || 0,
                              })
                            }
                          />
                        </div>
                        <div>
                          <Label className="block text-xs mb-1">Alert: brute-force threshold per user</Label>
                          <Input
                            type="number"
                            min={0}
                            value={settings.bruteforce_alert_threshold_per_user}
                            onChange={(e) =>
                              setSettings({
                                ...settings,
                                bruteforce_alert_threshold_per_user: Number(e.target.value) || 0,
                              })
                            }
                          />
                        </div>
                        <div>
                          <Label className="block text-xs mb-1">Alert channel hint</Label>
                          <Input
                            value={settings.alert_channel || ''}
                            onChange={(e) =>
                              setSettings({ ...settings, alert_channel: e.target.value || null })
                            }
                            placeholder="email/slack/telegram (placeholder only)"
                          />
                        </div>
                      </div>
                    </div>
                  )}

                  <div className="flex items-center justify-end gap-2 pt-2 border-t mt-2">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => void loadSettings()}
                      disabled={settingsLoading || settingsSaving}
                    >
                      Reload
                    </Button>
                    <Button
                      size="sm"
                      onClick={() => void handleSaveSettings()}
                      disabled={settingsLoading || settingsSaving || !settings}
                    >
                      {settingsSaving ? 'Saving…' : 'Save settings'}
                    </Button>
                  </div>
                </CardContent>
              </Card>
            </TabsContent>
          </Tabs>
        </div>
      </main>
    </div>
  );
}
