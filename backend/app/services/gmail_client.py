from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional

import base64
import html as html_lib

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models_sqlalchemy.models import IntegrationAccount, IntegrationCredentials
from app.utils.logger import logger


GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"

# How many seconds before expiry we proactively refresh the access token.
_TOKEN_REFRESH_MARGIN_SECONDS = 60


def _decode_base64url(data: str) -> bytes:
    """Decode a base64url-encoded string from the Gmail API body.data field.

    Gmail uses URL-safe base64 without padding; this helper restores padding
    and decodes to raw bytes.
    """

    # Replace URL-safe chars and pad to a multiple of 4.
    data = data.replace("-", "+").replace("_", "/")
    padding = "=" * (-len(data) % 4)
    return base64.b64decode(data + padding)


def _parse_date_header(value: Optional[str]) -> Optional[datetime]:
    """Parse RFC2822/2822-like Date headers into timezone-aware datetimes."""

    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
        # Ensure timezone-aware and normalized to UTC.
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


class _HtmlTextExtractor(HTMLParser):
    """Very small HTML→text helper used for Gmail HTML-only messages.

    We deliberately avoid heavy dependencies and keep extraction simple:
    - Collect all text nodes.
    - Strip and join them with single spaces.
    - Decode HTML entities.

    This is sufficient to get a readable `body_text` from eBay-style HTML
    templates while keeping the implementation lightweight.
    """

    def __init__(self) -> None:
        super().__init__()
        self._parts: List[str] = []

    def handle_data(self, data: str) -> None:  # type: ignore[override]
        if not data:
            return
        self._parts.append(data)

    def get_text(self) -> str:
        # Join non-empty segments with single spaces.
        raw = " ".join(part.strip() for part in self._parts if part.strip())
        if not raw:
            return ""
        return html_lib.unescape(raw)


def _html_to_text(value: Optional[str]) -> Optional[str]:
    """Convert a small HTML fragment to plain text.

    Returns ``None`` when the conversion results in an empty string.
    """

    if not value:
        return None
    parser = _HtmlTextExtractor()
    try:
        parser.feed(value)
        parser.close()
    except Exception:
        # On any parsing issue, fall back to a very naive strip of tags.
        # This keeps the pipeline robust even for malformed HTML.
        text = html_lib.unescape(value)
        return text.strip() or None

    text = parser.get_text().strip()
    return text or None


@dataclass
class GmailMessageMeta:
    """Lightweight representation of a Gmail message id + thread id."""

    id: str
    thread_id: Optional[str]


@dataclass
class GmailMessage:
    """Normalized Gmail message payload used by the sync service."""

    external_id: str
    thread_id: Optional[str]
    from_address: Optional[str]
    to_addresses: List[str]
    cc_addresses: List[str]
    bcc_addresses: List[str]
    subject: Optional[str]
    body_text: Optional[str]
    body_html: Optional[str]
    sent_at: Optional[datetime]


class GmailClient:
    """Small helper around the Gmail REST API for a single integration account.

    The client is instantiated with the SQLAlchemy session, the owning
    IntegrationAccount and its IntegrationCredentials. It handles token
    refresh (when a refresh_token is available) and exposes convenience
    methods for listing and fetching messages.
    """

    def __init__(
        self,
        db: Session,
        account: IntegrationAccount,
        credentials: IntegrationCredentials,
    ) -> None:
        self.db = db
        self.account = account
        self.credentials = credentials

    # ------------------------------------------------------------------
    # Token management
    # ------------------------------------------------------------------

    async def refresh_access_token_if_needed(self) -> None:
        """Refresh access_token via refresh_token when close to expiry.

        If no refresh_token is available, this is a no-op; the caller must
        handle eventual 401s from the Gmail API. On refresh failure, the
        account status is set to "error" and the exception is propagated.
        """

        expires_at = self.credentials.expires_at
        now = datetime.now(timezone.utc)
        margin = timedelta(seconds=_TOKEN_REFRESH_MARGIN_SECONDS)

        if expires_at is not None and expires_at > now + margin:
            # Still valid; nothing to do.
            return

        refresh_token = self.credentials.refresh_token
        if not refresh_token:
            # No refresh token to use; caller will have to re-consent.
            logger.warning(
                "[gmail] account_id=%s has no refresh_token; cannot refresh access token",
                self.account.id,
            )
            return

        client_id = settings.GMAIL_CLIENT_ID
        client_secret = settings.GMAIL_CLIENT_SECRET
        if not client_id or not client_secret:
            logger.error("[gmail] OAuth client not configured; cannot refresh token")
            raise RuntimeError("gmail_oauth_not_configured")

        data = {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }

        logger.info("[gmail] Refreshing access token for account_id=%s", self.account.id)

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
                resp = await client.post(GOOGLE_TOKEN_ENDPOINT, data=data)
        except httpx.HTTPError as exc:  # pragma: no cover - network failure
            logger.error("[gmail] HTTP error refreshing token: %s", exc)
            self.account.status = "error"
            self.db.commit()
            raise

        if resp.status_code != 200:
            logger.error(
                "[gmail] Token refresh failed: status=%s body=%s",
                resp.status_code,
                resp.text,
            )
            self.account.status = "error"
            self.db.commit()
            raise RuntimeError(f"gmail_token_refresh_failed:{resp.status_code}")

        payload = resp.json()
        access_token = payload.get("access_token")
        expires_in = payload.get("expires_in")
        if not access_token:
            logger.error("[gmail] Token refresh response missing access_token: %s", payload)
            self.account.status = "error"
            self.db.commit()
            raise RuntimeError("gmail_token_refresh_missing_access_token")

        # Persist new token via encrypted properties.
        self.credentials.access_token = access_token
        if isinstance(expires_in, (int, float)):
            self.credentials.expires_at = now + timedelta(seconds=int(expires_in))
        self.db.commit()

    # ------------------------------------------------------------------
    # Gmail API helpers
    # ------------------------------------------------------------------

    @property
    def _access_token(self) -> Optional[str]:
        return self.credentials.access_token

    def _auth_headers(self) -> Dict[str, str]:
        token = self._access_token
        if not token:
            raise RuntimeError("gmail_access_token_missing")
        return {"Authorization": f"Bearer {token}"}

    async def list_message_ids_since(
        self,
        since: datetime,
        *,
        max_results: int = 100,
    ) -> List[GmailMessageMeta]:
        """List Gmail message ids newer than ``since``.

        We use a simple "after:YYYY/MM/DD" query which is coarse but sufficient
        for the training use case. Paging is limited to the first page (up to
        ``max_results`` messages).
        """

        if since.tzinfo is None:
            since = since.replace(tzinfo=timezone.utc)
        since_date = since.astimezone(timezone.utc).date()
        q = f"after:{since_date.strftime('%Y/%m/%d')}"

        params = {
            "maxResults": max_results,
            "q": q,
        }

        url = f"{GMAIL_API_BASE}/messages"

        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
            resp = await client.get(url, headers=self._auth_headers(), params=params)

        if resp.status_code != 200:
            logger.warning(
                "[gmail] list messages failed for account_id=%s: status=%s body=%s",
                self.account.id,
                resp.status_code,
                resp.text,
            )
            return []

        payload = resp.json()
        messages = payload.get("messages") or []
        out: List[GmailMessageMeta] = []
        for item in messages:
            msg_id = item.get("id")
            if not msg_id:
                continue
            out.append(GmailMessageMeta(id=msg_id, thread_id=item.get("threadId")))
        return out

    async def get_message(self, message_id: str) -> Optional[GmailMessage]:
        """Fetch a single Gmail message in ``format=full`` and normalize it.

        On non-200 responses this logs and returns ``None``.
        """

        url = f"{GMAIL_API_BASE}/messages/{message_id}"
        params = {"format": "full"}

        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
            resp = await client.get(url, headers=self._auth_headers(), params=params)

        if resp.status_code != 200:
            logger.warning(
                "[gmail] get message failed for account_id=%s message_id=%s: status=%s body=%s",
                self.account.id,
                message_id,
                resp.status_code,
                resp.text,
            )
            return None

        data = resp.json()
        payload = data.get("payload") or {}
        headers = payload.get("headers") or []

        header_map: Dict[str, str] = {}
        for h in headers:
            name = (h.get("name") or "").strip()
            value = (h.get("value") or "").strip()
            if not name:
                continue
            header_map[name.lower()] = value

        from_address = header_map.get("from")
        to_raw = header_map.get("to") or ""
        cc_raw = header_map.get("cc") or ""
        bcc_raw = header_map.get("bcc") or ""
        subject = header_map.get("subject")
        date_header = header_map.get("date")

        def _split_addrs(raw: str) -> List[str]:
            return [part.strip() for part in raw.split(",") if part.strip()]

        to_addresses = _split_addrs(to_raw)
        cc_addresses = _split_addrs(cc_raw)
        bcc_addresses = _split_addrs(bcc_raw)

        sent_at = _parse_date_header(date_header)

        # Extract body text and HTML by traversing the MIME tree.
        body_text: Optional[str] = None
        body_html: Optional[str] = None

        def _extract_from_part(part: Dict[str, Any]) -> None:
            nonlocal body_text, body_html

            mime_type = part.get("mimeType") or ""
            body = part.get("body") or {}
            data_field = body.get("data")

            if data_field and isinstance(data_field, str):
                try:
                    decoded = _decode_base64url(data_field).decode("utf-8", errors="replace")
                except Exception:
                    decoded = None
            else:
                decoded = None

            if mime_type == "text/plain" and decoded is not None:
                # Prefer the first plain-text part.
                if body_text is None:
                    body_text = decoded
            elif mime_type == "text/html" and decoded is not None:
                if body_html is None:
                    body_html = decoded

            for child in part.get("parts") or []:
                if isinstance(child, dict):
                    _extract_from_part(child)

        if payload:
            _extract_from_part(payload)

        # Some providers (including many eBay notifications) send HTML-only
        # emails. In that case `body_text` remains None even though we have a
        # perfectly good HTML body. To make downstream AI pairing logic work,
        # we synthesise a plain-text version from HTML when needed.
        if body_text is None and body_html:
            body_text = _html_to_text(body_html)

        return GmailMessage(
            external_id=data.get("id"),
            thread_id=data.get("threadId"),
            from_address=from_address,
            to_addresses=to_addresses,
            cc_addresses=cc_addresses,
            bcc_addresses=bcc_addresses,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            sent_at=sent_at,
        )
