# Timesheets Auth & Users Audit

This document summarizes how authentication and application users work today in the eBay Connector backend and how the new timesheets feature maps onto it.

## Existing auth

- **Auth mechanism**: Custom JWT-based auth using `fastapi` and `python-jose`.
- **Token creation**: `app.services.auth.create_access_token` signs a JWT with `sub = user.id`.
- **Auth dependency**:
  - `get_current_user` decodes the JWT and loads the user via `db.get_user_by_id`.
  - `get_current_active_user` enforces `user.is_active`.
  - `admin_required` enforces `user.role == UserRole.ADMIN`.

## Existing users table

There is already a primary `users` table and associated models:

- SQLAlchemy model (Postgres/SQLAlchemy layer): `app.db_models.user.User`
- Pydantic/user-facing model: `app.models.user.User` and related schemas

### DB schema (high level)

`app.db_models.user.User` maps to `users` with (simplified):

- `id: String(36)` – primary key (UUID-as-string)
- `email: String(255)` – unique, indexed
- `username: String(100)` – not unique today
- `hashed_password: String(255)`
- `role: String(20)` – app-level role ("user" or "admin")
- `is_active: Boolean`
- `created_at: timestamptz`
- `updated_at: timestamptz`
- eBay-related columns: `ebay_connected`, `ebay_user_id`, `ebay_access_token`, `ebay_refresh_token`, `ebay_token_expires_at`, `ebay_marketplace_id`, `ebay_last_sync_at`
- UI-related columns: `notification_preferences`, `display_preferences`

This table is already used for:

- Login / registration
- Determining per-user access to eBay accounts and admin routes

## Timesheets design decision

Per the spec:

> If there is already a users-like table, extend it to satisfy the fields below (no duplicates).

Given the existing `users` table is already the canonical application user store, we **extend that table** rather than creating a new `public.users`.

New fields added (via Alembic migration `timesheets_001`):

- `legacy_id numeric(18,0)` – optional MSSQL `dbo.tbl_Users.ID` mapping
- `full_name varchar(255)` – human-readable name
- `hourly_rate numeric(18,2)` – default hourly pay rate
- `auth_user_id uuid` – optional link to external auth provider (reserved for future use)
- `record_created timestamptz NOT NULL DEFAULT now()` – timesheet/audit creation timestamp
- `record_created_by varchar(50)` – who created the record
- `record_updated timestamptz NOT NULL DEFAULT now()` – last update timestamp
- `record_updated_by varchar(50)` – who last updated the record

Additional indexes / constraints:

- `idx_users_role_active` on `(role, is_active)` if both columns exist
- Partial unique index `users_auth_user_id_key` on `auth_user_id` where not null

A shared trigger function `public.set_record_updated_timestamp()` is created once and used to keep `record_updated` current on `UPDATE`.

## Roles for timesheets

For the timesheet feature we use a simple role model:

- `worker` – regular employees who can start/stop their own timers and view their own entries
- `admin` – administrators who can view, add, and edit timesheets for any user

Because the existing `users.role` is a free-form string constrained by application logic, we will:

- Treat `role == 'admin'` as timesheet admin
- Treat all other roles (including existing values like `user`) as workers, unless we later add a dedicated mapping.

Timesheet endpoints will rely on the current auth stack (`get_current_active_user`) and enforce:

- Worker endpoints: current user must be authenticated and active.
- Admin endpoints: current user must satisfy `role == 'admin'`.

## Summary

- We **reuse and extend** the existing `users` table rather than introducing a second users table.
- New timesheet-related fields and audit fields are added in-place.
- Auth remains unchanged (JWT + `get_current_active_user` / `admin_required`), and is reused for timesheet permissions.
- The new `timesheets` table references `users.id` as a foreign key for all entries.
