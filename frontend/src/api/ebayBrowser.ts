export interface BrowseSearchRequest {
  keywords: string;
  max_total_price?: number;
  min_total_price?: number;
  category_id?: string | null;
  category_hint?: string | null;
  exclude_keywords?: string[];
  condition_ids?: string[];
  aspect_filters?: Record<string, string[]>;
  limit?: number;
  offset?: number;
  sort?: string;
  include_refinements?: boolean;
  use_taxonomy_suggestions?: boolean;
}

export interface BrowseListing {
  item_id: string;
  title: string;
  price: number;
  shipping: number;
  total_price: number;
  condition?: string | null;
  description?: string | null;
  ebay_url?: string | null;
}

export interface CategoryRefinement {
  id: string;
  name: string;
  match_count: number;
}

export interface AspectValueRefinement {
  value: string;
  match_count: number;
}

export interface AspectRefinement {
  name: string;
  values: AspectValueRefinement[];
}

export interface ConditionRefinement {
  id: string;
  name: string;
  match_count: number;
}

export interface TaxonomySuggestion {
  id: string;
  name: string;
  path: string;
}

export interface BrowseSearchResponse {
  items: BrowseListing[];
  categories: CategoryRefinement[];
  aspects: AspectRefinement[];
  conditions: ConditionRefinement[];
  taxonomy_suggestions: TaxonomySuggestion[];
  total?: number | null;
}

import api from '@/lib/apiClient';

export async function searchBrowse(payload: BrowseSearchRequest): Promise<BrowseSearchResponse> {
  // Use relative path so baseURL (/api) is preserved
  const resp = await api.post<BrowseSearchResponse>('ebay/browse/search', payload);
  return resp.data;
}
