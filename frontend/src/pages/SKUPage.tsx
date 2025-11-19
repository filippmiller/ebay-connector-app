import { useEffect, useMemo, useState } from 'react';
import FixedHeader from '@/components/FixedHeader';
import { DataGridPage } from '@/components/DataGridPage';
import api from '@/lib/apiClient';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

interface SqInternalCategory {
  id: number;
  code: string;
  label: string;
}

interface SqShippingGroup {
  id: number;
  code: string;
  label: string;
}

interface SqCondition {
  id: number;
  code: string;
  label: string;
}

interface SqWarehouse {
  id: number;
  name: string;
  location?: string | null;
  warehouse_type?: string | null;
}

interface SqDictionaries {
  internal_categories: SqInternalCategory[];
  shipping_groups: SqShippingGroup[];
  conditions: SqCondition[];
  warehouses: SqWarehouse[];
  listing_types: { code: string; label: string }[];
  listing_durations: { code: string; label: string; days: number | null }[];
  sites: { code: string; label: string; site_id: number }[];
}

interface SqItemDetail {
  id: number;
  sku?: string | null;
  sku2?: string | null;
  model?: string | null;
  model_id?: number | null;
  part?: string | null;
  category?: string | null;
  description?: string | null;
  title?: string | null;
  brand?: string | null;
  price?: number | null;
  previous_price?: number | null;
  brutto?: number | null;
  shipping_type?: string | null;
  shipping_group?: string | null;
  condition_id?: number | null;
  condition_description?: string | null;
  part_number?: string | null;
  mpn?: string | null;
  upc?: string | null;
  alert_flag?: boolean | null;
  alert_message?: string | null;
  warehouse_id?: number | null;
  storage_alias?: string | null;
  pic_url1?: string | null;
  pic_url2?: string | null;
  pic_url3?: string | null;
  pic_url4?: string | null;
  pic_url5?: string | null;
  pic_url6?: string | null;
  pic_url7?: string | null;
  pic_url8?: string | null;
  pic_url9?: string | null;
  pic_url10?: string | null;
  pic_url11?: string | null;
  pic_url12?: string | null;
  record_created?: string | null;
  record_created_by?: string | null;
  record_updated?: string | null;
  record_updated_by?: string | null;
}

interface SqItemFormState {
  sku: string;
  autoSku: boolean;
  model: string;
  category: string;
  condition_id: string;
  price: string;
  shipping_group: string;
  title: string;
  description: string;
  part_number: string;
  mpn: string;
  upc: string;
  brand: string;
  warehouse_id: string;
  storage_alias: string;
  alert_flag: boolean;
  alert_message: string;
  pic_urls: string[]; // up to 12 urls
}

const emptyFormState = (): SqItemFormState => ({
  sku: '',
  autoSku: true,
  model: '',
  category: '',
  condition_id: '',
  price: '',
  shipping_group: '',
  title: '',
  description: '',
  part_number: '',
  mpn: '',
  upc: '',
  brand: '',
  warehouse_id: '',
  storage_alias: '',
  alert_flag: false,
  alert_message: '',
  pic_urls: Array(12).fill(''),
});

export default function SKUPage() {
  const [dicts, setDicts] = useState<SqDictionaries | null>(null);
  const [dictsError, setDictsError] = useState<string | null>(null);

  const [refreshKey, setRefreshKey] = useState(0);
  const gridParams = useMemo(() => ({ _refresh: refreshKey }), [refreshKey]);

  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<SqItemDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const [createOpen, setCreateOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [formMode, setFormMode] = useState<'create' | 'edit'>('create');
  const [formState, setFormState] = useState<SqItemFormState>(emptyFormState);
  const [formSubmitting, setFormSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const [currentImageIndex, setCurrentImageIndex] = useState(0);

  // Load dictionaries once
  useEffect(() => {
    const loadDictionaries = async () => {
      try {
        const resp = await api.get<SqDictionaries>('/api/sq/dictionaries');
        setDicts(resp.data);
        setDictsError(null);
      } catch (e: any) {
        console.error('Failed to load SQ dictionaries', e);
        setDictsError(e?.response?.data?.detail || e?.message || 'Failed to load dictionaries');
      }
    };

    void loadDictionaries();
  }, []);

  // Load detail when a row is selected
  useEffect(() => {
    const loadDetail = async () => {
      if (!selectedId) {
        setDetail(null);
        return;
      }
      setDetailLoading(true);
      try {
        const resp = await api.get<SqItemDetail>(`/api/sq/items/${selectedId}`);
        setDetail(resp.data);
        setCurrentImageIndex(0);
      } catch (e) {
        console.error('Failed to load SQ item detail', e);
      } finally {
        setDetailLoading(false);
      }
    };

    void loadDetail();
  }, [selectedId]);

  const openCreate = () => {
    setFormMode('create');
    setFormState(emptyFormState());
    setFormError(null);
    setCreateOpen(true);
  };

  const openEdit = () => {
    if (!detail) return;
    const pics: string[] = [
      detail.pic_url1 || '',
      detail.pic_url2 || '',
      detail.pic_url3 || '',
      detail.pic_url4 || '',
      detail.pic_url5 || '',
      detail.pic_url6 || '',
      detail.pic_url7 || '',
      detail.pic_url8 || '',
      detail.pic_url9 || '',
      detail.pic_url10 || '',
      detail.pic_url11 || '',
      detail.pic_url12 || '',
    ];
    setFormMode('edit');
    setFormState({
      sku: detail.sku || '',
      autoSku: false,
      model: detail.model || '',
      category: detail.category || '',
      condition_id: detail.condition_id ? String(detail.condition_id) : '',
      price: detail.price != null ? String(detail.price) : '',
      shipping_group: detail.shipping_group || '',
      title: detail.title || '',
      description: detail.description || '',
      part_number: detail.part_number || '',
      mpn: detail.mpn || '',
      upc: detail.upc || '',
      brand: detail.brand || '',
      warehouse_id: detail.warehouse_id ? String(detail.warehouse_id) : '',
      storage_alias: detail.storage_alias || '',
      alert_flag: !!detail.alert_flag,
      alert_message: detail.alert_message || '',
      pic_urls: pics,
    });
    setFormError(null);
    setEditOpen(true);
  };

  const closeForm = () => {
    setCreateOpen(false);
    setEditOpen(false);
    setFormSubmitting(false);
  };

  const validateForm = (): string | null => {
    if (!formState.model.trim()) return 'Model is required.';
    if (!formState.category.trim()) return 'Internal category is required.';
    if (!formState.condition_id.trim()) return 'Condition is required.';
    if (!formState.price.trim() || isNaN(Number(formState.price))) return 'Price must be a valid number.';
    if (!formState.shipping_group.trim()) return 'Shipping group is required.';
    return null;
  };

  const handleSubmitForm = async () => {
    const err = validateForm();
    if (err) {
      setFormError(err);
      return;
    }

    setFormSubmitting(true);
    setFormError(null);

    const payload: any = {
      sku: formState.autoSku ? undefined : formState.sku || undefined,
      model: formState.model.trim(),
      category: formState.category,
      condition_id: Number(formState.condition_id),
      price: Number(formState.price),
      shipping_group: formState.shipping_group,
      title: formState.title || undefined,
      description: formState.description || undefined,
      part_number: formState.part_number || undefined,
      mpn: formState.mpn || undefined,
      upc: formState.upc || undefined,
      brand: formState.brand || undefined,
      warehouse_id: formState.warehouse_id ? Number(formState.warehouse_id) : undefined,
      storage_alias: formState.storage_alias || undefined,
      alert_flag: formState.alert_flag || undefined,
      alert_message: formState.alert_flag ? formState.alert_message || undefined : undefined,
      pic_url1: formState.pic_urls[0] || undefined,
      pic_url2: formState.pic_urls[1] || undefined,
      pic_url3: formState.pic_urls[2] || undefined,
      pic_url4: formState.pic_urls[3] || undefined,
      pic_url5: formState.pic_urls[4] || undefined,
      pic_url6: formState.pic_urls[5] || undefined,
      pic_url7: formState.pic_urls[6] || undefined,
      pic_url8: formState.pic_urls[7] || undefined,
      pic_url9: formState.pic_urls[8] || undefined,
      pic_url10: formState.pic_urls[9] || undefined,
      pic_url11: formState.pic_urls[10] || undefined,
      pic_url12: formState.pic_urls[11] || undefined,
    };

    try {
      let resp;
      if (formMode === 'create') {
        resp = await api.post<SqItemDetail>('/api/sq/items', payload);
      } else if (detail) {
        resp = await api.put<SqItemDetail>(`/api/sq/items/${detail.id}`, payload);
      }

      if (resp && resp.data) {
        const createdOrUpdated = resp.data;
        setRefreshKey((k) => k + 1);
        setSelectedId(createdOrUpdated.id);
        setDetail(createdOrUpdated);
        closeForm();
      }
    } catch (e: any) {
      console.error('Failed to submit SQ item form', e);
      setFormError(e?.response?.data?.detail || e?.message || 'Failed to save SQ item');
    } finally {
      setFormSubmitting(false);
    }
  };

  const firstImageUrl = useMemo(() => {
    if (!detail) return '';
    const pics = [
      detail.pic_url1,
      detail.pic_url2,
      detail.pic_url3,
      detail.pic_url4,
      detail.pic_url5,
      detail.pic_url6,
      detail.pic_url7,
      detail.pic_url8,
      detail.pic_url9,
      detail.pic_url10,
      detail.pic_url11,
      detail.pic_url12,
    ].filter((u) => !!u) as string[];
    if (pics.length === 0) return '';
    return pics[(currentImageIndex + pics.length) % pics.length];
  }, [detail, currentImageIndex]);

  const cycleImage = (delta: number) => {
    setCurrentImageIndex((idx) => idx + delta);
  };

  const resolveConditionLabel = (conditionId?: number | null): string => {
    if (!conditionId || !dicts) return '-';
    const c = dicts.conditions.find((x) => x.id === conditionId);
    return c ? c.label : String(conditionId);
  };

  const resolveCategoryLabel = (code?: string | null): string => {
    if (!code || !dicts) return code || '-';
    const c = dicts.internal_categories.find((x) => x.code === code || String(x.id) === code);
    return c ? c.label : code;
  };

  const resolveShippingGroupLabel = (code?: string | null): string => {
    if (!code || !dicts) return code || '-';
    const g = dicts.shipping_groups.find((x) => x.code === code || String(x.id) === code);
    return g ? g.label : code;
  };

  const resolveWarehouseLabel = (id?: number | null): string => {
    if (!id || !dicts) return '-';
    const w = dicts.warehouses.find((x) => x.id === id);
    return w ? w.name : String(id);
  };

  return (
    <div className="h-screen flex flex-col bg-gray-50">
      <FixedHeader />
      <div className="pt-16 flex-1 px-4 py-4 overflow-hidden flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold">SQ Catalog (SKU)</h1>
            <p className="text-xs text-gray-500">
              Modern replacement for legacy SQ catalog (tbl_parts_detail). Use this tab to manage per-model spare parts.
            </p>
          </div>
          <div className="flex items-center gap-2">
            {dictsError && <span className="text-xs text-red-600">{dictsError}</span>}
            <Button size="sm" onClick={openCreate}>
              New SKU
            </Button>
          </div>
        </div>

        {/* Main grid + detail layout */}
        <div className="flex-1 min-h-0 flex flex-col gap-3">
          <div className="flex-[2] min-h-0 border rounded-lg bg-white flex flex-col">
            <div className="flex items-center justify-between px-3 py-2 border-b bg-gray-50 text-xs">
              <div className="font-semibold">SQ catalog grid</div>
              <div className="text-gray-500">Click a row to see details below or add to listing.</div>
            </div>
            <div className="flex-1 min-h-0">
              <DataGridPage
                gridKey="sku_catalog"
                title="SQ catalog"
                extraParams={gridParams}
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                onRowClick={(row: any) => {
                  if (row && typeof row.id === 'number') {
                    setSelectedId(row.id);
                  }
                }}
              />
            </div>
          </div>

          {/* Detail panel */}
          {detail && (
            <div className="flex-[1] min-h-[220px] border rounded-lg bg-white flex flex-row gap-4 p-3 text-xs">
              <div className="w-40 flex flex-col items-center gap-2 border-r pr-3">
                {firstImageUrl ? (
                  <img
                    src={firstImageUrl}
                    alt={detail.title || detail.part || detail.sku || 'SQ item'}
                    className="w-36 h-36 object-contain border rounded bg-gray-50"
                  />
                ) : (
                  <div className="w-36 h-36 flex items-center justify-center border rounded bg-gray-50 text-gray-400">
                    No image
                  </div>
                )}
                <div className="flex items-center gap-2">
                  <Button variant="outline" size="sm" onClick={() => cycleImage(-1)} disabled={!firstImageUrl}>
                    ◀
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => cycleImage(1)} disabled={!firstImageUrl}>
                    ▶
                  </Button>
                </div>
              </div>

              <div className="flex-1 grid grid-cols-2 gap-x-6 gap-y-1">
                <div>
                  <div className="font-semibold text-gray-600">Title</div>
                  <div className="text-sm">{detail.title || detail.part || '(no title)'}</div>
                </div>
                <div>
                  <div className="font-semibold text-gray-600">Price</div>
                  <div className="text-sm font-medium">
                    {detail.price != null ? `$${detail.price.toFixed(2)}` : '-'}
                  </div>
                </div>
                <div>
                  <div className="font-semibold text-gray-600">SKU</div>
                  <div className="text-sm font-mono cursor-pointer select-all">{detail.sku || '-'}</div>
                </div>
                <div>
                  <div className="font-semibold text-gray-600">Model</div>
                  <div className="text-sm cursor-default">{detail.model || '-'}</div>
                </div>
                <div>
                  <div className="font-semibold text-gray-600">Internal Category</div>
                  <div className="text-sm">{resolveCategoryLabel(detail.category)}</div>
                </div>
                <div>
                  <div className="font-semibold text-gray-600">Condition</div>
                  <div className="text-sm">{resolveConditionLabel(detail.condition_id)}</div>
                </div>
                <div>
                  <div className="font-semibold text-gray-600">Shipping Group</div>
                  <div className="text-sm">{resolveShippingGroupLabel(detail.shipping_group)}</div>
                </div>
                <div>
                  <div className="font-semibold text-gray-600">Part Number</div>
                  <div className="text-sm font-mono">{detail.part_number || '-'}</div>
                </div>
                <div>
                  <div className="font-semibold text-gray-600">UPC</div>
                  <div className="text-sm font-mono">{detail.upc || '-'}</div>
                </div>
                <div>
                  <div className="font-semibold text-gray-600">MPN</div>
                  <div className="text-sm font-mono">{detail.mpn || '-'}</div>
                </div>
                <div>
                  <div className="font-semibold text-gray-600">Warehouse</div>
                  <div className="text-sm">{resolveWarehouseLabel(detail.warehouse_id)}</div>
                </div>
                <div>
                  <div className="font-semibold text-gray-600">Storage / Alias</div>
                  <div className="text-sm font-mono">{detail.storage_alias || '-'}</div>
                </div>
                <div className="col-span-2">
                  <div className="font-semibold text-gray-600">Description</div>
                  <div className="text-sm whitespace-pre-wrap max-h-20 overflow-auto border rounded p-2 bg-gray-50">
                    {detail.description || '(no description)'}
                  </div>
                </div>
                <div>
                  <div className="font-semibold text-gray-600">Created By</div>
                  <div className="text-sm">
                    {detail.record_created_by || '-'}{' '}
                    {detail.record_created ? `• ${new Date(detail.record_created).toLocaleString()}` : ''}
                  </div>
                </div>
                <div>
                  <div className="font-semibold text-gray-600">Updated By</div>
                  <div className="text-sm">
                    {detail.record_updated_by || '-'}{' '}
                    {detail.record_updated ? `• ${new Date(detail.record_updated).toLocaleString()}` : ''}
                  </div>
                </div>
                {detail.alert_flag && (
                  <div className="col-span-2 mt-1">
                    <div className="font-semibold text-red-600">Alert</div>
                    <div className="text-sm text-red-700 whitespace-pre-wrap">
                      {detail.alert_message || '(no alert message)'}
                    </div>
                  </div>
                )}
              </div>

              <div className="w-32 flex flex-col justify-between items-end gap-2">
                <Button size="sm" variant="outline" onClick={openEdit}>
                  Edit SKU
                </Button>
              </div>
            </div>
          )}

          {!detail && !detailLoading && (
            <div className="flex-[1] min-h-[160px] border rounded-lg bg-white flex items-center justify-center text-xs text-gray-500">
              Select a row in the SQ catalog grid to see detailed information.
            </div>
          )}
        </div>
      </div>

      {/* Create / Edit SKU dialog */}
      <Dialog open={createOpen || editOpen} onOpenChange={closeForm}>
        <DialogContent className="max-w-4xl">
          <DialogHeader>
            <DialogTitle>{formMode === 'create' ? 'Create new SQ item (SKU)' : 'Edit SQ item (SKU)'}</DialogTitle>
            <DialogDescription>
              Fill in the core catalog fields. Advanced template and eBay-specific options will be added later.
            </DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-4 gap-4 text-xs mt-2 max-h-[70vh] overflow-y-auto pr-1">
            {/* Left column: core identifiers */}
            <div className="col-span-4 md:col-span-2 space-y-3">
              <div>
                <label className="block text-[11px] font-semibold mb-1">Title</label>
                <Input
                  value={formState.title}
                  maxLength={80}
                  onChange={(e) => setFormState((s) => ({ ...s, title: e.target.value }))}
                />
                <div className="text-[10px] text-gray-500 mt-0.5">
                  {80 - (formState.title?.length || 0)} characters left
                </div>
              </div>
              <div>
                <label className="block text-[11px] font-semibold mb-1">Model</label>
                <Input
                  value={formState.model}
                  onChange={(e) => setFormState((s) => ({ ...s, model: e.target.value }))}
                />
              </div>
              <div className="flex items-center gap-2">
                <div className="flex-1">
                  <label className="block text-[11px] font-semibold mb-1">SKU</label>
                  <Input
                    value={formState.sku}
                    disabled={formState.autoSku}
                    onChange={(e) => setFormState((s) => ({ ...s, sku: e.target.value }))}
                  />
                </div>
                <div className="flex items-center gap-1 mt-5">
                  <Checkbox
                    checked={formState.autoSku}
                    onCheckedChange={(val) =>
                      setFormState((s) => ({ ...s, autoSku: !!val }))
                    }
                  />
                  <span className="text-[11px]">Auto generated</span>
                </div>
              </div>
              <div>
                <label className="block text-[11px] font-semibold mb-1">Internal Category</label>
                <Select
                  value={formState.category || ''}
                  onValueChange={(v) => setFormState((s) => ({ ...s, category: v }))}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select category" />
                  </SelectTrigger>
                  <SelectContent>
                    {dicts?.internal_categories.map((c) => (
                      <SelectItem key={c.id} value={c.code}>
                        {c.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-[11px] font-semibold mb-1">Condition</label>
                  <Select
                    value={formState.condition_id || ''}
                    onValueChange={(v) => setFormState((s) => ({ ...s, condition_id: v }))}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Select condition" />
                    </SelectTrigger>
                    <SelectContent>
                      {dicts?.conditions.map((c) => (
                        <SelectItem key={c.id} value={String(c.id)}>
                          {c.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <label className="block text-[11px] font-semibold mb-1">Price</label>
                  <Input
                    type="number"
                    step="0.01"
                    value={formState.price}
                    onChange={(e) => setFormState((s) => ({ ...s, price: e.target.value }))}
                  />
                </div>
              </div>
              <div>
                <label className="block text-[11px] font-semibold mb-1">Shipping Group</label>
                <Select
                  value={formState.shipping_group || ''}
                  onValueChange={(v) => setFormState((s) => ({ ...s, shipping_group: v }))}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select group" />
                  </SelectTrigger>
                  <SelectContent>
                    {dicts?.shipping_groups.map((g) => (
                      <SelectItem key={g.id} value={g.code}>
                        {g.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            {/* Middle column: images & shipping / storage */}
            <div className="col-span-4 md:col-span-2 space-y-3">
              <div>
                <label className="block text-[11px] font-semibold mb-1">Images (URLs)</label>
                <div className="grid grid-cols-2 gap-2">
                  {formState.pic_urls.map((url, idx) => (
                    <Input
                      key={idx}
                      placeholder={`Pic ${idx + 1}`}
                      value={url}
                      onChange={(e) => {
                        const next = [...formState.pic_urls];
                        next[idx] = e.target.value;
                        setFormState((s) => ({ ...s, pic_urls: next }));
                      }}
                    />
                  ))}
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-[11px] font-semibold mb-1">Warehouse</label>
                  <Select
                    value={formState.warehouse_id || ''}
                    onValueChange={(v) => setFormState((s) => ({ ...s, warehouse_id: v }))}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Select warehouse" />
                    </SelectTrigger>
                    <SelectContent>
                      {dicts?.warehouses.map((w) => (
                        <SelectItem key={w.id} value={String(w.id)}>
                          {w.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <label className="block text-[11px] font-semibold mb-1">Storage / Alias</label>
                  <Input
                    value={formState.storage_alias}
                    onChange={(e) => setFormState((s) => ({ ...s, storage_alias: e.target.value }))}
                    placeholder="e.g. B16:1"
                  />
                </div>
              </div>
              <div className="grid grid-cols-3 gap-2">
                <div>
                  <label className="block text-[11px] font-semibold mb-1">Part Number</label>
                  <Input
                    value={formState.part_number}
                    onChange={(e) => setFormState((s) => ({ ...s, part_number: e.target.value }))}
                  />
                </div>
                <div>
                  <label className="block text-[11px] font-semibold mb-1">MPN</label>
                  <Input
                    value={formState.mpn}
                    onChange={(e) => setFormState((s) => ({ ...s, mpn: e.target.value }))}
                  />
                </div>
                <div>
                  <label className="block text-[11px] font-semibold mb-1">UPC</label>
                  <Input
                    value={formState.upc}
                    onChange={(e) => setFormState((s) => ({ ...s, upc: e.target.value }))}
                  />
                </div>
              </div>
              <div>
                <label className="block text-[11px] font-semibold mb-1">Brand</label>
                <Input
                  value={formState.brand}
                  onChange={(e) => setFormState((s) => ({ ...s, brand: e.target.value }))}
                />
              </div>
              <div>
                <label className="block text-[11px] font-semibold mb-1">Description</label>
                <Textarea
                  className="min-h-[80px]"
                  value={formState.description}
                  onChange={(e) => setFormState((s) => ({ ...s, description: e.target.value }))}
                />
              </div>
              <div className="flex items-start gap-2 mt-1">
                <Checkbox
                  checked={formState.alert_flag}
                  onCheckedChange={(val) =>
                    setFormState((s) => ({ ...s, alert_flag: !!val }))
                  }
                />
                <div className="flex-1">
                  <div className="text-[11px] font-semibold mb-1">Enable Alert</div>
                  <Textarea
                    className="min-h-[50px]"
                    disabled={!formState.alert_flag}
                    value={formState.alert_message}
                    onChange={(e) => setFormState((s) => ({ ...s, alert_message: e.target.value }))}
                  />
                </div>
              </div>
            </div>
          </div>

          {formError && (
            <div className="mt-2 text-[11px] text-red-600">{formError}</div>
          )}

          <DialogFooter className="mt-3">
            <Button variant="outline" size="sm" onClick={closeForm}>
              Cancel
            </Button>
            <Button size="sm" onClick={handleSubmitForm} disabled={formSubmitting}>
              {formSubmitting ? 'Saving…' : formMode === 'create' ? 'Create SKU' : 'Save changes'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
