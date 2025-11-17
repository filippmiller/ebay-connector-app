import { useState, useEffect, useMemo } from 'react';
import { Card } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Loader2 } from 'lucide-react';
import FixedHeader from '@/components/FixedHeader';
import { DataGridPage } from '@/components/DataGridPage';

export default function FinancialsPage() {
  const [summary, setSummary] = useState({
    gross_sales: 0,
    total_fees: 0,
    net: 0,
    payouts_total: 0,
    refunds: 0
  });
  const [loading, setLoading] = useState(true);

  // Filters for the Finances ledger grid
  const [fromDate, setFromDate] = useState('');
  const [toDate, setToDate] = useState('');
  const [transactionType, setTransactionType] = useState('');

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

  const financesExtraParams = useMemo(() => {
    const params: Record<string, string> = {};
    if (fromDate) params.from = fromDate;
    if (toDate) params.to = toDate;
    if (transactionType) params.transaction_type = transactionType;
    return params;
  }, [fromDate, toDate, transactionType]);

  return (
    <div className="min-h-screen bg-gray-50">
      <FixedHeader />
      <div className="w-full pt-16 px-4 py-6">
        <div className="max-w-7xl mx-auto">
          <h1 className="text-3xl font-bold mb-6">Finances</h1>

          {loading ? (
            <div className="flex justify-center p-12">
              <Loader2 className="h-8 w-8 animate-spin" />
            </div>
          ) : (
            <Tabs defaultValue="summary" className="w-full">
              <TabsList>
                <TabsTrigger value="summary">Summary</TabsTrigger>
                <TabsTrigger value="ledger">Ledger</TabsTrigger>
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

              <TabsContent value="ledger">
                <div className="mt-6 space-y-4">
                  <div className="flex flex-wrap items-end gap-4">
                    <div>
                      <label className="block text-xs font-medium text-gray-600 mb-1">From</label>
                      <input
                        type="date"
                        className="border rounded px-2 py-1 text-sm"
                        value={fromDate}
                        onChange={(e) => setFromDate(e.target.value)}
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-600 mb-1">To</label>
                      <input
                        type="date"
                        className="border rounded px-2 py-1 text-sm"
                        value={toDate}
                        onChange={(e) => setToDate(e.target.value)}
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-600 mb-1">Transaction type</label>
                      <select
                        className="border rounded px-2 py-1 text-sm"
                        value={transactionType}
                        onChange={(e) => setTransactionType(e.target.value)}
                      >
                        <option value="">All</option>
                        <option value="SALE">SALE</option>
                        <option value="REFUND">REFUND</option>
                        <option value="SHIPPING_LABEL">SHIPPING_LABEL</option>
                        <option value="NON_SALE_CHARGE">NON_SALE_CHARGE</option>
                      </select>
                    </div>
                  </div>
                  <div className="h-[600px]">
                    <DataGridPage
                      gridKey="finances"
                      title="Finances ledger"
                      extraParams={financesExtraParams}
                    />
                  </div>
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
