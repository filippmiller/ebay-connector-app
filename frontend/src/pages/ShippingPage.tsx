import { useEffect, useMemo, useState } from 'react';
import FixedHeader from '@/components/FixedHeader';
import api from '@/lib/apiClient';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';

type ShippingJobRow = {
  id: string;
  ebay_account_id?: string | null;
  ebay_order_id?: string | null;
  ebay_order_line_item_ids?: string[];
  buyer_user_id?: string | null;
  buyer_name?: string | null;
  ship_to_address?: Record<string, unknown> | null;
  ship_to_summary?: string | null;
  warehouse_id?: string | null;
  storage_ids?: string[];
  status?: string | null;
  label?: {
    id: string;
    tracking_number?: string | null;
    carrier?: string | null;
    service_name?: string | null;
    voided?: boolean;
  } | null;
  paid_time?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

type ShippingLabelRow = {
  id: string;
  shipping_job_id: string;
  provider?: string | null;
  tracking_number?: string | null;
  carrier?: string | null;
  service_name?: string | null;
  label_url?: string | null;
  label_file_type?: string | null;
  label_cost_amount?: number | null;
  label_cost_currency?: string | null;
  purchased_at?: string | null;
  voided: boolean;
};

export default function ShippingPage() {
  // Awaiting shipment state
  const [awaitingJobs, setAwaitingJobs] = useState<ShippingJobRow[]>([]);
  const [awaitingLoading, setAwaitingLoading] = useState(false);
  const [awaitingError, setAwaitingError] = useState<string | null>(null);
  const [awaitingSelected, setAwaitingSelected] = useState<Set<string>>(new Set());
  const [awaitingSearch, setAwaitingSearch] = useState('');

  // Modals
  const [editPackageOpen, setEditPackageOpen] = useState(false);
  const [manualLabelOpen, setManualLabelOpen] = useState(false);
  const [pkgWeightOz, setPkgWeightOz] = useState('');
  const [pkgLengthIn, setPkgLengthIn] = useState('');
  const [pkgWidthIn, setPkgWidthIn] = useState('');
  const [pkgHeightIn, setPkgHeightIn] = useState('');
  const [pkgType, setPkgType] = useState('');
  const [pkgCarrierPref, setPkgCarrierPref] = useState('');

  const [labelTracking, setLabelTracking] = useState('');
  const [labelCarrier, setLabelCarrier] = useState('');
  const [labelService, setLabelService] = useState('');
  const [labelCost, setLabelCost] = useState('');
  const [savingModal, setSavingModal] = useState(false);

  // Shipping scanner tab
  const [scanTracking, setScanTracking] = useState('');
  const [scanStorage, setScanStorage] = useState('');
  const [scanJob, setScanJob] = useState<ShippingJobRow | null>(null);
  const [scanLoading, setScanLoading] = useState(false);
  const [scanError, setScanError] = useState<string | null>(null);

  // Status tab
  const [statusJobs, setStatusJobs] = useState<ShippingJobRow[]>([]);
  const [statusLoading, setStatusLoading] = useState(false);

  // Labels tab
  const [labels, setLabels] = useState<ShippingLabelRow[]>([]);
  const [labelsLoading, setLabelsLoading] = useState(false);

  const anyAwaitingSelected = awaitingSelected.size > 0;
  const singleAwaitingSelectedId = useMemo(
    () => (awaitingSelected.size === 1 ? Array.from(awaitingSelected)[0] : null),
    [awaitingSelected],
  );

  const loadAwaiting = async () => {
    setAwaitingLoading(true);
    setAwaitingError(null);
    try {
      const resp = await api.get<{ rows: ShippingJobRow[] }>(
        '/shipping/awaiting',
        {
          params: {
            limit: 100,
            offset: 0,
            search: awaitingSearch || undefined,
            include_picking: true,
          },
        },
      );
      setAwaitingJobs(resp.data.rows || []);
      // Drop selections that no longer exist
      setAwaitingSelected((prev) => {
        const ids = new Set(prev);
        const existing = new Set((resp.data.rows || []).map((r) => r.id));
        for (const id of ids) {
          if (!existing.has(id)) ids.delete(id);
        }
        return ids;
      });
    } catch (e: any) {
      setAwaitingError(e?.response?.data?.detail || e.message || 'Failed to load awaiting jobs');
    } finally {
      setAwaitingLoading(false);
    }
  };

  useEffect(() => {
    void loadAwaiting();
  }, []);

  const toggleAwaitingSelect = (id: string) => {
    setAwaitingSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleAwaitingSelectAll = () => {
    if (awaitingSelected.size === awaitingJobs.length) {
      setAwaitingSelected(new Set());
    } else {
      setAwaitingSelected(new Set(awaitingJobs.map((j) => j.id)));
    }
  };

  const handleSendToShipping = async () => {
    if (!anyAwaitingSelected) return;
    const ids = Array.from(awaitingSelected);
    try {
      for (const id of ids) {
        await api.post(`/shipping/jobs/${id}/status`, {
          status: 'PICKING',
          source: 'MANUAL',
          reason: 'Sent to Shipping from UI',
        });
      }
      await loadAwaiting();
    } catch (e) {
      console.error('Failed to update status for jobs', e);
    }
  };

  const handleBulkPackageSave = async () => {
    if (!anyAwaitingSelected) return;
    setSavingModal(true);
    try {
      const items = Array.from(awaitingSelected).map((id) => ({
        shippingJobId: id,
        weightOz: pkgWeightOz ? Number(pkgWeightOz) : undefined,
        lengthIn: pkgLengthIn ? Number(pkgLengthIn) : undefined,
        widthIn: pkgWidthIn ? Number(pkgWidthIn) : undefined,
        heightIn: pkgHeightIn ? Number(pkgHeightIn) : undefined,
        packageType: pkgType || undefined,
        carrierPreference: pkgCarrierPref || undefined,
      }));
      await api.post('/shipping/packages/bulk-update', items);
      setEditPackageOpen(false);
    } catch (e) {
      console.error('Failed to save package info', e);
    } finally {
      setSavingModal(false);
    }
  };

  const handleManualLabelSave = async () => {
    if (!singleAwaitingSelectedId) return;
    setSavingModal(true);
    try {
      await api.post('/shipping/labels/manual', {
        shippingJobId: singleAwaitingSelectedId,
        trackingNumber: labelTracking,
        carrier: labelCarrier,
        serviceName: labelService,
        labelCostAmount: labelCost ? Number(labelCost) : undefined,
      });
      setManualLabelOpen(false);
      setLabelTracking('');
      setLabelCarrier('');
      setLabelService('');
      setLabelCost('');
      setAwaitingSelected(new Set());
      await loadAwaiting();
      await loadStatusJobs();
      await loadLabels();
    } catch (e) {
      console.error('Failed to create manual label', e);
    } finally {
      setSavingModal(false);
    }
  };

  const loadScanJob = async () => {
    setScanLoading(true);
    setScanError(null);
    setScanJob(null);
    try {
      const resp = await api.get<{ rows: ShippingJobRow[] }>('/shipping/jobs', {
        params: {
          limit: 10,
          offset: 0,
          search: scanTracking || scanStorage || undefined,
        },
      });
      const rows = resp.data.rows || [];
      setScanJob(rows[0] || null);
      if (!rows.length) {
        setScanError('No matching shipping job found for the provided criteria');
      }
    } catch (e: any) {
      setScanError(e?.response?.data?.detail || e.message || 'Failed to search shipping jobs');
    } finally {
      setScanLoading(false);
    }
  };

  const handleScanStatusChange = async (status: 'PACKED' | 'SHIPPED') => {
    if (!scanJob) return;
    try {
      const resp = await api.post<ShippingJobRow>(`/shipping/jobs/${scanJob.id}/status`, {
        status,
        source: 'WAREHOUSE_SCAN',
      });
      setScanJob(resp.data);
      await loadStatusJobs();
      await loadAwaiting();
    } catch (e) {
      console.error('Failed to update job status from scanner', e);
    }
  };

  const loadStatusJobs = async () => {
    setStatusLoading(true);
    try {
      const resp = await api.get<{ rows: ShippingJobRow[] }>('/shipping/jobs', {
        params: {
          limit: 200,
          offset: 0,
          exclude_status: 'SHIPPED',
        },
      });
      setStatusJobs(resp.data.rows || []);
    } catch (e) {
      console.error('Failed to load shipping status jobs', e);
    } finally {
      setStatusLoading(false);
    }
  };

  const loadLabels = async () => {
    setLabelsLoading(true);
    try {
      const resp = await api.get<{ rows: ShippingLabelRow[] }>('/shipping/labels', {
        params: { limit: 200, offset: 0 },
      });
      setLabels(resp.data.rows || []);
    } catch (e) {
      console.error('Failed to load shipping labels', e);
    } finally {
      setLabelsLoading(false);
    }
  };

  const formatDateTime = (value?: string | null) => {
    if (!value) return '-';
    try {
      return new Date(value).toLocaleString();
    } catch {
      return value;
    }
  };

  const formatMoney = (amount?: number | null, currency?: string | null) => {
    if (amount == null) return '-';
    return `${currency || 'USD'} ${amount.toFixed(2)}`;
  };

  return (
    <div className="h-screen flex flex-col bg-gray-50">
      <FixedHeader />
      <div className="pt-16 flex-1 px-4 py-6 overflow-hidden">
        <div className="w-full h-full flex flex-col">
          <h1 className="text-3xl font-bold mb-4">Shipping</h1>

          <Tabs defaultValue="awaiting" className="w-full h-full flex flex-col">
            <TabsList>
              <TabsTrigger value="awaiting">Awaiting shipment</TabsTrigger>
              <TabsTrigger value="shipping">Shipping (scanner)</TabsTrigger>
              <TabsTrigger value="status">Status table</TabsTrigger>
              <TabsTrigger value="labels">Labels</TabsTrigger>
            </TabsList>

            <TabsContent value="awaiting" className="mt-4 flex-1 min-h-0 flex flex-col">
              <Card className="p-4 mb-3">
                <div className="flex flex-wrap items-center gap-3">
                  <Input
                    placeholder="Search by order, buyer, or storage..."
                    value={awaitingSearch}
                    onChange={(e) => setAwaitingSearch(e.target.value)}
                    className="w-64"
                  />
                  <Button size="sm" variant="outline" onClick={() => void loadAwaiting()}>
                    Reload
                  </Button>
                  <div className="flex-1" />
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={!anyAwaitingSelected}
                    onClick={() => setEditPackageOpen(true)}
                  >
                    Edit package
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={!singleAwaitingSelectedId}
                    onClick={() => setManualLabelOpen(true)}
                  >
                    Create label (manual)
                  </Button>
                  <Button
                    size="sm"
                    disabled={!anyAwaitingSelected}
                    onClick={() => void handleSendToShipping()}
                  >
                    Send to Shipping
                  </Button>
                </div>
              </Card>

              <Card className="flex-1 min-h-0 overflow-auto">
                {awaitingLoading ? (
                  <div className="p-6 text-sm text-gray-500">Loading awaiting shipment jobs...</div>
                ) : awaitingError ? (
                  <div className="p-6 text-sm text-red-600">{awaitingError}</div>
                ) : awaitingJobs.length === 0 ? (
                  <div className="p-6 text-sm text-gray-500">No jobs awaiting shipment.</div>
                ) : (
                  <table className="w-full text-sm">
                    <thead className="bg-gray-50 border-b">
                      <tr>
                        <th className="p-2 w-8">
                          <Checkbox
                            checked={awaitingSelected.size === awaitingJobs.length && awaitingJobs.length > 0}
                            onCheckedChange={toggleAwaitingSelectAll}
                          />
                        </th>
                        <th className="p-2 text-left">Order</th>
                        <th className="p-2 text-left">Buyer</th>
                        <th className="p-2 text-left">Ship to</th>
                        <th className="p-2 text-left">Storage</th>
                        <th className="p-2 text-left">Status</th>
                        <th className="p-2 text-left">Tracking</th>
                        <th className="p-2 text-left">Paid time</th>
                      </tr>
                    </thead>
                    <tbody>
                      {awaitingJobs.map((job) => (
                        <tr key={job.id} className="border-b hover:bg-gray-50">
                          <td className="p-2 align-top">
                            <Checkbox
                              checked={awaitingSelected.has(job.id)}
                              onCheckedChange={() => toggleAwaitingSelect(job.id)}
                            />
                          </td>
                          <td className="p-2 align-top">
                            <div className="font-mono text-xs">{job.ebay_order_id || '-'}</div>
                            <div className="text-[11px] text-gray-500">{job.ebay_account_id || ''}</div>
                          </td>
                          <td className="p-2 align-top">
                            <div>{job.buyer_name || '-'}</div>
                            <div className="text-[11px] text-gray-500">{job.buyer_user_id || ''}</div>
                          </td>
                          <td className="p-2 align-top text-xs max-w-xs truncate">
                            {job.ship_to_summary || '-'}
                          </td>
                          <td className="p-2 align-top text-xs">
                            {(job.storage_ids || []).join(', ') || '-'}
                          </td>
                          <td className="p-2 align-top text-xs">{job.status || '-'}</td>
                          <td className="p-2 align-top text-xs">
                            {job.label?.tracking_number || '-'}
                          </td>
                          <td className="p-2 align-top text-xs">
                            {formatDateTime(job.paid_time)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </Card>

              {/* Edit package modal */}
              <Dialog open={editPackageOpen} onOpenChange={setEditPackageOpen}>
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle>Edit package for selected jobs</DialogTitle>
                  </DialogHeader>
                  <div className="grid grid-cols-2 gap-3 mt-2 text-sm">
                    <div>
                      <label className="block text-xs text-gray-600 mb-1">Weight (oz)</label>
                      <Input
                        value={pkgWeightOz}
                        onChange={(e) => setPkgWeightOz(e.target.value)}
                        type="number"
                        min={0}
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-gray-600 mb-1">Package type</label>
                      <Input
                        value={pkgType}
                        onChange={(e) => setPkgType(e.target.value)}
                        placeholder="BOX / ENVELOPE / POLYMAILER"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-gray-600 mb-1">Length (in)</label>
                      <Input
                        value={pkgLengthIn}
                        onChange={(e) => setPkgLengthIn(e.target.value)}
                        type="number"
                        min={0}
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-gray-600 mb-1">Width (in)</label>
                      <Input
                        value={pkgWidthIn}
                        onChange={(e) => setPkgWidthIn(e.target.value)}
                        type="number"
                        min={0}
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-gray-600 mb-1">Height (in)</label>
                      <Input
                        value={pkgHeightIn}
                        onChange={(e) => setPkgHeightIn(e.target.value)}
                        type="number"
                        min={0}
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-gray-600 mb-1">Carrier preference</label>
                      <Input
                        value={pkgCarrierPref}
                        onChange={(e) => setPkgCarrierPref(e.target.value)}
                        placeholder="e.g. USPS / UPS / FedEx"
                      />
                    </div>
                  </div>
                  <DialogFooter className="mt-4 flex justify-end gap-2">
                    <Button variant="outline" size="sm" onClick={() => setEditPackageOpen(false)}>
                      Cancel
                    </Button>
                    <Button size="sm" onClick={() => void handleBulkPackageSave()} disabled={savingModal}>
                      {savingModal ? 'Saving…' : 'Save'}
                    </Button>
                  </DialogFooter>
                </DialogContent>
              </Dialog>

              {/* Manual label modal */}
              <Dialog open={manualLabelOpen} onOpenChange={setManualLabelOpen}>
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle>Create manual label</DialogTitle>
                  </DialogHeader>
                  <div className="grid grid-cols-2 gap-3 mt-2 text-sm">
                    <div className="col-span-2">
                      <label className="block text-xs text-gray-600 mb-1">Tracking number</label>
                      <Input
                        value={labelTracking}
                        onChange={(e) => setLabelTracking(e.target.value)}
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-gray-600 mb-1">Carrier</label>
                      <Input
                        value={labelCarrier}
                        onChange={(e) => setLabelCarrier(e.target.value)}
                        placeholder="USPS / UPS / FedEx"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-gray-600 mb-1">Service</label>
                      <Input
                        value={labelService}
                        onChange={(e) => setLabelService(e.target.value)}
                        placeholder="Priority / Ground / First Class"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-gray-600 mb-1">Label cost</label>
                      <Input
                        value={labelCost}
                        onChange={(e) => setLabelCost(e.target.value)}
                        type="number"
                        min={0}
                        step="0.01"
                      />
                    </div>
                  </div>
                  <DialogFooter className="mt-4 flex justify-end gap-2">
                    <Button variant="outline" size="sm" onClick={() => setManualLabelOpen(false)}>
                      Cancel
                    </Button>
                    <Button size="sm" onClick={() => void handleManualLabelSave()} disabled={savingModal}>
                      {savingModal ? 'Saving…' : 'Create label'}
                    </Button>
                  </DialogFooter>
                </DialogContent>
              </Dialog>
            </TabsContent>

            <TabsContent value="shipping" className="mt-4 flex-1 min-h-0 flex flex-col">
              <Card className="p-4 mb-3">
                <div className="flex flex-wrap items-end gap-3">
                  <div className="w-64">
                    <label className="block text-xs text-gray-600 mb-1">Tracking number</label>
                    <Input
                      autoFocus
                      value={scanTracking}
                      onChange={(e) => setScanTracking(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') {
                          e.preventDefault();
                          void loadScanJob();
                        }
                      }}
                    />
                  </div>
                  <div className="w-48">
                    <label className="block text-xs text-gray-600 mb-1">Storage</label>
                    <Input
                      value={scanStorage}
                      onChange={(e) => setScanStorage(e.target.value)}
                    />
                  </div>
                  <Button size="sm" onClick={() => void loadScanJob()}>
                    Find job
                  </Button>
                </div>
              </Card>

              <Card className="flex-1 min-h-0 p-4 overflow-auto">
                {scanLoading ? (
                  <div className="text-sm text-gray-500">Searching for matching job...</div>
                ) : scanError ? (
                  <div className="text-sm text-red-600 mb-2">{scanError}</div>
                ) : null}

                {scanJob && (
                  <div className="space-y-3 text-sm">
                    <div>
                      <span className="font-semibold">Order:</span> {scanJob.ebay_order_id || '-'}
                    </div>
                    <div>
                      <span className="font-semibold">Buyer:</span> {scanJob.buyer_name || '-'} ({
                        scanJob.buyer_user_id || '-'
                      })
                    </div>
                    <div>
                      <span className="font-semibold">Ship to:</span> {scanJob.ship_to_summary || '-'}
                    </div>
                    <div>
                      <span className="font-semibold">Storage:</span> {(scanJob.storage_ids || []).join(', ') || '-'}
                    </div>
                    <div>
                      <span className="font-semibold">Status:</span> {scanJob.status || '-'}
                    </div>
                    <div className="flex gap-3 mt-4">
                      <Button size="lg" variant="secondary" onClick={() => void handleScanStatusChange('PACKED')}>
                        Mark as PACKED (Box)
                      </Button>
                      <Button size="lg" onClick={() => void handleScanStatusChange('SHIPPED')}>
                        Mark as SHIPPED
                      </Button>
                    </div>
                  </div>
                )}

                {!scanJob && !scanLoading && !scanError && (
                  <div className="text-sm text-gray-500">
                    Scan or enter a tracking number or storage ID to locate a shipping job.
                  </div>
                )}
              </Card>
            </TabsContent>

            <TabsContent value="status" className="mt-4 flex-1 min-h-0 flex flex-col">
              <Card className="p-4 mb-3 flex items-center justify-between">
                <div className="text-sm text-gray-600">
                  Jobs with status not equal to SHIPPED. This mirrors the legacy status grid.
                </div>
                <Button size="sm" variant="outline" onClick={() => void loadStatusJobs()}>
                  Reload
                </Button>
              </Card>
              <Card className="flex-1 min-h-0 overflow-auto">
                {statusLoading ? (
                  <div className="p-6 text-sm text-gray-500">Loading shipping jobs...</div>
                ) : statusJobs.length === 0 ? (
                  <div className="p-6 text-sm text-gray-500">No open shipping jobs.</div>
                ) : (
                  <table className="w-full text-sm">
                    <thead className="bg-gray-50 border-b">
                      <tr>
                        <th className="p-2 text-left">Job ID</th>
                        <th className="p-2 text-left">Order</th>
                        <th className="p-2 text-left">Buyer</th>
                        <th className="p-2 text-left">Storage</th>
                        <th className="p-2 text-left">Status</th>
                        <th className="p-2 text-left">Tracking</th>
                        <th className="p-2 text-left">Paid time</th>
                      </tr>
                    </thead>
                    <tbody>
                      {statusJobs.map((job) => (
                        <tr key={job.id} className="border-b hover:bg-gray-50">
                          <td className="p-2 font-mono text-xs align-top">{job.id}</td>
                          <td className="p-2 text-xs align-top">{job.ebay_order_id || '-'}</td>
                          <td className="p-2 text-xs align-top">{job.buyer_name || job.buyer_user_id || '-'}</td>
                          <td className="p-2 text-xs align-top">{(job.storage_ids || []).join(', ') || '-'}</td>
                          <td className="p-2 text-xs align-top">{job.status || '-'}</td>
                          <td className="p-2 text-xs align-top">{job.label?.tracking_number || '-'}</td>
                          <td className="p-2 text-xs align-top">{formatDateTime(job.paid_time)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </Card>
            </TabsContent>

            <TabsContent value="labels" className="mt-4 flex-1 min-h-0 flex flex-col">
              <Card className="p-4 mb-3 flex items-center justify-between">
                <div className="text-sm text-gray-600">
                  All shipping labels created in this system (manual or provider-based).
                </div>
                <Button size="sm" variant="outline" onClick={() => void loadLabels()}>
                  Reload
                </Button>
              </Card>
              <Card className="flex-1 min-h-0 overflow-auto">
                {labelsLoading ? (
                  <div className="p-6 text-sm text-gray-500">Loading labels...</div>
                ) : labels.length === 0 ? (
                  <div className="p-6 text-sm text-gray-500">No labels yet.</div>
                ) : (
                  <table className="w-full text-sm">
                    <thead className="bg-gray-50 border-b">
                      <tr>
                        <th className="p-2 text-left">Created</th>
                        <th className="p-2 text-left">Provider</th>
                        <th className="p-2 text-left">Carrier</th>
                        <th className="p-2 text-left">Service</th>
                        <th className="p-2 text-left">Tracking</th>
                        <th className="p-2 text-left">Cost</th>
                        <th className="p-2 text-left">Status</th>
                        <th className="p-2 text-left">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {labels.map((lbl) => (
                        <tr key={lbl.id} className="border-b hover:bg-gray-50">
                          <td className="p-2 text-xs align-top">{formatDateTime(lbl.purchased_at)}</td>
                          <td className="p-2 text-xs align-top">{lbl.provider || '-'}</td>
                          <td className="p-2 text-xs align-top">{lbl.carrier || '-'}</td>
                          <td className="p-2 text-xs align-top">{lbl.service_name || '-'}</td>
                          <td className="p-2 text-xs align-top font-mono">
                            {lbl.tracking_number || '-'}
                          </td>
                          <td className="p-2 text-xs align-top">
                            {formatMoney(lbl.label_cost_amount ?? null, lbl.label_cost_currency || undefined)}
                          </td>
                          <td className="p-2 text-xs align-top">
                            {lbl.voided ? 'VOIDED' : 'ACTIVE'}
                          </td>
                          <td className="p-2 text-xs align-top space-x-2">
                            {lbl.label_url && (
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => {
                                  window.open(lbl.label_url || 'about:blank', '_blank');
                                }}
                              >
                                Download
                              </Button>
                            )}
                            <Button
                              size="sm"
                              variant={lbl.voided ? 'outline' : 'destructive'}
                              onClick={async () => {
                                try {
                                  await api.post(`/shipping/labels/${lbl.id}/void`, {
                                    voided: !lbl.voided,
                                  });
                                  await loadLabels();
                                } catch (e) {
                                  console.error('Failed to void label', e);
                                }
                              }}
                            >
                              {lbl.voided ? 'Unvoid' : 'Void'}
                            </Button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </Card>
            </TabsContent>
          </Tabs>
        </div>
      </div>
    </div>
  );
}
