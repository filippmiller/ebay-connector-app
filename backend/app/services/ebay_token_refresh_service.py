from __future__ import annotations

"""Centralised helpers for refreshing eBay OAuth tokens for an account.

This module encapsulates the end-to-end flow used by:
- the background token refresh worker,
- the admin debug refresh endpoint,
- any future manual "force refresh" admin actions.

The flow is:
    load EbayToken -> decrypt refresh_token (via model property)
    -> call eBay Identity API /oauth2/token
    -> on success, persist new tokens and expiry
    -> write EbayTokenRefreshLog row with success/error and new_expires_at.

When capture_http=True, the helper will also return the raw HTTP
request/response shape produced by EbayService.debug_refresh_access_token_http,
which the Admin UI can render in a terminal-like view.
"""

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
from app.models_sqlalchemy.models import EbayAccount, EbayToken
from app.models_sqlalchemy.ebay_workers import EbayTokenRefreshLog
from app.services.ebay_account_service import ebay_account_service
from app.services.ebay import ebay_service
from app.utils.logger import logger


async def refresh_access_token_for_account(
    db: Session,
    account: EbayAccount,
    *,
    triggered_by: str = "scheduled",
    persist: bool = True,
    capture_http: bool = False,
) -> Dict[str, Any]:
    """Refresh OAuth tokens for a single EbayAccount.

    Parameters
    ----------
    db:
        SQLAlchemy session.
    account:
        EbayAccount ORM instance whose tokens should be refreshed.
    triggered_by:
        Short label stored on EbayTokenRefreshLog.triggered_by.
        Examples: "scheduled", "debug", "admin", "manual".
    persist:
        When True, persist new access/refresh tokens + expiry into EbayToken.
    capture_http:
        When True, the helper will perform the refresh via
        ebay_service.debug_refresh_access_token_http and include the raw HTTP
        request/response details in the returned dict under the "http" key.

    Returns
    -------
    dict with at least:
        success: bool
        error: Optional[str]
        error_message: Optional[str]
        http: Optional[dict]  # present when capture_http=True
    """

    now = datetime.now(timezone.utc)

    token: Optional[EbayToken] = (
        db.query(EbayToken)
        .filter(EbayToken.ebay_account_id == account.id)
        .first()
    )

    # Create a refresh log row early so that even "no refresh token" cases
    # have a traceable entry.
    refresh_log = EbayTokenRefreshLog(
        id=str(uuid.uuid4()),
        ebay_account_id=account.id,
        started_at=now,
        old_expires_at=getattr(token, "expires_at", None),
        triggered_by=triggered_by,
    )
    db.add(refresh_log)
    db.flush()

    if not token or not token.refresh_token:
        msg = "No refresh token available"
        logger.warning("Account %s (%s) has no refresh token", account.id, account.house_name)

        refresh_log.success = False
        refresh_log.error_code = "NO_REFRESH_TOKEN"
        refresh_log.error_message = msg
        refresh_log.finished_at = datetime.now(timezone.utc)

        if token is not None:
            token.refresh_error = msg

        db.commit()
        return {
            "success": False,
            "error": "no_refresh_token",
            "error_message": msg,
            "http": None,
        }

    env = settings.EBAY_ENVIRONMENT or "sandbox"

    # Decide which low-level helper to use.
    # - capture_http=False -> use refresh_access_token (returns EbayTokenResponse)
    # - capture_http=True  -> use debug_refresh_access_token_http (returns
    #                        raw HTTP request/response details only)
    try:
        if capture_http:
            debug_payload = await ebay_service.debug_refresh_access_token_http(
                token.refresh_token,
                environment=env,
            )

            success = bool(debug_payload.get("success"))
            error: Optional[str] = debug_payload.get("error")
            error_description: Optional[str] = debug_payload.get("error_description")

            if not success:
                msg = error_description or error or "Token refresh failed"
                logger.error(
                    "Token refresh debug for account %s (%s) failed: %s",
                    account.id,
                    account.house_name,
                    msg,
                )

                refresh_log.success = False
                refresh_log.error_code = error or "debug_error"
                refresh_log.error_message = msg[:2000]
                refresh_log.finished_at = datetime.now(timezone.utc)

                token.refresh_error = msg
                db.commit()

                return {
                    "success": False,
                    "error": error or "debug_error",
                    "error_message": msg,
                    "http": debug_payload,
                }

            # Parse token payload from HTTP response body.
            resp = debug_payload.get("response") or {}
            body_text = resp.get("body") or ""
            try:
                token_data = json.loads(body_text) if body_text else {}
            except Exception:
                token_data = {}

            access_token = token_data.get("access_token")
            expires_in = token_data.get("expires_in")
            new_refresh_token = token_data.get("refresh_token")
            refresh_token_expires_in = token_data.get("refresh_token_expires_in")

            if not access_token or not isinstance(expires_in, (int, float)):
                msg = "Token refresh debug succeeded but response is missing access_token/expires_in"
                logger.error(
                    "Account %s (%s): %s. Raw body length=%s",
                    account.id,
                    account.house_name,
                    msg,
                    len(body_text),
                )
                refresh_log.success = False
                refresh_log.error_code = "invalid_response"
                refresh_log.error_message = msg[:2000]
                refresh_log.finished_at = datetime.now(timezone.utc)
                token.refresh_error = msg
                db.commit()
                return {
                    "success": False,
                    "error": "invalid_response",
                    "error_message": msg,
                    "http": debug_payload,
                }

            # Persist tokens if requested.
            if persist:
                ebay_account_service.save_tokens(
                    db,
                    account.id,
                    access_token=access_token,
                    refresh_token=new_refresh_token or token.refresh_token,
                    expires_in=int(expires_in),
                    refresh_token_expires_in=int(refresh_token_expires_in)
                    if isinstance(refresh_token_expires_in, (int, float))
                    else None,
                )
                # Reload token so we can capture the updated expires_at.
                token = ebay_account_service.get_token(db, account.id) or token

            finished = datetime.now(timezone.utc)
            refresh_log.success = True
            refresh_log.finished_at = finished
            try:
                if getattr(token, "expires_at", None) is not None:
                    refresh_log.new_expires_at = token.expires_at
                else:
                    refresh_log.new_expires_at = finished + timedelta(
                        seconds=int(expires_in),
                    )
            except Exception:  # pragma: no cover - defensive
                refresh_log.new_expires_at = None

            # Any previous error is now cleared on success.
            token.refresh_error = None
            db.commit()

            logger.info(
                "Successfully refreshed token for account %s (%s) via debug flow",
                account.id,
                account.house_name,
            )

            return {
                "success": True,
                "error": None,
                "error_message": None,
                "http": debug_payload,
            }

        # === capture_http=False: normal worker/admin flow ===
        new_token_data = await ebay_service.refresh_access_token(
            token.refresh_token,
            user_id=getattr(account, "org_id", None),
            environment=env,
        )

        # Persist new tokens if requested.
        if persist:
            ebay_account_service.save_tokens(
                db,
                account.id,
                access_token=new_token_data.access_token,
                refresh_token=(
                    getattr(new_token_data, "refresh_token", None)
                    or token.refresh_token
                ),
                expires_in=int(getattr(new_token_data, "expires_in", 0) or 0),
                refresh_token_expires_in=int(
                    getattr(new_token_data, "refresh_token_expires_in", 0) or 0,
                )
                if getattr(new_token_data, "refresh_token_expires_in", None)
                is not None
                else None,
            )
            # Reload token so we can capture updated expires_at.
            token = ebay_account_service.get_token(db, account.id) or token

        finished = datetime.now(timezone.utc)
        refresh_log.success = True
        refresh_log.finished_at = finished
        try:
            if getattr(token, "expires_at", None) is not None:
                refresh_log.new_expires_at = token.expires_at
            else:
                refresh_log.new_expires_at = finished + timedelta(
                    seconds=int(getattr(new_token_data, "expires_in", 0) or 0),
                )
        except Exception:  # pragma: no cover - defensive
            refresh_log.new_expires_at = None

        token.refresh_error = None
        db.commit()

        logger.info(
            "Successfully refreshed token for account %s (%s) via worker/admin flow",
            account.id,
            account.house_name,
        )

        return {
            "success": True,
            "error": None,
            "error_message": None,
            "http": None,
        }

    except HTTPException as exc:
        # HTTPException from EbayService (non-200 or network error).
        msg = str(exc.detail) if isinstance(exc.detail, str) else str(exc.detail)
        logger.error(
            "Token refresh for account %s (%s) failed with HTTPException: %s",
            account.id,
            account.house_name,
            msg,
        )

        refresh_log.success = False
        refresh_log.error_code = str(exc.status_code)
        refresh_log.error_message = msg[:2000]
        refresh_log.finished_at = datetime.now(timezone.utc)
        if token is not None:
            token.refresh_error = msg
        db.commit()

        return {
            "success": False,
            "error": str(exc.status_code),
            "error_message": msg,
            "http": None,
        }

    except Exception as exc:  # noqa: BLE001
        # Catch-all for unexpected errors so that the worker can continue.
        msg = str(exc)
        logger.error(
            "Unexpected error refreshing token for account %s (%s): %s",
            account.id,
            account.house_name,
            msg,
        )

        refresh_log.success = False
        refresh_log.error_code = "exception"
        refresh_log.error_message = msg[:2000]
        refresh_log.finished_at = datetime.now(timezone.utc)
        if token is not None:
            token.refresh_error = msg
        db.commit()

        return {
            "success": False,
            "error": "exception",
            "error_message": msg,
            "http": None,
        }
