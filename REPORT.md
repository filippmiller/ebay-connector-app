# OAuth Tokens Audit (Production)

Date: 2025-11-13
Scope: Production only (Sandbox unchanged)

## 1) Where OAuth flows are implemented

- Build Authorization URL (Connect to eBay)
  - backend/app/services/ebay.py → class EbayService
    - get_authorization_url(redirect_uri, state, scopes, environment)
      - Uses auth.ebay.com for production, auth.sandbox.ebay.com for sandbox
      - Ensures base scope first: https://api.ebay.com/oauth/api_scope
      - Includes: sell.account, sell.fulfillment, sell.finances, sell.inventory
  - backend/app/routers/ebay.py → start_ebay_auth()
    - Accepts redirect_uri + environment; logs request; returns authorization_url

- Callback (authorization_code → tokens)
  - backend/app/routers/ebay.py → ebay_auth_callback()
    - Calls ebay_service.exchange_code_for_token(...)
    - Persists tokens in both account-level (EbayToken) and user-level (save_user_tokens)
    - Saves authorizations (scopes) to EbayAuthorization when present
    - Derives ebay_user_id, username via EbayService helper calls

- Code → user access token + refresh token
  - backend/app/services/ebay.py → exchange_code_for_token()
    - POST https://api.ebay.com/identity/v1/oauth2/token
    - Returns EbayTokenResponse; logs; no secrets

- Refresh user access token (by refresh_token)
  - backend/app/services/ebay.py → refresh_access_token(refresh_token)
    - POST token_url; returns EbayTokenResponse; logs; no secrets
  - Token Refresh Worker: backend/app/workers/token_refresh_worker.py
    - Uses ebay_account_service.get_accounts_needing_refresh(); calls ebay_service.refresh_access_token; saves tokens

## 2) Where tokens/metadata are stored

- Account-level tables (normalized)
  - backend/app/models_sqlalchemy/models.py
    - EbayAccount: id, org_id(user), ebay_user_id, username, house_name, ...
    - EbayToken: ebay_account_id (FK), access_token, refresh_token, token_type, expires_at, last_refreshed_at, refresh_error, created/updated_at
    - EbayAuthorization: ebay_account_id (FK), scopes JSONB

- User-level fields (legacy/compat)
  - backend/app/models/user.py (Pydantic projection of user; DB model in models_sqlalchemy not shown here)
    - ebay_access_token, ebay_refresh_token, ebay_token_expires_at (production)
    - ebay_sandbox_* counterparts (alembic/versions/20251107_add_sandbox_tokens_to_users.py)

- Expires_at computation
  - ebay_account_service.save_tokens(): expires_at = now + expires_in (UTC)
  - save_user_tokens(): expires_at = now + expires_in (UTC)

## 3) Scopes

- Requested during authorization (production):
  - Base scope: https://api.ebay.com/oauth/api_scope (must be first)
  - https://api.ebay.com/oauth/api_scope/sell.account
  - https://api.ebay.com/oauth/api_scope/sell.fulfillment
  - https://api.ebay.com/oauth/api_scope/sell.finances
  - https://api.ebay.com/oauth/api_scope/sell.inventory
  - Defined in backend/app/services/ebay.py → get_authorization_url()
- Saved scopes
  - When present, callback stores to EbayAuthorization.scopes (JSONB)

## 4) UI / API Debugger (current)

- Components/Pages
  - frontend/src/components/EbayDebugger.tsx → Debugger UI, Token Info (user-level), Total Testing Mode
  - It fetches /ebay/token-info (user context) and shows token_full (unmasked in local UI only); added admin Token Info (feature-flagged) in this change.
- Why only one token and TTL looked wrong before
  - Prior section used /ebay/token-info (user context) and derived expiry from user fields; account-level expiry is authoritative in EbayToken.expires_at.
  - Missing admin refresh/info endpoints; fixed with /api/admin/ebay/tokens/info and /api/admin/ebay/tokens/refresh (feature-flagged).
- Which token signs /identity/v1/oauth2/userinfo
  - Debug endpoint /ebay/debug uses EbayAPIDebugger.load_user_token() → user access token; scopes come from EbayAuthorization via DB lookup.

## 5) Errors (403 insufficient permission)

- /identity/v1/oauth2/userinfo requires base scope https://api.ebay.com/oauth/api_scope.
- If missing or token invalid/expired, Identity returns 4xx or an empty/denied response. Debugger now shows missing_scopes computed via token_utils.validate_scopes.

## 6) Data model confirmation / oauth_tokens

- Existing normalized storage is EbayAccount + EbayToken + EbayAuthorization. This already matches the intended oauth_tokens separation (account-level). No new table required.
- Expires_at is stored as timezone-aware DateTime (UTC) in SqlAlchemy models; computation uses datetime.utcnow().

## 7) New Admin API (Production only; feature flag)

- backend/app/routers/admin.py (this change)
  - GET /api/admin/ebay/tokens/info?env=production
    - Returns masked refresh/access, expires_at (UTC), ttl_sec, scopes, account summary, now_utc
  - POST /api/admin/ebay/tokens/refresh?env=production
    - Exchanges refresh_token → new access_token; updates expires_at; logs
  - Both guarded by admin_required and FEATURE_TOKEN_INFO

## 8) UI additions (feature-flagged)

- frontend/src/components/EbayDebugger.tsx
  - Feature flag: VITE_FEATURE_TOKEN_INFO=true
  - Token Info (Production) panel: masked tokens, UTC/TTL, scopes, Refresh Now button
  - No tokens logged; copy buttons work on masked strings only by default

## 9) Known gaps / next steps

- Optional validate endpoint (/api/admin/ebay/tokens/validate) can be added later.
- Ensure Railway deploy of backend so /api/admin endpoints are available in production.
- Pages env: set VITE_FEATURE_TOKEN_INFO=true to enable UI.

## 10) File references

- OAuth flow: backend/app/services/ebay.py; backend/app/routers/ebay.py
- Token storage: backend/app/models_sqlalchemy/models.py (EbayToken, EbayAuthorization)
- Account service: backend/app/services/ebay_account_service.py (save_tokens, save_authorizations)
- Token helper: backend/app/utils/ebay_token_helper.py
- Admin API: backend/app/routers/admin.py (new endpoints)
- Debugger UI: frontend/src/components/EbayDebugger.tsx
