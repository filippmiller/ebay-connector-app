import FixedHeader from '@/components/FixedHeader';
import { DataGridPage } from '@/components/DataGridPage';

export default function CasesPage() {
  return (
    <div className="h-screen flex flex-col bg-gray-50">
      <FixedHeader />
      {/* Main content area under fixed header: full width, grid fills all available space */}
      <div className="pt-16 flex-1 px-4 py-6 overflow-hidden">
        <div className="w-full h-full flex flex-col">
          <div className="mb-4">
            <h1 className="text-3xl font-bold">Cases &amp; Disputes</h1>
            <p className="text-gray-600 mt-2 text-sm max-w-3xl">
              Unified view of Item Not Received (INR) and Significantly Not As Described (SNAD)
              payment disputes and Post-Order cases from eBay. Grid layout and column visibility are
              saved per user.
            </p>
          </div>
          <div className="flex-1">
            <DataGridPage gridKey="cases" title="Cases &amp; Disputes" />
          </div>
        </div>
      </div>
    </div>
  );
}
