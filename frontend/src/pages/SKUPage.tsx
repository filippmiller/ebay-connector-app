import { useState } from 'react';
import FixedHeader from '@/components/FixedHeader';
import { DataGridPage } from '@/components/DataGridPage';
import { SkuFormModal, type SkuFormMode } from '@/components/SkuFormModal';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { X } from 'lucide-react';

export default function SKUPage() {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [selectedRow, setSelectedRow] = useState<Record<string, any> | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [formOpen, setFormOpen] = useState(false);
  const [formMode, setFormMode] = useState<SkuFormMode>('create');
  const [editingId, setEditingId] = useState<number | null>(null);

  const [filters, setFilters] = useState({
    model: '',
    category: '',
    part_number: '',
    title: '',
    sku: ''
  });

  const clearFilters = () => {
    setFilters({
      model: '',
      category: '',
      part_number: '',
      title: '',
      sku: ''
    });
  };

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
          {/* Top: Filter Bar */}
          <div className="flex items-center gap-2 p-2 bg-white border rounded-lg shadow-sm">
            <Button
              variant="ghost"
              size="sm"
              onClick={clearFilters}
              className="text-red-600 h-8 text-xs hover:bg-red-50"
            >
              <X className="w-3 h-3 mr-1" /> Clear Filters
            </Button>

            <div className="flex items-center gap-2 flex-1">
              <Input
                placeholder="Model"
                className="h-8 text-xs w-32"
                value={filters.model}
                onChange={(e) => setFilters({ ...filters, model: e.target.value })}
              />
              <Input
                placeholder="Category"
                className="h-8 text-xs w-32"
                value={filters.category}
                onChange={(e) => setFilters({ ...filters, category: e.target.value })}
              />
              <Input
                placeholder="Part Number"
                className="h-8 text-xs w-32"
                value={filters.part_number}
                onChange={(e) => setFilters({ ...filters, part_number: e.target.value })}
              />
              <Input
                placeholder="Title"
                className="h-8 text-xs flex-1"
                value={filters.title}
                onChange={(e) => setFilters({ ...filters, title: e.target.value })}
              />
              <Input
                placeholder="SKU"
                className="h-8 text-xs w-32"
                value={filters.sku}
                onChange={(e) => setFilters({ ...filters, sku: e.target.value })}
              />
            </div>
          </div>

          {/* Middle: SKU grid backed by SKU table via gridKey="sku_catalog" */}
          <div className="flex-[2] min-h-0 border rounded-lg bg-white flex flex-col">
            <div className="flex items-center justify-between px-3 py-2 border-b bg-gray-50 text-xs">
              <div className="font-semibold">SKU grid</div>
              <div className="text-gray-500">Click a row to see details below.</div>
            </div>
            <div className="flex-1 min-h-0">
              <DataGridPage
                gridKey="sku_catalog"
                title="SKU catalog"
                extraParams={{ _refresh: refreshKey, ...filters }}
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                onRowClick={(row: any) => {
                  setSelectedRow(row || null);
                }}
              />
            </div>
          </div>

          {/* Bottom: detail panel from selected grid row */}
          {selectedRow ? (
            <div className="flex-[1] min-h-[200px] border rounded-lg bg-white flex flex-col overflow-hidden">
              <div className="bg-blue-100 px-3 py-1 border-b border-blue-200 flex justify-between items-center">
                <span className="text-xs font-bold text-blue-800 uppercase">Detailed Information for SKU Items</span>
                <Button
                  size="sm"
                  variant="outline"
                  className="h-6 text-xs bg-white hover:bg-blue-50"
                  disabled={typeof selectedRow.id !== 'number'}
                  onClick={handleOpenEditFromSelection}
                >
                  Edit SKU
                </Button>
              </div>

              <div className="flex-1 p-3 flex gap-4 text-xs overflow-auto">
                {/* Left: Image */}
                <div className="w-48 h-32 bg-gray-100 border flex items-center justify-center text-gray-400 shrink-0">
                  {selectedRow.image_url ? (
                    <img src={selectedRow.image_url} alt="SKU" className="max-w-full max-h-full object-contain" />
                  ) : (
                    <div className="text-center p-2">
                      <span className="block text-xs">Click to enlarge</span>
                      <span className="text-[10px]">(No Image)</span>
                    </div>
                  )}
                </div>

                {/* Middle Column */}
                <div className="flex-1 space-y-1 min-w-[200px]">
                  <div className="flex gap-2">
                    <span className="font-bold text-gray-700 w-24">Alert Message:</span>
                    <span className="text-red-600 font-medium">{selectedRow.alert_message || '-'}</span>
                  </div>
                  <div className="flex gap-2">
                    <span className="font-bold text-gray-700 w-24">Price:</span>
                    <span className="font-medium">${selectedRow.price}</span>
                  </div>
                  <div className="flex gap-2">
                    <span className="font-bold text-gray-700 w-24">SKU:</span>
                    <span className="text-red-600 font-bold select-all">{selectedRow.sku_code || selectedRow.sku}</span>
                  </div>
                  <div className="flex gap-2">
                    <span className="font-bold text-gray-700 w-24">Model:</span>
                    <span className="text-blue-600 font-medium">{selectedRow.model}</span>
                  </div>
                  <div className="flex gap-2">
                    <span className="font-bold text-gray-700 w-24">Category:</span>
                    <span className="text-blue-600 font-medium">{selectedRow.category}</span>
                  </div>
                  <div className="flex gap-2">
                    <span className="font-bold text-gray-700 w-24">Brand:</span>
                    <span className="font-medium uppercase">{selectedRow.brand || 'GENERIC'}</span>
                  </div>
                </div>

                {/* Right Column */}
                <div className="flex-1 space-y-1 min-w-[200px]">
                  <div className="flex gap-2">
                    <span className="font-bold text-gray-700 w-28">Shipping Group:</span>
                    <span>{selectedRow.shipping_group || '-'}</span>
                  </div>
                  <div className="flex gap-2">
                    <span className="font-bold text-gray-700 w-28">Part Number:</span>
                    <span className="text-blue-600 font-medium">{selectedRow.part_number || '-'}</span>
                  </div>
                  <div className="flex gap-2">
                    <span className="font-bold text-gray-700 w-28">Weight:</span>
                    <span>{selectedRow.weight || '-'}</span>
                  </div>
                  <div className="flex gap-2">
                    <span className="font-bold text-gray-700 w-28">Created By:</span>
                    <span>{selectedRow.record_created_by || 'system'}</span>
                  </div>
                  <div className="flex gap-2">
                    <span className="font-bold text-gray-700 w-28">Updated By:</span>
                    <span>{selectedRow.record_updated_by || 'system'}</span>
                  </div>
                </div>

                {/* Far Right: Descriptions */}
                <div className="flex-1 min-w-[250px] space-y-2">
                  <div>
                    <div className="font-bold text-gray-700 mb-1">Condition Description:</div>
                    <div className="bg-gray-50 border p-1 h-12 overflow-y-auto text-[11px]">
                      {selectedRow.condition_description || selectedRow.condition || '-'}
                    </div>
                  </div>
                  <div>
                    <div className="font-bold text-gray-700 mb-1">Description:</div>
                    <div className="bg-gray-50 border p-1 h-20 overflow-y-auto text-[11px] whitespace-pre-wrap">
                      {selectedRow.description || '-'}
                    </div>
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
