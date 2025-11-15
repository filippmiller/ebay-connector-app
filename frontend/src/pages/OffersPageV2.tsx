import { useState, useEffect, useMemo } from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { RefreshCw, CheckCircle2, XCircle, Clock, Download } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import FixedHeader from '@/components/FixedHeader';
import api from '@/lib/apiClient';
import { DataGridPage } from '@/components/DataGridPage';

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
  const [syncing, setSyncing] = useState(false);
  const [syncStatus, setSyncStatus] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  
  const [filters, setFilters] = useState({
    state: '',
    direction: '',
    buyer: '',
    item_id: '',
    sku: ''
  });
  
  const { toast } = useToast();

  const gridParams = useMemo(() => {
    const params: Record<string, string | number> = { _refresh: refreshKey };
    if (filters.state) params.state = filters.state;
    if (filters.direction) params.direction = filters.direction;
    if (filters.buyer) params.buyer = filters.buyer;
    if (filters.item_id) params.item_id = filters.item_id;
    if (filters.sku) params.sku = filters.sku;
    return params;
  }, [filters, refreshKey]);

  useEffect(() => {
    if (jobId && syncing) {
      const interval = setInterval(() => pollJobStatus(jobId), 2000);
      return () => clearInterval(interval);
    }
  }, [jobId, syncing]);

  const startSync = async () => {
    setSyncing(true);
    setSyncStatus('queued');
    try {
      const { data } = await api.post('/offers/admin/sync');
      setJobId(data.job_id);
      toast({ title: "Sync Started", description: "Offers sync job queued" });
    } catch (error) {
      setSyncing(false);
      toast({ title: "Sync Failed", variant: "destructive" });
    }
  };

  const pollJobStatus = async (currentJobId: string) => {
    try {
      const { data } = await api.get(`/offers/admin/sync/jobs/${currentJobId}`);
      setSyncStatus(data.status);
      
      if (data.status === 'success' || data.status === 'error') {
        setSyncing(false);
        if (data.status === 'success') {
          toast({ title: "Sync Complete", description: `Synced in ${data.duration_ms}ms` });
          setRefreshKey((k) => k + 1);
        }
      }
    } catch (error) {
      console.error('Failed to poll:', error);
    }
  };

  const exportCSV = async () => {
    try {
      const params: Record<string, string> = {};
      if (filters.state) params.state = filters.state;
      if (filters.direction) params.direction = filters.direction;
      if (filters.buyer) params.buyer = filters.buyer;
      if (filters.item_id) params.item_id = filters.item_id;
      if (filters.sku) params.sku = filters.sku;

      const response = await api.get('/offers/export.csv', {
        params,
        responseType: 'blob',
      });

      const blob = new Blob([response.data], { type: 'text/csv;charset=utf-8;' });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `offers-${new Date().toISOString()}.csv`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (error) {
      console.error('Failed to export offers:', error);
      toast({ title: "Export Failed", variant: "destructive" });
    }
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
          <Select
            value={filters.state || '__all__'}
            onValueChange={(v) => setFilters({ ...filters, state: v === '__all__' ? '' : v })}
          >
            <SelectTrigger>
              <SelectValue placeholder="State" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__all__">All States</SelectItem>
              <SelectItem value="PENDING">Pending</SelectItem>
              <SelectItem value="ACCEPTED">Accepted</SelectItem>
              <SelectItem value="DECLINED">Declined</SelectItem>
              <SelectItem value="EXPIRED">Expired</SelectItem>
              <SelectItem value="COUNTERED">Countered</SelectItem>
            </SelectContent>
          </Select>

          <Select
            value={filters.direction || '__all__'}
            onValueChange={(v) => setFilters({ ...filters, direction: v === '__all__' ? '' : v })}
          >
            <SelectTrigger>
              <SelectValue placeholder="Direction" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__all__">All Directions</SelectItem>
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
        <Card className="mt-4">
          <div className="h-[60vh] p-4">
            <DataGridPage gridKey="offers" title="Offers" extraParams={gridParams} />
          </div>
        </Card>
      )}
      </div>
    </div>
  );
}
