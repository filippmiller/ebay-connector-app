import { useEffect, useMemo, useState } from 'react';
import FixedHeader from '@/components/FixedHeader';
import { DataGridPage } from '@/components/DataGridPage';
import api from '@/lib/apiClient';

export default function InventoryPageV3() {
  const initialFilterState = {
    id: '',
    sku: '',
    itemId: '',
    title: '',
    statusSku: '',
    storage: '',
    serial: '',
  };
  const [filterInputs, setFilterInputs] = useState(initialFilterState);
  const [filters, setFilters] = useState(initialFilterState);
  const [statusOptions, setStatusOptions] = useState<{ id: number; label: string; color?: string | null }[]>([]);
  const [showCounts, setShowCounts] = useState(false);

  const extraParams = useMemo(() => {
    const params: Record<string, string> = {};
    if (filters.id) params.inv_id = filters.id;
    if (filters.sku) params.inv_sku = filters.sku;
    if (filters.itemId) params.inv_item_id = filters.itemId;
    if (filters.title) params.inv_title = filters.title;
    if (filters.statusSku) params.inv_statussku = filters.statusSku;
    if (filters.storage) params.inv_storage = filters.storage;
    if (filters.serial) params.inv_serial_number = filters.serial;
    if (showCounts) params.includeCounts = '1';
    return params;
  }, [filters, showCounts]);

  const handleFilterInputChange = (key: keyof typeof filterInputs, value: string) => {
    setFilterInputs((prev) => ({ ...prev, [key]: value }));
  };

  const applyFilter = (key: keyof typeof filterInputs) => {
    setFilters((prev) => ({ ...prev, [key]: filterInputs[key] }));
  };

  const resetFilters = () => {
    setFilterInputs(initialFilterState);
    setFilters(initialFilterState);
    setShowCounts(false);
  };

  useEffect(() => {
    const loadStatuses = async () => {
      try {
        const resp = await api.get<{ items: { id: number; label: string; color?: string | null }[] }>(
          '/api/grids/inventory/statuses'
        );
        setStatusOptions(resp.data.items || []);
      } catch {
        setStatusOptions([]);
      }
    };
    void loadStatuses();
  }, []);

  return (
    <div className="h-screen flex flex-col bg-gray-50">
      <FixedHeader />
      <div className="pt-10 flex-1 px-4 py-4 overflow-hidden">
        <div className="w-full h-full flex flex-col min-h-0">
          <h1 className="text-2xl font-bold mb-2">Inventory</h1>

          <div className="flex-1 min-h-0">
            <DataGridPage
              gridKey="inventory"
              title=""
              hideTitle
              extraParams={extraParams}
              topContent={
                <div className="flex flex-wrap items-end gap-2 text-[11px]">
                  {[
                    { key: 'id', label: 'ID', width: 'w-24' },
                    { key: 'sku', label: 'SKU', width: 'w-32' },
                    { key: 'itemId', label: 'ItemID', width: 'w-32' },
                    { key: 'title', label: 'Title', width: 'w-40' },
                    { key: 'statusSku', label: 'StatusSKU', width: 'w-36' },
                    { key: 'storage', label: 'Storage', width: 'w-28' },
                    { key: 'serial', label: 'Serial Number', width: 'w-36' },
                  ].map((f) => (
                    <div key={f.key} className={`flex flex-col gap-1 ${f.width}`}>
                      {f.key === 'statusSku' ? (
                        <select
                          className="border rounded px-2 py-1 text-[11px]"
                          aria-label="Filter by StatusSKU"
                          value={filterInputs.statusSku}
                          onChange={(e) => {
                            const value = e.target.value;
                            handleFilterInputChange('statusSku', value);
                            applyFilter('statusSku');
                          }}
                        >
                          <option value="">All</option>
                          {statusOptions.map((opt) => (
                            <option key={opt.id} value={opt.label}>
                              {opt.label}
                            </option>
                          ))}
                        </select>
                      ) : (
                        <input
                          className="border rounded px-2 py-1 text-[11px]"
                          value={filterInputs[f.key as keyof typeof filterInputs]}
                          placeholder={f.label}
                          onChange={(e) => handleFilterInputChange(f.key as keyof typeof filterInputs, e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') {
                              applyFilter(f.key as keyof typeof filterInputs);
                            }
                          }}
                        />
                      )}
                    </div>
                  ))}
                  <button
                    type="button"
                    className="ml-1 px-3 py-2 border rounded bg-white hover:bg-gray-50 text-[11px]"
                    onClick={resetFilters}
                  >
                    Reset
                  </button>
                </div>
              }
            />
          </div>
          <div className="mt-2 flex items-center text-[11px]">
            <label className="inline-flex items-center gap-1">
              <input
                type="checkbox"
                checked={showCounts}
                onChange={(e) => setShowCounts(e.target.checked)}
              />
              <span>Show SKU/ItemID counts</span>
            </label>
          </div>
        </div>
      </div>
    </div>
  );
}
