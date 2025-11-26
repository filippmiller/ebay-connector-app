# REPORT_TOKEN_FLOW

This document describes the current eBay OAuth token flow in production, storage fields, TTL sources, required scopes, and fixes applied to the Token Info UI.

1) Authorization Code Flow (Production)
- Authorization URL generation
  - File: backend/app/services/ebay.py → EbayService.get_authorization_url()
  - Uses production auth base URL, RuName, scopes. Logs a sanitized event.
- Callback and code exchange
  - Files:
    - backend/app/routers/ebay.py → @router.post("/auth/callback")
    - backend/app/services/ebay.py → EbayService.exchange_code_for_token()
  - On success, saves account, tokens, and scopes.

2) Storage of tokens and fields
- Models and columns
  - Table: ebay_accounts
  - Table: ebay_tokens
    - access_token (Text)
    - refresh_token (Text)
    - token_type (Text)
    - expires_at (DateTime(timezone=True)) — user access token expiry (UTC)
    - refresh_expires_at (DateTime(timezone=True)) — refresh token expiry (UTC) [added]
    - last_refreshed_at (DateTime(timezone=True))
    - refresh_error (Text)
- Where saved
  - backend/app/services/ebay_account_service.py → save_tokens()
    - Now accepts refresh_token_expires_in and computes refresh_expires_at = now_utc + delta.
  - backend/app/routers/ebay.py (callback) passes refresh_token_expires_in from token response (if present).

3) Timezone and TTL sources
- All computations use timezone-aware UTC: datetime.now(timezone.utc) + timedelta(seconds=…)
- access_expires_at from expires_in.
- refresh_expires_at from refresh_token_expires_in when present; if not present, the value remains null and UI shows a helpful hint.

4) Scopes
- Scopes are stored at account level: ebay_authorizations.scopes (array of strings).
- UI and Debugger use scopes to validate template access.
- Required scopes mapping (client/UI):
  - identity → https://api.ebay.com/oauth/api_scope
  - orders/disputes → https://api.ebay.com/oauth/api_scope/sell.fulfillment
  - transactions → https://api.ebay.com/oauth/api_scope/sell.finances
  - inventory/offers → https://api.ebay.com/oauth/api_scope/sell.inventory
  - messages → https://api.ebay.com/oauth/api_scope/trading

**2025-11-26 – Sniper / Buy Offer note:**

- Для Sniper-модуля (Buy Browse + Buy Offer) мы дополнительно полагаемся на
  наличие buy-скопов в user-токене, в частности:
  - base: `https://api.ebay.com/oauth/api_scope`;
  - bidding: `https://api.ebay.com/oauth/api_scope/buy.offer.auction`.
- Эти scope не отражены в упрощённой матрице выше (она фокусируется на
  sell-* и базовых Debugger-шаблонах), но фактически присутствуют в
  `ebay_authorizations.scopes` для аккаунтов, переподключённых после
  применения миграции `ensure_buy_offer_auction_scope_20251126`.
- При анализе проблем со Sniper/ставками всегда проверяйте, что у
  соответствующего аккаунта в `ebay_authorizations.scopes` есть
  `buy.offer.auction`.

5) Why “Full Access” TTL looked like 2 hours previously
- The UI used the term “Full Access Token” for the displayed token but actually showed the user access token, which naturally has ~2h TTL. This was a terminology/UI bug. The UI is corrected to:
  - “User access token (~2h)” — used for REST calls.
  - “Refresh token (long-lived)” — used only to obtain a new user access token.

6) Admin endpoints (Production, feature flagged by FEATURE_TOKEN_INFO)
- GET /api/admin/ebay/tokens/info?env=production
  - Returns masked access and refresh tokens, access_expires_at/TTL, refresh_expires_at/TTL (if available), scopes.
- POST /api/admin/ebay/tokens/refresh?env=production
  - Refreshes user access token using refresh token; returns updated access TTL.
- GET /api/admin/ebay/tokens/logs?env=production&limit=100
  - Returns last 100 token-related actions (token_info_viewed, token_refreshed, token_refresh_failed, token_call_blocked_missing_scopes).
- POST /api/admin/ebay/tokens/logs/blocked-scope?env=production
  - Records token_call_blocked_missing_scopes with {template, path, required_scopes, missing_scopes}.

7) Debugger usage and guards
- All Debugger “Send Request” calls are signed with the user access token (Bearer) by backend.
- Quick Templates have requiredScopes; on missing scopes the UI blocks the call, shows a banner, and logs a token_call_blocked_missing_scopes event (production, feature-flagged).

8) Manual test checklist
- Connect to eBay (Production) and ensure tokens persisted (access_expires_at and, if provided by eBay, refresh_expires_at).
- Open API Debugger → Token Info: see both tokens, access TTL, refresh TTL (or hint if missing), scopes.
- Click Manual User Token Refresh: see updated access TTL; a token_refreshed event appears in Token Terminal Log.
- Pick a template without required scope: see a “Missing required scopes” banner and a token_call_blocked_missing_scopes entry in the log.

9) Files changed
- backend/app/models_sqlalchemy/models.py (add refresh_expires_at)
- backend/alembic/versions/20251113_add_refresh_expires_at_to_ebay_tokens.py
- backend/app/services/ebay_account_service.py (save_tokens signature, UTC-aware)
- backend/app/routers/ebay.py (callback passes refresh_token_expires_in)
- backend/app/routers/admin.py (info returns refresh TTL; refresh uses UTC; token logs endpoints)
- frontend/src/components/EbayDebugger.tsx (UI: TTLs, hints; scope guard; token terminal log)
