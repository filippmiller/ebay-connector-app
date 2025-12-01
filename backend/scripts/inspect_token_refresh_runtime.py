"""Inspect token refresh logs and worker heartbeat (read-only).

Usage (from backend/ directory with DATABASE_URL configured):

    python -m scripts.inspect_token_refresh_runtime

This prints, for each EbayAccount:
- last N EbayTokenRefreshLog rows (success/error, error_code, triggered_by)

And then prints the BackgroundWorker row for the token_refresh_worker.
"""
from __future__ import annotations

from typing import Optional

from app.models_sqlalchemy import get_db
from app.models_sqlalchemy.models import EbayAccount
from app.models_sqlalchemy.ebay_workers import EbayTokenRefreshLog, BackgroundWorker


def main(limit_per_account: int = 5) -> None:
    session = next(get_db())
    try:
        accounts = session.query(EbayAccount).order_by(EbayAccount.house_name.asc()).all()
        print(f"Found {len(accounts)} ebay_accounts\n")

        for acc in accounts:
            print("Account:")
            print(f"  id         : {acc.id}")
            print(f"  house_name : {acc.house_name}")
            print(f"  ebay_user  : {acc.ebay_user_id}")
            print("")

            logs = (
                session.query(EbayTokenRefreshLog)
                .filter(EbayTokenRefreshLog.ebay_account_id == acc.id)
                .order_by(EbayTokenRefreshLog.started_at.desc())
                .limit(limit_per_account)
                .all()
            )
            if not logs:
                print("  No token refresh logs found.\n")
                continue

            print(f"  Last {len(logs)} token refresh attempts:")
            for row in logs:
                print(f"    id            : {row.id}")
                print(f"    started_at    : {row.started_at}")
                print(f"    finished_at   : {row.finished_at}")
                print(f"    success       : {row.success}")
                print(f"    triggered_by  : {row.triggered_by}")
                print(f"    error_code    : {row.error_code}")
                print(f"    error_message : {row.error_message}")
                print(f"    old_expires_at: {row.old_expires_at}")
                print(f"    new_expires_at: {row.new_expires_at}")
                print("")

        print("\nBackground worker heartbeat (token_refresh_worker):\n")
        worker: Optional[BackgroundWorker] = (
            session.query(BackgroundWorker)
            .filter(BackgroundWorker.worker_name == "token_refresh_worker")
            .one_or_none()
        )
        if worker is None:
            print("  No BackgroundWorker row found for token_refresh_worker.")
        else:
            print(f"  worker_name       : {worker.worker_name}")
            print(f"  interval_seconds  : {worker.interval_seconds}")
            print(f"  last_started_at   : {worker.last_started_at}")
            print(f"  last_finished_at  : {worker.last_finished_at}")
            print(f"  last_status       : {worker.last_status}")
            print(f"  last_error_message: {worker.last_error_message}")
            print(f"  runs_ok_in_row    : {worker.runs_ok_in_row}")
            print(f"  runs_error_in_row : {worker.runs_error_in_row}")

    finally:
        session.close()


if __name__ == "__main__":  # pragma: no cover - manual diagnostic
    main()