export interface BrowseSearchRequest {
  keywords: string;
  max_total_price?: number;
  category_hint?: string | null;
  exclude_keywords?: string[];
  limit?: number;
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

export async function searchBrowse(payload: BrowseSearchRequest): Promise<BrowseListing[]> {
  const resp = await fetch('/api/ebay/browse/search', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) {
    throw new Error(await resp.text());
  }
  return resp.json();
}
