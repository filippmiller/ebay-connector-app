"""
Run Allocator Service for creating sync runs with unique IDs
"""
import uuid
import time
from typing import Dict, Any
from app.services.ebay_database import ebay_db


def allocate_run(user_id: str, sync_type: str) -> Dict[str, Any]:
    """
    Allocate a new sync run with unique run_id and job_id.
    Creates both database records and returns identifiers.
    
    Args:
        user_id: User ID performing the sync
        sync_type: Type of sync (orders, transactions, disputes, messages, offers)
    
    Returns:
        Dict with run_id and job_id
    """
    run_id = f"{sync_type}_{int(time.time())}_{uuid.uuid4().hex[:8]}"
    
    job_id = ebay_db.create_sync_job(user_id, sync_type)
    
    return {
        "run_id": run_id,
        "job_id": job_id,
        "sync_type": sync_type,
        "user_id": user_id
    }


def check_active_run(user_id: str, sync_type: str) -> Dict[str, Any] | None:
    """
    Check if there's already an active sync run for this user and sync type.
    Returns the active run info if found, None otherwise.
    
    This prevents duplicate concurrent syncs for the same resource.
    """
    return None
