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

## End-to-end architecture

Timesheets span the legacy MSSQL data, the new Postgres schema, FastAPI backend, and the React frontend.

**Storage and schema**

- Legacy table: `dbo.tbl_Timesheet` (source system). See `docs/timesheets_schema_mapping.md` for column-by-column mapping.
- Migration layer: Alembic migration `20251117_timesheets_001.py` creates the new `timesheets` table and backfills from legacy when available.
- Primary table: `public.timesheets` (SQLAlchemy model `app.db_models.timesheet.Timesheet`).
- Each row may contain `legacy_id` pointing back to the original `tbl_Timesheet.ID`.

**Backend services**

- API router: `app.routers.timesheets` mounted at `/api/timesheets`.
- Dependencies:
  - `get_db()` – SQLAlchemy session.
  - `get_current_active_user()` – JWT-based auth from `app.services.auth`.
- Key functions:
  - `start_timesheet()` – worker start; validates that there is no open entry and then inserts a new row.
  - `stop_timesheet()` – worker stop; finds the latest open row and finalizes it with `end_time` and `duration_minutes`.
  - `list_my_timesheets()` – worker history; filters by `user_id` and optional `from`/`to` range.
  - `admin_list_timesheets()` – admin grid; multi-user listing with filters.
  - `admin_add_timesheet()` – admin manual insertion.
  - `admin_patch_timesheet()` – admin editing / soft delete.
- DTOs:
  - `TimesheetEntry` – canonical JSON contract for a timesheet row (camelCase field names).
  - `Pagination` – standard paginated response wrapper.
  - `Envelope` – `{ success, data, error }` wrapper used across endpoints.

**Frontend integration**

- API client: `frontend/src/api/timesheets.ts` wraps the HTTP endpoints and exposes typed helpers:
  - `startTimesheet(description?)` → `POST /api/timesheets/start`.
  - `stopTimesheet(description?)` → `POST /api/timesheets/stop`.
  - `getMyTimesheets({ from, to, page, pageSize })` → `GET /api/timesheets/my`.
  - `adminListTimesheets`, `adminAddTimesheet`, `adminPatchTimesheet` for admin use.
- Worker UI:
  - `frontend/src/pages/MyTimesheetPage.tsx` renders the **My Timesheet** worker view.
  - It uses `startTimesheet` / `stopTimesheet` and calls `getMyTimesheets` with a **14-day window** (`from = now-14d`, `to = now`).
  - The page detects the active entry by checking for `endTime === null && !deleteFlag`.
- Admin UI:
  - `frontend/src/pages/AdminTimesheetsPage.tsx` implements the admin grid, add/edit/delete controls, and filters.
- Navigation:
  - Header component `frontend/src/components/FixedHeader.tsx` renders a small **clock icon** button near the build info.
  - Clicking the clock runs `navigate('/timesheets/my')` and takes the current user to their own timesheet page.
  - The same header uses the logged-in user from `useAuth()` to decide which admin tabs to show.

## Request/response flow examples

### Worker starts a timer from the nav clock

1. User clicks the clock icon in the fixed header.
2. `FixedHeader` calls `navigate('/timesheets/my')` (client-side route change).
3. `MyTimesheetPage` loads and immediately invokes `loadData()`:
   - Computes `now` and `fourteenDaysAgo`.
   - Calls `getMyTimesheets({ from, to, page: 1, pageSize: 100 })`.
   - Backend `list_my_timesheets()` filters rows for the current `user_id` and date range and returns a paginated `TimesheetEntry` list.
4. User optionally types a description and clicks **Start Time**.
5. Frontend calls `startTimesheet(description)` → `POST /api/timesheets/start`.
6. Backend `start_timesheet()`:
   - Checks for an open timer entry for this user.
   - Inserts a new `timesheets` row with `start_time = now`, `end_time = NULL`, and initial audit fields.
   - Returns `Envelope(success=True, data=TimesheetEntry, error=None)`.
7. Frontend clears the description and reloads data to show the new active entry.

### Worker stops a timer

1. On the **My Timesheet** page, user clicks **Stop Time**.
2. Frontend calls `stopTimesheet(description)` → `POST /api/timesheets/stop`.
3. Backend `stop_timesheet()`:
   - Finds the most recent open entry (`end_time IS NULL`) for this user.
   - Sets `end_time = now` and recomputes `duration_minutes`.
   - Optionally updates `description`.
   - Updates audit columns and commits the transaction.
4. Frontend reloads the last 14 days and shows the closed entry in the **Recent entries** table.

### Admin edits an entry

1. Admin navigates to `/timesheets/admin` and uses filters as needed.
2. Frontend calls `adminListTimesheets()` → `GET /api/timesheets`.
3. Backend `admin_list_timesheets()` checks that `current_user.role == 'admin'` and then returns paginated `TimesheetEntry` items.
4. Admin uses **Edit** on a row and saves changes.
5. Frontend calls `adminPatchTimesheet(id, payload)` → `PATCH /api/timesheets/admin/{id}`.
6. Backend `admin_patch_timesheet()`:
   - Applies partial updates (start, end, rate, description, deleteFlag).
   - Validates that `end_time > start_time` when both are set and recomputes `duration_minutes`.
   - Updates `record_updated`/`record_updated_by` and returns the updated `TimesheetEntry`.

These flows should give future maintainers and agents enough context to safely evolve the timesheet system without re-reading the entire codebase.
