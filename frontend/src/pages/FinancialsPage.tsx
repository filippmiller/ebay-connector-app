import { useState, useMemo } from 'react';
import FixedHeader from '@/components/FixedHeader';
import { DataGridPage } from '@/components/DataGridPage';

export default function FinancialsPage() {
  // Filters for the Finances fees grid (backed by Supabase table ebay_finances_fees)
  const [fromDate, setFromDate] = useState('');
  const [toDate, setToDate] = useState('');
  const [searchQuery, setSearchQuery] = useState('');

  const financesFeesExtraParams = useMemo(() => {
    const params: Record<string, string> = {};
    if (fromDate) params.from = fromDate;
    if (toDate) params.to = toDate;
    // search is currently handled client-side via the grid toolbar; keep this here for future backend wiring.
    if (searchQuery) params.search = searchQuery;
    return params;
  }, [fromDate, toDate, searchQuery]);

  return (
    <div className="h-screen flex flex-col bg-gray-50">
      <FixedHeader />
      {/* Main content area under fixed header: full width, grid fills all available space */}
      <div className="pt-16 flex-1 px-4 py-6 overflow-hidden">
        <div className="w-full h-full flex flex-col">
          <h1 className="text-3xl font-bold mb-4">Finances</h1>

          <div className="flex-1 min-h-0 flex flex-col gap-3">
            <div className="flex flex-wrap items-end gap-4 mb-4">
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
              <div className="flex-1 min-w-[200px]">
                <label className="block text-xs font-medium text-gray-600 mb-1">Search</label>
                <input
                  type="text"
                  className="border rounded px-2 py-1 text-sm w-full"
                  placeholder="Search across fee rows..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                />
              </div>
            </div>

            <div className="flex-1 min-h-0">
              <DataGridPage
                gridKey="finances_fees"
                title="Finances fees"
                extraParams={financesFeesExtraParams}
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
