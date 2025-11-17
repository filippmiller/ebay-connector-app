# Timesheets Overview

This document describes the new timesheet system for the eBay Connector internal admin app: schema, flows, and roles.

## Tables

### users (extended)

The existing `users` table is reused and extended to support timesheets:

- Existing core fields: `id`, `email`, `username`, `hashed_password`, `role`, `is_active`, `created_at`, `updated_at`, plus eBay and preference fields.
- New timesheet/audit fields:
  - `legacy_id numeric(18,0)` – optional link to `dbo.tbl_Users.ID`.
  - `full_name varchar(255)` – display name for employees.
  - `hourly_rate numeric(18,2)` – default hourly pay rate.
  - `auth_user_id uuid` – reserved link to external auth provider.
  - `record_created timestamptz NOT NULL DEFAULT now()`.
  - `record_created_by varchar(50)`.
  - `record_updated timestamptz NOT NULL DEFAULT now()`.
  - `record_updated_by varchar(50)`.

A trigger `trg_users_set_record_updated` ensures `record_updated` is updated automatically on `UPDATE` via the shared `public.set_record_updated_timestamp()` function.

### timesheets (new)

The new `timesheets` table stores per-user time entries:

- `id bigserial` – primary key.
- `user_id String(36)` – FK to `users.id`.
- `username varchar(50)` – copy of `users.username` for migration/history.
- `start_time timestamptz` – start of the time slot.
- `end_time timestamptz` – end of the time slot.
- `duration_minutes integer` – computed at stop time.
- `rate numeric(18,2)` – hourly rate used for this entry.
- `description text` – description of work performed.
- `delete_flag boolean NOT NULL DEFAULT false` – soft delete.
- `record_created timestamptz NOT NULL DEFAULT now()`.
- `record_created_by varchar(50)`.
- `record_updated timestamptz NOT NULL DEFAULT now()`.
- `record_updated_by varchar(50)`.
- `legacy_id numeric(18,0)` – original `dbo.tbl_Timesheet.ID` if available.

Constraints and indexes:

- `timesheets_consistent_time_chk` – ensures either both `start_time`/`end_time` are null, or both non-null with `end_time > start_time`.
- `idx_timesheets_user_start` on `(user_id, start_time DESC)`.
- `idx_timesheets_delete_flag` on `delete_flag`.
- Trigger `trg_timesheets_set_record_updated` keeps `record_updated` in sync on updates.

See `docs/timesheets_schema_mapping.md` for detailed MSSQL → Postgres mapping.

## Roles and permissions

Timesheets rely on the existing auth system (`get_current_active_user` / JWT tokens) and the `users.role` field.

- **Worker** – regular user; can:
  - Start a timer (`POST /api/timesheets/start`).
  - Stop their active timer (`POST /api/timesheets/stop`).
  - View their own entries (`GET /api/timesheets/my`).
  - Cannot manually create or edit arbitrary entries.
- **Admin** – user with `role == 'admin'` (enforced server-side); can:
  - List timesheets across users (`GET /api/timesheets`).
  - Add time for any user (`POST /api/timesheets/admin/add`).
  - Edit existing entries (`PATCH /api/timesheets/admin/{id}`).

All admin endpoints must enforce admin role checks and return a 403-style error when the caller is not an admin.

## Flows

### Worker flow

1. **Start work**
   - User visits the "My Timesheet" page.
   - Clicks **Start Time** → `POST /api/timesheets/start` (optional `description`).
   - Backend checks for an existing open timer (no `end_time`); if one exists, returns `TIMER_ALREADY_RUNNING`.
   - Otherwise, creates a new `timesheets` row with server-side `start_time = now()`.

2. **Stop work**
   - User clicks **Stop Time** → `POST /api/timesheets/stop` (optional updated `description`).
   - Backend finds latest open entry for the current user and sets `end_time = now()`.
   - Computes `duration_minutes` as the rounded difference in minutes.

3. **Review history**
   - Page loads `GET /api/timesheets/my` with optional date range and pagination.
   - Shows a grid with key columns: user, start date/time, end date/time, duration, description, rate.

Workers **cannot** add or edit arbitrary entries; they can only control their own active timer.

### Admin flow

1. **Browse timesheets**
   - Admin visits the "Timesheets" page.
   - Uses filters: user, date range, etc.
   - Frontend calls `GET /api/timesheets` with filters and pagination.

2. **Add time**
   - Admin selects a user and enters a time range in a dialog.
   - Frontend calls `POST /api/timesheets/admin/add` with user, start/end, rate, description.
   - Backend validates the time range and either uses the provided `rate` or defaults to the user’s `hourly_rate`.

3. **Edit time**
   - Admin edits an existing row from the grid.
   - Frontend sends partial updates to `PATCH /api/timesheets/admin/{id}`.
   - Backend recomputes `duration_minutes` when start or end changes and validates the new time range.

## JSON contracts

The JSON contracts for users, timesheet entries, pagination, and error envelopes are defined in the implementation spec and followed by the timesheet endpoints:

- `User` object – exposes id, legacyId, username, fullName, role, hourlyRate, isActive, recordCreated/Updated (+ _By).
- `TimesheetEntry` – exposes core timesheet fields with camelCase names.
- Pagination wrapper – `{ items, page, pageSize, totalItems, totalPages }`.
- Error envelope – `{ success, data, error }` with structured error codes.

## Worker vs admin summary

- Workers:
  - Use **Start/Stop** only.
  - Cannot retroactively change time.
  - See only their own records.

- Admins:
  - Can view records for all users.
  - Can create and edit entries for any user.
  - Are responsible for fixing mistakes and handling missed clock-ins.
