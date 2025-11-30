"""
Background Workers for eBay Connector

This module contains background workers that run periodically to maintain
the health and functionality of eBay account connections.

Workers:
- token_refresh_worker: Runs every 10 minutes to refresh tokens expiring within 5 minutes
- health_check_worker: Runs every 15 minutes to verify all account connections are healthy
"""

from app.workers.token_refresh_worker import refresh_expiring_tokens, run_token_refresh_worker_loop
from app.workers.health_check_worker import run_all_health_checks, run_health_check_worker_loop
from app.workers.ebay_workers_loop import run_ebay_workers_loop, run_ebay_workers_once
from app.workers.tasks_reminder_worker import run_tasks_reminder_worker_loop
from app.workers.sniper_executor import run_sniper_loop
# NOTE: The ebay_monitor_worker currently depends on app.config.worker_settings,
# which is not part of this project. Importing it at module import time causes
# ModuleNotFoundError when any worker module is executed with `-m app.workers.*`.
# To keep the token refresh + ebay workers loops usable in production, we do
# NOT import run_monitoring_loop here. It can be wired back in once
# worker_settings is available.
# from app.workers.ebay_monitor_worker import run_monitoring_loop
# NOTE: Several auxiliary workers (auto_offer_buy, ebay_monitor, etc.) depend
# on optional configuration modules such as app.config.worker_settings that are
# not always present. Import them lazily so that core loops (token refresh,
# ebay data workers) can run even when those optional pieces are missing.
try:  # pragma: no cover - defensive import
    from app.workers.auto_offer_buy_worker import run_auto_offer_buy_loop  # type: ignore
except Exception:  # pragma: no cover
    run_auto_offer_buy_loop = None  # type: ignore[arg-type]

from app.workers.gmail_sync_worker import run_gmail_sync_loop, run_gmail_sync_once
from app.workers.db_migration_worker import run_db_migration_workers_loop
from app.workers.ebay_search_watch_worker import run_search_watch_loop

__all__ = [
    "refresh_expiring_tokens",
    "run_token_refresh_worker_loop",
    "run_all_health_checks",
    "run_health_check_worker_loop",
    "run_ebay_workers_loop",
    "run_ebay_workers_once",
    "run_tasks_reminder_worker_loop",
    "run_sniper_loop",
    # "run_monitoring_loop",  # temporarily disabled (requires app.config.worker_settings)
    "run_auto_offer_buy_loop",
    "run_gmail_sync_loop",
    "run_gmail_sync_once",
    "run_db_migration_workers_loop",
    "run_search_watch_loop",
]
