from __future__ import annotations

import base64
import json
import time
from typing import Optional, Tuple, Dict, Any

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from app.config import settings
from app.services.ebay import ebay_service
from app.utils.logger import logger

# In-memory cache for eBay public keys, keyed by kid. Each entry is a tuple of
# (public_key_pem: str, fetched_at_epoch: float).
_PUBLIC_KEY_CACHE: Dict[str, Tuple[str, float]] = {}
_PUBLIC_KEY_TTL_SECONDS = 60 * 60  # 1 hour


async def _get_ebay_public_key(kid: str) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    """Fetch the eBay Notification public key for a given ``kid``.

    This uses the Commerce Notification public key endpoint documented by eBay
    and authenticates using an application access token obtained via
    ``get_app_access_token``. Results are cached in-memory per-process for a
    short TTL to avoid repeated HTTP calls on every webhook event.

    Returns (public_key_pem, error_info_dict). On failure, public_key_pem will
    be ``None`` and error_info_dict will contain a short error description.
    """

    if not kid:
        return None, {
            "type": "missing_kid",
            "message": "X-EBAY-SIGNATURE header did not contain a kid field",
        }

    # Cache check
    now = time.time()
    cached = _PUBLIC_KEY_CACHE.get(kid)
    if cached is not None:
        pem, fetched_at = cached
        if now - fetched_at < _PUBLIC_KEY_TTL_SECONDS:
            return pem, None

    try:
        app_token = await ebay_service.get_app_access_token()
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(
            "[webhook-signature] Failed to obtain app token for public key fetch kid=%s: %s",
            kid,
            exc,
            exc_info=True,
        )
        return None, {
            "type": "key_fetch_failed",
            "message": f"Could not obtain app token to fetch public key for kid={kid}",
        }

    base_url = settings.ebay_api_base_url.rstrip("/")
    url = f"{base_url}/commerce/notification/v1/public_key/{kid}"

    headers = {
        "Authorization": f"Bearer {app_token}",
        "Accept": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers)
    except httpx.RequestError as exc:  # pragma: no cover - defensive
        logger.warning(
            "[webhook-signature] HTTP error fetching public key kid=%s: %s",
            kid,
            exc,
            exc_info=True,
        )
        return None, {
            "type": "key_fetch_failed",
            "message": f"HTTP error fetching public key for kid={kid}: {exc}",
        }

    if resp.status_code != 200:
        try:
            body = resp.json()
        except Exception:
            body = resp.text
        logger.warning(
            "[webhook-signature] Non-200 response fetching public key kid=%s status=%s body=%s",
            kid,
            resp.status_code,
            str(body)[:500],
        )
        return None, {
            "type": "key_fetch_failed",
            "message": f"Public key endpoint returned HTTP {resp.status_code} for kid={kid}",
        }

    try:
        data = resp.json() or {}
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(
            "[webhook-signature] Failed to parse public key response JSON kid=%s: %s",
            kid,
            exc,
            exc_info=True,
        )
        return None, {
            "type": "key_fetch_failed",
            "message": f"Invalid JSON in public key response for kid={kid}",
        }

    # eBay docs show a response containing at least a "key" field with the
    # PEM-encoded public key.
    pem = data.get("key")
    if not isinstance(pem, str) or not pem.strip():
        logger.warning(
            "[webhook-signature] Public key response for kid=%s missing 'key' field: %s",
            kid,
            data,
        )
        return None, {
            "type": "key_fetch_failed",
            "message": f"Public key response for kid={kid} did not contain a usable 'key' field",
        }

    _PUBLIC_KEY_CACHE[kid] = (pem, now)
    return pem, None


def _decode_signature_header(signature_header: str) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Decode the X-EBAY-SIGNATURE header into a JSON object.

    Per eBay docs, the header value is a **Base64-encoded JSON string** with at
    least:

    - alg: algorithm identifier (e.g. "ECDSA")
    - kid: public key id
    - signature: Base64-encoded signature bytes
    - digest: digest algorithm used (e.g. "SHA1")

    Returns (header_dict, error_info). On failure, header_dict is None and
    error_info contains a short description.
    """

    if not signature_header:
        return None, None

    try:
        decoded = base64.b64decode(signature_header)
        obj = json.loads(decoded.decode("utf-8"))
        if not isinstance(obj, dict):
            raise ValueError("decoded header is not a JSON object")
        return obj, None
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(
            "[webhook-signature] Failed to decode X-EBAY-SIGNATURE header: %s",
            exc,
            exc_info=True,
        )
        return None, {
            "type": "signature_header_invalid",
            "message": f"Could not decode X-EBAY-SIGNATURE header: {exc}",
        }


async def verify_ebay_notification_signature(
    signature_header: str,
    raw_body: bytes,
) -> Tuple[Optional[bool], Optional[str], Optional[Dict[str, Any]]]:
    """Verify X-EBAY-SIGNATURE for a Notification API webhook.

    This implements the flow described in eBay's Event Notification signature
    verification docs:

    1. Decode the Base64-encoded JSON header to extract ``kid``, ``alg``,
       ``signature`` and ``digest`` fields.
    2. Fetch the corresponding public key via the Commerce Notification
       public-key endpoint.
    3. Verify the ECDSA signature over the raw HTTP body using the indicated
       digest algorithm.

    Returns a tuple of (signature_valid, signature_kid, error_info_dict):

    - signature_valid = True  → signature verified successfully
    - signature_valid = False → verification failed (invalid signature)
    - signature_valid = None  → verification could not be performed (missing
      kid, key fetch failure, or header decode problem)
    """

    if not signature_header:
        return None, None, None

    header_obj, header_err = _decode_signature_header(signature_header)
    if header_obj is None:
        # Header could not be decoded; treat as invalid signature but continue
        # storing the event.
        return False, None, header_err

    kid = header_obj.get("kid")
    alg = header_obj.get("alg")
    sig_b64 = header_obj.get("signature")
    digest_alg = header_obj.get("digest")

    if not isinstance(sig_b64, str) or not sig_b64.strip():
        return False, str(kid) if kid else None, {
            "type": "signature_header_missing_signature",
            "message": "Decoded X-EBAY-SIGNATURE header missing 'signature' field",
        }

    # Fetch public key for kid
    public_key_pem, key_err = await _get_ebay_public_key(str(kid) if kid else "")
    if public_key_pem is None:
        # We could not obtain a public key; treat validity as unknown but
        # surface the error so it can be logged with the event.
        return None, str(kid) if kid else None, key_err

    # Choose hash algorithm based on digest hint; default to SHA1 which is
    # what eBay examples use for ECDSA verification.
    digest_upper = (digest_alg or "SHA1").upper()
    if digest_upper in {"SHA1", "SHA-1"}:
        hash_alg = hashes.SHA1()
    elif digest_upper in {"SHA256", "SHA-256"}:
        hash_alg = hashes.SHA256()
    else:
        # Unknown digest; log and fall back to SHA1 for now.
        logger.info(
            "[webhook-signature] Unknown digest '%s' for kid=%s; falling back to SHA1",
            digest_alg,
            kid,
        )
        hash_alg = hashes.SHA1()

    try:
        public_key = serialization.load_pem_public_key(public_key_pem.encode("utf-8"))
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(
            "[webhook-signature] Failed to load public key PEM for kid=%s: %s",
            kid,
            exc,
            exc_info=True,
        )
        return None, str(kid) if kid else None, {
            "type": "public_key_invalid",
            "message": f"Failed to load public key for kid={kid}: {exc}",
        }

    try:
        signature_bytes = base64.b64decode(sig_b64)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(
            "[webhook-signature] Failed to base64-decode signature for kid=%s: %s",
            kid,
            exc,
            exc_info=True,
        )
        return False, str(kid) if kid else None, {
            "type": "signature_decode_failed",
            "message": f"Could not decode signature bytes for kid={kid}: {exc}",
        }

    try:
        # eBay docs demonstrate ECDSA verification over the raw request body
        # using the configured digest (often SHA1).
        if isinstance(public_key, ec.EllipticCurvePublicKey):
            public_key.verify(signature_bytes, raw_body, ec.ECDSA(hash_alg))
        else:
            # If the key is not an EC key, we currently do not support
            # verification and mark it as unknown rather than failing hard.
            logger.info(
                "[webhook-signature] Public key for kid=%s is not an EC key; skipping verification",
                kid,
            )
            return None, str(kid) if kid else None, {
                "type": "unsupported_key_type",
                "message": "Only EC public keys are supported for X-EBAY-SIGNATURE verification",
            }
    except InvalidSignature:
        logger.info("[webhook-signature] kid=%s status=INVALID", kid)
        return False, str(kid) if kid else None, {
            "type": "signature_invalid",
            "message": f"Signature verification failed for kid={kid}",
            "kid": str(kid) if kid else None,
        }
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(
            "[webhook-signature] Error verifying signature for kid=%s: %s",
            kid,
            exc,
            exc_info=True,
        )
        return None, str(kid) if kid else None, {
            "type": "signature_verification_error",
            "message": f"Unexpected error during signature verification for kid={kid}: {exc}",
        }

    logger.info("[webhook-signature] kid=%s status=VALID", kid)
    return True, str(kid) if kid else None, None
