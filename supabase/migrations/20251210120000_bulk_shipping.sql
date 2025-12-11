-- Bulk Shipping: batches, enriched labels, and defensive creation of shipping tables
-- This migration is idempotent and will not override existing data.

-- 1) Enums (created only if missing)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'shipping_job_status') THEN
        CREATE TYPE shipping_job_status AS ENUM ('NEW', 'PICKING', 'PACKED', 'SHIPPED', 'CANCELLED', 'ERROR');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'shipping_label_provider') THEN
        CREATE TYPE shipping_label_provider AS ENUM ('EBAY_LOGISTICS', 'EXTERNAL', 'MANUAL');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'shipping_status_source') THEN
        CREATE TYPE shipping_status_source AS ENUM ('WAREHOUSE_SCAN', 'API', 'MANUAL');
    END IF;
END
$$;

-- 2) Core tables from the Phase 1 shipping module (created only if absent)
CREATE TABLE IF NOT EXISTS public.shipping_jobs (
    id                VARCHAR(36) PRIMARY KEY,
    -- Use TEXT to match existing ebay_accounts.id type in remote DB
    ebay_account_id   TEXT REFERENCES public.ebay_accounts(id) ON DELETE SET NULL,
    ebay_order_id     TEXT,
    ebay_order_line_item_ids JSONB,
    buyer_user_id     TEXT,
    buyer_name        TEXT,
    ship_to_address   JSONB,
    warehouse_id      TEXT,
    storage_ids       JSONB,
    status            shipping_job_status NOT NULL DEFAULT 'NEW',
    label_id          VARCHAR(36),
    paid_time         TIMESTAMPTZ,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- users.id is varchar in remote DB, keep FK compatible
    created_by        TEXT REFERENCES public.users(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_shipping_jobs_status_warehouse ON public.shipping_jobs(status, warehouse_id);
CREATE INDEX IF NOT EXISTS idx_shipping_jobs_ebay_order_id ON public.shipping_jobs(ebay_order_id);

CREATE TABLE IF NOT EXISTS public.shipping_packages (
    id                 VARCHAR(36) PRIMARY KEY,
    shipping_job_id    VARCHAR(36) REFERENCES public.shipping_jobs(id) ON DELETE CASCADE NOT NULL,
    combined_for_buyer BOOLEAN NOT NULL DEFAULT FALSE,
    weight_oz          NUMERIC(10,2),
    length_in          NUMERIC(10,2),
    width_in           NUMERIC(10,2),
    height_in          NUMERIC(10,2),
    package_type       TEXT,
    carrier_preference TEXT,
    notes              TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_shipping_packages_job_id ON public.shipping_packages(shipping_job_id);

CREATE TABLE IF NOT EXISTS public.shipping_status_log (
    id            VARCHAR(36) PRIMARY KEY,
    shipping_job_id VARCHAR(36) REFERENCES public.shipping_jobs(id) ON DELETE CASCADE NOT NULL,
    status_before shipping_job_status,
    status_after  shipping_job_status NOT NULL,
    source        shipping_status_source NOT NULL DEFAULT 'MANUAL',
    reason        TEXT,
    user_id       VARCHAR(36) REFERENCES public.users(id) ON DELETE SET NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_shipping_status_log_job_created ON public.shipping_status_log(shipping_job_id, created_at);

-- 2b) Inventory enrichment to support FIFO by item_id
ALTER TABLE public.inventory
    ADD COLUMN IF NOT EXISTS item_id VARCHAR(120);
CREATE INDEX IF NOT EXISTS idx_inventory_item_id_created ON public.inventory(item_id, rec_created);

-- 3) New: shipping_batches
CREATE TABLE IF NOT EXISTS public.shipping_batches (
    id          VARCHAR(36) PRIMARY KEY,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- users.id is varchar in remote DB
    created_by  TEXT REFERENCES public.users(id) ON DELETE SET NULL,
    labels_count INTEGER NOT NULL DEFAULT 0,
    total_cost  NUMERIC(14,2),
    currency    CHAR(3) NOT NULL DEFAULT 'USD',
    status      VARCHAR(20) NOT NULL DEFAULT 'DRAFT', -- DRAFT, PURCHASING, PURCHASED, FAILED
    notes       TEXT
);
CREATE INDEX IF NOT EXISTS idx_shipping_batches_status_created ON public.shipping_batches(status, created_at DESC);

-- 4) shipping_labels (create if missing, then extend with new columns)
CREATE TABLE IF NOT EXISTS public.shipping_labels (
    id                    VARCHAR(36) PRIMARY KEY,
    shipping_job_id       VARCHAR(36) REFERENCES public.shipping_jobs(id) ON DELETE CASCADE NOT NULL,
    provider              shipping_label_provider NOT NULL,
    provider_shipment_id  TEXT,
    tracking_number       TEXT,
    carrier               TEXT,
    service_name          TEXT,
    label_url             TEXT,
    label_file_type       TEXT,
    label_cost_amount     NUMERIC(12,2),
    label_cost_currency   CHAR(3) NOT NULL DEFAULT 'USD',
    purchased_at          TIMESTAMPTZ,
    voided                BOOLEAN NOT NULL DEFAULT FALSE,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 4a) Enrich shipping_labels with bulk-shipping specific columns
ALTER TABLE public.shipping_labels
    ADD COLUMN IF NOT EXISTS batch_id VARCHAR(36) REFERENCES public.shipping_batches(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS order_id VARCHAR(120),
    ADD COLUMN IF NOT EXISTS order_line_item_id VARCHAR(120),
    ADD COLUMN IF NOT EXISTS legacy_transaction_id VARCHAR(120),
    ADD COLUMN IF NOT EXISTS item_id VARCHAR(120),
    ADD COLUMN IF NOT EXISTS sku VARCHAR(120),
    ADD COLUMN IF NOT EXISTS inventory_id INTEGER REFERENCES public.inventory(id),
    ADD COLUMN IF NOT EXISTS storage_id VARCHAR(120),
    ADD COLUMN IF NOT EXISTS quantity INTEGER NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS weight_oz NUMERIC(10,2),
    ADD COLUMN IF NOT EXISTS length_in NUMERIC(10,2),
    ADD COLUMN IF NOT EXISTS width_in NUMERIC(10,2),
    ADD COLUMN IF NOT EXISTS height_in NUMERIC(10,2),
    ADD COLUMN IF NOT EXISTS carrier_code VARCHAR(50),
    ADD COLUMN IF NOT EXISTS service_code VARCHAR(120),
    ADD COLUMN IF NOT EXISTS label_status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    ADD COLUMN IF NOT EXISTS label_pdf_url TEXT,
    ADD COLUMN IF NOT EXISTS label_zpl_url TEXT,
    ADD COLUMN IF NOT EXISTS created_by TEXT REFERENCES public.users(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS updated_by TEXT REFERENCES public.users(id) ON DELETE SET NULL;

-- 4b) Helpful indexes
CREATE INDEX IF NOT EXISTS ix_shipping_labels_tracking_number ON public.shipping_labels(tracking_number);
CREATE INDEX IF NOT EXISTS idx_shipping_labels_provider_shipment ON public.shipping_labels(provider, provider_shipment_id);
CREATE INDEX IF NOT EXISTS idx_shipping_labels_order_line ON public.shipping_labels(order_id, order_line_item_id);
CREATE INDEX IF NOT EXISTS idx_shipping_labels_inventory ON public.shipping_labels(inventory_id);
CREATE INDEX IF NOT EXISTS idx_shipping_labels_batch ON public.shipping_labels(batch_id);

-- 5) Keep updated_at in sync
ALTER TABLE public.shipping_labels
    ALTER COLUMN updated_at SET DEFAULT NOW();

ALTER TABLE public.shipping_batches
    ALTER COLUMN updated_at SET DEFAULT NOW();


