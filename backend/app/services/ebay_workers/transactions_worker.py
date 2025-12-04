from __future__ import annotations

import os
from typing import Optional, Any, Dict

from sqlalchemy.orm import Session

from app.models_sqlalchemy.models import EbayAccount, EbayToken, User
from app.services.ebay import EbayService
from app.utils.logger import logger
from app.config import settings
from .base_worker import BaseWorker


# Diagnostic flag - set EBAY_DEBUG_TRANSACTIONS=1 to enable verbose logging
_DEBUG_TRANSACTIONS = os.getenv("EBAY_DEBUG_TRANSACTIONS", "0") == "1"


class TransactionsWorker(BaseWorker):
    def __init__(self):
        super().__init__(
            api_family="transactions",
            overlap_minutes=30,
            initial_backfill_days=90,
            limit=200,
        )

    async def execute_sync(
        self,
        db: Session,
        account: EbayAccount,
        token: EbayToken,
        run_id: str,
        sync_run_id: str,
        window_from: Optional[str],
        window_to: Optional[str],
    ) -> Dict[str, Any]:
        ebay_service = EbayService()
        user_id = account.org_id

        # Fetch user to get environment
        user = db.query(User).filter(User.id == user_id).first()
        environment = user.ebay_environment if user else "sandbox"

        # Determine mode from triggered_by
        # Map triggered_by to mode: "manual" -> "manual", "scheduler" -> "automatic", "internal_scheduler" -> "automatic"
        triggered_by = getattr(self, '_triggered_by', 'unknown')
        if triggered_by == "manual":
            mode = "manual"
        elif triggered_by in ("scheduler", "internal_scheduler"):
            mode = "automatic"
        else:
            mode = "unknown"
        
        # Use sync_run_id as correlation_id for tracking this specific run
        correlation_id = sync_run_id

        # Diagnostic logging
        if _DEBUG_TRANSACTIONS:
            token_value = token.access_token
            token_prefix = token_value[:20] if token_value else "<none>"
            is_encrypted = token_value.startswith("ENC:") if token_value else False
            logger.info(
                "[TRANSACTIONS_WORKER_DEBUG] account_id=%s ebay_user_id=%s user_id=%s "
                "user.ebay_environment=%s resolved_environment=%s "
                "settings.EBAY_ENVIRONMENT=%s token_prefix=%s... token_encrypted=%s "
                "window_from=%s window_to=%s mode=%s correlation_id=%s",
                account.id,
                account.ebay_user_id,
                user_id,
                user.ebay_environment if user else "<no_user>",
                environment,
                settings.EBAY_ENVIRONMENT,
                token_prefix,
                is_encrypted,
                window_from,
                window_to,
                mode,
                correlation_id,
            )
            
            # CRITICAL: Warn if token is still encrypted at this point
            if is_encrypted:
                logger.error(
                    "[TRANSACTIONS_WORKER_DEBUG] ⚠️ TOKEN STILL ENCRYPTED! "
                    "account_id=%s token_prefix=%s... This will cause 401 errors!",
                    account.id, token_prefix
                )

        # Always log key environment info at INFO level for observability
        logger.info(
            "[transactions_worker] Starting sync for account=%s environment=%s (global=%s) mode=%s correlation_id=%s",
            account.id,
            environment,
            settings.EBAY_ENVIRONMENT,
            mode,
            correlation_id,
        )

        result = await ebay_service.sync_all_transactions(
            user_id=user_id,
            access_token=token.access_token,
            run_id=sync_run_id,
            ebay_account_id=account.id,
            ebay_user_id=account.ebay_user_id,
            window_from=window_from,
            window_to=window_to,
            environment=environment,
            mode=mode,
            correlation_id=correlation_id,
        )

        # Log success/failure summary
        total_fetched = result.get("total_fetched", 0)
        total_stored = result.get("total_stored", 0)
        error_msg = result.get("error_message") or result.get("error")
        if error_msg:
            logger.warning(
                "[transactions_worker] Completed with error for account=%s: fetched=%s stored=%s error=%s",
                account.id, total_fetched, total_stored, error_msg[:200] if error_msg else None,
            )
        else:
            logger.info(
                "[transactions_worker] Completed successfully for account=%s: fetched=%s stored=%s",
                account.id, total_fetched, total_stored,
            )

        return result


async def run_transactions_worker_for_account(
    ebay_account_id: str,
    triggered_by: str = "unknown",
) -> Optional[str]:
    """Run Transactions sync worker for a specific eBay account.
    
    Args:
        ebay_account_id: UUID of the eBay account
        triggered_by: How this run was triggered ("manual", "scheduler", or "unknown")
    """
    worker = TransactionsWorker()
    return await worker.run_for_account(ebay_account_id, triggered_by=triggered_by)


async def run_transactions_sync_for_all_accounts(
    triggered_by: str = "internal_scheduler",
) -> Dict[str, Any]:
    """Run Transactions sync for ALL active eBay accounts.
    
    This is the unified entry point for both manual "Run Now" and automatic
    worker loop. It ensures consistent token handling and logging.
    
    Args:
        triggered_by: Label for logging ("manual", "scheduler", "internal_scheduler")
    
    Returns:
        Dict with summary: accounts_processed, accounts_succeeded, accounts_failed, details
    """
    from app.models_sqlalchemy import SessionLocal
    from app.models_sqlalchemy.models import EbayAccount
    from app.models_sqlalchemy.ebay_workers import EbaySyncState
    from app.services.ebay_workers.state import are_workers_globally_enabled, get_or_create_sync_state
    from datetime import datetime, timezone
    import hashlib
    
    started_at = datetime.now(timezone.utc)
    correlation_id = hashlib.sha256(f"txn_sync_{started_at.isoformat()}".encode()).hexdigest()[:12]
    
    logger.info(
        "[transactions_sync_all] Starting sync for all accounts triggered_by=%s correlation_id=%s",
        triggered_by, correlation_id
    )
    
    db = SessionLocal()
    results = {
        "correlation_id": correlation_id,
        "started_at": started_at.isoformat(),
        "triggered_by": triggered_by,
        "accounts_processed": 0,
        "accounts_succeeded": 0,
        "accounts_failed": 0,
        "accounts_skipped": 0,
        "details": [],
    }
    
    try:
        # Check global workers enabled
        if not are_workers_globally_enabled(db):
            logger.info(
                "[transactions_sync_all] Workers globally disabled - skipping correlation_id=%s",
                correlation_id
            )
            results["status"] = "skipped"
            results["reason"] = "workers_globally_disabled"
            return results
        
        # Get all active accounts
        accounts = db.query(EbayAccount).filter(EbayAccount.is_active == True).all()
        if not accounts:
            logger.info(
                "[transactions_sync_all] No active accounts found correlation_id=%s",
                correlation_id
            )
            results["status"] = "ok"
            results["reason"] = "no_active_accounts"
            return results
        
        logger.info(
            "[transactions_sync_all] Found %d active accounts correlation_id=%s",
            len(accounts), correlation_id
        )
        
        for account in accounts:
            account_id = account.id
            account_result = {
                "account_id": account_id,
                "house_name": account.house_name,
                "ebay_user_id": account.ebay_user_id,
            }
            
            # Check if transactions worker is enabled for this account
            state = db.query(EbaySyncState).filter(
                EbaySyncState.ebay_account_id == account_id,
                EbaySyncState.api_family == "transactions",
            ).first()
            
            if not state:
                # Create state if not exists
                state = get_or_create_sync_state(
                    db,
                    ebay_account_id=account_id,
                    ebay_user_id=account.ebay_user_id or "unknown",
                    api_family="transactions",
                )
            
            if not state.enabled:
                logger.info(
                    "[transactions_sync_all] Worker disabled for account=%s correlation_id=%s",
                    account_id, correlation_id
                )
                account_result["status"] = "skipped"
                account_result["reason"] = "worker_disabled"
                results["accounts_skipped"] += 1
                results["details"].append(account_result)
                continue
            
            # Run the transactions worker for this account
            try:
                run_id = await run_transactions_worker_for_account(
                    account_id,
                    triggered_by=triggered_by,
                )
                
                results["accounts_processed"] += 1
                
                if run_id:
                    account_result["status"] = "started"
                    account_result["run_id"] = run_id
                    results["accounts_succeeded"] += 1
                    logger.info(
                        "[transactions_sync_all] Worker started for account=%s run_id=%s correlation_id=%s",
                        account_id, run_id, correlation_id
                    )
                else:
                    account_result["status"] = "skipped"
                    account_result["reason"] = "already_running_or_no_token"
                    results["accounts_skipped"] += 1
                    logger.info(
                        "[transactions_sync_all] Worker skipped for account=%s (already running or no token) correlation_id=%s",
                        account_id, correlation_id
                    )
                    
            except Exception as e:
                error_msg = str(e)[:200]
                account_result["status"] = "error"
                account_result["error"] = error_msg
                results["accounts_failed"] += 1
                results["accounts_processed"] += 1
                logger.error(
                    "[transactions_sync_all] Worker failed for account=%s error=%s correlation_id=%s",
                    account_id, error_msg, correlation_id,
                    exc_info=True,
                )
            
            results["details"].append(account_result)
        
        finished_at = datetime.now(timezone.utc)
        results["finished_at"] = finished_at.isoformat()
        results["duration_ms"] = int((finished_at - started_at).total_seconds() * 1000)
        results["status"] = "ok"
        
        logger.info(
            "[transactions_sync_all] Completed: processed=%d succeeded=%d failed=%d skipped=%d "
            "duration_ms=%d correlation_id=%s",
            results["accounts_processed"],
            results["accounts_succeeded"],
            results["accounts_failed"],
            results["accounts_skipped"],
            results["duration_ms"],
            correlation_id,
        )
        
        return results
        
    except Exception as e:
        error_msg = str(e)
        logger.error(
            "[transactions_sync_all] Fatal error: %s correlation_id=%s",
            error_msg, correlation_id,
            exc_info=True,
        )
        results["status"] = "error"
        results["error"] = error_msg
        return results
        
    finally:
        db.close()
