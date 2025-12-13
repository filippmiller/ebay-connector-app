-- Hard mapping: legacy inventory / parts_detail / SKU -> eBay ItemID
-- This prevents losing ItemID even if parts_detail update fails.

create table if not exists public.ebay_bin_listings_map (
  id bigserial primary key,
  created_at timestamptz not null default now(),
  run_id bigint null references public.ebay_bin_test_runs(id) on delete set null,
  legacy_inventory_id bigint not null,
  parts_detail_id bigint null,
  sku text null,
  item_id text not null
);

create index if not exists idx_ebay_bin_listings_map_created_at on public.ebay_bin_listings_map (created_at desc);
create index if not exists idx_ebay_bin_listings_map_item_id on public.ebay_bin_listings_map (item_id);
create index if not exists idx_ebay_bin_listings_map_legacy_inventory_id on public.ebay_bin_listings_map (legacy_inventory_id);
create index if not exists idx_ebay_bin_listings_map_parts_detail_id on public.ebay_bin_listings_map (parts_detail_id);
create index if not exists idx_ebay_bin_listings_map_sku on public.ebay_bin_listings_map (sku);


