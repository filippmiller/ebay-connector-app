import { useState, useEffect } from 'react';
import FixedHeader from '@/components/FixedHeader';
import { DataGridPage } from '@/components/DataGridPage';

export default function TransactionsPage() {
  const [, setTransactions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);

  useEffect(() => {
    // legacy, no-op; DataGridPage handles data fetching
    setLoading(false);
  }, []);

  return (
    <div className="min-h-screen bg-gray-50">
      <FixedHeader />
      <div className="w-full pt-16 px-4 py-6">
        <div className="max-w-7xl mx-auto">
          <h1 className="text-3xl font-bold mb-6">Transactions (Sales)</h1>
          <div className="h-[70vh]">
            <DataGridPage gridKey="transactions" title="Transactions" />
          </div>
        </div>
      </div>
    </div>
  );
}
