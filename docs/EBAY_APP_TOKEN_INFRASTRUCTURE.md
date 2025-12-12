# eBay Application Access Token (AppToken) Infrastructure

## 1. Overview

### 1.1 Application vs user access tokens

The eBay platform exposes two main OAuth token types:

- **Application access token (AppToken)**
  - Obtained via the **client_credentials** grant.
  - Represents the *application* itself, not a specific seller account.
  - Typically used for operations that are scoped to the app, such as:
    - Notification API management for topics with `scope = APPLICATION`.
    - Public metadata / discovery calls that do not act on a seller’s account.

- **User access token**
  - Obtained via the **authorization_code** flow (and refreshed via **refresh_token**).
  - Represents a specific seller’s account and consented scopes.
  - Used for all account-specific actions: Orders, Finances, Inventory, Offers,
    Messages, and Sniper bidding.

### 1.2 How this project uses each token type today

Within this repository:

- **User access tokens** are the primary tokens for business logic:
  - They are stored per account in `ebay_tokens` and per authorization in
    `ebay_authorizations.scopes`.
  - Workers and routers use them for Fulfillment, Finances, Inventory, Offers,
    Messages, and Sniper (Browse + Buy Offer) flows.

- **Application access tokens (AppTokens)** are used more narrowly today:
  - To call the eBay Commerce Notification **public key** endpoint for webhook
    signature verification.
  - To manage **Notification API subscriptions** for application-scoped topics
    (notably `MARKETPLACE_ACCOUNT_DELETION` and `AUTHORIZATION_REVOCATION`),
    depending on topic metadata.
  - They are always minted programmatically via `grant_type=client_credentials`
    using the configured Client ID / Cert ID.

Sniper and most normal REST calls **do not** use AppTokens today; they rely on
user access tokens that carry the full user-consent scope set.

---

## 2. Code locations and helpers

### 2.1 Core helper: `EbayService.get_app_access_token`

**File:** `backend/app/services/ebay.py`  
**Symbol:** `class EbayService`, method `async def get_app_access_token(...) -> str`

Responsibilities:

- Mint an **application access token** using the eBay Identity OAuth endpoint
  with `grant_type=client_credentials`.
- Choose the correct environment (sandbox vs production) before making the
  request.
- Request a configurable list of scopes (defaulting to the base scope).
- Log structured events about the request/response via `ebay_logger`.

Behavior (simplified):

```python
async def get_app_access_token(
    self,
    scopes: Optional[List[str]] = None,
    environment: Optional[str] = None,
) -> str:
    target_env = environment or settings.EBAY_ENVIRONMENT or "sandbox"
    original_env = settings.EBAY_ENVIRONMENT
    settings.EBAY_ENVIRONMENT = target_env
    try:
        if not settings.ebay_client_id or not settings.ebay_cert_id:
            # log error and raise HTTPException(500)
        credentials = f"{settings.ebay_client_id}:{settings.ebay_cert_id}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {encoded_credentials}",
        }
        if not scopes:
            scopes = ["https://api.ebay.com/oauth/api_scope"]
        scopes = [s.strip() for s in scopes if s and s.strip()]
        data = {
            "grant_type": "client_credentials",
            "scope": " ".join(scopes),
        }
        # log app_token_request with masked headers
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(self.token_url, headers=headers, data=data)
        # log app_token_response
        # on 200: parse JSON, return token_data["access_token"]; on error: raise
    finally:
        settings.EBAY_ENVIRONMENT = original_env
```

Key characteristics:

- **Grant type:** `client_credentials` (always application access token).
- **Default scopes:** `['https://api.ebay.com/oauth/api_scope']`.
- **Scope handling:**
  - Caller may pass an explicit `scopes` list.
  - The method normalizes it (strip whitespace, drop empty strings) and joins
    with spaces as required by eBay.
- **Environment:**
  - Temporarily mutates `settings.EBAY_ENVIRONMENT` to the desired target
    (`sandbox` or `production`) so that `self.token_url` and
    `settings.ebay_client_id` / `settings.ebay_cert_id` resolve correctly.

### 2.2 Indirect helper: `EbayService.ensure_notification_subscription`

**File:** `backend/app/services/ebay.py`  
**Symbol:** `async def ensure_notification_subscription(...)`

Responsibilities:

- Manage Commerce Notification API **subscriptions** for a given `topic_id`
  and `destination_id`.
- Internally decides whether to use an **application** token or a **user**
  token for subscription operations based on the topic’s `scope` metadata.

Relevant behavior for AppTokens:

- Fetches topic metadata via `GET /commerce/notification/v1/topic/{topicId}`.
- Reads `topic_json.get("scope")` and normalizes it.
- Derives a boolean flag:

  ```python
  topic_scope = str(topic_json.get("scope") or "").upper()
  use_app_token = topic_scope == "APPLICATION" or topic_id == "MARKETPLACE_ACCOUNT_DELETION"
  sub_token = access_token

  if use_app_token:
      debug_log.append("[topic] scope=...; using application access token for subscription calls")
      sub_token = await self.get_app_access_token()
  else:
      debug_log.append("[topic] scope=...; using user access token for subscription calls")
  ```

- After that, **all subscription list/create/update calls** in this helper use
  `sub_token`, which for `APPLICATION` topics is an AppToken minted by
  `get_app_access_token`.

While `ensure_notification_subscription` is not itself an AppToken minting
function, it is an **important consumer** that automatically switches to an
AppToken for application-scoped topics.

### 2.3 Webhook signature helper: `ebay_signature._get_ebay_public_key`

**File:** `backend/app/services/ebay_signature.py`  
**Symbol:** `async def _get_ebay_public_key(kid: str) -> Tuple[Optional[str], Optional[Dict[str, Any]]]`

Responsibilities:

- Fetch and cache the **public key** used to verify eBay webhook signatures
  (`X-EBAY-SIGNATURE` header).
- Authenticate the public-key endpoint using an **application access token**.

Key behavior:

- Maintains an in-memory cache `_PUBLIC_KEY_CACHE` keyed by `kid` with a
  TTL of one hour.
- On cache miss:

  ```python
  app_token = await ebay_service.get_app_access_token()
  base_url = settings.ebay_api_base_url.rstrip("/")
  url = f"{base_url}/commerce/notification/v1/public_key/{kid}"
  headers = {"Authorization": f"Bearer {app_token}", "Accept": "application/json"}
  # GET public_key endpoint
  ```

This is the main **non-Notification** consumer of AppTokens: every time a
previously unseen `kid` appears in a webhook signature, this helper mints an
AppToken and caches the associated public key.

### 2.4 Admin diagnostics: `admin.test_marketplace_deletion_notification`

**File:** `backend/app/routers/admin.py`  
**Endpoint:** `POST /api/admin/notifications/test-marketplace-deletion`

Responsibilities:

- End-to-end test for the Notification API setup for the
  `MARKETPLACE_ACCOUNT_DELETION` topic.
- Ensures destination + subscription and then calls the Notification API
  `/subscription/{id}/test` endpoint.

AppToken usage:

- Before calling `test_notification_subscription`, this endpoint explicitly
  mints an AppToken:

  ```python
  app_access_token = await ebay_service.get_app_access_token()
  debug_log.append("[token] Using eBay application access token (client_credentials) for subscription + test")
  test_result = await ebay_service.test_notification_subscription(
      app_access_token,
      sub_id,
      debug_log=debug_log,
  )
  ```

- This mirrors eBay’s recommendation that **application-scoped topics** use an
  application token for test operations.

### 2.5 Admin diagnostics: `admin.test_notification_topic`

**File:** `backend/app/routers/admin.py`  
**Endpoint:** `POST /api/admin/notifications/test-topic`

Responsibilities:

- Generic test endpoint for arbitrary configured topics.
- Ensures destination + subscription, then decides whether to use a user token
  or an AppToken for the test call.

AppToken usage:

- After obtaining a subscription, it calls `EbayService.get_notification_topic_metadata`
  and inspects `scope`:

  ```python
  topic_meta = await ebay_service.get_notification_topic_metadata(access_token, topic_id, debug_log=debug_log)
  raw_scope = topic_meta.get("scope")
  scope_upper = raw_scope.upper() if isinstance(raw_scope, str) else None

  if scope_upper == "APPLICATION":
      app_access_token = await ebay_service.get_app_access_token()
      test_access_token = app_access_token
      debug_log.append("[token] Using eBay application access token (client_credentials) for subscription + test")
      token_type = "application"
  else:
      test_access_token = access_token
      debug_log.append("[token] Using eBay user access token for subscription + test")
      token_type = "user"
  ```

- This makes AppToken use for tests **topic-aware** instead of hardcoded.

---

## 3. Configuration & environment variables

### 3.1 Core eBay OAuth credentials and environment

**File:** `backend/app/config.py`  
**Symbol:** `class Settings(BaseSettings)`

Relevant settings:

- `EBAY_ENVIRONMENT: str = "sandbox"`
  - Global flag controlling which environment is “active”.
- Sandbox credentials:
  - `EBAY_SANDBOX_CLIENT_ID: Optional[str]`
  - `EBAY_SANDBOX_CERT_ID: Optional[str]`
  - `EBAY_SANDBOX_DEV_ID: Optional[str]`
- Production credentials:
  - `EBAY_PRODUCTION_CLIENT_ID: Optional[str]`
  - `EBAY_PRODUCTION_CERT_ID: Optional[str]`
  - `EBAY_PRODUCTION_DEV_ID: Optional[str]`
- Redirect/RuName values per environment (used mainly for user tokens):
  - `EBAY_SANDBOX_RUNAME`, `EBAY_PRODUCTION_RUNAME`
- Derived properties:
  - `settings.ebay_client_id` → returns sandbox or production client ID based on
    `EBAY_ENVIRONMENT`.
  - `settings.ebay_cert_id` → same pattern for Cert ID.
  - `settings.ebay_api_base_url` → `https://api.sandbox.ebay.com` or
    `https://api.ebay.com`.
  - `settings.ebay_auth_base_url` → `https://auth.sandbox.ebay.com` or
    `https://auth.ebay.com`.

These are the **single source of truth** for Client ID / Cert ID and auth
endpoints.

### 3.2 Token endpoint URLs

**File:** `backend/app/services/ebay.py`  
**Symbol:** `EbayService.__init__`, `auth_url`, `token_url` properties

- Sandbox endpoints:
  - `self.sandbox_auth_url = "https://auth.sandbox.ebay.com/oauth2/authorize"`
  - `self.sandbox_token_url = "https://api.sandbox.ebay.com/identity/v1/oauth2/token"`
- Production endpoints:
  - `self.production_auth_url = "https://auth.ebay.com/oauth2/authorize"`
  - `self.production_token_url = "https://api.ebay.com/identity/v1/oauth2/token"`

`EbayService.token_url` chooses between `sandbox_token_url` and
`production_token_url` based on `settings.EBAY_ENVIRONMENT` at call time. This
is what `get_app_access_token` uses when performing the `client_credentials`
exchange.

### 3.3 Notification-related configuration

**File:** `backend/app/config.py`

- `EBAY_NOTIFICATION_DESTINATION_URL: Optional[str]`
  - Public webhook URL used in Notification API destination configuration.
- `EBAY_NOTIFICATION_VERIFICATION_TOKEN: Optional[str]`
  - Token required for Notification API destination verification.

Although these settings are not directly involved in minting AppTokens, they
are part of the scenarios where AppTokens are used (Notification API
subscription management and test flows).

---

## 4. Token lifetime, caching, and storage

### 4.1 AppToken lifetime (expires_in)

The eBay Identity API returns AppTokens with a finite TTL, typically via the
`expires_in` field in seconds. The current implementation of
`get_app_access_token`:

- Parses the JSON response into `token_data`.
- Extracts `access_token` and returns it as a **plain string**.
- Does **not** surface `expires_in` or other metadata to the caller.

### 4.2 In-memory caching

There is **no general-purpose cache** for AppTokens today. Each call to
`get_app_access_token`:

- Performs a fresh `client_credentials` exchange with eBay.
- Logs the request and response.

The only caching behavior in this area is **public-key caching** in
`ebay_signature.py`:

- `_PUBLIC_KEY_CACHE` maps `kid` → `(public_key_pem, fetched_at_epoch)`.
- The cache TTL is 1 hour (`_PUBLIC_KEY_TTL_SECONDS = 3600`).
- When the cache misses, `_get_ebay_public_key` calls
  `get_app_access_token()` to mint a new AppToken and then fetches the public
  key from `/commerce/notification/v1/public_key/{kid}`.

This means:

- **Public keys** are cached.
- **AppTokens themselves are not cached**; each new `kid` or app-scope
  operation that calls `get_app_access_token` will perform its own
  client-credentials exchange.

### 4.3 Database storage

AppTokens are **not persisted** in the database anywhere:

- `ebay_tokens` table only stores **user** access/refresh tokens (encrypted)
  associated with an `EbayAccount`.
- There is no column or model field dedicated to application access tokens.

All AppTokens are held only in memory for the duration of the operation that
requested them.

### 4.4 Implications

- Simplicity: there is no risk of stale AppTokens in the DB or cache – each
  operation uses a freshly minted token.
- Cost / limits: high-frequency operations that repeatedly call
  `get_app_access_token` could increase traffic to
  `/identity/v1/oauth2/token` and approach eBay’s `client_credentials` limits.
  Current consumers (Notification setup/tests and webhook key fetch) are
  infrequent enough that this is acceptable for now.

---

## 5. Current consumers of AppToken

### 5.1 `EbayService.ensure_notification_subscription`

- Uses `get_app_access_token` internally when the topic metadata scope is
  `APPLICATION` or when `topic_id == "MARKETPLACE_ACCOUNT_DELETION"`.
- Affects:
  - Admin diagnostics / tests that ensure subscriptions exist.
  - Any code path that wants to idempotently configure Notification
    subscriptions.

### 5.2 `admin.test_marketplace_deletion_notification`

- Explicitly mints an AppToken via `get_app_access_token()` and uses it for the
  Notification API `test` call.
- This endpoint is called only when an admin manually triggers the “Test
  notification” button for `MARKETPLACE_ACCOUNT_DELETION`.

### 5.3 `admin.test_notification_topic`

- Generic version of the above; inspects topic scope and uses an AppToken only
  when the topic is application-scoped.
- Also triggers Notification API `test` calls and optional event-processing
  helpers.

### 5.4 `ebay_signature._get_ebay_public_key`

- Uses `get_app_access_token()` when a new `kid` value appears in
  `X-EBAY-SIGNATURE` for webhooks.
- The public key result is cached per `kid` for one hour, so this only mints
  AppTokens when:
  - A new key ID is introduced by eBay, or
  - The cache entry expires.

### 5.5 Non-consumers: Sniper and Browse

- Sniper routers (`backend/app/routers/sniper.py`) and the sniper executor
  worker (`backend/app/workers/sniper_executor.py`) **do not** use
  `get_app_access_token` today.
- Browse calls for Sniper (legacy ItemId → REST itemId conversion and auction
  metadata) use **user tokens** from `ebay_tokens`.
- Buy Offer bidding and bidding-status calls also use the same per-account
  user tokens.

Conclusion: at the time of this audit, **Sniper does not rely on AppTokens** at
all; it is purely user-token-based.

---

## 6. Relationship to the scope catalog (`ebay_scope_definitions`)

### 6.1 Scope catalog purpose

The project maintains a DB-backed catalog of scopes in the
`ebay_scope_definitions` table, represented by the `EbayScopeDefinition` model
(`backend/app/models_sqlalchemy/models.py`) and seeded by the Alembic
migration `20251114_add_ebay_scope_definitions.py`.

This catalog is used primarily for **user-consent scopes**:

- `/ebay/auth/start` loads all active scopes with `grant_type in ('user','both')`
  to build the list used in the authorization URL when the client does not
  pass explicit scopes.
- Frontend components (Connection page, Debugger) consume this catalog via
  `/ebay/scopes` to visualize and configure user scopes.

### 6.2 AppToken vs scope catalog

`get_app_access_token` currently:

- Does **not** read from `ebay_scope_definitions`.
- Uses a hardcoded default scope list:

  ```python
  if not scopes:
      scopes = ["https://api.ebay.com/oauth/api_scope"]
  ```

- Accepts an explicit `scopes` list from callers, but those callers also do not
  reference the catalog today.

Implications:

- **User tokens** are tied to the scope catalog and admin tooling.
- **AppTokens** use either:
  - A fixed default base scope, or
  - Ad-hoc scopes passed in by calling code (not currently used in this repo).
- There is no coupling between AppToken scopes and `ebay_scope_definitions` at
  the moment; they are conceptually and practically separate.

For Notification API operations, this is acceptable because:

- Application-scoped topics typically require only the base
  `https://api.ebay.com/oauth/api_scope` (plus any specific commerce.* scope if
  needed in the future).
- The actual topic scope (APPLICATION vs USER) is determined via live topic
  metadata (`/commerce/notification/v1/topic/{topicId}`), not from the local
  catalog.

---

## 7. Sandbox vs Production behavior

### 7.1 Environment selection

`get_app_access_token` takes an optional `environment` argument and falls back
as follows:

1. Use the explicit `environment` argument if provided (`"sandbox"` or
   `"production"`).
2. Otherwise, use `settings.EBAY_ENVIRONMENT`.
3. If that is not set, default to `"sandbox"`.

The method temporarily overrides `settings.EBAY_ENVIRONMENT` with the chosen
`target_env` while it mints the AppToken, then restores the original value in
a `finally` block.

### 7.2 Endpoint and scope differences

- **Token endpoints** differ only in host:
  - Sandbox: `https://api.sandbox.ebay.com/identity/v1/oauth2/token`.
  - Production: `https://api.ebay.com/identity/v1/oauth2/token`.
- **Base scopes** are environment-agnostic:
  - The default scope for AppTokens is always
    `https://api.ebay.com/oauth/api_scope`, regardless of sandbox vs
    production.
- **Notification API base URL** used for public keys and topics also respects
  `settings.ebay_api_base_url`, which switches between `api.sandbox.ebay.com`
  and `api.ebay.com`.

In practice, the same code paths are used for both environments; only the
underlying hostnames and credentials differ.

---

## 8. Gaps, risks, and TODOs

Based on this audit, the current AppToken infrastructure is functionally
correct for its limited use cases but has a few gaps to be aware of.

### 8.1 Gaps and inconsistencies

- **No AppToken caching**
  - Every call to `get_app_access_token` mints a new AppToken and discards its
    metadata (`expires_in`).
  - For low-frequency admin/test operations this is fine, but it does not
    scale well if AppTokens are used more broadly (e.g., for Browse by
    default).

- **AppToken scopes are hardcoded, not catalog-driven**
  - The default scope list is embedded in `get_app_access_token` and does not
    leverage `ebay_scope_definitions`.
  - This is acceptable for the single base scope today but may become harder
    to audit if additional AppToken scopes are needed (e.g., specific
    commerce.* scopes).

- **No explicit observability for AppToken usage volume**
  - Logs capture each request/response, but there is no summary metric or
    rate counter for `client_credentials` calls.

### 8.2 Potential risks

- **Excessive calls to `client_credentials` endpoint**
  - If future features (Sniper Browse, AI workers) start calling
    `get_app_access_token` in hot paths without caching, the app could:
    - Increase load on eBay’s token endpoint.
    - Approach rate limits for the client_credentials grant.

- **Diverging scope sets**
  - User scopes are curated via `ebay_scope_definitions`, but AppToken scopes
    are not. Over time, it may become unclear which capabilities rely on
    which type of token if AppToken scopes are extended ad hoc.

### 8.3 TODOs for future work

The following items are **not** implemented in this task but are recommended
for future iterations, especially as Sniper and AI features evolve.

1. **Introduce a lightweight in-memory AppToken cache**
   - Cache structure: per `(environment, frozenset(scopes))` key, store
     `{ access_token, expires_at }`.
   - Before minting a new token, check if a cached entry exists and is not
     near expiry (e.g., valid for at least 60–120 seconds).
   - This would significantly reduce `client_credentials` traffic for
     Notification API and any future Browse/AI consumers.

2. **Optional: expose AppToken metrics**
   - Log or emit counters for:
     - `app_token_requests_total` (by environment, success/failure).
     - `app_token_cache_hits` / `misses` if caching is added.
   - This helps monitor whether AppToken usage remains within reasonable
     bounds.

3. **Consider aligning AppToken scopes with the scope catalog**
   - For now, AppToken scopes are simple (just the base scope). If additional
     scopes become necessary, consider:
     - Adding a dedicated `grant_type = 'client'` or `grant_type = 'both'`
       section in `ebay_scope_definitions` for app-only scopes.
     - Allowing `get_app_access_token` to derive its default scope set from
       that catalog rather than from a hardcoded list.

4. **Clarify and document planned AppToken usage for Sniper/AI**
   - If we decide to use AppTokens for **Browse** in Sniper or for AI
     discovery workers:
     - Document the intended scopes and flows in this file.
     - Ensure caching is in place before putting AppTokens in a
       high-frequency code path.

5. **Add tests around AppToken minting**
   - Unit tests for `get_app_access_token`:
     - Correct selection of token endpoint by environment.
     - Proper handling of custom scope lists.
     - Error handling for missing credentials and non-200 responses.
   - Integration tests (where feasible) for Notification API helpers that rely
     on AppTokens, using mocked HTTP clients.

By addressing these items in follow-up work, the project will be ready to use
eBay Application access tokens safely and efficiently for Sniper Browse and
future AI workers while staying within eBay’s client_credentials best
practices.
