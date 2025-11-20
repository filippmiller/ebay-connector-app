import { useState } from 'react';
import FixedHeader from '@/components/FixedHeader';
import { DataGridPage } from '@/components/DataGridPage';
import { SkuFormModal, type SkuFormMode } from '@/components/SkuFormModal';
import { Button } from '@/components/ui/button';

export default function SKUPage() {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [selectedRow, setSelectedRow] = useState<Record<string, any> | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [formOpen, setFormOpen] = useState(false);
  const [formMode, setFormMode] = useState<SkuFormMode>('create');
  const [editingId, setEditingId] = useState<number | null>(null);

  const handleOpenCreate = () => {
    setFormMode('create');
    setEditingId(null);
    setFormOpen(true);
  };

  const handleOpenEditFromSelection = () => {
    if (!selectedRow || typeof selectedRow.id !== 'number') return;
    setFormMode('edit');
    setEditingId(selectedRow.id);
    setFormOpen(true);
  };

  const handleSaved = (id: number) => {
    // Trigger grid reload and keep last saved row selected in the detail panel.
    setRefreshKey((prev) => prev + 1);
    setFormOpen(false);
    setEditingId(id);
    // The grid does not expose a selected-row API; we keep the old detail until user clicks again.
  };

  return (
    <div className="h-screen flex flex-col bg-gray-50">
      <FixedHeader />
      <div className="pt-16 flex-1 px-4 py-4 overflow-hidden flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold">SKU Catalog</h1>
            <p className="text-xs text-gray-500">
              SQ catalog backed by the canonical SKU table. Use the form to create or edit SKUs.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button size="sm" className="text-xs" onClick={handleOpenCreate}>
              Add SKU
            </Button>
          </div>
        </div>

        <div className="flex-1 min-h-0 flex flex-col gap-3">
          {/* Top: SKU grid backed by SKU table via gridKey="sku_catalog" */}
          <div className="flex-[2] min-h-0 border rounded-lg bg-white flex flex-col">
            <div className="flex items-center justify-between px-3 py-2 border-b bg-gray-50 text-xs">
              <div className="font-semibold">SKU grid</div>
              <div className="text-gray-500">Click a row to see details below.</div>
            </div>
            <div className="flex-1 min-h-0">
              <DataGridPage
                gridKey="sku_catalog"
                title="SKU catalog"
                extraParams={{ _refresh: refreshKey }}
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                onRowClick={(row: any) => {
                  setSelectedRow(row || null);
                }}
              />
            </div>
          </div>

          {/* Bottom: detail panel from selected grid row */}
          {selectedRow ? (
            <div className="flex-[1] min-h-[160px] border rounded-lg bg-white flex flex-col p-3 text-xs gap-2">
              <div className="flex items-center justify-between mb-2">
                <div className="font-semibold text-gray-700 text-sm">Selected SKU details</div>
                <div className="flex items-center gap-2">
                  <Button
                    size="xs"
                    variant="outline"
                    disabled={typeof selectedRow.id !== 'number'}
                    onClick={handleOpenEditFromSelection}
                  >
                    Edit SKU
                  </Button>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-x-6 gap-y-1">
                <div>
                  <div className="font-semibold text-gray-600">Title</div>
                  <div className="text-sm">{selectedRow.title || '(no title)'}</div>
                </div>
                <div>
                  <div className="font-semibold text-gray-600">Price</div>
                  <div className="text-sm font-medium">
                    {selectedRow.price != null ? String(selectedRow.price) : '-'}
                  </div>
                </div>
                <div>
                  <div className="font-semibold text-gray-600">SKU</div>
                  <div className="text-sm font-mono select-all">
                    {selectedRow.sku_code || selectedRow.sku || '-'}
                  </div>
                </div>
                <div>
                  <div className="font-semibold text-gray-600">Model</div>
                  <div className="text-sm">{selectedRow.model || '-'}</div>
                </div>
                <div>
                  <div className="font-semibold text-gray-600">Category</div>
                  <div className="text-sm">{selectedRow.category || '-'}</div>
                </div>
                <div>
                  <div className="font-semibold text-gray-600">Condition</div>
                  <div className="text-sm">{selectedRow.condition || selectedRow.condition_description || '-'}</div>
                </div>
                <div>
                  <div className="font-semibold text-gray-600">Part Number</div>
                  <div className="text-sm font-mono">{selectedRow.part_number || '-'}</div>
                </div>
                <div>
                  <div className="font-semibold text-gray-600">Brand</div>
                  <div className="text-sm">{selectedRow.brand || '-'}</div>
                </div>
                <div className="col-span-2">
                  <div className="font-semibold text-gray-600">Description</div>
                  <div className="text-sm whitespace-pre-wrap max-h-20 overflow-auto border rounded p-2 bg-gray-50">
                    {selectedRow.description || '(no description)'}
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div className="flex-[1] min-h-[160px] border rounded-lg bg-white flex items-center justify-center text-xs text-gray-500">
              Select a row in the SKU grid to see details.
            </div>
          )}
        </div>
      </div>

      <SkuFormModal
        open={formOpen}
        mode={formMode}
        skuId={editingId}
        onSaved={handleSaved}
        onClose={() => setFormOpen(false)}
      />
    </div>
  );
}
