# Tasks & Reminders

This module provides lightweight work management inside the eBay Connector app.

## Data model

### tasks

Single table for both tasks and reminders.

- `id` – string UUID (36 chars)
- `type` – `task` or `reminder`
- `title`, `description`
- `creator_id`, `assignee_id`
- `status`
  - Tasks: `new`, `in_progress`, `snoozed`, `done`, `cancelled`
  - Reminders: `scheduled`, `fired`, `snoozed`, `done`, `dismissed`
- `priority` – `low`, `normal`, `high`
- `due_at`, `snooze_until`
- `is_popup` – whether to show as corner popup
- `created_at`, `updated_at`, `completed_at`, `deleted_at`

### task_comments

Timeline of user comments and system events for a task/reminder.

- `kind` – `comment`, `status_change`, `snooze`, `system`

### task_notifications

Per-user notifications backing the bell icon and corner popups.

- `kind` – `task_assigned`, `task_status_changed`, `task_comment_added`, `reminder_fired`
- `status` – `unread`, `read`, `dismissed`

## Backend API

Routers live in `app/routers/tasks.py`.

### Tasks

- `GET /api/tasks`
  - Query: `type`, `role`, `status`, `search`, `page`, `page_size`
  - Returns paginated list with comment counts and basic creator/assignee info.
- `GET /api/tasks/{task_id}` – full task + comments timeline.
- `POST /api/tasks` – create task or reminder (creator = current user).
- `PATCH /api/tasks/{task_id}` – edit title/description/due_at/priority/is_popup/assignee.
- `POST /api/tasks/{task_id}/status` – change status with optional comment.
- `POST /api/tasks/{task_id}/comments` – add comment.
- `POST /api/tasks/{task_id}/snooze` – set `status=snoozed` and `snooze_until`.

Permissions:

- Non-admins can only see/modify tasks where they are creator or assignee.
- Only creator or admin can cancel tasks (`status=cancelled`).

### Notifications

- `GET /api/task-notifications/unread`
  - Returns unread notifications for current user + minimal task summary.
- `POST /api/task-notifications/{id}/read`
- `POST /api/task-notifications/{id}/dismiss`

Notifications are created for the "other" side (creator vs assignee) on:

- Task assignment
- Status change
- New comment
- Reminder fired (assignee/creator via background worker)

## Reminder worker

Background worker: `app/workers/tasks_reminder_worker.py`.

- Runs every ~60 seconds from `startup_event` in `app/main.py`.
- Finds reminders where:
  - `type='reminder'`
  - `deleted_at IS NULL`
  - (`status='scheduled'` and `due_at <= now`) OR (`status='snoozed'` and `snooze_until <= now`)
- For each row:
  - sets `status='fired'`, clears `snooze_until`
  - inserts `task_comments` system row ("Reminder fired at …")
  - inserts `task_notifications` row with `kind='reminder_fired'` for assignee (or creator if no assignee)

## Frontend

### Bell + dropdown + popups

`TaskNotificationsBell` is mounted in `FixedHeader` and provides:

- Bell icon with unread count badge (polled every 20s).
- Dropdown list of unread notifications with quick actions:
  - Tasks: Start / Done / Dismiss
  - Reminders: Done / Snooze 15m/1h / Dismiss
- Corner popups (max 3 visible, queued) for new notifications with:
  - Open (navigates to `/tasks?taskId=...`)
  - Same quick actions as dropdown

### Tasks page

`/tasks` route handled by `TasksPage`:

- Filters:
  - Type (All / Tasks / Reminders)
  - Role (Assigned to me / Created by me / All – admin only)
  - Status dropdown
  - Search in title/description
- View modes:
  - List view: simple table
  - Board view: 4 columns (`New`, `In progress`, `Snoozed`, `Done`) for `type='task'`
- Detail panel on the right with:
  - Status + priority badges
  - Creator / assignee / due date
  - Buttons:
    - Tasks: Start / Snooze 1h / Done / Cancel
    - Reminders: Snooze 1h / Done / Dismiss
  - Activity timeline (comments + system events)
  - Comment box (adds comment via `/comments`)

## Tests

Minimal unit tests live in `backend/tests/test_tasks_status.py` and cover:

- Valid task status transitions
- Invalid transitions raising `HTTPException`
- Reminder status transitions
