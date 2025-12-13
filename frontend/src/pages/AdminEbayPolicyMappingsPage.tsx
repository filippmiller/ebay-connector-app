import { useEffect, useMemo, useState } from 'react';
import FixedHeader from '@/components/FixedHeader';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { ebayApi, type EbayShippingGroupPolicyMappingRow, type EbayShippingGroupPolicyMappingUpsertDto } from '@/api/ebay';
import { useSqDictionaries } from '@/hooks/useSqDictionaries';

export default function AdminEbayPolicyMappingsPage() {
  const { data: dictionaries } = useSqDictionaries();

  const [accountKey, setAccountKey] = useState('default');
  const [marketplaceId, setMarketplaceId] = useState('EBAY_US');

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [rows, setRows] = useState<EbayShippingGroupPolicyMappingRow[]>([]);
  const [coverage, setCoverage] = useState<any>(null);

  // Create/upsert form
  const [shippingGroupId, setShippingGroupId] = useState('');
  const [shippingType, setShippingType] = useState<'Flat' | 'Calculated'>('Flat');
  const [domesticOnly, setDomesticOnly] = useState<'any' | 'true' | 'false'>('any');
  const [shippingPolicyId, setShippingPolicyId] = useState('');
  const [paymentPolicyId, setPaymentPolicyId] = useState('');
  const [returnPolicyId, setReturnPolicyId] = useState('');
  const [notes, setNotes] = useState('');
  const [isActive, setIsActive] = useState(true);

  const businessPolicies = dictionaries?.ebay_business_policies;

  const shippingGroups = useMemo(() => dictionaries?.shipping_groups || [], [dictionaries]);

  const load = async () => {
    try {
      setLoading(true);
      setError(null);
      const resp = await ebayApi.listShippingGroupPolicyMappings(accountKey, marketplaceId);
      setRows(resp.rows || []);
      try {
        const cov = await ebayApi.getShippingGroupPolicyMappingsCoverage(accountKey, marketplaceId);
        setCoverage(cov);
      } catch {
        setCoverage(null);
      }
    } catch (e: any) {
      setError(String(e?.response?.data?.detail || e?.message || e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleUpsert = async () => {
    const sg = Number(shippingGroupId);
    if (!Number.isFinite(sg) || sg <= 0) {
      setError('shipping_group_id must be a positive number');
      return;
    }

    const domFlag = domesticOnly === 'any' ? null : domesticOnly === 'true';

    const payload: EbayShippingGroupPolicyMappingUpsertDto = {
      account_key: accountKey,
      marketplace_id: marketplaceId,
      shipping_group_id: sg,
      shipping_type: shippingType,
      domestic_only_flag: domFlag,
      shipping_policy_id: shippingPolicyId ? Number(shippingPolicyId) : null,
      payment_policy_id: paymentPolicyId ? Number(paymentPolicyId) : null,
      return_policy_id: returnPolicyId ? Number(returnPolicyId) : null,
      is_active: Boolean(isActive),
      notes: notes.trim() || null,
    };

    try {
      setLoading(true);
      setError(null);
      await ebayApi.upsertShippingGroupPolicyMapping(payload);
      await load();
    } catch (e: any) {
      setError(String(e?.response?.data?.detail || e?.message || e));
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (row: EbayShippingGroupPolicyMappingRow) => {
    if (!confirm(`Delete mapping #${row.id}?`)) return;
    try {
      setLoading(true);
      setError(null);
      await ebayApi.deleteShippingGroupPolicyMapping(row.id);
      await load();
    } catch (e: any) {
      setError(String(e?.response?.data?.detail || e?.message || e));
    } finally {
      setLoading(false);
    }
  };

  const handleSeed = async () => {
    if (!confirm('Seed mapping keys for ALL active shipping groups? (Idempotent)')) return;
    try {
      setLoading(true);
      setError(null);
      await ebayApi.seedShippingGroupPolicyMappings({
        account_key: accountKey,
        marketplace_id: marketplaceId,
        include_domestic_variants: true,
        include_shipping_types: ['Flat', 'Calculated'],
        activate_seeded: true,
        notes: 'seeded',
      });
      await load();
    } catch (e: any) {
      setError(String(e?.response?.data?.detail || e?.message || e));
    } finally {
      setLoading(false);
    }
  };

  const handleApplyToSkus = async () => {
    if (!confirm('Bulk apply mappings to SKU policies now? (Writes ebay_sku_business_policies)')) return;
    try {
      setLoading(true);
      setError(null);
      await ebayApi.applyShippingGroupMappingsToSkus({
        account_key: accountKey,
        marketplace_id: marketplaceId,
        only_missing: true,
        limit: 5000,
      });
      await load();
    } catch (e: any) {
      setError(String(e?.response?.data?.detail || e?.message || e));
    } finally {
      setLoading(false);
    }
  };

  const shippingPolicyOptions = (businessPolicies?.shipping || []).filter((p) => p.is_active);
  const paymentPolicyOptions = (businessPolicies?.payment || []).filter((p) => p.is_active);
  const returnPolicyOptions = (businessPolicies?.return || []).filter((p) => p.is_active);

  return (
    <div className="min-h-screen bg-gray-50">
      <FixedHeader />
      <main className="w-full pt-14 px-4 sm:px-6 lg:px-10 py-4">
        <div className="w-full mx-auto space-y-4">
          <h1 className="text-xl font-semibold">eBay Policy Mappings</h1>
          <p className="text-xs text-gray-600 max-w-3xl">
            Map legacy <span className="font-mono">ShippingGroup / ShippingType / DomesticOnly</span> to eBay Business Policy IDs
            (Trading API SellerProfiles). Used for auto-wiring on the SKU form.
          </p>

          <Card className="p-3">
            <div className="flex flex-wrap items-end gap-2">
              <div>
                <div className="text-xs text-gray-700 mb-1">account_key</div>
                <Input className="h-8 text-sm w-48" value={accountKey} onChange={(e) => setAccountKey(e.target.value)} />
              </div>
              <div>
                <div className="text-xs text-gray-700 mb-1">marketplace_id</div>
                <Input className="h-8 text-sm w-40" value={marketplaceId} onChange={(e) => setMarketplaceId(e.target.value)} />
              </div>
              <Button size="sm" onClick={() => void load()} disabled={loading}>
                {loading ? 'Loading…' : 'Reload'}
              </Button>
              <Button size="sm" variant="outline" onClick={() => void handleSeed()} disabled={loading}>
                Seed keys
              </Button>
              <Button size="sm" variant="outline" onClick={() => void handleApplyToSkus()} disabled={loading}>
                Apply to SKUs
              </Button>
            </div>
            {error && <div className="mt-2 text-sm text-red-600">{error}</div>}
            {coverage && (
              <div className="mt-2 text-xs text-gray-600">
                Coverage: {coverage.covered_combinations}/{coverage.expected_combinations} covered • missing:{' '}
                {Array.isArray(coverage.missing) ? coverage.missing.length : '—'}
              </div>
            )}
          </Card>

          <Card className="p-3">
            <div className="text-sm font-semibold mb-2">Upsert mapping</div>
            <div className="grid grid-cols-1 md:grid-cols-6 gap-2 items-end">
              <div className="md:col-span-2">
                <div className="text-xs text-gray-700 mb-1">Shipping group</div>
                <select
                  className="border rounded px-2 py-1 text-sm h-8 w-full"
                  value={shippingGroupId}
                  onChange={(e) => setShippingGroupId(e.target.value)}
                  aria-label="shipping group"
                >
                  <option value="">Select…</option>
                  {shippingGroups.map((g) => (
                    <option key={g.id} value={String(g.code)}>
                      {g.label}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <div className="text-xs text-gray-700 mb-1">Shipping type</div>
                <select
                  className="border rounded px-2 py-1 text-sm h-8 w-full"
                  value={shippingType}
                  onChange={(e) => setShippingType(e.target.value as any)}
                  aria-label="shipping type"
                >
                  <option value="Flat">Flat</option>
                  <option value="Calculated">Calculated</option>
                </select>
              </div>
              <div>
                <div className="text-xs text-gray-700 mb-1">Domestic only</div>
                <select
                  className="border rounded px-2 py-1 text-sm h-8 w-full"
                  value={domesticOnly}
                  onChange={(e) => setDomesticOnly(e.target.value as any)}
                  aria-label="domestic only"
                >
                  <option value="any">Any</option>
                  <option value="true">True</option>
                  <option value="false">False</option>
                </select>
              </div>
              <div>
                <div className="text-xs text-gray-700 mb-1">Active</div>
                <label className="text-xs flex items-center gap-2 h-8">
                  <input type="checkbox" checked={isActive} onChange={(e) => setIsActive(e.target.checked)} />
                  enabled
                </label>
              </div>

              <div className="md:col-span-2">
                <div className="text-xs text-gray-700 mb-1">Shipping policy</div>
                <select
                  className="border rounded px-2 py-1 text-sm h-8 w-full"
                  value={shippingPolicyId}
                  onChange={(e) => setShippingPolicyId(e.target.value)}
                  aria-label="shipping policy"
                >
                  <option value="">(none)</option>
                  {shippingPolicyOptions.map((p) => (
                    <option key={p.id} value={String(p.policy_id)}>
                      {p.policy_name} ({p.policy_id})
                    </option>
                  ))}
                </select>
              </div>
              <div className="md:col-span-2">
                <div className="text-xs text-gray-700 mb-1">Payment policy</div>
                <select
                  className="border rounded px-2 py-1 text-sm h-8 w-full"
                  value={paymentPolicyId}
                  onChange={(e) => setPaymentPolicyId(e.target.value)}
                  aria-label="payment policy"
                >
                  <option value="">(none)</option>
                  {paymentPolicyOptions.map((p) => (
                    <option key={p.id} value={String(p.policy_id)}>
                      {p.policy_name} ({p.policy_id})
                    </option>
                  ))}
                </select>
              </div>
              <div className="md:col-span-2">
                <div className="text-xs text-gray-700 mb-1">Return policy</div>
                <select
                  className="border rounded px-2 py-1 text-sm h-8 w-full"
                  value={returnPolicyId}
                  onChange={(e) => setReturnPolicyId(e.target.value)}
                  aria-label="return policy"
                >
                  <option value="">(none)</option>
                  {returnPolicyOptions.map((p) => (
                    <option key={p.id} value={String(p.policy_id)}>
                      {p.policy_name} ({p.policy_id})
                    </option>
                  ))}
                </select>
              </div>

              <div className="md:col-span-6">
                <div className="text-xs text-gray-700 mb-1">Notes</div>
                <Textarea className="text-sm" value={notes} onChange={(e) => setNotes(e.target.value)} />
              </div>

              <div className="md:col-span-6 flex justify-end">
                <Button size="sm" onClick={() => void handleUpsert()} disabled={loading}>
                  Save mapping
                </Button>
              </div>
            </div>
          </Card>

          <Card className="p-3">
            <div className="text-sm font-semibold mb-2">Existing mappings</div>
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-gray-600">
                    <th className="py-2 pr-3">group</th>
                    <th className="py-2 pr-3">type</th>
                    <th className="py-2 pr-3">domestic</th>
                    <th className="py-2 pr-3">shipping</th>
                    <th className="py-2 pr-3">payment</th>
                    <th className="py-2 pr-3">return</th>
                    <th className="py-2 pr-3">active</th>
                    <th className="py-2 pr-3">actions</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.id} className="border-t">
                      <td className="py-2 pr-3 font-mono text-xs">{r.shipping_group_id}</td>
                      <td className="py-2 pr-3 font-mono text-xs">{r.shipping_type}</td>
                      <td className="py-2 pr-3 font-mono text-xs">{r.domestic_only_flag == null ? 'any' : String(r.domestic_only_flag)}</td>
                      <td className="py-2 pr-3 font-mono text-xs">{r.shipping_policy_id || '—'}</td>
                      <td className="py-2 pr-3 font-mono text-xs">{r.payment_policy_id || '—'}</td>
                      <td className="py-2 pr-3 font-mono text-xs">{r.return_policy_id || '—'}</td>
                      <td className="py-2 pr-3 text-xs">{r.is_active ? 'yes' : 'no'}</td>
                      <td className="py-2 pr-3">
                        <button
                          type="button"
                          className="px-2 py-1 rounded text-xs border border-red-300 bg-red-50"
                          onClick={() => void handleDelete(r)}
                          disabled={loading}
                        >
                          delete
                        </button>
                      </td>
                    </tr>
                  ))}
                  {!rows.length && (
                    <tr>
                      <td colSpan={8} className="py-4 text-xs text-gray-500">
                        No mappings found.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      </main>
    </div>
  );
}
