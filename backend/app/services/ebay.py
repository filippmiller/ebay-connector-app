import base64
import hashlib
import httpx
import asyncio
import json
from typing import Optional, Dict, Any, List, Tuple, Iterable
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from urllib.parse import urlencode
from fastapi import HTTPException, status
from app.config import settings
from app.models.ebay import EbayTokenResponse
from app.services.database import db
from app.services.ebay_connect_logger import ebay_connect_logger
from app.utils.logger import logger, ebay_logger
from app.utils import crypto


def _mask_prefix(value: Optional[str], length: int = 12) -> str:
    """Return a short, non-sensitive preview of a token for logs.

    We only log the first ``length`` characters and never the full value.
    """
    if not value:
        return "<none>"
    return value[:length] + ("…" if len(value) > length else "")


def _looks_like_ebay_refresh_token(token: Optional[str]) -> bool:
    """Heuristic check that a token looks like an eBay refresh token.

    All tokens we receive from eBay today start with ``"v^"``.
    """
    return isinstance(token, str) and token.startswith("v^")

ORDERS_PAGE_LIMIT = 200          # Fulfillment API max
TRANSACTIONS_PAGE_LIMIT = 200    # Finances API max
DISPUTES_PAGE_LIMIT = 100        # Fulfillment API max
OFFERS_PAGE_LIMIT = 100          # Inventory API max
MESSAGES_HEADERS_LIMIT = 200     # Trading API max for headers
MESSAGES_BODIES_BATCH = 10       # Trading API hard limit for bodies

ORDERS_CONCURRENCY = 6
TRANSACTIONS_CONCURRENCY = 5
DISPUTES_CONCURRENCY = 5
OFFERS_CONCURRENCY = 6
MESSAGES_CONCURRENCY = 5


@dataclass
class _AppTokenCacheEntry:
    access_token: str
    expires_at: datetime  # UTC


# In-memory cache for application access tokens, keyed by (environment, scopes_key).
# scopes_key is a deterministic, normalized representation of the scopes list.
_APP_TOKEN_CACHE: Dict[Tuple[str, str], _AppTokenCacheEntry] = {}
# Safety margin (in seconds) subtracted from expires_in so we refresh a bit early.
_APP_TOKEN_SAFETY_MARGIN_SECONDS = 120


class EbayService:
    
    def __init__(self):
        self.sandbox_auth_url = "https://auth.sandbox.ebay.com/oauth2/authorize"
        self.sandbox_token_url = "https://api.sandbox.ebay.com/identity/v1/oauth2/token"
        
        self.production_auth_url = "https://auth.ebay.com/oauth2/authorize"
        self.production_token_url = "https://api.ebay.com/identity/v1/oauth2/token"

    # ------------------------------------------------------------------
    # Notification API helpers (destinations, subscriptions, tests)
    # ------------------------------------------------------------------

    async def _notification_api_request(
        self,
        method: str,
        path: str,
        access_token: str,
        *,
        json_body: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        timeout: float = 30.0,
        debug_log: Optional[List[str]] = None,
    ) -> httpx.Response:
        """Low-level helper for calling the Notification API.

        Raises HTTPException on non-2xx responses with the full error payload
        included in ``detail`` for easier surfacing in the admin UI.
        """

        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="eBay access token required for Notification API",
            )

        base_url = settings.ebay_api_base_url.rstrip("/")
        url = f"{base_url}{path}"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        # Structured logging for admin Notifications test endpoint.
        # Authorization and any sensitive headers are redacted.
        if debug_log is not None:
            debug_log.append(f"[req] {method.upper()} {url}")
            debug_log.append("[req] headers:")
            masked_headers = {}
            for k, v in headers.items():
                lk = k.lower()
                if lk == "authorization":
                    masked = "***REDACTED***"
                elif "secret" in lk or "token" in lk:
                    masked = "***REDACTED***"
                else:
                    masked = v
                masked_headers[k] = masked
                debug_log.append(f"  {k}: {masked}")

            debug_log.append("[req] body:")
            if json_body is not None:
                try:
                    body_str = json.dumps(json_body, indent=2, sort_keys=True)
                except Exception:
                    body_str = str(json_body)
                for line in body_str.splitlines() or [""]:
                    debug_log.append(f"  {line}")
            else:
                debug_log.append("  <no body>")

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.request(method, url, headers=headers, json=json_body, params=params)
        except httpx.RequestError as exc:
            logger.error("Notification API request error %s %s: %s", method, url, exc, exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Notification API request error: {exc}",
            )

        # Parse body once so we can both log and surface it on errors.
        try:
            body = resp.json()
        except Exception:
            body = resp.text

        if debug_log is not None:
            debug_log.append(f"[res] status: {resp.status_code}")
            # Response headers (with any sensitive values redacted)
            debug_log.append("[res] headers:")
            resp_headers = {}
            for k, v in resp.headers.items():
                lk = k.lower()
                if lk == "set-cookie" or "token" in lk or "authorization" in lk:
                    masked = "***REDACTED***"
                else:
                    masked = v
                resp_headers[k] = masked
                debug_log.append(f"  {k}: {masked}")

            # Response body
            debug_log.append("[res] body:")
            if isinstance(body, (dict, list)):
                try:
                    pretty = json.dumps(body, indent=2, sort_keys=True)
                except Exception:
                    pretty = str(body)
            else:
                # Non-JSON body; best-effort text representation
                try:
                    pretty = str(body)
                except Exception:
                    pretty = f"<non-text body of type {type(body).__name__}>"
            for line in pretty.splitlines() or [""]:
                debug_log.append(f"  {line}")

        if 200 <= resp.status_code < 300:
            return resp

        logger.error(
            "Notification API error %s %s status=%s body=%s",
            method,
            url,
            resp.status_code,
            body,
        )
        raise HTTPException(
            status_code=resp.status_code,
            detail={"message": "Notification API error", "status_code": resp.status_code, "body": body},
        )

    async def ensure_notification_destination(
        self,
        access_token: str,
        endpoint_url: str,
        verification_token: Optional[str] = None,
        debug_log: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Ensure a Notification API destination exists for the given endpoint.

        Returns a dict containing at least ``destinationId`` and ``endpoint``.
        """

        # List existing destinations
        resp = await self._notification_api_request(
            "GET",
            "/commerce/notification/v1/destination",
            access_token,
            debug_log=debug_log,
        )
        try:
            data = resp.json() or {}
        except Exception:
            # Some Notification API endpoints may return 204/empty bodies even on success.
            # In that case we treat it as "no destinations" rather than failing the test.
            data = {}
        destinations = data.get("destinations") or data.get("destinationConfigurations") or []

        existing = None
        for dest in destinations:
            delivery_cfg = dest.get("deliveryConfig") or {}
            if delivery_cfg.get("endpoint") == endpoint_url:
                existing = dest
                break

        # If a destination already exists but is disabled, try to re-enable it
        # instead of creating a brand new configuration. This keeps the
        # Notification API diagnostics cleaner and avoids "duplicate
        # destination" errors.
        if existing:
            dest_status = (existing.get("status") or "").upper()
            dest_id = existing.get("destinationId") or existing.get("id")
            if dest_id and dest_status != "ENABLED":
                delivery_cfg = existing.get("deliveryConfig") or {}
                body = {
                    "name": existing.get("name") or "OneMillionParts Notifications",
                    "status": "ENABLED",
                    "deliveryConfig": {
                        "endpoint": endpoint_url,
                        # Prefer explicit verification_token, fall back to the
                        # one already stored on the destination if present.
                        "verificationToken": verification_token
                        or delivery_cfg.get("verificationToken"),
                        "protocol": "HTTPS",
                        "payloadFormat": "JSON",
                        "status": "ENABLED",
                    },
                }
                update_resp = await self._notification_api_request(
                    "PUT",
                    f"/commerce/notification/v1/destination/{dest_id}",
                    access_token,
                    json_body=body,
                    debug_log=debug_log,
                )
                # Some variants may return 204 No Content; fall back to the
                # existing object with updated status/config in that case.
                try:
                    updated = update_resp.json() or {}
                except Exception:
                    updated = existing or {}
                if isinstance(updated, dict):
                    updated.setdefault("deliveryConfig", body["deliveryConfig"])
                    updated["status"] = "ENABLED"
                return updated

            return existing

        if not verification_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="EBAY_NOTIFICATION_VERIFICATION_TOKEN is required to create a destination",
            )

        body = {
            "name": "OneMillionParts Notifications",
            "status": "ENABLED",
            "deliveryConfig": {
                "endpoint": endpoint_url,
                "verificationToken": verification_token,
                "protocol": "HTTPS",
                "payloadFormat": "JSON",
                # Some variants of the Notifications API expect status on the deliveryConfig as well.
                # Including it here is harmless and satisfies both shapes.
                "status": "ENABLED",
            },
        }

        created_resp = await self._notification_api_request(
            "POST",
            "/commerce/notification/v1/destination",
            access_token,
            json_body=body,
            debug_log=debug_log,
        )
        try:
            created = created_resp.json() or {}
        except Exception:
            # If Notification API happens to return 204/empty on create, at
            # least return a minimal shape so Diagnostics can proceed.
            created = {
                "status": "ENABLED",
                "deliveryConfig": body["deliveryConfig"],
            }
        return created

    async def ensure_notification_subscription(
        self,
        access_token: str,
        destination_id: str,
        topic_id: str,
        debug_log: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Ensure a subscription exists for ``topic_id`` + ``destination_id``.

        Returns the subscription JSON object.
        """

        # Fetch topic metadata to determine schemaVersion and scope.
        topic_resp = await self._notification_api_request(
            "GET",
            f"/commerce/notification/v1/topic/{topic_id}",
            access_token,
            debug_log=debug_log,
        )
        try:
            topic_json = topic_resp.json() or {}
        except Exception:
            topic_json = {}
        schema_versions = topic_json.get("supportedSchemaVersions") or []
        if isinstance(schema_versions, list) and schema_versions:
            schema_version = str(schema_versions[-1])
        else:
            schema_version = str(topic_json.get("schemaVersion") or "1.0")

        # Decide which token to use for subscription operations.
        topic_scope = str(topic_json.get("scope") or "").upper()
        use_app_token = topic_scope == "APPLICATION" or topic_id == "MARKETPLACE_ACCOUNT_DELETION"
        sub_token = access_token

        if use_app_token:
            if debug_log is not None:
                debug_log.append(
                    f"[topic] scope={topic_scope or 'UNKNOWN'}; using application access token for subscription calls",
                )
            # Obtain an application access token via client_credentials grant.
            sub_token = await self.get_app_access_token()
        elif debug_log is not None:
            debug_log.append(
                f"[topic] scope={topic_scope or 'UNKNOWN'}; using user access token for subscription calls",
            )

        # List subscriptions and look for a match
        subs_resp = await self._notification_api_request(
            "GET",
            "/commerce/notification/v1/subscription",
            sub_token,
            debug_log=debug_log,
        )
        try:
            subs_json = subs_resp.json() or {}
        except Exception:
            subs_json = {}
        subscriptions = subs_json.get("subscriptions") or []

        existing = None
        for sub in subscriptions:
            if sub.get("topicId") == topic_id and sub.get("destinationId") == destination_id:
                existing = sub
                break

        payload_cfg = {
            "format": "JSON",
            "deliveryProtocol": "HTTPS",
            "schemaVersion": schema_version,
        }

        if existing is None:
            body = {
                "topicId": topic_id,
                "destinationId": destination_id,
                "status": "ENABLED",
                "payload": payload_cfg,
            }
            create_resp = await self._notification_api_request(
                "POST",
                "/commerce/notification/v1/subscription",
                sub_token,
                json_body=body,
                debug_log=debug_log,
            )

            created_sub: Dict[str, Any] | None = None
            sub_id: Optional[str] = None

            # First, try to read subscriptionId from the JSON body (if any).
            try:
                body_json = create_resp.json() or {}
                if isinstance(body_json, dict):
                    created_sub = body_json
                    sub_id = (
                        body_json.get("subscriptionId")
                        or body_json.get("id")
                    )
            except Exception:
                # Some variants of the API may return 201 + empty body.
                created_sub = None

            # If subscriptionId was not present in the body, try the Location header.
            if not sub_id:
                location = create_resp.headers.get("location") or create_resp.headers.get("Location")
                if location:
                    # Expected shape: .../subscription/{id}
                    try:
                        sub_id = location.rstrip("/").split("/")[-1]
                        if debug_log is not None:
                            debug_log.append(
                                f"[subscription] Parsed subscriptionId from Location header: {sub_id}",
                            )
                    except Exception:
                        sub_id = None

            # If we have a subscriptionId, ensure the returned object carries it.
            if sub_id:
                if created_sub is None or not isinstance(created_sub, dict):
                    created_sub = {}
                created_sub.setdefault("subscriptionId", sub_id)
                created_sub.setdefault("id", sub_id)
                created_sub.setdefault("topicId", topic_id)
                created_sub.setdefault("destinationId", destination_id)
                created_sub.setdefault("status", "ENABLED")
                return created_sub

            # Last resort: re-fetch subscriptions and pick the one matching topic+destination.
            if debug_log is not None:
                debug_log.append(
                    "[subscription] Could not determine subscriptionId from create response; refetching list",
                )
            refetch_resp = await self._notification_api_request(
                "GET",
                "/commerce/notification/v1/subscription",
                sub_token,
                debug_log=debug_log,
            )
            try:
                refetch_json = refetch_resp.json() or {}
            except Exception:
                refetch_json = {}
            refetch_subs = refetch_json.get("subscriptions") or []
            for sub in refetch_subs:
                if sub.get("topicId") == topic_id and sub.get("destinationId") == destination_id:
                    return sub

            # If we still do not have a subscription object, surface a clear error
            # instead of returning a dict without subscriptionId.
            msg = (
                "Notification API created a subscription but subscriptionId could not "
                "be resolved from the response or subsequent list call."
            )
            if debug_log is not None:
                debug_log.append(f"[subscription] ERROR: {msg}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "message": msg,
                    "status_code": 500,
                },
            )

        # Ensure it is enabled / up to date
        sub_id = existing.get("subscriptionId") or existing.get("id")
        if not sub_id:
            return existing

        body = {
            "topicId": topic_id,
            "destinationId": destination_id,
            "status": "ENABLED",
            "payload": payload_cfg,
        }
        await self._notification_api_request(
            "PUT",
            f"/commerce/notification/v1/subscription/{sub_id}",
            sub_token,
            json_body=body,
            debug_log=debug_log,
        )
        existing["status"] = "ENABLED"
        existing["payload"] = payload_cfg
        return existing

    async def get_notification_topic_metadata(
        self,
        access_token: str,
        topic_id: str,
        debug_log: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Fetch Notification API topic metadata for a given topicId.

        This is a small wrapper around ``GET /commerce/notification/v1/topic/{topicId}``
        so that callers (e.g. admin diagnostics and test endpoints) can inspect
        fields like ``scope`` and ``supportedSchemaVersions`` without duplicating
        the raw HTTP call logic.
        """

        resp = await self._notification_api_request(
            "GET",
            f"/commerce/notification/v1/topic/{topic_id}",
            access_token,
            debug_log=debug_log,
        )
        try:
            data = resp.json() or {}
        except Exception:
            data = {}
        if not isinstance(data, dict):
            data = {}
        return data

    async def test_notification_subscription(
        self,
        access_token: str,
        subscription_id: str,
        debug_log: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Trigger Notification API test for a subscription."""

        resp = await self._notification_api_request(
            "POST",
            f"/commerce/notification/v1/subscription/{subscription_id}/test",
            access_token,
            json_body={},
            debug_log=debug_log,
        )
        # eBay usually returns 204 No Content; normalize to a simple payload.
        return {"status_code": resp.status_code}

    async def get_notification_status(
        self,
        access_token: str,
        endpoint_url: str,
        topic_id: str,
        debug_log: Optional[List[str]] = None,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """Inspect current Notification destination + subscription state.

        Returns (destination, subscription) where either element may be None.
        """

        # Destinations
        dest_resp = await self._notification_api_request(
            "GET",
            "/commerce/notification/v1/destination",
            access_token,
            debug_log=debug_log,
        )
        try:
            dest_json = dest_resp.json() or {}
        except Exception:
            dest_json = {}
        destinations = dest_json.get("destinations") or dest_json.get("destinationConfigurations") or []

        dest = None
        for d in destinations:
            delivery_cfg = d.get("deliveryConfig") or {}
            if delivery_cfg.get("endpoint") == endpoint_url:
                dest = d
                break

        # Subscriptions
        sub = None
        if dest is not None:
            dest_id = dest.get("destinationId") or dest.get("id")
            sub_resp = await self._notification_api_request(
                "GET",
                "/commerce/notification/v1/subscription",
                access_token,
                debug_log=debug_log,
            )
            try:
                sub_json = sub_resp.json() or {}
            except Exception:
                sub_json = {}
            subs = sub_json.get("subscriptions") or []
            for s in subs:
                if s.get("topicId") == topic_id and s.get("destinationId") == dest_id:
                    sub = s
                    break

        return dest, sub
    
    @property
    def auth_url(self) -> str:
        is_sandbox = settings.EBAY_ENVIRONMENT == "sandbox"
        return self.sandbox_auth_url if is_sandbox else self.production_auth_url
    
    @property
    def token_url(self) -> str:
        is_sandbox = settings.EBAY_ENVIRONMENT == "sandbox"
        return self.sandbox_token_url if is_sandbox else self.production_token_url
    
    def get_authorization_url(self, redirect_uri: str, state: Optional[str] = None, scopes: Optional[List[str]] = None, environment: str = "production") -> str:
        """
        Generate eBay OAuth authorization URL.

        In normal flows, the `scopes` list is populated from the DB-backed
        `ebay_scope_definitions` catalog by the /ebay/auth/start endpoint.
        The hardcoded scope list below is used only as a last-resort fallback
        when the caller passes an empty/None scopes list.

        Args:
            redirect_uri: OAuth redirect URI (frontend callback URL, logged for diagnostics)
            state: OAuth state parameter (opaque JSON for CSRF + metadata)
            scopes: List of OAuth scopes. If empty/None, a conservative fallback list is applied.
            environment: 'sandbox' or 'production' (default: 'production')
        """
        # Temporarily set environment to get correct credentials
        original_env = settings.EBAY_ENVIRONMENT
        settings.EBAY_ENVIRONMENT = environment
        
        try:
            if not settings.ebay_client_id:
                ebay_logger.log_ebay_event(
                    "authorization_url_error",
                    "eBay Client ID not configured",
                    status="error",
                    error="EBAY_CLIENT_ID not set in environment"
                )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="eBay credentials not configured"
                )
            
            if not settings.ebay_runame:
                ebay_logger.log_ebay_event(
                    "authorization_url_error",
                    "eBay RuName not configured",
                    status="error",
                    error="EBAY_RUNAME not set in environment"
                )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="eBay RuName not configured"
                )
            
            # LAST-RESORT FALLBACK: if caller gave us no scopes at all, apply a minimal
            # seller set so the flow can still succeed. Under normal circumstances
            # /ebay/auth/start populates scopes from ebay_scope_definitions instead.
            if not scopes:
                scopes = [
                    "https://api.ebay.com/oauth/api_scope",  # Base scope for Identity API (MUST be first)
                    "https://api.ebay.com/oauth/api_scope/sell.account",
                    "https://api.ebay.com/oauth/api_scope/sell.fulfillment",  # For Orders
                    "https://api.ebay.com/oauth/api_scope/sell.finances",  # For Transactions
                    "https://api.ebay.com/oauth/api_scope/sell.inventory",  # For Inventory/Offers
                    "https://api.ebay.com/oauth/api_scope/commerce.notification.subscription",  # For Notification API
                ]
            
            # Ensure base scope is first (required for Identity API)
            base_scope = "https://api.ebay.com/oauth/api_scope"
            if base_scope in scopes:
                scopes.remove(base_scope)
            scopes.insert(0, base_scope)
            
            # Remove any trailing spaces and empty strings
            scopes = [s.strip() for s in scopes if s.strip()]
            
            params = {
                "client_id": settings.ebay_client_id,
                "redirect_uri": settings.ebay_runame,
                "response_type": "code",
                "scope": " ".join(scopes)
            }
            
            if state:
                params["state"] = state
            
            # Use correct auth URL based on environment
            if environment == "sandbox":
                auth_base_url = self.sandbox_auth_url
            else:
                auth_base_url = self.production_auth_url
            
            auth_url = f"{auth_base_url}?{urlencode(params)}"
            
            ebay_logger.log_ebay_event(
                "authorization_url_generated",
                f"Generated eBay authorization URL ({environment}) with RuName: {settings.ebay_runame}",
                request_data={
                    "environment": environment,
                    "redirect_uri": settings.ebay_runame,
                    "frontend_callback": redirect_uri,
                    "scopes": scopes,
                    "state": state
                },
                status="success"
            )
            
            logger.info(f"Generated eBay {environment} authorization URL with RuName: {settings.ebay_runame} (frontend callback: {redirect_uri})")
            return auth_url
        finally:
            # Restore original environment
            settings.EBAY_ENVIRONMENT = original_env
    
    async def exchange_code_for_token(
        self,
        code: str,
        redirect_uri: str,
        *,
        user_id: Optional[str] = None,
        environment: Optional[str] = None
    ) -> EbayTokenResponse:
        target_env = environment or settings.EBAY_ENVIRONMENT
        original_env = settings.EBAY_ENVIRONMENT
        settings.EBAY_ENVIRONMENT = target_env

        try:
            if not settings.ebay_client_id or not settings.ebay_cert_id:
                ebay_logger.log_ebay_event(
                    "token_exchange_error",
                    "eBay credentials not configured",
                    status="error",
                    error="EBAY_CLIENT_ID or EBAY_CERT_ID not set"
                )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="eBay credentials not configured"
                )

            credentials = f"{settings.ebay_client_id}:{settings.ebay_cert_id}"
            encoded_credentials = base64.b64encode(credentials.encode()).decode()

            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": f"Basic {encoded_credentials}"
            }

            data = {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.ebay_runame
            }

            masked_headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": "Basic **** (masked)"
            }

            request_payload = {
                "method": "POST",
                "url": self.token_url,
                "headers": masked_headers,
                "body": {"grant_type": "authorization_code", "redirect_uri": redirect_uri, "code": code[:6] + "..." if len(code) > 6 else code}
            }

            ebay_logger.log_ebay_event(
                "token_exchange_request",
                f"Exchanging authorization code for access token ({target_env})",
                request_data={
                    "environment": target_env,
                    "grant_type": "authorization_code",
                    "redirect_uri": redirect_uri,
                    "code": code[:10] + "..." if len(code) > 10 else code,
                    "client_id": settings.ebay_client_id
                }
            )

            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        self.token_url,
                        headers=headers,
                        data=data,
                        timeout=30.0
                    )

                response_body: Any
                try:
                    response_body = response.json()
                except ValueError:
                    response_body = response.text

                ebay_logger.log_ebay_event(
                    "token_exchange_response",
                    f"Received token exchange response with status {response.status_code}",
                    response_data={
                        "status_code": response.status_code,
                        "response_body": response_body if isinstance(response_body, (dict, list)) else str(response_body)[:5000]
                    }
                )

                if response.status_code != 200:
                    error_detail = response_body if isinstance(response_body, str) else response.text
                    ebay_connect_logger.log_event(
                        user_id=user_id,
                        environment=target_env,
                        action="token_exchange_failed",
                        request=request_payload,
                        response={
                            "status": response.status_code,
                            "headers": dict(response.headers),
                            "body": response_body,
                        },
                        error=str(error_detail)[:2000]
                    )
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Failed to exchange code for token: {error_detail}"
                    )

                token_data = response_body if isinstance(response_body, dict) else response.json()

                ebay_logger.log_ebay_event(
                    "token_exchange_success",
                    "Successfully obtained eBay access token",
                    response_data={
                        "access_token": token_data.get("access_token"),
                        "token_type": token_data.get("token_type"),
                        "expires_in": token_data.get("expires_in"),
                        "has_refresh_token": "refresh_token" in token_data
                    },
                    status="success"
                )

                ebay_connect_logger.log_event(
                    user_id=user_id,
                    environment=target_env,
                    action="exchange_code_for_token",
                    request=request_payload,
                    response={
                        "status": response.status_code,
                        "headers": dict(response.headers),
                        "body": token_data,
                    }
                )

                logger.info("Successfully exchanged authorization code for eBay access token")

                return EbayTokenResponse(**token_data)

            except httpx.RequestError as e:
                error_msg = f"HTTP request failed: {str(e)}"
                ebay_logger.log_ebay_event(
                    "token_exchange_error",
                    "HTTP request error during token exchange",
                    status="error",
                    error=error_msg
                )
                ebay_connect_logger.log_event(
                    user_id=user_id,
                    environment=target_env,
                    action="token_exchange_error",
                    request=request_payload,
                    response=None,
                    error=error_msg
                )
                logger.error(error_msg)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=error_msg
                )
        finally:
            settings.EBAY_ENVIRONMENT = original_env

    def _build_refresh_token_request_components(
        self,
        refresh_token: str,
        *,
        environment: Optional[str] = None,
        caller: Optional[str] = None,
    ) -> tuple[str, Dict[str, str], Dict[str, str], Dict[str, Any]]:
        """Build common headers/body/payload for the refresh_token grant.

        All refresh flows (worker, admin refresh, debug) must go through this
        helper so we can guarantee that:
        - encrypted blobs (``ENC:v1:…``) are decrypted exactly once;
        - no ``ENC:`` value is ever sent to eBay;
        - the final token looks like a real eBay refresh token (starts with
          ``"v^"``);
        - failures surface as a deterministic ``decrypt_failed`` error.

        The returned ``request_payload`` is used only for admin-only
        diagnostics (connect logs + Workers UI). It contains the exact headers
        and body that are sent to eBay and must not be exposed outside trusted
        admin contexts.
        """
        if not settings.ebay_client_id or not settings.ebay_cert_id:
            ebay_logger.log_ebay_event(
                "token_refresh_error",
                "eBay credentials not configured",
                status="error",
                error="EBAY_CLIENT_ID or EBAY_CERT_ID not set",
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "code": "config_error",
                    "message": "eBay credentials not configured",
                },
            )

        caller_label = caller or "unknown"

        # ------------------------------------------------------------------
        # Normalize and, if necessary, decrypt an ENC:v1: blob.
        # ------------------------------------------------------------------
        raw_token = refresh_token or ""
        decrypted_token = raw_token

        if isinstance(raw_token, str) and raw_token.startswith("ENC:v1:"):
            try:
                decrypted = crypto.decrypt(raw_token)
            except Exception as exc:  # pragma: no cover - defensive
                msg = f"Failed to decrypt refresh token for caller={caller_label}: {exc}"
                logger.error(msg)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail={"code": "decrypt_failed", "message": msg},
                )
            decrypted_token = decrypted

        # Final safety checks: non-empty, no ENC prefix, and looks like eBay token.
        if not isinstance(decrypted_token, str) or not decrypted_token:
            msg = f"Missing or empty refresh token for caller={caller_label}"
            logger.error(msg)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"code": "decrypt_failed", "message": msg},
            )

        if decrypted_token.startswith("ENC:v1:"):
            msg = (
                "Refresh token still encrypted after decrypt attempt; "
                f"caller={caller_label}. Account requires reconnect."
            )
            logger.error(msg)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"code": "decrypt_failed", "message": msg},
            )

        if not _looks_like_ebay_refresh_token(decrypted_token):
            msg = (
                "Refresh token does not look like an eBay token "
                f"(prefix={_mask_prefix(decrypted_token)}) for caller={caller_label}. "
                "Account requires reconnect."
            )
            logger.error(msg)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"code": "decrypt_failed", "message": msg},
            )

        final_token = decrypted_token

        # Log a short diagnostic so we can prove worker vs debug use the same
        # value without leaking secrets.
        logger.info(
            "token_refresh_path caller=%s input_prefix=%s decrypted_prefix=%s final_prefix=%s",
            caller_label,
            _mask_prefix(raw_token),
            _mask_prefix(decrypted_token),
            _mask_prefix(final_token),
        )

        target_env = environment or settings.EBAY_ENVIRONMENT or "sandbox"

        credentials = f"{settings.ebay_client_id}:{settings.ebay_cert_id}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {encoded_credentials}",
        }

        data = {
            "grant_type": "refresh_token",
            "refresh_token": final_token,
        }

        request_payload = {
            "method": "POST",
            "url": self.token_url,
            "headers": headers,
            "body": data,
        }

        return target_env, headers, data, request_payload

    async def refresh_access_token(
        self,
        refresh_token: str,
        *,
        user_id: Optional[str] = None,
        environment: Optional[str] = None,
        source: Optional[str] = None,
    ) -> EbayTokenResponse:
        """Refresh an access token using a long-lived refresh token.

        When user_id/environment are provided, this will also write a detailed
        entry to ebay_connect_logs with the HTTP request/response used for
        the refresh (credentials are masked in the request payload).
        """
        target_env, headers, data, request_payload = self._build_refresh_token_request_components(
            refresh_token,
            environment=environment,
            caller=source or "worker_or_admin",
        )

        ebay_logger.log_ebay_event(
            "token_refresh_request",
            "Refreshing eBay access token",
            request_data={
                "grant_type": "refresh_token",
                "refresh_token": "<hidden>",
                "environment": target_env,
            },
        )

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.token_url,
                    headers=headers,
                    data=data,
                    timeout=30.0,
                )

                # Try to capture a structured body for logging
                try:
                    response_body: Any = response.json()
                except ValueError:
                    response_body = response.text

                if response.status_code != 200:
                    error_detail = response_body if isinstance(response_body, str) else response.text

                    ebay_logger.log_ebay_event(
                        "token_refresh_failed",
                        f"Token refresh failed with status {response.status_code}",
                        response_data={"error": error_detail},
                        status="error",
                        error=error_detail,
                    )

                    # Optional connect log entry – only if we have user context
                    if user_id is not None:
                        ebay_connect_logger.log_event(
                            user_id=user_id,
                            environment=target_env,
                            action="token_refresh_failed",
                            request=request_payload,
                            response={
                                "status": response.status_code,
                                "headers": dict(response.headers),
                                "body": response_body
                                if isinstance(response_body, (dict, list))
                                else str(response_body)[:5000],
                            },
                            error=str(error_detail)[:2000],
                            source=source,
                        )

                    raise HTTPException(
                        status_code=response.status_code,
                        detail=f"Failed to refresh token: {error_detail}",
                    )

                token_data = response_body if isinstance(response_body, dict) else response.json()

                ebay_logger.log_ebay_event(
                    "token_refresh_success",
                    "Successfully refreshed eBay access token",
                    response_data={
                        "access_token": token_data.get("access_token"),
                        "expires_in": token_data.get("expires_in"),
                    },
                    status="success",
                )

                # Optional connect log entry for successful refresh
                if user_id is not None:
                    ebay_connect_logger.log_event(
                        user_id=user_id,
                        environment=target_env,
                        action="token_refreshed",
                        request=request_payload,
                        response={
                            "status": response.status_code,
                            "headers": dict(response.headers),
                            # Store full parsed JSON body; may include tokens
                            "body": token_data,
                        },
                        source=source,
                    )

                logger.info("Successfully refreshed eBay access token")

                return EbayTokenResponse(**token_data)

        except httpx.RequestError as e:
            error_msg = f"HTTP request failed: {str(e)}"
            ebay_logger.log_ebay_event(
                "token_refresh_error",
                "HTTP request error during token refresh",
                status="error",
                error=error_msg,
            )

            # Optional connect log entry for network-level errors
            if user_id is not None:
                ebay_connect_logger.log_event(
                    user_id=user_id,
                    environment=target_env,
                    action="token_refresh_error",
                    request=request_payload,
                    response=None,
                    error=error_msg,
                    source=source,
                )

            logger.error(error_msg)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_msg,
            )

    async def debug_refresh_access_token_http(
        self,
        refresh_token: str,
        *,
        environment: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Perform a refresh_token call and capture raw HTTP request/response.

        This method is used exclusively by the admin debug endpoint. It shares
        the same request-building logic with ``refresh_access_token`` but does
        **not** write anything to normal logs or ebay_connect_logs and instead
        returns a structured payload suitable for a "terminal"-style UI.
        """
        target_env, headers, data, _ = self._build_refresh_token_request_components(
            refresh_token,
            environment=environment,
            caller="debug",
        )

        # Urlencode the body for human-friendly display.
        from urllib.parse import urlencode as _urlencode  # local import to avoid polluting namespace

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.token_url,
                    headers=headers,
                    data=data,
                    timeout=30.0,
                )
        except httpx.RequestError as exc:
            # Network-level error: we can still show the intended request.
            request_text_body = _urlencode(data)
            request_info = {
                "method": "POST",
                "url": self.token_url,
                "headers": dict(headers),
                "body": request_text_body,
            }
            return {
                "environment": target_env,
                "success": False,
                "error": "request_error",
                "error_description": str(exc),
                "request": request_info,
                "response": None,
            }

        # Build request details from the real httpx.Request object.
        req = response.request
        try:
            raw_req_body = req.content or b""
        except Exception:  # pragma: no cover - very defensive
            raw_req_body = b""
        try:
            req_body_text = (
                raw_req_body.decode("utf-8", errors="replace")
                if isinstance(raw_req_body, (bytes, bytearray))
                else str(raw_req_body)
            )
        except Exception:  # pragma: no cover - defensive
            req_body_text = "<unable to decode request body>"

        request_info = {
            "method": req.method,
            "url": str(req.url),
            "headers": dict(req.headers),
            "body": req_body_text,
        }

        # Build response details.
        try:
            resp_text = response.text
        except Exception:  # pragma: no cover - defensive
            resp_text = "<unable to read response body>"

        response_info = {
            "status_code": response.status_code,
            "reason": response.reason_phrase,
            "headers": dict(response.headers),
            "body": resp_text,
        }

        error: Optional[str] = None
        error_description: Optional[str] = None
        if response.status_code != 200:
            try:
                body_json = response.json()
                if isinstance(body_json, dict):
                    err_val = body_json.get("error")
                    if isinstance(err_val, str):
                        error = err_val
                    err_desc = body_json.get("error_description")
                    if isinstance(err_desc, str):
                        error_description = err_desc
            except Exception:  # pragma: no cover - defensive
                pass

        return {
            "environment": target_env,
            "success": response.status_code == 200,
            "error": error,
            "error_description": error_description,
            "request": request_info,
            "response": response_info,
        }

    async def _get_app_access_token_raw(
        self,
        scopes: Optional[Iterable[str]] = None,
        environment: Optional[str] = None,
    ) -> Tuple[str, Optional[int]]:
        """Low-level helper to obtain an AppToken and its TTL.

        Returns (access_token, expires_in_seconds). Callers that do not care
        about caching can ignore the second element.
        """
        target_env = environment or settings.EBAY_ENVIRONMENT or "sandbox"
        original_env = settings.EBAY_ENVIRONMENT
        settings.EBAY_ENVIRONMENT = target_env

        try:
            if not settings.ebay_client_id or not settings.ebay_cert_id:
                ebay_logger.log_ebay_event(
                    "app_token_error",
                    "eBay credentials not configured for app token",
                    status="error",
                    error="EBAY_CLIENT_ID or EBAY_CERT_ID not set",
                )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="eBay credentials not configured",
                )

            credentials = f"{settings.ebay_client_id}:{settings.ebay_cert_id}"
            encoded_credentials = base64.b64encode(credentials.encode()).decode()

            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": f"Basic {encoded_credentials}",
            }

            scopes_list: List[str]
            if not scopes:
                scopes_list = ["https://api.ebay.com/oauth/api_scope"]
            else:
                scopes_list = list(scopes)

            # Normalize scopes: strip whitespace and drop empties.
            scopes_list = [s.strip() for s in scopes_list if s and s.strip()]
            scope_str = " ".join(scopes_list)

            data = {
                "grant_type": "client_credentials",
                "scope": scope_str,
            }

            masked_headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": "Basic **** (masked)",
            }

            ebay_logger.log_ebay_event(
                "app_token_request",
                "Requesting eBay application access token via client_credentials",
                request_data={
                    "environment": target_env,
                    "scopes": scopes_list,
                    "url": self.token_url,
                    "headers": masked_headers,
                },
            )

            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        self.token_url,
                        headers=headers,
                        data=data,
                    )

                try:
                    response_body: Any = response.json()
                except ValueError:
                    response_body = response.text

                ebay_logger.log_ebay_event(
                    "app_token_response",
                    f"Received app token response with status {response.status_code}",
                    response_data={
                        "status_code": response.status_code,
                        "body": response_body if isinstance(response_body, (dict, list)) else str(response_body)[:2000],
                    },
                )

                if response.status_code != 200:
                    error_detail = response_body if isinstance(response_body, str) else response.text
                    logger.error(f"Failed to obtain eBay application access token: {error_detail}")
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Failed to obtain eBay application access token: {error_detail}",
                    )

                token_data = response_body if isinstance(response_body, dict) else response.json()
                access_token = token_data.get("access_token")
                expires_in: Optional[int] = None
                try:
                    if "expires_in" in token_data:
                        expires_in = int(token_data.get("expires_in"))  # type: ignore[arg-type]
                except Exception:
                    expires_in = None

                if not access_token:
                    logger.error("eBay app token response missing access_token field")
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="eBay app token response missing access_token",
                    )

                logger.info("Successfully obtained eBay application access token")
                return str(access_token), expires_in

            except httpx.RequestError as e:
                error_msg = f"HTTP request failed during app token request: {e}"
                ebay_logger.log_ebay_event(
                    "app_token_error",
                    "HTTP request error during app token request",
                    status="error",
                    error=error_msg,
                )
                logger.error(error_msg)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=error_msg,
                )
        finally:
            settings.EBAY_ENVIRONMENT = original_env

    async def get_browse_app_token(
        self,
        scopes: Optional[List[str]] = None,
        environment: Optional[str] = None,
    ) -> str:
        """Return a cached AppToken suitable for Browse/read-only operations.

        This helper wraps the client_credentials flow with a small in-memory
        cache keyed by (environment, scopes). It is intended for read-heavy
        paths such as Browse API calls used by Sniper/AI workers.
        """
        target_env = environment or settings.EBAY_ENVIRONMENT or "sandbox"

        # Normalize scopes deterministically for cache key purposes.
        if not scopes:
            scopes_list = ["https://api.ebay.com/oauth/api_scope"]
        else:
            scopes_list = [s.strip() for s in scopes if s and s.strip()]
        scopes_key = " ".join(sorted(set(scopes_list)))

        cache_key = (target_env, scopes_key)
        now = datetime.now(timezone.utc)
        entry = _APP_TOKEN_CACHE.get(cache_key)
        if entry and entry.expires_at > now:
            return entry.access_token

        # Cache miss or expired entry: mint a new AppToken and cache it.
        token, expires_in = await self._get_app_access_token_raw(
            scopes=scopes_list,
            environment=target_env,
        )

        ttl = expires_in or 3600  # fall back to a conservative 1h TTL if missing
        safety = min(_APP_TOKEN_SAFETY_MARGIN_SECONDS, max(0, ttl // 2))
        effective_ttl = max(0, ttl - safety)
        expires_at = now + timedelta(seconds=effective_ttl)

        _APP_TOKEN_CACHE[cache_key] = _AppTokenCacheEntry(
            access_token=token,
            expires_at=expires_at,
        )

        return token
    def save_user_tokens(
        self,
        user_id: str,
        token_response: EbayTokenResponse,
        environment: Optional[str] = None,
    ) -> None:
        """
        Save eBay tokens to user record based on environment.

        Args:
            user_id: User ID
            token_response: Token response from eBay
            environment: 'sandbox' or 'production'. If None, uses settings.EBAY_ENVIRONMENT
        """
        env = environment or settings.EBAY_ENVIRONMENT or "sandbox"
        expires_at = datetime.utcnow() + timedelta(seconds=token_response.expires_in)

        if env == "sandbox":
            updates = {
                "ebay_connected": True,
                "ebay_sandbox_access_token": token_response.access_token,
                "ebay_sandbox_refresh_token": token_response.refresh_token,
                "ebay_sandbox_token_expires_at": expires_at,
                "ebay_environment": env,
            }
        else:
            updates = {
                "ebay_connected": True,
                "ebay_access_token": token_response.access_token,
                "ebay_refresh_token": token_response.refresh_token,
                "ebay_token_expires_at": expires_at,
                "ebay_environment": env,
            }

        db.update_user(user_id, updates)

        ebay_logger.log_ebay_event(
            "user_tokens_saved",
            f"Saved eBay tokens for user {user_id}",
            request_data={
                "user_id": user_id,
                "expires_at": expires_at.isoformat(),
            },
            status="success",
        )

        logger.info(f"Saved eBay tokens for user: {user_id}")
    
    async def fetch_orders(self, access_token: str, filter_params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Fetch orders from eBay Fulfillment API
        """
        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="eBay access token required"
            )
        
        api_url = f"{settings.ebay_api_base_url}/sell/fulfillment/v1/order"
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"  # Required for all eBay APIs
        }
        
        params = filter_params or {}
        
        ebay_logger.log_ebay_event(
            "fetch_orders_request",
            f"Fetching orders from eBay ({settings.EBAY_ENVIRONMENT})",
            request_data={
                "environment": settings.EBAY_ENVIRONMENT,
                "api_url": api_url,
                "params": params
            }
        )
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    api_url,
                    headers=headers,
                    params=params,
                    timeout=30.0
                )
                
                if response.status_code != 200:
                    error_detail = response.text
                    try:
                        error_json = response.json()
                        error_detail = str(error_json)
                        logger.error(f"Orders API error {response.status_code}: {error_json}")
                    except:
                        logger.error(f"Orders API error {response.status_code}: {error_detail}")
                    ebay_logger.log_ebay_event(
                        "fetch_orders_failed",
                        f"Failed to fetch orders: {response.status_code}",
                        response_data={"error": error_detail},
                        status="error",
                        error=error_detail
                    )
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=f"Failed to fetch orders: {error_detail}"
                    )
                
                orders_data = response.json()
                
                ebay_logger.log_ebay_event(
                    "fetch_orders_success",
                    f"Successfully fetched {orders_data.get('total', 0)} orders from eBay",
                    response_data={
                        "total_orders": orders_data.get('total', 0),
                        "orders_count": len(orders_data.get('orders', []))
                    },
                    status="success"
                )
                
                logger.info(f"Successfully fetched {orders_data.get('total', 0)} orders from eBay")
                
                return orders_data
                
        except httpx.RequestError as e:
            error_msg = f"HTTP request failed: {str(e)}"
            ebay_logger.log_ebay_event(
                "fetch_orders_error",
                "HTTP request error during orders fetch",
                status="error",
                error=error_msg
            )
            logger.error(error_msg)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_msg
            )
    
    async def get_user_identity(self, access_token: str, user_scopes: Optional[List[str]] = None, 
                                user_email: Optional[str] = None, user_id: Optional[str] = None,
                                environment: Optional[str] = None) -> Dict[str, Any]:
        """
        Get eBay user identity (username, userId) from access token using Identity API
        
        Args:
            access_token: eBay OAuth access token
            user_scopes: Optional list of user scopes (for logging)
            user_email: Optional user email (for logging)
            user_id: Optional user ID (for logging)
            environment: Optional environment override ("sandbox" or "production")
                        If not provided, uses settings.EBAY_ENVIRONMENT
        """
        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="eBay access token required"
            )
        
        # CRITICAL: Validate token is NOT encrypted before making API call
        if access_token.startswith("ENC:"):
            from app.utils.build_info import get_build_number
            build_number = get_build_number()
            logger.error(
                "[get_user_identity] ⚠️⚠️⚠️ CRITICAL: ENCRYPTED TOKEN RECEIVED! "
                "user_id=%s user_email=%s token_prefix=%s... "
                "This will cause 401 errors! Token must be decrypted before calling Identity API. BUILD=%s",
                user_id, user_email, access_token[:30] if access_token else "None",
                build_number,
            )
            return {
                "username": None,
                "userId": None,
                "error": "Access token is encrypted (ENC:v1:...) - decryption failed. Check SECRET_KEY configuration.",
            }
        
        # Determine the correct base URL based on environment
        target_env = environment or settings.EBAY_ENVIRONMENT
        if target_env == "sandbox":
            base_url = "https://api.sandbox.ebay.com"
        else:
            base_url = "https://api.ebay.com"
        
        api_url = f"{base_url}/identity/v1/oauth2/userinfo"
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"  # Required for all eBay APIs
        }
        
        # Log request context
        from app.utils.token_utils import log_request_context
        log_request_context(
            api_name="identity",
            method="GET",
            url=api_url,
            token=access_token,
            user_scopes=user_scopes,
            user_email=user_email,
            user_id=user_id,
            environment=settings.EBAY_ENVIRONMENT
        )
        
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=5.0)) as client:
                response = await client.get(api_url, headers=headers)
                
                logger.info(f"Identity API response status: {response.status_code}")
                logger.info(f"Identity API response headers: {dict(response.headers)}")
                
                if response.status_code != 200:
                    error_detail = response.text
                    try:
                        error_json = response.json()
                        error_detail = str(error_json)
                        logger.error(f"Identity API error {response.status_code}: {error_json}")
                    except:
                        logger.error(f"Identity API error {response.status_code}: {error_detail}")
                    logger.warning(f"Failed to get user identity: {response.status_code} - {error_detail}")
                    return {"username": None, "userId": None, "error": error_detail}
                
                # Log raw response for debugging
                response_text = response.text
                logger.info(f"Identity API raw response: {response_text[:500]}")  # First 500 chars
                
                try:
                    identity_data = response.json()
                    logger.info(f"Identity API parsed JSON: {identity_data}")
                except Exception as json_error:
                    logger.error(f"Failed to parse Identity API response as JSON: {json_error}, raw: {response_text[:200]}")
                    return {"username": None, "userId": None, "error": f"Invalid JSON response: {str(json_error)}"}
                
                # eBay Identity API returns user_id (not userId) and username
                username = identity_data.get("username")
                user_id = identity_data.get("user_id") or identity_data.get("userId")
                
                logger.info(f"Extracted from Identity API - username: {username}, userId: {user_id}")
                
                return {
                    "username": username,
                    "userId": user_id,
                    "accountType": identity_data.get("accountType"),
                    "registrationMarketplaceId": identity_data.get("registrationMarketplaceId"),
                    "raw_response": identity_data  # Include for debugging
                }
        except Exception as e:
            logger.error(f"Error getting user identity: {str(e)}", exc_info=True)
            return {"username": None, "userId": None, "error": str(e)}

    async def fetch_transactions(
        self, 
        access_token: str, 
        filter_params: Optional[Dict[str, Any]] = None, 
        environment: Optional[str] = None,
        *,
        mode: Optional[str] = None,
        correlation_id: Optional[str] = None,
        account_id: Optional[str] = None,
        ebay_user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Fetch transaction records from eBay Finances API
        By default, fetches transactions from the last 90 days
        
        FIXED: Use RSQL filter format: filter=transactionDate:[...] (correct Finances API format)
        
        Args:
            access_token: eBay OAuth access token
            filter_params: Optional filter parameters for the API call
            environment: Optional environment override (sandbox/production)
            mode: Optional mode label ("manual", "automatic", "internal_scheduler")
            correlation_id: Optional correlation ID for tracking this sync batch
            account_id: Optional eBay account ID for logging
            ebay_user_id: Optional eBay user ID for logging
        """
        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="eBay access token required"
            )
        
        # Determine environment and base URL
        target_env = environment or settings.EBAY_ENVIRONMENT
        if target_env == "sandbox":
            base_url = "https://apiz.sandbox.ebay.com"
        else:
            base_url = "https://apiz.ebay.com"

        # Finances API lives on apiz.ebay.com / apiz.sandbox.ebay.com, not api.ebay.com
        api_url = f"{base_url}/sell/finances/v1/transaction"
        
        # CRITICAL: Validate token is NOT encrypted before making API call
        if access_token.startswith("ENC:"):
            logger.error(
                "[fetch_transactions] ⚠️⚠️⚠️ CRITICAL: ENCRYPTED TOKEN RECEIVED! "
                "mode=%s correlation_id=%s account_id=%s ebay_user_id=%s "
                "token_prefix=%s... This will cause 401 errors!",
                mode or "unknown", correlation_id, account_id, ebay_user_id,
                access_token[:30] if access_token else "None",
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Access token is encrypted (ENC:v1:...) - decryption failed. Check SECRET_KEY configuration."
            )
        
        # Redact token from headers for logging
        token_hash = hashlib.sha256(access_token.encode()).hexdigest()[:16] if access_token else "none"
        
        # DIAGNOSTIC: Log token status
        from app.utils.build_info import get_build_number
        build_number = get_build_number()
        logger.info(
            "[fetch_transactions] Token validation: mode=%s correlation_id=%s account_id=%s "
            "ebay_user_id=%s token_hash=%s token_prefix=%s... token_is_decrypted=YES BUILD=%s",
            mode or "unknown", correlation_id, account_id, ebay_user_id,
            token_hash, access_token[:15] if access_token else "None",
            build_number,
        )
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"  # Optional but recommended
        }
        
        # Headers for logging (with token redacted)
        headers_for_log = {
            "Authorization": f"Bearer ***REDACTED*** (hash={token_hash})",
            "Accept": headers["Accept"],
            "X-EBAY-C-MARKETPLACE-ID": headers["X-EBAY-C-MARKETPLACE-ID"],
        }
        
        params = filter_params or {}
        
        # FIXED: Use RSQL filter format: filter=transactionDate:[...]
        if 'filter' not in params:
            from datetime import datetime, timedelta
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=90)
            # Format: YYYY-MM-DDTHH:MM:SS.000Z (RSQL format with brackets)
            params['filter'] = f"transactionDate:[{start_date.strftime('%Y-%m-%dT%H:%M:%S.000Z')}..{end_date.strftime('%Y-%m-%dT%H:%M:%S.000Z')}]"
        
        # Optional: filter by transaction type
        if 'transactionType' not in params:
            # params['transactionType'] = 'SALE'  # Uncomment if you want only sales
            pass
        
        # Enhanced logging with mode, correlation_id, account info
        log_context = {
            "target_env": target_env,
            "base_url": base_url,
            "api_url": api_url,
            "mode": mode or "unknown",
            "correlation_id": correlation_id,
            "account_id": account_id,
            "ebay_user_id": ebay_user_id,
            "token_hash": token_hash,
        }
        
        logger.info(
            "[fetch_transactions] mode=%s correlation_id=%s account_id=%s ebay_user_id=%s "
            "target_env=%s base_url=%s api_url=%s token_hash=%s",
            mode or "unknown", correlation_id, account_id, ebay_user_id,
            target_env, base_url, api_url, token_hash,
        )
        
        ebay_logger.log_ebay_event(
            "fetch_transactions_request",
            f"Fetching transactions from eBay ({target_env})",
            request_data={
                "environment": target_env,
                "global_environment": settings.EBAY_ENVIRONMENT,
                "api_url": api_url,
                "method": "GET",
                "headers": headers_for_log,
                "params": params,
                "mode": mode,
                "correlation_id": correlation_id,
                "account_id": account_id,
                "ebay_user_id": ebay_user_id,
            }
        )
        
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=5.0)) as client:
                response = await client.get(
                    api_url,
                    headers=headers,
                    params=params
                )
                
                if response.status_code == 204:
                    ebay_logger.log_ebay_event(
                        "fetch_transactions_empty",
                        "No transactions found matching the criteria",
                        request_data={
                            "mode": mode,
                            "correlation_id": correlation_id,
                            "account_id": account_id,
                            "ebay_user_id": ebay_user_id,
                        },
                        response_data={
                            "status_code": 204,
                            "mode": mode,
                            "correlation_id": correlation_id,
                            "account_id": account_id,
                        },
                        status="success"
                    )
                    logger.info(
                        "[fetch_transactions] Empty response (204) mode=%s correlation_id=%s account_id=%s",
                        mode or "unknown", correlation_id, account_id,
                    )
                    return {"transactions": [], "total": 0}
                
                if response.status_code != 200:
                    error_detail = response.text
                    try:
                        error_json = response.json()
                        error_detail = str(error_json)
                        logger.error(
                            "[fetch_transactions] API error %d mode=%s correlation_id=%s account_id=%s: %s",
                            response.status_code, mode or "unknown", correlation_id, account_id, error_json,
                        )
                    except:
                        logger.error(
                            "[fetch_transactions] API error %d mode=%s correlation_id=%s account_id=%s: %s",
                            response.status_code, mode or "unknown", correlation_id, account_id, error_detail[:200],
                        )
                    
                    ebay_logger.log_ebay_event(
                        "fetch_transactions_failed",
                        f"Failed to fetch transactions: {response.status_code}",
                        request_data={
                            "mode": mode,
                            "correlation_id": correlation_id,
                            "account_id": account_id,
                            "ebay_user_id": ebay_user_id,
                        },
                        response_data={
                            "status_code": response.status_code,
                            "error": error_detail[:500] if isinstance(error_detail, str) else str(error_detail),
                            "headers": {k: v for k, v in dict(response.headers).items() if not k.lower().startswith('authorization')},
                            "mode": mode,
                            "correlation_id": correlation_id,
                            "account_id": account_id,
                        },
                        status="error",
                        error=error_detail[:500] if isinstance(error_detail, str) else str(error_detail)
                    )
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=f"Failed to fetch transactions (HTTP {response.status_code}): {error_detail[:200]}"
                    )
                
                transactions_data = response.json()
                total_transactions = transactions_data.get('total', 0)
                
                ebay_logger.log_ebay_event(
                    "fetch_transactions_success",
                    f"Successfully fetched transactions from eBay",
                    request_data={
                        "mode": mode,
                        "correlation_id": correlation_id,
                        "account_id": account_id,
                        "ebay_user_id": ebay_user_id,
                    },
                    response_data={
                        "status_code": 200,
                        "total_transactions": total_transactions,
                        "mode": mode,
                        "correlation_id": correlation_id,
                        "account_id": account_id,
                    },
                    status="success"
                )
                
                logger.info(
                    "[fetch_transactions] Success: fetched=%d mode=%s correlation_id=%s account_id=%s",
                    total_transactions, mode or "unknown", correlation_id, account_id,
                )
                
                return transactions_data
                
        except httpx.RequestError as e:
            error_msg = f"HTTP request failed: {str(e)}"
            ebay_logger.log_ebay_event(
                "fetch_transactions_error",
                "HTTP request error during transactions fetch",
                request_data={
                    "mode": mode,
                    "correlation_id": correlation_id,
                    "account_id": account_id,
                    "ebay_user_id": ebay_user_id,
                },
                response_data={
                    "mode": mode,
                    "correlation_id": correlation_id,
                    "account_id": account_id,
                },
                status="error",
                error=error_msg
            )
            logger.error(
                "[fetch_transactions] Request error: %s mode=%s correlation_id=%s account_id=%s",
                error_msg, mode or "unknown", correlation_id, account_id,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_msg
            )


    async def sync_all_orders(
        self,
        user_id: str,
        access_token: str,
        run_id: Optional[str] = None,
        ebay_account_id: Optional[str] = None,
        ebay_user_id: Optional[str] = None,
        window_from: Optional[str] = None,
        window_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Synchronize orders from eBay to database with pagination (limit=200).

        If ``window_from``/``window_to`` are provided, they define the inclusive
        ``lastmodifieddate`` window used for Fulfillment search via an RSQL
        filter (e.g. ``lastmodifieddate:[start..end]``). When the values are
        missing or cannot be parsed, a conservative default of the last 90 days
        ending at "now" (UTC) is applied.

        Args:
            user_id: User ID
            access_token: eBay OAuth access token
            run_id: Optional run_id for sync event logging
            ebay_account_id: Optional internal eBay account id for tagging
            ebay_user_id: Optional eBay user id for tagging
            window_from: Optional ISO8601 datetime (UTC) for the start of the window
            window_to: Optional ISO8601 datetime (UTC) for the end of the window
        """
        from app.services.ebay_database import ebay_db
        from app.services.sync_event_logger import SyncEventLogger
        import time
        
        # Use provided run_id if available, otherwise create new one
        event_logger = SyncEventLogger(user_id, 'orders', run_id=run_id)
        job_id = ebay_db.create_sync_job(user_id, 'orders')
        start_time = time.time()
        
        try:
            total_fetched = 0
            total_stored = 0
            limit = ORDERS_PAGE_LIMIT
            offset = 0
            has_more = True
            current_page = 0
            max_pages = 200  # Safety limit to prevent infinite loops
            
            # Get user scopes from user object if available
            from app.services.database import db
            user_obj = db.get_user_by_id(user_id)
            user_scopes = []
            user_email = None
            if user_obj:
                user_email = user_obj.email
                # Try to get scopes from ebay_account if available
                from app.services.ebay_account_service import ebay_account_service
                from app.models_sqlalchemy import get_db
                db_session = next(get_db())
                try:
                    accounts = ebay_account_service.get_accounts_by_org(db_session, user_id)
                    if accounts:
                        # Get scopes from first account's authorizations (flatten JSONB array)
                        from app.models_sqlalchemy.models import EbayAuthorization
                        auths = db_session.query(EbayAuthorization).filter(
                            EbayAuthorization.ebay_account_id == accounts[0].id
                        ).all()
                        user_scopes = [s for auth in auths for s in (auth.scopes or [])] if auths else []
                except Exception as e:
                    logger.warning(f"Could not retrieve scopes from account: {e}")
                finally:
                    db_session.close()
            
            # Get user identity for logging "who we are"
            identity = await self.get_user_identity(access_token, user_scopes=user_scopes, 
                                                   user_email=user_email, user_id=user_id)
            username = identity.get("username", "unknown")
            identity_ebay_user_id = identity.get("userId", "unknown")

            # Prefer explicitly provided ebay_user_id (e.g. from worker/account),
            # but fall back to Identity API userId when not provided.
            effective_ebay_user_id = ebay_user_id or identity_ebay_user_id
            
            # Log Identity API errors if any
            if identity.get("error"):
                event_logger.log_error(f"Identity API error: {identity.get('error')}")
                event_logger.log_warning("⚠️ Token may be invalid or missing required scopes. Please reconnect to eBay.")
            
            # Validate scopes and log warnings
            from app.utils.token_utils import validate_scopes, format_scopes_for_display
            scope_validation = validate_scopes(user_scopes, "orders")
            if scope_validation["missing_scopes"]:
                missing_display = format_scopes_for_display(scope_validation["missing_scopes"])
                event_logger.log_warning(f"⚠️ Missing required scopes for Orders API: {missing_display}")

            # Persist context so PostgresEbayDatabase can tag rows
            from app.services.ebay_database import ebay_db

            # Determine effective date window for Fulfillment search and
            # logging. Workers pass ``window_from``/``window_to`` based on a
            # cursor with overlap (e.g. cursor - 30 minutes). We convert those
            # into a concrete ``lastModifiedDate:[start..end]`` filter so that
            # each run only refetches a narrow tail of orders.
            from datetime import datetime, timedelta, timezone

            now_utc = datetime.now(timezone.utc)

            def _parse_iso(dt_str: str) -> Optional[datetime]:
                try:
                    if dt_str.endswith("Z"):
                        dt_str = dt_str.replace("Z", "+00:00")
                    return datetime.fromisoformat(dt_str)
                except Exception:
                    return None

            if window_to:
                end_dt = _parse_iso(window_to) or now_utc
            else:
                end_dt = now_utc

            if window_from:
                start_dt = _parse_iso(window_from) or (end_dt - timedelta(days=90))
            else:
                start_dt = end_dt - timedelta(days=90)

            # Pre-compute ISO strings for the Fulfillment filter so we use a
            # stable, millisecond-truncated representation.
            start_iso = start_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")
            end_iso = end_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")

            event_logger.log_start(f"Starting Orders sync from eBay ({settings.EBAY_ENVIRONMENT}) - using bulk limit={limit}")
            event_logger.log_info(f"=== WHO WE ARE ===")
            event_logger.log_info(f"Connected as: {username} (eBay UserID: {effective_ebay_user_id})")
            event_logger.log_info(f"Environment: {settings.EBAY_ENVIRONMENT}")
            event_logger.log_info(
                f"API Configuration: Fulfillment API v1, max batch size: {limit} orders per request"
            )
            event_logger.log_info(
                f"Date window: {start_dt.strftime('%Y-%m-%dT%H:%M:%S.000Z')}.."
                f"{end_dt.strftime('%Y-%m-%dT%H:%M:%S.000Z')}"
            )
            event_logger.log_info(f"Safety limit: max {max_pages} pages")
            logger.info(f"Starting full order sync for user {user_id} ({username}) with limit={limit}")
            
            await asyncio.sleep(0.5)
            
            while has_more:
                # Safety check: max pages limit
                if current_page >= max_pages:
                    event_logger.log_warning(f"Reached safety limit of {max_pages} pages. Stopping to prevent infinite loop.")
                    logger.warning(f"Order sync reached max_pages limit ({max_pages}) for run_id {event_logger.run_id}")
                    break
                
                # Check for cancellation
                from app.services.sync_event_logger import is_cancelled
                if is_cancelled(event_logger.run_id):
                    logger.info(f"Order sync cancelled for run_id {event_logger.run_id}")
                    event_logger.log_warning("Sync operation cancelled by user")
                    event_logger.log_done(
                        f"Orders sync cancelled: {total_fetched} fetched, {total_stored} stored",
                        total_fetched,
                        total_stored,
                        int((time.time() - start_time) * 1000)
                    )
                    event_logger.close()
                    return {
                        "status": "cancelled",
                        "total_fetched": total_fetched,
                        "total_stored": total_stored,
                        "job_id": job_id,
                        "run_id": event_logger.run_id
                    }
                
                current_page += 1
                # Restrict search to the effective lastmodifieddate window so
                # workers truly behave incrementally instead of always pulling
                # the full 90-day default. NOTE: the Fulfillment API expects the
                # field name to be all lower-case ("lastmodifieddate").
                filter_params = {
                    "limit": limit,
                    "offset": offset,
                    "fieldGroups": "TAX_BREAKDOWN",
                    "filter": (
                        f"lastmodifieddate:[{start_iso}..{end_iso}]"
                    ),
                }
                
                # Check for cancellation BEFORE making the API request
                from app.services.sync_event_logger import is_cancelled
                if is_cancelled(event_logger.run_id):
                    logger.info(f"Order sync cancelled for run_id {event_logger.run_id} (before API request)")
                    event_logger.log_warning("Sync operation cancelled by user")
                    event_logger.log_done(
                        f"Orders sync cancelled: {total_fetched} fetched, {total_stored} stored",
                        total_fetched,
                        total_stored,
                        int((time.time() - start_time) * 1000)
                    )
                    event_logger.close()
                    return {
                        "status": "cancelled",
                        "total_fetched": total_fetched,
                        "total_stored": total_stored,
                        "job_id": job_id,
                        "run_id": event_logger.run_id
                    }
                
                # Build full URL for logging
                api_url = f"{settings.ebay_api_base_url}/sell/fulfillment/v1/order"
                query_string = "&".join([f"{k}={v}" for k, v in filter_params.items()])
                full_url = f"{api_url}?{query_string}"
                
                # Log request context before API call
                event_logger.log_debug(
                    f"[DEBUG] → GET {api_url}",
                    http_method="GET",
                    http_url=full_url,
                    token=access_token,
                    scopes=user_scopes,
                    headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
                )
                
                event_logger.log_info(f"→ Requesting page {current_page}: GET /sell/fulfillment/v1/order?limit={limit}&offset={offset}")
                
                request_start = time.time()
                try:
                    orders_response = await self.fetch_orders(access_token, filter_params)
                except Exception as e:
                    # Check for cancellation after error (in case error took a long time)
                    if is_cancelled(event_logger.run_id):
                        logger.info(f"Order sync cancelled for run_id {event_logger.run_id} (after API error)")
                        event_logger.log_warning("Sync operation cancelled by user")
                        event_logger.log_done(
                            f"Orders sync cancelled: {total_fetched} fetched, {total_stored} stored",
                            total_fetched,
                            total_stored,
                            int((time.time() - start_time) * 1000)
                        )
                        event_logger.close()
                        return {
                            "status": "cancelled",
                            "total_fetched": total_fetched,
                            "total_stored": total_stored,
                            "job_id": job_id,
                            "run_id": event_logger.run_id
                        }
                    raise  # Re-raise if not cancelled
                request_duration = int((time.time() - request_start) * 1000)
                
                # Check for cancellation AFTER the API request (in case request took a long time)
                if is_cancelled(event_logger.run_id):
                    logger.info(f"Order sync cancelled for run_id {event_logger.run_id} (after API request)")
                    event_logger.log_warning("Sync operation cancelled by user")
                    event_logger.log_done(
                        f"Orders sync cancelled: {total_fetched} fetched, {total_stored} stored",
                        total_fetched,
                        total_stored,
                        int((time.time() - start_time) * 1000)
                    )
                    event_logger.close()
                    return {
                        "status": "cancelled",
                        "total_fetched": total_fetched,
                        "total_stored": total_stored,
                        "job_id": job_id,
                        "run_id": event_logger.run_id
                    }
                
                orders = orders_response.get('orders', [])
                total = orders_response.get('total', 0) or 0  # Ensure total is always a number
                total_pages = (total + limit - 1) // limit if total > 0 else 1
                
                event_logger.log_http_request(
                    'GET',
                    f'/sell/fulfillment/v1/order?limit={limit}&offset={offset}',
                    200,
                    request_duration,
                    len(orders)
                )
                
                event_logger.log_info(f"← Response: 200 OK ({request_duration}ms) - Received {len(orders)} orders (Total available: {total})")
                
                # Early exit if total == 0 (no orders in window)
                if total == 0 and current_page == 1:
                    event_logger.log_info(f"✓ No orders found in date window. Total available: 0")
                    event_logger.log_warning("No orders in window - check date range, account, or environment")
                    break
                
                total_fetched += len(orders)
                
                await asyncio.sleep(0.3)
                
                # Check for cancellation before storing
                if is_cancelled(event_logger.run_id):
                    logger.info(f"Order sync cancelled for run_id {event_logger.run_id} (before storing)")
                    event_logger.log_warning("Sync operation cancelled by user")
                    event_logger.log_done(
                        f"Orders sync cancelled: {total_fetched} fetched, {total_stored} stored",
                        total_fetched,
                        total_stored,
                        int((time.time() - start_time) * 1000)
                    )
                    event_logger.close()
                    return {
                        "status": "cancelled",
                        "total_fetched": total_fetched,
                        "total_stored": total_stored,
                        "job_id": job_id,
                        "run_id": event_logger.run_id
                    }
                
                event_logger.log_info(f"→ Storing {len(orders)} orders in database...")
                store_start = time.time()
                # When using PostgresEbayDatabase, this will tag each row with
                # ebay_account_id (if provided) and effective_ebay_user_id.
                try:
                    batch_stored = ebay_db.batch_upsert_orders(  # type: ignore[arg-type]
                        user_id,
                        orders,
                        ebay_account_id=ebay_account_id,
                        ebay_user_id=effective_ebay_user_id,
                    )
                except TypeError:
                    # SQLite legacy path without batch_upsert_orders
                    from app.services.ebay_database import EbayDatabase as _SQLiteDB
                    if isinstance(ebay_db, _SQLiteDB):  # type: ignore[misc]
                        batch_stored = 0
                        from app.utils.logger import logger as _logger
                        _logger.warning("batch_upsert_orders not supported on SQLite ebay_db; skipping tagging")
                    else:
                        raise
                store_duration = int((time.time() - store_start) * 1000)
                total_stored += batch_stored
                
                event_logger.log_info(f"← Database: Stored {batch_stored} orders ({store_duration}ms)")
                
                event_logger.log_progress(
                    f"Page {current_page}/{total_pages} complete: {len(orders)} fetched, {batch_stored} stored | Running total: {total_fetched}/{total} fetched, {total_stored} stored",
                    current_page,
                    total_pages,
                    total_fetched,
                    total_stored
                )
                
                logger.info(f"Synced batch: {len(orders)} orders (total: {total_fetched}/{total}, stored: {total_stored})")
                
                # Check for cancellation before continuing to next page
                if is_cancelled(event_logger.run_id):
                    logger.info(f"Order sync cancelled for run_id {event_logger.run_id} (before next page)")
                    event_logger.log_warning("Sync operation cancelled by user")
                    event_logger.log_done(
                        f"Orders sync cancelled: {total_fetched} fetched, {total_stored} stored",
                        total_fetched,
                        total_stored,
                        int((time.time() - start_time) * 1000)
                    )
                    event_logger.close()
                    return {
                        "status": "cancelled",
                        "total_fetched": total_fetched,
                        "total_stored": total_stored,
                        "job_id": job_id,
                        "run_id": event_logger.run_id
                    }
                
                # Update has_more BEFORE incrementing offset to prevent infinite loops
                # Stop if: no more orders, or we've fetched all available, or offset would exceed total
                has_more = len(orders) > 0 and len(orders) == limit and (offset + limit) < total
                
                offset += limit
                
                if has_more:
                    await asyncio.sleep(0.8)
            
            duration_ms = int((time.time() - start_time) * 1000)
            ebay_db.update_sync_job(job_id, 'completed', total_fetched, total_stored)
            
            event_logger.log_done(
                f"Orders sync completed: {total_fetched} fetched, {total_stored} stored in {duration_ms}ms",
                total_fetched,
                total_stored,
                duration_ms
            )
            
            logger.info(f"Order sync completed: fetched={total_fetched}, stored={total_stored}")
            
            return {
                "status": "completed",
                "total_fetched": total_fetched,
                "total_stored": total_stored,
                "job_id": job_id,
                "run_id": event_logger.run_id
            }
            
        except Exception as e:
            error_msg = str(e)
            event_logger.log_error(f"Orders sync failed: {error_msg}", e)
            logger.error(f"Order sync failed: {error_msg}")
            ebay_db.update_sync_job(job_id, 'failed', error_message=error_msg)
            raise
        finally:
            event_logger.close()


    async def fetch_payment_disputes(self, access_token: str, filter_params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Fetch payment disputes from eBay Fulfillment API using search endpoint."""
        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="eBay access token required",
            )

        # Payment Disputes API uses POST method with search criteria
        api_url = f"{settings.ebay_api_base_url}/sell/fulfillment/v1/payment_dispute_summary/search"

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",  # Required for all eBay APIs
        }

        # Payment disputes search requires POST with search criteria in body
        search_body = filter_params or {}

        ebay_logger.log_ebay_event(
            "fetch_disputes_request",
            f"Fetching payment disputes from eBay ({settings.EBAY_ENVIRONMENT})",
            request_data={
                "environment": settings.EBAY_ENVIRONMENT,
                "api_url": api_url,
                "method": "POST",
                "body": search_body,
            },
        )

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    api_url,
                    headers=headers,
                    json=search_body,
                    timeout=30.0,
                )

            if response.status_code != 200:
                error_detail: Any = response.text
                try:
                    error_json = response.json()
                    error_detail = error_json
                except Exception:
                    pass

                ebay_logger.log_ebay_event(
                    "fetch_disputes_failed",
                    f"Failed to fetch disputes: {response.status_code}",
                    response_data={"error": error_detail},
                    status="error",
                    error=str(error_detail),
                )
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Failed to fetch disputes: {error_detail}",
                )

            disputes_data = response.json()

            ebay_logger.log_ebay_event(
                "fetch_disputes_success",
                "Successfully fetched disputes from eBay",
                response_data={
                    "total_disputes": disputes_data.get("total", 0),
                },
                status="success",
            )

            logger.info("Successfully fetched disputes from eBay")
            return disputes_data

        except httpx.RequestError as e:
            error_msg = f"HTTP request failed: {str(e)}"
            ebay_logger.log_ebay_event(
                "fetch_disputes_error",
                "HTTP request error during disputes fetch",
                status="error",
                error=error_msg,
            )
            logger.error(error_msg)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_msg,
            )

    async def fetch_inquiries(
        self,
        access_token: str,
        filter_params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Fetch buyer inquiries from the Post-Order Inquiry API.

        This mirrors fetch_postorder_cases but targets /post-order/v2/inquiry/search
        so workers can ingest the pre-case buyer disputes.
        """
        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="eBay access token required",
            )

        api_url = f"{settings.ebay_api_base_url}/post-order/v2/inquiry/search"
        timeout_seconds = 30.0

        headers = {
            # Post-Order API expects OAuth user tokens in the IAF scheme, not Bearer.
            "Authorization": f"IAF {access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
        }

        params = filter_params or {}

        ebay_logger.log_ebay_event(
            "fetch_postorder_inquiries_request",
            f"Fetching Post-Order inquiries from eBay ({settings.EBAY_ENVIRONMENT})",
            request_data={
                "environment": settings.EBAY_ENVIRONMENT,
                "api_url": api_url,
                "method": "GET",
                "params": params,
            },
        )

        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                response = await client.get(api_url, headers=headers, params=params)

            if response.status_code != 200:
                correlation_id = (
                    response.headers.get("X-EBAY-CORRELATION-ID")
                    or response.headers.get("x-ebay-correlation-id")
                )
                try:
                    error_body: Any = response.json()
                except Exception:
                    error_body = response.text

                body_snippet = (
                    str(error_body)[:2000]
                    if not isinstance(error_body, (dict, list))
                    else error_body
                )

                message = (
                    f"EBAY Post-Order error {response.status_code} on GET "
                    f"/post-order/v2/inquiry/search; "
                    f"correlation-id={correlation_id or 'unknown'}; body={body_snippet}"
                )

                ebay_logger.log_ebay_event(
                    "fetch_postorder_inquiries_failed",
                    "Failed to fetch Post-Order inquiries from eBay",
                    response_data={
                        "status_code": response.status_code,
                        "correlation_id": correlation_id,
                        "headers": dict(response.headers),
                        "body": body_snippet,
                    },
                    status="error",
                    error=message,
                )
                logger.error(message)
                raise HTTPException(status_code=response.status_code, detail=message)

            inquiries_data = response.json()

            total = inquiries_data.get("total")
            items = (
                inquiries_data.get("inquiries")
                or inquiries_data.get("inquirySummaries")
                or inquiries_data.get("members")
                or []
            )

            ebay_logger.log_ebay_event(
                "fetch_postorder_inquiries_success",
                "Successfully fetched Post-Order inquiries",
                response_data={
                    "total_inquiries": total if total is not None else len(items),
                },
                status="success",
            )
            logger.info("Successfully fetched Post-Order inquiries from eBay")
            return inquiries_data

        except httpx.TimeoutException as e:
            message = (
                f"Timeout calling EBAY Post-Order GET /post-order/v2/inquiry/search "
                f"after {timeout_seconds}s: {str(e)}"
            )
            ebay_logger.log_ebay_event(
                "fetch_postorder_inquiries_timeout",
                "Timeout during Post-Order inquiries fetch",
                status="error",
                error=message,
            )
            logger.error(message)
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail=message,
            )
        except httpx.RequestError as e:
            message = (
                "Network error calling EBAY Post-Order GET "
                "/post-order/v2/inquiry/search: "
                f"{str(e)}"
            )
            ebay_logger.log_ebay_event(
                "fetch_postorder_inquiries_error",
                "HTTP request error during Post-Order inquiries fetch",
                status="error",
                error=message,
            )
            logger.error(message)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=message,
            )

    async def fetch_inquiry_detail(
        self,
        access_token: str,
        inquiry_id: str,
    ) -> Dict[str, Any]:
        """Fetch a single Post-Order inquiry by id.

        This calls ``GET /post-order/v2/inquiry/{inquiryId}`` so that we can
        store the full detailed object (including history, responses, etc.) in
        ``ebay_inquiries.raw_json`` instead of only the search summary row.
        """
        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="eBay access token required",
            )
        if not inquiry_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="inquiry_id is required",
            )

        api_url = f"{settings.ebay_api_base_url}/post-order/v2/inquiry/{inquiry_id}"
        timeout_seconds = 30.0

        headers = {
            "Authorization": f"IAF {access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
        }

        ebay_logger.log_ebay_event(
            "fetch_postorder_inquiry_detail_request",
            "Fetching Post-Order inquiry detail from eBay",
            request_data={
                "environment": settings.EBAY_ENVIRONMENT,
                "api_url": api_url,
                "method": "GET",
                "inquiry_id": inquiry_id,
            },
        )

        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                response = await client.get(api_url, headers=headers)

            if response.status_code != 200:
                correlation_id = (
                    response.headers.get("X-EBAY-CORRELATION-ID")
                    or response.headers.get("x-ebay-correlation-id")
                )
                try:
                    error_body: Any = response.json()
                except Exception:
                    error_body = response.text

                body_snippet = (
                    str(error_body)[:2000]
                    if not isinstance(error_body, (dict, list))
                    else error_body
                )

                message = (
                    f"EBAY Post-Order error {response.status_code} on GET "
                    f"/post-order/v2/inquiry/{inquiry_id}; "
                    f"correlation-id={correlation_id or 'unknown'}; body={body_snippet}"
                )

                ebay_logger.log_ebay_event(
                    "fetch_postorder_inquiry_detail_failed",
                    "Failed to fetch Post-Order inquiry detail from eBay",
                    response_data={
                        "status_code": response.status_code,
                        "correlation_id": correlation_id,
                        "headers": dict(response.headers),
                        "body": body_snippet,
                    },
                    status="error",
                    error=message,
                )
                logger.error(message)
                raise HTTPException(status_code=response.status_code, detail=message)

            data: Any
            try:
                data = response.json() or {}
            except Exception:
                data = {}

            if not isinstance(data, dict):
                data = {"raw": data}

            ebay_logger.log_ebay_event(
                "fetch_postorder_inquiry_detail_success",
                "Successfully fetched Post-Order inquiry detail",
                response_data={
                    "inquiry_id": inquiry_id,
                },
                status="success",
            )
            logger.info("Successfully fetched Post-Order inquiry detail from eBay")
            return data

        except httpx.TimeoutException as e:
            message = (
                f"Timeout calling EBAY Post-Order GET /post-order/v2/inquiry/{inquiry_id} "
                f"after {timeout_seconds}s: {str(e)}"
            )
            ebay_logger.log_ebay_event(
                "fetch_postorder_inquiry_detail_timeout",
                "Timeout during Post-Order inquiry detail fetch",
                status="error",
                error=message,
            )
            logger.error(message)
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail=message,
            )
        except httpx.RequestError as e:
            message = (
                "Network error calling EBAY Post-Order GET "
                f"/post-order/v2/inquiry/{inquiry_id}: {str(e)}"
            )
            ebay_logger.log_ebay_event(
                "fetch_postorder_inquiry_detail_error",
                "HTTP request error during Post-Order inquiry detail fetch",
                status="error",
                error=message,
            )
            logger.error(message)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=message,
            )

    async def fetch_postorder_cases(
        self,
        access_token: str,
        filter_params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Fetch cases from the Post-Order Case Management API (casemanagement).

        IMPORTANT: This helper must surface *detailed* eBay errors so that the
        workers UI can show the real cause (status, body, correlation id)
        instead of a generic "Failed to fetch Post-Order cases" message.
        """
        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="eBay access token required",
            )

        api_url = f"{settings.ebay_api_base_url}/post-order/v2/casemanagement/search"
        timeout_seconds = 30.0

        headers = {
            # Post-Order API expects OAuth user tokens in the IAF scheme, not Bearer.
            # See eBay Post-Order docs: Authorization: IAF <user_access_token>
            "Authorization": f"IAF {access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            # Many modern eBay REST APIs require marketplace id; include it here
            # so Post-Order requests are properly routed.
            "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
        }

        search_body = filter_params or {}

        ebay_logger.log_ebay_event(
            "fetch_postorder_cases_request",
            f"Fetching Post-Order cases from eBay ({settings.EBAY_ENVIRONMENT})",
            request_data={
                "environment": settings.EBAY_ENVIRONMENT,
                "api_url": api_url,
                "method": "GET",
                "params": search_body,
            },
        )

        try:
            async with httpx.AsyncClient() as client:
                # NOTE: According to eBay Post-Order docs, casemanagement/search is
                # a GET endpoint and expects filters as query parameters.
                response = await client.get(
                    api_url,
                    headers=headers,
                    params=search_body,
                    timeout=timeout_seconds,
                )

            if response.status_code != 200:
                # Extract as much context as possible from the failing response.
                correlation_id = (
                    response.headers.get("X-EBAY-CORRELATION-ID")
                    or response.headers.get("x-ebay-correlation-id")
                )

                error_body: Any
                try:
                    error_body = response.json()
                except Exception:
                    error_body = response.text

                # Truncate body to keep logs and last_error reasonably small.
                body_snippet = (
                    str(error_body)[:2000]
                    if not isinstance(error_body, (dict, list))
                    else error_body
                )

                message = (
                    f"EBAY Post-Order error {response.status_code} on GET "
                    f"/post-order/v2/casemanagement/search; "
                    f"correlation-id={correlation_id or 'unknown'}; body={body_snippet}"
                )

                ebay_logger.log_ebay_event(
                    "fetch_postorder_cases_failed",
                    "Failed to fetch Post-Order cases from eBay",
                    response_data={
                        "status_code": response.status_code,
                        "correlation_id": correlation_id,
                        "headers": dict(response.headers),
                        "body": body_snippet,
                    },
                    status="error",
                    error=message,
                )

                logger.error(message)

                # Raise an HTTPException whose detail carries the full message so
                # worker last_error and /ebay/workers/run can display it.
                raise HTTPException(
                    status_code=response.status_code,
                    detail=message,
                )

            cases_data = response.json()

            ebay_logger.log_ebay_event(
                "fetch_postorder_cases_success",
                "Successfully fetched Post-Order cases",
                response_data={
                    "total_cases": cases_data.get("total", len(cases_data.get("cases", []))),
                },
                status="success",
            )

            logger.info("Successfully fetched Post-Order cases from eBay")
            return cases_data

        except httpx.TimeoutException as e:
            message = (
                f"Timeout calling EBAY Post-Order GET /post-order/v2/casemanagement/search "
                f"after {timeout_seconds}s: {str(e)}"
            )
            ebay_logger.log_ebay_event(
                "fetch_postorder_cases_timeout",
                "Timeout during Post-Order cases fetch",
                status="error",
                error=message,
            )
            logger.error(message)
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail=message,
            )
        except httpx.RequestError as e:
            # Non-timeout network / connection error.
            message = (
                "Network error calling EBAY Post-Order GET "
                "/post-order/v2/casemanagement/search: "
                f"{str(e)}"
            )
            ebay_logger.log_ebay_event(
                "fetch_postorder_cases_error",
                "HTTP request error during Post-Order cases fetch",
                status="error",
                error=message,
            )
            logger.error(message)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=message,
            )

    async def fetch_postorder_returns(
        self,
        access_token: str,
        filter_params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Fetch return requests from the Post-Order Returns API.

        This wraps ``GET /post-order/v2/return/search`` as documented in the
        eBay Post-Order API. We surface detailed errors (status, body,
        correlation id) so worker UIs can show real failure causes.
        """
        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="eBay access token required",
            )

        # See "Search Returns" docs: GET https://api.ebay.com/post-order/v2/return/search
        api_url = f"{settings.ebay_api_base_url}/post-order/v2/return/search"
        timeout_seconds = 30.0

        headers = {
            # Post-Order API expects OAuth user tokens in the IAF scheme.
            # Docs: all Post-Order calls use standard OAuth tokens via the
            # Authorization header. Historically these are sent as
            # "Authorization: IAF <user_access_token>".
            "Authorization": f"IAF {access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
        }

        params = filter_params or {}

        ebay_logger.log_ebay_event(
            "fetch_postorder_returns_request",
            f"Fetching Post-Order returns from eBay ({settings.EBAY_ENVIRONMENT})",
            request_data={
                "environment": settings.EBAY_ENVIRONMENT,
                "api_url": api_url,
                "method": "GET",
                "params": params,
            },
        )

        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                response = await client.get(api_url, headers=headers, params=params)

            if response.status_code != 200:
                correlation_id = (
                    response.headers.get("X-EBAY-CORRELATION-ID")
                    or response.headers.get("x-ebay-correlation-id")
                )
                try:
                    error_body: Any = response.json()
                except Exception:
                    error_body = response.text

                body_snippet = (
                    str(error_body)[:2000]
                    if not isinstance(error_body, (dict, list))
                    else error_body
                )

                message = (
                    f"EBAY Post-Order error {response.status_code} on GET "
                    f"/post-order/v2/return/search; "
                    f"correlation-id={correlation_id or 'unknown'}; body={body_snippet}"
                )

                ebay_logger.log_ebay_event(
                    "fetch_postorder_returns_failed",
                    "Failed to fetch Post-Order returns from eBay",
                    response_data={
                        "status_code": response.status_code,
                        "correlation_id": correlation_id,
                        "headers": dict(response.headers),
                        "body": body_snippet,
                    },
                    status="error",
                    error=message,
                )
                logger.error(message)
                raise HTTPException(status_code=response.status_code, detail=message)

            returns_data = response.json()

            total = returns_data.get("total")
            items = (
                returns_data.get("members")
                or returns_data.get("returns")
                or returns_data.get("returnSummaries")
                or []
            )

            ebay_logger.log_ebay_event(
                "fetch_postorder_returns_success",
                "Successfully fetched Post-Order returns",
                response_data={
                    "total_returns": total if total is not None else len(items),
                },
                status="success",
            )
            logger.info("Successfully fetched Post-Order returns from eBay")
            return returns_data

        except httpx.TimeoutException as e:
            message = (
                f"Timeout calling EBAY Post-Order GET /post-order/v2/return/search "
                f"after {timeout_seconds}s: {str(e)}"
            )
            ebay_logger.log_ebay_event(
                "fetch_postorder_returns_timeout",
                "Timeout during Post-Order returns fetch",
                status="error",
                error=message,
            )
            logger.error(message)
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail=message,
            )
        except httpx.RequestError as e:
            message = (
                "Network error calling EBAY Post-Order GET "
                "/post-order/v2/return/search: "
                f"{str(e)}"
            )
            ebay_logger.log_ebay_event(
                "fetch_postorder_returns_error",
                "HTTP request error during Post-Order returns fetch",
                status="error",
                error=message,
            )
            logger.error(message)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=message,
            )

    async def fetch_postorder_return_detail(
        self,
        access_token: str,
        return_id: str,
        fieldgroups: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Fetch a single Post-Order return request by id.

        This wraps ``GET /post-order/v2/return/{returnId}`` so workers can store
        the full detailed payload (including refund breakdown, shipment info,
        and history) in ``ebay_returns.raw_json``.
        """
        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="eBay access token required",
            )
        if not return_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="return_id is required",
            )

        # See "Get Return" docs: GET https://api.ebay.com/post-order/v2/return/{returnId}
        api_url = f"{settings.ebay_api_base_url}/post-order/v2/return/{return_id}"
        timeout_seconds = 30.0

        headers = {
            "Authorization": f"IAF {access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
        }

        params: Dict[str, Any] = {}
        if fieldgroups:
            params["fieldgroups"] = fieldgroups

        ebay_logger.log_ebay_event(
            "fetch_postorder_return_detail_request",
            "Fetching Post-Order return detail from eBay",
            request_data={
                "environment": settings.EBAY_ENVIRONMENT,
                "api_url": api_url,
                "method": "GET",
                "return_id": return_id,
                "params": params,
            },
        )

        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                response = await client.get(api_url, headers=headers, params=params)

            if response.status_code != 200:
                correlation_id = (
                    response.headers.get("X-EBAY-CORRELATION-ID")
                    or response.headers.get("x-ebay-correlation-id")
                )
                try:
                    error_body: Any = response.json()
                except Exception:
                    error_body = response.text

                body_snippet = (
                    str(error_body)[:2000]
                    if not isinstance(error_body, (dict, list))
                    else error_body
                )

                message = (
                    f"EBAY Post-Order error {response.status_code} on GET "
                    f"/post-order/v2/return/{return_id}; "
                    f"correlation-id={correlation_id or 'unknown'}; body={body_snippet}"
                )

                ebay_logger.log_ebay_event(
                    "fetch_postorder_return_detail_failed",
                    "Failed to fetch Post-Order return detail from eBay",
                    response_data={
                        "status_code": response.status_code,
                        "correlation_id": correlation_id,
                        "headers": dict(response.headers),
                        "body": body_snippet,
                    },
                    status="error",
                    error=message,
                )
                logger.error(message)
                raise HTTPException(status_code=response.status_code, detail=message)

            data: Any
            try:
                data = response.json() or {}
            except Exception:
                data = {}

            if not isinstance(data, dict):
                data = {"raw": data}

            ebay_logger.log_ebay_event(
                "fetch_postorder_return_detail_success",
                "Successfully fetched Post-Order return detail",
                response_data={
                    "return_id": return_id,
                },
                status="success",
            )
            logger.info("Successfully fetched Post-Order return detail from eBay")
            return data

        except httpx.TimeoutException as e:
            message = (
                f"Timeout calling EBAY Post-Order GET /post-order/v2/return/{return_id} "
                f"after {timeout_seconds}s: {str(e)}"
            )
            ebay_logger.log_ebay_event(
                "fetch_postorder_return_detail_timeout",
                "Timeout during Post-Order return detail fetch",
                status="error",
                error=message,
            )
            logger.error(message)
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail=message,
            )
        except httpx.RequestError as e:
            message = (
                "Network error calling EBAY Post-Order GET "
                f"/post-order/v2/return/{return_id}: {str(e)}"
            )
            ebay_logger.log_ebay_event(
                "fetch_postorder_return_detail_error",
                "HTTP request error during Post-Order return detail fetch",
                status="error",
                error=message,
            )
            logger.error(message)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=message,
            )

    async def fetch_inventory_items(self, access_token: str, limit: int = 200, offset: int = 0) -> Dict[str, Any]:
        """
        Fetch inventory items from eBay Inventory API
        According to eBay API docs: GET /sell/inventory/v1/inventory_item
        Parameters: limit (1-200, default 25), offset (default 0)
        """
        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="eBay access token required"
            )
        
        api_url = f"{settings.ebay_api_base_url}/sell/inventory/v1/inventory_item"
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"
        }
        
        # Validate limit (1-200 per eBay API docs)
        limit = max(1, min(200, limit))
        params = {
            "limit": str(limit),
            "offset": str(offset)
        }
        
        ebay_logger.log_ebay_event(
            "fetch_inventory_items_request",
            f"Fetching inventory items from eBay ({settings.EBAY_ENVIRONMENT})",
            request_data={
                "environment": settings.EBAY_ENVIRONMENT,
                "api_url": api_url,
                "params": params
            }
        )
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    api_url,
                    headers=headers,
                    params=params,
                    timeout=30.0
                )
                
                if response.status_code != 200:
                    error_detail = response.text
                    try:
                        error_json = response.json()
                        error_detail = str(error_json)
                    except:
                        pass
                    
                    ebay_logger.log_ebay_event(
                        "fetch_inventory_items_failed",
                        f"Failed to fetch inventory items: {response.status_code}",
                        response_data={"error": error_detail},
                        status="error",
                        error=error_detail
                    )
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=f"Failed to fetch inventory items: {error_detail}"
                    )
                
                inventory_data = response.json()
                
                ebay_logger.log_ebay_event(
                    "fetch_inventory_items_success",
                    f"Successfully fetched inventory items from eBay",
                    response_data={
                        "total": inventory_data.get('total', 0),
                        "count": len(inventory_data.get('inventoryItems', []))
                    },
                    status="success"
                )
                
                logger.info(f"Successfully fetched {len(inventory_data.get('inventoryItems', []))} inventory items from eBay")
                
                return inventory_data
                
        except httpx.RequestError as e:
            error_msg = f"HTTP request failed: {str(e)}"
            ebay_logger.log_ebay_event(
                "fetch_inventory_items_error",
                "HTTP request error during inventory items fetch",
                status="error",
                error=error_msg
            )
            logger.error(error_msg)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_msg
            )

    async def fetch_offers(self, access_token: str, sku: str, filter_params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Fetch offers from eBay Inventory API for a specific SKU
        According to eBay API docs: GET /sell/inventory/v1/offer requires 'sku' parameter (Required)
        Parameters: sku (required), limit (optional), offset (optional), format (optional), marketplace_id (optional)
        """
        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="eBay access token required",
            )
        
        api_url = f"{settings.ebay_api_base_url}/sell/inventory/v1/offer"
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
        }
        
        # According to eBay API docs: sku is REQUIRED parameter
        # Allowed params: sku (required), limit (optional), offset (optional), format (optional), marketplace_id (optional)
        params = {
            "sku": sku,
        }
        
        # Add optional params from filter_params
        if filter_params:
            allowed_optional_params = {"limit", "offset", "format", "marketplace_id"}
            for key, value in filter_params.items():
                if key in allowed_optional_params and value is not None and value != "":
                    params[key] = value
        
        # Set defaults for pagination if not provided
        if "limit" not in params:
            params["limit"] = 200  # Max allowed by eBay
        if "offset" not in params:
            params["offset"] = 0
        
        logger.info(
            "fetch_offers params: sku=%s, limit=%s, offset=%s",
            sku,
            params.get("limit"),
            params.get("offset"),
        )
        
        ebay_logger.log_ebay_event(
            "fetch_offers_request",
            f"Fetching offers from eBay ({settings.EBAY_ENVIRONMENT})",
            request_data={
                "environment": settings.EBAY_ENVIRONMENT,
                "api_url": api_url,
                "params": params,
            },
        )
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(api_url, headers=headers, params=params)
        except httpx.RequestError as e:
            error_msg = f"HTTP request failed: {e}"
            ebay_logger.log_ebay_event(
                "fetch_offers_error",
                "HTTP request error during offers fetch",
                status="error",
                error=error_msg,
            )
            logger.error(error_msg)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_msg,
            )
        
        if response.status_code != 200:
            error_detail = response.text
            try:
                error_json = response.json()
                error_detail = str(error_json)
            except Exception:
                pass
        
            ebay_logger.log_ebay_event(
                "fetch_offers_failed",
                f"Failed to fetch offers: {response.status_code}",
                response_data={"error": error_detail},
                status="error",
                error=error_detail,
            )
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Failed to fetch offers: {error_detail}",
            )
        
        offers_data = response.json()
        
        ebay_logger.log_ebay_event(
            "fetch_offers_success",
            "Successfully fetched offers from eBay",
            response_data={
                "total": offers_data.get("total", 0),
                "count": len(offers_data.get("offers", [])),
            },
            status="success",
        )
        
        logger.info(
            "Successfully fetched %s offers for SKU %s from eBay",
            len(offers_data.get("offers", [])),
            sku,
        )
        
        return offers_data

    async def fetch_offers_debug(
        self,
        access_token: str,
        sku: str,
        filter_params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Fetch offers and return real HTTP request/response metadata (admin preview tooling).

        Returns:
          {
            "payload": <offers_json>,
            "http": {
              "request": {method, url, headers, params},
              "response": {status_code, headers, body},
              "duration_ms": int
            }
          }

        Security:
        - Authorization header is masked in returned metadata.
        """

        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="eBay access token required",
            )

        start = time.time()
        base_url = settings.ebay_api_base_url.rstrip("/")
        api_url = f"{base_url}/sell/inventory/v1/offer"

        headers: Dict[str, Any] = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
            "Accept": "application/json",
        }

        params: Dict[str, Any] = {"sku": sku}
        if filter_params:
            allowed_optional_params = {"limit", "offset", "format", "marketplace_id"}
            for key, value in filter_params.items():
                if key in allowed_optional_params and value is not None and value != "":
                    params[key] = value

        if "limit" not in params:
            params["limit"] = 200
        if "offset" not in params:
            params["offset"] = 0

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(api_url, headers=headers, params=params)
        except httpx.RequestError as e:
            duration_ms = int((time.time() - start) * 1000)
            masked_headers = dict(headers)
            if "Authorization" in masked_headers:
                masked_headers["Authorization"] = "Bearer ***"
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "message": f"fetch_offers network error: {e}",
                    "http": {
                        "request": {
                            "method": "GET",
                            "url": api_url,
                            "headers": masked_headers,
                            "params": params,
                        },
                        "response": None,
                        "duration_ms": duration_ms,
                    },
                },
            )

        duration_ms = int((time.time() - start) * 1000)
        req = response.request

        masked_req_headers = dict(req.headers)
        if "Authorization" in masked_req_headers:
            masked_req_headers["Authorization"] = "Bearer ***"

        http_meta: Dict[str, Any] = {
            "request": {
                "method": req.method,
                "url": str(req.url),
                "headers": dict(masked_req_headers),
                "params": params,
            },
            "response": {
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "body": None,
            },
            "duration_ms": duration_ms,
        }

        try:
            body: Any = response.json()
        except Exception:
            body = response.text
        http_meta["response"]["body"] = body

        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail={"message": "fetch_offers_failed", "http": http_meta},
            )

        if not isinstance(body, dict):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"message": "fetch_offers_invalid_json", "http": http_meta},
            )

        return {"payload": body, "http": http_meta}

    async def place_proxy_bid(
        self,
        access_token: str,
        item_id: str,
        *,
        max_amount_value: str,
        currency: str,
        marketplace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Place a proxy bid on an auction listing via Buy Offer API.

        This is a thin wrapper over
        ``POST /buy/offer/v1_beta/bidding/{item_id}/place_proxy_bid``.
        ``item_id`` is the RESTful item id returned by Browse/Feed APIs
        (e.g. "v1|1234567890|0").
        """

        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="eBay access token required",
            )

        base_url = settings.ebay_api_base_url.rstrip("/")
        api_url = f"{base_url}/buy/offer/v1_beta/bidding/{item_id}/place_proxy_bid"

        headers: Dict[str, Any] = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if marketplace_id:
            headers["X-EBAY-C-MARKETPLACE-ID"] = marketplace_id

        body = {
            "maxAmount": {
                "currency": currency,
                "value": max_amount_value,
            }
        }

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=5.0)) as client:
                response = await client.post(api_url, headers=headers, json=body)
        except httpx.RequestError as exc:
            error_msg = f"HTTP request failed during placeProxyBid: {exc}"
            logger.error(error_msg)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=error_msg,
            )

        try:
            payload: Any = response.json()
        except Exception:
            payload = {}

        if response.status_code not in (200, 201):
            error_body = payload or response.text
            logger.error(
                "placeProxyBid failed: status=%s body=%s",
                response.status_code,
                error_body,
            )
            raise HTTPException(
                status_code=response.status_code,
                detail={
                    "message": "placeProxyBid failed",
                    "status_code": response.status_code,
                    "body": error_body,
                },
            )

        return payload

    async def get_bidding_status(
        self,
        access_token: str,
        item_id: str,
        *,
        marketplace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Retrieve bidding status for an auction via Buy Offer API.

        Wrapper over ``GET /buy/offer/v1_beta/bidding/{item_id}``.
        Returns the parsed JSON body on success and raises HTTPException on
        non-2xx responses.
        """

        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="eBay access token required",
            )

        base_url = settings.ebay_api_base_url.rstrip("/")
        api_url = f"{base_url}/buy/offer/v1_beta/bidding/{item_id}"

        headers: Dict[str, Any] = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }
        if marketplace_id:
            headers["X-EBAY-C-MARKETPLACE-ID"] = marketplace_id

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=5.0)) as client:
                response = await client.get(api_url, headers=headers)
        except httpx.RequestError as exc:
            error_msg = f"HTTP request failed during get_bidding_status: {exc}"
            logger.error(error_msg)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=error_msg,
            )

        try:
            payload: Any = response.json()
        except Exception:
            payload = {}

        if response.status_code != 200:
            error_body = payload or response.text
            logger.error(
                "get_bidding_status failed: status=%s body=%s",
                response.status_code,
                error_body,
            )
            raise HTTPException(
                status_code=response.status_code,
                detail={
                    "message": "getBidding failed",
                    "status_code": response.status_code,
                    "body": error_body,
                },
            )

        return payload

    async def bulk_publish_offers(
        self,
        access_token: str,
        offer_ids: List[str],
    ) -> Tuple[int, Dict[str, Any]]:
        """Publish multiple existing offers as live listings.

        Thin wrapper over ``POST /sell/inventory/v1/bulk_publish_offer``.
        Returns ``(status_code, parsed_json_payload)``. On non-2xx/207
        responses a HTTPException is raised so callers can surface a
        structured error in their own traces.
        """

        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="eBay access token required",
            )

        if not offer_ids:
            # Treat empty input as a no-op that still looks successful.
            return 200, {"responses": []}

        api_url = f"{settings.ebay_api_base_url}/sell/inventory/v1/bulk_publish_offer"

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        body = {"requests": [{"offerId": oid} for oid in offer_ids]}

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(api_url, headers=headers, json=body)
        except httpx.RequestError as e:
            error_msg = f"HTTP request failed during bulk_publish_offer: {e}"
            logger.error(error_msg)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_msg,
            )

        try:
            payload: Any = response.json()
        except Exception:
            payload = {}

        if response.status_code not in (200, 207):
            error_body = payload or response.text
            logger.error(
                "bulk_publish_offer failed: status=%s body=%s",
                response.status_code,
                error_body,
            )
            raise HTTPException(
                status_code=response.status_code,
                detail={
                    "message": "bulkPublishOffer failed",
                    "status_code": response.status_code,
                    "body": error_body,
                },
            )

        if not isinstance(payload, dict):
            payload = {}

        return response.status_code, payload

    async def sync_all_transactions(
        self,
        user_id: str,
        access_token: str,
        run_id: Optional[str] = None,
        ebay_account_id: Optional[str] = None,
        ebay_user_id: Optional[str] = None,
        window_from: Optional[str] = None,
        window_to: Optional[str] = None,
        environment: Optional[str] = None,
        *,
        mode: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Synchronize transactions from eBay to database with pagination (limit=200).

        If `window_from`/`window_to` are provided, restricts the sync to that
        transactionDate window. Otherwise, defaults to a 90-day backfill window
        ending at "now" (UTC).

        Args:
            user_id: User ID
            access_token: eBay OAuth access token
            run_id: Optional run_id for sync event logging
            ebay_account_id: Optional internal eBay account id for tagging
            ebay_user_id: Optional eBay user id for tagging
            window_from: Optional ISO8601 datetime (UTC) for the start of the window
            window_to: Optional ISO8601 datetime (UTC) for the end of the window
            environment: Optional environment override (sandbox/production)
            mode: Optional mode label ("manual", "automatic", "internal_scheduler")
            correlation_id: Optional correlation ID for tracking this sync batch
        """
        from app.services.ebay_database import ebay_db
        from app.services.sync_event_logger import SyncEventLogger
        from app.utils.build_info import get_build_number
        import time
        import traceback
        
        # CRITICAL: Log entry point and token status
        build_number = get_build_number()
        token_is_encrypted = access_token.startswith("ENC:") if access_token else False
        token_prefix = access_token[:30] if access_token else "None"
        caller_stack = "".join(traceback.format_stack()[-3:-1])  # Last 2 frames before this
        
        logger.error(
            "[sync_all_transactions] ENTRY POINT: user_id=%s ebay_account_id=%s ebay_user_id=%s "
            "run_id=%s mode=%s correlation_id=%s token_prefix=%s... token_is_encrypted=%s BUILD=%s",
            user_id, ebay_account_id, ebay_user_id, run_id, mode, correlation_id,
            token_prefix, token_is_encrypted, build_number
        )
        logger.error(
            "[sync_all_transactions] CALLER STACK:\n%s",
            caller_stack
        )
        
        # CRITICAL: Fail immediately if token is encrypted
        if token_is_encrypted:
            logger.error(
                "[sync_all_transactions] ⚠️⚠️⚠️ CRITICAL: ENCRYPTED TOKEN RECEIVED! "
                "user_id=%s ebay_account_id=%s run_id=%s mode=%s token_prefix=%s... "
                "This should NEVER happen - BaseWorker.run_for_account() should have decrypted it! BUILD=%s",
                user_id, ebay_account_id, run_id, mode, token_prefix, build_number
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Access token is encrypted (ENC:v1:...) - decryption failed. Check SECRET_KEY configuration."
            )

        # Use provided run_id if available, otherwise create new one
        event_logger = SyncEventLogger(user_id, 'transactions', run_id=run_id)
        job_id = ebay_db.create_sync_job(user_id, 'transactions')
        start_time = time.time()

        try:
            total_fetched = 0
            total_stored = 0

            from datetime import datetime, timedelta, timezone

            # Determine effective date range
            now_utc = datetime.now(timezone.utc)

            def _parse_iso(dt_str: str) -> Optional[datetime]:
                try:
                    # Support both "...Z" and "+00:00" style
                    if dt_str.endswith('Z'):
                        dt_str = dt_str.replace('Z', '+00:00')
                    return datetime.fromisoformat(dt_str)
                except Exception:
                    return None

            end_date: datetime
            if window_to:
                parsed_to = _parse_iso(window_to)
                end_date = parsed_to or now_utc
            else:
                end_date = now_utc

            if window_from:
                parsed_from = _parse_iso(window_from)
                if parsed_from:
                    start_date = parsed_from
                else:
                    start_date = end_date - timedelta(days=90)
            else:
                start_date = end_date - timedelta(days=90)

            limit = TRANSACTIONS_PAGE_LIMIT
            offset = 0
            has_more = True
            current_page = 0
            max_pages = 200  # Safety limit to prevent infinite loops

            # Get user identity for logging "who we are"
            # Pass environment to ensure we call the correct API endpoint
            identity = await self.get_user_identity(access_token, environment=environment)
            username = identity.get("username", "unknown")
            identity_ebay_user_id = identity.get("userId", "unknown")

            effective_ebay_user_id = ebay_user_id or identity_ebay_user_id

            # Log Identity API errors if any
            if identity.get("error"):
                event_logger.log_error(f"Identity API error: {identity.get('error')}")
                event_logger.log_warning("⚠️ Token may be invalid or missing required scopes. Please reconnect to eBay.")

            days_span = (end_date - start_date).days
            event_logger.log_start(
                f"Starting Transactions sync from eBay ({environment or settings.EBAY_ENVIRONMENT}) - using bulk limit={limit}"
            )
            event_logger.log_info(f"=== WHO WE ARE ===")
            event_logger.log_info(f"Connected as: {username} (eBay UserID: {effective_ebay_user_id})")
            event_logger.log_info(f"Environment: {settings.EBAY_ENVIRONMENT}")
            event_logger.log_info(f"API Configuration: Finances API v1, max batch size: {limit} transactions per request")
            event_logger.log_info(
                f"Date range: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')} (~{days_span} days)"
            )
            event_logger.log_info(
                f"Window: {start_date.strftime('%Y-%m-%dT%H:%M:%S.000Z')}..{end_date.strftime('%Y-%m-%dT%H:%M:%S.000Z')}"
            )
            event_logger.log_info(f"Safety limit: max {max_pages} pages")
            logger.info(
                f"Starting transaction sync for user {user_id} ({username}) with limit={limit}, "
                f"window={start_date.isoformat()}..{end_date.isoformat()}"
            )

            await asyncio.sleep(0.5)

            while has_more:
                # Safety check: max pages limit
                if current_page >= max_pages:
                    event_logger.log_warning(
                        f"Reached safety limit of {max_pages} pages. Stopping to prevent infinite loop."
                    )
                    logger.warning(
                        f"Transactions sync reached max_pages limit ({max_pages}) for run_id {event_logger.run_id}"
                    )
                    break
                # Check for cancellation
                from app.services.sync_event_logger import is_cancelled
                if is_cancelled(event_logger.run_id):
                    logger.info(f"Transaction sync cancelled for run_id {event_logger.run_id}")
                    event_logger.log_warning("Sync operation cancelled by user")
                    event_logger.log_done(
                        f"Transactions sync cancelled: {total_fetched} fetched, {total_stored} stored",
                        total_fetched,
                        total_stored,
                        int((time.time() - start_time) * 1000)
                    )
                    event_logger.close()
                    return {
                        "status": "cancelled",
                        "total_fetched": total_fetched,
                        "total_stored": total_stored,
                        "job_id": job_id,
                        "run_id": event_logger.run_id,
                    }

                current_page += 1
                # Use RSQL filter format: restrict transactionDate to our effective window
                filter_params = {
                    'filter': (
                        f"transactionDate:[{start_date.strftime('%Y-%m-%dT%H:%M:%S.000Z')}.."
                        f"{end_date.strftime('%Y-%m-%dT%H:%M:%S.000Z')}]"
                    ),
                    'limit': limit,
                    'offset': offset,
                }

                # Check for cancellation BEFORE making the API request
                from app.services.sync_event_logger import is_cancelled
                if is_cancelled(event_logger.run_id):
                    logger.info(
                        f"Transactions sync cancelled for run_id {event_logger.run_id} (before API request)"
                    )
                    event_logger.log_warning("Sync operation cancelled by user")
                    event_logger.log_done(
                        f"Transactions sync cancelled: {total_fetched} fetched, {total_stored} stored",
                        total_fetched,
                        total_stored,
                        int((time.time() - start_time) * 1000)
                    )
                    event_logger.close()
                    return {
                        "status": "cancelled",
                        "total_fetched": total_fetched,
                        "total_stored": total_stored,
                        "job_id": job_id,
                        "run_id": event_logger.run_id,
                    }

                event_logger.log_info(
                    f"→ Requesting page {current_page}: GET /sell/finances/v1/transaction?limit={limit}&offset={offset}"
                )

                request_start = time.time()
                try:
                    transactions_response = await self.fetch_transactions(
                        access_token, 
                        filter_params, 
                        environment=environment,
                        mode=mode,
                        correlation_id=correlation_id,
                        account_id=ebay_account_id,
                        ebay_user_id=ebay_user_id,
                    )
                except Exception as e:
                    # Check for cancellation after error
                    if is_cancelled(event_logger.run_id):
                        logger.info(
                            f"Transactions sync cancelled for run_id {event_logger.run_id} (after API error)"
                        )
                        event_logger.log_warning("Sync operation cancelled by user")
                        event_logger.log_done(
                            f"Transactions sync cancelled: {total_fetched} fetched, {total_stored} stored",
                            total_fetched,
                            total_stored,
                            int((time.time() - start_time) * 1000)
                        )
                        event_logger.close()
                        return {
                            "status": "cancelled",
                            "total_fetched": total_fetched,
                            "total_stored": total_stored,
                            "job_id": job_id,
                            "run_id": event_logger.run_id,
                        }
                    raise
                request_duration = int((time.time() - request_start) * 1000)

                # Check for cancellation AFTER the API request
                if is_cancelled(event_logger.run_id):
                    logger.info(
                        f"Transactions sync cancelled for run_id {event_logger.run_id} (after API request)"
                    )
                    event_logger.log_warning("Sync operation cancelled by user")
                    event_logger.log_done(
                        f"Transactions sync cancelled: {total_fetched} fetched, {total_stored} stored",
                        total_fetched,
                        total_stored,
                        int((time.time() - start_time) * 1000)
                    )
                    event_logger.close()
                    return {
                        "status": "cancelled",
                        "total_fetched": total_fetched,
                        "total_stored": total_stored,
                        "job_id": job_id,
                        "run_id": event_logger.run_id,
                    }

                transactions = transactions_response.get('transactions', [])
                total = transactions_response.get('total', 0) or 0  # Ensure total is always a number
                total_pages = (total + limit - 1) // limit if total > 0 else 1

                event_logger.log_http_request(
                    'GET',
                    f'/sell/finances/v1/transaction?limit={limit}&offset={offset}',
                    200,
                    request_duration,
                    len(transactions),
                )

                event_logger.log_info(
                    f"← Response: 200 OK ({request_duration}ms) - Received {len(transactions)} transactions (Total available: {total})"
                )

                # Early exit if total == 0 (no transactions in window)
                if total == 0 and current_page == 1:
                    event_logger.log_info("✓ No transactions found in date window. Total available: 0")
                    event_logger.log_warning("No transactions in window - check date range, account, or environment")
                    break

                total_fetched += len(transactions)

                await asyncio.sleep(0.3)

                # Check for cancellation before storing
                if is_cancelled(event_logger.run_id):
                    logger.info(
                        f"Transactions sync cancelled for run_id {event_logger.run_id} (before storing)"
                    )
                    event_logger.log_warning("Sync operation cancelled by user")
                    event_logger.log_done(
                        f"Transactions sync cancelled: {total_fetched} fetched, {total_stored} stored",
                        total_fetched,
                        total_stored,
                        int((time.time() - start_time) * 1000)
                    )
                    event_logger.close()
                    return {
                        "status": "cancelled",
                        "total_fetched": total_fetched,
                        "total_stored": total_stored,
                        "job_id": job_id,
                        "run_id": event_logger.run_id,
                    }

                event_logger.log_info(f"→ Storing {len(transactions)} transactions in database...")
                store_start = time.time()
                batch_stored = 0
                for transaction in transactions:
                    if ebay_db.upsert_transaction(  # type: ignore[arg-type]
                        user_id,
                        transaction,
                        ebay_account_id=ebay_account_id,
                        ebay_user_id=effective_ebay_user_id,
                    ):
                        batch_stored += 1
                total_stored += batch_stored
                store_duration = int((time.time() - store_start) * 1000)

                event_logger.log_info(
                    f"← Database: Stored {batch_stored} transactions ({store_duration}ms)"
                )

                event_logger.log_progress(
                    f"Page {current_page}/{total_pages} complete: {len(transactions)} fetched, {batch_stored} stored | "
                    f"Running total: {total_fetched}/{total} fetched, {total_stored} stored",
                    current_page,
                    total_pages,
                    total_fetched,
                    total_stored,
                )

                logger.info(
                    f"Synced batch: {len(transactions)} transactions (total: {total_fetched}/{total}, stored: {total_stored})"
                )

                # Check for cancellation before continuing to next page
                if is_cancelled(event_logger.run_id):
                    logger.info(
                        f"Transactions sync cancelled for run_id {event_logger.run_id} (before next page)"
                    )
                    event_logger.log_warning("Sync operation cancelled by user")
                    event_logger.log_done(
                        f"Transactions sync cancelled: {total_fetched} fetched, {total_stored} stored",
                        total_fetched,
                        total_stored,
                        int((time.time() - start_time) * 1000)
                    )
                    event_logger.close()
                    return {
                        "status": "cancelled",
                        "total_fetched": total_fetched,
                        "total_stored": total_stored,
                        "job_id": job_id,
                        "run_id": event_logger.run_id,
                    }

                # Update has_more BEFORE incrementing offset to prevent infinite loops
                # Stop if: no more transactions, or we've fetched all available, or offset would exceed total
                has_more = (
                    len(transactions) > 0
                    and len(transactions) == limit
                    and (offset + limit) < total
                )

                offset += limit

                if has_more:
                    await asyncio.sleep(0.8)

            duration_ms = int((time.time() - start_time) * 1000)
            ebay_db.update_sync_job(job_id, 'completed', total_fetched, total_stored)

            event_logger.log_done(
                f"Transactions sync completed: {total_fetched} fetched, {total_stored} stored in {duration_ms}ms",
                total_fetched,
                total_stored,
                duration_ms,
            )

            logger.info(
                f"Transaction sync completed: fetched={total_fetched}, stored={total_stored}, "
                f"window={start_date.isoformat()}..{end_date.isoformat()}"
            )

            return {
                "status": "completed",
                "total_fetched": total_fetched,
                "total_stored": total_stored,
                "job_id": job_id,
                "run_id": event_logger.run_id,
            }

        except Exception as e:
            error_msg = str(e)
            event_logger.log_error(f"Transactions sync failed: {error_msg}", e)
            logger.error(f"Transaction sync failed: {error_msg}")
            ebay_db.update_sync_job(job_id, 'failed', error_message=error_msg)
            raise
        finally:
            event_logger.close()

    async def sync_finances_transactions(
        self,
        user_id: str,
        access_token: str,
        run_id: Optional[str] = None,
        ebay_account_id: Optional[str] = None,
        ebay_user_id: Optional[str] = None,
        window_from: Optional[str] = None,
        window_to: Optional[str] = None,
        environment: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Synchronize Finances transactions into Postgres tables.

        This mirrors ``sync_all_transactions`` but writes into
        ``ebay_finances_transactions`` / ``ebay_finances_fees`` using
        ``PostgresEbayDatabase.upsert_finances_transaction``.
        """
        from app.services.postgres_ebay_database import PostgresEbayDatabase
        from app.services.sync_event_logger import SyncEventLogger
        import time

        fin_db = PostgresEbayDatabase()

        # Use provided run_id if available, otherwise create new one
        event_logger = SyncEventLogger(user_id, "finances", run_id=run_id)
        job_id = fin_db.create_sync_job(user_id, "finances")
        start_time = time.time()

        try:
            total_fetched = 0
            total_stored = 0

            from datetime import datetime, timedelta, timezone

            # Determine effective date range
            now_utc = datetime.now(timezone.utc)

            def _parse_iso(dt_str: str) -> Optional[datetime]:
                try:
                    # Support both "...Z" and "+00:00" style
                    if dt_str.endswith("Z"):
                        dt_str = dt_str.replace("Z", "+00:00")
                    return datetime.fromisoformat(dt_str)
                except Exception:
                    return None

            end_date: datetime
            if window_to:
                parsed_to = _parse_iso(window_to)
                end_date = parsed_to or now_utc
            else:
                end_date = now_utc

            if window_from:
                parsed_from = _parse_iso(window_from)
                if parsed_from:
                    start_date = parsed_from
                else:
                    start_date = end_date - timedelta(days=90)
            else:
                start_date = end_date - timedelta(days=90)

            limit = TRANSACTIONS_PAGE_LIMIT
            offset = 0
            has_more = True
            current_page = 0
            max_pages = 200  # Safety limit to prevent infinite loops

            # Get user identity for logging "who we are"
            # Pass environment to ensure we call the correct API endpoint
            identity = await self.get_user_identity(access_token, environment=environment)
            username = identity.get("username", "unknown")
            identity_ebay_user_id = identity.get("userId", "unknown")

            effective_ebay_user_id = ebay_user_id or identity_ebay_user_id

            # Log Identity API errors if any
            if identity.get("error"):
                event_logger.log_error(f"Identity API error: {identity.get('error')}")
                event_logger.log_warning(
                    "⚠️ Token may be invalid or missing required scopes. Please reconnect to eBay."
                )

            days_span = (end_date - start_date).days
            event_logger.log_start(
                f"Starting Finances transactions sync from eBay ({environment or settings.EBAY_ENVIRONMENT}) - using bulk limit={limit}"
            )
            event_logger.log_info("=== WHO WE ARE ===")
            event_logger.log_info(
                f"Connected as: {username} (eBay UserID: {effective_ebay_user_id})"
            )
            event_logger.log_info(f"Environment: {settings.EBAY_ENVIRONMENT}")
            event_logger.log_info(
                f"API Configuration: Finances API v1, max batch size: {limit} transactions per request"
            )
            event_logger.log_info(
                f"Date range: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')} (~{days_span} days)"
            )
            event_logger.log_info(
                f"Window: {start_date.strftime('%Y-%m-%dT%H:%M:%S.000Z')}..{end_date.strftime('%Y-%m-%dT%H:%M:%S.000Z')}"
            )
            event_logger.log_info(f"Safety limit: max {max_pages} pages")
            logger.info(
                f"Starting finances transaction sync for user {user_id} ({username}) with limit={limit}, "
                f"window={start_date.isoformat()}..{end_date.isoformat()}"
            )

            await asyncio.sleep(0.5)

            from app.services.sync_event_logger import is_cancelled

            while has_more:
                # Safety check: max pages limit
                if current_page >= max_pages:
                    event_logger.log_warning(
                        f"Reached safety limit of {max_pages} pages. Stopping to prevent infinite loop."
                    )
                    logger.warning(
                        "Finances transactions sync reached max_pages limit (%s) for run_id %s",
                        max_pages,
                        event_logger.run_id,
                    )
                    break

                # Check for cancellation
                if is_cancelled(event_logger.run_id):
                    logger.info(
                        "Finances transactions sync cancelled for run_id %s",
                        event_logger.run_id,
                    )
                    event_logger.log_warning("Sync operation cancelled by user")
                    event_logger.log_done(
                        f"Finances transactions sync cancelled: {total_fetched} fetched, {total_stored} stored",
                        total_fetched,
                        total_stored,
                        int((time.time() - start_time) * 1000),
                    )
                    event_logger.close()
                    return {
                        "status": "cancelled",
                        "total_fetched": total_fetched,
                        "total_stored": total_stored,
                        "job_id": job_id,
                        "run_id": event_logger.run_id,
                    }

                current_page += 1
                # Use RSQL filter format: restrict transactionDate to our effective window
                filter_params = {
                    "filter": (
                        f"transactionDate:[{start_date.strftime('%Y-%m-%dT%H:%M:%S.000Z')}.."
                        f"{end_date.strftime('%Y-%m-%dT%H:%M:%S.000Z')}]"
                    ),
                    "limit": limit,
                    "offset": offset,
                }

                # Check for cancellation BEFORE making the API request
                if is_cancelled(event_logger.run_id):
                    logger.info(
                        "Finances transactions sync cancelled for run_id %s (before API request)",
                        event_logger.run_id,
                    )
                    event_logger.log_warning("Sync operation cancelled by user")
                    event_logger.log_done(
                        f"Finances transactions sync cancelled: {total_fetched} fetched, {total_stored} stored",
                        total_fetched,
                        total_stored,
                        int((time.time() - start_time) * 1000),
                    )
                    event_logger.close()
                    return {
                        "status": "cancelled",
                        "total_fetched": total_fetched,
                        "total_stored": total_stored,
                        "job_id": job_id,
                        "run_id": event_logger.run_id,
                    }

                event_logger.log_info(
                    f"→ Requesting page {current_page}: GET /sell/finances/v1/transaction?limit={limit}&offset={offset}"
                )

                request_start = time.time()
                try:
                    transactions_response = await self.fetch_transactions(
                        access_token, filter_params, environment=environment
                    )
                except Exception as e:
                    # Check for cancellation after error
                    if is_cancelled(event_logger.run_id):
                        logger.info(
                            "Finances transactions sync cancelled for run_id %s (after API error)",
                            event_logger.run_id,
                        )
                        event_logger.log_warning("Sync operation cancelled by user")
                        event_logger.log_done(
                            f"Finances transactions sync cancelled: {total_fetched} fetched, {total_stored} stored",
                            total_fetched,
                            total_stored,
                            int((time.time() - start_time) * 1000),
                        )
                        event_logger.close()
                        return {
                            "status": "cancelled",
                            "total_fetched": total_fetched,
                            "total_stored": total_stored,
                            "job_id": job_id,
                            "run_id": event_logger.run_id,
                        }
                    raise
                request_duration = int((time.time() - request_start) * 1000)

                # Check for cancellation AFTER the API request
                if is_cancelled(event_logger.run_id):
                    logger.info(
                        "Finances transactions sync cancelled for run_id %s (after API request)",
                        event_logger.run_id,
                    )
                    event_logger.log_warning("Sync operation cancelled by user")
                    event_logger.log_done(
                        f"Finances transactions sync cancelled: {total_fetched} fetched, {total_stored} stored",
                        total_fetched,
                        total_stored,
                        int((time.time() - start_time) * 1000),
                    )
                    event_logger.close()
                    return {
                        "status": "cancelled",
                        "total_fetched": total_fetched,
                        "total_stored": total_stored,
                        "job_id": job_id,
                        "run_id": event_logger.run_id,
                    }

                transactions = transactions_response.get("transactions", [])
                total = transactions_response.get("total", 0) or 0
                total_pages = (total + limit - 1) // limit if total > 0 else 1

                event_logger.log_http_request(
                    "GET",
                    f"/sell/finances/v1/transaction?limit={limit}&offset={offset}",
                    200,
                    request_duration,
                    len(transactions),
                )

                event_logger.log_info(
                    f"← Response: 200 OK ({request_duration}ms) - Received {len(transactions)} transactions (Total available: {total})"
                )

                # Early exit if total == 0 (no transactions in window)
                if total == 0 and current_page == 1:
                    event_logger.log_info(
                        "✓ No finances transactions found in date window. Total available: 0"
                    )
                    event_logger.log_warning(
                        "No finances transactions in window - check date range, account, or environment"
                    )
                    break

                total_fetched += len(transactions)

                await asyncio.sleep(0.3)

                # Check for cancellation before storing
                if is_cancelled(event_logger.run_id):
                    logger.info(
                        "Finances transactions sync cancelled for run_id %s (before storing)",
                        event_logger.run_id,
                    )
                    event_logger.log_warning("Sync operation cancelled by user")
                    event_logger.log_done(
                        f"Finances transactions sync cancelled: {total_fetched} fetched, {total_stored} stored",
                        total_fetched,
                        total_stored,
                        int((time.time() - start_time) * 1000),
                    )
                    event_logger.close()
                    return {
                        "status": "cancelled",
                        "total_fetched": total_fetched,
                        "total_stored": total_stored,
                        "job_id": job_id,
                        "run_id": event_logger.run_id,
                    }

                event_logger.log_info(
                    f"→ Storing {len(transactions)} finances transactions in database..."
                )
                store_start = time.time()
                batch_stored = 0
                for transaction in transactions:
                    if fin_db.upsert_finances_transaction(
                        user_id,
                        transaction,
                        ebay_account_id=ebay_account_id,
                        ebay_user_id=effective_ebay_user_id,
                    ):
                        batch_stored += 1
                total_stored += batch_stored
                store_duration = int((time.time() - store_start) * 1000)

                event_logger.log_info(
                    f"← Database: Stored {batch_stored} finances transactions ({store_duration}ms)"
                )

                event_logger.log_progress(
                    f"Page {current_page}/{total_pages} complete: {len(transactions)} fetched, {batch_stored} stored | "
                    f"Running total: {total_fetched}/{total} fetched, {total_stored} stored",
                    current_page,
                    total_pages,
                    len(transactions),
                    batch_stored,
                )

                logger.info(
                    "Synced finances batch: %s transactions (total: %s/%s, stored: %s)",
                    len(transactions),
                    total_fetched,
                    total,
                    total_stored,
                )

                # Check for cancellation before continuing to next page
                if is_cancelled(event_logger.run_id):
                    logger.info(
                        "Finances transactions sync cancelled for run_id %s (before next page)",
                        event_logger.run_id,
                    )
                    event_logger.log_warning("Sync operation cancelled by user")
                    event_logger.log_done(
                        f"Finances transactions sync cancelled: {total_fetched} fetched, {total_stored} stored",
                        total_fetched,
                        total_stored,
                        int((time.time() - start_time) * 1000),
                    )
                    event_logger.close()
                    return {
                        "status": "cancelled",
                        "total_fetched": total_fetched,
                        "total_stored": total_stored,
                        "job_id": job_id,
                        "run_id": event_logger.run_id,
                    }

                # Update has_more BEFORE incrementing offset to prevent infinite loops
                has_more = (
                    len(transactions) > 0
                    and len(transactions) == limit
                    and (offset + limit) < total
                )

                offset += limit

                if has_more:
                    await asyncio.sleep(0.8)

            duration_ms = int((time.time() - start_time) * 1000)
            fin_db.update_sync_job(job_id, "completed", total_fetched, total_stored)

            event_logger.log_done(
                f"Finances transactions sync completed: {total_fetched} fetched, {total_stored} stored in {duration_ms}ms",
                total_fetched,
                total_stored,
                duration_ms,
            )

            logger.info(
                "Finances transactions sync completed: fetched=%s, stored=%s, window=%s..%s",
                total_fetched,
                total_stored,
                start_date.isoformat(),
                end_date.isoformat(),
            )

            return {
                "status": "completed",
                "total_fetched": total_fetched,
                "total_stored": total_stored,
                "job_id": job_id,
                "run_id": event_logger.run_id,
            }

        except Exception as e:
            error_msg = str(e)
            event_logger.log_error(f"Finances transactions sync failed: {error_msg}", e)
            logger.error(f"Finances transactions sync failed: {error_msg}")
            fin_db.update_sync_job(job_id, "failed", error_message=error_msg)
            raise
        finally:
            event_logger.close()

    async def sync_all_disputes(
        self,
        user_id: str,
        access_token: str,
        run_id: Optional[str] = None,
        ebay_account_id: Optional[str] = None,
        ebay_user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Synchronize all payment disputes from eBay to database with logging."""
        from app.services.ebay_database import ebay_db
        from app.services.sync_event_logger import SyncEventLogger
        import time
        
        # Use provided run_id if available, otherwise create new one
        event_logger = SyncEventLogger(user_id, 'disputes', run_id=run_id)
        job_id = ebay_db.create_sync_job(user_id, 'disputes')
        start_time = time.time()
        
        try:
            total_fetched = 0
            total_stored = 0
            
            event_logger.log_start(f"Starting Disputes sync from eBay ({settings.EBAY_ENVIRONMENT})")
            event_logger.log_info(f"API Configuration: Fulfillment API v1 payment_dispute")
            logger.info(f"Starting disputes sync for user {user_id}")
            
            await asyncio.sleep(0.5)
            
            # Check for cancellation before starting
            from app.services.sync_event_logger import is_cancelled
            if is_cancelled(event_logger.run_id):
                logger.info(f"Disputes sync cancelled for run_id {event_logger.run_id}")
                event_logger.log_warning("Sync operation cancelled by user")
                event_logger.log_done(
                    f"Disputes sync cancelled: 0 fetched, 0 stored",
                    0,
                    0,
                    int((time.time() - start_time) * 1000)
                )
                event_logger.close()
                return {
                    "status": "cancelled",
                    "total_fetched": 0,
                    "total_stored": 0,
                    "job_id": job_id,
                    "run_id": event_logger.run_id
                }
            
            # Check for cancellation BEFORE making the API request
            if is_cancelled(event_logger.run_id):
                logger.info(f"Disputes sync cancelled for run_id {event_logger.run_id} (before API request)")
                event_logger.log_warning("Sync operation cancelled by user")
                event_logger.log_done(
                    f"Disputes sync cancelled: 0 fetched, 0 stored",
                    0,
                    0,
                    int((time.time() - start_time) * 1000)
                )
                event_logger.close()
                return {
                    "status": "cancelled",
                    "total_fetched": 0,
                    "total_stored": 0,
                    "job_id": job_id,
                    "run_id": event_logger.run_id
                }
            
            event_logger.log_info(f"→ Requesting: POST /sell/fulfillment/v1/payment_dispute_summary/search")
            
            request_start = time.time()
            try:
                disputes_response = await self.fetch_payment_disputes(access_token)
            except Exception as e:
                # Check for cancellation after error
                if is_cancelled(event_logger.run_id):
                    logger.info(f"Disputes sync cancelled for run_id {event_logger.run_id} (after API error)")
                    event_logger.log_warning("Sync operation cancelled by user")
                    event_logger.log_done(
                        f"Disputes sync cancelled: 0 fetched, 0 stored",
                        0,
                        0,
                        int((time.time() - start_time) * 1000)
                    )
                    event_logger.close()
                    return {
                        "status": "cancelled",
                        "total_fetched": 0,
                        "total_stored": 0,
                        "job_id": job_id,
                        "run_id": event_logger.run_id
                    }
                raise
            request_duration = int((time.time() - request_start) * 1000)
            
            # Check for cancellation after API call
            if is_cancelled(event_logger.run_id):
                logger.info(f"Disputes sync cancelled for run_id {event_logger.run_id}")
                event_logger.log_warning("Sync operation cancelled by user")
                event_logger.log_done(
                    f"Disputes sync cancelled: 0 fetched, 0 stored",
                    0,
                    0,
                    int((time.time() - start_time) * 1000)
                )
                event_logger.close()
                return {
                    "status": "cancelled",
                    "total_fetched": 0,
                    "total_stored": 0,
                    "job_id": job_id,
                    "run_id": event_logger.run_id
                }
            
            disputes = disputes_response.get('paymentDisputeSummaries', [])
            total_fetched = len(disputes)
            
            event_logger.log_http_request(
                'GET',
                '/sell/fulfillment/v1/payment_dispute',
                200,
                request_duration,
                total_fetched
            )
            
            event_logger.log_info(f"← Response: 200 OK ({request_duration}ms) - Received {total_fetched} disputes")
            
            await asyncio.sleep(0.3)
            
            event_logger.log_info(f"→ Storing {total_fetched} disputes in database...")
            store_start = time.time()
            for dispute in disputes:
                # Check for cancellation during storage
                if is_cancelled(event_logger.run_id):
                    logger.info(f"Disputes sync cancelled for run_id {event_logger.run_id}")
                    event_logger.log_warning("Sync operation cancelled by user")
                    event_logger.log_done(
                        f"Disputes sync cancelled: {total_fetched} fetched, {total_stored} stored",
                        total_fetched,
                        total_stored,
                        int((time.time() - start_time) * 1000)
                    )
                    event_logger.close()
                    return {
                        "status": "cancelled",
                        "total_fetched": total_fetched,
                        "total_stored": total_stored,
                        "job_id": job_id,
                        "run_id": event_logger.run_id
                    }
                
                if ebay_db.upsert_dispute(
                    user_id,
                    dispute,
                    ebay_account_id=ebay_account_id,
                    ebay_user_id=ebay_user_id,
                ):
                    total_stored += 1
            store_duration = int((time.time() - store_start) * 1000)
            
            event_logger.log_info(f"← Database: Stored {total_stored} disputes ({store_duration}ms)")
            
            event_logger.log_progress(
                f"Disputes sync complete: {total_fetched} fetched, {total_stored} stored",
                1,
                1,
                total_fetched,
                total_stored
            )
            
            duration_ms = int((time.time() - start_time) * 1000)
            ebay_db.update_sync_job(job_id, 'completed', total_fetched, total_stored)
            
            event_logger.log_done(
                f"Disputes sync completed: {total_fetched} fetched, {total_stored} stored in {duration_ms}ms",
                total_fetched,
                total_stored,
                duration_ms
            )
            
            logger.info(f"Disputes sync completed: fetched={total_fetched}, stored={total_stored}")
            
            return {
                "status": "completed",
                "total_fetched": total_fetched,
                "total_stored": total_stored,
                "job_id": job_id,
                "run_id": event_logger.run_id
            }
            
        except Exception as e:
            error_msg = str(e)
            event_logger.log_error(f"Disputes sync failed: {error_msg}", e)
            logger.error(f"Disputes sync failed: {error_msg}")
            ebay_db.update_sync_job(job_id, 'failed', error_message=error_msg)
            raise
        finally:
            event_logger.close()

    async def sync_postorder_inquiries(
        self,
        user_id: str,
        access_token: str,
        run_id: Optional[str] = None,
        ebay_account_id: Optional[str] = None,
        ebay_user_id: Optional[str] = None,
        window_from: Optional[str] = None,
        window_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Sync Post-Order inquiries into ebay_inquiries.

        Similar to sync_postorder_cases, this currently treats the time window as
        metadata for logging and the worker cursor while the API call itself
        fetches the latest inquiries available.
        """
        from app.services.ebay_database import ebay_db
        from app.services.sync_event_logger import SyncEventLogger
        import time

        event_logger = SyncEventLogger(user_id, "inquiries", run_id=run_id)
        job_id = ebay_db.create_sync_job(user_id, "inquiries")
        start_time = time.time()

        try:
            total_fetched = 0
            total_stored = 0

            event_logger.log_start(
                f"Starting Post-Order inquiries sync from eBay ({settings.EBAY_ENVIRONMENT})",
            )
            logger.info(f"Starting Post-Order inquiries sync for user {user_id}")

            await asyncio.sleep(0.3)

            from app.services.sync_event_logger import is_cancelled

            if is_cancelled(event_logger.run_id):
                logger.info(
                    f"Inquiries sync cancelled for run_id {event_logger.run_id} (before API request)",
                )
                event_logger.log_warning("Sync operation cancelled by user")
                duration_ms = int((time.time() - start_time) * 1000)
                event_logger.log_done(
                    "Inquiries sync cancelled: 0 fetched, 0 stored",
                    0,
                    0,
                    duration_ms,
                )
                ebay_db.update_sync_job(job_id, "cancelled", 0, 0)
                return {
                    "status": "cancelled",
                    "total_fetched": 0,
                    "total_stored": 0,
                    "job_id": job_id,
                    "run_id": event_logger.run_id,
                }

            event_logger.log_info("→ Requesting: GET /post-order/v2/inquiry/search")
            request_start = time.time()
            try:
                inquiries_response = await self.fetch_inquiries(access_token)
            except Exception:
                if is_cancelled(event_logger.run_id):
                    logger.info(
                        f"Inquiries sync cancelled for run_id {event_logger.run_id} (after API error)",
                    )
                    event_logger.log_warning("Sync operation cancelled by user")
                    duration_ms = int((time.time() - start_time) * 1000)
                    event_logger.log_done(
                        "Inquiries sync cancelled: 0 fetched, 0 stored",
                        0,
                        0,
                        duration_ms,
                    )
                    ebay_db.update_sync_job(job_id, "cancelled", 0, 0)
                    return {
                        "status": "cancelled",
                        "total_fetched": 0,
                        "total_stored": 0,
                        "job_id": job_id,
                        "run_id": event_logger.run_id,
                    }
                raise

            request_duration = int((time.time() - request_start) * 1000)

            inquiries = (
                inquiries_response.get("inquiries")
                or inquiries_response.get("inquirySummaries")
                or inquiries_response.get("members")
                or []
            )
            total_fetched = len(inquiries)

            event_logger.log_http_request(
                "GET",
                "/post-order/v2/inquiry/search",
                200,
                request_duration,
                total_fetched,
            )
            event_logger.log_info(
                f"← Response: 200 OK ({request_duration}ms) - Received {total_fetched} inquiries",
            )

            await asyncio.sleep(0.2)

            stored = 0
            for inquiry in inquiries:
                if is_cancelled(event_logger.run_id):
                    logger.info(
                        f"Inquiries sync cancelled for run_id {event_logger.run_id} (during storage)",
                    )
                    event_logger.log_warning("Sync operation cancelled by user")
                    duration_ms = int((time.time() - start_time) * 1000)
                    event_logger.log_done(
                        f"Inquiries sync cancelled: {total_fetched} fetched, {stored} stored",
                        total_fetched,
                        stored,
                        duration_ms,
                    )
                    ebay_db.update_sync_job(job_id, "cancelled", total_fetched, stored)
                    return {
                        "status": "cancelled",
                        "total_fetched": total_fetched,
                        "total_stored": stored,
                        "job_id": job_id,
                        "run_id": event_logger.run_id,
                    }

                # Prefer detailed inquiry payload when available so raw_json carries
                # the full timeline/state from the Post-Order API.
                detail_payload: Dict[str, Any] = inquiry
                inquiry_id = (
                    inquiry.get("inquiryId")
                    or inquiry.get("inquiry_id")
                )
                if inquiry_id:
                    try:
                        detail_payload = await self.fetch_inquiry_detail(access_token, inquiry_id)
                    except HTTPException as http_exc:  # pragma: no cover - defensive
                        # Log a warning but fall back to the summary row so the
                        # grid remains populated.
                        try:
                            detail = http_exc.detail  # type: ignore[assignment]
                        except Exception:
                            detail = str(http_exc)
                        event_logger.log_warning(
                            f"Failed to fetch inquiry detail for {inquiry_id}: {detail}",
                        )
                    except Exception as exc:  # pragma: no cover - defensive
                        event_logger.log_warning(
                            f"Unexpected error fetching inquiry detail for {inquiry_id}: {exc}",
                        )

                try:
                    ok = ebay_db.upsert_inquiry(  # type: ignore[attr-defined]
                        user_id,
                        detail_payload,
                        ebay_account_id=ebay_account_id,
                        ebay_user_id=ebay_user_id,
                    )
                except Exception as exc:  # pragma: no cover - defensive
                    logger.warning(
                        "Inquiries sync: failed to upsert inquiry payload: %s",
                        exc,
                        exc_info=True,
                    )
                    ok = False

                if ok:
                    stored += 1

            total_stored = stored
            duration_ms = int((time.time() - start_time) * 1000)
            ebay_db.update_sync_job(job_id, "completed", total_fetched, total_stored)

            event_logger.log_done(
                f"Inquiries sync completed: {total_fetched} fetched, {total_stored} stored in {duration_ms}ms",
                total_fetched,
                total_stored,
                duration_ms,
            )

            logger.info(
                "Inquiries sync completed: fetched=%s, stored=%s",
                total_fetched,
                total_stored,
            )

            return {
                "status": "completed",
                "total_fetched": total_fetched,
                "total_stored": total_stored,
                "job_id": job_id,
                "run_id": event_logger.run_id,
            }

        except Exception as e:
            error_msg = str(e)
            event_logger.log_error(f"Inquiries sync failed: {error_msg}", e)
            logger.error(f"Inquiries sync failed: {error_msg}")
            ebay_db.update_sync_job(job_id, "failed", error_message=error_msg)
            raise
        finally:
            event_logger.close()

    async def sync_postorder_cases(
        self,
        user_id: str,
        access_token: str,
        run_id: Optional[str] = None,
        ebay_account_id: Optional[str] = None,
        ebay_user_id: Optional[str] = None,
        window_from: Optional[str] = None,
        window_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Sync INR/SNAD Post-Order cases into ebay_cases.

        The Post-Order casemanagement/search endpoint does not expose a precise
        time-based filter that matches our internal cursor model, but we still
        accept ``window_from``/``window_to`` for logging and future use. For now,
        these values are recorded in the sync logs and the worker cursor while the
        API request itself fetches the latest available cases.
        """
        from app.services.ebay_database import ebay_db
        from app.services.sync_event_logger import SyncEventLogger
        import time

        event_logger = SyncEventLogger(user_id, "cases", run_id=run_id)
        job_id = ebay_db.create_sync_job(user_id, "cases")
        start_time = time.time()

        try:
            total_fetched = 0
            total_stored = 0
            normalized_full = 0
            normalized_partial = 0
            normalization_errors = 0

            event_logger.log_start(
                f"Starting Post-Order cases sync from eBay ({settings.EBAY_ENVIRONMENT})",
            )
            logger.info(f"Starting Post-Order cases sync for user {user_id}")

            await asyncio.sleep(0.3)

            from app.services.sync_event_logger import is_cancelled

            if is_cancelled(event_logger.run_id):
                logger.info(f"Cases sync cancelled for run_id {event_logger.run_id} (before API request)")
                event_logger.log_warning("Sync operation cancelled by user")
                duration_ms = int((time.time() - start_time) * 1000)
                event_logger.log_done(
                    "Cases sync cancelled: 0 fetched, 0 stored",
                    0,
                    0,
                    duration_ms,
                )
                ebay_db.update_sync_job(job_id, "cancelled", 0, 0)
                return {
                    "status": "cancelled",
                    "total_fetched": 0,
                    "total_stored": 0,
                    "job_id": job_id,
                    "run_id": event_logger.run_id,
                }

            event_logger.log_info("→ Requesting: GET /post-order/v2/casemanagement/search")
            request_start = time.time()
            try:
                cases_response = await self.fetch_postorder_cases(access_token)
            except Exception as exc:
                if is_cancelled(event_logger.run_id):
                    logger.info(
                        f"Cases sync cancelled for run_id {event_logger.run_id} (after API error)",
                    )
                    event_logger.log_warning("Sync operation cancelled by user")
                    duration_ms = int((time.time() - start_time) * 1000)
                    event_logger.log_done(
                        "Cases sync cancelled: 0 fetched, 0 stored",
                        0,
                        0,
                        duration_ms,
                    )
                    ebay_db.update_sync_job(job_id, "cancelled", 0, 0)
                    return {
                        "status": "cancelled",
                        "total_fetched": 0,
                        "total_stored": 0,
                        "job_id": job_id,
                        "run_id": event_logger.run_id,
                    }
                raise

            request_duration = int((time.time() - request_start) * 1000)

            cases = cases_response.get("cases") or cases_response.get("members") or []
            total_fetched = len(cases)

            event_logger.log_http_request(
                "GET",
                "/post-order/v2/casemanagement/search",
                200,
                request_duration,
                total_fetched,
            )
            event_logger.log_info(
                f"← Response: 200 OK ({request_duration}ms) - Received {total_fetched} cases",
            )

            await asyncio.sleep(0.2)

            stored = 0
            for c in cases:
                # Check for cancellation during storage loop
                if is_cancelled(event_logger.run_id):
                    logger.info(f"Cases sync cancelled for run_id {event_logger.run_id} (during storage)")
                    event_logger.log_warning("Sync operation cancelled by user")
                    duration_ms = int((time.time() - start_time) * 1000)
                    event_logger.log_done(
                        f"Cases sync cancelled: {total_fetched} fetched, {stored} stored",
                        total_fetched,
                        stored,
                        duration_ms,
                    )
                    ebay_db.update_sync_job(job_id, "cancelled", total_fetched, stored)
                    return {
                        "status": "cancelled",
                        "total_fetched": total_fetched,
                        "total_stored": stored,
                        "job_id": job_id,
                        "run_id": event_logger.run_id,
                    }

                # Store all Post-Order cases (no filtering by issue type)
                try:
                    ok = ebay_db.upsert_case(  # type: ignore[attr-defined]
                        user_id,
                        c,
                        ebay_account_id=ebay_account_id,
                        ebay_user_id=ebay_user_id,
                    )
                except Exception as exc:  # pragma: no cover - defensive
                    normalization_errors += 1
                    logger.warning(
                        "Cases sync: failed to upsert case payload (case data error): %s",
                        exc,
                        exc_info=True,
                    )
                    ok = False

                if ok:
                    stored += 1
                    # Heuristic: treat rows with both itemId and transactionId
                    # present as "fully" normalized; otherwise partial.
                    item_id = c.get("itemId") or c.get("item_id")
                    txn_id = c.get("transactionId") or c.get("transaction_id")
                    if item_id and txn_id:
                        normalized_full += 1
                    else:
                        normalized_partial += 1
                else:
                    normalization_errors += 1

            total_stored = stored
            duration_ms = int((time.time() - start_time) * 1000)
            ebay_db.update_sync_job(job_id, "completed", total_fetched, total_stored)

            event_logger.log_done(
                f"Cases sync completed: {total_fetched} fetched, {total_stored} stored in {duration_ms}ms"
                f" (normalized_full={normalized_full}, normalized_partial={normalized_partial}, "
                f"normalization_errors={normalization_errors})",
                total_fetched,
                total_stored,
                duration_ms,
            )
            logger.info(
                "Cases sync completed: fetched=%s, stored=%s, normalized_full=%s, "
                "normalized_partial=%s, normalization_errors=%s",
                total_fetched,
                total_stored,
                normalized_full,
                normalized_partial,
                normalization_errors,
            )

            return {
                "status": "completed",
                "total_fetched": total_fetched,
                "total_stored": total_stored,
                "normalized_full": normalized_full,
                "normalized_partial": normalized_partial,
                "normalization_errors": normalization_errors,
                "job_id": job_id,
                "run_id": event_logger.run_id,
            }

        except Exception as exc:
            # Preserve detailed HTTPException messages (including eBay status,
            # body, and correlation id) so they flow into worker last_error.
            if isinstance(exc, HTTPException):
                error_msg = f"{exc.status_code}: {exc.detail}"
            else:
                error_msg = str(exc)

            event_logger.log_error(f"Cases sync failed: {error_msg}", exc)
            logger.error(f"Cases sync failed: {error_msg}")
            ebay_db.update_sync_job(job_id, "failed", error_message=error_msg)
            raise
        finally:
            event_logger.close()

    async def sync_postorder_returns(
        self,
        user_id: str,
        access_token: str,
        run_id: Optional[str] = None,
        ebay_account_id: Optional[str] = None,
        ebay_user_id: Optional[str] = None,
        window_from: Optional[str] = None,
        window_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Sync Post-Order returns into ebay_returns.

        The Post-Order Returns search endpoint has limited date filtering
        capabilities, so we currently treat the worker window as diagnostic
        metadata while relying on upserts + overlap for safety, mirroring the
        strategy used for inquiries and cases.
        """
        from app.services.ebay_database import ebay_db
        from app.services.sync_event_logger import SyncEventLogger, is_cancelled
        import time

        event_logger = SyncEventLogger(user_id, "returns", run_id=run_id)
        job_id = ebay_db.create_sync_job(user_id, "returns")
        start_time = time.time()

        try:
            total_fetched = 0
            total_stored = 0
            api_calls = 0

            event_logger.log_start(
                f"Starting Post-Order returns sync from eBay ({settings.EBAY_ENVIRONMENT})",
            )
            if window_from or window_to:
                event_logger.log_info(
                    f"Worker window from={window_from!r} to={window_to!r} (diagnostic only)",
                )

            logger.info(f"Starting Post-Order returns sync for user {user_id}")

            await asyncio.sleep(0.3)

            if is_cancelled(event_logger.run_id):
                logger.info(
                    f"Returns sync cancelled for run_id {event_logger.run_id} (before API request)",
                )
                event_logger.log_warning("Sync operation cancelled by user")
                duration_ms = int((time.time() - start_time) * 1000)
                event_logger.log_done(
                    "Returns sync cancelled: 0 fetched, 0 stored",
                    0,
                    0,
                    duration_ms,
                )
                ebay_db.update_sync_job(job_id, "cancelled", 0, 0)
                return {
                    "status": "cancelled",
                    "total_fetched": 0,
                    "total_stored": 0,
                    "api_calls": 0,
                    "job_id": job_id,
                    "run_id": event_logger.run_id,
                }

            # Initial search call; for now we do not project the window onto
            # query params until Post-Order filtering is validated in prod.
            event_logger.log_info("→ Requesting: GET /post-order/v2/return/search")
            request_start = time.time()
            try:
                search_response = await self.fetch_postorder_returns(access_token)
                api_calls += 1
            except Exception:
                if is_cancelled(event_logger.run_id):
                    logger.info(
                        f"Returns sync cancelled for run_id {event_logger.run_id} (after API error)",
                    )
                    event_logger.log_warning("Sync operation cancelled by user")
                    duration_ms = int((time.time() - start_time) * 1000)
                    event_logger.log_done(
                        "Returns sync cancelled: 0 fetched, 0 stored",
                        0,
                        0,
                        duration_ms,
                    )
                    ebay_db.update_sync_job(job_id, "cancelled", 0, 0)
                    return {
                        "status": "cancelled",
                        "total_fetched": 0,
                        "total_stored": 0,
                        "api_calls": api_calls,
                        "job_id": job_id,
                        "run_id": event_logger.run_id,
                    }
                raise

            request_duration = int((time.time() - request_start) * 1000)

            returns = (
                search_response.get("members")
                or search_response.get("returns")
                or search_response.get("returnSummaries")
                or []
            )
            total_fetched = len(returns)

            event_logger.log_http_request(
                "GET",
                "/post-order/v2/return/search",
                200,
                request_duration,
                total_fetched,
            )
            event_logger.log_info(
                f"← Response: 200 OK ({request_duration}ms) - Received {total_fetched} returns",
            )

            await asyncio.sleep(0.2)

            stored = 0
            for summary in returns:
                if is_cancelled(event_logger.run_id):
                    logger.info(
                        f"Returns sync cancelled for run_id {event_logger.run_id} (during storage)",
                    )
                    event_logger.log_warning("Sync operation cancelled by user")
                    duration_ms = int((time.time() - start_time) * 1000)
                    event_logger.log_done(
                        f"Returns sync cancelled: {total_fetched} fetched, {stored} stored",
                        total_fetched,
                        stored,
                        duration_ms,
                    )
                    ebay_db.update_sync_job(job_id, "cancelled", total_fetched, stored)
                    return {
                        "status": "cancelled",
                        "total_fetched": total_fetched,
                        "total_stored": stored,
                        "api_calls": api_calls,
                        "job_id": job_id,
                        "run_id": event_logger.run_id,
                    }

                # Each element from the search response is treated as the
                # high-level summary. We resolve the return id from it and then
                # attempt to fetch the full detail payload to build a merged
                # {"summary": ..., "detail": ...} object for normalized
                # storage in ebay_returns.
                return_id = summary.get("returnId") or summary.get("return_id")
                detail: Dict[str, Any] = {}
                if return_id:
                    try:
                        detail = await self.fetch_postorder_return_detail(access_token, return_id)
                        api_calls += 1
                    except HTTPException as http_exc:  # pragma: no cover - defensive
                        try:
                            detail_msg = http_exc.detail  # type: ignore[assignment]
                        except Exception:
                            detail_msg = str(http_exc)
                        event_logger.log_warning(
                            f"Failed to fetch return detail for {return_id}: {detail_msg}",
                        )
                        # Fall back to storing summary-only data.
                        detail = {}
                    except Exception as exc:  # pragma: no cover - defensive
                        event_logger.log_warning(
                            f"Unexpected error fetching return detail for {return_id}: {exc}",
                        )
                        detail = {}

                merged_payload: Dict[str, Any] = {
                    "summary": summary,
                    "detail": detail,
                }

                try:
                    ok = ebay_db.upsert_return(  # type: ignore[attr-defined]
                        user_id,
                        merged_payload,
                        ebay_account_id=ebay_account_id,
                        ebay_user_id=ebay_user_id,
                        return_id=return_id,
                    )
                except Exception as exc:  # pragma: no cover - defensive
                    logger.warning(
                        "Returns sync: failed to upsert return payload: %s",
                        exc,
                        exc_info=True,
                    )
                    event_logger.log_warning(
                        f"Upsert error for return_id={return_id!r}: {exc}",
                    )
                    ok = False

                if not ok:
                    # Either upsert_return() returned False (e.g. missing returnId
                    # or DB-level error) or we hit an exception above. Emit a
                    # structured warning into the worker log so the UI clearly
                    # shows which payloads were skipped while the underlying
                    # reason remains in the backend logs.
                    event_logger.log_warning(
                        f"Skipped storing Post-Order return (upsert_return returned False) "
                        f"for return_id={return_id!r}. See backend logs for "
                        f"'Return data missing returnId' or 'Error upserting return'.",
                    )

                if ok:
                    stored += 1

            total_stored = stored
            duration_ms = int((time.time() - start_time) * 1000)
            ebay_db.update_sync_job(job_id, "completed", total_fetched, total_stored)

            event_logger.log_done(
                f"Returns sync completed: {total_fetched} fetched, {total_stored} stored in {duration_ms}ms (api_calls={api_calls})",
                total_fetched,
                total_stored,
                duration_ms,
            )

            logger.info(
                "Returns sync completed: fetched=%s, stored=%s, api_calls=%s",
                total_fetched,
                total_stored,
                api_calls,
            )

            return {
                "status": "completed",
                "total_fetched": total_fetched,
                "total_stored": total_stored,
                "api_calls": api_calls,
                "job_id": job_id,
                "run_id": event_logger.run_id,
            }

        except Exception as exc:
            error_msg = str(exc)
            event_logger.log_error(f"Returns sync failed: {error_msg}", exc)
            logger.error(f"Returns sync failed: {error_msg}")
            ebay_db.update_sync_job(job_id, "failed", error_message=error_msg)
            raise
        finally:
            event_logger.close()

    async def sync_all_offers(
        self,
        user_id: str,
        access_token: str,
        run_id: Optional[str] = None,
        ebay_account_id: Optional[str] = None,
        ebay_user_id: Optional[str] = None,
        window_from: Optional[str] = None,
        window_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Synchronize offers from eBay to database.

        Inventory/Offers APIs do not expose a direct date filter, so `window_from`
        and `window_to` are used primarily for logging and for filtering which
        offers we store based on their `creationDate`. Older offers outside the
        window are skipped at write-time, and upserts keep the operation
        idempotent.
        
        According to eBay API documentation:
        - getOffers endpoint requires 'sku' parameter (Required)
        - To get all offers, we must:
          1. First get all inventory items via getInventoryItems (paginated)
          2. For each SKU, call getOffers to get offers for that SKU
        
        API Flow:
        1. GET /sell/inventory/v1/inventory_item?limit=200&offset=0 (get all SKUs)
        2. For each SKU: GET /sell/inventory/v1/offer?sku={sku}&limit=200&offset=0
        3. Store all offers in database
        
        Args:
            user_id: User ID
            access_token: eBay OAuth access token
            run_id: Optional run_id for sync event logging
            
        Returns:
            Dict with status, total_fetched, total_stored, job_id, run_id
        """
        from app.services.ebay_database import ebay_db
        from app.services.sync_event_logger import SyncEventLogger
        import time
        
        # Use provided run_id if available, otherwise create new one
        event_logger = SyncEventLogger(user_id, 'offers', run_id=run_id)
        job_id = ebay_db.create_sync_job(user_id, 'offers')
        start_time = time.time()
        
        try:
            total_fetched = 0
            total_stored = 0
            all_skus = []
            
            event_logger.log_start(f"Starting Offers sync from eBay ({settings.EBAY_ENVIRONMENT})")
            event_logger.log_info(f"API Configuration: Inventory API v1 - getInventoryItems → getOffers per SKU")
            event_logger.log_info(f"Step 1: Fetching all inventory items to get SKU list...")
            logger.info(f"Starting offers sync for user {user_id}")
            
            await asyncio.sleep(0.5)
            
            # Check for cancellation before starting
            from app.services.sync_event_logger import is_cancelled
            if is_cancelled(event_logger.run_id):
                logger.info(f"Offers sync cancelled for run_id {event_logger.run_id}")
                event_logger.log_warning("Sync operation cancelled by user")
                event_logger.log_done(
                    f"Offers sync cancelled: 0 fetched, 0 stored",
                    0,
                    0,
                    int((time.time() - start_time) * 1000)
                )
                event_logger.close()
                return {
                    "status": "cancelled",
                    "total_fetched": 0,
                    "total_stored": 0,
                    "job_id": job_id,
                    "run_id": event_logger.run_id
                }
            
            # Step 1: Get all inventory items (SKUs) with pagination
            limit = 200
            offset = 0
            has_more_items = True
            inventory_page = 0
            
            while has_more_items:
                inventory_page += 1
                
                # Check for cancellation
                if is_cancelled(event_logger.run_id):
                    logger.info(f"Offers sync cancelled for run_id {event_logger.run_id}")
                    event_logger.log_warning("Sync operation cancelled by user")
                    event_logger.log_done(
                        f"Offers sync cancelled: {total_fetched} fetched, {total_stored} stored",
                        total_fetched,
                        total_stored,
                        int((time.time() - start_time) * 1000)
                    )
                    event_logger.close()
                    return {
                        "status": "cancelled",
                        "total_fetched": total_fetched,
                        "total_stored": total_stored,
                        "job_id": job_id,
                        "run_id": event_logger.run_id
                    }
                
                # Check for cancellation BEFORE making the API request
                if is_cancelled(event_logger.run_id):
                    logger.info(f"Offers sync cancelled for run_id {event_logger.run_id} (before inventory API request)")
                    event_logger.log_warning("Sync operation cancelled by user")
                    event_logger.log_done(
                        f"Offers sync cancelled: {total_fetched} fetched, {total_stored} stored",
                        total_fetched,
                        total_stored,
                        int((time.time() - start_time) * 1000)
                    )
                    event_logger.close()
                    return {
                        "status": "cancelled",
                        "total_fetched": total_fetched,
                        "total_stored": total_stored,
                        "job_id": job_id,
                        "run_id": event_logger.run_id
                    }
                
                event_logger.log_info(f"→ Fetching inventory items page {inventory_page}: GET /sell/inventory/v1/inventory_item?limit={limit}&offset={offset}")
                
                request_start = time.time()
                try:
                    inventory_response = await self.fetch_inventory_items(access_token, limit=limit, offset=offset)
                except Exception as e:
                    # Check for cancellation after error
                    if is_cancelled(event_logger.run_id):
                        logger.info(f"Offers sync cancelled for run_id {event_logger.run_id} (after inventory API error)")
                        event_logger.log_warning("Sync operation cancelled by user")
                        event_logger.log_done(
                            f"Offers sync cancelled: {total_fetched} fetched, {total_stored} stored",
                            total_fetched,
                            total_stored,
                            int((time.time() - start_time) * 1000)
                        )
                        event_logger.close()
                        return {
                            "status": "cancelled",
                            "total_fetched": total_fetched,
                            "total_stored": total_stored,
                            "job_id": job_id,
                            "run_id": event_logger.run_id
                        }
                    raise
                request_duration = int((time.time() - request_start) * 1000)
                
                # Check for cancellation AFTER the API request
                if is_cancelled(event_logger.run_id):
                    logger.info(f"Offers sync cancelled for run_id {event_logger.run_id} (after inventory API request)")
                    event_logger.log_warning("Sync operation cancelled by user")
                    event_logger.log_done(
                        f"Offers sync cancelled: {total_fetched} fetched, {total_stored} stored",
                        total_fetched,
                        total_stored,
                        int((time.time() - start_time) * 1000)
                    )
                    event_logger.close()
                    return {
                        "status": "cancelled",
                        "total_fetched": total_fetched,
                        "total_stored": total_stored,
                        "job_id": job_id,
                        "run_id": event_logger.run_id
                    }
                
                inventory_items = inventory_response.get('inventoryItems', [])
                total_items = inventory_response.get('total', 0)
                
                # Extract SKUs from inventory items
                page_skus = [item.get('sku') for item in inventory_items if item.get('sku')]
                all_skus.extend(page_skus)
                
                event_logger.log_info(f"← Response: 200 OK ({request_duration}ms) - Received {len(inventory_items)} items, {len(page_skus)} SKUs (Total: {total_items})")
                
                # Check if more pages
                offset += limit
                has_more_items = len(inventory_items) == limit and offset < total_items
                
                if has_more_items:
                    await asyncio.sleep(0.3)
            
            event_logger.log_info(f"✓ Step 1 complete: Found {len(all_skus)} unique SKUs")
            
            if not all_skus:
                event_logger.log_warning("No SKUs found in inventory - no offers to sync")
                event_logger.log_done(
                    f"Offers sync completed: 0 SKUs found, 0 offers fetched, 0 stored",
                    0,
                    0,
                    int((time.time() - start_time) * 1000)
                )
                ebay_db.update_sync_job(job_id, 'completed', 0, 0)
                return {
                    "status": "completed",
                    "total_fetched": 0,
                    "total_stored": 0,
                    "job_id": job_id,
                    "run_id": event_logger.run_id
                }
            
            # Step 2: For each SKU, get offers
            event_logger.log_info(f"Step 2: Fetching offers for {len(all_skus)} SKUs...")
            sku_count = 0
            
            for sku in all_skus:
                sku_count += 1
                
                # Check for cancellation
                if is_cancelled(event_logger.run_id):
                    logger.info(f"Offers sync cancelled for run_id {event_logger.run_id}")
                    event_logger.log_warning("Sync operation cancelled by user")
                    event_logger.log_done(
                        f"Offers sync cancelled: {total_fetched} fetched, {total_stored} stored",
                        total_fetched,
                        total_stored,
                        int((time.time() - start_time) * 1000)
                    )
                    event_logger.close()
                    return {
                        "status": "cancelled",
                        "total_fetched": total_fetched,
                        "total_stored": total_stored,
                        "job_id": job_id,
                        "run_id": event_logger.run_id
                    }
                
                # Check for cancellation BEFORE making the API request
                if is_cancelled(event_logger.run_id):
                    logger.info(f"Offers sync cancelled for run_id {event_logger.run_id} (before offers API request)")
                    event_logger.log_warning("Sync operation cancelled by user")
                    event_logger.log_done(
                        f"Offers sync cancelled: {total_fetched} fetched, {total_stored} stored",
                        total_fetched,
                        total_stored,
                        int((time.time() - start_time) * 1000)
                    )
                    event_logger.close()
                    return {
                        "status": "cancelled",
                        "total_fetched": total_fetched,
                        "total_stored": total_stored,
                        "job_id": job_id,
                        "run_id": event_logger.run_id
                    }
                
                event_logger.log_info(f"→ [{sku_count}/{len(all_skus)}] Fetching offers for SKU: {sku}")
                
                try:
                    request_start = time.time()
                    offers_response = await self.fetch_offers(access_token, sku=sku)
                    request_duration = int((time.time() - request_start) * 1000)
                    
                    # Check for cancellation AFTER the API request
                    if is_cancelled(event_logger.run_id):
                        logger.info(f"Offers sync cancelled for run_id {event_logger.run_id} (after offers API request)")
                        event_logger.log_warning("Sync operation cancelled by user")
                        event_logger.log_done(
                            f"Offers sync cancelled: {total_fetched} fetched, {total_stored} stored",
                            total_fetched,
                            total_stored,
                            int((time.time() - start_time) * 1000)
                        )
                        event_logger.close()
                        return {
                            "status": "cancelled",
                            "total_fetched": total_fetched,
                            "total_stored": total_stored,
                            "job_id": job_id,
                            "run_id": event_logger.run_id
                        }
                    
                    offers = offers_response.get('offers', [])
                    total_fetched += len(offers)
                    
                    event_logger.log_info(f"← [{sku_count}/{len(all_skus)}] SKU {sku}: {len(offers)} offers ({request_duration}ms)")
                    
                    # Store offers
                    for offer in offers:
                        if ebay_db.upsert_offer(user_id, offer):
                            total_stored += 1
                    
                    # Rate limiting - small delay between SKU requests
                    await asyncio.sleep(0.2)
                    
                except Exception as e:
                    # Check for cancellation after error
                    if is_cancelled(event_logger.run_id):
                        logger.info(f"Offers sync cancelled for run_id {event_logger.run_id} (after offers API error)")
                        event_logger.log_warning("Sync operation cancelled by user")
                        event_logger.log_done(
                            f"Offers sync cancelled: {total_fetched} fetched, {total_stored} stored",
                            total_fetched,
                            total_stored,
                            int((time.time() - start_time) * 1000)
                        )
                        event_logger.close()
                        return {
                            "status": "cancelled",
                            "total_fetched": total_fetched,
                            "total_stored": total_stored,
                            "job_id": job_id,
                            "run_id": event_logger.run_id
                        }
                    error_msg = f"Failed to fetch offers for SKU {sku}: {str(e)}"
                    event_logger.log_warning(error_msg)
                    logger.warning(error_msg)
                    # Continue with next SKU
                    continue
            
            event_logger.log_info(f"✓ Step 2 complete: Processed {sku_count} SKUs")
            
            duration_ms = int((time.time() - start_time) * 1000)
            ebay_db.update_sync_job(job_id, 'completed', total_fetched, total_stored)
            
            event_logger.log_done(
                f"Offers sync completed: {total_fetched} offers fetched, {total_stored} stored from {sku_count} SKUs in {duration_ms}ms",
                total_fetched,
                total_stored,
                duration_ms
            )
            
            logger.info(f"Offers sync completed: fetched={total_fetched}, stored={total_stored} from {sku_count} SKUs")
            
            return {
                "status": "completed",
                "total_fetched": total_fetched,
                "total_stored": total_stored,
                "job_id": job_id,
                "run_id": event_logger.run_id
            }
            
        except Exception as e:
            error_msg = str(e)
            event_logger.log_error(f"Offers sync failed: {error_msg}", e)
            logger.error(f"Offers sync failed: {error_msg}")
            ebay_db.update_sync_job(job_id, 'failed', error_message=error_msg)
            raise
        finally:
            event_logger.close()
    
    async def sync_all_inventory(self, user_id: str, access_token: str, run_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Synchronize all inventory items from eBay to database with pagination and incremental sync support.
        
        According to eBay API documentation:
        - GET /sell/inventory/v1/inventory_item?limit=200&offset=0
        - Parameters: limit (1-200, default 25), offset (default 0)
        - Returns paginated list of inventory items
        
        API Flow:
        1. GET /sell/inventory/v1/inventory_item?limit=200&offset=0 (paginated)
        2. For each inventory item, extract and store in database
        3. Support incremental sync via cursor tracking (future enhancement)
        
        Args:
            user_id: User ID
            access_token: eBay OAuth access token
            run_id: Optional run_id for sync event logging
            
        Returns:
            Dict with status, total_fetched, total_stored, job_id, run_id
        """
        from app.services.postgres_ebay_database import PostgresEbayDatabase
        from app.services.sync_event_logger import SyncEventLogger
        import time
        
        ebay_db = PostgresEbayDatabase()
        
        # Use provided run_id if available, otherwise create new one
        event_logger = SyncEventLogger(user_id, 'inventory', run_id=run_id)
        job_id = ebay_db.create_sync_job(user_id, 'inventory')
        start_time = time.time()
        
        try:
            total_fetched = 0
            total_stored = 0
            
            event_logger.log_start(f"Starting Inventory sync from eBay ({settings.EBAY_ENVIRONMENT})")
            event_logger.log_info(f"API Configuration: Inventory API v1 - getInventoryItems with pagination")
            logger.info(f"Starting inventory sync for user {user_id}")
            
            await asyncio.sleep(0.5)
            
            # Check for cancellation before starting
            from app.services.sync_event_logger import is_cancelled
            if is_cancelled(event_logger.run_id):
                logger.info(f"Inventory sync cancelled for run_id {event_logger.run_id}")
                event_logger.log_warning("Sync operation cancelled by user")
                event_logger.log_done(
                    f"Inventory sync cancelled: 0 fetched, 0 stored",
                    0,
                    0,
                    int((time.time() - start_time) * 1000)
                )
                event_logger.close()
                return {
                    "status": "cancelled",
                    "total_fetched": 0,
                    "total_stored": 0,
                    "job_id": job_id,
                    "run_id": event_logger.run_id
                }
            
            # Pagination loop
            limit = 200  # Max allowed by eBay API
            offset = 0
            has_more = True
            current_page = 0
            
            while has_more:
                current_page += 1
                
                # Check for cancellation
                if is_cancelled(event_logger.run_id):
                    logger.info(f"Inventory sync cancelled for run_id {event_logger.run_id}")
                    event_logger.log_warning("Sync operation cancelled by user")
                    event_logger.log_done(
                        f"Inventory sync cancelled: {total_fetched} fetched, {total_stored} stored",
                        total_fetched,
                        total_stored,
                        int((time.time() - start_time) * 1000)
                    )
                    event_logger.close()
                    return {
                        "status": "cancelled",
                        "total_fetched": total_fetched,
                        "total_stored": total_stored,
                        "job_id": job_id,
                        "run_id": event_logger.run_id
                    }
                
                # Check for cancellation BEFORE making the API request
                if is_cancelled(event_logger.run_id):
                    logger.info(f"Inventory sync cancelled for run_id {event_logger.run_id} (before API request)")
                    event_logger.log_warning("Sync operation cancelled by user")
                    event_logger.log_done(
                        f"Inventory sync cancelled: {total_fetched} fetched, {total_stored} stored",
                        total_fetched,
                        total_stored,
                        int((time.time() - start_time) * 1000)
                    )
                    event_logger.close()
                    return {
                        "status": "cancelled",
                        "total_fetched": total_fetched,
                        "total_stored": total_stored,
                        "job_id": job_id,
                        "run_id": event_logger.run_id
                    }
                
                event_logger.log_info(f"→ Requesting page {current_page}: GET /sell/inventory/v1/inventory_item?limit={limit}&offset={offset}")
                
                request_start = time.time()
                try:
                    inventory_response = await self.fetch_inventory_items(access_token, limit=limit, offset=offset)
                except Exception as e:
                    # Check for cancellation after error
                    if is_cancelled(event_logger.run_id):
                        logger.info(f"Inventory sync cancelled for run_id {event_logger.run_id} (after API error)")
                        event_logger.log_warning("Sync operation cancelled by user")
                        event_logger.log_done(
                            f"Inventory sync cancelled: {total_fetched} fetched, {total_stored} stored",
                            total_fetched,
                            total_stored,
                            int((time.time() - start_time) * 1000)
                        )
                        event_logger.close()
                        return {
                            "status": "cancelled",
                            "total_fetched": total_fetched,
                            "total_stored": total_stored,
                            "job_id": job_id,
                            "run_id": event_logger.run_id
                        }
                    raise
                request_duration = int((time.time() - request_start) * 1000)
                
                # Check for cancellation AFTER the API request
                if is_cancelled(event_logger.run_id):
                    logger.info(f"Inventory sync cancelled for run_id {event_logger.run_id} (after API request)")
                    event_logger.log_warning("Sync operation cancelled by user")
                    event_logger.log_done(
                        f"Inventory sync cancelled: {total_fetched} fetched, {total_stored} stored",
                        total_fetched,
                        total_stored,
                        int((time.time() - start_time) * 1000)
                    )
                    event_logger.close()
                    return {
                        "status": "cancelled",
                        "total_fetched": total_fetched,
                        "total_stored": total_stored,
                        "job_id": job_id,
                        "run_id": event_logger.run_id
                    }
                
                inventory_items = inventory_response.get('inventoryItems', [])
                total_items = inventory_response.get('total', 0)
                total_pages = (total_items + limit - 1) // limit if total_items > 0 else 1
                
                event_logger.log_http_request(
                    'GET',
                    f'/sell/inventory/v1/inventory_item?limit={limit}&offset={offset}',
                    200,
                    request_duration,
                    len(inventory_items)
                )
                
                event_logger.log_info(f"← Response: 200 OK ({request_duration}ms) - Received {len(inventory_items)} items (Total available: {total_items})")
                
                total_fetched += len(inventory_items)
                
                await asyncio.sleep(0.3)
                
                event_logger.log_info(f"→ Storing {len(inventory_items)} inventory items in database...")
                store_start = time.time()
                
                for item in inventory_items:
                    # Check for cancellation during storage
                    if is_cancelled(event_logger.run_id):
                        logger.info(f"Inventory sync cancelled for run_id {event_logger.run_id}")
                        event_logger.log_warning("Sync operation cancelled by user")
                        event_logger.log_done(
                            f"Inventory sync cancelled: {total_fetched} fetched, {total_stored} stored",
                            total_fetched,
                            total_stored,
                            int((time.time() - start_time) * 1000)
                        )
                        event_logger.close()
                        return {
                            "status": "cancelled",
                            "total_fetched": total_fetched,
                            "total_stored": total_stored,
                            "job_id": job_id,
                            "run_id": event_logger.run_id
                        }
                    
                    if ebay_db.upsert_inventory_item(user_id, item):
                        total_stored += 1
                
                store_duration = int((time.time() - store_start) * 1000)
                
                event_logger.log_info(f"← Database: Stored {total_stored - (total_fetched - len(inventory_items))} items ({store_duration}ms)")
                
                event_logger.log_progress(
                    f"Page {current_page}/{total_pages} complete: {len(inventory_items)} fetched, {total_stored - (total_fetched - len(inventory_items))} stored | Running total: {total_fetched}/{total_items} fetched, {total_stored} stored",
                    current_page,
                    total_pages,
                    total_fetched,
                    total_stored
                )
                
                logger.info(f"Synced batch: {len(inventory_items)} items (total: {total_fetched}/{total_items}, stored: {total_stored})")
                
                # Check if more pages
                offset += limit
                has_more = len(inventory_items) == limit and offset < total_items
                
                if has_more:
                    await asyncio.sleep(0.8)
            
            duration_ms = int((time.time() - start_time) * 1000)
            ebay_db.update_sync_job(job_id, 'completed', total_fetched, total_stored)
            
            event_logger.log_done(
                f"Inventory sync completed: {total_fetched} fetched, {total_stored} stored in {duration_ms}ms",
                total_fetched,
                total_stored,
                duration_ms
            )
            
            logger.info(f"Inventory sync completed: fetched={total_fetched}, stored={total_stored}")
            
            return {
                "status": "completed",
                "total_fetched": total_fetched,
                "total_stored": total_stored,
                "job_id": job_id,
                "run_id": event_logger.run_id
            }
            
        except Exception as e:
            error_msg = str(e)
            event_logger.log_error(f"Inventory sync failed: {error_msg}", e)
            logger.error(f"Inventory sync failed: {error_msg}")
            ebay_db.update_sync_job(job_id, 'failed', error_message=error_msg)
            raise
        finally:
            event_logger.close()

    async def get_purchases(
        self,
        access_token: str,
        since: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch BUYING-side purchases for the authenticated account.

        This is a thin wrapper around the Trading API ``GetMyeBayBuying`` call.
        It intentionally returns a *normalized* list of dicts that map closely to
        the ``ebay_buyer`` columns so that workers can upsert into Postgres
        without needing to know the raw XML structure.

        NOTE: The Trading schema is quite large; this helper focuses on the
        fields we need for the BUYING grid and leaves the rest in comments/raw
        payloads for future enrichment.
        """
        import xml.etree.ElementTree as ET  # local import to avoid global cost

        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="eBay access token required",
            )

        # For now we rely on eBay's default time window for GetMyeBayBuying.
        # The ``since`` parameter is reserved so we can switch to an explicit
        # date-based filter later without changing the worker signature.
        target_env = settings.EBAY_ENVIRONMENT or "sandbox"
        api_url = (
            "https://api.sandbox.ebay.com/ws/api.dll"
            if target_env == "sandbox"
            else "https://api.ebay.com/ws/api.dll"
        )

        entries_per_page = 200
        page_number = 1

        purchases: List[Dict[str, Any]] = []
        has_more = True

        while has_more:
            xml_request = f"""<?xml version="1.0" encoding="utf-8"?>
<GetMyeBayBuyingRequest xmlns="urn:ebay:apis:eBLBaseComponents">
  <RequesterCredentials>
    <eBayAuthToken>{access_token}</eBayAuthToken>
  </RequesterCredentials>
  <DetailLevel>ReturnAll</DetailLevel>
  <Pagination>
    <EntriesPerPage>{entries_per_page}</EntriesPerPage>
    <PageNumber>{page_number}</PageNumber>
  </Pagination>
  <WarningLevel>High</WarningLevel>
</GetMyeBayBuyingRequest>"""

            headers = {
                "X-EBAY-API-COMPATIBILITY-LEVEL": "967",
                "X-EBAY-API-CALL-NAME": "GetMyeBayBuying",
                "X-EBAY-API-SITEID": "0",
                "Content-Type": "text/xml",
            }

            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(api_url, content=xml_request, headers=headers)
            except httpx.RequestError as e:
                msg = f"HTTP error calling GetMyeBayBuying: {e}"
                logger.error(msg)
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=msg,
                )

            if response.status_code != 200:
                msg = f"GetMyeBayBuying failed: HTTP {response.status_code} - {response.text[:1000]}"
                logger.error(msg)
                raise HTTPException(status_code=response.status_code, detail=msg)

            raw_xml = response.text or ""
            try:
                root = ET.fromstring(raw_xml)
            except ET.ParseError as e:
                logger.error(f"Failed to parse GetMyeBayBuying XML: {e}")
                break

            ns = {"ebay": "urn:ebay:apis:eBLBaseComponents"}

            # The Trading response groups purchases under a number of lists; for
            # now we look under any ItemArray elements we can find.
            item_elems: List[ET.Element] = []
            for path in [
                ".//ebay:BidList/ebay:ItemArray/ebay:Item",
                ".//ebay:WonList/ebay:ItemArray/ebay:Item",
                ".//ebay:PurchaseHistory/ebay:ItemArray/ebay:Item",
            ]:
                parent = root.findall(path, ns)
                if parent:
                    item_elems.extend(parent)

            # Fallback: any Item under any ItemArray
            if not item_elems:
                generic_parent = root.findall(".//ebay:ItemArray/ebay:Item", ns)
                item_elems.extend(generic_parent)

            fetched_this_page = 0

            for item in item_elems:
                def _text(elem: Optional[ET.Element]) -> Optional[str]:
                    return elem.text if elem is not None and elem.text is not None else None

                item_id = _text(item.find("ebay:ItemID", ns))
                title = _text(item.find("ebay:Title", ns))

                seller_elem = item.find("ebay:Seller", ns)
                seller_id = _text(seller_elem.find("ebay:UserID", ns)) if seller_elem is not None else None
                seller_email = _text(seller_elem.find("ebay:Email", ns)) if seller_elem is not None else None

                quantity_purchased = None
                qty_elem = item.find("ebay:QuantityPurchased", ns)
                if qty_elem is None:
                    qty_elem = item.find("ebay:Quantity", ns)
                if qty_elem is not None and qty_elem.text is not None:
                    try:
                        quantity_purchased = int(qty_elem.text)
                    except ValueError:
                        quantity_purchased = None

                # Prices
                current_price = None
                total_transaction_price = None
                price_elem = item.find("ebay:ConvertedCurrentPrice", ns) or item.find("ebay:CurrentPrice", ns)
                if price_elem is not None and price_elem.text is not None:
                    try:
                        current_price = float(price_elem.text)
                    except ValueError:
                        current_price = None

                total_elem = item.find("ebay:TotalTransactionPrice", ns)
                if total_elem is not None and total_elem.text is not None:
                    try:
                        total_transaction_price = float(total_elem.text)
                    except ValueError:
                        total_transaction_price = None

                # Shipping / tracking
                shipping_carrier = None
                tracking_number = None
                shipment = item.find("ebay:Shipment", ns)
                if shipment is not None:
                    shipping_carrier = _text(shipment.find("ebay:ShippingCarrierUsed", ns))
                    tracking_number = _text(shipment.find("ebay:ShipmentTrackingNumber", ns))

                paid_time = None
                paid_elem = item.find("ebay:PaidTime", ns)
                if paid_elem is not None and paid_elem.text:
                    try:
                        paid_time = datetime.fromisoformat(paid_elem.text.replace("Z", "+00:00"))
                    except Exception:
                        paid_time = None

                # Compose minimal DTO compatible with EbayBuyer
                purchases.append(
                    {
                        "item_id": item_id,
                        "title": title,
                        "transaction_id": None,
                        "order_line_item_id": None,
                        "shipping_carrier": shipping_carrier,
                        "tracking_number": tracking_number,
                        "seller_id": seller_id,
                        "seller_email": seller_email,
                        "quantity_purchased": quantity_purchased,
                        "current_price": current_price,
                        "total_transaction_price": total_transaction_price,
                        "paid_time": paid_time,
                    }
                )
                fetched_this_page += 1

            # Basic pagination handling: look for TotalNumberOfPages when present.
            total_pages = 1
            total_pages_elem = root.find(
                ".//ebay:PaginationResult/ebay:TotalNumberOfPages",
                ns,
            )
            if total_pages_elem is not None and total_pages_elem.text:
                try:
                    total_pages = int(total_pages_elem.text)
                except ValueError:
                    total_pages = 1

            has_more = page_number < total_pages and fetched_this_page > 0
            page_number += 1

            if not has_more:
                break

        return purchases

    async def sync_active_inventory_report(
        self,
        user_id: str,
        access_token: str,
        *,
        run_id: Optional[str] = None,
        ebay_account_id: Optional[str] = None,
        ebay_user_id: Optional[str] = None,
        window_from: Optional[str] = None,
        window_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build Active Inventory snapshot using Trading GetMyeBaySelling.

        Sell Feed does not expose a usable feedType for active inventory for
        this app, and Inventory API only returns items created via that API
        (plus shared demo SKUs like the GoPro helmet). To get a real snapshot
        of all *active* listings for the seller account (including those
        created via Trading/UI), we use the Trading API GetMyeBaySelling
        ActiveList and persist the results into ebay_active_inventory.
        """
        import time
        import xml.etree.ElementTree as ET
        from datetime import datetime, timezone
        from decimal import Decimal, InvalidOperation

        from app.services.postgres_ebay_database import PostgresEbayDatabase
        from app.services.sync_event_logger import SyncEventLogger
        from app.models_sqlalchemy import get_db
        from app.models_sqlalchemy.models import ActiveInventory

        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="eBay access token required",
            )

        if not ebay_account_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="ebay_account_id is required for active inventory sync",
            )

        ebay_db = PostgresEbayDatabase()
        event_logger = SyncEventLogger(user_id, "active_inventory", run_id=run_id)
        job_id = ebay_db.create_sync_job(user_id, "active_inventory")
        start_time = time.time()

        api_url = "https://api.ebay.com/ws/api.dll"

        try:
            total_fetched = 0
            total_stored = 0

            from app.config import settings
            import asyncio

            # Parse window timestamps for incremental sync
            window_from_dt: Optional[datetime] = None
            window_to_dt: Optional[datetime] = None
            if window_from:
                try:
                    if window_from.endswith("Z"):
                        window_from = window_from.replace("Z", "+00:00")
                    window_from_dt = datetime.fromisoformat(window_from)
                except Exception:
                    logger.warning(f"Invalid window_from format: {window_from}")
            if window_to:
                try:
                    if window_to.endswith("Z"):
                        window_to = window_to.replace("Z", "+00:00")
                    window_to_dt = datetime.fromisoformat(window_to)
                except Exception:
                    logger.warning(f"Invalid window_to format: {window_to}")

            event_logger.log_start(
                f"Starting Active Inventory sync via Trading GetMyeBaySelling ({settings.EBAY_ENVIRONMENT})",
            )
            sync_mode = "incremental" if window_from_dt else "full"
            event_logger.log_info(
                f"Sync mode: {sync_mode}, window_from={window_from_dt.isoformat() if window_from_dt else 'None'}, "
                f"window_to={window_to_dt.isoformat() if window_to_dt else 'None'}"
            )
            event_logger.log_info(
                "API Configuration: Trading GetMyeBaySelling ActiveList, paginate and upsert into ebay_active_inventory",
            )

            entries_per_page = 200
            page_number = 1
            max_pages = 200
            has_more = True
            total_items_skipped = 0  # Track total skipped items across all pages

            db_session = next(get_db())
            try:
                # Pre-fetch existing items with their last_seen_at timestamps for incremental filtering
                existing_items: Dict[tuple, datetime] = {}
                if window_from_dt and ebay_account_id:
                    existing_records = db_session.query(
                        ActiveInventory.sku,
                        ActiveInventory.item_id,
                        ActiveInventory.last_seen_at
                    ).filter(
                        ActiveInventory.ebay_account_id == ebay_account_id
                    ).all()
                    for record in existing_records:
                        key = (record.sku or "", record.item_id or "")
                        if record.last_seen_at:
                            existing_items[key] = record.last_seen_at
                    
                    event_logger.log_info(
                        f"Loaded {len(existing_items)} existing items from database for incremental filtering"
                    )
                while has_more and page_number <= max_pages:
                    event_logger.log_info(
                        f"→ Requesting ActiveList page {page_number}: GetMyeBaySelling",
                    )

                    xml_request = f"""<?xml version="1.0" encoding="utf-8"?>
<GetMyeBaySellingRequest xmlns="urn:ebay:apis:eBLBaseComponents">
  <RequesterCredentials>
    <eBayAuthToken>{access_token}</eBayAuthToken>
  </RequesterCredentials>
  <ActiveList>
    <Include>true</Include>
    <Pagination>
      <EntriesPerPage>{entries_per_page}</EntriesPerPage>
      <PageNumber>{page_number}</PageNumber>
    </Pagination>
  </ActiveList>
  <WarningLevel>High</WarningLevel>
</GetMyeBaySellingRequest>"""

                    headers = {
                        "X-EBAY-API-SITEID": "0",
                        "X-EBAY-API-COMPATIBILITY-LEVEL": "967",
                        "X-EBAY-API-CALL-NAME": "GetMyeBaySelling",
                        "Content-Type": "text/xml",
                    }

                    request_start = time.time()
                    try:
                        async with httpx.AsyncClient(timeout=30.0) as client:
                            response = await client.post(
                                api_url,
                                content=xml_request,
                                headers=headers,
                            )
                    except httpx.RequestError as e:
                        msg = f"HTTP error calling GetMyeBaySelling: {e}"
                        event_logger.log_error(msg)
                        logger.error(msg)
                        ebay_db.update_sync_job(job_id, "failed", error_message=msg)
                        raise HTTPException(
                            status_code=status.HTTP_502_BAD_GATEWAY,
                            detail=msg,
                        )

                    request_duration = int((time.time() - request_start) * 1000)
                    event_logger.log_http_request(
                        "POST",
                        f"/ws/api.dll (GetMyeBaySelling ActiveList page {page_number})",
                        response.status_code,
                        request_duration,
                        0,
                    )

                    if response.status_code != 200:
                        msg = f"GetMyeBaySelling failed: HTTP {response.status_code} - {response.text[:1000]}"
                        event_logger.log_error(msg)
                        logger.error(msg)
                        ebay_db.update_sync_job(job_id, "failed", error_message=msg)
                        raise HTTPException(
                            status_code=response.status_code,
                            detail=msg,
                        )

                    raw_xml = response.text or ""
                    logger.info(
                        f"GetMyeBaySelling ActiveList raw XML (first 2000 chars): {raw_xml[:2000]}"
                    )

                    root = ET.fromstring(raw_xml)
                    ns = {"ebay": "urn:ebay:apis:eBLBaseComponents"}

                    items_elem = root.find(".//ebay:ActiveList/ebay:ItemArray", ns)
                    item_elems = (
                        items_elem.findall("ebay:Item", ns) if items_elem is not None else []
                    )

                    fetched_this_page = len(item_elems)
                    total_fetched += fetched_this_page

                    now_utc = datetime.now(timezone.utc)
                    items_skipped = 0  # Initialize before processing items
                    items_stored_this_page = 0  # Track items stored in this page

                    for item in item_elems:
                        def _text(path: str) -> Optional[str]:
                            elem = item.find(path, ns)
                            return elem.text if elem is not None else None

                        item_id = _text("ebay:ItemID")
                        sku = _text("ebay:SKU")
                        title = _text("ebay:Title")

                        qty_str = _text("ebay:Quantity") or "0"
                        qty_sold_str = item.findtext(
                            "ebay:SellingStatus/ebay:QuantitySold", default="0", namespaces=ns
                        )
                        try:
                            quantity_total = int(qty_str)
                        except ValueError:
                            quantity_total = 0
                        try:
                            quantity_sold = int(qty_sold_str or "0")
                        except ValueError:
                            quantity_sold = 0
                        quantity_available = max(quantity_total - quantity_sold, 0)

                        start_price_elem = item.find("ebay:StartPrice", ns)
                        price_val: Optional[Decimal] = None
                        currency: Optional[str] = None
                        if start_price_elem is not None and start_price_elem.text is not None:
                            raw_price = start_price_elem.text
                            currency = start_price_elem.attrib.get("currencyID")
                            try:
                                price_val = Decimal(str(raw_price))
                            except InvalidOperation:
                                price_val = None

                        listing_status = item.findtext(
                            "ebay:SellingStatus/ebay:ListingStatus",
                            default=None,
                            namespaces=ns,
                        )

                        condition_id = item.findtext(
                            "ebay:ConditionID", default=None, namespaces=ns
                        )
                        condition_text = item.findtext(
                            "ebay:ConditionDisplayName", default=None, namespaces=ns
                        )

                        if not item_id and not sku:
                            continue

                        # Incremental sync filtering: skip items that were recently updated
                        if window_from_dt:
                            item_key = (sku or "", item_id or "")
                            existing_last_seen = existing_items.get(item_key)
                            
                            # Skip if item exists and was seen after window_from (already up-to-date)
                            if existing_last_seen and existing_last_seen >= window_from_dt:
                                items_skipped += 1
                                continue

                        # Define raw_payload for the insert statement
                        raw_payload = {
                            "ItemID": item_id,
                            "SKU": sku,
                            "Title": title,
                            "Quantity": quantity_total,
                            "QuantitySold": quantity_sold,
                            "StartPrice": float(price_val) if price_val is not None else None,
                            "Currency": currency,
                            "ListingStatus": listing_status,
                            "ConditionID": condition_id,
                            "ConditionDisplayName": condition_text
                        }

                        # Atomic upsert using PostgreSQL ON CONFLICT to prevent race conditions
                        from sqlalchemy.dialects.postgresql import insert as pg_insert

                        stmt = pg_insert(ActiveInventory).values(
                            ebay_account_id=ebay_account_id,
                            ebay_user_id=ebay_user_id,
                            sku=sku,
                            item_id=item_id,
                            title=title,
                            quantity_available=quantity_available,
                            price=price_val,
                            currency=currency,
                            listing_status=listing_status,
                            condition_id=condition_id,
                            condition_text=condition_text,
                            raw_payload=raw_payload,
                            last_seen_at=now_utc,
                        )
                        
                        stmt = stmt.on_conflict_do_update(
                            index_elements=['ebay_account_id', 'sku', 'item_id'],
                            set_={
                                'ebay_user_id': stmt.excluded.ebay_user_id,
                                'title': stmt.excluded.title,
                                'quantity_available': stmt.excluded.quantity_available,
                                'price': stmt.excluded.price,
                                'currency': stmt.excluded.currency,
                                'listing_status': stmt.excluded.listing_status,
                                'condition_id': stmt.excluded.condition_id,
                                'condition_text': stmt.excluded.condition_text,
                                'raw_payload': stmt.excluded.raw_payload,
                                'last_seen_at': stmt.excluded.last_seen_at,
                            }
                        )
                        db_session.execute(stmt)
                        total_stored += 1
                        items_stored_this_page += 1

                    # Log page results after processing
                    event_logger.log_info(
                        f"← Page {page_number}: received {fetched_this_page} active items, "
                        f"stored {items_stored_this_page}, "
                        f"skipped {items_skipped} (already up-to-date)"
                    )

                    db_session.commit()

                    total_pages_elem = root.find(
                        ".//ebay:ActiveList/ebay:PaginationResult/ebay:TotalNumberOfPages",
                        ns,
                    )
                    total_pages = 1
                    if total_pages_elem is not None and total_pages_elem.text:
                        try:
                            total_pages = int(total_pages_elem.text)
                        except ValueError:
                            total_pages = 1

                    has_more = page_number < total_pages and fetched_this_page > 0
                    total_items_skipped += items_skipped  # Accumulate skipped items before reset
                    items_skipped = 0  # Reset counter for next page
                    page_number += 1

                    if has_more:
                        await asyncio.sleep(0.5)

            except Exception:
                db_session.rollback()
                raise
            finally:
                db_session.close()

            duration_ms = int((time.time() - start_time) * 1000)
            ebay_db.update_sync_job(
                job_id,
                "completed",
                records_fetched=total_fetched,
                records_stored=total_stored,
            )

            skip_summary = f", {total_items_skipped} skipped (already up-to-date)" if total_items_skipped > 0 else ""
            event_logger.log_done(
                f"Active inventory sync completed: {total_fetched} items fetched, {total_stored} stored{skip_summary} in {duration_ms}ms",
                total_fetched,
                total_stored,
                duration_ms,
            )

            logger.info(
                f"Active inventory sync completed for user={user_id} ebay_account_id={ebay_account_id}: fetched={total_fetched}, stored={total_stored}"
            )

            return {
                "status": "completed",
                "total_fetched": total_fetched,
                "total_stored": total_stored,
                "job_id": job_id,
                "run_id": event_logger.run_id,
            }

        except Exception as e:
            error_msg = str(e)
            event_logger.log_error(f"Active inventory sync failed: {error_msg}", e)
            logger.error(f"Active inventory sync failed: {error_msg}")
            ebay_db.update_sync_job(job_id, "failed", error_message=error_msg)
            raise
        finally:
            event_logger.close()


    async def get_ebay_user_id(
        self,
        access_token: str,
        *,
        user_id: Optional[str] = None,
        environment: Optional[str] = None
    ) -> str:
        """Get eBay user ID from access token using GetUser Trading API call"""
        import xml.etree.ElementTree as ET
        
        target_env = environment or settings.EBAY_ENVIRONMENT
        api_url = "https://api.ebay.com/ws/api.dll" if target_env == "production" else "https://api.sandbox.ebay.com/ws/api.dll"
        
        xml_request = f"""<?xml version="1.0" encoding="utf-8"?>
<GetUserRequest xmlns="urn:ebay:apis:eBLBaseComponents">
    <RequesterCredentials>
        <eBayAuthToken>{access_token}</eBayAuthToken>
    </RequesterCredentials>
    <WarningLevel>High</WarningLevel>
</GetUserRequest>"""
        
        headers = {
            "X-EBAY-API-COMPATIBILITY-LEVEL": "967",
            "X-EBAY-API-CALL-NAME": "GetUser",
            "X-EBAY-API-SITEID": "0",
            "Content-Type": "text/xml"
        }
        
        request_payload = {
            "method": "POST",
            "url": api_url,
            "headers": {k: headers[k] for k in headers},
            "body": "<GetUserRequest ...>"  # simplified for logging purposes
        }
        request_payload["headers"]["Authorization"] = "Bearer **** (token masked)"
        request_payload["headers"]["Content-Type"] = "text/xml"
        request_payload["body"] = xml_request.replace(access_token, "<hidden-token>")
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(api_url, content=xml_request, headers=headers)
            
            root = ET.fromstring(response.text)
            user_id_elem = root.find(".//{urn:ebay:apis:eBLBaseComponents}UserID")
            
            if user_id_elem is not None and user_id_elem.text:
                ebay_connect_logger.log_event(
                    user_id=user_id,
                    environment=target_env,
                    action="get_user_id",
                    request=request_payload,
                    response={
                        "status": response.status_code,
                        "headers": dict(response.headers),
                        "body": user_id_elem.text
                    }
                )
                return user_id_elem.text
            
            ebay_connect_logger.log_event(
                user_id=user_id,
                environment=target_env,
                action="get_user_id",
                request=request_payload,
                response={
                    "status": response.status_code,
                    "headers": dict(response.headers),
                    "body": response.text[:2000]
                },
                error="UserID not found"
            )
            return "unknown"
        except Exception as e:
            logger.error(f"Failed to get eBay user ID: {str(e)}")
            ebay_connect_logger.log_event(
                user_id=user_id,
                environment=target_env,
                action="get_user_id_error",
                request=request_payload,
                error=str(e)
            )
            return "unknown"
    
    async def get_ebay_username(
        self,
        access_token: str,
        *,
        user_id: Optional[str] = None,
        environment: Optional[str] = None
    ) -> Optional[str]:
        """Get eBay username from access token using GetUser Trading API call"""
        import xml.etree.ElementTree as ET
        
        target_env = environment or settings.EBAY_ENVIRONMENT
        api_url = "https://api.ebay.com/ws/api.dll" if target_env == "production" else "https://api.sandbox.ebay.com/ws/api.dll"
        
        xml_request = f"""<?xml version="1.0" encoding="utf-8"?>
<GetUserRequest xmlns="urn:ebay:apis:eBLBaseComponents">
    <RequesterCredentials>
        <eBayAuthToken>{access_token}</eBayAuthToken>
    </RequesterCredentials>
    <WarningLevel>High</WarningLevel>
</GetUserRequest>"""
        
        headers = {
            "X-EBAY-API-COMPATIBILITY-LEVEL": "967",
            "X-EBAY-API-CALL-NAME": "GetUser",
            "X-EBAY-API-SITEID": "0",
            "Content-Type": "text/xml"
        }
        request_payload = {
            "method": "POST",
            "url": api_url,
            "headers": {k: headers[k] for k in headers},
            "body": xml_request.replace(access_token, "<hidden-token>")
        }
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(api_url, content=xml_request, headers=headers)
            
            root = ET.fromstring(response.text)
            user_id_elem = root.find(".//{urn:ebay:apis:eBLBaseComponents}UserID")
            
            if user_id_elem is not None and user_id_elem.text:
                ebay_connect_logger.log_event(
                    user_id=user_id,
                    environment=target_env,
                    action="get_user_username",
                    request=request_payload,
                    response={
                        "status": response.status_code,
                        "headers": dict(response.headers),
                        "body": user_id_elem.text
                    }
                )
                return user_id_elem.text
            
            ebay_connect_logger.log_event(
                user_id=user_id,
                environment=target_env,
                action="get_user_username",
                request=request_payload,
                response={
                    "status": response.status_code,
                    "headers": dict(response.headers),
                    "body": response.text[:2000]
                },
                error="Username not found"
            )
            return None
        except Exception as e:
            logger.error(f"Failed to get eBay username: {str(e)}")
            ebay_connect_logger.log_event(
                user_id=user_id,
                environment=target_env,
                action="get_user_username_error",
                request=request_payload,
                error=str(e)
            )
            return None
    
    async def get_message_folders(self, access_token: str) -> Dict[str, Any]:
        """Get message folders using GetMyMessages with ReturnSummary.

        Also logs the raw XML summary so we can distinguish between "0 folders in
        XML" vs "parser failed to find FolderSummary".
        """
        import xml.etree.ElementTree as ET
        
        api_url = "https://api.ebay.com/ws/api.dll"
        
        xml_request = f"""<?xml version="1.0" encoding="utf-8"?>
<GetMyMessagesRequest xmlns="urn:ebay:apis:eBLBaseComponents">
  <RequesterCredentials>
    <eBayAuthToken>{access_token}</eBayAuthToken>
  </RequesterCredentials>
  <DetailLevel>ReturnSummary</DetailLevel>
  <WarningLevel>High</WarningLevel>
</GetMyMessagesRequest>"""
        
        headers = {
            "X-EBAY-API-SITEID": "0",
            "X-EBAY-API-COMPATIBILITY-LEVEL": "1193",
            "X-EBAY-API-CALL-NAME": "GetMyMessages",
            "Content-Type": "text/xml"
        }
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(api_url, content=xml_request, headers=headers)
            
            raw_xml = response.text or ""
            # Log a truncated copy of the raw XML for diagnostics (no token in body)
            logger.info(f"GetMyMessages ReturnSummary raw XML (first 2000 chars): {raw_xml[:2000]}")
            
            root = ET.fromstring(raw_xml)
            ns = {"ebay": "urn:ebay:apis:eBLBaseComponents"}
            
            folders = []
            summary_elem = root.find(".//ebay:Summary", ns)
            total_message_count = None
            new_message_count = None
            if summary_elem is not None:
                tmc_elem = summary_elem.find("ebay:TotalMessageCount", ns)
                nmc_elem = summary_elem.find("ebay:NewMessageCount", ns)
                if tmc_elem is not None and tmc_elem.text is not None:
                    try:
                        total_message_count = int(tmc_elem.text)
                    except ValueError:
                        total_message_count = None
                if nmc_elem is not None and nmc_elem.text is not None:
                    try:
                        new_message_count = int(nmc_elem.text)
                    except ValueError:
                        new_message_count = None

                folder_elems = summary_elem.findall("ebay:FolderSummary", ns)
                if not folder_elems and (total_message_count or new_message_count):
                    logger.warning(
                        "GetMyMessages Summary has counts but no FolderSummary elements – parser may be misaligned with XML structure."
                    )
                for folder_elem in folder_elems:
                    folder_id_elem = folder_elem.find("ebay:FolderID", ns)
                    folder_name_elem = folder_elem.find("ebay:FolderName", ns)
                    total_elem = folder_elem.find("ebay:TotalMessageCount", ns)
                    
                    if folder_id_elem is not None and folder_name_elem is not None:
                        folders.append({
                            "folder_id": folder_id_elem.text,
                            "folder_name": folder_name_elem.text,
                            "total_count": int(total_elem.text) if total_elem is not None and total_elem.text is not None else 0,
                        })
            else:
                logger.warning("GetMyMessages ReturnSummary: <Summary> element not found in XML")
            
            if not folders and (total_message_count or new_message_count):
                logger.warning(
                    f"GetMyMessages summary counts present (TotalMessageCount={total_message_count}, NewMessageCount={new_message_count}) but no folders parsed."
                )
            elif not folders and not (total_message_count or new_message_count):
                logger.info("GetMyMessages summary indicates 0 folders/messages (no counts and no FolderSummary elements)")
            
            return {"folders": folders, "total_message_count": total_message_count, "new_message_count": new_message_count}
        except Exception as e:
            logger.error(f"Failed to get message folders: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to get message folders: {str(e)}")
    
    async def get_message_headers(
        self,
        access_token: str,
        folder_id: str,
        page_number: int = 1,
        entries_per_page: int = 200,
        start_time_from: Optional[str] = None,
        start_time_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get message headers (IDs only) using GetMyMessages with ReturnHeaders.

        Optional start_time_from/start_time_to allow worker-driven time windows.
        """
        import xml.etree.ElementTree as ET
        
        api_url = "https://api.ebay.com/ws/api.dll"
        
        now_iso = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z")
        start_from_iso = start_time_from or "2015-01-01T00:00:00.000Z"
        start_to_iso = start_time_to or now_iso
        
        xml_request = f"""<?xml version="1.0" encoding="utf-8"?>
<GetMyMessagesRequest xmlns="urn:ebay:apis:eBLBaseComponents">
  <RequesterCredentials>
    <eBayAuthToken>{access_token}</eBayAuthToken>
  </RequesterCredentials>
  <DetailLevel>ReturnHeaders</DetailLevel>
  <FolderID>{folder_id}</FolderID>
  <WarningLevel>High</WarningLevel>
  <StartTimeFrom>{start_from_iso}</StartTimeFrom>
  <StartTimeTo>{start_to_iso}</StartTimeTo>
  <Pagination>
    <EntriesPerPage>{entries_per_page}</EntriesPerPage>
    <PageNumber>{page_number}</PageNumber>
  </Pagination>
</GetMyMessagesRequest>"""
        
        headers = {
            "X-EBAY-API-SITEID": "0",
            "X-EBAY-API-COMPATIBILITY-LEVEL": "1193",
            "X-EBAY-API-CALL-NAME": "GetMyMessages",
            "Content-Type": "text/xml"
        }
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(api_url, content=xml_request, headers=headers)
            
            root = ET.fromstring(response.text)
            ns = {"ebay": "urn:ebay:apis:eBLBaseComponents"}
            
            message_ids = []
            alert_ids = []
            
            messages_elem = root.find(".//ebay:Messages", ns)
            if messages_elem is not None:
                for msg_elem in messages_elem.findall("ebay:Message", ns):
                    msg_id_elem = msg_elem.find("ebay:MessageID", ns)
                    if msg_id_elem is not None and msg_id_elem.text:
                        message_ids.append(msg_id_elem.text)
                
                for alert_elem in messages_elem.findall("ebay:Alert", ns):
                    alert_id_elem = alert_elem.find("ebay:AlertID", ns)
                    if alert_id_elem is not None and alert_id_elem.text:
                        alert_ids.append(alert_id_elem.text)
            
            pagination_elem = root.find(".//ebay:PaginationResult", ns)
            total_pages = 1
            total_entries = 0
            if pagination_elem is not None:
                total_pages_elem = pagination_elem.find("ebay:TotalNumberOfPages", ns)
                total_entries_elem = pagination_elem.find("ebay:TotalNumberOfEntries", ns)
                if total_pages_elem is not None:
                    total_pages = int(total_pages_elem.text)
                if total_entries_elem is not None:
                    total_entries = int(total_entries_elem.text)
            
            return {
                "message_ids": message_ids,
                "alert_ids": alert_ids,
                "total_pages": total_pages,
                "total_entries": total_entries
            }
        except Exception as e:
            logger.error(f"Failed to get message headers: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to get message headers: {str(e)}")
    
    async def get_message_bodies(self, access_token: str, message_ids: List[str]) -> List[Dict[str, Any]]:
        """Get message bodies using GetMyMessages with ReturnMessages (batch of up to 10 IDs).

        IMPORTANT: When requesting by MessageID, the Trading API expects a
        <MessageIDs> container with one or more <MessageID> children and no
        additional filters (no StartTime/EndTime/FolderID/Pagination).
        """
        import xml.etree.ElementTree as ET

        if not message_ids:
            return []

        if len(message_ids) > 10:
            raise ValueError("Cannot fetch more than 10 message IDs at once")

        api_url = "https://api.ebay.com/ws/api.dll"

        # Wrap message IDs in the required <MessageIDs><MessageID>...</MessageID></MessageIDs> container
        message_id_xml = "".join(f"<MessageID>{mid}</MessageID>" for mid in message_ids)

        xml_request = f"""<?xml version="1.0" encoding="utf-8"?>
<GetMyMessagesRequest xmlns="urn:ebay:apis:eBLBaseComponents">
  <RequesterCredentials>
    <eBayAuthToken>{access_token}</eBayAuthToken>
  </RequesterCredentials>
  <DetailLevel>ReturnMessages</DetailLevel>
  <WarningLevel>High</WarningLevel>
  <MessageIDs>
    {message_id_xml}
  </MessageIDs>
</GetMyMessagesRequest>"""

        headers = {
            "X-EBAY-API-SITEID": "0",
            "X-EBAY-API-COMPATIBILITY-LEVEL": "1193",
            "X-EBAY-API-CALL-NAME": "GetMyMessages",
            "Content-Type": "text/xml",
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(api_url, content=xml_request, headers=headers)

            raw_xml = response.text or ""
            # Log a truncated copy of the raw XML for debugging the first few batches
            logger.info(f"GetMyMessages ReturnMessages raw XML (first 2000 chars): {raw_xml[:2000]}")

            root = ET.fromstring(raw_xml)
            ns = {"ebay": "urn:ebay:apis:eBLBaseComponents"}

            messages: List[Dict[str, Any]] = []
            messages_elem = root.find(".//ebay:Messages", ns)
            if messages_elem is not None:
                for msg_elem in messages_elem.findall("ebay:Message", ns):
                    message: Dict[str, Any] = {}

                    for field in [
                        "MessageID",
                        "ExternalMessageID",
                        "Subject",
                        "Text",
                        "Sender",
                        "RecipientUserID",
                        "ReceiveDate",
                        "ExpirationDate",
                        "ItemID",
                        "FolderID",
                    ]:
                        elem = msg_elem.find(f"ebay:{field}", ns)
                        if elem is not None and elem.text is not None:
                            message[field.lower()] = elem.text

                    read_elem = msg_elem.find("ebay:Read", ns)
                    flagged_elem = msg_elem.find("ebay:Flagged", ns)
                    message["read"] = read_elem is not None and read_elem.text == "true"
                    message["flagged"] = flagged_elem is not None and flagged_elem.text == "true"

                    messages.append(message)

            return messages
        except Exception as e:
            logger.error(f"Failed to get message bodies: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to get message bodies: {str(e)}")

    async def sync_all_messages(
        self,
        user_id: str,
        access_token: str,
        run_id: Optional[str] = None,
        ebay_account_id: Optional[str] = None,
        ebay_user_id: Optional[str] = None,
        window_from: Optional[str] = None,
        window_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Synchronize messages from eBay Trading GetMyMessages into ebay_messages.

        This mirrors the logic used in the /messages/sync background job but is
        adapted for the multi-account worker model (user_id + ebay_account_id).
        Time window (window_from/window_to) is passed through to GetMyMessages
        StartTimeFrom/StartTimeTo to support incremental sync.
        """
        from app.services.sync_event_logger import SyncEventLogger, is_cancelled
        from app.services.ebay_database import ebay_db
        from app.models_sqlalchemy import SessionLocal
        from app.models_sqlalchemy.models import Message as SqlMessage
        from app.services.message_parser import parse_ebay_message_html
        from sqlalchemy.exc import IntegrityError
        import time

        event_logger = SyncEventLogger(user_id, "messages", run_id=run_id)
        job_id = ebay_db.create_sync_job(user_id, "messages")
        start_time = time.time()

        db_session = SessionLocal()
        try:
            total_fetched = 0
            total_stored = 0

            from app.config import settings
            import asyncio
            from datetime import datetime

            event_logger.log_start(
                f"Starting Messages sync from eBay ({settings.EBAY_ENVIRONMENT})",
            )
            event_logger.log_info(
                "API Configuration: Trading API (XML), message headers limit=200, bodies batch=10",
            )

            # Determine effective time window for headers
            now_iso = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z")
            start_from_iso = window_from or "2015-01-01T00:00:00.000Z"
            start_to_iso = window_to or now_iso

            event_logger.log_info(
                f"Time window: {start_from_iso} .. {start_to_iso}",
            )

            await asyncio.sleep(0.5)

            if is_cancelled(event_logger.run_id):
                event_logger.log_warning("Sync operation cancelled before start")
                duration_ms = int((time.time() - start_time) * 1000)
                event_logger.log_done(
                    "Messages sync cancelled: 0 fetched, 0 stored",
                    0,
                    0,
                    duration_ms,
                )
                ebay_db.update_sync_job(job_id, "cancelled", 0, 0)
                return {
                    "status": "cancelled",
                    "total_fetched": 0,
                    "total_stored": 0,
                    "job_id": job_id,
                    "run_id": event_logger.run_id,
                }

            # Step 1: get folders summary
            event_logger.log_info(
                "→ Requesting: GetMyMessages (ReturnSummary) for folders",
            )
            request_start = time.time()
            folders_response = await self.get_message_folders(access_token)
            request_duration = int((time.time() - request_start) * 1000)
            folders = folders_response.get("folders", [])

            event_logger.log_http_request(
                "POST",
                "/ws/eBayISAPI.dll (GetMyMessages - ReturnSummary)",
                200,
                request_duration,
                len(folders),
            )
            event_logger.log_info(
                f"← Response: 200 OK ({request_duration}ms) - Received {len(folders)} custom folders (Inbox/Sent are not included in FolderSummary)",
            )

            total_messages_declared = sum(f.get("total_count", 0) for f in folders)
            event_logger.log_info(
                f"Summary reports {total_messages_declared} messages across {len(folders)} custom folders (excluding Inbox/Sent)",
            )

            await asyncio.sleep(0.3)

            # Build folder list for sync: always include Inbox (0) and Sent (1),
            # plus any custom folders returned in Summary. This ensures we do
            # not incorrectly treat "no FolderSummary" as "no messages".
            folder_specs: List[Dict[str, Any]] = [
                {"folder_id": "0", "folder_name": "Inbox", "total_count": None},
                {"folder_id": "1", "folder_name": "Sent", "total_count": None},
            ]
            # Append custom folders (if any)
            for f in folders:
                fid = f.get("folder_id")
                if fid in ("0", "1"):
                    continue
                folder_specs.append({
                    "folder_id": fid,
                    "folder_name": f.get("folder_name"),
                    "total_count": f.get("total_count", 0),
                })

            folder_index = 0
            for folder in folder_specs:
                if is_cancelled(event_logger.run_id):
                    event_logger.log_warning("Sync operation cancelled by user")
                    duration_ms = int((time.time() - start_time) * 1000)
                    event_logger.log_done(
                        f"Messages sync cancelled: {total_fetched} fetched, {total_stored} stored",
                        total_fetched,
                        total_stored,
                        duration_ms,
                    )
                    ebay_db.update_sync_job(job_id, "cancelled", total_fetched, total_stored)
                    return {
                        "status": "cancelled",
                        "total_fetched": total_fetched,
                        "total_stored": total_stored,
                        "job_id": job_id,
                        "run_id": event_logger.run_id,
                    }

                folder_index += 1
                folder_id = folder.get("folder_id")
                folder_name = folder.get("folder_name")
                folder_total = folder.get("total_count", 0)

                event_logger.log_progress(
                    f"Processing folder {folder_index}/{len(folder_specs)}: {folder_name} ({folder_total if folder_total is not None else 'unknown'} messages)",
                    folder_index,
                    len(folder_specs),
                    total_fetched,
                    total_stored,
                )

                # Skip only if folder_id is missing; do not skip just because
                # total_count==0, since Inbox/Sent are not represented in
                # Summary counts and may still have messages.
                if not folder_id:
                    continue

                # Step 2: enumerate headers in this folder with pagination + window
                all_message_ids: List[str] = []
                page_number = 1
                max_pages = 1000
                consecutive_empty_pages = 0
                max_empty_pages = 3

                while page_number <= max_pages:
                    if is_cancelled(event_logger.run_id):
                        event_logger.log_warning("Sync operation cancelled by user")
                        duration_ms = int((time.time() - start_time) * 1000)
                        event_logger.log_done(
                            f"Messages sync cancelled: {total_fetched} fetched, {total_stored} stored",
                            total_fetched,
                            total_stored,
                            duration_ms,
                        )
                        ebay_db.update_sync_job(
                            job_id,
                            "cancelled",
                            total_fetched,
                            total_stored,
                        )
                        return {
                            "status": "cancelled",
                            "total_fetched": total_fetched,
                            "total_stored": total_stored,
                            "job_id": job_id,
                            "run_id": event_logger.run_id,
                        }

                    event_logger.log_info(
                        f"→ Requesting headers page {page_number}: GetMyMessages (ReturnHeaders, folder={folder_name})",
                    )

                    try:
                        request_start = time.time()
                        headers_response = await self.get_message_headers(
                            access_token,
                            folder_id,
                            page_number=page_number,
                            entries_per_page=MESSAGES_HEADERS_LIMIT,
                            start_time_from=start_from_iso,
                            start_time_to=start_to_iso,
                        )
                        request_duration = int((time.time() - request_start) * 1000)

                        message_ids = headers_response.get("message_ids", [])
                        alert_ids = headers_response.get("alert_ids", [])
                        total_pages = headers_response.get("total_pages", 1) or 1

                        all_message_ids.extend(message_ids)
                        all_message_ids.extend(alert_ids)

                        event_logger.log_http_request(
                            "POST",
                            f"/ws/eBayISAPI.dll (GetMyMessages - {folder_name} page {page_number})",
                            200,
                            request_duration,
                            len(message_ids) + len(alert_ids),
                        )
                        event_logger.log_info(
                            f"← Response: 200 OK ({request_duration}ms) - Page {page_number}/{total_pages}: {len(message_ids)} messages, {len(alert_ids)} alerts",
                        )

                        if not message_ids and not alert_ids:
                            consecutive_empty_pages += 1
                            if consecutive_empty_pages >= max_empty_pages:
                                event_logger.log_warning(
                                    f"Stopping pagination after {consecutive_empty_pages} consecutive empty pages",
                                )
                                break
                        else:
                            consecutive_empty_pages = 0

                        if page_number >= total_pages:
                            break

                        page_number += 1
                        await asyncio.sleep(0.5)

                    except Exception as e:
                        error_msg = (
                            f"Error fetching headers page {page_number} for folder {folder_name}: {str(e)}"
                        )
                        event_logger.log_error(error_msg, e)
                        page_number += 1
                        await asyncio.sleep(0.5)
                        continue

                # Step 3: fetch bodies in batches of 10 and upsert
                if not all_message_ids:
                    continue

                total_batches = (len(all_message_ids) + MESSAGES_BODIES_BATCH - 1) // MESSAGES_BODIES_BATCH
                batch_index = 0

                for i in range(0, len(all_message_ids), MESSAGES_BODIES_BATCH):
                    if is_cancelled(event_logger.run_id):
                        event_logger.log_warning("Sync operation cancelled by user")
                        duration_ms = int((time.time() - start_time) * 1000)
                        event_logger.log_done(
                            f"Messages sync cancelled: {total_fetched} fetched, {total_stored} stored",
                            total_fetched,
                            total_stored,
                            duration_ms,
                        )
                        ebay_db.update_sync_job(
                            job_id,
                            "cancelled",
                            total_fetched,
                            total_stored,
                        )
                        return {
                            "status": "cancelled",
                            "total_fetched": total_fetched,
                            "total_stored": total_stored,
                            "job_id": job_id,
                            "run_id": event_logger.run_id,
                        }

                    batch_ids = all_message_ids[i : i + MESSAGES_BODIES_BATCH]
                    batch_index += 1
                    event_logger.log_info(
                        f"→ Requesting bodies batch {batch_index}/{total_batches}: {len(batch_ids)} IDs",
                    )

                    request_start = time.time()
                    try:
                        messages = await self.get_message_bodies(access_token, batch_ids)
                        request_duration = int((time.time() - request_start) * 1000)

                        event_logger.log_http_request(
                            "POST",
                            f"/ws/eBayISAPI.dll (GetMyMessages - {folder_name} batch {batch_index}/{total_batches})",
                            200,
                            request_duration,
                            len(messages),
                        )
                        event_logger.log_info(
                            f"← Response: 200 OK ({request_duration}ms) - Received {len(messages)} message bodies",
                        )

                        total_fetched += len(messages)

                        # Store messages
                        for msg in messages:
                            message_id = msg.get("messageid") or msg.get("externalmessageid")
                            if not message_id:
                                continue

                            existing = (
                                db_session.query(SqlMessage)
                                .filter(
                                    SqlMessage.message_id == message_id,
                                    SqlMessage.user_id == user_id,
                                    SqlMessage.ebay_account_id == ebay_account_id,
                                )
                                .first()
                            )
                            
                            is_read = msg.get("read", False)
                            is_flagged = msg.get("flagged", False)
                            folder_id = msg.get("folderid")
                            is_archived = folder_id == "2"

                            if existing:
                                changed = False
                                if existing.is_read != is_read:
                                    existing.is_read = is_read
                                    changed = True
                                if existing.is_flagged != is_flagged:
                                    existing.is_flagged = is_flagged
                                    changed = True
                                if existing.is_archived != is_archived:
                                    existing.is_archived = is_archived
                                    changed = True
                                
                                if not changed:
                                    continue
                                
                                # If changed, we fall through to the logging and commit part.
                                # But wait, the original code creates db_message below.
                                # We need to restructure this loop slightly.
                                # Let's just log and update here, then continue to next iteration to avoid re-creating db_message logic which is complex.
                                
                                try:
                                    from app.services.ebay_event_inbox import log_ebay_event
                                    log_ebay_event(
                                        source="trading_poll",
                                        channel="messages",
                                        topic="MESSAGE_UPDATED",
                                        entity_type="MESSAGE",
                                        entity_id=message_id,
                                        ebay_account=ebay_user_id or ebay_account_id,
                                        event_time=datetime.utcnow(),
                                        publish_time=None,
                                        headers={
                                            "worker": "messages_worker",
                                            "api_family": "messages",
                                            "user_id": user_id,
                                            "ebay_account_id": ebay_account_id,
                                            "ebay_user_id": ebay_user_id,
                                        },
                                        payload=msg,
                                        db=db_session,
                                    )
                                except Exception:
                                    logger.warning("Failed to log ebay_events row for message %s", message_id, exc_info=True)

                                db_session.add(existing)
                                db_session.commit()
                                total_stored += 1
                                continue

                            sender = msg.get("sender", "")
                            recipient = msg.get("recipientuserid", "")
                            direction = "INCOMING"

                            receive_date_str = msg.get("receivedate", "")
                            message_date = datetime.utcnow()
                            if receive_date_str:
                                try:
                                    message_date = datetime.fromisoformat(
                                        receive_date_str.replace("Z", "+00:00")
                                    )
                                except Exception:
                                    pass

                            body_html = msg.get("text", "") or ""
                            parsed_body: Optional[Dict[str, Any]] = None
                            normalized: Dict[str, Any] = {}
                            preview_text: Optional[str] = None
                            listing_id = msg.get("itemid")
                            order_id: Optional[str] = None
                            transaction_id: Optional[str] = None
                            is_case_related = False
                            message_topic: Optional[str] = None
                            case_event_type: Optional[str] = None
                            has_attachments = False
                            attachments_meta: List[Any] = []

                            try:
                                if body_html:
                                    # Primary rich parser used by the legacy /messages grid.
                                    parsed = parse_ebay_message_html(
                                        body_html,
                                        our_account_username=ebay_user_id or "seller",
                                    )
                                    # Use pydantic JSON serialization to avoid HttpUrl issues.
                                    parsed_body = json.loads(parsed.json(exclude_none=True))
                                    # Use preview from the rich parser when available.
                                    preview_text = parsed.previewText or None
                            except Exception as parse_err:
                                # Parsing errors should never break ingestion; log and continue.
                                logger.warning(
                                    f"Failed to parse eBay message body for {message_id} via rich parser: {parse_err}"
                                )

                            # Best-effort normalized view on top of the same HTML, reusing
                            # the lighter-weight message_body_parser.
                            try:
                                from app.ebay.message_body_parser import parse_ebay_message_body

                                normalized_body = parse_ebay_message_body(
                                    body_html,
                                    our_account_username=ebay_user_id or "seller",
                                )
                                if parsed_body is None:
                                    # normalized_body already JSON-serializable
                                    parsed_body = normalized_body
                                else:
                                    # Merge normalized block into existing parsed_body
                                    if normalized_body.get("normalized"):
                                        parsed_body["normalized"] = normalized_body["normalized"]

                                norm = normalized_body.get("normalized") or {}
                                normalized = norm
                                # Map normalized fields into dedicated columns when present.
                                order_id = norm.get("orderId") or order_id
                                listing_id = norm.get("itemId") or listing_id
                                transaction_id = norm.get("transactionId") or transaction_id

                                message_topic = norm.get("topic") or None
                                case_event_type = norm.get("caseEventType") or None
                                # Simple heuristic: CASE/RETURN/INQUIRY/PAYMENT_DISPUTE
                                if message_topic in {"CASE", "RETURN", "INQUIRY", "PAYMENT_DISPUTE"}:
                                    is_case_related = True

                                # Attachments: outer attachments list can be synced into
                                # attachments_meta if present and well-formed.
                                attachments = norm.get("attachments") or []
                                if isinstance(attachments, list) and attachments:
                                    has_attachments = True
                                    # Store as-is; structure is documented in the spec.
                                    attachments_meta = attachments

                                # Prefer normalized summaryText as preview when available.
                                if norm.get("summaryText"):
                                    preview_text = norm.get("summaryText")
                            except Exception as parse_err:
                                logger.warning(
                                    f"Failed to build normalized view for eBay message {message_id}: {parse_err}"
                                )

                            db_message = SqlMessage(
                                ebay_account_id=ebay_account_id,
                                user_id=user_id,
                                message_id=message_id,
                                thread_id=msg.get("externalmessageid") or message_id,
                                sender_username=sender,
                                recipient_username=recipient,
                                subject=msg.get("subject", ""),
                                body=body_html,
                                message_type="MEMBER_MESSAGE",
                                is_read=msg.get("read", False),
                                is_flagged=msg.get("flagged", False),
                                is_archived=msg.get("folderid") == "2",
                                direction=direction,
                                message_date=message_date,
                                message_at=message_date,
                                order_id=order_id,
                                listing_id=listing_id,
                                case_id=normalized.get("caseId"),
                                case_type=normalized.get("caseType"),
                                inquiry_id=normalized.get("inquiryId"),
                                return_id=normalized.get("ReturnId"),
                                payment_dispute_id=normalized.get("paymentDisputeId"),
                                transaction_id=transaction_id,
                                is_case_related=is_case_related,
                                message_topic=message_topic,
                                case_event_type=case_event_type,
                                raw_data=str(msg),
                                parsed_body=parsed_body,
                                has_attachments=has_attachments,
                                attachments_meta=attachments_meta,
                                preview_text=preview_text,
                            )

                            # Log event for new message
                            try:
                                from app.services.ebay_event_inbox import log_ebay_event
                                log_ebay_event(
                                    source="trading_poll",
                                    channel="messages",
                                    topic="MESSAGE_CREATED",
                                    entity_type="MESSAGE",
                                    entity_id=message_id,
                                    ebay_account=ebay_user_id or ebay_account_id,
                                    event_time=message_date,
                                    publish_time=None,
                                    headers={
                                        "worker": "messages_worker",
                                        "api_family": "messages",
                                        "user_id": user_id,
                                        "ebay_account_id": ebay_account_id,
                                        "ebay_user_id": ebay_user_id,
                                    },
                                    payload=msg,
                                    db=db_session,
                                )
                            except Exception:
                                logger.warning("Failed to log ebay_events row for new message %s", message_id, exc_info=True)

                            try:
                                db_session.add(db_message)
                                db_session.commit()
                                total_stored += 1
                            except IntegrityError as ie:
                                # Duplicate per (ebay_account_id, user_id, message_id) – safe to ignore.
                                db_session.rollback()
                                logger.info(
                                    "Duplicate ebay_message skipped (account=%s, user=%s, message_id=%s): %s",
                                    ebay_account_id,
                                    user_id,
                                    message_id,
                                    str(ie),
                                )
                            except Exception as e:
                                db_session.rollback()
                                error_msg = (
                                    f"Error inserting ebay_message {message_id} in batch {batch_index} for folder {folder_name}: {str(e)}"
                                )
                                event_logger.log_error(error_msg, e)
                                await asyncio.sleep(0.5)
                                continue

                    except Exception as e:
                        db_session.rollback()
                        error_msg = (
                            f"Error fetching/storing bodies batch {batch_index} for folder {folder_name}: {str(e)}"
                        )
                        event_logger.log_error(error_msg, e)
                        await asyncio.sleep(0.5)
                        continue

            duration_ms = int((time.time() - start_time) * 1000)
            ebay_db.update_sync_job(job_id, "completed", total_fetched, total_stored)
            event_logger.log_done(
                f"Messages sync completed: {total_fetched} fetched, {total_stored} stored in {duration_ms}ms",
                total_fetched,
                total_stored,
                duration_ms,
            )

            return {
                "status": "completed",
                "total_fetched": total_fetched,
                "total_stored": total_stored,
                "job_id": job_id,
                "run_id": event_logger.run_id,
            }

        except Exception as e:
            error_msg = str(e)
            event_logger.log_error(f"Messages sync failed: {error_msg}", e)
            ebay_db.update_sync_job(job_id, "failed", error_message=error_msg)
            raise
        finally:
            db_session.close()
            event_logger.close()


ebay_service = EbayService()
