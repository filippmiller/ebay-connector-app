import FixedHeader from '@/components/FixedHeader';
import { DataGridPage } from '@/components/DataGridPage';

export default function InventoryPage() {
  return (
    <div className="h-screen flex flex-col bg-white">
      <FixedHeader />
      <div className="pt-16 flex-1 px-4 py-6 overflow-hidden">
        <div className="w-full h-full flex flex-col">
          <h1 className="text-2xl font-bold mb-4">Inventory (Active listings)</h1>
          <div className="flex-1">
            <DataGridPage gridKey="active_inventory" title="Active Inventory" />
          </div>
        </div>
      </div>
    </div>
  );
}
