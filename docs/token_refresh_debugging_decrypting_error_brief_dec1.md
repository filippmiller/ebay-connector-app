# Token refresh debugging & decrypting error brief (Dec 1)

## Context

On Dec 1, 2025 we investigated a production incident where the eBay token refresh worker was failing for some accounts while the manual **Refresh (debug)** flow in the Admin UI continued to succeed.

Key facts:

- Manual **Refresh (debug)** was successfully refreshing tokens using a plain eBay refresh token that started with `v^1.1#…`.
- The scheduled **token_refresh_worker** was intermittently failing with:
  - HTTP 400 `invalid_grant` from eBay, or
  - Internal 500 errors with message `Internal error: refresh token decryption failed`.
- HTTP logs for failing worker runs showed `"refresh_token": "ENC:v1:..."` in the request body, which is our own encrypted at-rest format, not a valid eBay token.

## Root cause

### Storage vs. runtime token formats

- The `ebay_tokens` table stores encrypted access and refresh tokens using the `EbayToken` ORM model.
- The physical DB column is `_refresh_token`, which holds encrypted blobs with an `ENC:v1:...` prefix.
- The public property `EbayToken.refresh_token` decrypts `_refresh_token` on read and returns the plain eBay token (starting with `v^...`).
- eBay **never** returns `ENC:...`; that prefix is strictly internal to our crypto helper.

### Divergence between worker and debug flows

Both the worker and the manual debug endpoint ultimately call `EbayService`:

- Worker/admin flow:
  - `token_refresh_worker.refresh_expiring_tokens()` →
  - `refresh_access_token_for_account(..., capture_http=False, triggered_by="scheduled"|"admin"|"manual")` →
  - `EbayService.refresh_access_token(token.refresh_token, ...)`.

- Debug flow:
  - `/api/admin/ebay/token/refresh-debug` →
  - `refresh_access_token_for_account(..., capture_http=True, triggered_by="debug")` →
  - `EbayService.debug_refresh_access_token_http(token.refresh_token, ...)`.

In theory both flows should pass the same `token.refresh_token` property into a common request-builder, which then posts to `https://api.ebay.com/identity/v1/oauth2/token`. In practice:

- Before Dec 1, `_build_refresh_token_request_components` attempted to detect `ENC:v1:` and decrypt it, but logs showed some worker requests where `ENC:v1:...` still leaked into the outgoing HTTP body.
- This implied that at least some paths were either:
  - passing an already-encrypted value into the builder, or
  - not validating the final token before sending the request.

## Fixes implemented

### 1. Single authoritative HTTP request builder

`backend/app/services/ebay.py`:

- `_build_refresh_token_request_components` was strengthened and now:
  - Accepts a logical `refresh_token` and a `caller` label (`scheduled`, `admin`, `debug`, etc.).
  - If it sees `ENC:v1:` prefix, it **always** attempts a single decrypt via `crypto.decrypt`.
  - After decryption, it enforces three invariants:
    - The token is a non-empty string.
    - It no longer starts with `ENC:v1:`.
    - It looks like an eBay token (by default, starts with `v^`).
  - If any of these checks fail, it raises an `HTTPException` with:
    - `status_code = 500` and
    - `detail = {"code": "decrypt_failed", "message": "..."}`.
  - It logs a diagnostic line with masked prefixes:
    - `input_prefix` (original argument),
    - `decrypted_prefix`,
    - `final_prefix` (the token actually used in the HTTP body),
    - tagged with the `caller` label.
  - It constructs headers and `data = {"grant_type": "refresh_token", "refresh_token": <plain eBay token>}` and returns these along with a `request_payload` copy used by connect-logs.

All eBay Identity refresh HTTP calls now go through this helper:

- `EbayService.refresh_access_token` for worker/admin.
- `EbayService.debug_refresh_access_token_http` for manual debug.

### 2. Strict fail-safe: never send ENC: to eBay

Because of the above invariants, any `ENC:v1:` that reaches `_build_refresh_token_request_components` is either:

- Successfully decrypted once to a plain `v^...` token, or
- Causes an immediate `decrypt_failed` HTTPException **before** any outbound HTTP is made.

Net effect:

- No new requests to `https://api.ebay.com/identity/v1/oauth2/token` will ever contain `refresh_token = "ENC:..."`.

### 3. Propagating decrypt_failed to worker & UI

`backend/app/services/ebay_token_refresh_service.py`:

- `refresh_access_token_for_account` catches `HTTPException` from `EbayService.refresh_access_token`.
- If `exc.detail` is a dict with `code == "decrypt_failed"`:
  - It sets `EbayToken.refresh_error = f"decrypt_failed: {msg}"` for that account.
  - It updates the corresponding `EbayTokenRefreshLog` row with:
    - `success = False`,
    - `error_code = "decrypt_failed"`,
    - `error_message = <message>`.
  - It returns `{"success": False, "error": "decrypt_failed", "error_message": msg}` to the caller.
- For other HTTP errors (non-200 responses from eBay, network errors), it preserves previous behavior but still records a structured error.

This gives the Admin UI a deterministic way to surface "needs reconnect" state via the `refresh_error` field and refresh log rows.

### 4. Caller/source tagging for diagnostics

To debug and prove parity between flows:

- `EbayService.refresh_access_token` now accepts a `source` parameter and passes it into `ebay_connect_logger.log_event` calls.
- `refresh_access_token_for_account` calls:
  - `refresh_access_token(..., source=triggered_by)` for worker/admin.
  - `debug_refresh_access_token_http(..., ...)` and then logs a `token_refresh_debug` connect-log entry with `source=triggered_by` for the debug flow.
- `EbayConnectLogger.log_event` was extended to accept and store a `source` field, so connect logs now include whether a given refresh came from:
  - `scheduled` (worker),
  - `admin`,
  - `manual`,
  - `debug`, etc.

Combined with the `token_refresh_path` diagnostics line (prefix logging in `_build_refresh_token_request_components`), this allows us to:

- Confirm that for a given account, both debug and worker use **identical** `final_prefix` values that start with `v^`.
- Quickly spot any future regressions if a caller starts feeding `ENC:` values into the builder.

## Verification steps (Dec 1)

To validate the fix, we followed this procedure for a known-good account:

1. Run **Refresh (debug)** from the Admin UI.
2. Inspect backend logs for a line similar to:

   ```
   token_refresh_path caller=admin_debug input_prefix=v^1.1#... decrypted_prefix=v^1.1#... final_prefix=v^1.1#...
   ```

3. Wait for the scheduled token refresh worker to run for the same account (or trigger a one-off cycle).
4. Inspect logs for:

   ```
   token_refresh_path caller=scheduled input_prefix=v^1.1#... decrypted_prefix=v^1.1#... final_prefix=v^1.1#...
   ```

5. Confirm that `final_prefix` matches between admin_debug and scheduled, and that it always starts with `v^` (never `ENC:`).
6. Verify, via the Token HTTP logs modal backed by connect-logs, that:
   - Request bodies for both flows have `refresh_token` values whose masked prefix matches `v^...`.
   - No new logs show `refresh_token` starting with `ENC:` after the deployment of this fix.

For accounts with corrupted or legacy-encrypted tokens that cannot be decrypted, we now see:

- Worker entries with `error_code = 'decrypt_failed'` and `token.refresh_error` set accordingly.
- No outbound `/identity/v1/oauth2/token` calls for those accounts.
- Clear log lines instructing that the account requires a full reconnect.

## Follow-ups

- Update the Admin UI to surface `decrypt_failed` as a clear "Needs reconnect" status in the per-account token status table.
- Optionally add a one-click "Reconnect" flow that guides the user through the OAuth process when `refresh_error` starts with `decrypt_failed:`.
- Keep the `token_refresh_path` and connect-log diagnostics in place for some time to monitor for regressions.
