-- eBay Business Policies dictionary (extensible: multi-policy, multi-account, multi-marketplace)

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- 1) Table
CREATE TABLE IF NOT EXISTS public.ebay_business_policies (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  is_active BOOLEAN NOT NULL DEFAULT TRUE,

  account_key TEXT NOT NULL,
  marketplace_id TEXT NOT NULL DEFAULT 'EBAY_US',

  policy_type TEXT NOT NULL CHECK (policy_type IN ('SHIPPING','PAYMENT','RETURN')),
  policy_id BIGINT NOT NULL,
  policy_name TEXT NOT NULL,
  policy_description TEXT NULL,

  is_default BOOLEAN NOT NULL DEFAULT FALSE,
  sort_order INT NOT NULL DEFAULT 0,
  raw_source JSONB NULL
);

-- 2) Uniqueness
CREATE UNIQUE INDEX IF NOT EXISTS ux_ebay_business_policies_identity
  ON public.ebay_business_policies (account_key, marketplace_id, policy_type, policy_id);

-- Only one default per (account_key, marketplace_id, policy_type)
CREATE UNIQUE INDEX IF NOT EXISTS ux_ebay_business_policies_default
  ON public.ebay_business_policies (account_key, marketplace_id, policy_type)
  WHERE is_default = TRUE;

-- 3) updated_at trigger (same style as ui_tweak_settings)
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_proc WHERE proname = 'set_timestamp_ebay_business_policies'
  ) THEN
    CREATE OR REPLACE FUNCTION set_timestamp_ebay_business_policies()
    RETURNS TRIGGER AS $func$
    BEGIN
      NEW.updated_at = NOW();
      RETURN NEW;
    END;
    $func$ LANGUAGE plpgsql;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_trigger WHERE tgname = 'set_timestamp_ebay_business_policies'
  ) THEN
    CREATE TRIGGER set_timestamp_ebay_business_policies
    BEFORE UPDATE ON public.ebay_business_policies
    FOR EACH ROW
    EXECUTE FUNCTION set_timestamp_ebay_business_policies();
  END IF;
END;
$$;

-- 4) Seed defaults (account_key='default', marketplace_id='EBAY_US')
INSERT INTO public.ebay_business_policies
  (account_key, marketplace_id, policy_type, policy_id, policy_name, policy_description, is_default, sort_order)
VALUES
  ('default','EBAY_US','SHIPPING',206348665012,'Default Shipping (US)',NULL,TRUE,0),
  ('default','EBAY_US','PAYMENT',179217199012,'Default Payment (Managed Payments)',NULL,TRUE,0),
  ('default','EBAY_US','RETURN',164486481012,'Default Return (30 days)',NULL,TRUE,0)
ON CONFLICT DO NOTHING;

-- 5) Optional view: defaults
CREATE OR REPLACE VIEW public.ebay_business_policies_defaults AS
SELECT
  account_key,
  marketplace_id,
  MAX(CASE WHEN policy_type='SHIPPING' AND is_default THEN policy_id END) AS shipping_policy_id,
  MAX(CASE WHEN policy_type='PAYMENT'  AND is_default THEN policy_id END) AS payment_policy_id,
  MAX(CASE WHEN policy_type='RETURN'   AND is_default THEN policy_id END) AS return_policy_id
FROM public.ebay_business_policies
WHERE is_active = TRUE
GROUP BY account_key, marketplace_id;


