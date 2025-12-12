# eBay Workers: Completion Notifications

This document describes how eBay workers emit completion notifications using
the existing Task / TaskNotification infrastructure so you can see concise
summaries of each run in the notifications UI.

---

## High-level behaviour

For every eBay worker run (Orders, Transactions, Finances, Messages, Cases,
Inquiries, Offers, Buyer, Active Inventory):

- When the worker **completes successfully**:
  - A small **Task** of type `reminder` is created.
  - A **TaskNotification** is created and marked `unread` for the owning org
    user (the `users.id` referenced by `ebay_accounts.org_id`).
- When the worker **fails with an error**:
  - A similar `reminder` Task is created with a `failed` suffix in the title.
  - The TaskNotification includes the error message in the Task description.

These reminders are purely informational; they do not introduce new todo work
items and are treated as *already-fired* reminders.

The notifications appear under the existing `/api/task-notifications/unread`
endpoint and in the corresponding UI panel.

---

## Helper: `create_worker_run_notification`

**File:** `backend/app/services/ebay_workers/notifications.py`

Workers do not talk to the Tasks router directly. Instead they call a small
helper:

```python path=null start=null
create_worker_run_notification(
    db,
    account=account,          # EbayAccount row for this worker
    api_family="orders",      # 'orders', 'transactions', 'finances', ...
    run_status="completed",   # 'completed' or 'error'
    summary=summary_dict,      # worker summary JSON passed to complete_run/fail_run
)
```

Key responsibilities of the helper:

- Determine **who to notify**:
  - Uses `account.org_id` as the canonical owner `users.id`.
- Build a short **title** for the Task:
  - Success: `"eBay {api_family} worker for {house_name} completed"`.
  - Failure: `"eBay {api_family} worker for {house_name} failed"`.
- Build a **description** string from the worker summary:
  - Window: `window_from → window_to`.
  - Counts: `Fetched: {total_fetched}; Stored: {total_stored}`.
  - Sync id: `sync_run_id` (if present).
  - Error: `Error: {error_message}` (failures only).
- Insert a `Task` row of type `reminder` with:
  - `creator_id = assignee_id = account.org_id`.
  - `status = 'fired'` for successful runs, `'done'` for failures.
  - `is_popup = True` so it can surface as a small popup/reminder.
- Insert a matching `TaskNotification` row:
  - `user_id = account.org_id`.
  - `kind = f"ebay_worker_{api_family}_completed"` or `_failed`.
  - `status = 'unread'`.

The helper is **best-effort only**: any exception is logged and rolled back,
but the worker run itself is not affected.

---

## Wiring in each worker

Each eBay worker already computes a `summary` dict and passes it into
`complete_run` / `fail_run`. As part of this change we ensure the summary always
includes:

- `total_fetched`
- `total_stored`
- `duration_ms`
- `window_from`
- `window_to`
- `sync_run_id`
- (errors only) `error_message`

Immediately after **successful** completion, a worker now calls the helper, for
example (Orders worker):

```python path=null start=null
summary = {
    "total_fetched": total_fetched,
    "total_stored": total_stored,
    "duration_ms": duration_ms,
    "window_from": from_iso,
    "window_to": to_iso,
    "sync_run_id": sync_run_id,
}

complete_run(db, run, summary=summary)

create_worker_run_notification(
    db,
    account=account,
    api_family="orders",
    run_status="completed",
    summary=summary,
)
```

On **errors**, the pattern is similar but includes an `error_message` field and
uses `run_status="error"`:

```python path=null start=null
error_summary = {
    "total_fetched": total_fetched,
    "total_stored": total_stored,
    "duration_ms": duration_ms,
    "window_from": from_iso,
    "window_to": to_iso,
    "sync_run_id": sync_run_id,
    "error_message": msg,
}

fail_run(db, run, error_message=msg, summary=error_summary)

create_worker_run_notification(
    db,
    account=account,
    api_family="orders",
    run_status="error",
    summary=error_summary,
)
```

The same pattern is applied consistently to:

- `orders_worker`
- `transactions_worker`
- `finances_worker`
- `messages_worker`
- `cases_worker`
- `inquiries_worker`
- `offers_worker`
- `purchases_worker` (Buyer)
- `active_inventory_worker`

---

## What you see in the UI

In the notifications panel you will now see entries like:

- **Title:** `eBay orders worker for HOUSE-1 completed`
- **Body:**
  - `Window: 2025-11-28T10:00:00Z → 2025-11-28T10:30:00Z`
  - `Fetched: 123; Stored: 120`
  - `Sync run id: worker_orders_...`

On failures, the body additionally contains an **Error** line summarising the
Python or eBay API error message captured by the worker.

Marking the notification as read/dismissed continues to use the existing
`/api/task-notifications/{id}/read` and `/dismiss` endpoints; the eBay workers
code does not change that behaviour.
