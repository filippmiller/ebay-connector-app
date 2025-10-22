import { useState, useEffect } from 'react';
import { Download, RefreshCw, X } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import FixedHeader from '@/components/FixedHeader';

interface InventoryItem {
  id: number;
  sku_code?: string;
  model?: string;
  category?: string;
  condition?: string;
  part_number?: string;
  title?: string;
  price_value?: number;
  price_currency?: string;
  ebay_listing_id?: string;
  ebay_status?: string;
  status: string;
  photo_count: number;
  storage_id?: string;
  warehouse_id?: number;
  quantity: number;
  rec_created?: string;
  author?: string;
}

export default function InventoryPageV3() {
  const [items, setItems] = useState<InventoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [total, setTotal] = useState(0);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  
  const [filters, setFilters] = useState({
    q: '',
    status: '',
    ebay_status: '',
    condition: '',
    category: '',
    storage: '',
    sku_code: '',
    ebay_listing_id: '',
    part_number: ''
  });
  
  const { toast } = useToast();
  const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

  useEffect(() => {
    fetchInventory();
  }, [filters]);

  const fetchInventory = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const params = new URLSearchParams();
      
      Object.entries(filters).forEach(([key, value]) => {
        if (value && value !== '__all__') params.append(key, value);
      });
      params.append('limit', '500');
      
      const response = await fetch(`${API_URL}/api/inventory/search?${params}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      
      if (response.ok) {
        const data = await response.json();
        setItems(data.rows || []);
        setTotal(data.total || 0);
      }
    } catch (error) {
      console.error('Failed to fetch inventory:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleBulkAction = async (action: string) => {
    if (selected.size === 0) {
      toast({ title: "No items selected", variant: "destructive" });
      return;
    }

    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_URL}/api/inventory/admin/bulk`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          ids: Array.from(selected),
          action
        })
      });

      if (response.ok) {
        const data = await response.json();
        toast({
          title: "Bulk Action Complete",
          description: `Updated ${data.updated} items`
        });
        setSelected(new Set());
        fetchInventory();
      }
    } catch (error) {
      toast({ title: "Bulk action failed", variant: "destructive" });
    }
  };

  const exportCSV = () => {
    const token = localStorage.getItem('token');
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => {
      if (value && value !== '__all__') params.append(key, value);
    });
    window.open(`${API_URL}/api/inventory/export.csv?${params}&token=${token}`, '_blank');
  };

  const clearFilters = () => {
    setFilters({
      q: '', status: '', ebay_status: '', condition: '', category: '',
      storage: '', sku_code: '', ebay_listing_id: '', part_number: ''
    });
  };

  const toggleSelect = (id: number) => {
    const newSelected = new Set(selected);
    if (newSelected.has(id)) {
      newSelected.delete(id);
    } else {
      newSelected.add(id);
    }
    setSelected(newSelected);
  };

  const toggleSelectAll = () => {
    if (selected.size === items.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(items.map(i => i.id)));
    }
  };

  const getStatusColor = (status: string) => {
    const colors: Record<string, string> = {
      AVAILABLE: '#4ade80',
      LISTED: '#60a5fa',
      SOLD: '#9ca3af',
      FROZEN: '#fb923c',
      REPAIR: '#fbbf24',
      RETURNED: '#f87171',
      PENDING_LISTING: '#a78bfa'
    };
    return colors[status] || '#9ca3af';
  };

  const getEbayDot = (ebayStatus?: string) => {
    if (!ebayStatus) return '#d1d5db';
    const colors: Record<string, string> = {
      ACTIVE: '#22c55e',
      ENDED: '#6b7280',
      DRAFT: '#a855f7',
      PENDING: '#eab308',
      UNKNOWN: '#d1d5db'
    };
    return colors[ebayStatus] || '#d1d5db';
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <FixedHeader />
      
      <div className="pt-12">
        {/* Toolbar */}
        <div className="bg-white border-b border-gray-200 px-2 py-1.5 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <button
              onClick={() => handleBulkAction('freeze')}
              disabled={selected.size === 0}
              className="px-2 py-1 text-xs bg-orange-500 text-white rounded disabled:opacity-50 hover:bg-orange-600"
            >
              Freeze
            </button>
            <button
              onClick={() => handleBulkAction('relist')}
              disabled={selected.size === 0}
              className="px-2 py-1 text-xs bg-purple-500 text-white rounded disabled:opacity-50 hover:bg-purple-600"
            >
              Relist
            </button>
            <button
              onClick={() => handleBulkAction('mark_listed')}
              disabled={selected.size === 0}
              className="px-2 py-1 text-xs bg-blue-500 text-white rounded disabled:opacity-50 hover:bg-blue-600"
            >
              Mark Listed
            </button>
            <button
              onClick={() => handleBulkAction('cancel_listings')}
              disabled={selected.size === 0}
              className="px-2 py-1 text-xs bg-red-500 text-white rounded disabled:opacity-50 hover:bg-red-600"
            >
              Cancel
            </button>
            <button
              onClick={exportCSV}
              className="px-2 py-1 text-xs bg-green-500 text-white rounded hover:bg-green-600 flex items-center gap-1"
            >
              <Download className="h-3 w-3" />
              CSV
            </button>
            <button
              onClick={fetchInventory}
              className="px-2 py-1 text-xs bg-gray-500 text-white rounded hover:bg-gray-600 flex items-center gap-1"
            >
              <RefreshCw className="h-3 w-3" />
            </button>
          </div>
          
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-600">
              {selected.size > 0 ? `${selected.size} selected | ` : ''}
              Total: {total}
            </span>
            <button
              onClick={clearFilters}
              className="px-2 py-1 text-xs text-gray-600 hover:text-gray-900 flex items-center gap-1"
            >
              <X className="h-3 w-3" />
              Clear
            </button>
          </div>
        </div>

        {/* Filters */}
        <div className="bg-gray-100 border-b border-gray-300 px-2 py-1 flex items-center gap-2 flex-wrap">
          <select
            value={filters.status}
            onChange={(e) => setFilters({...filters, status: e.target.value})}
            className="h-6 px-2 text-xs border border-gray-300 rounded bg-white"
          >
            <option value="">Status</option>
            <option value="AVAILABLE">Available</option>
            <option value="LISTED">Listed</option>
            <option value="SOLD">Sold</option>
            <option value="FROZEN">Frozen</option>
            <option value="REPAIR">Repair</option>
            <option value="PENDING_LISTING">Pending</option>
          </select>

          <select
            value={filters.ebay_status}
            onChange={(e) => setFilters({...filters, ebay_status: e.target.value})}
            className="h-6 px-2 text-xs border border-gray-300 rounded bg-white"
          >
            <option value="">eBay Status</option>
            <option value="ACTIVE">Active</option>
            <option value="ENDED">Ended</option>
            <option value="DRAFT">Draft</option>
            <option value="PENDING">Pending</option>
          </select>

          <input
            placeholder="Storage ID"
            value={filters.storage}
            onChange={(e) => setFilters({...filters, storage: e.target.value})}
            className="h-6 px-2 text-xs border border-gray-300 rounded w-24"
          />

          <input
            placeholder="SKU"
            value={filters.sku_code}
            onChange={(e) => setFilters({...filters, sku_code: e.target.value})}
            className="h-6 px-2 text-xs border border-gray-300 rounded w-32"
          />

          <input
            placeholder="ItemID"
            value={filters.ebay_listing_id}
            onChange={(e) => setFilters({...filters, ebay_listing_id: e.target.value})}
            className="h-6 px-2 text-xs border border-gray-300 rounded w-32"
          />

          <input
            placeholder="Part#"
            value={filters.part_number}
            onChange={(e) => setFilters({...filters, part_number: e.target.value})}
            className="h-6 px-2 text-xs border border-gray-300 rounded w-24"
          />

          <input
            placeholder="Title..."
            value={filters.q}
            onChange={(e) => setFilters({...filters, q: e.target.value})}
            className="h-6 px-2 text-xs border border-gray-300 rounded flex-1"
          />
        </div>

        {/* Grid Table */}
        <div className="overflow-x-auto">
          <table className="w-full text-xs border-collapse">
            <thead className="bg-gray-200 sticky top-12">
              <tr className="border-b border-gray-300">
                <th className="p-1 border-r border-gray-300 w-8">
                  <input
                    type="checkbox"
                    checked={selected.size === items.length && items.length > 0}
                    onChange={toggleSelectAll}
                    className="h-3 w-3"
                  />
                </th>
                <th className="p-1 border-r border-gray-300 text-left font-semibold">SKU</th>
                <th className="p-1 border-r border-gray-300 text-left font-semibold w-6">eBay</th>
                <th className="p-1 border-r border-gray-300 text-left font-semibold w-6">Img</th>
                <th className="p-1 border-r border-gray-300 text-left font-semibold">Status</th>
                <th className="p-1 border-r border-gray-300 text-left font-semibold">Storage</th>
                <th className="p-1 border-r border-gray-300 text-left font-semibold">Model</th>
                <th className="p-1 border-r border-gray-300 text-left font-semibold">ItemID</th>
                <th className="p-1 border-r border-gray-300 text-left font-semibold">Category</th>
                <th className="p-1 border-r border-gray-300 text-left font-semibold">Title</th>
                <th className="p-1 border-r border-gray-300 text-right font-semibold">Price</th>
                <th className="p-1 border-r border-gray-300 text-center font-semibold w-10">Qty</th>
                <th className="p-1 border-r border-gray-300 text-left font-semibold">Created</th>
                <th className="p-1 text-left font-semibold">Author</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={14} className="text-center py-8 text-gray-500">
                    Loading...
                  </td>
                </tr>
              ) : items.length === 0 ? (
                <tr>
                  <td colSpan={14} className="text-center py-8 text-gray-500">
                    No inventory items found
                  </td>
                </tr>
              ) : (
                items.map((item, idx) => (
                  <tr
                    key={item.id}
                    className={`border-b border-gray-200 hover:bg-blue-50 cursor-pointer ${
                      idx % 2 === 0 ? 'bg-white' : 'bg-gray-50'
                    }`}
                  >
                    <td className="p-1 border-r border-gray-200" onClick={(e) => e.stopPropagation()}>
                      <input
                        type="checkbox"
                        checked={selected.has(item.id)}
                        onChange={() => toggleSelect(item.id)}
                        className="h-3 w-3"
                      />
                    </td>
                    <td className="p-1 border-r border-gray-200 font-mono">{item.sku_code || '-'}</td>
                    <td className="p-1 border-r border-gray-200 text-center">
                      <div
                        className="inline-block h-2.5 w-2.5 rounded-full"
                        style={{ backgroundColor: getEbayDot(item.ebay_status) }}
                        title={item.ebay_status}
                      />
                    </td>
                    <td className="p-1 border-r border-gray-200 text-center text-gray-600">
                      {item.photo_count > 0 ? item.photo_count : '-'}
                    </td>
                    <td className="p-1 border-r border-gray-200">
                      <span
                        className="px-1.5 py-0.5 rounded text-white text-xxs font-medium"
                        style={{ backgroundColor: getStatusColor(item.status) }}
                      >
                        {item.status}
                      </span>
                    </td>
                    <td className="p-1 border-r border-gray-200 font-mono">{item.storage_id || '-'}</td>
                    <td className="p-1 border-r border-gray-200 truncate max-w-xs">{item.model || '-'}</td>
                    <td className="p-1 border-r border-gray-200 font-mono text-xxs">{item.ebay_listing_id?.substring(0, 10) || '-'}</td>
                    <td className="p-1 border-r border-gray-200">{item.category || '-'}</td>
                    <td className="p-1 border-r border-gray-200 truncate max-w-md">{item.title || '-'}</td>
                    <td className="p-1 border-r border-gray-200 text-right font-medium">
                      {item.price_value ? `${item.price_currency} ${item.price_value.toFixed(2)}` : '-'}
                    </td>
                    <td className="p-1 border-r border-gray-200 text-center">{item.quantity}</td>
                    <td className="p-1 border-r border-gray-200 text-gray-600">
                      {item.rec_created ? new Date(item.rec_created).toLocaleDateString('en-US', { month: '2-digit', day: '2-digit', year: '2-digit' }) : '-'}
                    </td>
                    <td className="p-1">{item.author || '-'}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      <style>{`
        .text-xxs { font-size: 0.625rem; line-height: 0.75rem; }
      `}</style>
    </div>
  );
}
