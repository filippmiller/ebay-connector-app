#!/usr/bin/env python3
"""
Diagnostic script to check transactions worker state in the database.

Usage:
    cd backend
    python scripts/check_transactions_worker_state.py

This script reads from the database and prints diagnostic information about:
- ebay_sync_state for transactions
- Recent ebay_worker_run entries for transactions
- Token refresh log entries
- User environment settings
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone
from app.models_sqlalchemy import SessionLocal
from app.models_sqlalchemy.models import EbayAccount, EbayToken, User
from app.models_sqlalchemy.ebay_workers import (
    EbaySyncState,
    EbayWorkerRun,
    EbayTokenRefreshLog,
    EbayWorkerGlobalConfig,
)
from app.config import settings


def main():
    print("=" * 80)
    print("TRANSACTIONS WORKER STATE DIAGNOSTIC")
    print("=" * 80)
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print(f"Global settings.EBAY_ENVIRONMENT: {settings.EBAY_ENVIRONMENT}")
    print()

    db = SessionLocal()
    try:
        # 1. Check global config
        print("-" * 40)
        print("1. GLOBAL WORKER CONFIG")
        print("-" * 40)
        global_cfg = db.query(EbayWorkerGlobalConfig).first()
        if global_cfg:
            print(f"   workers_enabled: {global_cfg.workers_enabled}")
            print(f"   defaults_json: {global_cfg.defaults_json}")
        else:
            print("   No global config found (workers likely enabled by default)")
        print()

        # 2. List active accounts
        print("-" * 40)
        print("2. ACTIVE EBAY ACCOUNTS")
        print("-" * 40)
        accounts = db.query(EbayAccount).filter(EbayAccount.is_active == True).all()
        if not accounts:
            print("   No active accounts found!")
            return

        for acc in accounts:
            # Get user for this account
            user = db.query(User).filter(User.id == acc.org_id).first()
            user_env = user.ebay_environment if user else "<no_user>"
            
            # Get token
            token = db.query(EbayToken).filter(EbayToken.ebay_account_id == acc.id).first()
            token_expires = token.expires_at.isoformat() if token and token.expires_at else "<none>"
            token_refreshed = token.last_refreshed_at.isoformat() if token and token.last_refreshed_at else "<none>"
            
            print(f"   Account ID: {acc.id}")
            print(f"   eBay User ID: {acc.ebay_user_id}")
            print(f"   House Name: {acc.house_name}")
            print(f"   User (org_id): {acc.org_id}")
            print(f"   User.ebay_environment: {user_env}")
            print(f"   Token expires_at: {token_expires}")
            print(f"   Token last_refreshed_at: {token_refreshed}")
            print()

        # 3. Check sync state for transactions
        print("-" * 40)
        print("3. SYNC STATE FOR api_family='transactions'")
        print("-" * 40)
        tx_states = db.query(EbaySyncState).filter(
            EbaySyncState.api_family == "transactions"
        ).all()
        
        if not tx_states:
            print("   No transactions sync state found!")
        else:
            for state in tx_states:
                print(f"   Account: {state.ebay_account_id}")
                print(f"   Enabled: {state.enabled}")
                print(f"   Cursor Value: {state.cursor_value}")
                print(f"   Last Run At: {state.last_run_at.isoformat() if state.last_run_at else '<never>'}")
                print(f"   Last Error: {state.last_error[:200] if state.last_error else '<none>'}")
                print()
        
        # 4. Recent worker runs for transactions
        print("-" * 40)
        print("4. RECENT WORKER RUNS (transactions, last 10)")
        print("-" * 40)
        recent_runs = (
            db.query(EbayWorkerRun)
            .filter(EbayWorkerRun.api_family == "transactions")
            .order_by(EbayWorkerRun.started_at.desc())
            .limit(10)
            .all()
        )
        
        if not recent_runs:
            print("   No recent transactions runs found!")
        else:
            for run in recent_runs:
                summary = run.summary_json or {}
                error_msg = summary.get("error_message", "")[:100] if summary.get("error_message") else ""
                print(f"   Run ID: {run.id[:8]}...")
                print(f"   Status: {run.status}")
                print(f"   Started: {run.started_at.isoformat() if run.started_at else '<none>'}")
                print(f"   Finished: {run.finished_at.isoformat() if run.finished_at else '<none>'}")
                print(f"   Fetched/Stored: {summary.get('total_fetched', '?')}/{summary.get('total_stored', '?')}")
                if error_msg:
                    print(f"   Error: {error_msg}...")
                print()

        # 5. Recent token refresh logs
        print("-" * 40)
        print("5. RECENT TOKEN REFRESH LOGS (last 5)")
        print("-" * 40)
        refresh_logs = (
            db.query(EbayTokenRefreshLog)
            .order_by(EbayTokenRefreshLog.started_at.desc())
            .limit(5)
            .all()
        )
        
        if not refresh_logs:
            print("   No token refresh logs found!")
        else:
            for log in refresh_logs:
                print(f"   Account: {log.ebay_account_id}")
                print(f"   Started: {log.started_at.isoformat() if log.started_at else '<none>'}")
                print(f"   Success: {log.success}")
                print(f"   Error Code: {log.error_code or '<none>'}")
                print(f"   Triggered By: {log.triggered_by}")
                if log.error_message:
                    print(f"   Error Msg: {log.error_message[:100]}...")
                print()

        print("=" * 80)
        print("DIAGNOSTIC COMPLETE")
        print("=" * 80)

    finally:
        db.close()


if __name__ == "__main__":
    main()





