# eBay Workers Loop – Architecture and Current Status

This document explains how the eBay data workers loop is wired in the "eBay Connector" app, what the Railway services are doing, and why the dedicated `aebay-workers-loop` service is currently _not_ running any cycles even though the code exists.

It is intended as a design/diagnostic doc for another engineer reading the system.

---

## 1. Components overview

There are three main pieces involved in running background eBay workers:

1. **Main API process (FastAPI / Uvicorn)** – service `ebay-connector-app` on Railway.
2. **Background workers package** – `app.workers` in the backend codebase.
3. **Standalone worker services on Railway** – specifically:
   - `aebay-workers-loop` – intended to run the main eBay workers loop.
   - `atoken-refresh-worker` – runs the token refresh loop.

### 1.1. Scheduler and per-account workers

The logic that decides _which workers run for which account_ lives in
`backend/app/services/ebay_workers/scheduler.py`:

```python path=/Users/filip/.gemini/antigravity/playground/silent-spirit/backend/app/services/ebay_workers/scheduler.py start=140
async def run_cycle_for_all_accounts() -> None:
    """Run one sync cycle for all *active* eBay accounts.

    This is the core entry point used by the background scheduler loop. It is
    safe to call from an external cron as well (e.g. Railway/Cloudflare).
    """

    db = _get_db()
    try:
        if not are_workers_globally_enabled(db):
            logger.info("Global workers_enabled=false – skipping cycle for all accounts")
            return

        # Fetch all active ebay accounts.
        accounts: List[EbayAccount] = (
            db.query(EbayAccount)
            .filter(EbayAccount.is_active == True)
            .all()
        )
        if not accounts:
            logger.info("No active eBay accounts found – skipping worker cycle")
            return
    finally:
        db.close()

    for account in accounts:
        try:
            logger.info(
                "Running worker cycle for account id=%s ebay_user_id=%s house_name=%s",
                account.id,
                getattr(account, "ebay_user_id", "unknown"),
                getattr(account, "house_name", None),
            )
            await run_cycle_for_account(account.id)
        except Exception as exc:
            logger.error(
                "Worker cycle failed for account id=%s: %s",
                account.id,
                exc,
                exc_info=True,
            )
```

`run_cycle_for_account` then dispatches to concrete per-account workers
(orders, transactions, offers, messages, active_inventory, buyer) based on
`EbaySyncState` flags (`enabled`, cursor, last_run_at, etc.). Each worker writes
rows into `ebay_worker_run` + `ebay_api_worker_log`, which feed the Admin
Workers UI.

### 1.2. The loop function

The **loop** that is supposed to call `run_cycle_for_all_accounts` every N
seconds is defined in `backend/app/workers/ebay_workers_loop.py`:

```python path=/Users/filip/.gemini/antigravity/playground/silent-spirit/backend/app/workers/ebay_workers_loop.py start=14
async def run_ebay_workers_once() -> None:
    """Run one full workers cycle for all active accounts."""
    try:
        await run_cycle_for_all_accounts()
    except Exception as exc:
        logger.error("eBay workers cycle failed: %s", exc, exc_info=True)


async def run_ebay_workers_loop(interval_seconds: int = 300) -> None:
    """Run eBay workers in a loop.

    Default interval is 300 seconds (5 minutes).
    """
    logger.info("eBay workers loop started (interval=%s seconds)", interval_seconds)

    while True:
        await run_ebay_workers_once()
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    asyncio.run(run_ebay_workers_loop())
```

So at the pure Python level:
- A **single iteration** for all accounts is `run_ebay_workers_once()`.
- A **long-running loop** is `run_ebay_workers_loop()`, which calls that once
  every 300 seconds.

---

## 2. How the loop is actually started in the main API

Inside `backend/app/main.py` (FastAPI application), there is a `startup` event
handler that **starts several background loops inside the main API process**:

```python path=/Users/filip/.gemini/antigravity/playground/silent-spirit/backend/app/main.py start=230
    if start_workers:
        logger.info("🔄 Starting background workers...")
        try:
            from app.workers import (
                run_token_refresh_worker_loop,
                run_health_check_worker_loop,
                run_ebay_workers_loop,
                run_tasks_reminder_worker_loop,
                run_sniper_loop,
                run_monitoring_loop,
                run_auto_offer_buy_loop,
                run_db_migration_workers_loop,
            )
            
            asyncio.create_task(run_token_refresh_worker_loop())
            logger.info("✅ Token refresh worker started (runs every 10 minutes)")
            
            asyncio.create_task(run_health_check_worker_loop())
            logger.info("✅ Health check worker started (runs every 15 minutes)")

            # eBay data workers loop – runs every 5 minutes and triggers all
            # enabled workers (orders, transactions, offers, messages, cases,
            # finances, active inventory) for all active accounts.
            asyncio.create_task(run_ebay_workers_loop())
            logger.info("✅ eBay workers loop started (runs every 5 minutes)")
            ...
```

Key points:

- The main FastAPI app imports **from `app.workers`**, not directly from
  `app.workers.ebay_workers_loop`.
- On startup (in production, where `DATABASE_URL` points to Postgres), it
  calls `asyncio.create_task(run_ebay_workers_loop())` inside the API process.
- This means: **even if there were no separate worker service, the eBay data
  workers loop would still run**, hosted by the `ebay-connector-app` service.

This is important context when interpreting the status of the dedicated
`aebay-workers-loop` Railway service.

---

## 3. The `app.workers` package and the circular import

The `app.workers` package (`backend/app/workers/__init__.py`) re-exports many
worker loop functions, including the eBay workers loop:

```python path=/Users/filip/.gemini/antigravity/playground/silent-spirit/backend/app/workers/__init__.py start=12
from app.workers.token_refresh_worker import refresh_expiring_tokens, run_token_refresh_worker_loop
from app.workers.health_check_worker import run_all_health_checks, run_health_check_worker_loop
from app.workers.ebay_workers_loop import run_ebay_workers_loop, run_ebay_workers_once
from app.workers.tasks_reminder_worker import run_tasks_reminder_worker_loop
from app.workers.sniper_executor import run_sniper_loop
...
```

So importing **`app.workers`** _immediately imports_ `app.workers.ebay_workers_loop`.

This is normally fine when `app.workers.ebay_workers_loop` is just a library
module. But now consider how the dedicated Railway worker service is started.

---

## 4. Railway services and their start commands

From `railway status --json` (summarized):

- `ebay-connector-app` – main FastAPI API, runs Uvicorn.
- `atoken-refresh-worker` – runs `python -m app.workers.token_refresh_worker`.
- `aebay-workers-loop` – runs `python -m app.workers.ebay_workers_loop`.

The relevant one is:

```text
Service: aebay-workers-loop
startCommand: "python -m app.workers.ebay_workers_loop"
```

When Python executes `python -m some.module`, it uses `runpy` to execute that
module as a script. Under _normal_ circumstances:

- The target module is loaded with `__name__ == "__main__"`.
- `if __name__ == "__main__": asyncio.run(run_ebay_workers_loop())` **does**
  run.

However, in our case the logs from `aebay-workers-loop` look like this:

```text
Starting Container
... Pydantic UserWarning spam ...
<frozen runpy>:128: RuntimeWarning: 'app.workers.ebay_workers_loop' found in sys.modules after import of package 'app.workers', but prior to execution of 'app.workers.ebay_workers_loop'; this may result in unpredictable behaviour
```

And **nothing else**:

- No `"eBay workers loop started (interval=300 seconds)"` from our logger.
- No worker cycle logs at all.

This tells us exactly what is happening under the hood:

1. The interpreter starts `python -m app.workers.ebay_workers_loop`.
2. Internally, `runpy` imports the package `app.workers`.
3. `app.workers.__init__` executes, which in turn does:
   `from app.workers.ebay_workers_loop import run_ebay_workers_loop, ...`.
4. That import loads `app.workers.ebay_workers_loop` as a **normal import**
   with `__name__ == "app.workers.ebay_workers_loop"` (not `"__main__"`).
5. When `runpy` then tries to execute `app.workers.ebay_workers_loop` as the
   main module, it finds that it is already present in `sys.modules` and
   issues the RuntimeWarning you see.
6. Because the module was already imported in library-mode, the `if __name__ == "__main__"` block never fires, and the loop is **never started**.

So the dedicated `aebay-workers-loop` process is effectively a **no-op**:

- It imports the module, prints a few warnings, and exits.
- No cycles, no logs, no work.

Meanwhile, the **main API process** _is_ starting `run_ebay_workers_loop` via
its startup hook, using the same function from `app.workers`.

---

## 5. Current runtime status

Based on live Railway logs and the code structure:

1. **Main API (`ebay-connector-app`)**
   - Starts background workers (token-refresh, health-check, eBay workers loop,
     etc.) on FastAPI startup.
   - You should see logs in this service like:
     - `"✅ eBay workers loop started (runs every 5 minutes)"`
     - Per-account worker logs (orders, transactions, offers, etc.) via
       `EbayWorkerRun`/`EbayApiWorkerLog`.
2. **Token refresh worker (`atoken-refresh-worker`)**
   - Runs independently with its own loop, and _is_ executing cycles.
   - Earlier, it was failing with `400 invalid_grant` because encrypted refresh
     tokens were being sent directly to eBay; that has been fixed by decrypting
     before HTTP and centralizing the refresh flow.
3. **Dedicated workers loop service (`aebay-workers-loop`)**
   - Starts container, prints Pydantic warnings and the `runpy` RuntimeWarning,
     then does nothing.
   - No `eBay workers loop started` message ever appears here.
   - All actual worker cycles are currently coming from the **main API
     process**, not this separate service.

So from a system point of view:

- **Functional behaviour:** eBay workers can still be running (and are intended
  to run) as long as the main API is healthy, because the loop is started from
  `main.py`.
- **Redundant / misconfigured service:** `aebay-workers-loop` adds no value in
  its current form due to the import cycle described above.

---

## 6. Options going forward

There are two primary ways to clean this up, depending on the desired
architecture.

### Option A – Rely solely on the main API to drive the loop (simplest)

1. **Disable or remove** the `aebay-workers-loop` service in Railway.
2. Let `ebay-connector-app` own all background loops via the FastAPI startup
   hook.
3. This is already how token refresh, health checks, tasks reminders, and
   sniper workers are managed; eBay workers loop fits naturally into the same
   pattern.

Pros:
- No duplication of scheduling responsibility.
- No import/runpy edge cases.
- Monitoring is centralized: if the API is up, workers are up.

Cons:
- Background workers share the same process/container with the API
  (acceptable for most deployments, but sometimes people prefer isolation).

### Option B – Keep a standalone workers-loop service (requires refactor)

If a separate `aebay-workers-loop` service is preferred, we need to break the
import cycle and provide a clean entrypoint. For example:

1. **Stop importing `run_ebay_workers_loop` in `app.workers.__init__`**.
   - Move that import into `main.py` so the API still has access.
   - `app.workers` should not depend on `app.workers.ebay_workers_loop` at
     import time when we also want to run that module via `python -m`.
2. Alternatively, create a tiny dedicated entrypoint module, e.g.
   `app.workers.ebay_workers_entrypoint`, that does:

   ```python
   from app.workers.ebay_workers_loop import run_ebay_workers_loop
   import asyncio

   if __name__ == "__main__":
       asyncio.run(run_ebay_workers_loop())
   ```

   and configure Railway to run:

   ```bash
   python -m app.workers.ebay_workers_entrypoint
   ```

In both variants, the key is: **do not import the target loop module from a
package that itself is imported by the script runner** before `runpy` has a
chance to execute it as `__main__`.

---

## 7. Summary for a quick mental model

- The real brain of the eBay background processing is
  `run_cycle_for_all_accounts` in `app.services.ebay_workers.scheduler`.
- The long-running loop wrapper is `run_ebay_workers_loop` in
  `app.workers.ebay_workers_loop`.
- The FastAPI app (`main.py`) already starts this loop internally via
  `asyncio.create_task(run_ebay_workers_loop())` on startup.
- A separate Railway service `aebay-workers-loop` tries to run the same
  module with `python -m app.workers.ebay_workers_loop`, but due to `app.workers`
  importing that module first, the `if __name__ == "__main__"` block never
  executes and the loop never starts.
- Practically, _today_ all real eBay worker cycles are (and should be)
  started from the **main API process**, not from `aebay-workers-loop`.

If the goal is reliability and simplicity, the recommended direction is:

- **Treat `ebay_workers_loop` as an internal background loop owned by the
  main API**, remove the redundant Railway worker-loop service, and keep all
  scheduling logic in `main.py` (or, if separation is desired, introduce a
  clean, non-circular entrypoint as described in Option B).
