import { useMemo, useState } from 'react';
import FixedHeader from '@/components/FixedHeader';
import { DataGridPage } from '@/components/DataGridPage';

export default function InventoryPageV3() {
  const [storageId, setStorageId] = useState('');
  const [ebayStatus, setEbayStatus] = useState('');

  const extraParams = useMemo(() => {
    const params: Record<string, string> = {};
    if (storageId) params.storageID = storageId;
    if (ebayStatus) params.ebay_status = ebayStatus;
    return params;
  }, [storageId, ebayStatus]);

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

          <div className="flex-1 min-h-0">
            <DataGridPage gridKey="inventory" title="Inventory" extraParams={extraParams} />
          </div>
        </div>
      </div>
    </div>
  );
}
