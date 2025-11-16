import FixedHeader from '@/components/FixedHeader';
import { DataGridPage } from '@/components/DataGridPage';

export default function CasesPage() {
  return (
    <div className="min-h-screen bg-gray-50">
      <FixedHeader />
      <div className="pt-12 p-4">
        <div className="max-w-7xl mx-auto flex flex-col gap-4">
          <div>
            <h1 className="text-2xl font-bold">Cases &amp; Disputes</h1>
            <p className="text-gray-600 mt-2 text-sm">
              Unified view of Item Not Received (INR) and Significantly Not As Described (SNAD)
              payment disputes and Post-Order cases from eBay.
            </p>
          </div>
          <div className="border rounded bg-white p-3">
            <DataGridPage gridKey="cases" title="Cases &amp; Disputes" />
          </div>
        </div>
      </div>
    </div>
  );
}
