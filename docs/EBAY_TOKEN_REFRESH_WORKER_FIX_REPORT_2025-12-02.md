# eBay Token Refresh Worker Fix Report (2025-12-02)

## A. Inventory — Code Involved

The following files participate in the eBay token refresh flow:

| File | Role | Relevant Functions |
| :--- | :--- | :--- |
| `backend/app/utils/crypto.py` | **Encryption/Decryption**. Derives key from `settings.secret_key`. Handles AES-GCM decryption. | `_get_key`, `decrypt`, `encrypt` |
| `backend/app/models_sqlalchemy/models.py` | **Data Model**. Defines `EbayToken` and its `refresh_token` property which calls `crypto.decrypt`. | `EbayToken`, `EbayToken.refresh_token` (property) |
| `backend/app/services/ebay_token_refresh_service.py` | **Orchestrator**. Shared helper for both Debug and Worker flows. Loads token, decrypts, calls eBay service, persists results. | `refresh_access_token_for_account`, `_get_plain_refresh_token` |
| `backend/app/services/ebay.py` | **eBay API Client**. Builds the actual HTTP request. Contains safety checks for `ENC:` prefix. | `_build_refresh_token_request_components`, `debug_refresh_access_token_http`, `refresh_access_token` |
| `backend/app/workers/token_refresh_worker.py` | **Worker Entrypoint**. Runs the scheduled loop. Calls the orchestrator. | `run_token_refresh_worker_loop`, `refresh_expiring_tokens` |
| `backend/app/routers/admin.py` | **Debug Entrypoint**. Admin API route. Calls the orchestrator. | `debug_refresh_ebay_token` |
| `backend/app/services/ebay_connect_logger.py` | **Logging**. Logs structured events to `ebay_connect_logs` table. | `log_event` |
| `backend/app/config.py` | **Configuration**. Loads `JWT_SECRET` / `SECRET_KEY` from environment. | `Settings.secret_key` |

## B. Call Graph — Debug vs Worker

### B.1 Manual Refresh Debug (Admin Button)

1.  **Entry:** `POST /api/admin/ebay/token/refresh-debug` (`backend/app/routers/admin.py`)
2.  **Orchestrator:** Calls `refresh_access_token_for_account(..., triggered_by="debug", capture_http=True)` in `ebay_token_refresh_service.py`.
3.  **Decryption:** Calls `_get_plain_refresh_token(token)`.
    *   Accesses `token.refresh_token` (ORM property).
    *   Calls `crypto.decrypt(enc_value)`.
    *   **Result:** `v^1.1...` (Decrypted successfully because Admin API has correct `JWT_SECRET`).
4.  **eBay Call:** Calls `ebay_service.debug_refresh_access_token_http(plain_token, ...)`.
5.  **Request Build:** `_build_refresh_token_request_components` receives `v^1.1...`.
    *   Safety check `startswith("ENC:")` passes (it's not encrypted).
    *   Builds HTTP request.
6.  **Execution:** Sends request to eBay. **Success (200 OK)**.

### B.2 Automatic Token Refresh Worker

1.  **Entry:** `run_token_refresh_worker_loop` -> `refresh_expiring_tokens` (`backend/app/workers/token_refresh_worker.py`).
2.  **Orchestrator:** Calls `refresh_access_token_for_account(..., triggered_by="scheduled", capture_http=False)` in `ebay_token_refresh_service.py`.
3.  **Decryption:** Calls `_get_plain_refresh_token(token)`.
    *   Accesses `token.refresh_token` (ORM property).
    *   Calls `crypto.decrypt(enc_value)`.
    *   **Result:** `ENC:v1:...` (**Decryption FAILED** because Worker process likely has wrong/missing `JWT_SECRET`. `crypto.decrypt` returns original input on failure).
4.  **eBay Call:** Calls `ebay_service.refresh_access_token(plain_token, ...)`.
    *   **Input:** `ENC:v1:...` (Still encrypted).
5.  **Request Build:** `_build_refresh_token_request_components` receives `ENC:v1:...`.
    *   Safety check `startswith("ENC:")` triggers.
    *   Attempts `crypto.decrypt` again (fails again).
    *   **Error:** Raises `HTTPException: Refresh token still encrypted after decrypt attempt`.
6.  **Result:** **Failure**.

## C. Root Cause Analysis

The code paths for Debug and Worker are **identical** up to the point of decryption. They use the same functions and the same database rows.

*   **Debug Flow (Web Service):** `crypto.decrypt` succeeds.
*   **Worker Flow (Worker Service):** `crypto.decrypt` fails and returns the original `ENC:` string.

**Why?**
`crypto.decrypt` relies on `settings.secret_key`, which is derived from the `JWT_SECRET` environment variable.
If the **Worker Service** in Railway does not have the *exact same* `JWT_SECRET` as the **Web Service**, it will generate a different decryption key. Attempting to decrypt a token encrypted by the Web Service will fail (invalid tag/signature), and `crypto.decrypt` will return the original ciphertext.

**Conclusion:** The root cause is a **Configuration Mismatch** in Railway. The Worker Service is missing the correct `JWT_SECRET`.

## D. Implementation Fix

We will add a "Fail Fast" check in `refresh_access_token_for_account` to explicitly catch the `ENC:` prefix immediately after retrieval, ensuring we never pass an encrypted token to the `ebay_service`.

### Changes to `backend/app/services/ebay_token_refresh_service.py`:

1.  In `refresh_access_token_for_account`, after calling `_get_plain_refresh_token`:
2.  Check if `plain_refresh_token.startswith("ENC:")`.
3.  If so, log a specific error ("Decryption failed - check Worker JWT_SECRET") and return failure immediately.

## E. Logging & Terminal

*   **Source Labeling:** The code already passes `triggered_by` ("debug" or "scheduled") to `ebay_connect_logger`.
*   **Terminal View:** The frontend terminal already filters/displays these logs.
*   **Verification:** Once the Env Var is fixed, we expect to see `source=scheduled` logs with `refresh_token=v^...` in the terminal.

## F. Verification Checklist (To be performed by User)

1.  [ ] **Railway Config:** Copy `JWT_SECRET` from Web Service to Worker Service.
2.  [ ] **Redeploy:** Redeploy the Worker Service.
3.  [ ] **Verify:** Check Token Refresh Terminal for `source=scheduled` entries with `v^...` prefix.

