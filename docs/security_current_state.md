# Security: Current State Overview

This document summarizes the current authentication, session, and logging behavior of the eBay Connector App before introducing the new Security Center.

## Authentication and users

Backend authentication is implemented in:

- `backend/app/routers/auth.py` – defines `/auth/register`, `/auth/login`, `/auth/me`, and password reset endpoints.
- `backend/app/services/auth.py` – provides password hashing, JWT token creation/validation, and dependencies used by routers.
- `backend/app/services/database.py` – exposes a `db` object that wraps the actual persistence layer.

### User storage

- The `db` service chooses implementation based on `settings.DATABASE_URL`:
  - When `DATABASE_URL` contains `postgresql`, it uses `PostgresDatabase` (modern Supabase/Postgres backend).
  - Otherwise it falls back to `SQLiteDatabase` (legacy/dev use).
- User records for the auth endpoints are defined via `app.db_models.user.User` and managed through the `db` service.
- There is also a modern SQLAlchemy `User` model in `backend/app/models_sqlalchemy/models.py` that represents users in the Postgres/Supabase schema and is used by newer modules (e.g. sync logs, events, timesheets).

### Registration

- `/auth/register` accepts `UserCreate` (email, username, password, optional role) and:
  - Ensures the email is unique using `db.get_user_by_email`.
  - Assigns `UserRole.ADMIN` automatically for a small allow-list of emails, otherwise `UserRole.USER`.
  - Hashes the password using the same SHA-256 function as for login.
  - Persists the user through `db.create_user`.

### Password hashing and verification

- Passwords are hashed using SHA-256 without salt:
  - `get_password_hash(password)` → `sha256(password).hexdigest()`.
  - `verify_password(plain, hashed)` recomputes the SHA-256 digest and compares.
- This is simple but not ideal from a security standpoint; the new Security Center work is an opportunity to move towards a stronger password hashing scheme (e.g. Argon2/bcrypt) in a backwards-compatible way.

### Login

- `/auth/login`:
  - Logs the attempt using the application logger with a request id (`rid`) when available.
  - Calls `authenticate_user(email, password)` which:
    - Looks up the user by email via `db.get_user_by_email`.
    - Verifies the SHA-256 password hash.
    - Returns the user object on success, or `None` on failure.
  - On failed authentication:
    - Logs a warning with the email and request id.
    - Raises `HTTPException` with 401 and a generic "Incorrect email or password" message.
  - On success:
    - Computes an access token expiry using `settings.ACCESS_TOKEN_EXPIRE_MINUTES`.
    - Calls `create_access_token({"sub": user.id}, expires_delta=...)`.
    - Returns `{ "access_token": <JWT>, "token_type": "bearer" }`.

### JWT tokens and sessions

- JWTs are created using `jose.jwt.encode` with:
  - Payload containing `sub` (user id) and `exp` (expiry timestamp).
  - Secret key: `settings.secret_key`.
  - Algorithm: `settings.ALGORITHM`.
- `get_current_user` extracts the token from the `Authorization: Bearer` header, decodes it with the same secret + algorithm, reads `sub` as the user id, and loads the user via `db.get_user_by_id`.
- `get_current_active_user` wraps `get_current_user` and enforces `is_active == True`.
- `admin_required` wraps `get_current_user` and enforces `role == UserRole.ADMIN`.

On the frontend:

- `frontend/src/auth/AuthContext.tsx` stores the JWT under `localStorage["auth_token"]` after a successful login.
- Subsequent API calls use a shared `api` client (`frontend/src/lib/apiClient.ts`) that attaches the token as an `Authorization` header when present.
- `AuthProvider` tries to fetch `/auth/me` on load when a token is present, and clears the token if the call fails.

At present there is no dedicated server-side session table or idle-time tracking. Session lifetime is governed solely by the JWT `exp` and the single `ACCESS_TOKEN_EXPIRE_MINUTES` setting.

## eBay tokens and related data

- eBay account and token data are stored in the modern Postgres/Supabase schema via SQLAlchemy models (see `backend/app/models_sqlalchemy/models.py`):
  - `EbayAccount` – account identity and metadata.
  - `EbayToken` – persistent access/refresh tokens and expiry timestamps per account.
  - `EbayAuthorization` – granted scopes per account.
- Admin endpoints under `/api/admin` (e.g. `/ebay/tokens/info`, `/ebay/tokens/refresh`) use these models to inspect and manage tokens. Sensitive values are always masked in responses and logs (only lengths and timestamps are exposed).

## Existing logging

### Application logs

- The authentication endpoints use `app.utils.logger` to log:
  - Registration attempts and successes.
  - Login attempts, failures, and successes (with email and request id, but no plaintext passwords).
  - Password-reset token creation and confirmation.
- Database errors and unexpected exceptions during login are logged with full tracebacks and surfaced to the client as 500 responses with generic messages.

### Structured DB logs (non-security-specific)

- Sync and worker activity is tracked via:
  - `sync_logs` and `sync_event_logs` tables (`SyncLog`, `SyncEventLog` models) with rich metadata for ingestion workers.
  - `ebay_connect_logs` for sensitive token-related operations, with masking applied to token values.
- eBay webhook and polling events are tracked in `ebay_events` and surfaced via the Notifications Center (`/api/admin/ebay-events`, `/api/admin/notifications/status`, etc.).

## Gaps relative to the planned Security Center

Based on the current state, the following gaps exist and will be addressed by the new Security Center work:

- No dedicated security events table for login/security-related actions (login_success/login_failed/login_blocked/settings_changed/etc.).
- No persistent login-attempt tracking per user/IP beyond basic logger messages.
- No brute-force protection or progressive delays between login attempts.
- No configurable session TTL or idle-timeout policy in the database (only a static `ACCESS_TOKEN_EXPIRE_MINUTES` setting).
- No central Security Center UI in the admin panel to:
  - Inspect login attempts and security events with filters and export.
  - See a "terminal" view of raw security events.
  - Adjust brute-force, session, and alert settings at runtime.

These gaps motivate the introduction of dedicated `security_events`, `login_attempts`, and `security_settings` tables, a backend security service for enforcement, and a new Security Center section in the admin UI.
