import { useMemo, useState } from 'react';
import FixedHeader from '@/components/FixedHeader';
import { DataGridPage } from '@/components/DataGridPage';
import api from '@/lib/apiClient';
import { useToast } from '@/hooks/use-toast';
import { WorkerDebugTerminalModal } from '@/components/WorkerDebugTerminalModal';
import { useEbayListingDebug } from '@/hooks/useEbayListingDebug';

type DraftListingStatus = 'awaiting_moderation' | 'checked';

interface DraftListingItem {
  tempId: string;
  skuId: number;
  skuCode: string;
  model?: string | null;
  category?: string | null;
  price: number;
  quantity: number;
  condition?: string | null;
  title?: string | null;
  storage: string;
  status: DraftListingStatus;
  warehouseId?: number | null;
}

function uuid(): string {
  return Math.random().toString(36).slice(2) + Math.random().toString(36).slice(2);
}

export default function ListingPage() {
  const { toast } = useToast();

  const [draftItems, setDraftItems] = useState<DraftListingItem[]>([]);
  const [selectedDraftIds, setSelectedDraftIds] = useState<Set<string>>(new Set());
  const [globalStorage, setGlobalStorage] = useState('');
  const [globalStatus, setGlobalStatus] = useState<DraftListingStatus>('awaiting_moderation');
  const [isCommitting, setIsCommitting] = useState(false);

  // Debug listing worker (parts_detail) – dev only
  const [debugIds, setDebugIds] = useState('');
  const [debugMaxItems, setDebugMaxItems] = useState<number | ''>(50);

  const {
    isDebugEnabled,
    runDebugForIds,
    runDebugForAutoCandidates,
    trace: debugTrace,
    open: debugOpen,
    setOpen: setDebugOpen,
    loading: debugLoading,
    error: debugError,
  } = useEbayListingDebug();

  const selectedDraftItems = useMemo(
    () => draftItems.filter((i) => selectedDraftIds.has(i.tempId)),
    [draftItems, selectedDraftIds]
  );

  const handleAddSkuToDraft = (row: Record<string, any>) => {
    if (!row || typeof row.id !== 'number') return;

    const skuId = row.id as number;
    const rawSku = row.sku_code ?? row.skuCode ?? '';
    const skuCode = rawSku !== null && rawSku !== undefined ? String(rawSku) : '';
    const model = (row.model || null) as string | null;
    const category = (row.category || null) as string | null;
    const price = typeof row.price === 'number' ? row.price : Number(row.price || 0) || 0;
    // The SKU grid exposes condition as either `condition_description` (human label)
    // or `condition_id`. Prefer the label if present.
    const condition = (row.condition_description || row.condition || null) as string | null;
    const title = (row.title || null) as string | null;

    // Duplicate strategy: if SKU already exists in draft, increment quantity.
    setDraftItems((prev) => {
      const existing = prev.find((i) => i.skuId === skuId);
      if (existing) {
        return prev.map((i) =>
          i.skuId === skuId ? { ...i, quantity: i.quantity + 1 } : i
        );
      }
      return [
        ...prev,
        {
          tempId: uuid(),
          skuId,
          skuCode,
          model,
          category,
          price,
          quantity: 1,
          condition,
          title,
          storage: '',
          status: 'awaiting_moderation',
          warehouseId: undefined,
        },
      ];
    });
  };

  const applyGlobalToSelected = () => {
    if (selectedDraftIds.size === 0) {
      toast({ title: 'No rows selected', description: 'Select rows in the bottom grid first.' });
      return;
    }

    setDraftItems((prev) =>
      prev.map((item) => {
        if (!selectedDraftIds.has(item.tempId)) return item;
        return {
          ...item,
          storage: globalStorage || item.storage,
          status: globalStatus,
        };
      })
    );
  };

  const removeSelected = () => {
    if (selectedDraftIds.size === 0) return;
    setDraftItems((prev) => prev.filter((i) => !selectedDraftIds.has(i.tempId)));
    setSelectedDraftIds(new Set());
  };

  const clearAll = () => {
    setDraftItems([]);
    setSelectedDraftIds(new Set());
  };

  const toggleDraftSelection = (tempId: string) => {
    setSelectedDraftIds((prev) => {
      const next = new Set(prev);
      if (next.has(tempId)) next.delete(tempId);
      else next.add(tempId);
      return next;
    });
  };

  const toggleSelectAllDraft = () => {
    if (selectedDraftIds.size === draftItems.length) {
      setSelectedDraftIds(new Set());
    } else {
      setSelectedDraftIds(new Set(draftItems.map((i) => i.tempId)));
    }
  };

  const handleCommitSelected = async () => {
    if (selectedDraftItems.length === 0) {
      toast({ title: 'Nothing to commit', description: 'Select rows in the draft grid first.' });
      return;
    }

    const invalid = selectedDraftItems.filter((i) => !i.storage.trim());
    if (invalid.length > 0) {
      toast({
        title: 'Storage required',
        description: 'All selected rows must have Storage set before commit.',
        variant: 'destructive',
      });
      return;
    }

    const payload = {
      model_id: null,
      storage: globalStorage || undefined,
      default_status: globalStatus,
      items: selectedDraftItems.map((item) => ({
        sku_code: item.skuCode,
        price: item.price,
        quantity: item.quantity,
        condition: item.condition,
        title: item.title,
        storage: item.storage,
        status: item.status,
        warehouse_id: item.warehouseId ?? undefined,
      })),
    };

    try {
      setIsCommitting(true);
      const resp = await api.post('/api/listing/commit', payload);
      const createdCount = resp.data?.created_count ?? 0;
      toast({
        title: 'Listing committed',
        description: `${createdCount} items committed to inventory`,
      });

      const committedSkuCodes = new Set(resp.data?.items?.map((i: any) => i.sku_code) ?? []);
      setDraftItems((prev) => prev.filter((i) => !committedSkuCodes.has(i.skuCode)));
      setSelectedDraftIds(new Set());

      // When debug mode is enabled, immediately run the listing worker for the
      // freshly created parts_detail rows so we can see the full trace.
      const pdIds: number[] = resp.data?.parts_detail_ids ?? [];
      if (isDebugEnabled && Array.isArray(pdIds) && pdIds.length > 0) {
        try {
          await runDebugForIds(pdIds, {
            dryRun: false,
            maxItems: pdIds.length || 50,
          });
        } catch {
          // Errors are surfaced inside the debug hook (toast + error state).
        }
      }
    } catch (e: any) {
      const detail = e?.response?.data?.detail ?? e?.message ?? 'Commit failed';
      toast({ title: 'Commit failed', description: String(detail), variant: 'destructive' });
    } finally {
      setIsCommitting(false);
    }
  };

  const handleRunDebugWorker = async () => {
    if (!isDebugEnabled) return;
    const raw = debugIds.trim();
    if (!raw) {
      toast({ title: 'No IDs provided', description: 'Enter parts_detail IDs (comma separated).', variant: 'destructive' });
      return;
    }

    const ids = Array.from(
      new Set(
        raw
          .split(/[\s,]+/)
          .map((s) => s.trim())
          .filter(Boolean)
          .map((s) => Number(s))
          .filter((n) => Number.isFinite(n) && n > 0),
      ),
    );

    if (!ids.length) {
      toast({ title: 'Invalid IDs', description: 'Could not parse any numeric IDs from input.', variant: 'destructive' });
      return;
    }

    try {
      await runDebugForIds(ids, { dryRun: false, maxItems: 50 });
    } catch {
      // Errors are already surfaced via the debug hook (toast + error state).
    }
  };

  return (
    <div className="h-screen flex flex-col bg-gray-50">
      <FixedHeader />
      <div className="pt-16 flex-1 px-4 py-4 overflow-hidden flex flex-col gap-4">
        <h1 className="text-2xl font-bold mb-2">Listing (SKU → Inventory)</h1>

        {/* Top section: SKU catalog grid */}
        <div className="flex-[2] min-h-0 border rounded-lg bg-white flex flex-col">
          <div className="flex items-center justify-between px-3 py-2 border-b bg-gray-50 text-xs">
            <div className="font-semibold">SKU catalog</div>
            <div className="flex items-center gap-2">
              <span className="text-gray-500">Select SKUs and click Add to listing</span>
            </div>
          </div>
          <div className="flex-1 min-h-0">
            <DataGridPage
              gridKey="sku_catalog"
              title="SKU catalog"
              onRowClick={handleAddSkuToDraft}
            />
          </div>
        </div>

        {/* Bottom section: Draft listing grid */}
        <div className="flex-[1] min-h-[220px] border rounded-lg bg-white flex flex-col">
          <div className="flex items-center justify-between px-3 py-2 border-b bg-gray-50 text-xs gap-4">
            <div className="font-semibold">Draft listing (per physical computer)</div>
            <div className="flex items-center gap-2 flex-wrap">
              <input
                className="border rounded px-2 py-1 text-xs w-32"
                placeholder="Storage (e.g. B16:1)"
                value={globalStorage}
                onChange={(e) => setGlobalStorage(e.target.value)}
              />
              <select
                className="border rounded px-2 py-1 text-xs"
                value={globalStatus}
                onChange={(e) => setGlobalStatus(e.target.value as DraftListingStatus)}
              >
                <option value="awaiting_moderation">Awaiting moderation</option>
                <option value="checked">Checked</option>
              </select>
              <button
                className="px-2 py-1 text-xs border rounded bg-gray-100 hover:bg-gray-200"
                onClick={applyGlobalToSelected}
              >
                Apply to selected
              </button>
              <button
                className="px-2 py-1 text-xs border rounded bg-white hover:bg-gray-100"
                onClick={removeSelected}
              >
                Remove selected
              </button>
              <button
                className="px-2 py-1 text-xs border rounded bg-white hover:bg-gray-100"
                onClick={clearAll}
              >
                Clear all
              </button>
              <button
                className="ml-2 px-3 py-1 text-xs rounded bg-green-600 text-white hover:bg-green-700 disabled:bg-gray-300 disabled:cursor-not-allowed"
                onClick={handleCommitSelected}
                disabled={isCommitting || selectedDraftItems.length === 0}
              >
                {isCommitting ? 'Committing…' : 'Commit selected'}
              </button>
            </div>
          </div>

          <div className="flex-1 min-h-0 overflow-auto">
            <table className="min-w-full text-[11px] border-collapse">
              <thead className="bg-gray-100">
                <tr>
                  <th className="ui-table-header px-2 py-1 border-b border-r w-6">
                    <input
                      type="checkbox"
                      className="h-3 w-3"
                      checked={draftItems.length > 0 && selectedDraftIds.size === draftItems.length}
                      onChange={toggleSelectAllDraft}
                    />
                  </th>
                  <th className="ui-table-header px-2 py-1 border-b border-r">#</th>
                  <th className="ui-table-header px-2 py-1 border-b border-r">SKU</th>
                  <th className="ui-table-header px-2 py-1 border-b border-r">Model</th>
                  <th className="ui-table-header px-2 py-1 border-b border-r">Category</th>
                  <th className="ui-table-header px-2 py-1 border-b border-r text-right">Price</th>
                  <th className="ui-table-header px-2 py-1 border-b border-r text-center">Qty</th>
                  <th className="ui-table-header px-2 py-1 border-b border-r">Condition</th>
                  <th className="ui-table-header px-2 py-1 border-b border-r">Storage</th>
                  <th className="ui-table-header px-2 py-1 border-b border-r">Status</th>
                  <th className="ui-table-header px-2 py-1 border-b">Title</th>
                </tr>
              </thead>
              <tbody>
                {draftItems.length === 0 ? (
                  <tr>
                    <td colSpan={11} className="px-3 py-4 text-center text-gray-500 text-xs">
                      No draft items. Select SKUs in the top grid and click "Add to listing".
                    </td>
                  </tr>
                ) : (
                  draftItems.map((item, idx) => (
                    <tr
                      key={item.tempId}
                      className={`border-t ${idx % 2 === 0 ? 'bg-white' : 'bg-gray-50'} hover:bg-blue-50`}
                    >
                      <td className="ui-table-cell px-2 py-1 border-r text-center">
                        <input
                          type="checkbox"
                          className="h-3 w-3"
                          checked={selectedDraftIds.has(item.tempId)}
                          onChange={() => toggleDraftSelection(item.tempId)}
                        />
                      </td>
                      <td className="ui-table-cell px-2 py-1 border-r text-right text-gray-500">{idx + 1}</td>
                      <td className="ui-table-cell px-2 py-1 border-r font-mono">{item.skuCode}</td>
                      <td className="ui-table-cell px-2 py-1 border-r truncate max-w-xs">{item.model || '-'}</td>
                      <td className="ui-table-cell px-2 py-1 border-r">{item.category || '-'}</td>
                      <td className="ui-table-cell px-2 py-1 border-r text-right">
                        {item.price ? item.price.toFixed(2) : '-'}
                      </td>
                      <td className="ui-table-cell px-2 py-1 border-r text-center">{item.quantity}</td>
                      <td className="ui-table-cell px-2 py-1 border-r">{item.condition || '-'}</td>
                      <td className="ui-table-cell px-2 py-1 border-r font-mono">
                        <input
                          className="border rounded px-1 py-0.5 text-[11px] w-20"
                          value={item.storage}
                          onChange={(e) =>
                            setDraftItems((prev) =>
                              prev.map((p) =>
                                p.tempId === item.tempId ? { ...p, storage: e.target.value } : p
                              )
                            )
                          }
                        />
                      </td>
                      <td className="ui-table-cell px-2 py-1 border-r">
                        {item.status === 'awaiting_moderation' ? 'Awaiting moderation' : 'Checked'}
                      </td>
                      <td className="ui-table-cell px-2 py-1 truncate max-w-md">{item.title || '-'}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>

        {isDebugEnabled && (
          <div className="mt-4 border rounded-lg bg-white p-3 text-xs font-mono text-gray-700">
            <div className="flex items-center justify-between mb-2">
              <div className="font-semibold text-gray-800">eBay Listing Worker Debug (parts_detail)</div>
              {debugLoading && <span className="text-blue-600">Running…</span>}
            </div>
            <div className="flex flex-wrap items-center gap-2 mb-2">
              <input
                className="border rounded px-2 py-1 text-xs min-w-[260px]"
                placeholder="parts_detail IDs (e.g. 101, 102, 103)"
                value={debugIds}
                onChange={(e) => setDebugIds(e.target.value)}
              />
              <button
                className="px-3 py-1 text-xs rounded bg-black text-white hover:bg-gray-800 disabled:bg-gray-300 disabled:cursor-not-allowed"
                onClick={handleRunDebugWorker}
                disabled={debugLoading}
              >
                Run listing worker (debug)
              </button>
              <input
                type="number"
                min={1}
                max={200}
                className="border rounded px-2 py-1 text-xs w-24"
                placeholder="max items"
                value={debugMaxItems === '' ? '' : debugMaxItems}
                onChange={(e) => {
                  const v = e.target.value;
                  setDebugMaxItems(v === '' ? '' : Number(v));
                }}
              />
              <button
                className="px-3 py-1 text-xs rounded bg-blue-700 text-white hover:bg-blue-800 disabled:bg-gray-300 disabled:cursor-not-allowed"
                onClick={async () => {
                  if (!isDebugEnabled) return;
                  const max = typeof debugMaxItems === 'number' && debugMaxItems > 0 ? debugMaxItems : 50;
                  try {
                    await runDebugForAutoCandidates({ dryRun: false, maxItems: max });
                  } catch {
                    // Errors are already surfaced via the debug hook (toast + error state).
                  }
                }}
                disabled={debugLoading}
              >
                Run worker for Checked (bulk)
              </button>
            </div>
            <p className="text-[11px] text-gray-500 mb-1">
              Bulk mode calls POST /api/debug/ebay/list-once without explicit ids; the backend auto-selects
              up to <span className="font-semibold">max_items</span> parts_detail rows with
              <code className="mx-1">status_sku = Checked</code>, <code className="mx-1">item_id IS NULL</code>, and no
              freeze/cancel flags, grouped by account and published in batches.
            </p>
            {debugError && <div className="text-red-600 text-[11px]">Error: {debugError}</div>}
          </div>
        )}
      </div>

      {isDebugEnabled && (
        <WorkerDebugTerminalModal
          isOpen={debugOpen}
          onClose={() => setDebugOpen(false)}
          trace={debugTrace}
        />
      )}
    </div>
  );
}
