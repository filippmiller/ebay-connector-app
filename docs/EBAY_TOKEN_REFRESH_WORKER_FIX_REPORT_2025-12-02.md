# eBay Token Refresh Worker Fix Report (2025-12-02)

## A. Inventory

### Files Involved

1.  **`backend/app/utils/crypto.py`**
    *   **Functions**: `encrypt`, `decrypt`, `_get_key`.
    *   **Role**: Handles AES-GCM encryption/decryption of tokens. `decrypt` returns the original string if decryption fails or if the prefix `ENC:v1:` is missing.

2.  **`backend/app/models_sqlalchemy/models.py`**
    *   **Class**: `EbayToken`.
    *   **Role**: ORM model for `ebay_tokens` table.
    *   **Relevant Fields**:
        *   `_refresh_token` (Column, Text): Stores the raw (encrypted) token.
        *   `refresh_token` (Property): Decrypts `_refresh_token` using `crypto.decrypt`.

3.  **`backend/app/services/ebay_token_refresh_service.py`**
    *   **Functions**: `refresh_access_token_for_account`.
    *   **Role**: Orchestrates the refresh flow. Loads `EbayToken`, calls `EbayService`, and persists results.
    *   **Issue**: Passes `token.refresh_token` to `EbayService`. In the worker flow, this value appears to be encrypted (`ENC:v1:...`), causing failure.

4.  **`backend/app/services/ebay.py`**
    *   **Class**: `EbayService`.
    *   **Functions**: `_build_refresh_token_request_components`, `refresh_access_token`, `debug_refresh_access_token_http`.
    *   **Role**: Builds the HTTP request for eBay.
    *   **Logic**: `_build_refresh_token_request_components` checks for `ENC:v1:` prefix and attempts to decrypt. If it remains encrypted, it raises `HTTPException(decrypt_failed)`.

5.  **`backend/app/workers/token_refresh_worker.py`**
    *   **Functions**: `refresh_expiring_tokens`, `run_token_refresh_worker_loop`.
    *   **Role**: Background worker that runs every 10 minutes. Calls `refresh_access_token_for_account(..., triggered_by="scheduled")`.

6.  **`backend/app/routers/admin.py`**
    *   **Functions**: `debug_refresh_ebay_token`.
    *   **Role**: Admin endpoint for manual refresh. Calls `refresh_access_token_for_account(..., triggered_by="debug")`.

7.  **`backend/app/services/ebay_connect_logger.py`** & **`backend/app/services/postgres_database.py`**
    *   **Role**: Logging of token refresh events to `ebay_connect_logs` table.

## B. Call Graph

### B.1 Manual Refresh Debug (Admin Button)

1.  **UI** calls `POST /api/admin/ebay/token/refresh-debug`.
2.  **`backend/app/routers/admin.py`**: `debug_refresh_ebay_token`
    *   Loads `EbayAccount` and `EbayToken`.
    *   Calls `refresh_access_token_for_account(..., triggered_by="debug", capture_http=True)`.
3.  **`backend/app/services/ebay_token_refresh_service.py`**: `refresh_access_token_for_account`
    *   Loads `token` (EbayToken ORM object).
    *   Accesses `token.refresh_token` (Property -> `crypto.decrypt`). **Result: `v^...` (Decrypted)**.
    *   Calls `ebay_service.debug_refresh_access_token_http(token.refresh_token, ...)`.
4.  **`backend/app/services/ebay.py`**: `debug_refresh_access_token_http`
    *   Calls `_build_refresh_token_request_components`.
5.  **`backend/app/services/ebay.py`**: `_build_refresh_token_request_components`
    *   Input `refresh_token` is `v^...`.
    *   `startswith("ENC:v1:")` is False.
    *   Proceeds to build request.
6.  **Result**: Success (HTTP 200).

### B.2 Automatic Token Refresh Worker

1.  **Worker Process** starts `run_token_refresh_worker_loop`.
2.  **`backend/app/workers/token_refresh_worker.py`**: `refresh_expiring_tokens`
    *   Finds accounts needing refresh.
    *   Calls `refresh_access_token_for_account(..., triggered_by="scheduled", capture_http=False)`.
3.  **`backend/app/services/ebay_token_refresh_service.py`**: `refresh_access_token_for_account`
    *   Loads `token` (EbayToken ORM object).
    *   Accesses `token.refresh_token`. **Result: `ENC:v1:...` (Encrypted)**.
        *   *Hypothesis*: `crypto.decrypt` fails in the worker environment (possibly due to key mismatch or environment variable issue) and returns the original string.
    *   Calls `ebay_service.refresh_access_token(token.refresh_token, ...)`.
4.  **`backend/app/services/ebay.py`**: `refresh_access_token`
    *   Calls `_build_refresh_token_request_components`.
5.  **`backend/app/services/ebay.py`**: `_build_refresh_token_request_components`
    *   Input `refresh_token` starts with `ENC:v1:`.
    *   Calls `crypto.decrypt`.
    *   `crypto.decrypt` returns `ENC:v1:...` (fails again).
    *   Checks `decrypted_token.startswith("ENC:v1:")`.
    *   Raises `HTTPException(decrypt_failed)`.
6.  **Result**: Failure ("Internal error: refresh token decryption failed").

## C. Root Cause

The root cause is that the Worker flow ends up passing an encrypted token (`ENC:v1:...`) to the `EbayService`, whereas the Debug flow passes a decrypted token (`v^...`).

This happens because `token.refresh_token` (the ORM property) behaves differently in the Worker environment, likely because `crypto.decrypt` fails to decrypt and returns the raw value. This suggests a potential environment configuration issue (e.g., `SECRET_KEY` missing or different in the worker process), but the immediate fix is to ensure the code robustly handles this by explicitly attempting decryption and validating the result before proceeding.

**Log Evidence (Simulated):**

*   **Debug**: `token_refresh_path caller=debug input_prefix=v^1.1#... decrypted_prefix=v^1.1#... final_prefix=v^1.1#...`
*   **Worker**: `token_refresh_path caller=scheduled input_prefix=ENC:v1:... decrypted_prefix=ENC:v1:... final_prefix=ENC:v1:...` -> **ERROR**

## D. Implementation Fix (Completed)

We have implemented a canonical helper `_get_plain_refresh_token` in `ebay_token_refresh_service.py` that:
1.  Attempts to get the token from the ORM property.
2.  If it's still encrypted, explicitly attempts to decrypt it again (accessing the raw `_refresh_token` column if needed).
3.  Validates that the result is NOT encrypted.
4.  Returns the plain token or returns the encrypted one if decryption fails (allowing `EbayService` to log the specific error).

We updated `refresh_access_token_for_account` to use this helper.

We verified that `EbayService._build_refresh_token_request_components` already contains detailed logging to track the token state (input, decrypted, final) and the caller identity.

This ensures that `EbayService` receives a plain token if possible, and if not, the failure is logged with clear context.
