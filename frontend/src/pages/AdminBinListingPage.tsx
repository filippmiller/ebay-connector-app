import { useEffect, useMemo, useState } from 'react';
import FixedHeader from '@/components/FixedHeader';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { ebayApi, BinSourcePreviewDto, BinDebugRequestDto, BinDebugResponseDto } from '@/api/ebay';

type RunMode = 'VERIFY' | 'LIST';

function mask(value: string): string {
  if (!value) return '';
  if (value.length <= 6) return '***';
  return `${value.slice(0, 2)}***${value.slice(-2)}`;
}

export default function AdminBinListingPage() {
  const [legacyInventoryId, setLegacyInventoryId] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [source, setSource] = useState<BinSourcePreviewDto | null>(null);

  // Policy / trading config (manual for now)
  const [shippingProfileId, setShippingProfileId] = useState<string>('');
  const [paymentProfileId, setPaymentProfileId] = useState<string>('');
  const [returnProfileId, setReturnProfileId] = useState<string>('');
  const [policiesMode, setPoliciesMode] = useState<'seller_profiles' | 'manual'>('seller_profiles');

  // Manual policies fallback (minimal)
  const [shippingService, setShippingService] = useState<string>('USPSGroundAdvantage');
  const [shippingCost, setShippingCost] = useState<string>('0.0');
  const [returnsWithin, setReturnsWithin] = useState<string>('Days_30');
  const [shippingCostPaidBy, setShippingCostPaidBy] = useState<string>('Seller');

  // Item specifics
  const [brand, setBrand] = useState<string>('Unbranded');
  const [mpn, setMpn] = useState<string>('');
  const [itemType, setItemType] = useState<string>('');
  const [compatibleBrand, setCompatibleBrand] = useState<string>('');

  // Condition selector (from tbl_parts_condition)
  const [conditionsLoading, setConditionsLoading] = useState(false);
  const [conditionsError, setConditionsError] = useState<string | null>(null);
  const [conditions, setConditions] = useState<{ ConditionID: number; ConditionDisplayName?: string | null }[]>([]);
  const [conditionOverride, setConditionOverride] = useState<string>('');

  // Business Policies dictionary (extensible: multi-account + marketplace)
  const accountKey = 'default';
  const marketplaceId = 'EBAY_US';
  const lsKey = (k: string) => `bin_${k}_${accountKey}_${marketplaceId}`;

  // eBay account selector (Trading token source)
  const [accountsLoading, setAccountsLoading] = useState(false);
  const [accountsError, setAccountsError] = useState<string | null>(null);
  const [accounts, setAccounts] = useState<
    { id: string; username?: string | null; house_name?: string | null; marketplace_id?: string | null; site_id?: number | null; is_active: boolean }[]
  >([]);
  const [selectedAccountId, setSelectedAccountId] = useState<string>('');

  const [policiesLoading, setPoliciesLoading] = useState(false);
  const [policiesError, setPoliciesError] = useState<string | null>(null);
  const [policies, setPolicies] = useState<{
    shipping: { policy_id: string; policy_name: string; is_default: boolean; is_active: boolean }[];
    payment: { policy_id: string; policy_name: string; is_default: boolean; is_active: boolean }[];
    return: { policy_id: string; policy_name: string; is_default: boolean; is_active: boolean }[];
  } | null>(null);
  const [location, setLocation] = useState<string>('');
  const [postalCode, setPostalCode] = useState<string>('');
  const [dispatchTimeMax, setDispatchTimeMax] = useState<string>('1');
  const [siteId, setSiteId] = useState<string>('0');
  const [siteCode, setSiteCode] = useState<string>('US');
  const [currency, setCurrency] = useState<string>('USD');
  const [country, setCountry] = useState<string>('US');
  const [listingDuration, setListingDuration] = useState<string>('GTC');
  const [siteIdsLoading, setSiteIdsLoading] = useState(false);
  const [siteIdsError, setSiteIdsError] = useState<string | null>(null);
  const [siteIds, setSiteIds] = useState<
    { site_id: number; site_name?: string | null; global_id?: string | null; territory?: string | null; active: boolean }[]
  >([]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setPoliciesLoading(true);
      setPoliciesError(null);
      try {
        const [list, defaults] = await Promise.all([
          ebayApi.getBusinessPolicies(accountKey, marketplaceId),
          ebayApi.getBusinessPolicyDefaults(accountKey, marketplaceId),
        ]);
        if (cancelled) return;
        setPolicies(list as any);

        const savedShip = localStorage.getItem(lsKey('policy_shipping'));
        const savedPay = localStorage.getItem(lsKey('policy_payment'));
        const savedRet = localStorage.getItem(lsKey('policy_return'));

        const shipId =
          savedShip ||
          defaults.shipping_policy_id ||
          (list.shipping || []).find((p: any) => p.is_default)?.policy_id ||
          '';
        const payId =
          savedPay ||
          defaults.payment_policy_id ||
          (list.payment || []).find((p: any) => p.is_default)?.policy_id ||
          '';
        const retId =
          savedRet ||
          defaults.return_policy_id ||
          (list.return || []).find((p: any) => p.is_default)?.policy_id ||
          '';

        setShippingProfileId(shipId);
        setPaymentProfileId(payId);
        setReturnProfileId(retId);
      } catch (e: any) {
        if (cancelled) return;
        setPoliciesError(String(e?.response?.data?.detail || e?.message || e));
      } finally {
        if (!cancelled) setPoliciesLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setConditionsLoading(true);
      setConditionsError(null);
      try {
        const rows = await ebayApi.getBinConditions(true);
        if (cancelled) return;
        setConditions(rows);
      } catch (e: any) {
        if (cancelled) return;
        setConditionsError(String(e?.response?.data?.detail || e?.message || e));
      } finally {
        if (!cancelled) setConditionsLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setAccountsLoading(true);
      setAccountsError(null);
      try {
        const rows = await ebayApi.getBinEbayAccounts(true);
        if (cancelled) return;
        setAccounts(rows);
        const saved = localStorage.getItem(lsKey('ebay_account_id'));
        const preferred = rows.find((a) => (a.username || '').toLowerCase() === 'mil_243') || rows[0];
        const initial = saved && rows.find((a) => a.id === saved) ? saved : preferred?.id || '';
        setSelectedAccountId(initial);
        if (initial) localStorage.setItem(lsKey('ebay_account_id'), initial);
      } catch (e: any) {
        if (cancelled) return;
        setAccountsError(String(e?.response?.data?.detail || e?.message || e));
      } finally {
        if (!cancelled) setAccountsLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setSiteIdsLoading(true);
      setSiteIdsError(null);
      try {
        const rows = await ebayApi.getBinTradingSiteIds(true);
        if (cancelled) return;
        setSiteIds(rows);
        const us = rows.find((r) => r.site_id === 0) || rows[0];
        if (us) {
          setSiteId(String(us.site_id));
          setSiteCode((us.territory || 'US').toUpperCase());
        }
      } catch (e: any) {
        if (cancelled) return;
        setSiteIdsError(String(e?.response?.data?.detail || e?.message || e));
      } finally {
        if (!cancelled) setSiteIdsLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const [runOpen, setRunOpen] = useState(false);
  const [runMode, setRunMode] = useState<RunMode>('VERIFY');
  const [runLoading, setRunLoading] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [runResp, setRunResp] = useState<BinDebugResponseDto | null>(null);

  const loadSource = async () => {
    const parsed = Number((legacyInventoryId || '').trim());
    if (!Number.isFinite(parsed) || parsed <= 0) {
      setError('Enter a valid legacy Inventory ID (tbl_parts_inventory.ID)');
      setSource(null);
      return;
    }
    try {
      setLoading(true);
      setError(null);
      const data = await ebayApi.getBinSourcePreview(parsed);
      setSource(data);
      // Default condition override to DB value (but allow user override)
      setConditionOverride(String(data.condition_id || ''));
      // If required specifics include Compatible Brand, try to infer from title
      if ((data.required_specifics || []).includes('Compatible Brand')) {
        const t = String(data.title || '').toUpperCase();
        if (!compatibleBrand) {
          if (t.includes(' HP ' ) || t.startsWith('HP ') || t.includes('Genuine HP')) setCompatibleBrand('HP');
        }
      }
    } catch (e: any) {
      // eslint-disable-next-line no-console
      console.error('Failed to load BIN source preview', e);
      setError(e?.response?.data?.detail || e.message || 'Failed to load source');
      setSource(null);
    } finally {
      setLoading(false);
    }
  };

  const checklist = useMemo(() => {
    const items: { key: string; label: string; ok: boolean; value?: any }[] = [];
    const has = (v: any) =>
      v !== null && v !== undefined && String(v).trim() !== '' && String(v).trim() !== '0';
    const hasAllowZero = (v: any) => v !== null && v !== undefined && String(v).trim() !== '';

    items.push({ key: 'db.title', label: 'Item.Title (<=80)', ok: has(source?.title), value: source?.title });

    items.push({
      key: 'cfg.account',
      label: 'eBay account (token source)',
      ok: has(selectedAccountId),
      value: selectedAccountId ? mask(selectedAccountId) : null,
    });
    items.push({
      key: 'db.description',
      label: 'Item.Description (HTML)',
      ok: has(source?.description),
      value: source?.description ? `${String(source.description).slice(0, 40)}…` : null,
    });
    items.push({
      key: 'db.category',
      label: 'Item.PrimaryCategory.CategoryID',
      ok: has(source?.category_id),
      value: source?.category_id,
    });
    if (source?.internal_category_id) {
      items.push({
        key: 'db.category_internal',
        label: 'Internal category (tbl_parts_detail.Category)',
        ok: true,
        value: source.internal_category_id,
      });
    }
    items.push({ key: 'db.price', label: 'Item.StartPrice', ok: has(source?.start_price), value: source?.start_price });
    items.push({ key: 'db.qty', label: 'Item.Quantity', ok: (source?.quantity || 0) > 0, value: source?.quantity });
    items.push({
      key: 'db.condition',
      label: 'Item.ConditionID',
      ok: has(conditionOverride || source?.condition_id),
      value: conditionOverride || source?.condition_id,
    });
    items.push({
      key: 'db.pics',
      label: 'Item.PictureDetails.PictureURL[] (>=1)',
      ok: (source?.picture_urls?.length || 0) > 0,
      value: source?.picture_urls?.length || 0,
    });

    items.push({
      key: 'cfg.site',
      label: 'Trading SiteID (tbl_GlobalSiteID) + Item.Site',
      // SiteID for eBay US is 0 (valid), so allow zero here.
      ok: hasAllowZero(siteId) && hasAllowZero(siteCode),
      value: hasAllowZero(siteId) && hasAllowZero(siteCode) ? `${siteId} / ${siteCode}` : null,
    });
    items.push({ key: 'cfg.duration', label: 'Item.ListingDuration', ok: has(listingDuration), value: listingDuration });
    items.push({ key: 'cfg.currency', label: 'Item.Currency', ok: has(currency), value: currency });
    items.push({ key: 'cfg.country', label: 'Item.Country', ok: has(country), value: country });
    items.push({ key: 'cfg.location', label: 'Item.Location', ok: has(location), value: location });
    items.push({ key: 'cfg.postal', label: 'Item.PostalCode', ok: has(postalCode), value: postalCode });
    items.push({ key: 'cfg.dispatch', label: 'Item.DispatchTimeMax', ok: has(dispatchTimeMax), value: dispatchTimeMax });

    // Item specifics (soft now, but we mark as mandatory to catch typical failures early)
    items.push({ key: 'spec.brand', label: 'ItemSpecifics.Brand', ok: has(brand), value: brand });
    items.push({ key: 'spec.mpn', label: 'ItemSpecifics.MPN', ok: has(mpn) || has(source?.condition_id), value: mpn || 'Does Not Apply' });
    const reqSpecs = new Set((source?.required_specifics || []).map((s) => String(s)));
    if (reqSpecs.has('Type')) {
      items.push({ key: 'spec.type', label: 'ItemSpecifics.Type (required)', ok: has(itemType), value: itemType });
    }
    if (reqSpecs.has('Compatible Brand')) {
      items.push({ key: 'spec.compat_brand', label: 'ItemSpecifics.Compatible Brand (required)', ok: has(compatibleBrand), value: compatibleBrand });
    }

    if (policiesMode === 'seller_profiles') {
      items.push({
        key: 'policy.shipping',
        label: 'SellerProfiles.SellerShippingProfile.ShippingProfileID',
        ok: has(shippingProfileId),
        value: shippingProfileId ? mask(shippingProfileId) : null,
      });
      items.push({
        key: 'policy.payment',
        label: 'SellerProfiles.SellerPaymentProfile.PaymentProfileID',
        ok: has(paymentProfileId),
        value: paymentProfileId ? mask(paymentProfileId) : null,
      });
      items.push({
        key: 'policy.return',
        label: 'SellerProfiles.SellerReturnProfile.ReturnProfileID',
        ok: has(returnProfileId),
        value: returnProfileId ? mask(returnProfileId) : null,
      });
    } else {
      items.push({ key: 'manual.ship', label: 'ShippingDetails.ShippingService (manual)', ok: has(shippingService), value: shippingService });
      items.push({ key: 'manual.cost', label: 'ShippingDetails.ShippingServiceCost (manual)', ok: has(shippingCost), value: shippingCost });
      items.push({ key: 'manual.returns', label: 'ReturnPolicy.ReturnsWithinOption (manual)', ok: has(returnsWithin), value: returnsWithin });
      items.push({ key: 'manual.paidby', label: 'ReturnPolicy.ShippingCostPaidByOption (manual)', ok: has(shippingCostPaidBy), value: shippingCostPaidBy });
    }

    return items;
  }, [
    source,
    selectedAccountId,
    siteId,
    siteCode,
    listingDuration,
    currency,
    country,
    location,
    postalCode,
    dispatchTimeMax,
    shippingProfileId,
    paymentProfileId,
    returnProfileId,
    policiesMode,
    shippingService,
    shippingCost,
    returnsWithin,
    shippingCostPaidBy,
    brand,
    mpn,
    itemType,
    compatibleBrand,
    conditionOverride,
  ]);

  const canRun = useMemo(() => checklist.every((i) => i.ok), [checklist]);

  const run = async (mode: RunMode) => {
    if (!source) return;
    setRunMode(mode);
    setRunOpen(true);
    setRunResp(null);
    setRunError(null);

    const payload: BinDebugRequestDto = {
      legacy_inventory_id: source.legacy_inventory_id,
      account_id: selectedAccountId || undefined,
      policies_mode: policiesMode,
      shipping_profile_id: policiesMode === 'seller_profiles' ? Number(shippingProfileId) : undefined,
      payment_profile_id: policiesMode === 'seller_profiles' ? Number(paymentProfileId) : undefined,
      return_profile_id: policiesMode === 'seller_profiles' ? Number(returnProfileId) : undefined,
      shipping_service: policiesMode === 'manual' ? shippingService : undefined,
      shipping_cost: policiesMode === 'manual' ? shippingCost : undefined,
      returns_within_option: policiesMode === 'manual' ? returnsWithin : undefined,
      shipping_cost_paid_by_option: policiesMode === 'manual' ? shippingCostPaidBy : undefined,
      brand,
      mpn: mpn || 'Does Not Apply',
      item_type: itemType || undefined,
      compatible_brand: compatibleBrand || undefined,
      condition_id_override: conditionOverride || undefined,
      site_id: Number(siteId),
      site_code: siteCode,
      listing_duration: listingDuration,
      currency,
      country,
      location,
      postal_code: postalCode,
      dispatch_time_max: Number(dispatchTimeMax),
    };

    try {
      setRunLoading(true);
      const resp =
        mode === 'VERIFY' ? await ebayApi.verifyBinListing(payload) : await ebayApi.listBinListing(payload);
      setRunResp(resp);
    } catch (e: any) {
      // eslint-disable-next-line no-console
      console.error('BIN run failed', e);
      setRunError(e?.response?.data?.detail || e.message || 'Run failed');
    } finally {
      setRunLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <FixedHeader />
      <main className="w-full pt-14 px-4 sm:px-6 lg:px-10 py-4">
        <div className="w-full mx-auto space-y-4">
          <h1 className="text-xl font-semibold mb-1">eBay BIN Listing Debug (Trading API)</h1>
          <p className="text-xs text-gray-600 max-w-3xl mb-2">
            Учебный стенд: строим XML для <span className="font-mono">VerifyAddFixedPriceItem</span> и{' '}
            <span className="font-mono">AddFixedPriceItem</span>, показываем полный request/response и сохраняем логи.
          </p>

          <Card className="p-0">
            <CardHeader className="py-2 px-3 pb-1 flex items-center justify-between">
              <CardTitle className="text-sm font-semibold">Select legacy inventory row</CardTitle>
            </CardHeader>
            <CardContent className="py-2 px-3 space-y-2 text-xs">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-gray-700">eBay account</span>
                <select
                  className="border rounded px-2 py-1 text-[11px] min-w-[260px]"
                  value={selectedAccountId}
                  onChange={(e) => {
                    setSelectedAccountId(e.target.value);
                    localStorage.setItem(lsKey('ebay_account_id'), e.target.value);
                  }}
                  disabled={accountsLoading}
                >
                  <option value="">Select account…</option>
                  {accounts.map((a) => (
                    <option key={a.id} value={a.id}>
                      {(a.username || a.house_name || a.id) + (a.marketplace_id ? ` • ${a.marketplace_id}` : '')}
                    </option>
                  ))}
                </select>
                {accountsLoading && <span className="text-[11px] text-gray-600">Loading…</span>}
              </div>
              {accountsError && <div className="text-red-600">Failed to load eBay accounts: {accountsError}</div>}

              <div className="flex flex-wrap items-center gap-2">
                <span className="text-gray-700">Legacy Inventory ID</span>
                <input
                  className="border rounded px-2 py-1 text-[11px] w-40"
                  placeholder="e.g. 501610"
                  value={legacyInventoryId}
                  onChange={(e) => setLegacyInventoryId(e.target.value.replace(/[^0-9]/g, ''))}
                />
                <button
                  type="button"
                  className="px-3 py-1 rounded bg-black text-white text-[11px] font-medium hover:bg-gray-800 disabled:bg-gray-300 disabled:cursor-not-allowed"
                  onClick={() => void loadSource()}
                  disabled={loading}
                >
                  {loading ? 'Loading…' : 'Load DB fields'}
                </button>
                {source && (
                  <span className="text-[11px] text-gray-600">
                    SKU={source.sku} • category={source.category_id || '—'} • pics={source.picture_urls.length} •
                    parts_detail_id={source.parts_detail_id ?? '—'}
                  </span>
                )}
              </div>
              {error && <div className="text-red-600">{String(error)}</div>}
              {policiesError && <div className="text-red-600">Failed to load Business Policies: {policiesError}</div>}
              {policiesLoading && <div className="text-[11px] text-gray-600">Loading Business Policies…</div>}
              {source?.condition_id && (
                <div className="text-[11px] text-gray-600">
                  ConditionID={source.condition_id} • {source.condition_display_name || '—'}
                </div>
              )}
            </CardContent>
          </Card>

          <Card className="p-0">
            <CardHeader className="py-2 px-3 pb-1 flex items-center justify-between">
              <CardTitle className="text-sm font-semibold">Trading config + Business Policies</CardTitle>
            </CardHeader>
            <CardContent className="py-2 px-3 space-y-2 text-xs">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div className="md:col-span-3">
                  <div className="text-gray-700 mb-1">Policies mode</div>
                  <div className="flex items-center gap-3 text-[11px]">
                    <label className="flex items-center gap-1">
                      <input
                        type="radio"
                        checked={policiesMode === 'seller_profiles'}
                        onChange={() => setPoliciesMode('seller_profiles')}
                      />
                      <span>SellerProfiles (canonical)</span>
                    </label>
                    <label className="flex items-center gap-1">
                      <input
                        type="radio"
                        checked={policiesMode === 'manual'}
                        onChange={() => setPoliciesMode('manual')}
                      />
                      <span>Manual fallback (shipping+returns)</span>
                    </label>
                  </div>
                </div>

                <div className="md:col-span-3">
                  <div className="text-gray-700 mb-1">Item specifics (recommended/usually required)</div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                    <div>
                      <div className="text-gray-700 mb-1">Brand</div>
                      <input className="border rounded px-2 py-1 text-[11px] w-full" value={brand} onChange={(e) => setBrand(e.target.value)} />
                    </div>
                    <div>
                      <div className="text-gray-700 mb-1">MPN</div>
                      <input
                        className="border rounded px-2 py-1 text-[11px] w-full"
                        value={mpn}
                        onChange={(e) => setMpn(e.target.value)}
                        placeholder="Leave blank to use Does Not Apply"
                      />
                    </div>
                    {(source?.required_specifics || []).includes('Type') && (
                      <div>
                        <div className="text-gray-700 mb-1">Type *</div>
                        <input className="border rounded px-2 py-1 text-[11px] w-full" value={itemType} onChange={(e) => setItemType(e.target.value)} placeholder="e.g. Palmrest / Keyboard / Touchpad" />
                      </div>
                    )}
                    {(source?.required_specifics || []).includes('Compatible Brand') && (
                      <div>
                        <div className="text-gray-700 mb-1">Compatible Brand *</div>
                        <input className="border rounded px-2 py-1 text-[11px] w-full" value={compatibleBrand} onChange={(e) => setCompatibleBrand(e.target.value)} placeholder="e.g. HP" />
                      </div>
                    )}
                  </div>
                </div>

                <div className="md:col-span-3">
                  <div className="text-gray-700 mb-1">Condition (tbl_parts_condition)</div>
                  <select
                    className="border rounded px-2 py-1 text-[11px] w-full"
                    value={conditionOverride}
                    onChange={(e) => setConditionOverride(e.target.value)}
                    disabled={conditionsLoading}
                  >
                    <option value="">(use SKU default)</option>
                    {conditions.map((c) => (
                      <option key={String(c.ConditionID)} value={String(c.ConditionID)}>
                        {c.ConditionID} — {c.ConditionDisplayName || ''}
                      </option>
                    ))}
                  </select>
                  {conditionsError && <div className="text-red-600 text-[11px] mt-1">Failed to load conditions: {conditionsError}</div>}
                </div>
                <div>
                  <div className="text-gray-700 mb-1">Location *</div>
                  <input className="border rounded px-2 py-1 text-[11px] w-full" value={location} onChange={(e) => setLocation(e.target.value)} placeholder="City, State" />
                </div>
                <div>
                  <div className="text-gray-700 mb-1">Postal code *</div>
                  <input className="border rounded px-2 py-1 text-[11px] w-full" value={postalCode} onChange={(e) => setPostalCode(e.target.value)} placeholder="ZIP" />
                </div>
                <div>
                  <div className="text-gray-700 mb-1">DispatchTimeMax *</div>
                  <input className="border rounded px-2 py-1 text-[11px] w-full" value={dispatchTimeMax} onChange={(e) => setDispatchTimeMax(e.target.value.replace(/[^0-9]/g, ''))} />
                </div>

                {policiesMode === 'seller_profiles' ? (
                  <>
                    <div>
                      <div className="text-gray-700 mb-1">Shipping policy *</div>
                      <select
                        className="border rounded px-2 py-1 text-[11px] w-full"
                        value={shippingProfileId}
                        onChange={(e) => {
                          setShippingProfileId(e.target.value);
                          localStorage.setItem(lsKey('policy_shipping'), e.target.value);
                        }}
                        disabled={policiesLoading}
                      >
                        <option value="">Select shipping policy…</option>
                        {(policies?.shipping || []).filter((p) => p.is_active).map((p) => (
                          <option key={p.policy_id} value={p.policy_id}>
                            {p.policy_name} ({p.policy_id})
                          </option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <div className="text-gray-700 mb-1">Payment policy *</div>
                      <select
                        className="border rounded px-2 py-1 text-[11px] w-full"
                        value={paymentProfileId}
                        onChange={(e) => {
                          setPaymentProfileId(e.target.value);
                          localStorage.setItem(lsKey('policy_payment'), e.target.value);
                        }}
                        disabled={policiesLoading}
                      >
                        <option value="">Select payment policy…</option>
                        {(policies?.payment || []).filter((p) => p.is_active).map((p) => (
                          <option key={p.policy_id} value={p.policy_id}>
                            {p.policy_name} ({p.policy_id})
                          </option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <div className="text-gray-700 mb-1">Return policy *</div>
                      <select
                        className="border rounded px-2 py-1 text-[11px] w-full"
                        value={returnProfileId}
                        onChange={(e) => {
                          setReturnProfileId(e.target.value);
                          localStorage.setItem(lsKey('policy_return'), e.target.value);
                        }}
                        disabled={policiesLoading}
                      >
                        <option value="">Select return policy…</option>
                        {(policies?.return || []).filter((p) => p.is_active).map((p) => (
                          <option key={p.policy_id} value={p.policy_id}>
                            {p.policy_name} ({p.policy_id})
                          </option>
                        ))}
                      </select>
                    </div>
                  </>
                ) : (
                  <>
                    <div>
                      <div className="text-gray-700 mb-1">Shipping service</div>
                      <input className="border rounded px-2 py-1 text-[11px] w-full" value={shippingService} onChange={(e) => setShippingService(e.target.value)} />
                    </div>
                    <div>
                      <div className="text-gray-700 mb-1">Shipping cost</div>
                      <input className="border rounded px-2 py-1 text-[11px] w-full" value={shippingCost} onChange={(e) => setShippingCost(e.target.value)} />
                    </div>
                    <div>
                      <div className="text-gray-700 mb-1">Returns within</div>
                      <input className="border rounded px-2 py-1 text-[11px] w-full" value={returnsWithin} onChange={(e) => setReturnsWithin(e.target.value)} />
                    </div>
                    <div>
                      <div className="text-gray-700 mb-1">Return shipping paid by</div>
                      <input className="border rounded px-2 py-1 text-[11px] w-full" value={shippingCostPaidBy} onChange={(e) => setShippingCostPaidBy(e.target.value)} />
                    </div>
                  </>
                )}

                <div className="md:col-span-2">
                  <div className="text-gray-700 mb-1">Trading Site (tbl_GlobalSiteID) *</div>
                  <select
                    className="border rounded px-2 py-1 text-[11px] w-full"
                    value={siteId}
                    onChange={(e) => {
                      const next = e.target.value;
                      setSiteId(next);
                      const row = siteIds.find((r) => String(r.site_id) === String(next));
                      if (row) setSiteCode((row.territory || 'US').toUpperCase());
                    }}
                    disabled={siteIdsLoading}
                  >
                    {siteIds.length === 0 && <option value="0">0 — eBay United States</option>}
                    {siteIds.map((r) => (
                      <option key={r.site_id} value={String(r.site_id)}>
                        {r.site_id} — {r.site_name || r.global_id || r.territory || 'eBay'} ({(r.territory || '').toUpperCase()})
                      </option>
                    ))}
                  </select>
                  {siteIdsError && <div className="text-red-600 text-[11px] mt-1">Failed to load tbl_GlobalSiteID: {siteIdsError}</div>}
                  {siteIdsLoading && <div className="text-[11px] text-gray-600 mt-1">Loading Site IDs…</div>}
                </div>
                <div>
                  <div className="text-gray-700 mb-1">Item.Site (auto)</div>
                  <input className="border rounded px-2 py-1 text-[11px] w-full bg-gray-50" value={siteCode} readOnly />
                </div>
                <div>
                  <div className="text-gray-700 mb-1">ListingDuration</div>
                  <input className="border rounded px-2 py-1 text-[11px] w-full" value={listingDuration} onChange={(e) => setListingDuration(e.target.value)} />
                </div>

                <div>
                  <div className="text-gray-700 mb-1">Currency</div>
                  <input className="border rounded px-2 py-1 text-[11px] w-full" value={currency} onChange={(e) => setCurrency(e.target.value.toUpperCase())} />
                </div>
                <div>
                  <div className="text-gray-700 mb-1">Country</div>
                  <input className="border rounded px-2 py-1 text-[11px] w-full" value={country} onChange={(e) => setCountry(e.target.value.toUpperCase())} />
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="p-0">
            <CardHeader className="py-2 px-3 pb-1 flex items-center justify-between">
              <CardTitle className="text-sm font-semibold">Mandatory checklist</CardTitle>
            </CardHeader>
            <CardContent className="py-2 px-3 space-y-2 text-xs">
              <div className="border rounded bg-white">
                {checklist.map((i) => (
                  <div key={i.key} className="px-2 py-1 border-b last:border-b-0 flex items-center justify-between gap-3">
                    <div className="flex items-center gap-2 min-w-0">
                      <input type="checkbox" checked={i.ok} readOnly />
                      <span className="text-gray-800">{i.label}</span>
                    </div>
                    {i.value != null && (
                      <span className="text-[11px] text-gray-500 font-mono break-all max-w-[50%]">
                        {String(i.value)}
                      </span>
                    )}
                  </div>
                ))}
              </div>

              <div className="flex items-center justify-end gap-2">
                <button
                  type="button"
                  className="px-3 py-1 rounded bg-blue-700 text-white text-[11px] font-medium hover:bg-blue-800 disabled:bg-gray-300 disabled:cursor-not-allowed"
                  onClick={() => void run('VERIFY')}
                  disabled={!source || !canRun || runLoading}
                >
                  VERIFY (safe)
                </button>
                <button
                  type="button"
                  className="px-3 py-1 rounded bg-green-700 text-white text-[11px] font-medium hover:bg-green-800 disabled:bg-gray-300 disabled:cursor-not-allowed"
                  onClick={() => void run('LIST')}
                  disabled={!source || !canRun || runLoading}
                >
                  LIST (real)
                </button>
              </div>
              {!canRun && <div className="text-[11px] text-red-600">Fill all mandatory fields to enable VERIFY/LIST.</div>}
            </CardContent>
          </Card>
        </div>
      </main>

      <Dialog open={runOpen} onOpenChange={(open) => !open && setRunOpen(false)}>
        <DialogContent className="max-w-6xl">
          <DialogHeader>
            <DialogTitle className="text-sm font-semibold">
              {runMode} result (Trading API)
            </DialogTitle>
          </DialogHeader>

          {runLoading && <div className="text-xs text-gray-600">Calling eBay…</div>}
          {runError && <div className="text-xs text-red-600">{String(runError)}</div>}

          {runResp && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 text-xs">
              <div className="border rounded bg-white lg:col-span-2">
                <div className="px-2 py-1 border-b bg-gray-50 font-semibold">Meta + persistence</div>
                <pre className="p-2 text-[11px] whitespace-pre-wrap break-all max-h-[25vh] overflow-auto">
                  {JSON.stringify(
                    {
                      meta: runResp.meta,
                      run_id: runResp.run_id,
                      log_saved: runResp.log_saved,
                      log_error: runResp.log_error ?? null,
                      item_id_saved_to_parts_detail: runResp.item_id_saved_to_parts_detail,
                      item_id_saved_to_map: runResp.item_id_saved_to_map,
                    },
                    null,
                    2,
                  )}
                </pre>
                {!runResp.log_saved && (
                  <div className="px-2 pb-2 text-[11px] text-red-700">
                    WARNING: eBay call executed but log was NOT saved. This is dangerous for debugging.
                  </div>
                )}
                {runResp.mode === 'LIST' && runResp.parsed?.item_id && !runResp.item_id_saved_to_map && (
                  <div className="px-2 pb-2 text-[11px] text-red-700">
                    WARNING: ItemID returned but mapping was NOT saved. Do not continue until this is fixed.
                  </div>
                )}
              </div>
              <div className="border rounded bg-white">
                <div className="px-2 py-1 border-b bg-gray-50 font-semibold">Request XML</div>
                <pre className="p-2 text-[11px] whitespace-pre-wrap break-all max-h-[50vh] overflow-auto">
                  {runResp.request_body_xml}
                </pre>
              </div>
              <div className="border rounded bg-white">
                <div className="px-2 py-1 border-b bg-gray-50 font-semibold">HTTP headers (masked) + URL</div>
                <pre className="p-2 text-[11px] whitespace-pre-wrap break-all max-h-[50vh] overflow-auto">
                  {JSON.stringify({ url: runResp.request_url, headers: runResp.request_headers_masked }, null, 2)}
                </pre>
              </div>
              <div className="border rounded bg-white lg:col-span-2">
                <div className="px-2 py-1 border-b bg-gray-50 font-semibold">
                  Response XML (HTTP {runResp.response_http_status}) • Ack={runResp.parsed?.ack ?? '—'} • ItemID={runResp.parsed?.item_id ?? '—'}
                </div>
                <pre className="p-2 text-[11px] whitespace-pre-wrap break-all max-h-[45vh] overflow-auto">
                  {runResp.response_body_xml}
                </pre>
              </div>
              <div className="border rounded bg-white lg:col-span-2">
                <div className="px-2 py-1 border-b bg-gray-50 font-semibold">Parsed summary</div>
                <pre className="p-2 text-[11px] whitespace-pre-wrap break-all max-h-[35vh] overflow-auto">
                  {JSON.stringify(runResp.parsed, null, 2)}
                </pre>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}


