import { useEffect, useMemo, useState } from 'react';
import FixedHeader from '@/components/FixedHeader';
import api from '@/lib/apiClient';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Checkbox } from '@/components/ui/checkbox';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Separator } from '@/components/ui/separator';

type CandidateRow = {
  order_id: string;
  order_line_item_id: string;
  order_date?: string | null;
  buyer_username?: string | null;
  buyer_name?: string | null;
  ship_to_city?: string | null;
  ship_to_state?: string | null;
  ship_to_postal_code?: string | null;
  ship_to_country_code?: string | null;
  item_id?: string | null;
  sku?: string | null;
  title?: string | null;
  quantity: number;
  inventory_id?: number | null;
  storage_id?: string | null;
  inventory_created_at?: string | null;
  shipping_status?: string | null;
  has_shipping_label: boolean;
};

type RateQuote = {
  carrier_code: string;
  service_code: string;
  service_name: string;
  amount: number;
  currency: string;
  estimated_days?: number | null;
};

type PackageInput = {
  weightOz: string;
  lengthIn: string;
  widthIn: string;
  heightIn: string;
};

type RatesMap = Record<string, RateQuote[]>;
type RateSelectionMap = Record<string, RateQuote>;
type PackageMap = Record<string, PackageInput>;

export default function BulkShippingPage() {
  const [candidates, setCandidates] = useState<CandidateRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [packages, setPackages] = useState<PackageMap>({});
  const [rates, setRates] = useState<RatesMap>({});
  const [rateSelection, setRateSelection] = useState<RateSelectionMap>({});
  const [purchasing, setPurchasing] = useState(false);

  const selectedRows = useMemo(() => candidates.filter((c) => selected.has(c.order_line_item_id)), [candidates, selected]);
  const totalEstimated = useMemo(
    () =>
      Object.values(rateSelection).reduce((sum, r) => {
        return sum + (r?.amount || 0);
      }, 0),
    [rateSelection],
  );

  const loadCandidates = async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await api.get<{ rows: CandidateRow[]; total: number }>('/shipping/bulk/candidates', {
        params: { search: search || undefined, limit: 100 },
      });
      const rows = resp.data.rows || [];
      setCandidates(rows);
      // prune selections
      setSelected((prev) => {
        const next = new Set<string>();
        for (const row of rows) {
          if (prev.has(row.order_line_item_id)) next.add(row.order_line_item_id);
        }
        return next;
      });
    } catch (e: any) {
      setError(e?.response?.data?.detail || e.message || 'Failed to load candidates');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadCandidates();
  }, []);

  const toggleRow = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleAll = () => {
    if (selected.size === candidates.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(candidates.map((c) => c.order_line_item_id)));
    }
  };

  const updatePackage = (lineId: string, field: keyof PackageInput, value: string) => {
    setPackages((prev) => ({
      ...prev,
      [lineId]: { ...(prev[lineId] || { weightOz: '', lengthIn: '', widthIn: '', heightIn: '' }), [field]: value },
    }));
  };

  const requestRates = async () => {
    const items = selectedRows.map((row) => {
      const pkg = packages[row.order_line_item_id] || {};
      const weightOz = Number(pkg.weightOz || 0);
      if (!weightOz) throw new Error(`Set weight for ${row.order_line_item_id}`);
      return {
        orderId: row.order_id,
        orderLineItemId: row.order_line_item_id,
        inventoryId: row.inventory_id,
        weightOz,
        lengthIn: pkg.lengthIn ? Number(pkg.lengthIn) : undefined,
        widthIn: pkg.widthIn ? Number(pkg.widthIn) : undefined,
        heightIn: pkg.heightIn ? Number(pkg.heightIn) : undefined,
        quantity: row.quantity || 1,
      };
    });

    try {
      const resp = await api.post<{ items: { order_line_item_id: string; rates: RateQuote[] }[] }>('/shipping/bulk/rates', {
        items,
      });
      const incoming: RatesMap = {};
      (resp.data.items || []).forEach((i) => {
        incoming[i.order_line_item_id] = i.rates || [];
      });
      setRates(incoming);
      // preselect cheapest
      const selectedRates: RateSelectionMap = {};
      Object.entries(incoming).forEach(([lineId, list]) => {
        if (list.length) {
          const cheapest = [...list].sort((a, b) => a.amount - b.amount)[0];
          selectedRates[lineId] = cheapest;
        }
      });
      setRateSelection(selectedRates);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e.message || 'Failed to fetch rates');
    }
  };

  const purchase = async () => {
    if (!selectedRows.length) return;
    setPurchasing(true);
    try {
      const selections = selectedRows.map((row) => {
        const rate = rateSelection[row.order_line_item_id];
        if (!rate) throw new Error(`Select rate for ${row.order_line_item_id}`);
        const pkg = packages[row.order_line_item_id] || {};
        const weightOz = Number(pkg.weightOz || 0);
        return {
          orderId: row.order_id,
          orderLineItemId: row.order_line_item_id,
          inventoryId: row.inventory_id,
          carrierCode: rate.carrier_code,
          serviceCode: rate.service_code,
          serviceName: rate.service_name,
          amount: rate.amount,
          currency: rate.currency,
          weightOz,
          lengthIn: pkg.lengthIn ? Number(pkg.lengthIn) : undefined,
          widthIn: pkg.widthIn ? Number(pkg.widthIn) : undefined,
          heightIn: pkg.heightIn ? Number(pkg.heightIn) : undefined,
          quantity: row.quantity || 1,
        };
      });
      await api.post('/shipping/bulk/purchase', { selections });
      await loadCandidates();
      setRates({});
      setRateSelection({});
      setSelected(new Set());
    } catch (e: any) {
      setError(e?.response?.data?.detail || e.message || 'Purchase failed');
    } finally {
      setPurchasing(false);
    }
  };

  const renderRates = (row: CandidateRow) => {
    const list = rates[row.order_line_item_id] || [];
    if (!list.length) return <div className="text-xs text-gray-500">No rates yet</div>;

    const carriers = Array.from(new Set(list.map((r) => r.carrier_code)));

    return (
      <Tabs defaultValue={carriers[0] || ''} className="w-full">
        <TabsList className="mb-2">
          {carriers.map((c) => (
            <TabsTrigger key={c} value={c}>
              {c}
            </TabsTrigger>
          ))}
        </TabsList>
        {carriers.map((c) => (
          <TabsContent key={c} value={c}>
            <div className="space-y-2">
              {list
                .filter((r) => r.carrier_code === c)
                .map((r) => {
                  const checked = rateSelection[row.order_line_item_id]?.service_code === r.service_code;
                  return (
                    <label
                      key={r.service_code}
                      className="flex items-start gap-3 border rounded p-2 hover:border-blue-500 cursor-pointer"
                    >
                      <input
                        type="radio"
                        name={`rate-${row.order_line_item_id}`}
                        checked={checked}
                        onChange={() =>
                          setRateSelection((prev) => ({
                            ...prev,
                            [row.order_line_item_id]: r,
                          }))
                        }
                      />
                      <div className="text-sm">
                        <div className="font-medium">
                          {r.service_name} ({r.service_code})
                        </div>
                        <div className="text-gray-600">
                          {r.currency} {r.amount.toFixed(2)} {r.estimated_days ? `• ${r.estimated_days}d` : ''}
                        </div>
                      </div>
                    </label>
                  );
                })}
            </div>
          </TabsContent>
        ))}
      </Tabs>
    );
  };

  return (
    <div className="min-h-screen flex flex-col bg-gray-50">
      <FixedHeader />
      <main className="flex-1 min-h-0 px-4 py-6 overflow-auto">
        <div className="flex flex-col gap-3 w-full">
          <div className="flex items-center justify-between">
            <h1 className="text-3xl font-bold">Bulk Shipping</h1>
            <div className="flex items-center gap-2">
              <Input
                placeholder="Search order / sku / storage"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-64"
              />
              <Button variant="outline" size="sm" onClick={() => void loadCandidates()}>
                Reload
              </Button>
            </div>
          </div>

          {error && <div className="text-red-600 text-sm">{error}</div>}

          <Card className="p-3">
            {loading ? (
              <div className="text-sm text-gray-500">Loading candidates…</div>
            ) : candidates.length === 0 ? (
              <div className="text-sm text-gray-500">No candidates found.</div>
            ) : (
              <table className="w-full text-sm">
                <thead className="bg-gray-50 border-b">
                  <tr>
                    <th className="p-2 w-8">
                      <Checkbox checked={selected.size === candidates.length} onCheckedChange={toggleAll} />
                    </th>
                    <th className="p-2 text-left">Status</th>
                    <th className="p-2 text-left">Order</th>
                    <th className="p-2 text-left">Item</th>
                    <th className="p-2 text-left">Qty</th>
                    <th className="p-2 text-left">Storage</th>
                    <th className="p-2 text-left">Ship to</th>
                    <th className="p-2 text-left">Package</th>
                    <th className="p-2 text-left">Rates</th>
                  </tr>
                </thead>
                <tbody>
                  {candidates.map((row) => {
                    const pkg = packages[row.order_line_item_id] || {};
                    return (
                      <tr key={row.order_line_item_id} className="border-b align-top hover:bg-gray-50">
                        <td className="p-2">
                          <Checkbox checked={selected.has(row.order_line_item_id)} onCheckedChange={() => toggleRow(row.order_line_item_id)} />
                        </td>
                        <td className="p-2">
                          <div className="text-xs">{row.shipping_status || 'New'}</div>
                        </td>
                        <td className="p-2">
                          <div className="font-mono text-xs">{row.order_id}</div>
                          <div className="text-[11px] text-gray-600">{row.order_date ? new Date(row.order_date).toLocaleDateString() : '-'}</div>
                          <div className="text-[11px] text-gray-600">{row.buyer_username || row.buyer_name || '-'}</div>
                        </td>
                        <td className="p-2">
                          <div className="text-xs font-medium truncate max-w-[220px]">{row.title || '-'}</div>
                          <div className="text-[11px] text-gray-600">Item: {row.item_id || '-'}</div>
                          <div className="text-[11px] text-gray-600">SKU: {row.sku || '-'}</div>
                        </td>
                        <td className="p-2 text-xs">{row.quantity}</td>
                        <td className="p-2 text-xs">
                          {row.storage_id || '-'}
                          <div className="text-[11px] text-gray-600">Inv: {row.inventory_id || '—'}</div>
                        </td>
                        <td className="p-2 text-xs">
                          {[row.ship_to_city, row.ship_to_state, row.ship_to_postal_code, row.ship_to_country_code].filter(Boolean).join(', ') || '-'}
                        </td>
                        <td className="p-2 text-xs">
                          <div className="grid grid-cols-2 gap-2">
                            <div>
                              <label className="block text-[11px] text-gray-600 mb-1">Weight (oz)</label>
                              <Input
                                value={pkg.weightOz || ''}
                                onChange={(e) => updatePackage(row.order_line_item_id, 'weightOz', e.target.value)}
                                type="number"
                                min={0}
                              />
                            </div>
                            <div>
                              <label className="block text-[11px] text-gray-600 mb-1">Length (in)</label>
                              <Input
                                value={pkg.lengthIn || ''}
                                onChange={(e) => updatePackage(row.order_line_item_id, 'lengthIn', e.target.value)}
                                type="number"
                                min={0}
                              />
                            </div>
                            <div>
                              <label className="block text-[11px] text-gray-600 mb-1">Width (in)</label>
                              <Input
                                value={pkg.widthIn || ''}
                                onChange={(e) => updatePackage(row.order_line_item_id, 'widthIn', e.target.value)}
                                type="number"
                                min={0}
                              />
                            </div>
                            <div>
                              <label className="block text-[11px] text-gray-600 mb-1">Height (in)</label>
                              <Input
                                value={pkg.heightIn || ''}
                                onChange={(e) => updatePackage(row.order_line_item_id, 'heightIn', e.target.value)}
                                type="number"
                                min={0}
                              />
                            </div>
                          </div>
                        </td>
                        <td className="p-2 align-top text-xs">{renderRates(row)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </Card>

          <Card className="p-3">
            <div className="flex flex-wrap gap-3 items-center">
              <Button size="sm" variant="outline" disabled={!selected.size} onClick={() => void requestRates()}>
                Get rates
              </Button>
              <Button size="sm" disabled={purchasing || !selected.size || !Object.keys(rateSelection).length} onClick={() => void purchase()}>
                {purchasing ? 'Purchasing…' : 'Purchase labels'}
              </Button>
              <Separator orientation="vertical" className="h-6" />
              <div className="text-sm text-gray-700">
                Selected: {selected.size} • Est. total: USD {totalEstimated.toFixed(2)}
              </div>
            </div>
          </Card>
        </div>
      </main>
    </div>
  );
}

