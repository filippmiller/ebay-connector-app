import { useState, useEffect } from 'react';
import { Card } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Loader2 } from 'lucide-react';
import FixedHeader from '@/components/FixedHeader';

export default function FinancialsPage() {
  const [summary, setSummary] = useState({
    gross_sales: 0,
    total_fees: 0,
    net: 0,
    payouts_total: 0,
    refunds: 0
  });
  const [loading, setLoading] = useState(true);
  
  const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

  useEffect(() => {
    fetchSummary();
  }, []);

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

  return (
    <div className="min-h-screen bg-gray-50">
      <FixedHeader />
      <div className="w-full pt-16 px-4 py-6">
        <div className="max-w-7xl mx-auto">
          <h1 className="text-3xl font-bold mb-6">Financials</h1>

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
                  <p className="text-gray-600">Fees module ready</p>
                </Card>
              </TabsContent>
              
              <TabsContent value="payouts">
                <Card className="p-6 mt-4">
                  <p className="text-gray-600">Payouts module ready</p>
                </Card>
              </TabsContent>
            </Tabs>
          )}
        </div>
      </div>
    </div>
  );
}
