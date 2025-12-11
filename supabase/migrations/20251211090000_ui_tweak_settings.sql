-- Create ui_tweak_settings table for UI/graph settings persistence (idempotent)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name = 'ui_tweak_settings'
    ) THEN
        CREATE TABLE public.ui_tweak_settings (
            id BIGSERIAL PRIMARY KEY,
            settings JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    END IF;
END
$$;

-- Ensure updated_at refreshes on updates (skip if trigger already exists)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_proc
        WHERE proname = 'set_timestamp_ui_tweak_settings'
          AND pg_function_is_visible(oid)
    ) THEN
        CREATE FUNCTION public.set_timestamp_ui_tweak_settings()
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
        WHERE tgname = 'set_timestamp_ui_tweak_settings'
    ) THEN
        CREATE TRIGGER set_timestamp_ui_tweak_settings
        BEFORE UPDATE ON public.ui_tweak_settings
        FOR EACH ROW
        EXECUTE FUNCTION public.set_timestamp_ui_tweak_settings();
    END IF;
END
$$;

-- Seed default row once to match backend defaults (safe no-op if row exists)
INSERT INTO public.ui_tweak_settings (settings)
SELECT jsonb_build_object(
    'fontScale', 1.0,
    'navScale', 1.0,
    'gridDensity', 'normal',
    'navActiveBg', '#2563eb',
    'navActiveText', '#ffffff',
    'navInactiveBg', 'transparent',
    'navInactiveText', '#374151'
)
WHERE NOT EXISTS (SELECT 1 FROM public.ui_tweak_settings);

