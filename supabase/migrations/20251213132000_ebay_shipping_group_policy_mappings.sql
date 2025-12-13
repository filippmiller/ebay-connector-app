-- Legacy ShippingGroup -> eBay Business Policies mapping
-- This bridges legacy semantics (ShippingGroup / ShippingType / DomesticOnlyFlag)
-- to Trading API SellerProfiles IDs (shipping/payment/return) to enable
-- deterministic policy selection per SKU.

CREATE TABLE IF NOT EXISTS public.ebay_shipping_group_policy_mappings (
  id BIGSERIAL PRIMARY KEY,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  account_key TEXT NOT NULL DEFAULT 'default',
  marketplace_id TEXT NOT NULL DEFAULT 'EBAY_US',

  -- Legacy inputs
  shipping_group_id INTEGER NOT NULL,
  shipping_type TEXT NOT NULL, -- 'Flat' | 'Calculated'
  -- NULL = any, TRUE = domestic-only, FALSE = international allowed
  domestic_only_flag BOOLEAN NULL,

  -- Target policy IDs (Trading SellerProfiles IDs)
  shipping_policy_id BIGINT NULL,
  payment_policy_id BIGINT NULL,
  return_policy_id BIGINT NULL,

  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  notes TEXT NULL
);

-- Ensure one active mapping per exact key; allow multiple rows (e.g. history)
-- by keeping the unique key independent of is_active.
CREATE UNIQUE INDEX IF NOT EXISTS ux_ebay_shipping_group_policy_mappings_key
  ON public.ebay_shipping_group_policy_mappings (
    account_key,
    marketplace_id,
    shipping_group_id,
    shipping_type,
    domestic_only_flag
  );

CREATE INDEX IF NOT EXISTS idx_ebay_shipping_group_policy_mappings_scope
  ON public.ebay_shipping_group_policy_mappings (account_key, marketplace_id);

CREATE INDEX IF NOT EXISTS idx_ebay_shipping_group_policy_mappings_group
  ON public.ebay_shipping_group_policy_mappings (shipping_group_id);

-- updated_at trigger
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'set_timestamp_ebay_shipping_group_policy_mappings') THEN
    CREATE OR REPLACE FUNCTION set_timestamp_ebay_shipping_group_policy_mappings()
    RETURNS TRIGGER AS $func$
    BEGIN
      NEW.updated_at = NOW();
      RETURN NEW;
    END;
    $func$ LANGUAGE plpgsql;
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'set_timestamp_ebay_shipping_group_policy_mappings') THEN
    CREATE TRIGGER set_timestamp_ebay_shipping_group_policy_mappings
    BEFORE UPDATE ON public.ebay_shipping_group_policy_mappings
    FOR EACH ROW
    EXECUTE FUNCTION set_timestamp_ebay_shipping_group_policy_mappings();
  END IF;
END;
$$;
