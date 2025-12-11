import { useState } from 'react';
import {
  searchBrowse,
  BrowseListing,
  BrowseSearchRequest,
  CategoryRefinement,
  ConditionRefinement,
  AspectRefinement,
  TaxonomySuggestion,
} from '@/api/ebayBrowser';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { EbayListingCard } from './EbayListingCard';
import { EbaySidebar } from './EbaySidebar';

const TARGET_ASPECTS = ['Screen Size', 'Processor', 'Operating System', 'Brand'] as const;

type ConditionFilter = 'any' | 'working' | 'non_working';

type AspectSelection = Record<string, string[]>;

export const EbaySearchTab: React.FC = () => {
  const [keywords, setKeywords] = useState('');
  const [onlyLaptops, setOnlyLaptops] = useState(true);
  const [maxPrice, setMaxPrice] = useState<number | undefined>(200);
  const [conditionFilter, setConditionFilter] = useState<ConditionFilter>('any');
  const [exclude, setExclude] = useState('for parts, not working, не работает');
  const [rows, setRows] = useState<BrowseListing[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Facets & meta
  const [categories, setCategories] = useState<CategoryRefinement[]>([]);
  const [conditions, setConditions] = useState<ConditionRefinement[]>([]);
  const [aspects, setAspects] = useState<AspectRefinement[]>([]);
  const [taxonomySuggestions, setTaxonomySuggestions] = useState<TaxonomySuggestion[]>([]);
  const [selectedCategoryId, setSelectedCategoryId] = useState<string | null>('177'); // 177 = PC Laptops & Netbooks
  const [selectedConditionIds, setSelectedConditionIds] = useState<string[]>([]);
  const [selectedAspectValues, setSelectedAspectValues] = useState<AspectSelection>({});
  const [total, setTotal] = useState<number | undefined>(undefined);

  // Pagination & Sorting
  const [offset, setOffset] = useState(0);
  const [sort, setSort] = useState('newlyListed');
  const [hasMore, setHasMore] = useState(true);

  const handleSearch = async (isLoadMore = false) => {
    if (!keywords.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const currentOffset = isLoadMore ? offset : 0;

      // Prepare aspect_filters payload
      const aspect_filters: AspectSelection = Object.fromEntries(
        Object.entries(selectedAspectValues)
          .map(([name, values]) => [name, values.filter(Boolean)])
          .filter(([, values]) => values.length > 0),
      );

      const body: BrowseSearchRequest = {
        keywords: keywords.trim(),
        max_total_price: maxPrice,
        category_id: selectedCategoryId,
        category_hint: onlyLaptops ? 'laptop' : 'all',
        exclude_keywords: exclude
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean),
        condition_ids:
          selectedConditionIds.length > 0 ? selectedConditionIds : undefined,
        aspect_filters: Object.keys(aspect_filters).length
          ? aspect_filters
          : undefined,
        limit: 50,
        offset: currentOffset,
        sort: sort,
        include_refinements: true,
        use_taxonomy_suggestions: true,
      };

      const data = await searchBrowse(body);

      // Server handles conditionIds; fall back to local heuristics only
      // when no explicit conditionIds are active.
      let filtered: BrowseListing[] = data.items;
      if (selectedConditionIds.length === 0 && conditionFilter !== 'any') {
        filtered = data.items.filter((item) =>
          filterByCondition(item, conditionFilter),
        );
      }

      if (isLoadMore) {
        setRows((prev) => [...prev, ...filtered]);
        setOffset((prev) => prev + 50);
      } else {
        setRows(filtered);
        setOffset(50);
      }

      setCategories(data.categories ?? []);
      setConditions(data.conditions ?? []);
      setAspects(data.aspects ?? []);
      setTaxonomySuggestions(data.taxonomy_suggestions ?? []);
      setTotal(typeof data.total === 'number' ? data.total : undefined);

      setHasMore(data.items.length === 50); // If we got full page, assume there's more
    } catch (e: any) {
      setError(e.message ?? String(e));
    } finally {
      setLoading(false);
    }
  };

  // Reset offset when filters change
  const onFilterChange = () => {
    setOffset(0);
    setHasMore(true);
  };

  const handleCategoryClick = (cat: CategoryRefinement | null) => {
    setSelectedCategoryId(cat ? cat.id : null);
    onFilterChange();
    void handleSearch(false);
  };

  const handleConditionFilterChange = (next: ConditionFilter) => {
    setConditionFilter(next);
    const ids = recomputeConditionSelection(next, conditions);
    setSelectedConditionIds(ids);
    onFilterChange();
    void handleSearch(false);
  };

  const toggleAspectValue = (aspectName: string, value: string) => {
    setSelectedAspectValues((prev) => {
      const current = prev[aspectName] ?? [];
      const exists = current.includes(value);
      const nextValues = exists
        ? current.filter((v) => v !== value)
        : [...current, value];
      const next: AspectSelection = { ...prev };
      if (nextValues.length === 0) {
        delete next[aspectName];
      } else {
        next[aspectName] = nextValues;
      }
      return next;
    });
    onFilterChange();
    void handleSearch(false);
  };

  const relevantAspects = pickRelevantAspects(aspects);

  const handleClearFilters = () => {
    setOnlyLaptops(true);
    setMaxPrice(200);
    setConditionFilter('any');
    setExclude('for parts, not working, не работает');
    setSelectedCategoryId(null);
    setSelectedConditionIds([]);
    setSelectedAspectValues({});
    onFilterChange();
  };

  return (
    <div className="flex flex-col gap-4 h-full">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
        <div className="space-y-1">
          <label className="text-xs font-medium text-gray-700">Ключевые слова</label>
          <Input
            value={keywords}
            onChange={(e) => setKeywords(e.target.value)}
            placeholder="Lenovo L500, MacBook Pro 2020..."
          />
        </div>

        <div className="space-y-1">
          <label className="text-xs font-medium text-gray-700">Максимальная цена (товар + доставка)</label>
          <Input
            type="number"
            min={0}
            step={1}
            value={maxPrice ?? ''}
            onChange={(e) => setMaxPrice(e.target.value ? Number(e.target.value) : undefined)}
          />
        </div>

        <div className="space-y-1">
          <label className="text-xs font-medium text-gray-700">Тип товара</label>
          <div className="flex items-center gap-3 mt-1">
            <label className="flex items-center gap-1 text-xs">
              <input
                type="checkbox"
                checked={onlyLaptops}
                onChange={(e) => setOnlyLaptops(e.target.checked)}
              />
              Только ноутбуки целиком
            </label>
          </div>
        </div>

        <div className="space-y-1">
          <label className="text-xs font-medium text-gray-700">Состояние</label>
          <div className="flex flex-col gap-1 mt-1 text-xs">
            <label className="flex items-center gap-1">
              <input
                type="radio"
                checked={conditionFilter === 'any'}
                onChange={() => handleConditionFilterChange('any')}
              />
              Любое
            </label>
            <label className="flex items-center gap-1">
              <input
                type="radio"
                checked={conditionFilter === 'working'}
                onChange={() => handleConditionFilterChange('working')}
              />
              Только рабочие
            </label>
            <label className="flex items-center gap-1">
              <input
                type="radio"
                checked={conditionFilter === 'non_working'}
                onChange={() => handleConditionFilterChange('non_working')}
              />
              Только нерабочие
            </label>
          </div>
        </div>

        <div className="space-y-1 md:col-span-2">
          <label className="text-xs font-medium text-gray-700">Исключить слова (через запятую)</label>
          <Textarea
            rows={2}
            value={exclude}
            onChange={(e) => setExclude(e.target.value)}
          />
        </div>

        <div className="space-y-1">
          <label className="text-xs font-medium text-gray-700">Сортировка</label>
          <Select value={sort} onValueChange={(val) => { setSort(val); onFilterChange(); }}>
            <SelectTrigger className="h-9 text-xs">
              <SelectValue placeholder="Sort by" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="newlyListed">Newly Listed</SelectItem>
              <SelectItem value="price">Price (Low to High)</SelectItem>
              <SelectItem value="-price">Price (High to Low)</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <Button
          size="sm"
          onClick={() => handleSearch(false)}
          disabled={loading || !keywords.trim()}
        >
          {loading ? 'Ищу…' : 'Искать'}
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={handleClearFilters}
          disabled={loading}
        >
          Сбросить фильтры
        </Button>
        {error && <span className="text-xs text-red-600">{error}</span>}
        {typeof total === 'number' && (
          <span className="text-xs text-gray-600">Найдено на eBay: {total}</span>
        )}
      </div>

      {taxonomySuggestions.length > 0 && (
        <div className="text-[11px] text-gray-700 flex flex-wrap items-center gap-2">
          <span className="font-semibold mr-1">Рекомендуемые категории:</span>
          {taxonomySuggestions.map((s) => (
            <button
              key={s.id}
              type="button"
              className="px-2 py-1 rounded border text-xs whitespace-nowrap bg-white hover:bg-gray-50"
              onClick={() =>
                handleCategoryClick({ id: s.id, name: s.name, match_count: 0 })
              }
              title={s.path}
            >
              {s.path}
            </button>
          ))}
        </div>
      )}

      {categories.length > 0 && (
        <div className="text-[11px] text-gray-700 flex flex-wrap items-center gap-2">
          <span className="font-semibold mr-1">Категории:</span>
          <button
            type="button"
            className={`px-2 py-1 rounded border text-xs ${selectedCategoryId === null
              ? 'bg-blue-600 text-white border-blue-600'
              : 'bg-white'
              }`}
            onClick={() => handleCategoryClick(null)}
          >
            Все
          </button>
          {categories.map((c) => (
            <button
              key={c.id}
              type="button"
              className={`px-2 py-1 rounded border text-xs whitespace-nowrap ${selectedCategoryId === c.id
                ? 'bg-blue-600 text-white border-blue-600'
                : 'bg-white hover:bg-gray-50'
                }`}
              onClick={() => handleCategoryClick(c)}
            >
              {c.name} ({c.match_count})
            </button>
          ))}
        </div>
      )}

      {relevantAspects.length > 0 && (
        <div className="text-[11px] text-gray-700 flex flex-col gap-2">
          {relevantAspects.map((aspect) => (
            <div key={aspect.name} className="flex flex-col gap-1">
              <span className="font-semibold">{aspect.name}</span>
              <div className="flex flex-wrap gap-2">
                {aspect.values.slice(0, 12).map((v) => (
                  <label
                    key={v.value}
                    className="flex items-center gap-1 cursor-pointer"
                  >
                    <input
                      type="checkbox"
                      checked={
                        selectedAspectValues[aspect.name]?.includes(v.value) ??
                        false
                      }
                      onChange={() => toggleAspectValue(aspect.name, v.value)}
                    />
                    <span>
                      {v.value} ({v.match_count})
                    </span>
                  </label>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Results Section with Sidebar */}
      <div className="flex-1 min-h-0 flex gap-3 overflow-hidden">
        {/* Sidebar */}
        <EbaySidebar
          categories={categories}
          selectedCategoryId={selectedCategoryId}
          onCategorySelect={(catId) => {
            setSelectedCategoryId(catId);
            void handleSearch(false);
          }}
        />

        {/* Results Grid */}
        <div className="flex-1 overflow-auto bg-gray-50 p-3">
          {rows.length === 0 ? (
            <div className="p-4 text-gray-500 text-center">
              Нет результатов. Задайте параметры и нажмите "Искать".
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-3">
              {rows.map((row) => (
                <EbayListingCard key={row.item_id} listing={row} />
              ))}
            </div>
          )}
        </div>
      </div>

      {rows.length > 0 && hasMore && (
        <div className="flex justify-center pt-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => handleSearch(true)}
            disabled={loading}
          >
            {loading ? 'Загрузка...' : 'Загрузить еще'}
          </Button>
        </div>
      )}
    </div>
  );
};

function recomputeConditionSelection(
  filter: ConditionFilter,
  conditions: ConditionRefinement[],
): string[] {
  if (filter === 'any') return [];

  const nonWorking = conditions.find((c) => {
    const name = c.name.toLowerCase();
    return name.includes('for parts') || name.includes('not working');
  });

  if (!nonWorking) return [];

  if (filter === 'non_working') return [nonWorking.id];

  // "Working" = any condition except the explicit non-working one.
  return conditions.filter((c) => c.id !== nonWorking.id).map((c) => c.id);
}

function pickRelevantAspects(all: AspectRefinement[]): AspectRefinement[] {
  if (!all.length) return [];
  const targetSet = new Set<string>(TARGET_ASPECTS as readonly string[]);
  return all.filter((a) => targetSet.has(a.name));
}

function filterByCondition(item: BrowseListing, filter: ConditionFilter): boolean {
  if (filter === 'any') return true;
  const text = `${item.title ?? ''} ${item.description ?? ''}`.toLowerCase();
  const NON_WORKING = [
    'not working',
    'does not power on',
    'for parts',
    'no power',
    'broken',
    'defective',
    'не включается',
    'не работает',
    'на запчасти',
  ];
  const WORKING = [
    'fully working',
    'tested',
    'in good working condition',
    'полностью рабочий',
    'проверен',
    'исправен',
  ];

  const hasNon = NON_WORKING.some((w) => text.includes(w.toLowerCase()));
  const hasWork = WORKING.some((w) => text.includes(w.toLowerCase()));

  if (filter === 'non_working') return hasNon;
  if (filter === 'working') {
    if (hasNon) return false;
    return hasWork;
  }
  return true;
}
