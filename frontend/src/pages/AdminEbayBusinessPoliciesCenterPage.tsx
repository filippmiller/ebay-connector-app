import { useEffect, useMemo, useState } from 'react';
import FixedHeader from '@/components/FixedHeader';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { ebayApi, type EbayBusinessPolicyDto, type EbayBusinessPolicyCreateDto } from '@/api/ebay';

function groupAll(p: { shipping: EbayBusinessPolicyDto[]; payment: EbayBusinessPolicyDto[]; return: EbayBusinessPolicyDto[] }) {
  return [
    ...p.shipping.map((x) => ({ ...x, policy_type: 'SHIPPING' as const })),
    ...p.payment.map((x) => ({ ...x, policy_type: 'PAYMENT' as const })),
    ...p.return.map((x) => ({ ...x, policy_type: 'RETURN' as const })),
  ];
}

export default function AdminEbayBusinessPoliciesCenterPage() {
  const [accountKey, setAccountKey] = useState('default');
  const [marketplaceId, setMarketplaceId] = useState('EBAY_US');

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [policies, setPolicies] = useState<{ shipping: EbayBusinessPolicyDto[]; payment: EbayBusinessPolicyDto[]; return: EbayBusinessPolicyDto[] } | null>(null);
  const [accounts, setAccounts] = useState<any[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState<string>('');
  const [deactivateMissing, setDeactivateMissing] = useState(false);

  const [createType, setCreateType] = useState<'SHIPPING' | 'PAYMENT' | 'RETURN'>('SHIPPING');
  const [createPolicyId, setCreatePolicyId] = useState('');
  const [createName, setCreateName] = useState('');
  const [createDescription, setCreateDescription] = useState('');
  const [createIsDefault, setCreateIsDefault] = useState(true);

  const rows = useMemo(() => (policies ? groupAll(policies) : []), [policies]);

  const load = async () => {
    try {
      setLoading(true);
      setError(null);
      const p = await ebayApi.getBusinessPolicies(accountKey, marketplaceId);
      setPolicies(p);
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

  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      try {
        const rows = await ebayApi.getBinEbayAccounts(true);
        if (cancelled) return;
        setAccounts(rows || []);
      } catch {
        // ignore
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleSyncFromEbay = async () => {
    if (!selectedAccountId) {
      setError('Select eBay account to sync from');
      return;
    }
    try {
      setLoading(true);
      setError(null);
      await ebayApi.syncBusinessPoliciesFromEbay({
        account_id: selectedAccountId,
        account_key: accountKey,
        marketplace_id: marketplaceId,
        deactivate_missing: deactivateMissing,
      });
      await load();
    } catch (e: any) {
      setError(String(e?.response?.data?.detail || e?.message || e));
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async () => {
    const policyIdNum = Number(createPolicyId);
    if (!Number.isFinite(policyIdNum) || policyIdNum <= 0) {
      setError('policy_id must be a positive number');
      return;
    }
    if (!createName.trim()) {
      setError('policy_name is required');
      return;
    }

    const payload: EbayBusinessPolicyCreateDto = {
      account_key: accountKey,
      marketplace_id: marketplaceId,
      policy_type: createType,
      policy_id: policyIdNum,
      policy_name: createName.trim(),
      policy_description: createDescription.trim() || null,
      is_default: Boolean(createIsDefault),
      sort_order: 0,
      is_active: true,
    };

    try {
      setLoading(true);
      setError(null);
      await ebayApi.createBusinessPolicy(payload);
      setCreatePolicyId('');
      setCreateName('');
      setCreateDescription('');
      await load();
    } catch (e: any) {
      setError(String(e?.response?.data?.detail || e?.message || e));
    } finally {
      setLoading(false);
    }
  };

  const handleToggleDefault = async (row: EbayBusinessPolicyDto) => {
    try {
      setLoading(true);
      setError(null);
      await ebayApi.updateBusinessPolicy(row.id, { is_default: !row.is_default });
      await load();
    } catch (e: any) {
      setError(String(e?.response?.data?.detail || e?.message || e));
    } finally {
      setLoading(false);
    }
  };

  const handleToggleActive = async (row: EbayBusinessPolicyDto) => {
    try {
      setLoading(true);
      setError(null);
      await ebayApi.updateBusinessPolicy(row.id, { is_active: !row.is_active });
      await load();
    } catch (e: any) {
      setError(String(e?.response?.data?.detail || e?.message || e));
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (row: EbayBusinessPolicyDto) => {
    if (!confirm(`Delete policy ${row.policy_name} (${row.policy_id})?`)) return;
    try {
      setLoading(true);
      setError(null);
      await ebayApi.deleteBusinessPolicy(row.id);
      await load();
    } catch (e: any) {
      setError(String(e?.response?.data?.detail || e?.message || e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <FixedHeader />
      <main className="w-full pt-14 px-4 sm:px-6 lg:px-10 py-4">
        <div className="w-full mx-auto space-y-4">
          <h1 className="text-xl font-semibold">Ebay Business Policies Center</h1>
          <p className="text-xs text-gray-600 max-w-3xl">
            CRUD for Supabase table <span className="font-mono">public.ebay_business_policies</span>. These policy IDs
            are used as Trading API <span className="font-mono">SellerProfiles</span> IDs.
          </p>

          <Card className="p-3">
            <div className="flex flex-wrap items-end gap-2">
              <div className="min-w-[260px]">
                <div className="text-xs text-gray-700 mb-1">Sync source eBay account</div>
                <select
                  className="border rounded px-2 py-1 text-sm h-8 w-full"
                  value={selectedAccountId}
                  onChange={(e) => {
                    const id = e.target.value;
                    setSelectedAccountId(id);
                    const a = (accounts || []).find((x) => String(x.id) === String(id));
                    if (a) {
                      // Recommended: use account.id as account_key so mappings are per-account.
                      setAccountKey(String(a.id));
                      setMarketplaceId(String(a.marketplace_id || 'EBAY_US'));
                    }
                  }}
                  aria-label="eBay account"
                >
                  <option value="">Select account…</option>
                  {(accounts || []).map((a) => (
                    <option key={String(a.id)} value={String(a.id)}>
                      {(a.username || a.house_name || a.id) + (a.marketplace_id ? ` • ${a.marketplace_id}` : '')}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <div className="text-xs text-gray-700 mb-1">account_key</div>
                <Input className="h-8 text-sm w-48" value={accountKey} onChange={(e) => setAccountKey(e.target.value)} />
              </div>
              <div>
                <div className="text-xs text-gray-700 mb-1">marketplace_id</div>
                <Input className="h-8 text-sm w-40" value={marketplaceId} onChange={(e) => setMarketplaceId(e.target.value)} />
              </div>
              <label className="text-xs flex items-center gap-2 h-8 mb-[2px]">
                <input type="checkbox" checked={deactivateMissing} onChange={(e) => setDeactivateMissing(e.target.checked)} />
                deactivate missing
              </label>
              <Button size="sm" onClick={() => void load()} disabled={loading}>
                {loading ? 'Loading…' : 'Reload'}
              </Button>
              <Button size="sm" variant="outline" onClick={() => void handleSyncFromEbay()} disabled={loading}>
                Sync from eBay
              </Button>
            </div>
            {error && <div className="mt-2 text-sm text-red-600">{error}</div>}
          </Card>

          <Card className="p-3">
            <div className="text-sm font-semibold mb-2">Add policy</div>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-2 items-end">
              <div>
                <div className="text-xs text-gray-700 mb-1">type</div>
                <select
                  className="border rounded px-2 py-1 text-sm h-8 w-full"
                  value={createType}
                  onChange={(e) => setCreateType(e.target.value as any)}
                  aria-label="policy type"
                >
                  <option value="SHIPPING">SHIPPING</option>
                  <option value="PAYMENT">PAYMENT</option>
                  <option value="RETURN">RETURN</option>
                </select>
              </div>
              <div>
                <div className="text-xs text-gray-700 mb-1">policy_id</div>
                <Input className="h-8 text-sm" value={createPolicyId} onChange={(e) => setCreatePolicyId(e.target.value.replace(/[^0-9]/g, ''))} />
              </div>
              <div className="md:col-span-2">
                <div className="text-xs text-gray-700 mb-1">policy_name</div>
                <Input className="h-8 text-sm" value={createName} onChange={(e) => setCreateName(e.target.value)} />
              </div>
              <div className="md:col-span-4">
                <div className="text-xs text-gray-700 mb-1">policy_description</div>
                <Textarea className="text-sm" value={createDescription} onChange={(e) => setCreateDescription(e.target.value)} />
              </div>
              <div className="md:col-span-4 flex items-center justify-between">
                <label className="text-xs flex items-center gap-2">
                  <input type="checkbox" checked={createIsDefault} onChange={(e) => setCreateIsDefault(e.target.checked)} />
                  set as default for this scope/type
                </label>
                <Button size="sm" onClick={() => void handleCreate()} disabled={loading}>
                  Add
                </Button>
              </div>
            </div>
          </Card>

          <Card className="p-3">
            <div className="text-sm font-semibold mb-2">Policies</div>
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-gray-600">
                    <th className="py-2 pr-3">type</th>
                    <th className="py-2 pr-3">policy_id</th>
                    <th className="py-2 pr-3">name</th>
                    <th className="py-2 pr-3">default</th>
                    <th className="py-2 pr-3">active</th>
                    <th className="py-2 pr-3">actions</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.id} className="border-t">
                      <td className="py-2 pr-3 font-mono text-xs">{r.policy_type}</td>
                      <td className="py-2 pr-3 font-mono text-xs">{r.policy_id}</td>
                      <td className="py-2 pr-3">{r.policy_name}</td>
                      <td className="py-2 pr-3">
                        <button
                          type="button"
                          className={`px-2 py-1 rounded text-xs border ${r.is_default ? 'bg-green-50 border-green-300' : 'bg-white border-gray-300'}`}
                          onClick={() => void handleToggleDefault(r)}
                          disabled={loading}
                        >
                          {r.is_default ? 'default' : 'set default'}
                        </button>
                      </td>
                      <td className="py-2 pr-3">
                        <button
                          type="button"
                          className={`px-2 py-1 rounded text-xs border ${r.is_active ? 'bg-blue-50 border-blue-300' : 'bg-white border-gray-300'}`}
                          onClick={() => void handleToggleActive(r)}
                          disabled={loading}
                        >
                          {r.is_active ? 'active' : 'inactive'}
                        </button>
                      </td>
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
                      <td colSpan={6} className="py-4 text-xs text-gray-500">
                        No policies found for this scope.
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
