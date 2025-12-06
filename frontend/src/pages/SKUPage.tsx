import { useState } from 'react';
import FixedHeader from '@/components/FixedHeader';
import { DataGridPage } from '@/components/DataGridPage';
import { SkuFormModal, type SkuFormMode } from '@/components/SkuFormModal';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { X, Trash2 } from 'lucide-react';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { useToast } from '@/hooks/use-toast';
import api from '@/lib/apiClient';

export default function SKUPage() {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [selectedRow, setSelectedRow] = useState<Record<string, any> | null>(null);
  const [selectedRows, setSelectedRows] = useState<Record<string, any>[]>([]);
  const [refreshKey, setRefreshKey] = useState(0);
  const [formOpen, setFormOpen] = useState(false);
  const [formMode, setFormMode] = useState<SkuFormMode>('create');
  const [editingId, setEditingId] = useState<number | null>(null);

  // Delete flow state
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [deleteStep, setDeleteStep] = useState<1 | 2>(1);
  const [deleteConfirmInput, setDeleteConfirmInput] = useState('');
  const [isDeleting, setIsDeleting] = useState(false);

  const { toast } = useToast();

  const [filters, setFilters] = useState({
    model: '',
    category: '',
    part_number: '',
    title: '',
    sku: ''
  });

  // Local state for filter inputs to avoid live search
  const [localFilters, setLocalFilters] = useState({
    model: '',
    category: '',
    part_number: '',
    title: '',
    sku: ''
  });

  const clearFilters = () => {
    const empty = {
      model: '',
      category: '',
      part_number: '',
      title: '',
      sku: ''
    };
    setFilters(empty);
    setLocalFilters(empty);
  };

  const handleFilterKeyDown = (key: string, e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      setFilters(prev => ({ ...prev, [key]: localFilters[key as keyof typeof localFilters].trim() }));
    }
  };

  const handleFilterChange = (key: string, value: string) => {
    setLocalFilters(prev => ({ ...prev, [key]: value }));
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
  };

  const handleDeleteClick = () => {
    if (selectedRows.length === 0) return;
    setDeleteStep(1);
    setDeleteConfirmInput('');
    setDeleteDialogOpen(true);
  };

  const handleConfirmDelete = async () => {
    if (deleteStep === 1) {
      setDeleteStep(2);
      return;
    }

    if (deleteConfirmInput !== 'DELETE') {
      return;
    }

    setIsDeleting(true);
    try {
      const ids = selectedRows.map((r) => r.id);
      const res = await api.post('/api/sq/items/bulk-delete', { ids });
      const count = res.data.count;
      toast({
        title: 'Deleted successfully',
        description: `Deleted ${count} items.`,
      });
      setRefreshKey((prev) => prev + 1);
      setSelectedRows([]);
      setSelectedRow(null);
      setDeleteDialogOpen(false);
    } catch (error) {
      toast({
        title: 'Delete failed',
        description: 'Failed to delete items. Please try again.',
        variant: 'destructive',
      });
    } finally {
      setIsDeleting(false);
    }
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
            {selectedRows.length > 0 && (
              <Button
                size="sm"
                variant="destructive"
                className="text-xs"
                onClick={handleDeleteClick}
              >
                <Trash2 className="w-3 h-3 mr-1" />
                Delete ({selectedRows.length})
              </Button>
            )}
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
                value={localFilters.model}
                onChange={(e) => handleFilterChange('model', e.target.value)}
                onKeyDown={(e) => handleFilterKeyDown('model', e)}
              />
              <Input
                placeholder="Category"
                className="h-8 text-xs w-32"
                value={localFilters.category}
                onChange={(e) => handleFilterChange('category', e.target.value)}
                onKeyDown={(e) => handleFilterKeyDown('category', e)}
              />
              <Input
                placeholder="Part Number"
                className="h-8 text-xs w-32"
                value={localFilters.part_number}
                onChange={(e) => handleFilterChange('part_number', e.target.value)}
                onKeyDown={(e) => handleFilterKeyDown('part_number', e)}
              />
              <Input
                placeholder="Title"
                className="h-8 text-xs flex-1"
                value={localFilters.title}
                onChange={(e) => handleFilterChange('title', e.target.value)}
                onKeyDown={(e) => handleFilterKeyDown('title', e)}
              />
              <Input
                placeholder="SKU"
                className="h-8 text-xs w-32"
                value={localFilters.sku}
                onChange={(e) => handleFilterChange('sku', e.target.value)}
                onKeyDown={(e) => handleFilterKeyDown('sku', e)}
              />
            </div>
          </div>

          {/* Middle: SKU grid backed by SKU table via gridKey="sku_catalog" */}
          <div className="flex-[2] min-h-0 border rounded-lg bg-white flex flex-col">
            <div className="flex items-center justify-between px-3 py-2 border-b bg-gray-50 text-xs">
              <div className="font-semibold">SKU grid</div>
              <div className="text-gray-500">
                {selectedRows.length > 0
                  ? `${selectedRows.length} rows selected`
                  : 'Click a row to see details below.'}
              </div>
            </div>
            <div className="flex-1 min-h-0">
              <DataGridPage
                gridKey="sku_catalog"
                title="SKU catalog"
                extraParams={{ _refresh: refreshKey, ...filters }}
                selectionMode="multiRow"
                onSelectionChange={setSelectedRows}
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

      {/* Delete Confirmation Dialog */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Are you absolutely sure?</AlertDialogTitle>
            <AlertDialogDescription>
              {deleteStep === 1 ? (
                <span>
                  This action cannot be undone. This will permanently delete{' '}
                  <span className="font-bold">{selectedRows.length}</span> SKU records.
                </span>
              ) : (
                <div className="space-y-2">
                  <span>To confirm deletion, please type <span className="font-bold font-mono text-red-600">DELETE</span> in the box below.</span>
                  <Input
                    value={deleteConfirmInput}
                    onChange={(e) => setDeleteConfirmInput(e.target.value)}
                    placeholder="Type DELETE"
                    className="border-red-300 focus:ring-red-500"
                  />
                </div>
              )}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={() => setDeleteDialogOpen(false)}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={(e) => {
                e.preventDefault();
                handleConfirmDelete();
              }}
              className="bg-red-600 hover:bg-red-700 focus:ring-red-600"
              disabled={deleteStep === 2 && deleteConfirmInput !== 'DELETE'}
            >
              {isDeleting ? 'Deleting...' : deleteStep === 1 ? 'Yes, continue' : 'Confirm Delete'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
