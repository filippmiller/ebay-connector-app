# eBay OAuth token refresh – unified flow

This document describes how eBay OAuth token refresh works end-to-end in the
multi-account connector, and how the background worker and admin debug tools
share the same logic.

## Storage and encryption

Per-account tokens are stored in the `ebay_tokens` table and mapped via
`EbayToken` in `backend/app/models_sqlalchemy/models.py`:

- Physical columns: `_access_token` and `_refresh_token` (encrypted blobs).
- Properties:
  - `EbayToken.access_token`
  - `EbayToken.refresh_token`

Both properties use the shared AES‑GCM helpers in `app.utils.crypto` to encrypt
on write and decrypt on read:

- Values stored in the DB use the prefix `ENC:v1:` and a base64 payload.
- `crypto.decrypt(value)` is **backwards compatible**: if the value does not
  start with `ENC:v1:`, it is returned as‑is.

Everywhere else in the code we work with the **plain** eBay tokens; encryption
is an implementation detail of the model.

## Low‑level HTTP helper

`EbayService._build_refresh_token_request_components` in
`backend/app/services/ebay.py` is the single place that prepares the
`refresh_token` HTTP call:

- Validates that `EBAY_CLIENT_ID` and `EBAY_CERT_ID` are configured.
- Builds the correct token URL for the active environment.
- Constructs headers:
  - `Content-Type: application/x-www-form-urlencoded`
  - `Authorization: Basic <base64(client_id:cert_id)>`
- Constructs the form body:
  - `grant_type=refresh_token`
  - `refresh_token=<plain eBay refresh token>`
- Produces a masked `request_payload` for connect logs.

**Critical safety:** if the input `refresh_token` **starts with
`"ENC:v1:"`**, the helper will attempt to decrypt it using `crypto.decrypt`.
If decryption fails or still returns an `ENC:v1:` string, the helper:

- Logs an error.
- Raises `HTTPException(500, "Internal error: refresh token decryption failed")`.
- **Never sends** the encrypted blob to eBay.

This guarantees that the Identity API always receives the plain token of the
form `v^1.1#i^1#...`, not an `ENC:...` placeholder.

## Central orchestrator: `refresh_access_token_for_account`

The high‑level refresh logic lives in
`backend/app/services/ebay_token_refresh_service.py` as
`refresh_access_token_for_account`:

```python
async def refresh_access_token_for_account(
    db: Session,
    account: EbayAccount,
    *,
    triggered_by: str = "scheduled",
    persist: bool = True,
    capture_http: bool = False,
) -> dict:
    ...
```

Responsibilities:

1. **Load token** – fetch `EbayToken` for the account and read
   `token.refresh_token` (plain string via model property).
2. **Create log row** – insert `EbayTokenRefreshLog` with:
   - `ebay_account_id`
   - `started_at`
   - `old_expires_at`
   - `triggered_by` (e.g. `"scheduled"`, `"debug"`, `"admin"`, `"manual"`).
3. **Handle missing token** – if there is no row or no refresh token:
   - Mark log as `success=False`, `error_code="NO_REFRESH_TOKEN"`.
   - Set `EbayToken.refresh_error` to a human‑readable message.
   - Commit and return `{"success": False, "error": "no_refresh_token", ...}`.
4. **Call eBay**:
   - When `capture_http=False` (worker/admin):
     - Call `EbayService.refresh_access_token` which:
       - Uses `_build_refresh_token_request_components` (and thus the
         decryption guard).
       - Performs the HTTP POST.
       - Returns an `EbayTokenResponse` with `access_token`, `expires_in`,
         and optional `refresh_token` / `refresh_token_expires_in`.
   - When `capture_http=True` (debug):
     - Call `EbayService.debug_refresh_access_token_http` which:
       - Uses the same `_build_refresh_token_request_components`.
       - Performs the HTTP POST.
       - Returns a structured object with
         `environment`, `success`, `error`, `error_description`, `request`,
         and `response` (body as text).
5. **Persist new tokens (optional)** – when `persist=True` and the HTTP call
   succeeds, `refresh_access_token_for_account` will:
   - Parse the Identity API JSON body (for debug) or use `EbayTokenResponse`
     (for worker/admin).
   - Call `EbayAccountService.save_tokens` with:
     - `access_token`
     - `refresh_token` (if eBay rotated it, otherwise keep the old one)
     - `expires_in`
     - Optional `refresh_token_expires_in`.
   - Reload `EbayToken` to get the updated `expires_at`.
6. **Update log and error fields**:
   - On **success**:
     - Set `EbayToken.refresh_error = None`.
     - Mark `EbayTokenRefreshLog.success = True`.
     - Set `finished_at` and `new_expires_at` (prefer the DB value; fallback
       to `finished_at + expires_in`).
   - On **failure** (HTTPException or generic exception):
     - Set `EbayToken.refresh_error` to a short message.
     - Mark `EbayTokenRefreshLog.success = False`.
     - Fill `error_code` (`HTTP status`, `debug_error`, `invalid_response`,
       or `exception`) and `error_message`.

Return value is a small dict:

- `success: bool`
- `error: Optional[str]`
- `error_message: Optional[str]`
- `http: Optional[dict]` – present only when `capture_http=True`.

## Who calls the orchestrator

All high‑level refresh flows now use
`refresh_access_token_for_account`:

- **Background worker** –
  `backend/app/workers/token_refresh_worker.py::refresh_expiring_tokens`:
  - Loops accounts needing refresh.
  - For each, calls:

    ```python
    result = await refresh_access_token_for_account(
        db,
        account,
        triggered_by="scheduled",
        persist=True,
        capture_http=False,
    )
    ```

  - Increments `refreshed_count` on success and collects a structured error
    list on failures.

- **Admin debug endpoint** –
  `POST /api/admin/ebay/token/refresh-debug` in
  `backend/app/routers/admin.py`:

  - Validates that the requested `EbayAccount` belongs to the current admin
    user and that a token exists.
  - Calls:

    ```python
    result = await refresh_access_token_for_account(
        db,
        account,
        triggered_by="debug",
        persist=True,
        capture_http=True,
    )
    ```

  - Extracts `debug_payload = result["http"]` and returns to the frontend:
    - `environment`
    - `success`
    - `error`
    - `error_description`
    - `request` (method, url, headers, body)
    - `response` (status_code, reason, headers, body)

  This is what powers the **“Refresh (debug)”** modal in the Admin Workers UI.

- **Admin production token refresh** –
  `POST /api/admin/ebay/tokens/refresh` (production only, feature‑gated by
  `FEATURE_TOKEN_INFO`):

  - Finds the latest active `EbayAccount` for the admin user.
  - Ensures a refresh token exists.
  - Calls `refresh_access_token_for_account` with
    `triggered_by="admin"`, `capture_http=False`.
  - Logs a `token_refreshed` or `token_refresh_failed` event to
    `ebay_connect_logs`.
  - Returns the new `access_expires_at` and `access_ttl_sec`.

- **Per‑user manual refresh** –
  `POST /ebay-accounts/{account_id}/refresh-token` in
  `backend/app/routers/ebay_accounts.py`:

  - Validates ownership of the account.
  - Ensures a refresh token exists.
  - Calls `refresh_access_token_for_account` with
    `triggered_by="manual"`, `capture_http=False`.

## UI: how status is computed and displayed

The Admin Workers page uses two main endpoints:

- `/api/admin/ebay/tokens/status` – implemented in `admin.py`, it combines
  `EbayAccount`, `EbayToken`, and recent `EbayTokenRefreshLog` rows into a
  per‑account status structure:
  - `expires_at`, `expires_in_seconds`
  - `last_refresh_at`, `last_refresh_success`, `last_refresh_error`
  - `refresh_failures_in_row` – computed from the last 10 log entries
    (consecutive failures until the first success).
- `/api/admin/ebay/tokens/refresh/log` – returns the detailed history of
  `EbayTokenRefreshLog` rows for one account, with human‑readable timestamps.

The **“Per-account token status”** table shows:

- `Expires in` – derived from `expires_in_seconds`.
- `Last refresh` – `last_refresh_at` with relative time and `last_refresh_error`
  when present.
- `Failures in row` – derived from consecutive failed
  `EbayTokenRefreshLog` entries.

Because all refresh flows now go through
`refresh_access_token_for_account`, a successful refresh by either the
background worker **or** the debug/admin endpoints will:

- Update `EbayToken.expires_at` and token values.
- Clear `EbayToken.refresh_error`.
- Insert a successful `EbayTokenRefreshLog` row with `new_expires_at`.

On the next `/api/admin/ebay/tokens/status` fetch, the UI will show:

- `Expires in` reset close to the full TTL (typically ~7200s for 2h tokens).
- `Failures in row = 0`.
- Most recent log entry as `success`.

## How to verify behaviour

For a given account:

1. **Debug refresh with HTTP trace** (Admin Workers UI):
   - Open the Admin Workers page.
   - In the “Per-account token status” table, click **“Refresh (debug)”**.
   - Inspect the modal:
     - The HTTP **request** body must contain
       `grant_type=refresh_token&refresh_token=v%5E1.1%23...`.
     - There must be **no** `ENC:v1:` anywhere in the request.
     - On success, the response body should include `access_token` and
       `expires_in`.

2. **Check DB‑backed status**:
   - After a successful debug refresh (or a worker cycle), the same account
     row in “Per-account token status” should show:
     - `Expires in` ≈ 2 hours.
     - `Failures in row = 0`.
     - `Last refresh` updated to just now, with no error text.
   - The **Token refresh log** modal for this account should have a new
     `success` row with `triggered_by` reflecting the source
     (`scheduled`, `debug`, or `admin`).

3. **Programmatic check** (admin endpoints):
   - Call `GET /api/admin/ebay/tokens/status` and locate the entry for the
     account; verify `expires_in_seconds` and `refresh_failures_in_row`.
   - Call `GET /api/admin/ebay/tokens/refresh/log?account_id=...` and inspect
     the latest `success` entry.

If any flow ever manages to send an `ENC:...` string in the
`refresh_token` field over HTTP, this indicates a **bug**: either the
caller bypassed the model properties and passed a raw DB column, or
`crypto.decrypt` failed unexpectedly. `_build_refresh_token_request_components`
now defends against this and will raise a 500 instead of contacting eBay,
so such regressions will be visible immediately in logs and the admin UI.
