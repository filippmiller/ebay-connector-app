# Gmail Integrations & AI Email Training

This document tracks the implementation of a generic Integrations module with Gmail as the first connector, plus the email/AI training data layer.

This iteration covers:

- **Phase 0 – Audit** of existing code (backend, frontend, workers).
- **Phase 1 – DB schema** (Alembic migrations + SQLAlchemy models + credentials encryption wiring).

Subsequent iterations will add OAuth flows, admin UI, workers, and AI training views.

---

## Phase 2 – Backend: Gmail OAuth2 flow & basic API

### Gmail ENV configuration

Gmail-specific settings are added to the main backend config (`backend/app/config.py`) and exposed via the global `settings` object:

- `GMAIL_CLIENT_ID: Optional[str]`
- `GMAIL_CLIENT_SECRET: Optional[str]`
- `GMAIL_OAUTH_REDIRECT_BASE_URL: Optional[str]`
  - Public base URL for backend API, typically including the `/api` prefix.
  - Example: `https://api.yourdomain.com/api`.
  - The actual callback URL becomes `{GMAIL_OAUTH_REDIRECT_BASE_URL}/integrations/gmail/callback`.
- `GMAIL_OAUTH_SCOPES: str`
  - Space-separated scopes; default is `"https://www.googleapis.com/auth/gmail.readonly"`.

These variables are documented and exemplified in `backend/.env.example`:

- `GMAIL_OAUTH_REDIRECT_BASE_URL=https://api.yourdomain.com/api`
- `GMAIL_CLIENT_ID=your-gmail-oauth-client-id`
- `GMAIL_CLIENT_SECRET=your-gmail-oauth-client-secret`
- `GMAIL_OAUTH_SCOPES=https://www.googleapis.com/auth/gmail.readonly`

At runtime, router code reads them only via `from app.config import settings`, never directly from `os.environ`.

### Gmail provider seeding

The Gmail provider row is created **lazily** the first time a successful OAuth callback is processed.

- Helper: `_ensure_gmail_provider(db: Session) -> IntegrationProvider` in
  `backend/app/routers/integrations.py`.
- Behavior:
  - Queries `IntegrationProvider` where `code = "gmail"`.
  - If found, returns it.
  - Otherwise creates a new row:
    - `code = "gmail"`
    - `name = "Gmail"`
    - `auth_type = "oauth2"`
    - `default_scopes` – parsed from `settings.GMAIL_OAUTH_SCOPES` into a JSON list of strings.
  - Flushes the session to obtain `id` and logs a short info line.

There is no separate startup seeding step; the provider row is guaranteed to exist after the first successful Gmail integration.

### OAuth endpoints

All Gmail and Integrations backend endpoints are implemented in a new router:

- File: `backend/app/routers/integrations.py`
- Router registration in `backend/app/main.py`:
  - Imported as `integrations` from `app.routers`.
  - Included via `app.include_router(integrations.router)`.
- Router prefix: `/integrations`
  - Externally, with the Cloudflare `/api` proxy, these endpoints are reachable as `/api/integrations/...`.

#### POST /api/integrations/gmail/auth-url

**Path in code:** `@router.post("/gmail/auth-url")`

**Purpose:**
Return a Google OAuth URL that the frontend can redirect the browser to in order to connect a Gmail account for the currently authenticated user.

**Auth:**

- `current_user: User = Depends(get_current_active_user)` – standard authenticated user.

**Logic:**

1. Validate configuration:
   - If `settings.GMAIL_CLIENT_ID` is missing, return HTTP 500 with a clear message (`"Gmail OAuth is not configured (missing GMAIL_CLIENT_ID)"`).
2. Compute redirect URI:
   - Use `_get_gmail_redirect_uri()` helper:
     - `base = settings.GMAIL_OAUTH_REDIRECT_BASE_URL`.
     - Final `redirect_uri = base.rstrip("/") + "/integrations/gmail/callback"`.
3. Build `state` JSON payload:

   ```json
   {
     "owner_user_id": "<current_user.id>",
     "nonce": "<ISO8601 timestamp>"
   }
   ```

   - Serialized via `json.dumps`.
4. Compute scopes:
   - `scopes_raw = settings.GMAIL_OAUTH_SCOPES or "https://www.googleapis.com/auth/gmail.readonly"`.
   - Split on whitespace to get list; join with a single space for the `scope` query param.
5. Construct Google OAuth URL:
   - Base: `https://accounts.google.com/o/oauth2/v2/auth`.
   - Query parameters:
     - `client_id = settings.GMAIL_CLIENT_ID`
     - `redirect_uri = <computed redirect_uri>`
     - `response_type = "code"`
     - `scope = <space-separated scopes>`
     - `access_type = "offline"` (we need refresh tokens)
     - `prompt = "consent"` (ensures refresh_token is returned on first connect)
     - `state = <JSON string from step 3>`
   - Final URL is built using `urllib.parse.urlencode`.
6. Log a short info entry (user id and redirect_uri).

**Response JSON:**

```json
{
  "auth_url": "https://accounts.google.com/o/oauth2/v2/auth?..."
}
```

No tokens or secrets are returned or logged.

#### GET /api/integrations/gmail/callback

**Path in code:** `@router.get("/gmail/callback")`

**Purpose:**
Handle Google’s OAuth redirect, exchange the `code` for tokens, determine the Gmail address, and upsert `IntegrationProvider`, `IntegrationAccount`, and `IntegrationCredentials` rows.

**Auth:**

- No JWT-based auth; this route is hit by the browser after Google redirects back.
- The owner is derived solely from the `state` parameter generated by `/gmail/auth-url`.

**Query parameters:**

- `code: str | None` – authorization code from Google.
- `state: str | None` – JSON string containing `owner_user_id` and a nonce.

**High-level behavior:**

1. **Basic validation:**
   - If `code` is missing → redirect to frontend:
     - `FRONTEND_URL/admin/integrations?gmail=error&reason=missing_code`.
   - If `state` is missing or cannot be parsed as JSON → redirect with `reason=missing_state` or `invalid_state`.
   - Extract `owner_user_id` from parsed state; if missing → redirect with `reason=missing_owner`.
2. **Token exchange:**
   - Endpoint: `https://oauth2.googleapis.com/token`.
   - POST form fields:
     - `client_id = settings.GMAIL_CLIENT_ID`
     - `client_secret = settings.GMAIL_CLIENT_SECRET`
     - `code = <code from query>`
     - `grant_type = "authorization_code"`
     - `redirect_uri = _get_gmail_redirect_uri()` (must match the one used in `/auth-url`).
   - Performed via `httpx.AsyncClient` with a 30-second timeout.
   - If HTTP error or non-200 status → redirect with `reason=token_http` or `token_failed`.
   - Parse JSON and extract:
     - `access_token`
     - `refresh_token` (may be `null` on re-consent)
     - `expires_in` (seconds)
3. **Profile lookup to determine Gmail address:**
   - Call `GET https://gmail.googleapis.com/gmail/v1/users/me/profile` with header:
     - `Authorization: Bearer <access_token>`.
   - On 200, extract `emailAddress` as `profile_email`.
   - On failure or missing `emailAddress`, log warning and redirect with `reason=profile_failed`.
4. **DB upsert (inside a try/except with rollback on error):**
   - Use SQLAlchemy session from `get_db()`.
   - Ensure provider exists via `_ensure_gmail_provider(db)`.
   - Optionally load owner `SAUser` row (for logging and serialization only).
   - **IntegrationAccount:**
     - Query by `(provider_id, owner_user_id, external_account_id=profile_email)`.
     - If none:
       - Create `IntegrationAccount` with:
         - `provider_id = provider.id`
         - `owner_user_id = owner_user_id`
         - `external_account_id = profile_email`
         - `display_name = f"Gmail – {profile_email}"`
         - `status = "active"`
       - `db.add(account)` and `db.flush()`.
     - If exists:
       - Ensure `status = "active"`.
   - **IntegrationCredentials:**
     - Query by `integration_account_id = account.id`.
     - Create if missing (`IntegrationCredentials(integration_account_id=account.id)`).
     - Set properties (these use the encryption helper under the hood):
       - `creds.access_token = access_token`
       - If `refresh_token` is present:
         - `creds.refresh_token = refresh_token`
         - If `refresh_token` is absent (common on re-consent), the previous stored value is preserved.
       - If `expires_in` present:
         - `creds.expires_at = now_utc + timedelta(seconds=expires_in)`.
       - `creds.scopes`:
         - From `token_payload["scope"]` if present, otherwise from `settings.GMAIL_OAUTH_SCOPES`.
         - Stored as a list of individual scope strings.
   - `db.commit()` on success; `db.rollback()` and log on any exception.
5. **Redirect back to frontend:**
   - On success:
     - `FRONTEND_URL/admin/integrations?gmail=connected` (HTTP 302).
   - On failure at any point:
     - Redirect with `gmail=error&reason=<short_reason>` (never including sensitive details).

No access_token or refresh_token is ever logged or returned to the client; both are stored only via the encrypted `IntegrationCredentials` model.

### Integrations admin API

The same router also exposes backend-only admin endpoints for listing and controlling `integrations_accounts`.

All routes below are mounted under `/integrations` prefix → externally `/api/integrations/...`.

#### GET /api/integrations/accounts

**Path in code:** `@router.get("/accounts")`

**Auth:**

- `current_user: User = Depends(admin_required)` – admin-only.

**Query parameters (optional):**

- `provider: str | None` – filter by provider code (e.g., `"gmail"`).
- `owner_user_id: str | None` – filter by owning user ID.

**Logic:**

- Query joins:
  - `IntegrationAccount`
  - `IntegrationProvider`
  - `User` (SQLAlchemy model, aliased as `SAUser`) via left join for owner email.
- Apply filters if provided.
- Order by `provider.code`, then `account.display_name`.
- Serialize each row using `_serialize_integration_account(...)`:

  ```json
  {
    "id": "<integration_account_id>",
    "provider_code": "gmail",
    "provider_name": "Gmail",
    "owner_user_id": "<user id>",
    "owner_email": "user@example.com",
    "external_account_id": "user@gmail.com",
    "display_name": "Gmail – user@gmail.com",
    "status": "active" | "disabled" | "error",
    "last_sync_at": "2025-11-25T12:34:56+00:00" | null,
    "meta": { ... }
  }
  ```

**Response JSON:**

```json
{
  "accounts": [ /* list of objects as above */ ],
  "count": 1
}
```

No credentials or tokens are included.

#### POST /api/integrations/accounts/{id}/disable

**Path in code:** `@router.post("/accounts/{account_id}/disable")`

**Auth:**

- Admin-only via `admin_required`.

**Logic:**

- Look up `IntegrationAccount` by `id`.
- If not found → 404 `integration_account_not_found`.
- Set `status = "disabled"`.
- Commit and refresh.
- Look up `IntegrationProvider` and owner `SAUser` for serialization.
- Log an info line indicating which admin disabled which account.

**Response:**

- Same shape as a single entry from `GET /accounts` (serialized account).

#### POST /api/integrations/accounts/{id}/enable

**Path in code:** `@router.post("/accounts/{account_id}/enable")`

- Mirror of `/disable`:
  - Sets `status = "active"`.
  - Returns updated serialized account.

#### POST /api/integrations/accounts/{id}/resync

**Path in code:** `@router.post("/accounts/{account_id}/resync")`

**Purpose:**
Mark an integration account for manual resync. Later, the Gmail worker will use this as a hint to prioritize the account.

**Auth:**

- Admin-only via `admin_required`.

**Logic:**

- Look up account by id; 404 if missing.
- Copy current `account.meta` (or `{}` if `None`).
- Set:

  ```python
  meta["manual_resync_requested_at"] = datetime.now(timezone.utc).isoformat()
  account.meta = meta
  ```

- Commit & refresh.
- Return serialized account as above.

**Response:**

- Same as `/disable` and `/enable`.

### Testing checklist for Phase 2

1. **Configure Gmail ENV variables (dev/local):**

   - In `backend/.env.example` (or your real `.env`), set:

   ```bash path=null start=null
   GMAIL_OAUTH_REDIRECT_BASE_URL=https://api.yourdomain.com/api
   GMAIL_CLIENT_ID=your-gmail-oauth-client-id
   GMAIL_CLIENT_SECRET=your-gmail-oauth-client-secret
   GMAIL_OAUTH_SCOPES=https://www.googleapis.com/auth/gmail.readonly
   ```

   - Ensure these are visible in the running backend via `settings.GMAIL_*`.

2. **Start backend API:**

   ```bash path=null start=null
   poetry -C backend run uvicorn app.main:app --reload
   ```

3. **Test `POST /api/integrations/gmail/auth-url`:**

   - Authenticate as a normal user (obtain a JWT via `/auth/login`).
   - Call `POST /integrations/gmail/auth-url` with `Authorization: Bearer <token>`.
   - Verify response JSON:

     ```json
     {
       "auth_url": "https://accounts.google.com/o/oauth2/v2/auth?...client_id=...&redirect_uri=.../integrations/gmail/callback&scope=...&state=..."
     }
     ```

   - Check that:
     - `client_id` matches your `GMAIL_CLIENT_ID`.
     - `redirect_uri` matches `{GMAIL_OAUTH_REDIRECT_BASE_URL}/integrations/gmail/callback`.
     - `scope` contains `https://www.googleapis.com/auth/gmail.readonly` (or your configured scopes).

4. **End-to-end OAuth test (with real credentials):**

   - In the browser, navigate to the `auth_url` from step 3.
   - Complete Google consent.
   - Google will redirect to your backend callback; the backend then redirects to:
     - `FRONTEND_URL/admin/integrations?gmail=connected` on success, or
     - `...gmail=error&reason=...` on failure.
   - After a successful run, verify in the database:
     - `integrations_providers` has a row with `code = 'gmail'`.
     - `integrations_accounts` has a row with:
       - `provider_id` → Gmail provider.
       - `owner_user_id` → your user id.
       - `external_account_id` → your Gmail address.
     - `integrations_credentials` has a row pointing to that account with non-null `access_token` and possibly `refresh_token` (encrypted).

5. **Verify tokens are stored encrypted:**

   - Directly query `integrations_credentials.access_token` and `refresh_token` from Postgres.
   - Values should be opaque `ENC:v1:...` strings; no raw bearer tokens in the DB.

6. **Test `GET /api/integrations/accounts` as admin:**

   - Authenticate as an admin user.
   - Call `GET /api/integrations/accounts`.
   - Verify the Gmail account appears with correct `provider_code`, `external_account_id`, and `display_name`.
   - Optionally filter:
     - `GET /api/integrations/accounts?provider=gmail`.

7. **Test enable/disable and resync endpoints:**

   - `POST /api/integrations/accounts/{id}/disable` → `status` becomes `"disabled"`.
   - `POST /api/integrations/accounts/{id}/enable` → `status` becomes `"active"`.
   - `POST /api/integrations/accounts/{id}/resync` → `meta.manual_resync_requested_at` is set to a recent ISO timestamp.

These backend capabilities complete **Phase 2**: Gmail OAuth wiring and a minimal yet functional Integrations admin API, ready to be consumed by the upcoming admin UI and Gmail sync worker.

---

## Phase 0 – Audit

### Backend findings

- **No existing generic "integrations" module**
  - Searched for `integration`, `gmail`, `google`, `oauth` across `backend/app`.
  - No tables or models named `integrations_*`, `emails_messages`, or `ai_training_pairs` exist.
  - Existing OAuth/integration logic is **eBay-specific only**.

- **Existing OAuth-style flow for eBay (good reference for Gmail later)**
  - Router: `backend/app/routers/ebay.py` implements eBay auth/callback endpoints and scope handling.
  - Supporting docs: `EBAY_OAUTH_TROUBLESHOOTING.md`, `EBAY_SETUP_GUIDE.md`, `docs/ebay-api-scopes-summary.md` explain the current OAuth patterns.
  - Frontend pages `EbayConnectionPage.tsx` and `EbayCallbackPage.tsx` (see frontend findings) are wired to these endpoints.

- **Existing encryption helper (reused for integrations)**
  - Module: `backend/app/utils/crypto.py`.
  - Implements AES-GCM encryption with versioned ciphertexts (`ENC:v1:` prefix) and derives the key from `settings.secret_key` via HKDF-SHA256.
  - Already used by `User` ORM for eBay tokens:
    - `User._ebay_access_token` / `User._ebay_refresh_token` columns.
    - Properties `ebay_access_token`, `ebay_refresh_token`, `ebay_sandbox_*` call `crypto.encrypt` / `crypto.decrypt`.
  - **Decision:** Reuse `app.utils.crypto.encrypt/decrypt` for `integrations_credentials` rather than introducing a second crypto helper or a new ENV key.

- **Existing AI-related tables (context only)**
  - `AiRule` → table `ai_rules` (analytics rules).
  - `AiQueryLog` → table `ai_query_log`.
  - `AiEbayCandidate` → table `ai_ebay_candidates`.
  - `AiEbayAction` → table `ai_ebay_actions`.
  - These confirm the project already uses dedicated AI tables and Alembic migrations (`ai_analytics_20251125.py`, `ai_ebay_candidates_20251125.py`, `ai_ebay_actions_20251125.py`).

- **No pre-existing Gmail or generic email layer**
  - No Gmail- or Google-specific modules under `backend/app/services` or `backend/app/routers`.
  - No normalized `emails`/`messages` table independent of eBay messages – only eBay-specific message normalization exists in `docs/MESSAGES_NORMALIZATION.md` and related tables.

### Frontend findings

- **Admin dashboard has no "Integrations" section yet**
  - File: `frontend/src/pages/AdminPage.tsx`.
  - Existing admin cards: Background Jobs, Settings, Users, eBay Connection, DB Explorer, Data Migration, Notifications, Security Center, UI Tweak, AI Grid Playground, AI Rules, Monitoring Candidates, Model Profitability, Auto-Offer / Auto-Buy Actions, Timesheets, Todo List.
  - **No card or route for a generic "Integrations" module or for Gmail specifically.**

- **Existing OAuth-style flow is eBay-only**
  - `frontend/src/pages/EbayConnectionPage.tsx` handles eBay connection management.
  - `frontend/src/pages/EbayCallbackPage.tsx` handles the OAuth callback from eBay.
  - There is an `oauth-smoke` Playwright test in `frontend/tests/oauth-smoke.spec.ts` that exercises the eBay OAuth flow.
  - **Decision:** These will be used as reference patterns for Gmail OAuth, but a new Integrations UI will be added separately in later phases.

### Worker patterns

- **Worker entrypoints and loop patterns (to reuse for Gmail sync later)**
  - `backend/app/workers/__init__.py` exports a set of worker loops:
    - `run_token_refresh_worker_loop` – token refresh.
    - `run_health_check_worker_loop` – health checks.
    - `run_ebay_workers_loop` / `run_ebay_workers_once` – eBay data workers.
    - `run_tasks_reminder_worker_loop` – reminders.
    - `run_sniper_loop` – sniper executor.
    - `run_monitoring_loop` – listing monitoring.
    - `run_auto_offer_buy_loop` – auto-offer/auto-buy actions.
  - `backend/app/workers/ebay_workers_loop.py` implements a canonical async loop:
    - Calls `run_cycle_for_all_accounts()` from `app.services.ebay_workers`.
    - Sleeps `interval_seconds` between cycles.
  - Additional single-purpose workers follow the same style:
    - `backend/app/workers/token_refresh_worker.py`.
    - `backend/app/workers/health_check_worker.py`.
    - `backend/app/workers/ebay_monitor_worker.py`.
    - `backend/app/workers/sniper_executor.py`.

- **Decision for Gmail worker**
  - The future `gmail_sync` / `integrations-worker` will follow the same pattern:
    - A dedicated module under `backend/app/workers/` with a `run_gmail_sync_loop` entrypoint.
    - A service layer function that processes all active accounts (similar to `run_cycle_for_all_accounts`).
  - No conflicting or overlapping generic integrations worker exists today, so the new worker can be introduced cleanly in a later phase.

---

## Phase 1 – DB schema

Phase 1 introduces the generic **Integrations** schema and the **email + AI training data** layer, implemented via:

- A new Alembic migration: `backend/alembic/versions/gmail_integrations_20251125.py`.
- New SQLAlchemy ORM models in `backend/app/models_sqlalchemy/models.py`.
- Wiring of encryption for credentials using the existing `app.utils.crypto` module.

### Tables

#### `integrations_providers`

Catalog of integration providers (Gmail, eBay, Slack, etc.).

- **Table name:** `integrations_providers`
- **Columns:**
  - `id` – `String(36)`, PK, UUID string.
  - `code` – `String(64)`, **unique** provider code (`"gmail"`, `"slack"`, ...).
  - `name` – `Text`, human-readable name (`"Gmail"`).
  - `auth_type` – `String(32)`, e.g. `"oauth2"`, `"api_key"`, `"webhook"`.
  - `default_scopes` – `JSONB`, optional default scope list.
  - `created_at` – `DateTime(timezone=True)`, `server_default=func.now()`.
  - `updated_at` – `DateTime(timezone=True)`, `server_default=func.now()`, `onupdate=func.now()`.
- **Indexes / constraints:**
  - `uq_integrations_providers_code` – unique index on `code`.
- **Relationships:**
  - One-to-many with `integrations_accounts` via `IntegrationProvider.accounts`.

#### `integrations_accounts`

Concrete connected accounts per provider and per owner (e.g. "Filipp – Gmail main").

- **Table name:** `integrations_accounts`
- **Columns:**
  - `id` – `String(36)`, PK, UUID string.
  - `provider_id` – `String(36)`, FK → `integrations_providers.id`, `ondelete="CASCADE"`, indexed.
  - `owner_user_id` – `String(36)`, FK → `users.id`, `ondelete="SET NULL"`, nullable, indexed.
  - `external_account_id` – `Text`, e.g. Gmail email address.
  - `display_name` – `Text`, label shown in the UI.
  - `status` – `String(32)`, default `"active"`, indexed (`"active" | "error" | "disabled"`).
  - `last_sync_at` – `DateTime(timezone=True)`, nullable.
  - `meta` – `JSONB`, arbitrary metadata (granted scopes, labels, etc.).
  - `created_at` – `DateTime(timezone=True)`, `server_default=func.now()`.
  - `updated_at` – `DateTime(timezone=True)`, `server_default=func.now()`, `onupdate=func.now()`.
- **Indexes:**
  - `idx_integrations_accounts_provider_id` on `provider_id`.
  - `idx_integrations_accounts_owner_user_id` on `owner_user_id`.
  - Implicit index on `status` via ORM model.
- **Relationships (ORM):**
  - `provider` – `IntegrationProvider`.
  - `owner` – `User`.
  - `credentials` – `IntegrationCredentials` (one-to-one in practice).
  - `email_messages` – collection of `EmailMessage`.
  - `training_pairs` – collection of `AiEmailTrainingPair`.

#### `integrations_credentials`

Encrypted access/refresh tokens and scopes for an `IntegrationAccount`.

- **Table name:** `integrations_credentials`
- **Columns:**
  - `id` – `String(36)`, PK, UUID string.
  - `integration_account_id` – `String(36)`, FK → `integrations_accounts.id`, `ondelete="CASCADE"`, indexed.
  - `access_token` – `Text`, encrypted string at rest.
  - `refresh_token` – `Text`, encrypted string at rest.
  - `expires_at` – `DateTime(timezone=True)`, nullable (access token expiry).
  - `scopes` – `JSONB`, actual granted scopes.
  - `created_at` – `DateTime(timezone=True)`, `server_default=func.now()`.
  - `updated_at` – `DateTime(timezone=True)`, `server_default=func.now()`, `onupdate=func.now()`.
- **Indexes:**
  - `idx_integrations_credentials_account_id` on `integration_account_id`.
- **Relationships (ORM):**
  - `account` – `IntegrationAccount.credentials`.

#### `emails_messages`

Provider-agnostic normalized email messages fetched from external providers (Gmail first).

- **Table name:** `emails_messages`
- **Columns:**
  - `id` – `String(36)`, PK, UUID string.
  - `integration_account_id` – `String(36)`, FK → `integrations_accounts.id`, `ondelete="CASCADE"`, indexed.
  - `external_id` – `Text`, provider message id (e.g. Gmail `message.id`).
  - `thread_id` – `Text`, provider thread id (e.g. Gmail `threadId`), indexed.
  - `direction` – `String(16)`, `"incoming"` or `"outgoing"`.
  - `from_address` – `Text`.
  - `to_addresses` – `JSONB`, list of recipient addresses.
  - `cc_addresses` – `JSONB`, list, nullable.
  - `bcc_addresses` – `JSONB`, list, nullable.
  - `subject` – `Text`, nullable.
  - `body_text` – `Text`, nullable (primary normalized text body).
  - `body_html` – `Text`, nullable (HTML body if stored).
  - `sent_at` – `DateTime(timezone=True)`, nullable, indexed.
  - `raw_headers` – `JSONB`, optional full header blob.
  - `created_at` – `DateTime(timezone=True)`, `server_default=func.now()`.
  - `updated_at` – `DateTime(timezone=True)`, `server_default=func.now()`, `onupdate=func.now()`.
- **Indexes / constraints:**
  - `uq_emails_messages_account_external_id` – unique on `(integration_account_id, external_id)`.
  - `idx_emails_messages_account` – on `integration_account_id`.
  - `idx_emails_messages_thread` – on `thread_id`.
  - `idx_emails_messages_sent_at` – on `sent_at`.
- **Relationships (ORM):**
  - `integration_account` – owning `IntegrationAccount`.
  - `client_pairs` – `AiEmailTrainingPair` rows where this message is the client message.
  - `reply_pairs` – `AiEmailTrainingPair` rows where this message is our reply.

#### `ai_training_pairs`

Email-based training pairs linking a client message to our reply within a thread.

- **Table name:** `ai_training_pairs`
- **Columns:**
  - `id` – `String(36)`, PK, UUID string.
  - `integration_account_id` – `String(36)`, FK → `integrations_accounts.id`, `ondelete="CASCADE"`, indexed.
  - `thread_id` – `Text`, optional reference to `emails_messages.thread_id`, indexed.
  - `client_message_id` – `String(36)`, FK → `emails_messages.id`, `ondelete="CASCADE"`.
  - `our_reply_message_id` – `String(36)`, FK → `emails_messages.id`, `ondelete="CASCADE"`.
  - `client_text` – `Text`, cleaned client email text (no long history, minimal noise).
  - `our_reply_text` – `Text`, cleaned reply text.
  - `status` – `String(32)`, default `"new"`, indexed (`"new" | "approved" | "rejected"` in later phases).
  - `labels` – `JSONB`, optional tags (category, language, sentiment, etc.).
  - `created_at` – `DateTime(timezone=True)`, `server_default=func.now()`.
  - `updated_at` – `DateTime(timezone=True)`, `server_default=func.now()`, `onupdate=func.now()`.
- **Indexes:**
  - `idx_ai_training_pairs_status` – on `status`.
  - `idx_ai_training_pairs_integration_account` – on `integration_account_id`.
  - `idx_ai_training_pairs_thread` – on `thread_id`.
- **Relationships (ORM):**
  - `integration_account` – parent `IntegrationAccount`.
  - `client_message` – `EmailMessage` referenced by `client_message_id`.
  - `our_reply_message` – `EmailMessage` referenced by `our_reply_message_id`.

### ORM models & locations

All new ORM models live in the existing main SQLAlchemy models module:

- File: `backend/app/models_sqlalchemy/models.py`
- New classes:
  - `IntegrationProvider` → `integrations_providers`
  - `IntegrationAccount` → `integrations_accounts`
  - `IntegrationCredentials` → `integrations_credentials`
  - `EmailMessage` → `emails_messages`
  - `AiEmailTrainingPair` → `ai_training_pairs`

These classes follow existing conventions:

- `id` fields use `String(36)` with a `uuid.uuid4()` default at the ORM level.
- Timestamps use `DateTime(timezone=True)` with `server_default=func.now()` and `onupdate=func.now()`.
- JSON payloads use `JSONB` from `sqlalchemy.dialects.postgresql`.
- Indexes declared in `__table_args__` mirror the Alembic migration constraints.

### Credentials encryption

We **reuse the existing encryption helper** instead of adding a new one:

- Module: `backend/app/utils/crypto.py`
  - Provides `encrypt(plaintext: str) -> str` and `decrypt(value: str) -> str`.
  - Uses AES-GCM with a key derived from `settings.secret_key` via HKDF-SHA256.
  - Ciphertexts are versioned with `ENC:v1:`; `decrypt` is backward-compatible and safe.

`IntegrationCredentials` is wired similarly to the existing `User` token fields:

- ORM columns:
  - `_access_token` mapped to physical column `access_token`.
  - `_refresh_token` mapped to `refresh_token`.
- Properties:
  - `access_token` and `refresh_token` properties encrypt on write and decrypt on read:
    - Writes:
      - If value is `None`/empty → store `NULL`.
      - Else → `crypto.encrypt(value)`.
    - Reads:
      - If DB value is `NULL` → `None`.
      - Else → `crypto.decrypt(raw_value)`.

**No new ENV variables** are introduced at this stage:

- Encryption key material continues to come from `settings.secret_key` via `app.utils.crypto`.
- When we later add Gmail, its OAuth tokens will be stored encrypted in `integrations_credentials` using this same helper.

### Migration notes

- **Migration file:**
  - Path: `backend/alembic/versions/gmail_integrations_20251125.py`
  - `revision`: `"gmail_integrations_20251125"`
  - `down_revision`: `"ai_ebay_actions_20251125"`
- **What it does:**
  - Creates:
    - `integrations_providers`
    - `integrations_accounts`
    - `integrations_credentials`
    - `emails_messages`
    - `ai_training_pairs`
  - Adds all indexes and unique constraints described above.
  - `downgrade()` drops the tables and indexes in reverse dependency order.

---

## How to apply Phase 1 changes locally

> Note: These commands assume you are running them from the repo root and have Poetry installed; adjust if your workflow differs.

1. **Install backend dependencies (if not already done):**

```bash path=null start=null
poetry -C backend install
```

2. **Run Alembic migrations to apply the new schema:**

```bash path=null start=null
poetry -C backend run alembic upgrade head
```

This will apply the `gmail_integrations_20251125` revision along with any earlier pending migrations.

3. **Quick sanity check: start the backend API locally (optional):**

```bash path=null start=null
poetry -C backend run uvicorn app.main:app --reload
```

If the server starts without errors and the migration has been applied, you should see the new tables (`integrations_providers`, `integrations_accounts`, `integrations_credentials`, `emails_messages`, `ai_training_pairs`) in the Postgres database.
