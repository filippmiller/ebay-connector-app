import FixedHeader from '@/components/FixedHeader';
import { DataGridPage } from '@/components/DataGridPage';

export default function BuyingPage() {
  return (
    <div className="h-screen flex flex-col bg-gray-50">
      <FixedHeader />
      <div className="pt-16 flex-1 px-4 py-6 overflow-hidden">
        <div className="w-full h-full flex flex-col">
          <h1 className="text-3xl font-bold mb-6">Buying (Purchases)</h1>
          <div className="flex-1 min-h-0">
            <DataGridPage gridKey="buying" title="Buying (Purchases)" />
          </div>
        </div>
      </div>
    </div>
  );
}
