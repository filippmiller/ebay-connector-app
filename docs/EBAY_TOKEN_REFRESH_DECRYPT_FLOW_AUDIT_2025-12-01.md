# eBay Token Refresh Decrypt Flow Audit (2025-12-01)

## Executive Summary

This audit maps the full encrypt/decrypt pipeline and the two token refresh paths for eBay accounts – (A) **manual "Refresh (debug)"** in the Admin Workers UI and (B) the **scheduled token refresh worker** – as implemented in `C:\dev\ebay-connector-app`.

**Key Finding:** At the code level, both flows are now routed through a single canonical helper, `refresh_access_token_for_account` (`backend/app/services/ebay_token_refresh_service.py`), which always reads the refresh token via the `EbayToken.refresh_token` ORM property (which decrypts the encrypted `_refresh_token` column using `app.utils.crypto.decrypt`) and then calls the shared request builder `_build_refresh_token_request_components` (`backend/app/services/ebay.py`). That builder enforces a strict invariant: if a value still looks like an encrypted `ENC:v1:` blob *after* a decrypt attempt, or does not look like a `v^...` eBay refresh token, it raises a deterministic `HTTPException` with `detail.code = "decrypt_failed"` and never calls eBay.

The "Refresh token still encrypted after decrypt attempt; caller=scheduled. Account requires reconnect." error is produced *only* by this builder when it sees a string that still starts with `ENC:v1:` after calling `crypto.decrypt`. In the worker flow, that error is then converted into `EbayToken.refresh_error`, a failed `EbayTokenRefreshLog` row, and a synthetic `EbayConnectLog` entry whose request body contains `"refresh_token": "<decrypt_failed>"`, which is exactly what the unified Token Refresh Terminal shows. In contrast, the Debug flow uses the same builder and the same ORM property, but captures the real HTTP request/response and (in the healthy cases observed by the user) sees a decrypted `v^...` token, so the builder never reaches the `still encrypted` branch.

This means the **code paths themselves are unified**; the observed divergence (Debug succeeds with a `v^...` token, Worker fails with `still encrypted` and `<decrypt_failed>`) can only occur when the *effective inputs to the builder* differ between processes – for example, if the background worker process derives a different AES key from `settings.secret_key` than the main API process, causing `crypto.decrypt` to fail and return the original `ENC:v1:...` value.

**Primary Hypothesis:** The most likely root cause is a **SECRET_KEY environment variable mismatch** between the main API service and the token refresh worker service/process, resulting in different AES-GCM decryption keys.

---

## File Inventory (Crypto + Token Refresh)

Below is a focused inventory of all modules that participate in token encryption/decryption, eBay token refresh, worker scheduling, admin/debug endpoints, token terminal logs, and supporting scripts/tests.

| ID  | File path                                                        | Role in decrypt/encrypt & refresh flows |
|-----|------------------------------------------------------------------|-----------------------------------------|
| B1  | `backend/app/utils/crypto.py`                                   | AES‑GCM encrypt/decrypt helpers with versioned `ENC:v1:` prefix; `decrypt` is backwards‑compatible and returns the original string on failure, which is crucial for understanding the `still encrypted after decrypt attempt` error. |
| B2a | `backend/app/models_sqlalchemy/models.py` (`EbayAccount`)  | Represents an eBay account, including `org_id`, `ebay_user_id`, `house_name`; worker and admin routes load accounts by id/org to resolve tenant context and `user_id` for connect logs. |
| B2b | `backend/app/models_sqlalchemy/models.py` (`EbayToken`)    | Stores per‑account tokens in encrypted columns `_access_token` and `_refresh_token`; the `refresh_token` property decrypts `_refresh_token` via `crypto.decrypt` and is the *only* way worker/debug access the refresh token. Also stores `expires_at`, `refresh_expires_at`, `last_refreshed_at`, and `refresh_error`. |
| B2c | `backend/app/models_sqlalchemy/ebay_workers.py` (`EbayTokenRefreshLog`) | Per‑attempt token refresh log: `started_at`, `finished_at`, `success`, `error_code`, `error_message`, `old_expires_at`, `new_expires_at`, `triggered_by`. Used by Admin UI to show "Failures in row" and recent history. |
| B2d | `backend/app/models_sqlalchemy/ebay_workers.py` (`BackgroundWorker`) | Tracks background worker heartbeat and run statistics (`worker_name="token_refresh_worker"`, `last_started_at`, `last_finished_at`, `last_status`, `runs_ok_in_row`, etc.) for displaying worker health. |
| B3a | `backend/app/services/ebay.py` (`_build_refresh_token_request_components`) | Canonical request builder for refresh‑token grant: decrypts `ENC:v1:` values via `crypto.decrypt`, enforces that final token starts with `v^`, logs masked prefixes, and returns `(environment, headers, form_data, request_payload)` used by both `refresh_access_token` and `debug_refresh_access_token_http`. Emits the `"Refresh token still encrypted after decrypt attempt; caller=..."` error. |
| B3b | `backend/app/services/ebay.py` (`refresh_access_token`) | Worker/admin helper for token refresh: calls the builder, performs HTTP POST to `self.token_url`, logs via `ebay_logger`, and writes connect‑log entries (`action="token_refreshed"` or `"token_refresh_failed"` / `"token_refresh_error"`) when `user_id` is provided. Raises `HTTPException` on failures. |
| B3c | `backend/app/services/ebay.py` (`debug_refresh_access_token_http`) | Debug‑only helper: calls the same builder with `caller="debug"`, then performs the HTTP request and returns a structured object containing full request/response (including unmasked headers/body) for the debug modal. Does *not* write connect logs itself; the service wrapper does. |
| B4a | `backend/app/services/ebay_token_refresh_service.py` (`refresh_access_token_for_account`) | Canonical per‑account refresh helper used by *both* Debug and Worker (and admin "Refresh now"). Reads `EbayToken.refresh_token`, decides between debug vs worker paths via `capture_http`, persists tokens via `ebay_account_service.save_tokens`, writes `EbayTokenRefreshLog`, sets `EbayToken.refresh_error`, and writes connect logs (including synthetic `<decrypt_failed>` requests when the builder raises). |
| B5a | `backend/app/workers/token_refresh_worker.py`                     | Implements `refresh_expiring_tokens` (single cycle) and `run_token_refresh_worker_loop` (infinite loop every 600s). Uses `ebay_account_service.get_accounts_needing_refresh` to pick accounts and, for each, calls `refresh_access_token_for_account(..., triggered_by="scheduled", capture_http=False)`. Updates `BackgroundWorker` heartbeat and logs per‑account successes/failures. |
| B6a | `backend/app/routers/admin.py` (`/api/admin/ebay/token/refresh-debug`) | Manual Refresh Debug endpoint. Validates account ownership, checks that a refresh token exists, then calls `refresh_access_token_for_account(..., triggered_by="debug", capture_http=True)` and returns the structured HTTP payload to the frontend for rendering. |
| B6d | `backend/app/routers/admin.py` (`/api/admin/ebay/tokens/terminal-logs`) | Token Refresh Terminal backend API. Reads recent `EbayConnectLog` entries via `ebay_connect_logger.get_logs(current_user.id, env, limit)`, filters for `action in {"token_refreshed", "token_refresh_failed", "token_refresh_debug"}`, masks `refresh_token` fields in request bodies, and returns `entries` for the unified terminal (worker + debug). |
| B7a | `frontend/src/api/ebay.ts`                                       | TypeScript client for admin eBay APIs, including: `debugRefreshToken` (POST `/api/admin/ebay/token/refresh-debug`), `getAdminTokenTerminalLogs` (GET `/api/admin/ebay/tokens/terminal-logs`), `getEbayTokenStatus`, `getTokenRefreshWorkerStatus`, and `getEbayTokenRefreshLog`. |
| B7b | `frontend/src/pages/AdminWorkersPage.tsx`                        | Admin Workers page. Renders: (a) per‑account token status table with a **"Refresh (debug)"** button that calls `openTokenRefreshDebug` → `ebayApi.debugRefreshToken`, and (b) a **Token refresh terminal (worker + debug)** modal that calls `ebayApi.getAdminTokenTerminalLogs('production', ...)` and renders entries with `source` and HTTP request/response shapes. |
| B8a | `backend/tests/test_ebay_refresh_tokens.py`                      | Unit tests for `_build_refresh_token_request_components` and the canonical flows. |
| B8b | `backend/scripts/inspect_ebay_tokens.py`                         | Diagnostic script: lists all `EbayAccount` rows and prints a *masked* prefix and length of `EbayToken.refresh_token` (after ORM decrypt), plus `refresh_error` and `expires_at`. Useful for distinguishing `ENC:` vs `v^` at the ORM/property level. |

---

## Flow A – Manual Refresh Debug (Call Graph)

**Entry point:** Admin Workers UI → "Refresh (debug)" button

```
Frontend (AdminWorkersPage.tsx):
  openTokenRefreshDebug(accountId)
    → ebayApi.debugRefreshToken(accountId)
      → POST /api/admin/ebay/token/refresh-debug

Backend (admin.py):
  debug_refresh_ebay_token(...)
    → Validate account ownership (org_id check)
    → Load EbayToken
    → Call: refresh_access_token_for_account(
        db, account, 
        triggered_by="debug", 
        persist=True, 
        capture_http=True
      )

Service (ebay_token_refresh_service.py):
  refresh_access_token_for_account [Debug branch]
    → Load EbayToken from DB
    → Read token.refresh_token property
        ├─→ DECRYPT #1: crypto.decrypt(_refresh_token)
        └─→ Returns decrypted string (e.g., "v^1.1..." or "ENC:v1:..." if decrypt failed)
    → Call: ebay_service.debug_refresh_access_token_http(token.refresh_token, env)

eBay Service (ebay.py):
  debug_refresh_access_token_http(refresh_token, environment)
    → Call: _build_refresh_token_request_components(refresh_token, caller="debug")
        ├─→ If refresh_token starts with "ENC:v1:":
        │     DECRYPT #2: crypto.decrypt(refresh_token)
        ├─→ If still starts with "ENC:v1:" after decrypt:
        │     RAISE HTTPException(code="decrypt_failed", 
        │           message="Refresh token still encrypted after decrypt attempt; caller=debug...")
        └─→ If doesn't start with "v^":
              RAISE HTTPException(code="decrypt_failed", message="Token doesn't look like eBay token")
        └─→ Otherwise: return (env, headers, data, payload)
    → HTTP POST to eBay Identity API
    → Return structured { request, response, success, error }

Service (continued):
  ← On success: persist tokens, write connect log (source="debug"), update EbayTokenRefreshLog
  ← On failure: set token.refresh_error, write synthetic connect log with <decrypt_failed>
```

**Crypto touchpoints in Flow A:**
- **Decrypt #1:** ORM property `EbayToken.refresh_token` → `crypto.decrypt(_refresh_token)` using `settings.secret_key`
- **Decrypt #2:** Builder `_build_refresh_token_request_components` → `crypto.decrypt(refresh_token)` if still `ENC:v1:`

---

## Flow B – Scheduled Token Refresh Worker (Call Graph)

**Entry point:** Background worker loop (every 600s)

```
Startup (main.py):
  startup_event()
    → If DATABASE_URL contains "postgresql":
        asyncio.create_task(run_token_refresh_worker_loop())

Worker Loop (token_refresh_worker.py):
  run_token_refresh_worker_loop()
    → Infinite loop:
        refresh_expiring_tokens()
          → Get accounts needing refresh via ebay_account_service
          → For each account:
              Call: refresh_access_token_for_account(
                  db, account,
                  triggered_by="scheduled",
                  persist=True,
                  capture_http=False
              )

Service (ebay_token_refresh_service.py):
  refresh_access_token_for_account [Worker branch]
    → Load EbayToken from DB
    → Read token.refresh_token property
        ├─→ DECRYPT #1: crypto.decrypt(_refresh_token)
        └─→ Returns decrypted string (or "ENC:v1:..." if decrypt failed)
    → Call: ebay_service.refresh_access_token(
        token.refresh_token, 
        user_id=account.org_id, 
        environment=env, 
        source="scheduled"
      )

eBay Service (ebay.py):
  refresh_access_token(refresh_token, user_id, environment, source)
    → Call: _build_refresh_token_request_components(refresh_token, caller=source)
        ├─→ If refresh_token starts with "ENC:v1:":
        │     DECRYPT #2: crypto.decrypt(refresh_token)
        ├─→ If still starts with "ENC:v1:" after decrypt:
        │     RAISE HTTPException(code="decrypt_failed", 
        │           message="Refresh token still encrypted after decrypt attempt; caller=scheduled...")
        └─→ If doesn't start with "v^":
              RAISE HTTPException(code="decrypt_failed")
        └─→ Otherwise: return (env, headers, data, payload)
    → HTTP POST to eBay Identity API
    → Write connect log (source="scheduled")
    → Return EbayTokenResponse

Service (continued):
  ← On HTTPException (decrypt_failed):
      Set token.refresh_error = "decrypt_failed: ..."
      Write EbayTokenRefreshLog (error_code="decrypt_failed")
      Write synthetic connect log:
        action="token_refresh_failed"
        source="scheduled"
        request.body.refresh_token = "<decrypt_failed>"
      Return { success: False, error: "decrypt_failed", error_message: ... }

Worker (continued):
  ← Log FAILURE with error_message
  ← Update BackgroundWorker stats
```

**Crypto touchpoints in Flow B:**
- **Decrypt #1:** ORM property `EbayToken.refresh_token` → `crypto.decrypt(_refresh_token)` using `settings.secret_key`
- **Decrypt #2:** Builder `_build_refresh_token_request_components` → `crypto.decrypt(refresh_token)` if still `ENC:v1:`

---

## Flow A vs Flow B Comparison

| Aspect                      | Flow A: Debug                                                   | Flow B: Worker                                                   |
|-----------------------------|-----------------------------------------------------------------|------------------------------------------------------------------|
| Entry point                 | Admin UI button → API endpoint                                  | Background loop every 600s                                       |
| Service helper params       | `triggered_by="debug"`, `capture_http=True`                     | `triggered_by="scheduled"`, `capture_http=False`                 |
| Token source                | **Identical:** `EbayToken.refresh_token` property (decrypts `_refresh_token`) | **Identical:** `EbayToken.refresh_token` property               |
| Builder function            | **Identical:** `_build_refresh_token_request_components`        | **Identical:** `_build_refresh_token_request_components`         |
| Caller label                | `caller="debug"`                                                | `caller="scheduled"`                                             |
| eBay HTTP function          | `debug_refresh_access_token_http` (returns full request/response to UI) | `refresh_access_token` (writes connect logs directly)          |
| Connect log source          | `source="debug"`                                                | `source="scheduled"`                                             |
| Error propagation           | Returns detailed HTTP payload to UI modal; also writes synthetic connect log on decrypt_failed | Writes synthetic connect log with `<decrypt_failed>` placeholder; updates BackgroundWorker stats |

**Key insight:** The only *code* difference is the `caller` label and the HTTP wrapper function. Both flows use:
- The same DB table (`ebay_tokens`)
- The same ORM property (`EbayToken.refresh_token`)
- The same decrypt logic (`crypto.decrypt`)
- The same builder (`_build_refresh_token_request_components`)

Therefore, if Debug succeeds with `v^...` but Worker fails with `"still encrypted"`, the **runtime environment** (specifically the `settings.secret_key` used to derive the AES key) must differ between processes.

---

## Root-Cause Hypotheses

### Hypothesis 1: SECRET_KEY Mismatch Between API and Worker (PRIMARY)

**Scenario:**
- The main API service (serving the Admin UI and `/api/admin/ebay/token/refresh-debug`) runs with `settings.secret_key = X`.
- The token refresh worker process runs with `settings.secret_key = Y` (different value).
- Tokens in the `ebay_tokens` table were encrypted using key `X`.

**Consequences:**
1. **Debug flow (API process, key=X):**
   - `crypto.decrypt(_refresh_token)` successfully decrypts to `"v^1.1..."`.
   - Builder sees `"v^..."`, does NOT attempt second decrypt, proceeds to eBay API.
   - eBay returns HTTP 200.
   - Debug modal shows `refresh_token=v^1.1...`.

2. **Worker flow (worker process, key=Y):**
   - `crypto.decrypt(_refresh_token)` fails (wrong key), returns original `"ENC:v1:..."`.
   - Builder sees `"ENC:v1..."`, attempts second decrypt, still returns `"ENC:v1..."`.
   - Builder raises `HTTPException(code="decrypt_failed", message="Refresh token still encrypted after decrypt attempt; caller=scheduled...")`.
   - Service writes synthetic connect log with `refresh_token="<decrypt_failed>"`.
   - Token Refresh Terminal shows `<decrypt_failed>` in request body.

**Code support:**
- `crypto._get_key()` derives AES key solely from `settings.secret_key` via HKDF.
- `crypto.decrypt` swallows all exceptions and returns the original `ENC:v1:...` string on failure.
- `_build_refresh_token_request_components` explicitly checks for `decrypted_token.startswith("ENC:v1:")` and raises `decrypt_failed`.

**Verification steps:**
- Check environment variables for `SECRET_KEY` in both API and worker services/containers.
- Run a debug script in both processes to log `hash(settings.secret_key)` and compare.
- Run `python -m scripts.inspect_ebay_tokens` in both environments and compare masked prefixes.

### Hypothesis 2: Old Worker Code Image

**Scenario:**
- The worker service is running an older code version that predates the unified builder or uses different crypto logic.

**Assessment:**
- Less likely, because the current repository shows all paths go through the same helper and builder.
- However, deploy-time issues (stale container images) could cause this.

**Verification:**
- Check container tags, build timestamps, git commit SHAs for API vs worker services.
- Verify that both import the same version of `backend/app/services/ebay.py` and `backend/app/utils/crypto.py`.

### Hypothesis 3: Data Corruption

**Scenario:**
- Some `_refresh_token` values in the DB are corrupted or use a legacy encryption format.

**Assessment:**
- Unlikely to explain the *asymmetry* (Debug succeeds, Worker fails for same account).
- If data were corrupted, both flows would fail identically.

---

## Verification Checklist

To confirm or falsify these hypotheses in production:

1. **Single-account comparison:**
   - Pick an account that shows the divergence (e.g. `mil_243`).
   - Run Debug refresh, capture the request body from the modal → should show `refresh_token=v^...`.
   - Wait for worker cycle or trigger manually.
   - Check Token Refresh Terminal → worker entry should show `refresh_token="<decrypt_failed>"` if SECRET_KEY mismatch exists.

2. **SECRET_KEY audit:**
   - Inspect environment variables for API and worker services (Railway/local config).
   - Ensure `SECRET_KEY` is identical in both.
   - If separate services, confirm they're reading from the same env var source.

3. **ORM-level token inspection:**
   - Run `python -m scripts.inspect_ebay_tokens` in both API and worker environments (if separate).
   - Compare `stored_prefix` for the same account in both outputs.
   - If API shows `v^...` and worker shows `ENC:...`, that confirms different decrypt keys.

4. **Connect logs inspection:**
   - Open Token Refresh Terminal in Admin UI.
   - Filter for recent entries with `source="scheduled"` and `source="debug"`.
   - For failing worker entries, check `request.body.refresh_token` → should be `"<decrypt_failed>"`.
   - For successful debug entries, check `request.body.refresh_token` → should show masked `v^` prefix.

5. **Code version verification:**
   - Check git commit SHA or container image tags for API and worker services.
   - Confirm both are running the same codebase version.

---

## Summary of Findings

1. **Code paths are unified:** Both Debug and Worker use the same ORM property (`EbayToken.refresh_token`), the same decrypt function (`crypto.decrypt`), and the same request builder (`_build_refresh_token_request_components`).

2. **Error message is deterministic:** The `"Refresh token still encrypted after decrypt attempt; caller=scheduled"` error can ONLY occur when:
   - The ORM property returns a string starting with `ENC:v1:` (i.e., `crypto.decrypt` failed and returned the original ciphertext), AND
   - The builder's second decrypt attempt also fails.

3. **Observed asymmetry requires environment difference:** Since Debug succeeds with `v^...` for accounts where Worker fails with `still encrypted`, the two processes must be using different AES keys derived from different `settings.secret_key` values.

4. **Primary root cause:** **SECRET_KEY environment variable mismatch** between API and worker services/processes.

5. **Verification required:** The human operator should:
   - Audit environment variables for SECRET_KEY in both services.
   - Run `inspect_ebay_tokens` script in both environments if separate.
   - Confirm container/code versions match.
   - Test single account end-to-end (Debug + Worker cycle + Terminal inspection).

---

## Recommended Next Steps

1. **Immediate:** Verify and align `SECRET_KEY` environment variable across all services (API, worker).

2. **Short-term:** Run diagnostic scripts (`inspect_ebay_tokens`, Token Refresh Terminal) to confirm all accounts now decrypt correctly in both flows.

3. **Medium-term:** Consider adding runtime checks or startup validation that logs a hash of `settings.secret_key` in both API and worker processes, with alerts if they diverge.

4. **Long-term:** Add integration tests that validate token encrypt/decrypt round-trip behavior using the actual config system.

---

**Document prepared:** 2025-12-01  
**Repository:** `C:\dev\ebay-connector-app`  
**Prepared by:** Warp AI Agent
