import FixedHeader from '@/components/FixedHeader';
import { DataGridPage } from '@/components/DataGridPage';

export default function TransactionsPage() {
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
