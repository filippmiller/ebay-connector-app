import types

import pytest
from fastapi import HTTPException

from app.config import settings
from app.services.ebay import EbayService
from app.utils import crypto


@pytest.fixture(autouse=True)
def _ensure_ebay_credentials(monkeypatch):
    """Provide dummy eBay credentials so the builder does not fail early.

    The tests focus on refresh-token handling, not real HTTP calls, so we just
    need non-empty client id / cert id values.
    """
    monkeypatch.setattr(settings, "ebay_client_id", "dummy-client-id", raising=False)
    monkeypatch.setattr(settings, "ebay_cert_id", "dummy-cert-id", raising=False)
    # Ensure environment is set to sandbox for deterministic token_url
    monkeypatch.setattr(settings, "EBAY_ENVIRONMENT", "sandbox", raising=False)


def _call_builder(raw_token: str, caller: str = "test"):
    svc = EbayService()
    return svc._build_refresh_token_request_components(
        raw_token,
        environment="sandbox",
        caller=caller,
    )


def test_builder_accepts_plain_v_prefix_token():
    """A normal v^... refresh token should pass through unchanged.

    The builder must not attempt any decryption when the token already looks
    like a real eBay refresh token.
    """
    target_env, headers, data, request_payload = _call_builder("v^1.1.fake-token", caller="debug")

    assert target_env == "sandbox"
    assert data["grant_type"] == "refresh_token"
    assert data["refresh_token"].startswith("v^")

    # The same value should be used in the request payload body.
    assert request_payload["body"]["refresh_token"] == data["refresh_token"]


def test_builder_decrypts_enc_prefix_once(monkeypatch):
    """ENC:v1:... tokens must be decrypted once before being sent to eBay."""

    def fake_decrypt(value: str) -> str:  # pragma: no cover - simple stub
        assert value.startswith("ENC:v1:")
        return "v^1.1.decrypted-token"

    monkeypatch.setattr(crypto, "decrypt", fake_decrypt)

    _, _, data, request_payload = _call_builder("ENC:v1:wrapped-token", caller="scheduled")

    assert data["refresh_token"] == "v^1.1.decrypted-token"
    assert request_payload["body"]["refresh_token"] == "v^1.1.decrypted-token"


@pytest.mark.parametrize("bad_token", [
    "",  # empty
    "   ",  # whitespace
    "ENC:v1:still-encrypted",  # decrypt returned ENC:v1:...
    "not-a-valid-prefix",  # does not start with v^
])
def test_builder_raises_decrypt_failed_for_invalid_tokens(monkeypatch, bad_token):
    """Invalid tokens must raise HTTPException with code=decrypt_failed.

    In these cases no HTTP request should be attempted; the builder itself
    validates and fails deterministically.
    """

    def fake_decrypt(value: str) -> str:
        # Return the provided "bad_token" so we can simulate a variety of
        # failure cases after decryption.
        return bad_token

    monkeypatch.setattr(crypto, "decrypt", fake_decrypt)

    # When the raw token already looks invalid and does not start with ENC:v1:,
    # the builder will not call crypto.decrypt at all; this is fine, we still
    # expect a decrypt_failed error.
    svc = EbayService()

    with pytest.raises(HTTPException) as excinfo:
        svc._build_refresh_token_request_components(
            "ENC:v1:wrapped-token" if bad_token.startswith("ENC:v1:") else bad_token,
            environment="sandbox",
            caller="scheduled",
        )

    detail = excinfo.value.detail
    assert isinstance(detail, dict)
    assert detail.get("code") == "decrypt_failed"


@pytest.mark.asyncio
async def test_debug_and_worker_use_same_refresh_token(monkeypatch):
    """debug_refresh_access_token_http and refresh_access_token share the final token.

    For the same plaintext refresh token, both the debug flow and the worker
    flow must build an HTTP body with the same grant_type and refresh_token.
    We stub httpx.AsyncClient so no real network is used.
    """
    # Dummy credentials
    monkeypatch.setattr(settings, "ebay_client_id", "dummy-client-id", raising=False)
    monkeypatch.setattr(settings, "ebay_cert_id", "dummy-cert-id", raising=False)
    monkeypatch.setattr(settings, "EBAY_ENVIRONMENT", "sandbox", raising=False)

    captured = {
        "debug": None,
        "worker": None,
    }

    class FakeResponse:
        def __init__(self, status_code: int, body: dict, request):
            self.status_code = status_code
            self._body = body
            self.request = request
            self.headers = {"content-type": "application/json"}
            self.reason_phrase = "OK"

        def json(self):
            return self._body

        @property
        def text(self):
            return "{}"

    class FakeRequest:
        def __init__(self, method: str, url: str, data: dict, headers: dict):
            self.method = method
            self.url = url
            self.headers = headers
            self._data = data

        @property
        def content(self):
            # httpx encodes form data as bytes; we just emulate a simple body
            from urllib.parse import urlencode

            return urlencode(self._data).encode("utf-8")

    class FakeClient:
        def __init__(self, label: str, *args, **kwargs):
            self._label = label

        async def __aenter__(self):  # pragma: no cover - trivial
            return self

        async def __aexit__(self, exc_type, exc, tb):  # pragma: no cover - trivial
            return False

        async def post(self, url: str, headers=None, data=None, timeout=None):
            # Capture the form data for the given label.
            captured[self._label] = {
                "url": url,
                "headers": headers or {},
                "data": dict(data or {}),
            }
            req = FakeRequest("POST", url, dict(data or {}), headers or {})
            # Minimal token payload for worker flow.
            body = {
                "access_token": "dummy-access",
                "refresh_token": data.get("refresh_token") if isinstance(data, dict) else None,
                "expires_in": 7200,
            }
            return FakeResponse(200, body, req)

    # Monkeypatch httpx.AsyncClient so that we can distinguish flows by label.
    import httpx

    async def fake_async_client_factory(*args, **kwargs):  # pragma: no cover
        return FakeClient("worker", *args, **kwargs)

    # We need two different labels for the two calls; use a small wrapper that
    # swaps the label on subsequent instantiations.
    original_async_client = httpx.AsyncClient

    created = {"count": 0}

    def async_client_factory(*args, **kwargs):  # pragma: no cover
        created["count"] += 1
        label = "debug" if created["count"] == 1 else "worker"
        return FakeClient(label, *args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", async_client_factory)

    svc = EbayService()
    token_value = "v^1.1.same-for-both"

    # Debug flow
    debug_payload = await svc.debug_refresh_access_token_http(token_value, environment="sandbox")
    assert debug_payload["success"] is True

    # Worker flow
    worker_resp = await svc.refresh_access_token(
        token_value,
        user_id="user-1",
        environment="sandbox",
        source="scheduled",
    )
    assert worker_resp.access_token == "dummy-access"

    assert captured["debug"] is not None
    assert captured["worker"] is not None

    debug_body = captured["debug"]["data"]
    worker_body = captured["worker"]["data"]

    assert debug_body["grant_type"] == "refresh_token"
    assert worker_body["grant_type"] == "refresh_token"
    assert debug_body["refresh_token"] == token_value
    assert worker_body["refresh_token"] == token_value

    # Sanity check: both used the same token URL
    assert captured["debug"]["url"] == captured["worker"]["url"]
