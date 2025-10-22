import { useState, useEffect } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Loader2, CheckCircle2, XCircle, Clock, AlertCircle } from 'lucide-react';

interface SyncJob {
  id: number;
  job_id: string;
  endpoint: string;
  status: string;
  pages_fetched: number;
  records_fetched: number;
  records_stored: number;
  duration_ms: number;
  error_text?: string;
  started_at: string;
  completed_at?: string;
}

export default function AdminJobsPage() {
  const [jobs, setJobs] = useState<SyncJob[]>([]);
  const [loading, setLoading] = useState(true);
  
  const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

  useEffect(() => {
    fetchJobs();
    const interval = setInterval(fetchJobs, 5000);
    return () => clearInterval(interval);
  }, []);

  const fetchJobs = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_URL}/api/admin/sync-jobs?limit=50`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      
      if (response.ok) {
        const data = await response.json();
        setJobs(data.jobs || []);
      }
    } catch (error) {
      console.error('Failed to fetch jobs:', error);
    } finally {
      setLoading(false);
    }
  };

  const getStatusBadge = (status: string) => {
    const variants: Record<string, { icon: JSX.Element; className: string }> = {
      success: { icon: <CheckCircle2 className="h-4 w-4" />, className: "bg-green-100 text-green-800" },
      error: { icon: <XCircle className="h-4 w-4" />, className: "bg-red-100 text-red-800" },
      running: { icon: <Clock className="h-4 w-4 animate-pulse" />, className: "bg-blue-100 text-blue-800" },
      queued: { icon: <AlertCircle className="h-4 w-4" />, className: "bg-yellow-100 text-yellow-800" },
    };
    
    const variant = variants[status] || variants.queued;
    
    return (
      <Badge className={variant.className}>
        {variant.icon}
        <span className="ml-1">{status}</span>
      </Badge>
    );
  };

  const formatDuration = (ms: number) => {
    if (ms < 1000) return `${ms}ms`;
    return `${(ms / 1000).toFixed(2)}s`;
  };

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleString();
  };

  return (
    <div className="container mx-auto p-6">
      <h1 className="text-3xl font-bold mb-6">Admin: Sync Jobs Dashboard</h1>

      {loading ? (
        <div className="flex justify-center p-12">
          <Loader2 className="h-8 w-8 animate-spin" />
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium text-gray-600">Total Jobs</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{jobs.length}</div>
              </CardContent>
            </Card>
            
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium text-gray-600">Success</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold text-green-600">
                  {jobs.filter(j => j.status === 'success').length}
                </div>
              </CardContent>
            </Card>
            
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium text-gray-600">Running</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold text-blue-600">
                  {jobs.filter(j => j.status === 'running').length}
                </div>
              </CardContent>
            </Card>
            
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium text-gray-600">Failed</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold text-red-600">
                  {jobs.filter(j => j.status === 'error').length}
                </div>
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Recent Sync Jobs</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b">
                      <th className="text-left p-2">Status</th>
                      <th className="text-left p-2">Endpoint</th>
                      <th className="text-left p-2">Pages</th>
                      <th className="text-left p-2">Records</th>
                      <th className="text-left p-2">Duration</th>
                      <th className="text-left p-2">Started</th>
                      <th className="text-left p-2">Completed</th>
                    </tr>
                  </thead>
                  <tbody>
                    {jobs.length === 0 ? (
                      <tr>
                        <td colSpan={7} className="text-center p-8 text-gray-500">
                          No sync jobs yet. Trigger a sync from Buying, Transactions, or Financials pages.
                        </td>
                      </tr>
                    ) : (
                      jobs.map((job) => (
                        <tr key={job.id} className="border-b hover:bg-gray-50">
                          <td className="p-2">{getStatusBadge(job.status)}</td>
                          <td className="p-2 font-medium">{job.endpoint}</td>
                          <td className="p-2">{job.pages_fetched || 0}</td>
                          <td className="p-2">{job.records_stored || 0}</td>
                          <td className="p-2">{formatDuration(job.duration_ms || 0)}</td>
                          <td className="p-2 text-sm text-gray-600">{formatDate(job.started_at)}</td>
                          <td className="p-2 text-sm text-gray-600">
                            {job.completed_at ? formatDate(job.completed_at) : '-'}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
