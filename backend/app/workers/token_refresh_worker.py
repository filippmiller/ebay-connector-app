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

        accounts = ebay_account_service.get_accounts_needing_refresh(db, threshold_minutes=5)

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
            token = None
            refresh_log: Optional[EbayTokenRefreshLog] = None
            try:
                token = ebay_account_service.get_token(db, account.id)

                # Create a refresh log row early so even "no refresh token" cases
                # have a traceable entry.
                start_ts = datetime.now(timezone.utc)
                old_expires_at = getattr(token, "expires_at", None)
                refresh_log = EbayTokenRefreshLog(
                    id=str(uuid.uuid4()),
                    ebay_account_id=account.id,
                    started_at=start_ts,
                    old_expires_at=old_expires_at,
                    triggered_by="scheduled",
                )
                db.add(refresh_log)
                db.flush()

                if not token or not token.refresh_token:
                    logger.warning(
                        "Account %s (%s) has no refresh token", account.id, account.house_name
                    )
                    if refresh_log is not None:
                        refresh_log.success = False
                        refresh_log.error_code = "NO_REFRESH_TOKEN"
                        refresh_log.error_message = "No refresh token available"
                        refresh_log.finished_at = datetime.now(timezone.utc)
                    errors.append(
                        {
                            "account_id": account.id,
                            "house_name": account.house_name,
                            "error": "No refresh token available",
                        }
                    )
                    db.commit()
                    continue

                logger.info(
                    "Refreshing token for account %s (%s)", account.id, account.house_name
                )

                # Use org_id as the logical user_id for connect logs
                org_id = getattr(account, "org_id", None)
                env = settings.EBAY_ENVIRONMENT or "sandbox"

                new_token_data = await ebay_service.refresh_access_token(
                    token.refresh_token,
                    user_id=org_id,
                    environment=env,
                )

                # Defensive log: type and public attributes only (no secrets)
                try:
                    attrs = [a for a in dir(new_token_data) if not a.startswith("_")]
                    logger.info(
                        "Token refresh response: type=%s, attrs=%s, has_refresh=%s",
                        type(new_token_data).__name__,
                        attrs,
                        bool(getattr(new_token_data, "refresh_token", None)),
                    )
                except Exception:  # pragma: no cover - defensive
                    logger.debug("Could not introspect token refresh response")

                ebay_account_service.save_tokens(
                    db,
                    account.id,
                    new_token_data.access_token,
                    getattr(new_token_data, "refresh_token", None) or token.refresh_token,
                    new_token_data.expires_in,
                )

                refreshed_count += 1
                logger.info(
                    "Successfully refreshed token for account %s (%s)",
                    account.id,
                    account.house_name,
                )

                if refresh_log is not None:
                    finished_ts = datetime.now(timezone.utc)
                    refresh_log.success = True
                    refresh_log.finished_at = finished_ts
                    try:
                        # Mirror EbayAccountService.save_tokens expiry computation.
                        refresh_log.new_expires_at = finished_ts + timedelta(
                            seconds=int(getattr(new_token_data, "expires_in", 0) or 0)
                        )
                    except Exception:  # pragma: no cover - defensive
                        refresh_log.new_expires_at = None
                    db.commit()

            except Exception as e:  # noqa: BLE001
                error_msg = str(e)
                logger.error(
                    "Failed to refresh token for account %s (%s): %s",
                    account.id,
                    account.house_name,
                    error_msg,
                )

                if token:
                    token.refresh_error = error_msg
                    db.commit()

                if refresh_log is None:
                    # Ensure we still capture an entry even if we failed early.
                    refresh_log = EbayTokenRefreshLog(
                        id=str(uuid.uuid4()),
                        ebay_account_id=account.id,
                        started_at=datetime.now(timezone.utc),
                        triggered_by="scheduled",
                    )
                    db.add(refresh_log)

                refresh_log.success = False
                refresh_log.error_message = error_msg[:2000]
                # Try to capture a short error code when possible.
                status_code = getattr(e, "status_code", None)
                if status_code is not None:
                    refresh_log.error_code = str(status_code)
                refresh_log.finished_at = datetime.now(timezone.utc)
                db.commit()

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
