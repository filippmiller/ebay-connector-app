import { useState, useMemo } from 'react';
import FixedHeader from '@/components/FixedHeader';
import { DataGridPage } from '@/components/DataGridPage';

export default function FinancialsPage() {
  // Filters for the Finances fees grid (backed by ebay_finances_fees via /api/grids/finances_fees).
  const [fromDate, setFromDate] = useState('');
  const [toDate, setToDate] = useState('');
  const [feeType, setFeeType] = useState('');

  const financesFeesExtraParams = useMemo(() => {
    const params: Record<string, string> = {};
    if (fromDate) params.from = fromDate;
    if (toDate) params.to = toDate;
    if (feeType) params.fee_type = feeType;
    return params;
  }, [fromDate, toDate, feeType]);

  return (
    <div className="h-screen flex flex-col bg-gray-50">
      <FixedHeader />
      {/* Main content area under fixed header: full width, grid fills all available space */}
      <div className="pt-16 flex-1 px-4 py-6 overflow-hidden">
        <div className="w-full h-full flex flex-col min-h-0">
          <h1 className="text-3xl font-bold mb-4">Finances</h1>

          <div className="flex-1 min-h-0 flex flex-col gap-3">
            <div className="flex flex-wrap items-end gap-4 mb-4">
              <div>
                <label htmlFor="fin-from" className="block text-xs font-medium text-gray-600 mb-1">From</label>
                <input
                  id="fin-from"
                  type="date"
                  className="border rounded px-2 py-1 text-sm"
                  value={fromDate}
                  onChange={(e) => setFromDate(e.target.value)}
                />
              </div>
              <div>
                <label htmlFor="fin-to" className="block text-xs font-medium text-gray-600 mb-1">To</label>
                <input
                  id="fin-to"
                  type="date"
                  className="border rounded px-2 py-1 text-sm"
                  value={toDate}
                  onChange={(e) => setToDate(e.target.value)}
                />
              </div>
              <div>
                <label htmlFor="fin-fee-type" className="block text-xs font-medium text-gray-600 mb-1">Fee type</label>
                <select
                  id="fin-fee-type"
                  className="border rounded px-2 py-1 text-sm w-56"
                  value={feeType}
                  onChange={(e) => setFeeType(e.target.value)}
                >
                  <option value="">All types</option>
                  <option value="FINAL_VALUE_FEE">FINAL_VALUE_FEE*</option>
                  <option value="PROMOTED_LISTING_FEE">PROMOTED_LISTING_FEE*</option>
                  <option value="SHIPPING_LABEL_FEE">SHIPPING_LABEL_FEE*</option>
                  <option value="CHARITY">CHARITY / DONATION</option>
                </select>
                <p className="mt-1 text-[11px] text-gray-500">
                  Use the grid search box to search across IDs and text; use this dropdown to focus on specific fee types.
                </p>
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
