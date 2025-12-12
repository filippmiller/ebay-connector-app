# UI Tweak Settings Migration Plan (ui_tweak_settings_20251121)

This document describes how to create and apply the `ui_tweak_settings` table in the production Supabase / Railway environment so that `/api/ui-tweak` and `/api/admin/ui-tweak` work without falling back to defaults only.

## 1. Migration details

- Alembic revision ID: `ui_tweak_settings_20251121`
- Migration file: `backend/alembic/versions/ui_tweak_settings_20251121.py`
- Depends on: `shipping_tables_20251121`

The migration:

- Creates table `ui_tweak_settings` with columns:
  - `id` – `INTEGER`, primary key, autoincrement.
  - `settings` – `JSONB NOT NULL` with server default `'{}'::jsonb`.
  - `created_at` – `TIMESTAMPTZ NOT NULL` with `now()` default.
  - `updated_at` – `TIMESTAMPTZ NOT NULL` with `now()` default.
- Seeds a single row with default settings if the table is empty.

## 2. Running the migration in production

> IMPORTANT: These commands must be executed in the same environment and with the same `DATABASE_URL` that the production backend uses (Railway service).

From the repo root:

1. Ensure code is deployed and the backend container has the latest Alembic files.
2. Use Railway CLI (or your existing deployment tooling) to run Alembic inside the backend service, for example:

```bash
railway run --service ebay-connector-app --environment production -- \
  poetry -C backend run alembic upgrade ui_tweak_settings_20251121
```

If your project prefers upgrading to the latest head, you can instead run:

```bash
railway run --service ebay-connector-app --environment production -- \
  poetry -C backend run alembic upgrade head
```

Make sure `RAILWAY_TOKEN`, `DATABASE_URL`, and other required env vars are present for the service.

## 3. Verifying the migration

After running the migration:

1. Connect to the same Postgres instance (via `psql` or a SQL console) and run:

```sql
SELECT * FROM ui_tweak_settings LIMIT 1;
```

You should see one row with a JSON `settings` payload.

2. Call the backend endpoint (through the deployed API):

- `GET /api/ui-tweak`
- `GET /api/admin/ui-tweak` (as an admin user)

You should now receive a JSON payload with UI tweak settings and **no 500 errors**.

3. From the Admin UI Tweak page, change a setting (e.g. nav color or grid density) and confirm:

- The change is reflected visually after a page reload.
- A subsequent `GET /api/ui-tweak` returns the updated settings.

## 4. Failure modes and rollbacks

- If the migration fails due to permission or connection issues, **do not** retry blindly:
  - Verify `DATABASE_URL` and credentials.
  - Check Alembic’s current revision with:

    ```bash
    railway run --service ebay-connector-app --environment production -- \
      poetry -C backend run alembic current -v
    ```

- To roll back just this migration (not usually necessary), you can run:

  ```bash
  railway run --service ebay-connector-app --environment production -- \
    poetry -C backend run alembic downgrade shipping_tables_20251121
  ```

  This will drop the `ui_tweak_settings` table. Only use this if you are certain you need to undo the migration.

## 5. Application behaviour before vs after migration

- **Before migration:**
  - `/api/ui-tweak` and `/api/admin/ui-tweak` return **default** settings only.
  - Admin attempts to `PUT /api/admin/ui-tweak` receive a 503 response with a clear message indicating the missing table.
- **After migration:**
  - Settings are persisted in `ui_tweak_settings.settings`.
  - Both endpoints operate normally; admins can change global UI tweak settings for all users.
