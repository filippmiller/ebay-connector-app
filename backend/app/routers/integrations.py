from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from typing import Optional, List

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.models_sqlalchemy import get_db
from app.models_sqlalchemy.models import (
    IntegrationProvider,
    IntegrationAccount,
    IntegrationCredentials,
    EmailMessage,
    AiEmailTrainingPair,
    AiProvider,
    User as SAUser,
)
from app.services.auth import get_current_active_user, admin_required
from app.models.user import User
from app.utils.logger import logger
from app.services.gmail_sync import sync_gmail_account


router = APIRouter(prefix="/integrations", tags=["integrations"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_gmail_redirect_uri() -> str:
    """Return the public Gmail OAuth redirect URI based on settings.

    GMAIL_OAUTH_REDIRECT_BASE_URL is expected to include the external /api
    prefix, e.g. https://api.example.com/api, so the final callback URL is:

        {base}/integrations/gmail/callback
    """

    base = settings.GMAIL_OAUTH_REDIRECT_BASE_URL
    if not base:
        raise RuntimeError("GMAIL_OAUTH_REDIRECT_BASE_URL is not configured")
    return base.rstrip("/") + "/integrations/gmail/callback"


def _ensure_gmail_provider(db: Session) -> IntegrationProvider:
    """Get or create the IntegrationProvider row for Gmail.

    This is called lazily during the Gmail OAuth callback, so no separate
    startup seeding step is required.
    """

    provider = (
        db.query(IntegrationProvider)
        .filter(IntegrationProvider.code == "gmail")
        .one_or_none()
    )
    if provider:
        return provider

    scopes_raw = settings.GMAIL_OAUTH_SCOPES or "https://www.googleapis.com/auth/gmail.readonly"
    # Store scopes as a JSON array for easier inspection later.
    scopes_list: List[str] = [s for s in scopes_raw.split() if s]

    provider = IntegrationProvider(
        code="gmail",
        name="Gmail",
        auth_type="oauth2",
        default_scopes=scopes_list,
    )
    db.add(provider)
    db.flush()  # assign id
    logger.info("Created IntegrationProvider for Gmail (id=%s)", provider.id)
    return provider


def _serialize_integration_account(
    account: IntegrationAccount,
    provider: IntegrationProvider,
    owner: Optional[SAUser],
) -> dict:
    return {
        "id": account.id,
        "provider_code": provider.code,
        "provider_name": provider.name,
        "owner_user_id": account.owner_user_id,
        "owner_email": getattr(owner, "email", None) if owner else None,
        "external_account_id": account.external_account_id,
        "display_name": account.display_name,
        "status": account.status,
        "last_sync_at": account.last_sync_at.isoformat() if account.last_sync_at else None,
        "meta": account.meta or {},
    }


def _serialize_ai_email_pair(
    pair: AiEmailTrainingPair,
    account: IntegrationAccount,
    provider: IntegrationProvider,
) -> dict:
    return {
        "id": pair.id,
        "provider_code": provider.code,
        "integration_account_id": account.id,
        "integration_display_name": account.display_name,
        "thread_id": pair.thread_id,
        "status": pair.status,
        "client_text": pair.client_text,
        "our_reply_text": pair.our_reply_text,
        "created_at": pair.created_at.isoformat() if pair.created_at else None,
        "updated_at": pair.updated_at.isoformat() if pair.updated_at else None,
    }


# ---------------------------------------------------------------------------
# Gmail OAuth endpoints
# ---------------------------------------------------------------------------


@router.post("/gmail/auth-url")
async def get_gmail_auth_url(
    request: Request,
    current_user: User = Depends(get_current_active_user),
):
    """Return a Google OAuth URL to connect a Gmail account for the user.

    The frontend will redirect the browser to this URL to start the OAuth
    consent flow. The resulting callback will hit /integrations/gmail/callback
    with ?code=...&state=... from Google.
    """

    client_id = settings.GMAIL_CLIENT_ID
    if not client_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Gmail OAuth is not configured (missing GMAIL_CLIENT_ID)",
        )

    redirect_uri = _get_gmail_redirect_uri()

    # Build state with the owner user id and a nonce. We could later extend
    # this with HMAC signing or additional return-url metadata if needed.
    state_payload = {
        "owner_user_id": current_user.id,
        "nonce": datetime.utcnow().isoformat(),
    }
    state = json.dumps(state_payload)

    scopes_raw = settings.GMAIL_OAUTH_SCOPES or "https://www.googleapis.com/auth/gmail.readonly"
    scopes = [s for s in scopes_raw.split() if s]
    scope_param = " ".join(scopes)

    # According to Google OAuth 2.0 for Web Server Applications docs.
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": scope_param,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }

    from urllib.parse import urlencode

    auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)

    logger.info(
        "Generated Gmail OAuth URL for user %s (redirect_uri=%s)",
        current_user.id,
        redirect_uri,
    )

    return {"auth_url": auth_url}


@router.get("/gmail/callback")
async def gmail_oauth_callback(
    request: Request,
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Handle Google OAuth callback, exchange code for tokens, and persist.

    This endpoint does not require an authenticated user; the identity of the
    app user is derived from the signed/opaque ``state`` value produced by
    /gmail/auth-url.
    """

    if not code:
        logger.warning("Gmail callback received without code")
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL.rstrip('/')}/admin/integrations?gmail=error&reason=missing_code"
        )

    if not state:
        logger.warning("Gmail callback received without state")
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL.rstrip('/')}/admin/integrations?gmail=error&reason=missing_state"
        )

    try:
        state_data = json.loads(state)
    except Exception:
        logger.exception("Failed to parse Gmail OAuth state: %s", state)
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL.rstrip('/')}/admin/integrations?gmail=error&reason=invalid_state"
        )

    owner_user_id = state_data.get("owner_user_id")
    if not owner_user_id:
        logger.error("Gmail OAuth state missing owner_user_id: %s", state_data)
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL.rstrip('/')}/admin/integrations?gmail=error&reason=missing_owner"
        )

    token_endpoint = "https://oauth2.googleapis.com/token"

    client_id = settings.GMAIL_CLIENT_ID
    client_secret = settings.GMAIL_CLIENT_SECRET
    if not client_id or not client_secret:
        logger.error("Gmail OAuth is not fully configured (client id/secret)")
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL.rstrip('/')}/admin/integrations?gmail=error&reason=server_config"
        )

    redirect_uri = _get_gmail_redirect_uri()

    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
    }

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
            resp = await client.post(token_endpoint, data=data)
    except httpx.HTTPError as e:
        logger.error("HTTP error talking to Google token endpoint: %s", e)
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL.rstrip('/')}/admin/integrations?gmail=error&reason=token_http"
        )

    if resp.status_code != 200:
        logger.error("Gmail token endpoint error: status=%s body=%s", resp.status_code, resp.text)
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL.rstrip('/')}/admin/integrations?gmail=error&reason=token_failed"
        )

    token_payload = resp.json()
    access_token: Optional[str] = token_payload.get("access_token")
    refresh_token: Optional[str] = token_payload.get("refresh_token")
    expires_in: Optional[int] = token_payload.get("expires_in")

    if not access_token:
        logger.error("Gmail token response missing access_token: %s", token_payload)
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL.rstrip('/')}/admin/integrations?gmail=error&reason=missing_access_token"
        )

    # Fetch profile to determine the Gmail address.
    profile_email: Optional[str] = None
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
            profile_resp = await client.get(
                "https://gmail.googleapis.com/gmail/v1/users/me/profile",
                headers={"Authorization": f"Bearer {access_token}"},
            )
        if profile_resp.status_code == 200:
            profile_json = profile_resp.json()
            profile_email = profile_json.get("emailAddress")
        else:
            logger.warning(
                "Gmail users.me.profile returned %s: %s",
                profile_resp.status_code,
                profile_resp.text,
            )
    except httpx.HTTPError as e:
        logger.error("HTTP error calling users.me.profile: %s", e)

    if not profile_email:
        logger.error("Could not determine Gmail address from profile; aborting integration")
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL.rstrip('/')}/admin/integrations?gmail=error&reason=profile_failed"
        )

    # Upsert provider, account, and credentials in a single DB transaction.
    try:
        provider = _ensure_gmail_provider(db)

        # Optional: attach owner info (for response serialization only).
        owner: Optional[SAUser] = db.query(SAUser).filter(SAUser.id == owner_user_id).one_or_none()

        account = (
            db.query(IntegrationAccount)
            .filter(
                IntegrationAccount.provider_id == provider.id,
                IntegrationAccount.owner_user_id == owner_user_id,
                IntegrationAccount.external_account_id == profile_email,
            )
            .one_or_none()
        )
        if not account:
            display_name = f"Gmail – {profile_email}"
            account = IntegrationAccount(
                provider_id=provider.id,
                owner_user_id=owner_user_id,
                external_account_id=profile_email,
                display_name=display_name,
                status="active",
            )
            db.add(account)
            db.flush()
            logger.info(
                "Created new Gmail IntegrationAccount id=%s for user=%s email=%s",
                account.id,
                owner_user_id,
                profile_email,
            )
        else:
            # Ensure the account is marked active again.
            account.status = "active"

        creds = (
            db.query(IntegrationCredentials)
            .filter(IntegrationCredentials.integration_account_id == account.id)
            .one_or_none()
        )
        if not creds:
            creds = IntegrationCredentials(integration_account_id=account.id)
            db.add(creds)

        # Use property setters so values are transparently encrypted at rest.
        creds.access_token = access_token
        if refresh_token:
            # On re-consent Google may omit refresh_token; keep existing one in that case.
            creds.refresh_token = refresh_token

        if expires_in is not None:
            creds.expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))

        scopes_raw = token_payload.get("scope") or settings.GMAIL_OAUTH_SCOPES or "https://www.googleapis.com/auth/gmail.readonly"
        scopes_list: List[str] = [s for s in scopes_raw.split() if s]
        creds.scopes = scopes_list

        db.commit()

        logger.info(
            "Gmail integration updated: account_id=%s owner_user_id=%s email=%s",
            account.id,
            owner_user_id,
            profile_email,
        )

    except Exception:
        db.rollback()
        logger.exception("Failed to persist Gmail integration for user %s", owner_user_id)
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL.rstrip('/')}/admin/integrations?gmail=error&reason=persist_failed"
        )

    # Successful completion: redirect back to admin Integrations page.
    return RedirectResponse(
        url=f"{settings.FRONTEND_URL.rstrip('/')}/admin/integrations?gmail=connected",
        status_code=status.HTTP_302_FOUND,
    )


# ---------------------------------------------------------------------------
# Integrations admin API (backend only)
# ---------------------------------------------------------------------------


@router.get("/accounts")
async def list_integration_accounts(
    provider: Optional[str] = Query(None, description="Filter by provider code, e.g. 'gmail'"),
    owner_user_id: Optional[str] = Query(None, description="Filter by owner user id"),
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required),
):
    """List integration accounts for admin purposes.

    This endpoint never exposes secrets; it only returns high-level metadata
    needed by the future Integrations admin UI.
    """

    q = db.query(IntegrationAccount, IntegrationProvider, SAUser).join(
        IntegrationProvider, IntegrationAccount.provider_id == IntegrationProvider.id
    ).outerjoin(SAUser, SAUser.id == IntegrationAccount.owner_user_id)

    if provider:
        q = q.filter(IntegrationProvider.code == provider)
    if owner_user_id:
        q = q.filter(IntegrationAccount.owner_user_id == owner_user_id)

    rows = q.order_by(IntegrationProvider.code, IntegrationAccount.display_name).all()

    accounts = [
        _serialize_integration_account(acc, prov, user) for acc, prov, user in rows
    ]
    return {"accounts": accounts, "count": len(accounts)}


@router.post("/accounts/{account_id}/disable")
async def disable_integration_account(
    account_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required),
):
    account = db.query(IntegrationAccount).filter(IntegrationAccount.id == account_id).one_or_none()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="integration_account_not_found")

    account.status = "disabled"
    db.commit()
    db.refresh(account)

    provider = db.query(IntegrationProvider).filter(IntegrationProvider.id == account.provider_id).one()
    owner = db.query(SAUser).filter(SAUser.id == account.owner_user_id).one_or_none()

    logger.info("Integration account %s disabled by admin %s", account.id, current_user.id)

    return _serialize_integration_account(account, provider, owner)


@router.post("/accounts/{account_id}/enable")
async def enable_integration_account(
    account_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required),
):
    account = db.query(IntegrationAccount).filter(IntegrationAccount.id == account_id).one_or_none()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="integration_account_not_found")

    account.status = "active"
    db.commit()
    db.refresh(account)

    provider = db.query(IntegrationProvider).filter(IntegrationProvider.id == account.provider_id).one()
    owner = db.query(SAUser).filter(SAUser.id == account.owner_user_id).one_or_none()

    logger.info("Integration account %s enabled by admin %s", account.id, current_user.id)

    return _serialize_integration_account(account, provider, owner)


@router.post("/accounts/{account_id}/resync")
async def request_integration_resync(
    account_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required),
):
    """Mark an integration account for manual resync.

    The future Gmail worker will look at meta["manual_resync_requested_at"]
    as a hint to prioritise this account on the next run.
    """

    account = db.query(IntegrationAccount).filter(IntegrationAccount.id == account_id).one_or_none()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="integration_account_not_found")

    meta = dict(account.meta or {})
    meta["manual_resync_requested_at"] = datetime.now(timezone.utc).isoformat()
    account.meta = meta

    db.commit()
    db.refresh(account)

    provider = db.query(IntegrationProvider).filter(IntegrationProvider.id == account.provider_id).one()
    owner = db.query(SAUser).filter(SAUser.id == account.owner_user_id).one_or_none()

    logger.info("Manual resync requested for integration account %s by admin %s", account.id, current_user.id)

    return _serialize_integration_account(account, provider, owner)


@router.post("/accounts/{account_id}/sync-now")
async def sync_integration_account_now(
    account_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required),  # noqa: ARG001
):
    """Run a one-off sync for a single integration account.

    This endpoint is primarily used by the admin Integrations UI to provide a
    "Run sync now" button with an immediate textual summary of what changed.
    """

    account = db.query(IntegrationAccount).filter(IntegrationAccount.id == account_id).one_or_none()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="integration_account_not_found")

    provider = db.query(IntegrationProvider).filter(IntegrationProvider.id == account.provider_id).one_or_none()
    if not provider:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="integration_provider_not_found")

    if provider.code != "gmail":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="sync_not_supported_for_provider")

    try:
        summary = await sync_gmail_account(db, account.id, manual=True)
    except RuntimeError as exc:
        # Controlled failures (missing creds, inactive, etc.).
        logger.error("Gmail sync-now failed for account %s: %s", account.id, exc)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Gmail sync-now failed for account %s: %s", account.id, exc, exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="gmail_sync_failed") from exc

    # Reload account to ensure last_sync_at/meta are fresh.
    db.refresh(account)

    return {
        "account_id": summary.get("account_id"),
        "messages_fetched": summary.get("messages_fetched", 0),
        "messages_upserted": summary.get("messages_upserted", 0),
        "pairs_created": summary.get("pairs_created", 0),
        "pairs_skipped_existing": summary.get("pairs_skipped_existing", 0),
        "errors": summary.get("errors", []),
        "last_sync_at": account.last_sync_at.isoformat() if account.last_sync_at else None,
        "meta": account.meta or {},
    }

class AiEmailPairStatusUpdate(BaseModel):
    status: str


class OpenAiProviderPayload(BaseModel):
    api_key: Optional[str] = None
    model_default: Optional[str] = None


@router.get("/ai-email-pairs")
async def list_ai_email_pairs(
    status: str = Query("new", description="Filter by pair status: new|approved|rejected"),
    provider: Optional[str] = Query(None, description="Filter by provider code, e.g. 'gmail'"),
    integration_account_id: Optional[str] = Query(None, description="Filter by specific integration account id"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required),  # noqa: ARG001
):
    """List AI email training pairs for admin review.

    Returns a lightweight paginated payload suitable for the Admin AI Email Training UI.
    """

    q = (
        db.query(AiEmailTrainingPair, IntegrationAccount, IntegrationProvider)
        .join(IntegrationAccount, AiEmailTrainingPair.integration_account_id == IntegrationAccount.id)
        .join(IntegrationProvider, IntegrationAccount.provider_id == IntegrationProvider.id)
    )

    if status:
        q = q.filter(AiEmailTrainingPair.status == status)
    if provider:
        q = q.filter(IntegrationProvider.code == provider)
    if integration_account_id:
        q = q.filter(IntegrationAccount.id == integration_account_id)

    total = q.count()

    rows = (
        q.order_by(AiEmailTrainingPair.created_at.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )

    items = [
        _serialize_ai_email_pair(pair, account, prov)
        for pair, account, prov in rows
    ]

    return {"items": items, "count": total, "limit": limit, "offset": offset}


@router.post("/ai-email-pairs/{pair_id}/status")
async def update_ai_email_pair_status(
    pair_id: str,
    payload: AiEmailPairStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required),  # noqa: ARG001
):
    """Update the status of a single AI email training pair.

    Valid statuses are: new, approved, rejected.
    """

    new_status = (payload.status or "").strip().lower()
    allowed = {"new", "approved", "rejected"}
    if new_status not in allowed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_status")

    pair = db.query(AiEmailTrainingPair).filter(AiEmailTrainingPair.id == pair_id).one_or_none()
    if not pair:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ai_email_pair_not_found")

    pair.status = new_status
    db.commit()
    db.refresh(pair)

    account = db.query(IntegrationAccount).filter(IntegrationAccount.id == pair.integration_account_id).one()
    provider = db.query(IntegrationProvider).filter(IntegrationProvider.id == account.provider_id).one()

    return _serialize_ai_email_pair(pair, account, provider)


@router.get("/ai-provider/openai")
async def get_openai_provider(
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required),  # noqa: ARG001
):
    """Return OpenAI provider config without exposing the raw API key.

    The response indicates whether a key is set and what the default model is.
    """

    provider = (
        db.query(AiProvider)
        .filter(AiProvider.provider_code == "openai")
        .one_or_none()
    )

    has_api_key = bool(provider and provider.api_key)
    model_default = provider.model_default if provider else None

    return {
        "provider_code": "openai",
        "name": provider.name if provider else "OpenAI",
        "has_api_key": has_api_key,
        "model_default": model_default,
    }

@router.post("/ai-provider/openai")
async def upsert_openai_provider(
    payload: OpenAiProviderPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required),
):
    """Create or update the OpenAI provider configuration.

    - api_key: new key to store (encrypted). If omitted/empty, the existing
      key is preserved.
    - model_default: logical default model name (e.g. "gpt-4.1-mini").
    """

    provider = (
        db.query(AiProvider)
        .filter(AiProvider.provider_code == "openai")
        .one_or_none()
    )
    if not provider:
        provider = AiProvider(
            provider_code="openai",
            name="OpenAI",
            owner_user_id=str(current_user.id),
        )
        db.add(provider)

    # Update API key only when a non-empty value is provided, so an
    # accidental empty submit does not wipe the key.
    if payload.api_key is not None and payload.api_key != "":
        provider.api_key = payload.api_key

    if payload.model_default:
        provider.model_default = payload.model_default.strip()

    db.commit()
    db.refresh(provider)

    return {
        "provider_code": provider.provider_code,
        "name": provider.name,
        "has_api_key": bool(provider.api_key),
        "model_default": provider.model_default,
    }
