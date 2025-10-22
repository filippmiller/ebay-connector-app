import { useState, useEffect } from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Loader2, RefreshCw, CheckCircle2, XCircle, Clock } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import FixedHeader from '@/components/FixedHeader';

export default function BuyingPage() {
  const [, setPurchases] = useState([]);
  const [loading, setLoading] = useState(true);
  const [total, setTotal] = useState(0);
  const [syncing, setSyncing] = useState(false);
  const [syncStatus, setSyncStatus] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  
  const { toast } = useToast();
  const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

  useEffect(() => {
    fetchPurchases();
  }, []);

  useEffect(() => {
    if (jobId && syncing) {
      const interval = setInterval(() => pollJobStatus(jobId), 2000);
      return () => clearInterval(interval);
    }
  }, [jobId, syncing]);

  const fetchPurchases = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_URL}/api/buying?limit=50`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      
      if (response.ok) {
        const data = await response.json();
        setPurchases(data.purchases || []);
        setTotal(data.total || 0);
      }
    } catch (error) {
      console.error('Failed to fetch purchases:', error);
    } finally {
      setLoading(false);
    }
  };

  const startSync = async () => {
    setSyncing(true);
    setSyncStatus('queued');
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_URL}/api/buying/admin/sync`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      
      if (response.ok) {
        const data = await response.json();
        setJobId(data.job_id);
        toast({ title: "Sync Started", description: "Buying sync job queued" });
      }
    } catch (error) {
      setSyncing(false);
      toast({ title: "Sync Failed", variant: "destructive" });
    }
  };

  const pollJobStatus = async (currentJobId: string) => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_URL}/api/buying/admin/sync/jobs/${currentJobId}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      
      if (response.ok) {
        const data = await response.json();
        setSyncStatus(data.status);
        
        if (data.status === 'success' || data.status === 'error') {
          setSyncing(false);
          if (data.status === 'success') {
            toast({ title: "Sync Complete", description: `Synced in ${data.duration_ms}ms` });
            fetchPurchases();
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
    <div className="min-h-screen bg-gray-50">
      <FixedHeader />
      <div className="pt-12 px-4 py-6">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-3xl font-bold">Buying (Purchases)</h1>
        <Button onClick={startSync} disabled={syncing}>
          {getSyncIcon()}
          <span className="ml-2">{syncing ? 'Syncing...' : 'Sync Purchases'}</span>
        </Button>
      </div>

      {loading ? (
        <div className="flex justify-center p-12">
          <Loader2 className="h-8 w-8 animate-spin" />
        </div>
      ) : (
        <Card className="p-6">
          <div className="text-center">
            <p className="text-xl font-semibold mb-2">Total Purchases: {total}</p>
            <p className="text-gray-600">Buying module is live with sync</p>
            <p className="text-sm text-gray-500 mt-4">API: GET /api/buying + POST /admin/sync</p>
            {syncStatus && (
              <div className="mt-4">
                <span className="text-sm px-3 py-1 rounded-full bg-gray-100">
                  Last sync: {syncStatus}
                </span>
              </div>
            )}
          </div>
        </Card>
      )}
      </div>
    </div>
  );
}
