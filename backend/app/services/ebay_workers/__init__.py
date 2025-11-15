"""eBay worker services package.

This package contains services for background workers that sync data from eBay
(orders, finances, messages, trading, etc.) into Supabase/Postgres.

Key responsibilities:
- Enforce per-account + per-API locking so no two runs overlap.
- Respect per-job enable flags and the global kill-switch.
- Maintain safe cursors with overlap to avoid data loss.
- Write structured logs to ebay_api_worker_log for UI display.

Workers are *not* scheduled internally; they are invoked via HTTP endpoints in
`app.routers.ebay_workers` and can be triggered by external schedulers such as
Railway cron or Cloudflare Workers.
"""

from .scheduler import run_cycle_for_all_accounts, run_cycle_for_account
from .orders_worker import run_orders_worker_for_account
