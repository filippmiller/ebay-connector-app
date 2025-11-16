import FixedHeader from '@/components/FixedHeader';
import { DataGridPage } from '@/components/DataGridPage';

export default function TransactionsPage() {
  return (
    <div className="h-screen flex flex-col bg-gray-50">
      <FixedHeader />
      {/* Main content area under fixed header: full width, grid fills all available space */}
      <div className="pt-16 flex-1 px-4 py-6 overflow-hidden">
        <div className="w-full h-full flex flex-col">
          <h1 className="text-3xl font-bold mb-6">Transactions (Sales)</h1>
          <div className="flex-1">
            <DataGridPage gridKey="transactions" title="Transactions" />
          </div>
        </div>
      </div>
    </div>
  );
}
