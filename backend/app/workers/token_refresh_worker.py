"""
Token Refresh Worker
Runs every 10 minutes to check for tokens expiring within 5 minutes and refreshes them.

This module also records structured observability data so the admin UI can see
when the worker last ran and how individual token refresh attempts behaved.
"""
import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models_sqlalchemy.ebay_workers import BackgroundWorker, EbayTokenRefreshLog
from app.services.ebay_account_service import ebay_account_service
from app.services.ebay import ebay_service
from app.services.ebay_token_refresh_service import refresh_access_token_for_account
from app.utils.logger import logger

WORKER_NAME = "token_refresh_worker"
WORKER_INTERVAL_SECONDS = 600  # 10 minutes


def _get_or_create_worker_row(db: Session) -> BackgroundWorker:
    """Fetch or create the BackgroundWorker row for this worker.

    We keep this logic local to avoid duplicating it across modules and to make
    the worker resilient even if the row is missing for any reason.
    """

    worker: Optional[BackgroundWorker] = (
        db.query(BackgroundWorker)
        .filter(BackgroundWorker.worker_name == WORKER_NAME)
        .one_or_none()
    )
    if worker is None:
        worker = BackgroundWorker(
            id=str(uuid.uuid4()),
            worker_name=WORKER_NAME,
            interval_seconds=WORKER_INTERVAL_SECONDS,
        )
        db.add(worker)
        db.commit()
        db.refresh(worker)
    return worker


async def refresh_expiring_tokens():
    """
    Check for tokens expiring within 5 minutes and refresh them.
    This should be called every 10 minutes.
    """
    logger.info("Starting token refresh worker...")

    db = next(get_db())
    worker_status = "error"
    worker_error_message: Optional[str] = None

    # Best-effort heartbeat so Admin UI can see if the loop is alive.
    try:
        worker_row = _get_or_create_worker_row(db)
    except Exception as hb_exc:  # pragma: no cover - defensive
        logger.error("Failed to load/create BackgroundWorker row: %s", hb_exc)
        worker_row = None

    try:
        now_utc = datetime.now(timezone.utc)
        if worker_row is not None:
            worker_row.last_started_at = now_utc
            worker_row.last_status = "running"
            worker_row.last_error_message = None
            db.commit()

        accounts = ebay_account_service.get_accounts_needing_refresh(
            db,
            threshold_minutes=15,
            max_age_minutes=60,
        )

        if not accounts:
            logger.info("No accounts need token refresh")
            worker_status = "ok"
            return {
                "status": "completed",
                "accounts_checked": 0,
                "accounts_refreshed": 0,
                "errors": [],
            }

        logger.info(f"Found {len(accounts)} accounts needing token refresh")

        refreshed_count = 0
        errors = []

        for account in accounts:
            try:
                logger.info(
                    "[token-refresh-worker] Refreshing token for account %s (%s)",
                    account.id,
                    account.house_name,
                )

                result = await refresh_access_token_for_account(
                    db,
                    account,
                    triggered_by="scheduled",
                    persist=True,
                    capture_http=False,
                )

                success = bool(result.get("success"))
                error_msg = result.get("error_message") or result.get("error") or "unknown_error"

                if success:
                    refreshed_count += 1
                    logger.info(
                        "[token-refresh-worker] SUCCESS account=%s house=%s",
                        account.id,
                        account.house_name,
                    )
                else:
                    logger.warning(
                        "[token-refresh-worker] FAILURE account=%s house=%s ebay_user_id=%s error=%s",
                        account.id,
                        account.house_name,
                        getattr(account, "ebay_user_id", None),
                        error_msg,
                    )
                    # Detect hard 4xx-style errors (e.g. invalid_grant) on already
                    # expired tokens so we can surface a clear reconnect signal in
                    # logs/alerts.
                    try:
                        from app.models_sqlalchemy.models import EbayToken  # local import to avoid cycles

                        token = (
                            db.query(EbayToken)
                            .filter(EbayToken.ebay_account_id == account.id)
                            .order_by(EbayToken.updated_at.desc())
                            .first()
                        )
                    except Exception:  # pragma: no cover - defensive
                        token = None

                    is_expired = False
                    if token and getattr(token, "expires_at", None) is not None:
                        try:
                            expires_at = token.expires_at
                            if expires_at.tzinfo is None:
                                expires_at = expires_at.replace(tzinfo=timezone.utc)
                            now_local = datetime.now(timezone.utc)
                            is_expired = expires_at <= now_local
                        except Exception:  # pragma: no cover - defensive
                            is_expired = False

                    err_lower = (str(error_msg) or "").lower()
                    looks_like_4xx = "invalid_grant" in err_lower or "400" in err_lower

                    if is_expired and looks_like_4xx:
                        logger.critical(
                            "[token-refresh-worker] CRITICAL: token EXPIRED and REFRESH FAILED for account %s (%s, ebay_user_id=%s) with what looks like a 4xx from eBay (e.g. invalid_grant). Manual reconnect required.",
                            account.id,
                            account.house_name,
                            getattr(account, "ebay_user_id", None),
                        )

                    errors.append(
                        {
                            "account_id": account.id,
                            "house_name": account.house_name,
                            "error": error_msg,
                        }
                    )

            except Exception as e:  # noqa: BLE001
                error_msg = str(e)
                logger.error(
                    "[token-refresh-worker] Exception refreshing token for account %s (%s): %s",
                    account.id,
                    account.house_name,
                    error_msg,
                )

                errors.append(
                    {
                        "account_id": account.id,
                        "house_name": account.house_name,
                        "error": error_msg,
                    }
                )

        logger.info(
            "Token refresh worker completed: %s/%s accounts refreshed",
            refreshed_count,
            len(accounts),
        )
        worker_status = "ok"

        return {
            "status": "completed",
            "accounts_checked": len(accounts),
            "accounts_refreshed": refreshed_count,
            "errors": errors,
            "timestamp": datetime.utcnow().isoformat(),
        }

    except Exception as e:  # noqa: BLE001
        worker_error_message = str(e)
        logger.error("Token refresh worker failed: %s", worker_error_message)
        return {
            "status": "error",
            "error": worker_error_message,
            "timestamp": datetime.utcnow().isoformat(),
        }
    finally:
        try:
            if worker_row is not None:
                finished = datetime.now(timezone.utc)
                worker_row.last_finished_at = finished
                worker_row.last_status = worker_status
                if worker_status == "ok":
                    worker_row.runs_ok_in_row = (worker_row.runs_ok_in_row or 0) + 1
                    worker_row.runs_error_in_row = 0
                else:
                    worker_row.runs_error_in_row = (worker_row.runs_error_in_row or 0) + 1
                    if worker_error_message:
                        worker_row.last_error_message = worker_error_message[:2000]
                db.commit()
        except Exception as hb_exc:  # pragma: no cover - defensive
            logger.error("Failed to update background worker heartbeat: %s", hb_exc)
        finally:
            db.close()


async def run_token_refresh_worker_loop():
    """
    Run the token refresh worker in a loop every 10 minutes.
    This is the main entry point for the background worker.
    """
    logger.info("Token refresh worker loop started")
    
    while True:
        try:
            result = await refresh_expiring_tokens()
            logger.info(f"Token refresh cycle completed: {result}")
        except Exception as e:
            logger.error(f"Token refresh worker loop error: {str(e)}")
        
        await asyncio.sleep(600)


if __name__ == "__main__":
    asyncio.run(run_token_refresh_worker_loop())
