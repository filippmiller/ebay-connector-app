import { useState } from 'react';
import {
  searchBrowse,
  BrowseListing,
  BrowseSearchRequest,
  CategoryRefinement,
} from '@/api/ebayBrowser';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { EbayListingCard } from './EbayListingCard';
import { EbaySidebar } from './EbaySidebar';
import { EbayDetailsPanel } from './EbayDetailsPanel';
import { EbayItemModal } from './EbayItemModal';

export const EbaySearchTab: React.FC = () => {
  const [keywords, setKeywords] = useState('');
  const [maxPrice, setMaxPrice] = useState<number | undefined>(200);
  const [rows, setRows] = useState<BrowseListing[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedItem, setSelectedItem] = useState<BrowseListing | null>(null);
  const [modalItem, setModalItem] = useState<BrowseListing | null>(null);
  const [modalOpen, setModalOpen] = useState(false);

  const [categories, setCategories] = useState<CategoryRefinement[]>([]);
  const [selectedCategoryId, setSelectedCategoryId] = useState<string | null>('177');

  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(true);

  const handleSearch = async (isLoadMore = false) => {
    if (!keywords.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const currentOffset = isLoadMore ? offset : 0;

      const body: BrowseSearchRequest = {
        keywords: keywords.trim(),
        max_total_price: maxPrice,
        category_id: selectedCategoryId,
        // Removed: exclude_keywords - was filtering out 99.99% of results
        // Removed: category_hint - redundant with category_id: '177'
        limit: 50,
        offset: currentOffset,
        sort: 'newlyListed',
        include_refinements: true,
        use_taxonomy_suggestions: false,
      };

      const data = await searchBrowse(body);

      if (isLoadMore) {
        setRows((prev) => [...prev, ...data.items]);
        setOffset((prev) => prev + 50);
      } else {
        setRows(data.items);
        setOffset(50);
        setSelectedItem(null);
      }

      setCategories(data.categories ?? []);
      setHasMore(data.items.length === 50);
    } catch (e: any) {
      setError(e.message ?? String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="h-full flex flex-col">
      {/* Compact Search Bar - NO top padding, right against navbar */}
      <div className="px-4 py-1 bg-white border-b flex items-center gap-3 flex-shrink-0">
        <Input
          placeholder="Search laptops... (e.g. Lenovo L500, MacBook Pro)"
          value={keywords}
          onChange={(e) => setKeywords(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSearch(false)}
          className="flex-1 max-w-lg h-8"
        />
        <Input
          type="number"
          placeholder="Max price"
          value={maxPrice ?? ''}
          onChange={(e) => setMaxPrice(e.target.value ? Number(e.target.value) : undefined)}
          className="w-28 h-8"
        />
        <Button
          onClick={() => handleSearch(false)}
          disabled={loading || !keywords.trim()}
          size="sm"
        >
          {loading ? 'Searching...' : 'Search'}
        </Button>
        {rows.length > 0 && (
          <span className="text-xs text-gray-600">
            Showing {rows.length} {hasMore && `(load more available)`}
          </span>
        )}
        {error && <span className="text-xs text-red-600">{error}</span>}
      </div>

      {/* Main Content: Sidebar + Results */}
      <div className="flex-1 min-h-0 flex overflow-hidden">
        {/* Category Sidebar */}
        <EbaySidebar
          categories={categories}
          selectedCategoryId={selectedCategoryId}
          onCategorySelect={(catId) => {
            setSelectedCategoryId(catId);
            void handleSearch(false);
          }}
        />

        {/* Results Area */}
        <div className="flex-1 flex flex-col min-w-0">
          {/* Results Grid - Takes most space */}
          <div className={`overflow-auto bg-gray-50 p-3 ${selectedItem ? 'flex-1' : 'flex-1'}`}>
            {rows.length === 0 ? (
              <div className="p-8 text-gray-500 text-center">
                {loading ? 'Searching...' : 'Enter search terms and click Search'}
              </div>
            ) : (
              <>
                <div className="grid grid-cols-1 gap-3">
                  {rows.map((row) => (
                    <div
                      key={row.item_id}
                      onClick={() => setSelectedItem(row)}
                      className="cursor-pointer"
                    >
                      <EbayListingCard listing={row} />
                    </div>
                  ))}
                </div>

                {hasMore && rows.length > 0 && (
                  <div className="flex justify-center pt-4">
                    <Button
                      variant="outline"
                      onClick={() => handleSearch(true)}
                      disabled={loading}
                    >
                      {loading ? 'Loading...' : 'Load More'}
                    </Button>
                  </div>
                )}
              </>
            )}
          </div>

          {/* Details Panel - Bottom */}
          {selectedItem && (
            <EbayDetailsPanel
              listing={selectedItem}
              onClose={() => setSelectedItem(null)}
              onItemIdClick={() => {
                setModalItem(selectedItem);
                setModalOpen(true);
              }}
            />
          )}
        </div>
      </div>

      {/* Full Item Modal */}
      <EbayItemModal
        listing={modalItem}
        open={modalOpen}
        onClose={() => {
          setModalOpen(false);
          setModalItem(null);
        }}
      />
    </div>
  );
};
