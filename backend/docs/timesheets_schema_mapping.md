# Timesheets Schema Mapping (MSSQL → Postgres)

This document records how the legacy MSSQL tables map to the new Postgres schema used for the timesheet system.

## Legacy MSSQL tables

- `dbo.tbl_Users`
- `dbo.tbl_Timesheet`

## Postgres tables

- `public.users` (existing app users table, extended for timesheets)
- `public.timesheets` (new per-user time entries)

## dbo.tbl_Users → public.users

| MSSQL column          | Postgres column         | Notes                                        |
|-----------------------|-------------------------|----------------------------------------------|
| `ID`                  | `users.legacy_id`       | Numeric ID from legacy system (nullable).    |
| `UserName`            | `users.username`        | Existing username field, reused.             |
| other auth fields     | existing `users.*`      | Email, hashed password, etc., already exist. |

Additional timesheet-specific columns on `users`:

- `full_name` – optional full display name for employees.
- `hourly_rate` – default hourly pay rate for this user.
- `auth_user_id` – optional UUID linking to external auth provider (reserved).
- `record_created`, `record_created_by` – who/when the row was created.
- `record_updated`, `record_updated_by` – who/when the row was last updated.

## dbo.tbl_Timesheet → public.timesheets

| MSSQL column          | Postgres column             | Notes                                                        |
|-----------------------|-----------------------------|--------------------------------------------------------------|
| `ID`                  | `timesheets.legacy_id`      | Legacy numeric identifier; Postgres has its own `id`.        |
| `UserName`            | `timesheets.username`       | Copied for migration/history.                                |
| `UserID` (if exists)  | `timesheets.user_id`        | FK to `users.id` (string UUID); must be resolved on import.  |
| `StartTime`           | `timesheets.start_time`     | Converted to `timestamptz`.                                  |
| `EndTime`             | `timesheets.end_time`       | Converted to `timestamptz`.                                  |
| `Rate`                | `timesheets.rate`           | Numeric(18,2).                                               |
| `Description`         | `timesheets.description`    | Free-form text.                                              |
| `DeleteFlag`          | `timesheets.delete_flag`    | Boolean soft delete.                                         |
| `record_created`      | `timesheets.record_created` | Creation timestamp.                                          |
| `record_created_by`   | `timesheets.record_created_by` | Who created the row.                                     |
| `record_updated`      | `timesheets.record_updated` | Last update timestamp.                                       |
| `record_updated_by`   | `timesheets.record_updated_by` | Who last updated the row.                                 |

Additional Postgres-only columns on `timesheets`:

- `id` – `bigserial` primary key for Postgres.
- `duration_minutes` – computed duration at stop time.

## Constraints and triggers

### Time consistency

`timesheets` has a check constraint:

```sql
(start_time IS NULL AND end_time IS NULL)
OR (start_time IS NOT NULL AND end_time IS NOT NULL AND end_time > start_time)
```

This mirrors the expectation in the legacy system that a time slot is either entirely unset or has a valid end after its start.

### record_updated trigger

A shared trigger function `public.set_record_updated_timestamp()` updates `record_updated` on each `UPDATE` for:

- `users`
- `timesheets`

This provides a consistent audit trail similar to the legacy `record_updated` field while centralizing the update logic in the database.

## Summary

- Legacy `tbl_Users` maps into the existing `users` table via `legacy_id` and shared `username`.
- Legacy `tbl_Timesheet` maps into the new `timesheets` table via `legacy_id`, `username`, and resolved `user_id` FKs.
- Additional audit fields and constraints are added to support robust, migration-friendly timesheet handling.
