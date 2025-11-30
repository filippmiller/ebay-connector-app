from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.models_sqlalchemy.models import EbayAccount, EbayToken
from app.services.ebay import ebay_service


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
    from app.config import settings  # imported lazily
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
