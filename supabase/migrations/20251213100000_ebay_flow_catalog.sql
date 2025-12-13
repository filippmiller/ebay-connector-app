-- Create ebay_flow_catalog table: searchable catalog of eBay data flows (idempotent)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name = 'ebay_flow_catalog'
    ) THEN
        CREATE TABLE public.ebay_flow_catalog (
            id BIGSERIAL PRIMARY KEY,
            flow_key TEXT NOT NULL,
            title TEXT NOT NULL,
            summary TEXT NULL,
            category TEXT NULL,
            keywords TEXT[] NOT NULL DEFAULT '{}'::text[],
            graph JSONB NOT NULL DEFAULT '{"nodes": {}, "edges": []}'::jsonb,
            source JSONB NOT NULL DEFAULT '{}'::jsonb,
            generated_at TIMESTAMPTZ NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_ebay_flow_catalog_flow_key UNIQUE (flow_key)
        );
    END IF;
END
$$;

-- Documentation (stored in DB comments)
COMMENT ON TABLE public.ebay_flow_catalog IS
'Admin catalog of eBay-related data flows. Each row documents the nodes (eBay calls, backend endpoints/workers, database tables) and edges (data movement) as JSON graph plus searchable metadata.';

COMMENT ON COLUMN public.ebay_flow_catalog.flow_key IS
'Unique stable key for the flow (used in URLs and upserts). Example: transactions_sync, sold_assign_storages_legacy.';

COMMENT ON COLUMN public.ebay_flow_catalog.title IS
'Human-friendly name of the flow.';

COMMENT ON COLUMN public.ebay_flow_catalog.summary IS
'Concise description of what the flow does and why it exists.';

COMMENT ON COLUMN public.ebay_flow_catalog.category IS
'Optional grouping for UI (e.g. sold, listing, inventory, finances, legacy).';

COMMENT ON COLUMN public.ebay_flow_catalog.keywords IS
'Free-form searchable tags (lowercase preferred).';

COMMENT ON COLUMN public.ebay_flow_catalog.graph IS
'JSON graph: {nodes: {key: {type,label,...}}, edges: [{from,to,label,...}]}. Used for rendering arrows/table in Admin.';

COMMENT ON COLUMN public.ebay_flow_catalog.source IS
'Generator metadata: how/when this row was produced (auto/manual), plus detected entrypoints and tables.';

COMMENT ON COLUMN public.ebay_flow_catalog.generated_at IS
'Last time the auto-generator refreshed this row.';

-- updated_at trigger function/trigger (idempotent)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_proc
        WHERE proname = 'set_timestamp_ebay_flow_catalog'
          AND pg_function_is_visible(oid)
    ) THEN
        CREATE FUNCTION public.set_timestamp_ebay_flow_catalog()
        RETURNS TRIGGER AS $func$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $func$ LANGUAGE plpgsql;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_trigger
        WHERE tgname = 'set_timestamp_ebay_flow_catalog'
    ) THEN
        CREATE TRIGGER set_timestamp_ebay_flow_catalog
        BEFORE UPDATE ON public.ebay_flow_catalog
        FOR EACH ROW
        EXECUTE FUNCTION public.set_timestamp_ebay_flow_catalog();
    END IF;
END
$$;

-- Indexes for search (idempotent)
CREATE INDEX IF NOT EXISTS idx_ebay_flow_catalog_category ON public.ebay_flow_catalog (category);
CREATE INDEX IF NOT EXISTS idx_ebay_flow_catalog_keywords_gin ON public.ebay_flow_catalog USING GIN (keywords);
CREATE INDEX IF NOT EXISTS idx_ebay_flow_catalog_search_tsv_gin
ON public.ebay_flow_catalog
USING GIN (
    to_tsvector(
        'simple',
        coalesce(flow_key, '') || ' ' ||
        coalesce(title, '') || ' ' ||
        coalesce(summary, '') || ' ' ||
        coalesce(array_to_string(keywords, ' '), '')
    )
);
