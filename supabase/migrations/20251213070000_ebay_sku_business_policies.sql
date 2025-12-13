-- Per-SKU eBay Business Policies mapping (SKU_catalog -> policy ids)
-- This allows Create/Edit SKU to store the selected SellerProfiles IDs
-- without altering the legacy-mirrored SKU_catalog schema.

CREATE TABLE IF NOT EXISTS public.ebay_sku_business_policies (
  id BIGSERIAL PRIMARY KEY,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  sku_catalog_id BIGINT NOT NULL,
  account_key TEXT NOT NULL DEFAULT 'default',
  marketplace_id TEXT NOT NULL DEFAULT 'EBAY_US',

  shipping_policy_id BIGINT NULL,
  payment_policy_id BIGINT NULL,
  return_policy_id BIGINT NULL
);

-- One row per SKU per scope
CREATE UNIQUE INDEX IF NOT EXISTS ux_ebay_sku_business_policies_scope
  ON public.ebay_sku_business_policies (sku_catalog_id, account_key, marketplace_id);

CREATE INDEX IF NOT EXISTS idx_ebay_sku_business_policies_sku
  ON public.ebay_sku_business_policies (sku_catalog_id);

CREATE INDEX IF NOT EXISTS idx_ebay_sku_business_policies_marketplace
  ON public.ebay_sku_business_policies (marketplace_id);

-- updated_at trigger
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'set_timestamp_ebay_sku_business_policies') THEN
    CREATE OR REPLACE FUNCTION set_timestamp_ebay_sku_business_policies()
    RETURNS TRIGGER AS $func$
    BEGIN
      NEW.updated_at = NOW();
      RETURN NEW;
    END;
    $func$ LANGUAGE plpgsql;
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'set_timestamp_ebay_sku_business_policies') THEN
    CREATE TRIGGER set_timestamp_ebay_sku_business_policies
    BEFORE UPDATE ON public.ebay_sku_business_policies
    FOR EACH ROW
    EXECUTE FUNCTION set_timestamp_ebay_sku_business_policies();
  END IF;
END;
$$;
