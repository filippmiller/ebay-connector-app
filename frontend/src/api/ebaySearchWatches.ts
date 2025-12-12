export interface EbaySearchWatchBase {
  name: string;
  keywords: string;
  max_total_price?: number;
  category_hint?: string | null;
  exclude_keywords?: string[];
  check_interval_sec?: number;
  enabled: boolean;
  notification_mode: 'task' | 'none';
}

export interface EbaySearchWatchResponse extends EbaySearchWatchBase {
  id: string;
  last_checked_at?: string | null;
}

export interface RunOnceListing {
  item_id: string;
  title: string;
  price: number;
  shipping: number;
  total_price: number;
  condition?: string | null;
  description?: string | null;
  ebay_url?: string | null;
}

export async function getWatches(): Promise<EbaySearchWatchResponse[]> {
  const resp = await fetch('/api/ebay/search-watches');
  if (!resp.ok) throw new Error(await resp.text());
  return resp.json();
}

export async function createWatch(payload: EbaySearchWatchBase): Promise<EbaySearchWatchResponse> {
  const resp = await fetch('/api/ebay/search-watches', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) throw new Error(await resp.text());
  return resp.json();
}

export async function updateWatch(
  id: string,
  payload: Partial<EbaySearchWatchBase>,
): Promise<EbaySearchWatchResponse> {
  const resp = await fetch(`/api/ebay/search-watches/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) throw new Error(await resp.text());
  return resp.json();
}

export async function deleteWatch(id: string): Promise<void> {
  const resp = await fetch(`/api/ebay/search-watches/${id}`, { method: 'DELETE' });
  if (!resp.ok && resp.status !== 404) throw new Error(await resp.text());
}

export async function runWatchOnce(id: string): Promise<RunOnceListing[]> {
  const resp = await fetch(`/api/ebay/search-watches/${id}/run-once`, {
    method: 'POST',
  });
  if (!resp.ok) throw new Error(await resp.text());
  return resp.json();
}
