from __future__ import annotations

"""Minimal encryption utilities for protecting sensitive tokens at rest.

This module provides two helpers, :func:`encrypt` and :func:`decrypt`, which
wrap AES-GCM encryption with a key derived from the application secret.

- Encryption is **authenticated** (AES-GCM) and uses a per-message nonce.
- Ciphertexts are versioned and prefixed so we can safely distinguish them
  from legacy plain-text values stored in the database.
- ``decrypt`` is **backwards compatible**: if the value does not look like
  an encrypted blob produced by this module, it is returned as-is. This lets
  us gradually migrate existing rows without a dedicated backfill job.

The format is:

    ENC:v1:<base64(nonce || ciphertext || tag)>

where:
- ``nonce`` is 12 random bytes per encryption
- ``ciphertext||tag`` is produced by :class:`cryptography.hazmat.primitives.ciphers.aead.AESGCM`.

IMPORTANT:
    These helpers are intended for long-lived secrets (tokens, client
    credentials). Do NOT use them for password hashing; passwords must go
    through a dedicated hashing scheme (PBKDF2/bcrypt/argon2) and **never** be
    decrypted.
"""

import base64
import os
from typing import Optional

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.config import settings


_PREFIX = "ENC:v1:"
_NONCE_SIZE = 12  # 96-bit nonce recommended for AES-GCM
_KEY_SIZE = 32    # 256-bit AES key


def _get_key() -> bytes:
    """Derive a stable AES-GCM key from the application secret.

    We avoid introducing a new mandatory ENV var by deriving the key from
    ``settings.secret_key`` using HKDF-SHA256 and a fixed context string.
    If you later decide to rotate the key, you can either:
    - introduce an explicit ENCRYPTION_KEY env var and change this derivation,
    - or add a new prefix version (e.g. ENC:v2:) with a new derivation.
    """

    # Base key material; MUST be secret and reasonably high-entropy.
    base = settings.secret_key.encode("utf-8")

    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=_KEY_SIZE,
        salt=None,
        info=b"ebay-token-encryption",
    )
    return hkdf.derive(base)


def encrypt(plaintext: Optional[str]) -> Optional[str]:
    """Encrypt a string value using AES-GCM.

    Returns a versioned ciphertext string. ``None`` is passed through as ``None``.
    """

    if plaintext is None:
        return None
    if not isinstance(plaintext, str):
        plaintext = str(plaintext)

    key = _get_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(_NONCE_SIZE)
    ct = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), associated_data=None)

    blob = base64.b64encode(nonce + ct).decode("ascii")
    return _PREFIX + blob


def decrypt(value: Optional[str]) -> Optional[str]:
    """Decrypt a value produced by :func:`encrypt`.

    Backwards compatible:
    - If ``value`` is None, returns None.
    - If ``value`` is not a string or does not start with our prefix,
      returns it unchanged (assumed legacy plain-text).
    - If decryption fails for any reason, returns the original value.

    This behaviour ensures we never crash the app on unexpected data and we
    can migrate existing rows lazily.
    """

    if value is None:
        return None
    if not isinstance(value, str):
        return value
    if not value.startswith(_PREFIX):
        # Legacy plain-text or another format; return as-is.
        return value

    try:
        blob_b64 = value[len(_PREFIX) :]
        raw = base64.b64decode(blob_b64.encode("ascii"))
        if len(raw) <= _NONCE_SIZE:
            # Malformed; treat as opaque string.
            return value
        nonce, ct = raw[:_NONCE_SIZE], raw[_NONCE_SIZE:]
        key = _get_key()
        aesgcm = AESGCM(key)
        pt_bytes = aesgcm.decrypt(nonce, ct, associated_data=None)
        return pt_bytes.decode("utf-8")
    except Exception as e:
        # Log the error for diagnostics, but return original value to be safe/compatible
        # with legacy plain-text data.
        from app.utils.logger import logger
        logger.error(f"Crypto decryption failed: {type(e).__name__}: {e}")
        return value