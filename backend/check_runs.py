from dotenv import load_dotenv
import os
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))
from app.models_sqlalchemy import SessionLocal
from app.models_sqlalchemy.ebay_workers import EbayWorkerRun
from sqlalchemy import desc
from datetime import datetime, timedelta

db = SessionLocal()
try:
    print("--- Recent Worker Runs ---")
    runs = db.query(EbayWorkerRun).order_by(desc(EbayWorkerRun.started_at)).limit(20).all()
    for run in runs:
        print(f"ID: {run.id} | Account: {run.ebay_account_id} | API: {run.api_family} | Status: {run.status} | Started: {run.started_at} | Finished: {run.finished_at}")

    print("\n--- Stale Running Jobs ---")
    cutoff = datetime.utcnow() - timedelta(minutes=15)
    stale_runs = db.query(EbayWorkerRun).filter(EbayWorkerRun.status == 'running', EbayWorkerRun.heartbeat_at < cutoff).all()
    for run in stale_runs:
        print(f"STALE ID: {run.id} | Account: {run.ebay_account_id} | API: {run.api_family} | Started: {run.started_at} | Heartbeat: {run.heartbeat_at}")

finally:
    db.close()
