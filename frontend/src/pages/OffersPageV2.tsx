import { useState, useEffect } from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Loader2, RefreshCw, CheckCircle2, XCircle, Clock, Download } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import FixedHeader from '@/components/FixedHeader';

interface Offer {
  offer_id: string;
  direction: string;
  state: string;
  item_id: string;
  sku?: string;
  buyer_username?: string;
  quantity: number;
  price_value: number;
  price_currency: string;
  original_price_value?: number;
  created_at?: string;
  expires_at?: string;
  message?: string;
}

export default function OffersPageV2() {
  const [offers, setOffers] = useState<Offer[]>([]);
  const [loading, setLoading] = useState(true);
  const [total, setTotal] = useState(0);
  const [syncing, setSyncing] = useState(false);
  const [syncStatus, setSyncStatus] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  
  const [filters, setFilters] = useState({
    state: '',
    direction: '',
    buyer: '',
    item_id: '',
    sku: ''
  });
  
  const { toast } = useToast();
  const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

  useEffect(() => {
    fetchOffers();
  }, [filters]);

  useEffect(() => {
    if (jobId && syncing) {
      const interval = setInterval(() => pollJobStatus(jobId), 2000);
      return () => clearInterval(interval);
    }
  }, [jobId, syncing]);

  const fetchOffers = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const params = new URLSearchParams();
      if (filters.state) params.append('state', filters.state);
      if (filters.direction) params.append('direction', filters.direction);
      if (filters.buyer) params.append('buyer', filters.buyer);
      if (filters.item_id) params.append('item_id', filters.item_id);
      if (filters.sku) params.append('sku', filters.sku);
      params.append('limit', '50');
      
      const response = await fetch(`${API_URL}/api/offers?${params}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      
      if (response.ok) {
        const data = await response.json();
        setOffers(data.offers || []);
        setTotal(data.total || 0);
      }
    } catch (error) {
      console.error('Failed to fetch offers:', error);
    } finally {
      setLoading(false);
    }
  };

  const startSync = async () => {
    setSyncing(true);
    setSyncStatus('queued');
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_URL}/api/offers/admin/sync`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      
      if (response.ok) {
        const data = await response.json();
        setJobId(data.job_id);
        toast({ title: "Sync Started", description: "Offers sync job queued" });
      }
    } catch (error) {
      setSyncing(false);
      toast({ title: "Sync Failed", variant: "destructive" });
    }
  };

  const pollJobStatus = async (currentJobId: string) => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_URL}/api/offers/admin/sync/jobs/${currentJobId}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      
      if (response.ok) {
        const data = await response.json();
        setSyncStatus(data.status);
        
        if (data.status === 'success' || data.status === 'error') {
          setSyncing(false);
          if (data.status === 'success') {
            toast({ title: "Sync Complete", description: `Synced in ${data.duration_ms}ms` });
            fetchOffers();
          }
        }
      }
    } catch (error) {
      console.error('Failed to poll:', error);
    }
  };

  const exportCSV = () => {
    const token = localStorage.getItem('token');
    const params = new URLSearchParams();
    if (filters.state) params.append('state', filters.state);
    if (filters.direction) params.append('direction', filters.direction);
    if (filters.buyer) params.append('buyer', filters.buyer);
    if (filters.item_id) params.append('item_id', filters.item_id);
    if (filters.sku) params.append('sku', filters.sku);
    
    window.open(`${API_URL}/api/offers/export.csv?${params}&token=${token}`, '_blank');
  };

  const getStateBadge = (state: string) => {
    const colors: Record<string, string> = {
      PENDING: 'bg-yellow-100 text-yellow-800',
      ACCEPTED: 'bg-green-100 text-green-800',
      DECLINED: 'bg-red-100 text-red-800',
      EXPIRED: 'bg-gray-100 text-gray-800',
      COUNTERED: 'bg-blue-100 text-blue-800'
    };
    return <Badge className={colors[state] || 'bg-gray-100'}>{state}</Badge>;
  };

  const getDirectionBadge = (direction: string) => {
    return direction === 'INBOUND' ? 
      <Badge className="bg-purple-100 text-purple-800">Inbound</Badge> :
      <Badge className="bg-orange-100 text-orange-800">Outbound</Badge>;
  };

  const getSyncIcon = () => {
    if (syncStatus === 'success') return <CheckCircle2 className="h-4 w-4 text-green-600" />;
    if (syncStatus === 'error') return <XCircle className="h-4 w-4 text-red-600" />;
    if (syncing) return <Clock className="h-4 w-4 animate-pulse text-blue-600" />;
    return <RefreshCw className="h-4 w-4" />;
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <FixedHeader />
      <div className="pt-12 px-4 py-6">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-3xl font-bold">Offers (Best Offers)</h1>
        <div className="flex gap-2">
          <Button onClick={exportCSV} variant="outline">
            <Download className="h-4 w-4 mr-2" />
            Export CSV
          </Button>
          <Button onClick={startSync} disabled={syncing}>
            {getSyncIcon()}
            <span className="ml-2">{syncing ? 'Syncing...' : 'Sync Offers'}</span>
          </Button>
        </div>
      </div>

      <Card className="p-4 mb-4">
        <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
          <Select value={filters.state} onValueChange={(v) => setFilters({...filters, state: v})}>
            <SelectTrigger>
              <SelectValue placeholder="State" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="">All States</SelectItem>
              <SelectItem value="PENDING">Pending</SelectItem>
              <SelectItem value="ACCEPTED">Accepted</SelectItem>
              <SelectItem value="DECLINED">Declined</SelectItem>
              <SelectItem value="EXPIRED">Expired</SelectItem>
              <SelectItem value="COUNTERED">Countered</SelectItem>
            </SelectContent>
          </Select>

          <Select value={filters.direction} onValueChange={(v) => setFilters({...filters, direction: v})}>
            <SelectTrigger>
              <SelectValue placeholder="Direction" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="">All Directions</SelectItem>
              <SelectItem value="INBOUND">Inbound</SelectItem>
              <SelectItem value="OUTBOUND">Outbound</SelectItem>
            </SelectContent>
          </Select>

          <Input
            placeholder="Buyer username"
            value={filters.buyer}
            onChange={(e) => setFilters({...filters, buyer: e.target.value})}
          />

          <Input
            placeholder="Item ID"
            value={filters.item_id}
            onChange={(e) => setFilters({...filters, item_id: e.target.value})}
          />

          <Input
            placeholder="SKU"
            value={filters.sku}
            onChange={(e) => setFilters({...filters, sku: e.target.value})}
          />
        </div>
      </Card>

      {loading ? (
        <div className="flex justify-center p-12">
          <Loader2 className="h-8 w-8 animate-spin" />
        </div>
      ) : (
        <Card>
          <div className="p-4 border-b">
            <p className="text-sm text-gray-600">Total Offers: {total}</p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-50">
                <tr>
                  <th className="p-3 text-left text-sm font-medium">Offer ID</th>
                  <th className="p-3 text-left text-sm font-medium">Direction</th>
                  <th className="p-3 text-left text-sm font-medium">State</th>
                  <th className="p-3 text-left text-sm font-medium">Item ID</th>
                  <th className="p-3 text-left text-sm font-medium">SKU</th>
                  <th className="p-3 text-left text-sm font-medium">Buyer</th>
                  <th className="p-3 text-left text-sm font-medium">Qty</th>
                  <th className="p-3 text-left text-sm font-medium">Price</th>
                  <th className="p-3 text-left text-sm font-medium">Created</th>
                  <th className="p-3 text-left text-sm font-medium">Expires</th>
                </tr>
              </thead>
              <tbody>
                {offers.length === 0 ? (
                  <tr>
                    <td colSpan={10} className="text-center p-8 text-gray-500">
                      No offers found. Try syncing or adjusting filters.
                    </td>
                  </tr>
                ) : (
                  offers.map((offer) => (
                    <tr key={offer.offer_id} className="border-b hover:bg-gray-50">
                      <td className="p-3 text-sm font-mono">{offer.offer_id.substring(0, 12)}...</td>
                      <td className="p-3">{getDirectionBadge(offer.direction)}</td>
                      <td className="p-3">{getStateBadge(offer.state)}</td>
                      <td className="p-3 text-sm">{offer.item_id}</td>
                      <td className="p-3 text-sm">{offer.sku || '-'}</td>
                      <td className="p-3 text-sm">{offer.buyer_username || '-'}</td>
                      <td className="p-3 text-sm">{offer.quantity}</td>
                      <td className="p-3 text-sm font-medium">
                        {offer.price_currency} {offer.price_value.toFixed(2)}
                      </td>
                      <td className="p-3 text-sm text-gray-600">
                        {offer.created_at ? new Date(offer.created_at).toLocaleDateString() : '-'}
                      </td>
                      <td className="p-3 text-sm text-gray-600">
                        {offer.expires_at ? new Date(offer.expires_at).toLocaleDateString() : '-'}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </Card>
      )}
      </div>
    </div>
  );
}
