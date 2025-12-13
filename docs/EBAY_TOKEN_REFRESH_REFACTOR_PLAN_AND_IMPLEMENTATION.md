# eBay Token Refresh – Problem Analysis, Plan, and Implementation Outline (Dec 1, 2025)

## 1. Problems as observed

This section restates the concrete problems based on current production behaviour and screenshots.

### 1.1 Manual Refresh (debug) not appearing in unified terminal

Symptoms:

- On **Admin → Workers**, the **Token refresh terminal (worker + debug)** modal shows ~70–80 historical entries.
- The newest entry in that terminal is from **2025‑11‑30**, even after:
  - Performing a manual **Refresh (debug)** for account `mil_243` (or `better_planet_computers`).
  - Seeing a **200 OK** response in the per-account **Token refresh (debug)** terminal (separate modal).
- After closing and reopening the unified terminal, the **entry count does not change**, and no new `source=debug` entry appears.

Impact:

- The unified terminal is **not trustworthy** as a single pane of glass for both manual and scheduled refresh flows.
- It is impossible to visually compare a fresh manual debug call with the worker behaviour for the same account.

### 1.2 Unified terminal only shows logs up to Nov 30

Symptoms:

- The unified terminal’s latest entries are from **2025‑11‑30**, but today is **2025‑12‑01**.
- Terminal entries clearly show old behaviour:
  - `source: unknown`
  - Request bodies where `refresh_token` starts with `"ENC:v1..."`.
  - HTTP 400 `invalid_grant` responses from eBay.

Impact:

- The terminal appears **stale** and suggests that:
  - Either no new token refresh HTTP calls are being made, or
  - New calls are **not being logged** into `EbayConnectLog` in a way this endpoint can see.

### 1.3 Belief that `atoken-refresh-worker` is not running

Symptoms (from the Admin UI and terminal):

- The last visible HTTP-level entries (connect logs) are from Nov 30.
- Per-account token status shows **`refresh_error` = "refresh token decryption failed"** for multiple accounts.
- It looks like tokens keep expiring without being automatically refreshed.

Impact:

- The system appears **unreliable** – admin cannot trust that the worker is protecting tokens from expiry.
- Manual intervention (Refresh debug) is required to keep tokens alive.

### 1.4 `Internal error: refresh token decryption failed`

Symptoms:

- Per-account token status surface shows errors such as:

  > `Internal error: refresh token decryption failed`

- This is visible for multiple accounts (e.g. `mil_243`, `better_planet_computers`, `betterplanetsales`).
- The unified terminal (historical entries) shows old runs where the request body sent:

  ```json
  {
    "grant_type": "refresh_token",
    "refresh_token": "ENC:v1..."
  }
  ```

  and eBay responded with `invalid_grant`.

Impact:

- Worker cannot complete refresh for some or all accounts.
- It is unclear **where decryption is failing** and **why manual debug succeeds** while worker does not.

### 1.5 Divergent behaviour: manual debug vs automatic worker

Symptoms from today (Dec 1):

- Manual **Refresh (debug)** for an account succeeds:
  - Request goes to `https://api.ebay.com/identity/v1/oauth2/token`.
  - Request body has `grant_type=refresh_token` and `refresh_token` starting with `v^1.1...` (plain token, as eBay expects).
  - Response is HTTP 200 with a valid token payload.
- Automatic worker behaviour:
  - Per-account status shows `refresh_error = "refresh token decryption failed"`.
  - Worker logs show decrypt failures or internal errors.
  - No new HTTP-level entries in the unified terminal for Dec 1.

Impact:

- There is clear evidence that **manual and worker paths are not behaving identically** in production.
- Even if the code *intends* to share one builder, the **effective runtime behaviour** is different.

---

## 2. First-pass plan (v1) – naive approach

This first plan is intentionally direct and somewhat naive. It focuses on rewiring the worker to use the exact same instruments as the manual debug flow, then making the unified terminal just a view over whatever the shared flow logs.

### 2.1 Goals

1. **Guarantee** that the worker and manual debug use **one** refresh flow with **one** builder that always sends:
   - `grant_type=refresh_token`
   - `refresh_token` starting with `v^...` (never `ENC:`) when HTTP is attempted.
2. Ensure **every refresh attempt** (manual or worker) writes a **connect-log entry** that:
   - Includes request + response (or a synthetic placeholder for pre-HTTP failures).
   - Is queryable by `/api/admin/ebay/tokens/terminal-logs`.
3. Make the terminal show **newest entries first** and include **both sources**:
   - `source=debug` for manual debug.
   - `source=scheduled` for worker.
4. Eliminate or at least precisely localise `decrypt_failed` so that:
   - It never occurs because we sent `ENC:` to eBay.
   - If it occurs, it is clearly a **DB/crypto** issue, not an HTTP-level issue.

### 2.2 Tasks (v1)

#### Task A – Hard rewire: worker uses the same debug helper

1. In `ebay_token_refresh_service.refresh_access_token_for_account`:
   - For the worker path (`triggered_by="scheduled"`), stop calling `EbayService.refresh_access_token` directly.
   - Instead, call `EbayService.debug_refresh_access_token_http` unconditionally.
   - Parse the HTTP payload and, on success, persist tokens via `ebay_account_service.save_tokens`.

2. Remove or deprecate the `capture_http=False` branch; treat everything like the debug flow.

Expected outcome:

- Worker follows **identical HTTP behaviour** as the manual debug endpoint.
- Any mismatch between manual and worker behaviour disappears.

#### Task B – Make unified terminal purely log-driven

1. Ensure **all refresh flows** (manual and worker) emit `EbayConnectLog` entries with:
   - `action` in {`token_refreshed`, `token_refresh_failed`, `token_refresh_error`, `token_refresh_debug`}.
   - `source` in {`scheduled`, `debug`, `admin`}.
   - `request` and `response` or a synthetic `request` + `error` when HTTP isn’t called.

2. In `/api/admin/ebay/tokens/terminal-logs`:
   - Fetch logs via `ebay_connect_logger.get_logs(current_user.id, env, limit)`.
   - Filter actions to the set above.
   - Sort logs by `created_at` descending.

3. In `AdminWorkersPage.tsx` (React):
   - Add a `getAdminTokenTerminalLogs(env, limit)` API client method.
   - When opening the terminal, fetch logs and store them sorted newest-first.
   - Render each entry with `source` prominently visible.

#### Task C – Fix decrypt_failed by enforcing non-ENC tokens everywhere

1. Audit all call sites of `EbayService.refresh_access_token` and `debug_refresh_access_token_http` to ensure they *only* receive:
   - `EbayToken.refresh_token` (ORM property that decrypts `_refresh_token`).

2. In `_build_refresh_token_request_components`:
   - Keep current decryption logic for `ENC:v1:...` but:
     - Log clearly when the input is already plain (`v^...`), without trying to decrypt.

3. For any remaining `decrypt_failed` errors:
   - Add extra diagnostics to log the **DB token row id**, **prefix**, and **account id**, so we can trace whether the data is genuinely corrupt vs mis-wired.

---

## 3. Critique of first-pass plan (v1)

This section analyses weaknesses and risks in the naive plan.

### 3.1 Replacing worker flow with debug helper is overkill and risky

- Forcing the worker path to **always** use `debug_refresh_access_token_http` has several downsides:
  - **Performance**: debug helper is designed for human inspection, not for constant background usage. It builds verbose string bodies and captures raw request/response payloads for every call.
  - **Logging volume**: writing full HTTP payloads for every scheduled refresh may generate a large volume of connect logs in production.
  - **API design**: the `capture_http=False` + `EbayTokenResponse` approach is simpler for normal operation, and other parts of the app already rely on it.
- The root problem is **not** that we have two helpers; it is that **effective runtime usage** is currently inconsistent and/or logging is not wired correctly.

Conclusion:

- We should **keep** `refresh_access_token` for the worker path but enforce that it:
  - Uses the **same builder**.
  - Writes fully structured logs using the same `request_payload` shape.
- `debug_refresh_access_token_http` should remain a **diagnostics-only** path for manual inspection.

### 3.2 Logging and querying logic may be the real reason debug runs don’t appear

Possible causes why manual debug runs aren’t visible in the unified terminal:

1. **User id mismatch**:
   - We log debug events under `user_id = account.org_id`.
   - The terminal fetches logs using `user_id = current_user.id`.
   - If `org_id != current_user.id` (e.g. multi-tenant org/user separation), terminal won’t see those entries.

2. **Environment mismatch**:
   - Debug log writes with `environment = settings.EBAY_ENVIRONMENT`.
   - Terminal filters by `env` query param (e.g. `env=production`).
   - If `EBAY_ENVIRONMENT` on the backend is `sandbox`, debug logs won’t match `env=production`.

3. **Action filter mismatch**:
   - Terminal endpoint only includes actions in a fixed whitelist.
   - If debug logs use a different action string, they will be filtered out.

4. **Limit window**:
   - Terminal fetches `limit=50` or `100`, and older entries may be at the tail.

Conclusion:

- Before rewiring flows, we should:
  - Verify that debug events are actually being written into `EbayConnectLog`.
  - Fix **user id/env/action** mismatches so that the terminal endpoint sees them.
  - Only if logs are truly missing at the DB level should we touch the refresh flow itself.

### 3.3 Decrypt failures might be legitimate data issues

- `decrypt_failed` could indicate:
  - Tokens that were encrypted with an old key/format.
  - Truncated or corrupted DB rows.
  - Tokens copied between environments (sandbox ↔ production) with mismatched secrets.
- For such accounts, neither worker **nor debug** should succeed. Yet we see debug working today.

This discrepancy strongly suggests:

- The **actual builder and crypto** are probably fine.
- The worker may still have **older code running** somewhere OR is using a **different token instance** / different refresh path under certain conditions.

Conclusion:

- Rather than fully replacing the worker flow, we should:
  - Double-check the **deployed** worker code (version/commit).
  - Add precise logging of prefixes + account ids in both worker and debug paths.
  - Confirm with real logs that both paths receive the **same** plaintext token for the same account.

---

## 4. Refined plan (v2) – targeted and safer

Taking the critique into account, this refined plan focuses on:

- Making logging reliable and queryable.
- Proving that worker and debug flows use the same builder and plaintext token.
- Fixing any remaining mismatch **surgically** rather than replacing flows entirely.

### 4.1 High-level strategy

1. **Logging correctness first**:
   - Ensure every manual debug and worker attempt writes a connect-log entry that the terminal endpoint can see.
   - Fix user id / environment / action filters until this is true.

2. **Prove or disprove token equality**:
   - For a test account, log sufficient masked diagnostics to show whether the worker sees the same `v^...` refresh token that debug uses.

3. **Only if necessary, adjust worker flow**:
   - If diagnostics show the worker still receives `ENC:...` while debug gets `v^...`, then fix the **input source** for the worker (which token field/property it uses), not the whole HTTP helper.

4. **Keep unified terminal as a pure log viewer**:
   - The terminal should not know how refresh is implemented; it should only render entries from connect logs.

### 4.2 Detailed TODO list (v2)

#### TODO 1 – Verify and fix debug logging into `EbayConnectLog`

1. **Inspect debug logging path** in `ebay_token_refresh_service.refresh_access_token_for_account`:
   - In the `capture_http=True` branch (used by `/api/admin/ebay/token/refresh-debug`), confirm we:
     - Call `EbayService.debug_refresh_access_token_http`.
     - Receive a `debug_payload` with `request` and `response`.
     - Call `ebay_connect_logger.log_event(...)` exactly once per debug run with:
       - `user_id = account.org_id` (or `current_user.id` – see next step).
       - `environment = settings.EBAY_ENVIRONMENT`.
       - `action = "token_refresh_debug"`.
       - `source = "debug"`.

2. **Align user id semantics**:
   - Determine whether `db.get_connect_logs(user_id, env, limit)` expects the **org id** or the **auth user id**.
   - If it expects `current_user.id`, but logs currently use `account.org_id`, unify them by:
     - Either changing `log_event` calls in token-refresh code to use `current_user.id` (preferred, via the route that has access to `current_user`).
     - Or changing `get_connect_logs` to group by org id, if that’s the canonical key.

3. **Align environment semantics**:
   - Confirm that for production calls we log with `environment = "production"`.
   - Ensure `/api/admin/ebay/tokens/terminal-logs` only filters by `env` when that env matches `settings.EBAY_ENVIRONMENT`.

4. **Smoke test**:
   - Run a manual debug refresh for a known account.
   - Query the DB (or add a temporary admin diagnostic endpoint) to list the last 5 entries in `ebay_connect_logs` for this org + env.
   - Verify that at least one new `token_refresh_debug` entry is present.

#### TODO 2 – Make `/ebay/tokens/terminal-logs` return those logs

1. In `backend/app/routers/admin.py` for `/api/admin/ebay/tokens/terminal-logs`:
   - Confirm it calls `ebay_connect_logger.get_logs(current_user.id, env, limit)`.
   - Confirm it filters actions to include:
     - `token_refreshed`
     - `token_refresh_failed`
     - `token_refresh_error`
     - `token_refresh_debug`

2. **Sorting**:
   - Ensure the backend either sorts by `created_at DESC` **or** the frontend sorts (frontend already sorts now).

3. **Filtering by env**:
   - If debug logs are written with `environment = production`, verify that the endpoint accepts `env=production` and does not further narrow it incorrectly.

4. **Return shape**:
   - Ensure each entry has:
     - `id`, `created_at`, `environment`, `action`, `source`, `request`, `response`, `error`.
   - For pre-HTTP failures (e.g. decrypt_failed), `request` may be synthetic (with `refresh_token: "<decrypt_failed>"`) and `response` null.

#### TODO 3 – Frontend terminal correctness

1. In `frontend/src/api/ebay.ts`:
   - Confirm `getAdminTokenTerminalLogs(env, limit)` calls:

     ```ts
     GET /api/admin/ebay/tokens/terminal-logs?env=production&limit=100
     ```

2. In `frontend/src/pages/AdminWorkersPage.tsx`:
   - On opening the terminal, fetch logs and **sort newest-first** (already implemented).
   - Render each entry with:
     - `time: created_at`
     - `source: <source>`
     - `action: <action>`
     - HTTP request/response sections.

3. **Manual verification**:
   - After TODO 1 & 2 are done, run:
     - A manual **Refresh (debug)**.
     - Then open the terminal and verify:
       - Entry `#1` (top) is a new `source=debug`, `action=token_refresh_debug` record with a 200 response.

#### TODO 4 – Prove worker and debug use the same plaintext refresh token

1. In `_build_refresh_token_request_components` (ebay.py):
   - Log **masked prefixes** for both input and decrypted token:

     ```text
     token_refresh_path caller=<caller> input_prefix=<masked> decrypted_prefix=<masked> final_prefix=<masked>
     ```

   - This already exists but ensure it is enabled and visible in the worker logs.

2. In `token_refresh_worker.refresh_expiring_tokens`:
   - For each account, log a line including:
     - Account id, house name, and the **same prefix information** (via a helper that reads the token and calls `_mask_prefix`).

3. For debug runs, rely on existing debug terminal and/or add a similar prefix log line.

4. **Compare logs** for a test account:
   - Run **Refresh (debug)**, capture the masked prefix from logs.
   - Wait for a scheduled worker cycle and capture the masked prefix for the same account.
   - Expected: `final_prefix` and the masked `refresh_token` prefix in the request both start with `v^` and **match** between debug and worker.

If they match, we know the worker is no longer sending `ENC:` tokens. Any remaining `decrypt_failed` must be from an earlier stage (e.g. DB decryption), not from `_build_refresh_token_request_components`.

#### TODO 5 – Investigate and resolve `decrypt_failed` errors

1. For any account where `refresh_error = "decrypt_failed: ..."`:
   - Add a debug endpoint or script that:
     - Loads the `EbayToken` row.
     - Logs:
       - Length and masked prefix of `_refresh_token` (encrypted column).
       - Any crypto errors when decrypting via the model property.

2. If the ORM property `EbayToken.refresh_token` successfully returns a plain `v^...` token:
   - Then `decrypt_failed` must originate **inside** `_build_refresh_token_request_components`.
   - Check whether that code is seeing `ENC:` for this path (in which case we have a mismatch between worker code path and debug path).

3. If ORM decryption *fails* for `_refresh_token`:
   - Accept that these specific rows are corrupt/legacy and require a **full reconnect**.
   - Ensure the UI surfaces this clearly (it already can via `refresh_error`).

4. For any genuine cryptographic mismatch between worker and debug:
   - Fix the worker’s input source so it uses the **same** `EbayToken` and property that debug uses.

#### TODO 6 – Final unified verification

1. For a chosen account (e.g. `mil_243`):
   - Run **Refresh (debug)**.
   - Wait for the worker to run once (or temporarily lower its interval in a dev environment).

2. Open **Token refresh terminal (worker + debug)** and verify that you see **both**:
   - A `source=debug`, `action=token_refresh_debug`, status 200 entry.
   - A `source=scheduled`, `action=token_refreshed` or `token_refresh_failed` entry for the same account/time window.

3. Confirm that in both entries the `grant_type` is `refresh_token` and the `refresh_token` body starts with `v^`.

4. Confirm that per-account token status shows:
   - `status = ok` or `expiring_soon`.
   - No lingering `decrypt_failed` errors for accounts that were successfully refreshed.

5. Update the existing status report (`EBAY_TOKEN_REFRESH_WORKER_STATUS_REPORT_2025-12-01.md`) with a short “fixed & verified” section summarising:
   - That manual and worker flows share the same builder.
   - That no new `ENC:` tokens are ever sent to eBay.
   - That the unified terminal now shows both flows with correct `source` labels and newest-first ordering.

---

## 5. Implementation outline (what will actually change)

This section summarises the expected code-level changes, without showing actual code here in the chat. The concrete snippets will be contained inside this markdown file and/or the existing status report as needed.

1. **Backend – logging & terminal endpoint**
   - Adjust `ebay_token_refresh_service.refresh_access_token_for_account` to:
     - Ensure debug logs use the correct `user_id` and `environment` for connect-logs.
     - Add a synthetic `token_refresh_failed` connect-log entry for `decrypt_failed` cases (already partially implemented, to be verified and refined).
   - Confirm `EbayService.refresh_access_token` always logs connect-log entries when `user_id` is provided.
   - Ensure `/api/admin/ebay/tokens/terminal-logs`:
     - Filters the right `action` values.
     - Returns `source` and full `request`/`response` details.

2. **Frontend – Admin Workers page**
   - Keep the existing per-account **Refresh (debug)** terminal unchanged.
   - For the unified terminal:
     - Use `getAdminTokenTerminalLogs('production', 100)`.
     - Sort entries by `created_at` descending.
     - Render `source` and `action` clearly for each entry.
     - Provide a **Copy all** button.

3. **Diagnostics for prefixes and decrypt failures**
   - Use `_build_refresh_token_request_components`’s diagnostic log lines to compare worker vs debug behaviour for the same account.
   - If required, add a one-off diagnostic endpoint/script to dump masked refresh token prefixes for a given account.

4. **No full rewiring of worker to debug helper**
   - Instead of forcing the worker to call `debug_refresh_access_token_http` for every run, we:
     - Keep worker on `refresh_access_token`.
     - Ensure both helpers use the same builder and share the same semantics.
     - Ensure logging is consistent and complete.

Once these changes are in place and verified via real Railway logs and the Admin UI, the three main problems will be addressed:

- Manual debug entries will appear in the unified terminal with `source=debug`.
- The unified terminal will show newest entries first and receive fresh records beyond Nov 30.
- The worker will either successfully refresh tokens using `v^...` refresh tokens or, in irrecoverable cases, clearly mark accounts as needing reconnect without sending `ENC:` tokens to eBay.
