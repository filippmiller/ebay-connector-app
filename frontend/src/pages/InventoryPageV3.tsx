import { useMemo, useState } from 'react';
import FixedHeader from '@/components/FixedHeader';
import { DataGridPage } from '@/components/DataGridPage';

export default function InventoryPageV3() {
  const [storageId, setStorageId] = useState('');
  const [ebayStatus, setEbayStatus] = useState('');
  const [filterInputs, setFilterInputs] = useState({
    id: '',
    sku: '',
    itemId: '',
    title: '',
    statusSku: '',
    storage: '',
    serial: '',
  });
  const [filters, setFilters] = useState({
    id: '',
    sku: '',
    itemId: '',
    title: '',
    statusSku: '',
    storage: '',
    serial: '',
  });

  const extraParams = useMemo(() => {
    const params: Record<string, string> = {};
    if (storageId) params.storageID = storageId;
    if (ebayStatus) params.ebay_status = ebayStatus;
    if (filters.id) params.inv_id = filters.id;
    if (filters.sku) params.inv_sku = filters.sku;
    if (filters.itemId) params.inv_item_id = filters.itemId;
    if (filters.title) params.inv_title = filters.title;
    if (filters.statusSku) params.inv_statussku = filters.statusSku;
    if (filters.storage) params.inv_storage = filters.storage;
    if (filters.serial) params.inv_serial_number = filters.serial;
    return params;
  }, [storageId, ebayStatus, filters]);

  const handleFilterInputChange = (key: keyof typeof filterInputs, value: string) => {
    setFilterInputs((prev) => ({ ...prev, [key]: value }));
  };

  const applyFilter = (key: keyof typeof filterInputs) => {
    setFilters((prev) => ({ ...prev, [key]: filterInputs[key] }));
  };

  return (
    <div className="h-screen flex flex-col bg-gray-50">
      <FixedHeader />
      <div className="pt-16 flex-1 px-4 py-6 overflow-hidden">
        <div className="w-full h-full flex flex-col">
          <h1 className="text-3xl font-bold mb-4">Inventory</h1>

          {/* Filters specific to Inventory grid */}
          <div className="mb-4 flex flex-wrap items-end gap-4">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Storage ID</label>
              <input
                type="text"
                className="border rounded px-2 py-1 text-sm w-40"
                placeholder="Storage ID"
                value={storageId}
                onChange={(e) => setStorageId(e.target.value)}
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">eBay status</label>
              <select
                className="border rounded px-2 py-1 text-sm w-40"
                value={ebayStatus}
                onChange={(e) => setEbayStatus(e.target.value)}
              >
                <option value="">All</option>
                <option value="ACTIVE">ACTIVE</option>
                <option value="ENDED">ENDED</option>
                <option value="DRAFT">DRAFT</option>
                <option value="PENDING">PENDING</option>
              </select>
            </div>
            <div className="flex-1 min-w-[220px] text-xs text-gray-500">
              Use the search box in the grid toolbar to search across all columns.
            </div>
          </div>

          {/* Column-specific filters (apply on Enter) */}
          <div className="mb-3 grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-2 text-xs">
            {[
              { key: 'id', label: 'ID' },
              { key: 'sku', label: 'SKU' },
              { key: 'itemId', label: 'ItemID' },
              { key: 'title', label: 'Title' },
              { key: 'statusSku', label: 'StatusSKU' },
              { key: 'storage', label: 'Storage' },
              { key: 'serial', label: 'Serial Number' },
            ].map((f) => (
              <div key={f.key} className="flex flex-col gap-1">
                <label className="text-[11px] text-gray-600">{f.label}</label>
                <input
                  className="border rounded px-2 py-1 text-[11px]"
                  value={filterInputs[f.key as keyof typeof filterInputs]}
                  placeholder={`Filter ${f.label} (Enter)`}
                  onChange={(e) => handleFilterInputChange(f.key as keyof typeof filterInputs, e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      applyFilter(f.key as keyof typeof filterInputs);
                    }
                  }}
                />
              </div>
            ))}
          </div>

          <div className="flex-1 min-h-0">
            <DataGridPage gridKey="inventory" title="Inventory" extraParams={extraParams} />
          </div>
        </div>
      </div>
    </div>
  );
}
