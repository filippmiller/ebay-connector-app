-- Category → required item specifics (learned from VerifyAddFixedPriceItem failures)

CREATE TABLE IF NOT EXISTS public.ebay_category_required_specifics (
  id BIGSERIAL PRIMARY KEY,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  marketplace_id TEXT NOT NULL DEFAULT 'EBAY_US',
  category_id TEXT NOT NULL,
  specific_name TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_ebay_category_required_specifics
  ON public.ebay_category_required_specifics (marketplace_id, category_id, specific_name);

-- Keep updated_at in sync (reusing same trigger name style)
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'set_timestamp_ebay_category_required_specifics') THEN
    CREATE OR REPLACE FUNCTION set_timestamp_ebay_category_required_specifics()
    RETURNS TRIGGER AS $func$
    BEGIN
      NEW.updated_at = NOW();
      RETURN NEW;
    END;
    $func$ LANGUAGE plpgsql;
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'set_timestamp_ebay_category_required_specifics') THEN
    CREATE TRIGGER set_timestamp_ebay_category_required_specifics
    BEFORE UPDATE ON public.ebay_category_required_specifics
    FOR EACH ROW
    EXECUTE FUNCTION set_timestamp_ebay_category_required_specifics();
  END IF;
END;
$$;

-- Seed: known required specifics for category 175676 (palmrest/keyboard/top case category)
INSERT INTO public.ebay_category_required_specifics (marketplace_id, category_id, specific_name)
VALUES
  ('EBAY_US','175676','Type'),
  ('EBAY_US','175676','Compatible Brand')
ON CONFLICT DO NOTHING;


