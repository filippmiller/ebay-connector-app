import { CategoryRefinement } from '@/api/ebayBrowser';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { useState } from 'react';

interface EbaySidebarProps {
    categories: CategoryRefinement[];
    selectedCategoryId: string | null;
    onCategorySelect: (categoryId: string | null) => void;
}

export const EbaySidebar: React.FC<EbaySidebarProps> = ({
    categories,
    selectedCategoryId,
    onCategorySelect,
}) => {
    const [categoryExpanded, setCategoryExpanded] = useState(true);

    if (categories.length === 0) {
        return null;
    }

    return (
        <div className="w-[220px] flex-shrink-0 border-r bg-gray-50 p-3 overflow-y-auto">
            <div className="mb-4">
                <button
                    onClick={() => setCategoryExpanded(!categoryExpanded)}
                    className="flex items-center gap-1 font-semibold text-sm text-gray-900 w-full hover:text-blue-600"
                >
                    {categoryExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                    Category
                </button>

                {categoryExpanded && (
                    <div className="mt-2 space-y-1">
                        {/* "All" option */}
                        <button
                            onClick={() => onCategorySelect(null)}
                            className={`
                w-full text-left text-xs px-2 py-1 rounded
                ${selectedCategoryId === null ? 'bg-blue-100 text-blue-700 font-semibold' : 'hover:bg-gray-200 text-gray-700'}
              `}
                        >
                            All Categories
                        </button>

                        {/* Category list */}
                        {categories.map((cat) => (
                            <button
                                key={cat.id}
                                onClick={() => onCategorySelect(cat.id)}
                                className={`
                  w-full text-left text-xs px-2 py-1 rounded
                  ${selectedCategoryId === cat.id ? 'bg-blue-100 text-blue-700 font-semibold' : 'hover:bg-gray-200 text-gray-700'}
                `}
                            >
                                <div className="truncate" title={cat.name}>
                                    {cat.name}
                                </div>
                                <div className="text-[10px] text-gray-500">({cat.match_count})</div>
                            </button>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
};
