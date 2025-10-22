import { useState, useEffect } from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Loader2, RefreshCw, CheckCircle2, XCircle, Clock } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';

export default function FinancialsPage() {
  const [summary, setSummary] = useState({
    gross_sales: 0,
    total_fees: 0,
    net: 0,
    payouts_total: 0,
    refunds: 0
  });
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [syncStatus, setSyncStatus] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  
  const { toast } = useToast();
  const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

  useEffect(() => {
    fetchSummary();
  }, []);

  useEffect(() => {
    if (jobId && syncing) {
      const interval = setInterval(() => pollJobStatus(jobId), 2000);
      return () => clearInterval(interval);
    }
  }, [jobId, syncing]);

  const fetchSummary = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_URL}/api/financials/summary`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      
      if (response.ok) {
        const data = await response.json();
        setSummary(data);
      }
    } catch (error) {
      console.error('Failed to fetch financials:', error);
    } finally {
      setLoading(false);
    }
  };

  const startSync = async () => {
    setSyncing(true);
    setSyncStatus('queued');
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_URL}/api/financials/admin/sync`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      
      if (response.ok) {
        const data = await response.json();
        setJobId(data.job_id);
        toast({ title: "Sync Started", description: "Financials sync job queued" });
      }
    } catch (error) {
      setSyncing(false);
      toast({ title: "Sync Failed", variant: "destructive" });
    }
  };

  const pollJobStatus = async (currentJobId: string) => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_URL}/api/financials/admin/sync/jobs/${currentJobId}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      
      if (response.ok) {
        const data = await response.json();
        setSyncStatus(data.status);
        
        if (data.status === 'success' || data.status === 'error') {
          setSyncing(false);
          if (data.status === 'success') {
            toast({ title: "Sync Complete", description: `Synced in ${data.duration_ms}ms` });
            fetchSummary();
          }
        }
      }
    } catch (error) {
      console.error('Failed to poll:', error);
    }
  };

  const getSyncIcon = () => {
    if (syncStatus === 'success') return <CheckCircle2 className="h-4 w-4 text-green-600" />;
    if (syncStatus === 'error') return <XCircle className="h-4 w-4 text-red-600" />;
    if (syncing) return <Clock className="h-4 w-4 animate-pulse text-blue-600" />;
    return <RefreshCw className="h-4 w-4" />;
  };

  return (
    <div className="container mx-auto p-6">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-3xl font-bold">Financials</h1>
        <Button onClick={startSync} disabled={syncing}>
          {getSyncIcon()}
          <span className="ml-2">{syncing ? 'Syncing...' : 'Sync Financials'}</span>
        </Button>
      </div>

      {loading ? (
        <div className="flex justify-center p-12">
          <Loader2 className="h-8 w-8 animate-spin" />
        </div>
      ) : (
        <Tabs defaultValue="summary" className="w-full">
          <TabsList>
            <TabsTrigger value="summary">Summary</TabsTrigger>
            <TabsTrigger value="fees">Fees</TabsTrigger>
            <TabsTrigger value="payouts">Payouts</TabsTrigger>
          </TabsList>
          
          <TabsContent value="summary">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-4">
              <Card className="p-4">
                <div className="text-sm text-gray-600">Gross Sales</div>
                <div className="text-2xl font-bold">${summary.gross_sales.toFixed(2)}</div>
              </Card>
              <Card className="p-4">
                <div className="text-sm text-gray-600">Total Fees</div>
                <div className="text-2xl font-bold">${summary.total_fees.toFixed(2)}</div>
              </Card>
              <Card className="p-4">
                <div className="text-sm text-gray-600">Net</div>
                <div className="text-2xl font-bold text-green-600">${summary.net.toFixed(2)}</div>
              </Card>
              <Card className="p-4">
                <div className="text-sm text-gray-600">Payouts</div>
                <div className="text-2xl font-bold">${summary.payouts_total.toFixed(2)}</div>
              </Card>
            </div>
          </TabsContent>
          
          <TabsContent value="fees">
            <Card className="p-6 mt-4">
              <p className="text-gray-600">Fees module ready with sync</p>
            </Card>
          </TabsContent>
          
          <TabsContent value="payouts">
            <Card className="p-6 mt-4">
              <p className="text-gray-600">Payouts module ready with sync</p>
            </Card>
          </TabsContent>
        </Tabs>
      )}
    </div>
  );
}
