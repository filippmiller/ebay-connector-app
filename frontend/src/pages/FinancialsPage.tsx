import { useState, useEffect, useMemo } from 'react';
import { Card } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Loader2 } from 'lucide-react';
import FixedHeader from '@/components/FixedHeader';
import { DataGridPage } from '@/components/DataGridPage';
import api from '@/lib/apiClient';

interface FinancialSummaryData {
  gross_sales: number;
  total_fees: number;
  net: number;
  payouts_total: number;
  refunds: number;
}

export default function FinancialsPage() {
  const [summary, setSummary] = useState<FinancialSummaryData>({
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
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    fetchSummary();
  }, []);

  const fetchSummary = async () => {
    try {
      const response = await api.get<FinancialSummaryData>('/financials/summary');
      setSummary(response.data);
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
    if (searchQuery) params.search = searchQuery;
    return params;
  }, [fromDate, toDate, transactionType, searchQuery]);

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      <FixedHeader />
      {/* Content area below fixed header fills remaining viewport height */}
      <div className="flex-1 pt-16 px-4 pb-4">
        <div className="h-full w-full flex flex-col">
          <h1 className="text-3xl font-bold mb-4">Finances</h1>

          {loading ? (
            <div className="flex-1 flex justify-center items-center">
              <Loader2 className="h-8 w-8 animate-spin" />
            </div>
          ) : (
            <Tabs defaultValue="ledger" className="w-full h-full flex flex-col">
              <TabsList>
                <TabsTrigger value="summary">Summary</TabsTrigger>
                <TabsTrigger value="ledger">Ledger</TabsTrigger>
                <TabsTrigger value="fees">Fees</TabsTrigger>
                <TabsTrigger value="payouts">Payouts</TabsTrigger>
              </TabsList>

              <TabsContent value="summary">
                <FinancialSummaryCards summary={summary} />
              </TabsContent>

              <TabsContent value="ledger" className="flex-1 flex flex-col">
                <FinancialSummaryCards summary={summary} />
                {/* Full-width ledger grid directly under summary */}
                <div className="mt-6 space-y-4 flex-1 flex flex-col">
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
                    <div className="flex-1 min-w-[200px]">
                      <label className="block text-xs font-medium text-gray-600 mb-1">Search</label>
                      <input
                        type="text"
                        className="border rounded px-2 py-1 text-sm w-full"
                        placeholder="Search across financial transactions..."
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                      />
                    </div>
                  </div>
                  <div className="flex-1 min-h-0">
                    <DataGridPage
                      gridKey="finances"
                      title="Finances ledger"
                      extraParams={financesExtraParams}
                    />
                  </div>
                </div>
              </TabsContent>

              <TabsContent value="fees" className="flex-1 flex flex-col">
                <div className="mt-4 flex-1 min-h-0">
                  <DataGridPage
                    gridKey="finances_fees"
                    title="Finances fees"
                    extraParams={financesExtraParams}
                  />
                </div>
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

function FinancialSummaryCards({ summary }: { summary: FinancialSummaryData }) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-4 w-full">
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
  );
}
