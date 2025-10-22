import { useState, useEffect } from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Checkbox } from '@/components/ui/checkbox';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { Loader2, Download, RefreshCw, X, Camera } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';

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
  rec_updated?: string;
  author?: string;
  buyer_info?: string;
  tracking_number?: string;
  notes?: string;
}

export default function InventoryPageV2() {
  const [items, setItems] = useState<InventoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [total, setTotal] = useState(0);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [detailId, setDetailId] = useState<number | null>(null);
  const [detailItem, setDetailItem] = useState<InventoryItem | null>(null);
  
  const [filters, setFilters] = useState({
    q: '',
    status: '',
    ebay_status: '',
    condition: '',
    category: '',
    storage: '',
    warehouse_id: '',
    sku_code: '',
    ebay_listing_id: '',
    part_number: '',
    author: '',
    tracking_number: '',
    buyer_info: '',
    date_from: '',
    date_to: ''
  });
  
  const { toast } = useToast();
  const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

  useEffect(() => {
    fetchInventory();
  }, [filters]);

  useEffect(() => {
    if (detailId) {
      fetchDetail(detailId);
    }
  }, [detailId]);

  const fetchInventory = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const params = new URLSearchParams();
      
      Object.entries(filters).forEach(([key, value]) => {
        if (value && value !== '__all__') params.append(key, value);
      });
      params.append('limit', '100');
      
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

  const fetchDetail = async (id: number) => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_URL}/api/inventory/${id}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      
      if (response.ok) {
        const data = await response.json();
        setDetailItem(data);
      }
    } catch (error) {
      console.error('Failed to fetch detail:', error);
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
      if (value) params.append(key, value);
    });
    window.open(`${API_URL}/api/inventory/export.csv?${params}&token=${token}`, '_blank');
  };

  const clearFilters = () => {
    setFilters({
      q: '', status: '', ebay_status: '', condition: '', category: '',
      storage: '', warehouse_id: '', sku_code: '', ebay_listing_id: '',
      part_number: '', author: '', tracking_number: '', buyer_info: '',
      date_from: '', date_to: ''
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

  const getStatusBadge = (status: string) => {
    const colors: Record<string, string> = {
      AVAILABLE: 'bg-green-100 text-green-800',
      LISTED: 'bg-blue-100 text-blue-800',
      SOLD: 'bg-gray-100 text-gray-800',
      FROZEN: 'bg-orange-100 text-orange-800',
      REPAIR: 'bg-yellow-100 text-yellow-800',
      RETURNED: 'bg-red-100 text-red-800',
      PENDING_LISTING: 'bg-purple-100 text-purple-800'
    };
    return <Badge className={colors[status] || 'bg-gray-100'}>{status}</Badge>;
  };

  const getEbayBadge = (ebayStatus?: string) => {
    if (!ebayStatus) return null;
    const colors: Record<string, string> = {
      ACTIVE: 'bg-green-500',
      ENDED: 'bg-gray-500',
      DRAFT: 'bg-purple-500',
      PENDING: 'bg-yellow-500',
      UNKNOWN: 'bg-gray-300'
    };
    return <div className={`h-3 w-3 rounded-full ${colors[ebayStatus] || 'bg-gray-300'}`} title={ebayStatus} />;
  };

  return (
    <div className="container mx-auto p-6">
      <div className="flex justify-between items-center mb-4">
        <h1 className="text-3xl font-bold">Production Inventory</h1>
        <div className="flex gap-2">
          <Button onClick={exportCSV} variant="outline" size="sm">
            <Download className="h-4 w-4 mr-1" />
            Export CSV
          </Button>
          <Button onClick={fetchInventory} variant="outline" size="sm">
            <RefreshCw className="h-4 w-4 mr-1" />
            Reload
          </Button>
        </div>
      </div>

      <Card className="mb-4 p-4">
        <div className="flex justify-between items-center mb-3">
          <div className="flex gap-2">
            <Button size="sm" onClick={() => handleBulkAction('freeze')} disabled={selected.size === 0}>
              Freeze Listings
            </Button>
            <Button size="sm" onClick={() => handleBulkAction('relist')} disabled={selected.size === 0}>
              Relistings
            </Button>
            <Button size="sm" onClick={() => handleBulkAction('mark_listed')} disabled={selected.size === 0}>
              Mark as Listed
            </Button>
            <Button size="sm" onClick={() => handleBulkAction('cancel_listings')} disabled={selected.size === 0}>
              Cancel Listings
            </Button>
          </div>
          <Button onClick={clearFilters} variant="ghost" size="sm">
            <X className="h-4 w-4 mr-1" />
            Clear Filters
          </Button>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
          <Select value={filters.status} onValueChange={(v) => setFilters({...filters, status: v})}>
            <SelectTrigger className="h-9">
              <SelectValue placeholder="Status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__all__">All Status</SelectItem>
              <SelectItem value="AVAILABLE">Available</SelectItem>
              <SelectItem value="LISTED">Listed</SelectItem>
              <SelectItem value="SOLD">Sold</SelectItem>
              <SelectItem value="FROZEN">Frozen</SelectItem>
              <SelectItem value="REPAIR">Repair</SelectItem>
              <SelectItem value="PENDING_LISTING">Pending</SelectItem>
            </SelectContent>
          </Select>

          <Select value={filters.ebay_status} onValueChange={(v) => setFilters({...filters, ebay_status: v})}>
            <SelectTrigger className="h-9">
              <SelectValue placeholder="eBay Status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__all__">All eBay</SelectItem>
              <SelectItem value="ACTIVE">Active</SelectItem>
              <SelectItem value="ENDED">Ended</SelectItem>
              <SelectItem value="DRAFT">Draft</SelectItem>
              <SelectItem value="PENDING">Pending</SelectItem>
            </SelectContent>
          </Select>

          <Input
            placeholder="Storage ID"
            value={filters.storage}
            onChange={(e) => setFilters({...filters, storage: e.target.value})}
            className="h-9"
          />

          <Input
            placeholder="SKU"
            value={filters.sku_code}
            onChange={(e) => setFilters({...filters, sku_code: e.target.value})}
            className="h-9"
          />

          <Input
            placeholder="ItemID / eBay ID"
            value={filters.ebay_listing_id}
            onChange={(e) => setFilters({...filters, ebay_listing_id: e.target.value})}
            className="h-9"
          />

          <Input
            placeholder="Part Number"
            value={filters.part_number}
            onChange={(e) => setFilters({...filters, part_number: e.target.value})}
            className="h-9"
          />

          <Input
            placeholder="Title Search"
            value={filters.q}
            onChange={(e) => setFilters({...filters, q: e.target.value})}
            className="h-9 col-span-2"
          />

          <Input
            placeholder="Author"
            value={filters.author}
            onChange={(e) => setFilters({...filters, author: e.target.value})}
            className="h-9"
          />

          <Input
            placeholder="Tracking #"
            value={filters.tracking_number}
            onChange={(e) => setFilters({...filters, tracking_number: e.target.value})}
            className="h-9"
          />
        </div>
      </Card>

      <Card>
        <div className="p-3 border-b flex justify-between items-center">
          <p className="text-sm text-gray-600">
            {selected.size > 0 ? `${selected.size} selected | ` : ''}
            Total: {total} items
          </p>
        </div>

        {loading ? (
          <div className="flex justify-center p-12">
            <Loader2 className="h-8 w-8 animate-spin" />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b">
                <tr>
                  <th className="p-2 w-10">
                    <Checkbox
                      checked={selected.size === items.length && items.length > 0}
                      onCheckedChange={toggleSelectAll}
                    />
                  </th>
                  <th className="p-2 text-left">SKU</th>
                  <th className="p-2 text-left">eBay</th>
                  <th className="p-2 text-left">Img</th>
                  <th className="p-2 text-left">Status</th>
                  <th className="p-2 text-left">Storage</th>
                  <th className="p-2 text-left">Model</th>
                  <th className="p-2 text-left">ItemID</th>
                  <th className="p-2 text-left">Category</th>
                  <th className="p-2 text-left">Title</th>
                  <th className="p-2 text-left">Price</th>
                  <th className="p-2 text-left">Qty</th>
                  <th className="p-2 text-left">Created</th>
                  <th className="p-2 text-left">Author</th>
                </tr>
              </thead>
              <tbody>
                {items.length === 0 ? (
                  <tr>
                    <td colSpan={14} className="text-center p-8 text-gray-500">
                      No inventory items found. Adjust filters or add items.
                    </td>
                  </tr>
                ) : (
                  items.map((item) => (
                    <tr
                      key={item.id}
                      className="border-b hover:bg-gray-50 cursor-pointer"
                      onClick={() => setDetailId(item.id)}
                    >
                      <td className="p-2" onClick={(e) => e.stopPropagation()}>
                        <Checkbox
                          checked={selected.has(item.id)}
                          onCheckedChange={() => toggleSelect(item.id)}
                        />
                      </td>
                      <td className="p-2 font-mono text-xs">{item.sku_code || '-'}</td>
                      <td className="p-2">{getEbayBadge(item.ebay_status)}</td>
                      <td className="p-2">
                        {item.photo_count > 0 ? (
                          <Badge variant="outline" className="text-xs">
                            <Camera className="h-3 w-3 mr-1" />
                            {item.photo_count}
                          </Badge>
                        ) : (
                          <span className="text-gray-400">-</span>
                        )}
                      </td>
                      <td className="p-2">{getStatusBadge(item.status)}</td>
                      <td className="p-2 text-xs">{item.storage_id || '-'}</td>
                      <td className="p-2 text-xs max-w-[150px] truncate">{item.model || '-'}</td>
                      <td className="p-2 text-xs">{item.ebay_listing_id?.substring(0, 12) || '-'}</td>
                      <td className="p-2 text-xs">{item.category || '-'}</td>
                      <td className="p-2 text-xs max-w-[200px] truncate">{item.title || '-'}</td>
                      <td className="p-2 text-xs font-medium">
                        {item.price_value ? `${item.price_currency} ${item.price_value.toFixed(2)}` : '-'}
                      </td>
                      <td className="p-2 text-xs">{item.quantity}</td>
                      <td className="p-2 text-xs text-gray-600">
                        {item.rec_created ? new Date(item.rec_created).toLocaleDateString() : '-'}
                      </td>
                      <td className="p-2 text-xs">{item.author || '-'}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Sheet open={detailId !== null} onOpenChange={(open) => !open && setDetailId(null)}>
        <SheetContent className="w-[600px] sm:w-[700px] overflow-y-auto">
          <SheetHeader>
            <SheetTitle>Inventory Item Detail</SheetTitle>
          </SheetHeader>
          
          {detailItem && (
            <div className="mt-6 space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <p className="text-sm font-medium text-gray-600">SKU Code</p>
                  <p className="text-sm">{detailItem.sku_code || '-'}</p>
                </div>
                <div>
                  <p className="text-sm font-medium text-gray-600">Status</p>
                  <p className="text-sm">{getStatusBadge(detailItem.status)}</p>
                </div>
                <div>
                  <p className="text-sm font-medium text-gray-600">Model</p>
                  <p className="text-sm">{detailItem.model || '-'}</p>
                </div>
                <div>
                  <p className="text-sm font-medium text-gray-600">Category</p>
                  <p className="text-sm">{detailItem.category || '-'}</p>
                </div>
                <div>
                  <p className="text-sm font-medium text-gray-600">Condition</p>
                  <p className="text-sm">{detailItem.condition || '-'}</p>
                </div>
                <div>
                  <p className="text-sm font-medium text-gray-600">Part Number</p>
                  <p className="text-sm">{detailItem.part_number || '-'}</p>
                </div>
                <div>
                  <p className="text-sm font-medium text-gray-600">Price</p>
                  <p className="text-sm font-medium">
                    {detailItem.price_value ? `${detailItem.price_currency} ${detailItem.price_value.toFixed(2)}` : '-'}
                  </p>
                </div>
                <div>
                  <p className="text-sm font-medium text-gray-600">Quantity</p>
                  <p className="text-sm">{detailItem.quantity}</p>
                </div>
                <div>
                  <p className="text-sm font-medium text-gray-600">Storage ID</p>
                  <p className="text-sm font-mono">{detailItem.storage_id || '-'}</p>
                </div>
                <div>
                  <p className="text-sm font-medium text-gray-600">Warehouse ID</p>
                  <p className="text-sm">{detailItem.warehouse_id || '-'}</p>
                </div>
                <div className="col-span-2">
                  <p className="text-sm font-medium text-gray-600">eBay Listing ID</p>
                  <p className="text-sm font-mono">{detailItem.ebay_listing_id || '-'}</p>
                </div>
                <div>
                  <p className="text-sm font-medium text-gray-600">eBay Status</p>
                  <p className="text-sm">{detailItem.ebay_status || '-'}</p>
                </div>
                <div>
                  <p className="text-sm font-medium text-gray-600">Photo Count</p>
                  <p className="text-sm">{detailItem.photo_count || 0}</p>
                </div>
                <div>
                  <p className="text-sm font-medium text-gray-600">Created</p>
                  <p className="text-sm">
                    {detailItem.rec_created ? new Date(detailItem.rec_created).toLocaleString() : '-'}
                  </p>
                </div>
                <div>
                  <p className="text-sm font-medium text-gray-600">Updated</p>
                  <p className="text-sm">
                    {detailItem.rec_updated ? new Date(detailItem.rec_updated).toLocaleString() : '-'}
                  </p>
                </div>
                <div>
                  <p className="text-sm font-medium text-gray-600">Author</p>
                  <p className="text-sm">{detailItem.author || '-'}</p>
                </div>
                <div>
                  <p className="text-sm font-medium text-gray-600">Tracking #</p>
                  <p className="text-sm">{detailItem.tracking_number || '-'}</p>
                </div>
                <div className="col-span-2">
                  <p className="text-sm font-medium text-gray-600">Title</p>
                  <p className="text-sm">{detailItem.title || '-'}</p>
                </div>
                <div className="col-span-2">
                  <p className="text-sm font-medium text-gray-600">Buyer Info</p>
                  <p className="text-sm">{detailItem.buyer_info || '-'}</p>
                </div>
                <div className="col-span-2">
                  <p className="text-sm font-medium text-gray-600">Notes</p>
                  <p className="text-sm whitespace-pre-wrap">{detailItem.notes || '-'}</p>
                </div>
              </div>
            </div>
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
}
