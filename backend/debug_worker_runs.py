import os
from dotenv import load_dotenv

# Load .env from the same directory
load_dotenv()

from sqlalchemy.orm import Session
from app.models_sqlalchemy import SessionLocal
from app.models_sqlalchemy.ebay_workers import EbayWorkerRun, EbaySyncState
from datetime import datetime, timezone

def check_runs():
    db = SessionLocal()
    try:
        print("--- Active 'running' runs ---")
        runs = db.query(EbayWorkerRun).filter(EbayWorkerRun.status == "running").all()
        for run in runs:
            print(f"Run ID: {run.id}")
            print(f"  Account: {run.ebay_account_id}")
            print(f"  API: {run.api_family}")
            print(f"  Started: {run.started_at}")
            print(f"  Heartbeat: {run.heartbeat_at}")
            print(f"  Stale? {(datetime.now(timezone.utc) - run.heartbeat_at).total_seconds() / 60 > 10}")
            print("-" * 20)

        print("\n--- Sync State for stuck workers ---")
        stuck_apis = ["cases", "finances", "inquiries", "returns"]
        states = db.query(EbaySyncState).filter(EbaySyncState.api_family.in_(stuck_apis)).all()
        for state in states:
            print(f"API: {state.api_family}")
            print(f"  Account: {state.ebay_account_id}")
            print(f"  Enabled: {state.enabled}")
            print(f"  Last Run: {state.last_run_at}")
            print(f"  Last Error: {state.last_error}")
            print(f"  Cursor: {state.cursor_value}")
            print("-" * 20)

    finally:
        db.close()

if __name__ == "__main__":
    check_runs()
