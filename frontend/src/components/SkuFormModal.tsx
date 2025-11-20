import { useEffect, useMemo, useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Button } from '@/components/ui/button';
import api from '@/lib/apiClient';
import { useToast } from '@/hooks/use-toast';
import { useSqDictionaries, type DictionariesResponse } from '@/hooks/useSqDictionaries';

export type SkuFormMode = 'create' | 'edit';

interface SkuFormModalProps {
  open: boolean;
  mode: SkuFormMode;
  skuId?: number | null;
  /** Called after successful save with the saved SKU ID. */
  onSaved: (id: number) => void;
  onClose: () => void;
}

interface SkuFormState {
  title: string;
  model: string;
  // SKU & category
  autoSku: boolean;
  sku: string;
  categoryType: 'internal' | 'ebay';
  internalCategoryCode: string; // maps to SqItem.category
  externalCategoryId: string;
  externalCategoryName: string;
  // Images
  pics: string[]; // length 12
  // Shipping
  shippingGroupCode: string;
  shippingType: 'Flat' | 'Calculated';
  domesticOnly: boolean;
  // Identifiers & condition
  upc: string;
  upcDoesNotApply: boolean;
  partNumber: string;
  part: string;
  mpn: string;
  conditionId: string; // store as string for Select
  gradeId: string;
  hasColor: boolean;
  colorValue: string;
  hasEpid: boolean;
  epidValue: string;
  // Price & weight
  price: string;
  weight: string;
  unit: string;
  // Listing settings
  listingType: string;
  listingDuration: string;
  siteId: string;
  oneTimeAuction: boolean;
  useMotors: boolean;
  // Descriptions
  conditionDescription: string;
  description: string;
  // Alerts / advanced
  alertEnabled: boolean;
  alertMessage: string;
}

const EMPTY_FORM: SkuFormState = {
  title: '',
  model: '',
  autoSku: true,
  sku: '',
  categoryType: 'internal',
  internalCategoryCode: '',
  externalCategoryId: '',
  externalCategoryName: '',
  pics: Array(12).fill(''),
  shippingGroupCode: '',
  shippingType: 'Flat',
  domesticOnly: false,
  upc: '',
  upcDoesNotApply: false,
  partNumber: '',
  part: '',
  mpn: '',
  conditionId: '',
  gradeId: '',
  hasColor: false,
  colorValue: '',
  hasEpid: false,
  epidValue: '',
  price: '',
  weight: '',
  unit: 'oz',
  listingType: 'FixedPriceItem',
  listingDuration: 'GTC',
  siteId: '',
  oneTimeAuction: false,
  useMotors: false,
  conditionDescription: '',
  description: '',
  alertEnabled: false,
  alertMessage: '',
};

export function SkuFormModal({ open, mode, skuId, onSaved, onClose }: SkuFormModalProps) {
  const { toast } = useToast();

  const { data: dictionaries, loading: dictionariesLoading, error: dictionariesError } = useSqDictionaries();
  const [loadingItem, setLoadingItem] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState<SkuFormState>(EMPTY_FORM);
  const [errors, setErrors] = useState<Record<string, string>>({});

  // Derived counters
  const titleRemaining = useMemo(() => 80 - (form.title?.length ?? 0), [form.title]);
  const conditionDescRemaining = useMemo(
    () => 1000 - (form.conditionDescription?.length ?? 0),
    [form.conditionDescription],
  );

  // Surface dictionary loading errors via toast once when the modal opens.
  useEffect(() => {
    if (!open) return;
    if (!dictionariesError) return;
    toast({ title: 'Failed to load SQ dictionaries', description: dictionariesError, variant: 'destructive' });
  }, [open, dictionariesError, toast]);

  // Reset / prefill form when modal mode or target changes.
  useEffect(() => {
    if (!open) return;

    setErrors({});

    if (mode === 'create') {
      setForm((prev) => ({
        ...EMPTY_FORM,
        // Preserve last selected unit / listing basics across opens for convenience.
        unit: prev.unit || 'oz',
        listingType: prev.listingType || 'FixedPriceItem',
        listingDuration: prev.listingDuration || 'GTC',
        siteId: prev.siteId || prev.siteId,
      }));
      return;
    }

    if (!skuId) return;

    const loadItem = async () => {
      try {
        setLoadingItem(true);
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const resp = await api.get<any>(`/api/sq/items/${skuId}`);
        const item = resp.data || {};

        const pics: string[] = [];
        for (let i = 1; i <= 12; i += 1) {
          pics.push(item[`pic_url${i}`] || '');
        }

        const external = Boolean(item.external_category_flag);

        setForm({
          title: item.title || '',
          model: item.model || '',
          autoSku: !item.sku,
          sku: item.sku != null ? String(item.sku) : '',
          categoryType: external ? 'ebay' : 'internal',
          internalCategoryCode: !external && item.category != null ? String(item.category) : '',
          externalCategoryId: external && item.external_category_id != null ? String(item.external_category_id) : '',
          externalCategoryName: external && item.external_category_name ? String(item.external_category_name) : '',
          pics,
          shippingGroupCode: item.shipping_group != null ? String(item.shipping_group) : '',
          shippingType: (item.shipping_type as 'Flat' | 'Calculated') || 'Flat',
          domesticOnly: Boolean(item.domestic_only_flag),
          upc: item.upc === 'Does not apply' ? '' : item.upc || '',
          upcDoesNotApply: item.upc === 'Does not apply',
          partNumber: item.part_number || '',
          part: item.part || '',
          mpn: item.mpn || '',
          conditionId: item.condition_id != null ? String(item.condition_id) : '',
          gradeId: item.item_grade_id != null ? String(item.item_grade_id) : '',
          hasColor: Boolean(item.color_flag),
          colorValue: item.color_value || '',
          hasEpid: Boolean(item.epid_flag),
          epidValue: item.epid_value || '',
          price: item.price != null ? String(item.price) : '',
          weight: item.weight != null ? String(item.weight) : '',
          unit: item.unit || 'oz',
          listingType: item.listing_type || 'FixedPriceItem',
          listingDuration: item.listing_duration || 'GTC',
          siteId: item.site_id != null ? String(item.site_id) : '',
          oneTimeAuction: Boolean(item.one_time_auction),
          useMotors: Boolean(item.use_ebay_motors_site_flag),
          conditionDescription: item.condition_description || '',
          description: item.description || '',
          alertEnabled: Boolean(item.alert_flag),
          alertMessage: item.alert_message || '',
        });
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      } catch (e: any) {
        toast({
          title: 'Failed to load SKU',
          description: String(e?.response?.data?.detail || e.message || e),
          variant: 'destructive',
        });
      } finally {
        setLoadingItem(false);
      }
    };

    void loadItem();
  }, [open, mode, skuId, toast]);

  const conditionOptions = dictionaries?.conditions ?? [];
  const defaultUsedConditionId = useMemo(() => {
    if (!conditionOptions.length) return '';
    const used = conditionOptions.find((c) => c.code.toUpperCase() === 'USED');
    return used?.id != null ? String(used.id) : String(conditionOptions[0].id);
  }, [conditionOptions]);

  // Ensure we always have a condition default in create mode once dictionaries load.
  useEffect(() => {
    if (!open || mode !== 'create' || !dictionaries) return;
    setForm((prev) => ({
      ...prev,
      conditionId: prev.conditionId || defaultUsedConditionId,
      listingType: prev.listingType || dictionaries.listing_types[0]?.code || 'FixedPriceItem',
      listingDuration: prev.listingDuration || dictionaries.listing_durations[0]?.code || 'GTC',
      siteId:
        prev.siteId ||
        (dictionaries.sites.length ? String(dictionaries.sites[0].site_id ?? '') : prev.siteId),
    }));
  }, [open, mode, dictionaries, defaultUsedConditionId]);

  const handleChange = (field: keyof SkuFormState, value: any) => {
    setForm((prev) => ({ ...prev, [field]: value }));
  };

  const handlePicChange = (index: number, value: string) => {
    setForm((prev) => {
      const next = [...prev.pics];
      next[index] = value;
      return { ...prev, pics: next };
    });
  };

  const validate = (): boolean => {
    const nextErrors: Record<string, string> = {};

    if (!form.title.trim()) {
      nextErrors.title = 'Title is required';
    } else if (form.title.length > 80) {
      nextErrors.title = 'Max 80 characters';
    }

    if (!form.model.trim()) {
      nextErrors.model = 'Model is required';
    }

    if (!form.autoSku && !form.sku.trim()) {
      nextErrors.sku = 'SKU is required when Auto Generated is off';
    }

    if (form.categoryType === 'internal') {
      if (!form.internalCategoryCode.trim()) {
        nextErrors.category = 'Internal category is required';
      }
    } else {
      if (!form.externalCategoryId.trim() && !form.externalCategoryName.trim()) {
        nextErrors.externalCategory = 'Provide external category ID or name';
      }
    }

    const priceNum = Number(form.price.replace(',', '.'));
    if (!form.price.trim() || Number.isNaN(priceNum) || priceNum <= 0) {
      nextErrors.price = 'Price must be a positive number';
    }

    if (!form.shippingGroupCode.trim()) {
      nextErrors.shippingGroupCode = 'Shipping group is required';
    }

    if (!form.conditionId) {
      nextErrors.conditionId = 'Condition is required';
    }

    setErrors(nextErrors);
    return Object.keys(nextErrors).length === 0;
  };

  const handleSubmit = async () => {
    if (!validate()) return;

    const isCreate = mode === 'create';

    const priceNum = Number(form.price.replace(',', '.'));
    const weightNum = form.weight.trim() ? Number(form.weight.replace(',', '.')) : null;

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const payload: any = {
      title: form.title.trim(),
      model: form.model.trim(),
      // SKU: omit when autoSku is enabled so backend generates next number.
      sku: form.autoSku ? undefined : form.sku.trim() || undefined,
      // Internal category uses the numeric/string code stored in SqInternalCategory.code
      category: form.categoryType === 'internal' ? form.internalCategoryCode.trim() || null : null,
      external_category_flag: form.categoryType === 'ebay',
      external_category_id: form.categoryType === 'ebay' && form.externalCategoryId.trim()
        ? form.externalCategoryId.trim()
        : null,
      external_category_name: form.categoryType === 'ebay' && form.externalCategoryName.trim()
        ? form.externalCategoryName.trim()
        : null,
      price: priceNum,
      shipping_group: form.shippingGroupCode.trim(),
      shipping_type: form.shippingType,
      domestic_only_flag: form.domesticOnly || undefined,
      upc: form.upcDoesNotApply ? 'Does not apply' : form.upc.trim() || null,
      part_number: form.partNumber.trim() || null,
      part: form.part.trim() || null,
      mpn: form.mpn.trim() || null,
      condition_id: form.conditionId ? Number(form.conditionId) : null,
      item_grade_id: form.gradeId ? Number(form.gradeId) : null,
      color_flag: form.hasColor || undefined,
      color_value: form.hasColor ? form.colorValue.trim() || null : null,
      epid_flag: form.hasEpid || undefined,
      epid_value: form.hasEpid ? form.epidValue.trim() || null : null,
      weight: weightNum,
      unit: form.unit || null,
      listing_type: form.listingType,
      listing_duration: form.listingDuration,
      site_id: form.siteId ? Number(form.siteId) : null,
      one_time_auction: form.oneTimeAuction || undefined,
      use_ebay_motors_site_flag: form.useMotors || undefined,
      condition_description: form.conditionDescription,
      description: form.description,
      alert_flag: form.alertEnabled || undefined,
      alert_message: form.alertEnabled ? form.alertMessage.trim() || null : null,
    };

    // Pictures
    form.pics.forEach((value, idx) => {
      if (value && value.trim()) {
        payload[`pic_url${idx + 1}`] = value.trim();
      } else {
        payload[`pic_url${idx + 1}`] = null;
      }
    });

    try {
      setSaving(true);
      const url = isCreate ? '/api/sq/items' : `/api/sq/items/${skuId}`;
      const method = isCreate ? 'post' : 'put';

      const resp = await api[method](url, payload);
      const saved = resp.data;
      const id = typeof saved?.id === 'number' ? saved.id : skuId;

      toast({
        title: isCreate ? 'SKU created' : 'SKU updated',
        description: isCreate ? 'New SKU has been created.' : 'Changes have been saved.',
      });

      if (typeof id === 'number') {
        onSaved(id);
      } else {
        onSaved(saved.id ?? 0);
      }
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } catch (e: any) {
      const detail = e?.response?.data?.detail ?? e?.message ?? 'Save failed';
      toast({ title: 'Failed to save SKU', description: String(detail), variant: 'destructive' });
    } finally {
      setSaving(false);
    }
  };

  const disabled = saving || dictionariesLoading || (mode === 'edit' && loadingItem);

  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        if (!nextOpen) onClose();
      }}
    >
      <DialogContent className="max-w-5xl max-w-[95vw] w-full max-h-[90vh] min-w-[720px] min-h-[420px] flex flex-col resize-both overflow-auto">
        <DialogHeader>
          <DialogTitle>{mode === 'create' ? 'Create SKU' : 'Edit SKU'}</DialogTitle>
          <DialogDescription>
            Fill in the main business fields for the SQ catalog item. Description fields accept raw HTML and will be
            stored as-is in the database.
          </DialogDescription>
        </DialogHeader>

        <div className="flex-1 overflow-y-auto pr-1 space-y-3 text-xs">
          {/* Title & Model */}
          <section className="border rounded-md p-2.5 space-y-1.5 bg-gray-50/60">
            <div className="flex items-center justify-between gap-2">
              <h3 className="font-semibold text-sm">Title &amp; Model</h3>
              <span className="text-[11px] text-gray-500">
                {titleRemaining} characters left
              </span>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-2 items-center">
              <div className="md:col-span-2">
                <label className="block text-[11px] font-medium mb-1">Title *</label>
                <Input
                  value={form.title}
                  maxLength={80}
                  onChange={(e) => handleChange('title', e.target.value)}
                  className="h-8 text-xs"
                  placeholder="Short human-friendly title (max 80 chars)"
                />
                {errors.title && <p className="mt-1 text-[11px] text-red-600">{errors.title}</p>}
              </div>
              <div>
                <label className="block text-[11px] font-medium mb-1">Model *</label>
                <Input
                  value={form.model}
                  onChange={(e) => handleChange('model', e.target.value)}
                  className="h-8 text-xs"
                  placeholder="Select model or type a part…"
                />
                {errors.model && <p className="mt-1 text-[11px] text-red-600">{errors.model}</p>}
              </div>
            </div>
          </section>

          {/* SKU & Category */}
          <section className="border rounded-md p-2.5 space-y-2">
            <h3 className="font-semibold text-sm">SKU &amp; Category</h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-2 items-center">
              <div className="flex flex-col gap-1">
                <label className="text-[11px] font-medium">SKU</label>
                <div className="flex items-center gap-2">
                  <Input
                    value={form.sku}
                    onChange={(e) => handleChange('sku', e.target.value.replace(/[^0-9]/g, ''))}
                    disabled={form.autoSku}
                    className="h-8 text-xs"
                    placeholder={form.autoSku ? 'Auto generated on save' : 'Numeric SKU'}
                  />
                  <label className="flex items-center gap-1 text-[11px]">
                    <Checkbox
                      checked={form.autoSku}
                      onCheckedChange={(checked) => handleChange('autoSku', Boolean(checked))}
                    />
                    <span>Auto Generated SKU</span>
                  </label>
                </div>
                {errors.sku && <p className="mt-1 text-[11px] text-red-600">{errors.sku}</p>}
              </div>

              <div className="md:col-span-2 grid grid-cols-1 md:grid-cols-2 gap-3">
                <div>
                  <label className="text-[11px] font-medium mb-1 block">Category type</label>
                  <div className="flex items-center gap-4 text-[11px]">
                    <label className="flex items-center gap-1">
                      <input
                        type="radio"
                        className="h-3 w-3"
                        checked={form.categoryType === 'internal'}
                        onChange={() => handleChange('categoryType', 'internal')}
                      />
                      <span>Internal</span>
                    </label>
                    <label className="flex items-center gap-1">
                      <input
                        type="radio"
                        className="h-3 w-3"
                        checked={form.categoryType === 'ebay'}
                        onChange={() => handleChange('categoryType', 'ebay')}
                      />
                      <span>eBay</span>
                    </label>
                  </div>
                </div>

                {form.categoryType === 'internal' ? (
                  <div>
                    <label className="text-[11px] font-medium mb-1 block">Internal category *</label>
                    <Select
                      value={form.internalCategoryCode}
                      onValueChange={(value) => handleChange('internalCategoryCode', value)}
                    >
                      <SelectTrigger className="h-8 text-xs">
                        <SelectValue placeholder={dictionariesLoading && !dictionaries ? 'Loading…' : 'Select category'} />
                      </SelectTrigger>
                      <SelectContent>
                        {(dictionaries?.internal_categories || []).map((c) => (
                          <SelectItem key={c.id} value={c.code}>
                            {c.code} — {c.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    {errors.category && (
                      <p className="mt-1 text-[11px] text-red-600">{errors.category}</p>
                    )}
                  </div>
                ) : (
                  <div className="grid grid-cols-2 gap-2 items-center">
                    <div>
                      <label className="text-[11px] font-medium mb-1 block">External category ID</label>
                      <Input
                        value={form.externalCategoryId}
                        onChange={(e) => handleChange('externalCategoryId', e.target.value)}
                        className="h-8 text-xs"
                        placeholder="eBay category ID"
                      />
                    </div>
                    <div>
                      <label className="text-[11px] font-medium mb-1 block">External category name</label>
                      <Input
                        value={form.externalCategoryName}
                        onChange={(e) => handleChange('externalCategoryName', e.target.value)}
                        className="h-8 text-xs"
                        placeholder="Category name"
                      />
                    </div>
                    {errors.externalCategory && (
                      <p className="mt-1 text-[11px] text-red-600 col-span-2">
                        {errors.externalCategory}
                      </p>
                    )}
                  </div>
                )}
              </div>
            </div>
          </section>

          {/* Images */}
          <section className="border rounded-md p-2.5 space-y-1.5">
            <h3 className="font-semibold text-sm">Images (Pic#1–Pic#12)</h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-1.5">
              {form.pics.map((value, idx) => (
                <div key={idx} className="space-y-1">
                  <label className="text-[11px] font-medium block">Pic#{idx + 1}</label>
                  <Input
                    className="h-7 text-[11px] font-mono"
                    placeholder="https://…"
                    value={value}
                    onChange={(e) => handlePicChange(idx, e.target.value)}
                  />
                </div>
              ))}
            </div>
          </section>

          {/* Shipping */}
          <section className="border rounded-md p-2.5 space-y-2">
            <h3 className="font-semibold text-sm">Shipping</h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-2 items-center">
              <div>
                <label className="text-[11px] font-medium mb-1 block">Shipping group *</label>
                <Select
                  value={form.shippingGroupCode}
                  onValueChange={(value) => handleChange('shippingGroupCode', value)}
                >
                  <SelectTrigger className="h-8 text-xs">
                    <SelectValue placeholder={dictionariesLoading && !dictionaries ? 'Loading…' : 'Select group'} />
                  </SelectTrigger>
                  <SelectContent>
                    {(dictionaries?.shipping_groups || []).map((g) => (
                      <SelectItem key={g.id} value={g.code}>
                        {g.code} — {g.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {errors.shippingGroupCode && (
                  <p className="mt-1 text-[11px] text-red-600">{errors.shippingGroupCode}</p>
                )}
              </div>
              <div>
                <label className="text-[11px] font-medium mb-1 block">Shipping type</label>
                <Select
                  value={form.shippingType}
                  onValueChange={(value) => handleChange('shippingType', value as 'Flat' | 'Calculated')}
                >
                  <SelectTrigger className="h-8 text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="Flat">Flat</SelectItem>
                    <SelectItem value="Calculated">Calculated</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="flex items-center mt-5 gap-2">
                <Checkbox
                  checked={form.domesticOnly}
                  onCheckedChange={(checked) => handleChange('domesticOnly', Boolean(checked))}
                />
                <span className="text-[11px]">Domestic only shipping</span>
              </div>
            </div>
          </section>

          {/* Identifiers & condition */}
          <section className="border rounded-md p-2.5 space-y-2">
            <h3 className="font-semibold text-sm">Identifiers &amp; condition</h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
              <div>
                <label className="text-[11px] font-medium mb-1 block">UPC / EAN / ISBN</label>
                <Input
                  value={form.upc}
                  onChange={(e) => handleChange('upc', e.target.value)}
                  disabled={form.upcDoesNotApply}
                  className="h-8 text-xs"
                />
                <label className="mt-1 flex items-center gap-1 text-[11px]">
                  <Checkbox
                    checked={form.upcDoesNotApply}
                    onCheckedChange={(checked) => handleChange('upcDoesNotApply', Boolean(checked))}
                  />
                  <span>Does not apply</span>
                </label>
              </div>
              <div>
                <label className="text-[11px] font-medium mb-1 block">Part number</label>
                <Input
                  value={form.partNumber}
                  onChange={(e) => handleChange('partNumber', e.target.value)}
                  className="h-8 text-xs font-mono"
                />
              </div>
              <div>
                <label className="text-[11px] font-medium mb-1 block">Internal part name</label>
                <Input
                  value={form.part}
                  onChange={(e) => handleChange('part', e.target.value)}
                  className="h-8 text-xs"
                  placeholder="e.g. LCD COMPLETE"
                />
              </div>

              <div>
                <label className="text-[11px] font-medium mb-1 block">MPN</label>
                <Input
                  value={form.mpn}
                  onChange={(e) => handleChange('mpn', e.target.value)}
                  className="h-8 text-xs"
                />
              </div>

              <div>
                <label className="text-[11px] font-medium mb-1 block">Condition *</label>
                <Select
                  value={form.conditionId}
                  onValueChange={(value) => handleChange('conditionId', value)}
                >
                  <SelectTrigger className="h-8 text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {(dictionaries?.conditions || []).map((c) => (
                      <SelectItem key={c.id} value={String(c.id)}>
                        {c.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {errors.conditionId && (
                  <p className="mt-1 text-[11px] text-red-600">{errors.conditionId}</p>
                )}
              </div>

              <div>
                <label className="text-[11px] font-medium mb-1 block">Grade (optional)</label>
                <Input
                  value={form.gradeId}
                  onChange={(e) => handleChange('gradeId', e.target.value.replace(/[^0-9]/g, ''))}
                  className="h-8 text-xs"
                  placeholder="Numeric grade ID"
                />
              </div>

              <div className="flex items-center gap-2 mt-1">
                <Checkbox
                  checked={form.hasColor}
                  onCheckedChange={(checked) => handleChange('hasColor', Boolean(checked))}
                />
                <Input
                  value={form.colorValue}
                  onChange={(e) => handleChange('colorValue', e.target.value)}
                  disabled={!form.hasColor}
                  className="h-8 text-xs flex-1"
                  placeholder="Color value"
                />
              </div>

              <div className="flex items-center gap-2 mt-1">
                <Checkbox
                  checked={form.hasEpid}
                  onCheckedChange={(checked) => handleChange('hasEpid', Boolean(checked))}
                />
                <Input
                  value={form.epidValue}
                  onChange={(e) => handleChange('epidValue', e.target.value)}
                  disabled={!form.hasEpid}
                  className="h-8 text-xs flex-1"
                  placeholder="ePID value"
                />
              </div>
            </div>
          </section>

          {/* Price & weight */}
          <section className="border rounded-md p-2.5 space-y-2">
            <h3 className="font-semibold text-sm">Price &amp; weight</h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 items-center">
              <div>
                <label className="text-[11px] font-medium mb-1 block">Price *</label>
                <Input
                  value={form.price}
                  onChange={(e) => handleChange('price', e.target.value)}
                  className="h-8 text-xs"
                  placeholder="0.00"
                />
                {errors.price && <p className="mt-1 text-[11px] text-red-600">{errors.price}</p>}
              </div>
              <div className="flex items-center gap-2">
                <div className="flex-1">
                  <label className="text-[11px] font-medium mb-1 block">Weight</label>
                  <Input
                    value={form.weight}
                    onChange={(e) => handleChange('weight', e.target.value)}
                    className="h-8 text-xs"
                    placeholder="Numeric"
                  />
                </div>
                <div className="w-24 mt-5">
                  <Select value={form.unit} onValueChange={(v) => handleChange('unit', v)}>
                    <SelectTrigger className="h-8 text-xs">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="oz">oz</SelectItem>
                      <SelectItem value="lb">lb</SelectItem>
                      <SelectItem value="g">g</SelectItem>
                      <SelectItem value="kg">kg</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </div>
          </section>

          {/* Listing settings */}
          <section className="border rounded-md p-3 space-y-3">
            <h3 className="font-semibold text-sm">Listing settings</h3>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-2 items-center">
              <div>
                <label className="text-[11px] font-medium mb-1 block">Listing type</label>
                <Select
                  value={form.listingType}
                  onValueChange={(value) => handleChange('listingType', value)}
                >
                  <SelectTrigger className="h-8 text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {(dictionaries?.listing_types || []).map((t) => (
                      <SelectItem key={t.code} value={t.code}>
                        {t.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div>
                <label className="text-[11px] font-medium mb-1 block">Listing duration</label>
                <Select
                  value={form.listingDuration}
                  onValueChange={(value) => handleChange('listingDuration', value)}
                >
                  <SelectTrigger className="h-8 text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {(dictionaries?.listing_durations || []).map((d) => (
                      <SelectItem key={d.code} value={d.code}>
                        {d.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div>
                <label className="text-[11px] font-medium mb-1 block">Site</label>
                <Select
                  value={form.siteId}
                  onValueChange={(value) => handleChange('siteId', value)}
                >
                  <SelectTrigger className="h-8 text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {(dictionaries?.sites || []).map((s) => (
                      <SelectItem key={s.site_id} value={String(s.site_id)}>
                        {s.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2 mt-4">
                <label className="flex items-center gap-1 text-[11px]">
                  <Checkbox
                    checked={form.oneTimeAuction}
                    onCheckedChange={(checked) => handleChange('oneTimeAuction', Boolean(checked))}
                  />
                  <span>One time auction</span>
                </label>
                <label className="flex items-center gap-1 text-[11px]">
                  <Checkbox
                    checked={form.useMotors}
                    onCheckedChange={(checked) => handleChange('useMotors', Boolean(checked))}
                  />
                  <span>Use eBay Motors site</span>
                </label>
              </div>
            </div>
          </section>

          {/* Descriptions */}
          <section className="border rounded-md p-2.5 space-y-2">
            <div className="flex items-center justify-between gap-2">
              <h3 className="font-semibold text-sm">Descriptions &amp; templates</h3>
              <span className="text-[11px] text-gray-500">
                Condition description: {conditionDescRemaining} characters left
              </span>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
              <div className="space-y-1">
                <label className="text-[11px] font-medium block">Condition description</label>
                <Textarea
                  value={form.conditionDescription}
                  onChange={(e) => handleChange('conditionDescription', e.target.value)}
                  className="min-h-[80px] text-xs"
                />
              </div>
              <div className="space-y-1">
                <label className="text-[11px] font-medium block">Description (HTML allowed)</label>
                <Textarea
                  value={form.description}
                  onChange={(e) => handleChange('description', e.target.value)}
                  className="min-h-[120px] text-xs font-mono"
                  placeholder="Full listing description. HTML is stored as-is."
                />
              </div>
            </div>
          </section>

          {/* Advanced flags */}
          <section className="border rounded-md p-2.5 space-y-2 bg-gray-50/60">
            <h3 className="font-semibold text-sm">Advanced</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2 items-start">
              <div>
                <label className="flex items-center gap-1 text-[11px] mb-1">
                  <Checkbox
                    checked={form.alertEnabled}
                    onCheckedChange={(checked) => handleChange('alertEnabled', Boolean(checked))}
                  />
                  <span>Enable alert</span>
                </label>
                <Textarea
                  value={form.alertMessage}
                  onChange={(e) => handleChange('alertMessage', e.target.value)}
                  disabled={!form.alertEnabled}
                  className="min-h-[70px] text-xs"
                  placeholder="Internal alert message for this SKU"
                />
              </div>
              <div className="text-[11px] text-gray-600 space-y-1">
                <p>
                  Record status, checked flags, clone metadata and other low-level audit fields are managed automatically on
                  the backend and are not editable here.
                </p>
              </div>
            </div>
          </section>
        </div>

        <div className="mt-3 flex justify-end gap-2 text-xs">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={onClose}
            disabled={disabled}
          >
            Cancel
          </Button>
          <Button
            type="button"
            size="sm"
            className="bg-green-600 hover:bg-green-700 text-white"
            onClick={() => {
              void handleSubmit();
            }}
            disabled={disabled}
          >
            {saving ? 'Saving…' : 'Save'}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
