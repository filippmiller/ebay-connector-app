#!/usr/bin/env python3
"""
One-shot script to run the transactions worker for a specific account.

This simulates what the background scheduler does, but for a single account
and a single API family (transactions).

Usage:
    cd backend
    
    # Run with diagnostic logging enabled:
    EBAY_DEBUG_TRANSACTIONS=1 python scripts/run_transactions_worker_once.py [account_id]
    
    # Run without extra logging:
    python scripts/run_transactions_worker_once.py [account_id]

If account_id is not provided, it will use the first active account found.
"""

import sys
import os
import asyncio

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone
from app.models_sqlalchemy import SessionLocal
from app.models_sqlalchemy.models import EbayAccount
from app.services.ebay_workers.transactions_worker import run_transactions_worker_for_account
from app.services.ebay_token_refresh_service import run_token_refresh_job
from app.utils.logger import logger
from app.config import settings


async def main():
    print("=" * 80)
    print("TRANSACTIONS WORKER ONE-SHOT RUN")
    print("=" * 80)
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print(f"EBAY_DEBUG_TRANSACTIONS: {os.getenv('EBAY_DEBUG_TRANSACTIONS', '0')}")
    print(f"settings.EBAY_ENVIRONMENT: {settings.EBAY_ENVIRONMENT}")
    print()

    db = SessionLocal()
    
    try:
        # Determine which account to use
        account_id = None
        if len(sys.argv) > 1:
            account_id = sys.argv[1]
            print(f"Using provided account_id: {account_id}")
        else:
            # Find first active account
            account = db.query(EbayAccount).filter(EbayAccount.is_active == True).first()
            if account:
                account_id = account.id
                print(f"Using first active account: {account_id} ({account.house_name})")
            else:
                print("ERROR: No active accounts found!")
                return

        print()
        print("-" * 40)
        print("STEP 1: Token Refresh (like scheduler does)")
        print("-" * 40)
        
        # Run token refresh first, like the scheduler does
        refresh_result = await run_token_refresh_job(db, force_all=False, triggered_by="manual_test")
        print(f"Token refresh result: {refresh_result}")
        print()

        print("-" * 40)
        print("STEP 2: Run Transactions Worker")
        print("-" * 40)
        
        # Run the transactions worker
        run_id = await run_transactions_worker_for_account(account_id)
        
        if run_id:
            print(f"Worker completed with run_id: {run_id}")
        else:
            print("Worker returned None (may be disabled, already running, or no token)")

        print()
        print("-" * 40)
        print("STEP 3: Check Result in DB")
        print("-" * 40)
        
        # Refresh the session to get latest data
        db.expire_all()
        
        from app.models_sqlalchemy.ebay_workers import EbaySyncState, EbayWorkerRun
        
        # Check sync state
        state = db.query(EbaySyncState).filter(
            EbaySyncState.ebay_account_id == account_id,
            EbaySyncState.api_family == "transactions",
        ).first()
        
        if state:
            print(f"Sync State:")
            print(f"  cursor_value: {state.cursor_value}")
            print(f"  last_run_at: {state.last_run_at}")
            print(f"  last_error: {state.last_error[:200] if state.last_error else '<none>'}")
        
        # Check the run entry
        if run_id:
            run = db.query(EbayWorkerRun).filter(EbayWorkerRun.id == run_id).first()
            if run:
                print(f"\nWorker Run:")
                print(f"  status: {run.status}")
                print(f"  started_at: {run.started_at}")
                print(f"  finished_at: {run.finished_at}")
                summary = run.summary_json or {}
                print(f"  total_fetched: {summary.get('total_fetched', '?')}")
                print(f"  total_stored: {summary.get('total_stored', '?')}")
                if summary.get('error_message'):
                    print(f"  error_message: {summary['error_message'][:200]}")

        print()
        print("=" * 80)
        print("ONE-SHOT RUN COMPLETE")
        print("=" * 80)

    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())





