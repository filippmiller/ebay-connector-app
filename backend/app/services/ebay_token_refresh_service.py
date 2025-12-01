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

from dataclasses import dataclass



def _get_plain_refresh_token(token: EbayToken) -> str:
    """
    Canonical helper to retrieve the decrypted refresh token from an EbayToken object.

    This handles cases where the ORM property might return the raw encrypted value
    (e.g. if decryption fails or environment is flaky) by explicitly attempting
    decryption on the raw column if needed.
    """
    from app.utils import crypto

    # 1. Try the property first (standard path)
    # If decryption works, this returns "v^..."
    # If decryption fails (in crypto.decrypt), this returns "ENC:v1:..."
    val = token.refresh_token

    if val and isinstance(val, str) and not val.startswith("ENC:"):
        return val

    # 2. If we got an encrypted value (or None), try to access the raw column explicitly
    # and decrypt it. This is a fallback/retry.
    raw = token._refresh_token
    if not raw:
        return ""

    # Attempt explicit decryption
    decrypted = crypto.decrypt(raw)

    # 3. Final check
    if decrypted and isinstance(decrypted, str) and not decrypted.startswith("ENC:"):
        return decrypted

    # If it's still encrypted, it means we really can't decrypt it (wrong key?)
    return decrypted or ""


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

    # ------------------------------------------------------------------
    # 2. Decrypt/Validate Token
    # ------------------------------------------------------------------
    # Use our canonical helper to ensure we have a plain token (v^...)
    # before calling the service.
    plain_refresh_token = _get_plain_refresh_token(token) if token else ""

    if not plain_refresh_token:
        msg = "No refresh token available (or decryption failed)"
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
                plain_refresh_token,
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
        # HTTPException from EbayService (non-200, network error, or decrypt_failed).
        detail = exc.detail
        if isinstance(detail, dict):
            code = detail.get("code") or str(exc.status_code)
            message = detail.get("message") or str(detail)
        else:
            code = str(exc.status_code)
            message = str(detail)

        msg = message
        logger.error(
            "Token refresh for account %s (%s) failed with HTTPException: %s",
            account.id,
            account.house_name,
            msg,
        )

        refresh_log.success = False
        refresh_log.error_code = code
        refresh_log.error_message = msg[:2000]
        refresh_log.finished_at = datetime.now(timezone.utc)
        if token is not None:
            # Mark decrypt failures explicitly so the UI can show "needs reconnect".
            if code == "decrypt_failed":
                token.refresh_error = f"decrypt_failed: {msg}"
            else:
                token.refresh_error = msg
        db.commit()

        # Best-effort connect-log entry so the unified token terminal can show
        # decrypt_failed cases even when no outbound HTTP call was made.
        try:  # pragma: no cover - diagnostics only
            from app.services.ebay_connect_logger import ebay_connect_logger

            env = settings.EBAY_ENVIRONMENT or "sandbox"
            ebay_connect_logger.log_event(
                user_id=getattr(account, "org_id", None),
                environment=env,
                action="token_refresh_failed",
                request={
                    "method": "POST",
                    "url": ebay_service.token_url,
                    "headers": {
                        "Content-Type": "application/x-www-form-urlencoded",
                        "Authorization": "Basic **** (masked)",
                    },
                    "body": {
                        "grant_type": "refresh_token",
                        # We deliberately do not attempt to include the broken
                        # refresh token here; the important part for the UI is
                        # that this entry is clearly marked as decrypt_failed.
                        "refresh_token": "<decrypt_failed>",
                    },
                },
                response=None,
                error=msg[:2000],
                source=triggered_by,
            )
        except Exception:
            # Logging must never break the refresh flow.
            pass

        return {
            "success": False,
            "error": code,
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


@dataclass
class SanitizedRefreshTokenPreview:
    method: str
    url: str
    headers: Dict[str, Any]
    body_form: Dict[str, Any]


def _mask_refresh_token(refresh_token: str) -> Dict[str, Any]:
    """Return a safely masked view of the refresh token.

    Only exposes prefix/suffix/length and a couple of booleans.
    Never returns the full token.
    """
    if not refresh_token:
        return {
            "prefix": None,
            "suffix": None,
            "length": 0,
            "starts_with_v": False,
            "contains_enc_prefix": False,
        }

    length = len(refresh_token)
    prefix_len = 10 if length >= 10 else max(0, length // 2)
    suffix_len = 6 if length >= 6 else max(0, length - prefix_len)

    prefix = refresh_token[:prefix_len]
    suffix = refresh_token[-suffix_len:] if suffix_len > 0 else ""

    return {
        "prefix": prefix,
        "suffix": suffix,
        "length": length,
        "starts_with_v": refresh_token.startswith("v^1.1"),
        "contains_enc_prefix": "ENC:" in refresh_token,
    }


def _sanitize_headers(headers: Dict[str, Any]) -> Dict[str, Any]:
    """Return a sanitized subset of HTTP headers with no secrets.

    Drops Authorization and any header that obviously looks secret.
    """
    safe: Dict[str, Any] = {}
    for key, value in (headers or {}).items():
        k_lower = str(key).lower()
        if "authorization" in k_lower:
            continue
        if "secret" in k_lower or "token" in k_lower or "key" in k_lower:
            continue
        safe[key] = value
    return safe


def build_sanitized_refresh_preview_for_account(
    db: Session,
    ebay_account_id: str,
) -> Dict[str, Any]:
    """Build a sanitized preview of the refresh request for a single account.

    This uses the same refresh_token that the worker would use and the same
    EbayService.refresh_access_token builder, but does NOT perform any HTTP
    request. Instead, it reconstructs the method/url/headers/body shape and
    returns a masked view suitable for Admin UI.
    """
    account: Optional[EbayAccount] = db.query(EbayAccount).filter(
        EbayAccount.id == ebay_account_id,
    ).first()
    if not account:
        return {
            "error": "no_account",
            "message": "No EbayAccount found for this id",
        }

    token: Optional[EbayToken] = db.query(EbayToken).filter(
        EbayToken.ebay_account_id == ebay_account_id,
    ).order_by(EbayToken.updated_at.desc()).first()

    if not token or not token.refresh_token:
        return {
            "error": "no_token",
            "message": "No EbayToken with refresh_token found for this account",
        }

    # IMPORTANT: this must be the same plain refresh token the worker uses.
    refresh_token = token.refresh_token

    # Reconstruct what refresh_access_token builds internally today.
    # We mirror app.services.ebay.EbayService.refresh_access_token without
    # actually performing the HTTP call.
    import base64

    credentials = f"{settings.ebay_client_id}:{settings.ebay_cert_id}"
    encoded_credentials = base64.b64encode(credentials.encode()).decode()

    raw_headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Basic {encoded_credentials}",
    }
    raw_body = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }

    masked_token_info = _mask_refresh_token(refresh_token)

    preview: SanitizedRefreshTokenPreview = SanitizedRefreshTokenPreview(
        method="POST",
        url=ebay_service.token_url,
        headers=_sanitize_headers(raw_headers),
        body_form={
            "grant_type": raw_body["grant_type"],
            "refresh_token": masked_token_info,
        },
    )

    return {
        "method": preview.method,
        "url": preview.url,
        "headers": preview.headers,
        "body_form": preview.body_form,
        "account": {
            "id": str(account.id),
            "house_name": account.house_name,
            "username": account.username,
            "ebay_user_id": account.ebay_user_id,
        },
    }
