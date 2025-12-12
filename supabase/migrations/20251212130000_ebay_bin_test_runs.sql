-- eBay BIN Trading API debug runs (append-only debug logs)
-- This table is used by Admin → eBay BIN Listing Debug tooling.

create table if not exists public.ebay_bin_test_runs (
  id bigserial primary key,
  created_at timestamptz not null default now(),
  user_id bigint null,
  legacy_inventory_id bigint not null,
  parts_detail_id bigint null,
  sku text null,
  mode text not null check (mode in ('VERIFY','LIST')),

  request_url text not null,
  request_headers_masked jsonb null,
  request_body_xml text not null,

  response_http_status int not null,
  response_headers jsonb null,
  response_body_xml text not null,

  parsed_ack text null,
  parsed_errors jsonb null,
  parsed_warnings jsonb null,
  item_id text null,

  trace_id text null,
  debug_flags jsonb null
);

create index if not exists idx_ebay_bin_test_runs_created_at on public.ebay_bin_test_runs (created_at desc);
create index if not exists idx_ebay_bin_test_runs_legacy_inventory_id on public.ebay_bin_test_runs (legacy_inventory_id);
create index if not exists idx_ebay_bin_test_runs_parts_detail_id on public.ebay_bin_test_runs (parts_detail_id);
create index if not exists idx_ebay_bin_test_runs_sku on public.ebay_bin_test_runs (sku);


