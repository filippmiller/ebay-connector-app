# eBay Token Refresh Worker – Status & Debug Terminal Report (Dec 1, 2025)

## 1. Scope of this report

This report summarizes what is currently implemented around eBay token refresh diagnostics and where to find it in the Admin UI. It also covers:

- Where and how you can see **full HTTP request/response** for token refresh calls.
- Whether the **automatic token refresh worker** is running on Railway and how often.
- What evidence we have about **encrypted (`ENC:`) vs plain (`v^…`) refresh tokens** being sent to eBay.
- Where logging may still be insufficient or misleading compared to the original intent.

This is a read-only analysis of the current code and deployed Railway services as of **2025‑12‑01**.

---

## 2. Where the token refresh debug terminal exists today

There are **two distinct debug surfaces** related to token refresh:

1. **Per-account manual “Refresh (debug)” terminal** – *already wired and visible*.
2. **HTTP-level token logs modal** – *JSON log viewer, not a terminal, but contains per-call request/response*.

### 2.1 Manual “Refresh (debug)” terminal (per account)

Location in the UI:

- Navigate to **Admin → Workers**.
- In the middle of the page there is a card titled **“Per-account token status”**.
- Each row corresponds to one eBay account and has an **Actions** column with two buttons:
  - **“View log”** – opens a table of `EbayTokenRefreshLog` rows (high-level success/error metadata).
  - **“Refresh (debug)”** – this is the manual debug entrypoint.

Behavior of **Refresh (debug)**:

- When you click **Refresh (debug)** for a given account, the frontend calls:
  - `POST /api/admin/ebay/token/refresh-debug` with the selected `ebay_account_id`.
- The backend endpoint:
  - Validates that the account belongs to your org.
  - Looks up the latest `EbayToken` for that account.
  - Invokes the shared helper `refresh_access_token_for_account` with `capture_http=True` and `triggered_by="debug"`.
  - Returns a payload that includes:
    - `environment` (sandbox/production),
    - `success`, `error`, `error_description`,
    - `request` – method, URL, **full headers** and raw **request body**,
    - `response` – status code, reason, headers, and body text.

The Admin UI then:

- Opens a **full-screen black terminal-style modal** titled **“Token refresh (debug)”**.
- Renders the HTTP exchange in a single concatenated text stream:
  - A `=== HTTP REQUEST ===` block with method, URL, headers, and body.
  - A `=== HTTP RESPONSE ===` block with status line, headers, and body.
- Provides a **“Copy all”** button that copies the entire terminal content to the clipboard.

This terminal **does exactly what you described for the manual debug path**:

- Shows the **complete outgoing HTTP call** to `/identity/v1/oauth2/token` with **full headers and body**.
- Shows the **entire response** payload from eBay.
- Is **per-account and per-run**, and reflects the exact `refresh_token` used on that debug call.

### 2.2 Token HTTP logs modal (JSON log viewer)

Location in the UI:

- On the same **Admin → Workers** page, at the top there is a compact header row with three cards:
  1. **Background loops** (eBay workers loop + token refresh loop heartbeat).
  2. **Account selection**.
  3. **Token refresh status**.
- Inside the **“Token refresh status”** card you will see two links:
  - **“View token HTTP logs (JSON)”** in the header.
  - **“View raw HTTP token logs”** inside the card body.

Behavior:

- Both links call the same backend endpoint via the API client:
  - `GET /api/admin/ebay/tokens/logs?env=production`.
- The backend pulls recent entries from `EbayConnectLog` via `ebay_connect_logger.get_logs(...)` and filters them down to token-related actions:
  - `token_refreshed`,
  - `token_refresh_failed`,
  - `token_info_viewed`,
  - `token_call_blocked_missing_scopes`.
- It returns a list of logs with:
  - `action`, `environment`, `created_at`,
  - `request` – method, URL, headers, and **sanitized body**,
  - `response` – status code, headers, and body snippet,
  - `error` (if any).

The Admin UI displays these logs in a modal:

- Title: **“Token HTTP logs (request & response)”**.
- For each log entry, you see:
  - Action name, environment, timestamp, and error summary.
  - Pretty-printed JSON of the `request` and `response` sections.
- This is a **JSON viewer**, not a terminal; it is meant for **multi-call history** rather than a single run.

Important:

- The backend intentionally **masks `refresh_token` inside the logged request body** so this view remains safe for production:
  - If a `refresh_token` field is present, it is truncated to prefix + suffix: `prefix...suffix`.
- Even with masking, this modal is sufficient to check whether the **prefix looks like `v^…` or `ENC:…`** in recent calls.

---

## 3. Where the automatic worker’s HTTP-level terminal is supposed to be

From your specification, you wanted **one unified terminal** that:

- Shows both **manual debug** and **automatic worker-driven** refresh calls.
- Clearly labels each entry with **source**: `manual` vs `automatic` (or `debug` vs `scheduled`).
- Lives on the **Workers page**, with a **single button** that opens a **black terminal modal** similar to the eBay connect terminal.

What exists today:

- Backend side, the building blocks are largely there:
  - `EbayConnectLogger.log_event(...)` supports a `source` field.
  - Token refresh flows log structured events with `action` values such as:
    - `token_refreshed`,
    - `token_refresh_failed`,
    - `token_refresh_debug`.
  - There is a dedicated admin endpoint:
    - `GET /api/admin/ebay/tokens/terminal-logs?env=production&limit=…`.
    - It filters connect logs down to token refresh–related actions, **including `token_refresh_debug`**, and returns a list of entries with:
      - `action`, `source`, `request`, `response`, `error`, `environment`, `created_at`.
    - It **masks `refresh_token`** fields analogously to the JSON logs.
- Frontend side, for **Admin → Workers**, the following are wired:
  - Manual **Refresh (debug)** terminal (Section 2.1).
  - JSON HTTP logs modal (Section 2.2).
  - Worker loop heartbeat and token status tables.

What is **not** present in the current frontend:

- There is **no button** in `EbayWorkersPanel` or `AdminWorkersPage` that calls `/api/admin/ebay/tokens/terminal-logs`.
- There is **no dedicated “Token worker terminal” modal** that renders those logs in a black terminal-style screen.
- As a result, you **cannot currently open a unified terminal** that:
  - streams **all token refresh HTTP exchanges**, and
  - visually differentiates **automatic vs manual** by `source`.

Conclusion:

- The **backend support** for such a terminal is implemented (via `/api/admin/ebay/tokens/terminal-logs` and rich connect logs).
- The **frontend wiring for the worker token terminal was not completed**: the modal and button you requested on the Workers page are missing.
- What you *do* have today is:
  - Per-account manual terminal (**Refresh (debug)**), and
  - Per-project HTTP logs JSON viewer (**Token HTTP logs**).

---

## 4. Is the eBay token refresh worker running on Railway?

Using the Railway CLI against the production project, we can see the service layout:

- The project has an app service **`ebay-connector-app`** and at least two worker services:
  - **`aebay-workers-loop`** – runs the generic eBay data workers loop.
  - **`atoken-refresh-worker`** – runs the token refresh worker loop.
- For `atoken-refresh-worker`, the configured start command is:
  - `cd /app/backend && python -m app.workers.token_refresh_worker`.
- The latest deployment for `atoken-refresh-worker` is reported as **`SUCCESS`** and `deploymentStopped = false`.

Inspection of the **`atoken-refresh-worker` logs** (most recent ~200 lines) shows:

- The worker loop is **starting successfully** and then running in a **`while True` sleep(600) cycle**.
- Every ~10 minutes there are log entries from `refresh_expiring_tokens()` such as:
  - “Starting token refresh worker…”
  - Either:
    - “No accounts need token refresh”, or
    - “Found N accounts needing token refresh”, followed by per-account attempts.
- At the end of each run there is a summary log of the form:
  - `Token refresh worker completed: X/Y accounts refreshed`.
  - `Token refresh cycle completed: {"status": "completed", "accounts_checked": Y, "accounts_refreshed": X, "errors": [...], "timestamp": "..."}`.

The **heartbeat endpoint** `/api/admin/ebay/workers/loop-status` (used by the “Background loops” card) reads from the `BackgroundWorker` table and:

- Shows a **loop entry for `token_refresh_worker`** with:
  - `interval_seconds ≈ 600` (10 minutes),
  - non-null `last_started_at` and `last_finished_at`,
  - `last_status` equal to `"ok"` or `"error"` depending on recent runs,
  - a derived `stale` flag (false when the last finished time is within `3 × interval`).

Summary:

- The **token refresh worker service is running on Railway** as `atoken-refresh-worker`.
- The **loop is executing approximately every 10 minutes**.
- Each run is **recorded in `BackgroundWorker`** and surfaced in the **Admin → Workers / “Background loops”** card.
- So the worker is **not dead**; it is alive and attempting work regularly.

---

## 5. Why you might not see expected logs / behavior

Although the worker is running, the **actual outcome of recent runs is poor**:

- The worker logs for the last cycles show **0 accounts successfully refreshed**.
- Many accounts produce errors of the form:
  - `"Token refresh for account <id> (<house_name>) failed with HTTPException: Internal error: refresh token decryption failed"`.
- For affected accounts, the corresponding `EbayTokenRefreshLog` entries will have:
  - `success = False`,
  - `error_code = "decrypt_failed"`,
  - `error_message` describing a decryption failure.

What this means in practice:

1. **The worker is running and logging each cycle**, but for most accounts the refresh attempts fail very early (before contacting eBay) due to decryption errors.
2. When `get_accounts_needing_refresh(...)` returns an empty list, the worker logs:
   - “No accounts need token refresh” and exits the cycle.
3. When there are accounts to refresh but **all of them hit `decrypt_failed`**, the cycle summary looks like:
   - `accounts_checked = N`, `accounts_refreshed = 0`, and a non-empty `errors` list.

This can easily create the impression that the worker is **not running at all**, because:

- You do not see any successful refreshes in your per-account token status table.
- Access tokens continue to expire, especially for accounts with corrupted or legacy-encrypted `refresh_token` values.

However, the evidence from logs and the `BackgroundWorker` row confirms:

- The **scheduling and heartbeat** part is working as designed.
- The **business logic is currently blocked** by decryption problems for multiple accounts.

---

## 6. Are we still sending `ENC:` refresh tokens to eBay?

The earlier incident (documented in `docs/token_refresh_debugging_decrypting_error_brief_dec1.md`) established that:

- The database stores encrypted tokens in `_refresh_token` with an `ENC:v1:...` prefix.
- The ORM property `EbayToken.refresh_token` is supposed to **decrypt** this and return a plain eBay token starting with `v^1.1#…`.
- Historically, some worker flows leaked the encrypted `ENC:…` value all the way into the HTTP request body.

Fixes that are now in place, based on the same document and current code:

1. **Single authoritative builder for refresh requests** in the eBay service layer:
   - All token refresh HTTP calls (both worker/admin and debug) go through a common helper that:
     - Accepts a logical `refresh_token` and a `caller`/`source` label.
     - If the value starts with `ENC:`, it performs exactly one decrypt attempt.
     - After decryption, it enforces three invariants:
       1. The value is a non-empty string.
       2. It no longer starts with `ENC:`.
       3. It looks like an eBay token, typically starting with `v^`.
     - If any invariant fails, it raises an `HTTPException` with `code = "decrypt_failed"` **before sending any HTTP**.
2. **Strict fail-safe**:
   - A `decrypt_failed` error now causes the worker to **abort without calling eBay** for that account.
   - So in new code, no HTTP refresh request should contain `refresh_token = "ENC:..."`.
3. **Source tagging in connect-logs**:
   - Calls are logged with `action` and `source`, making it possible to distinguish:
     - `scheduled` (worker),
     - `admin`,
     - `manual`,
     - `debug`, etc.

Evidence from current production behavior:

- The **token refresh worker logs** now show many `decrypt_failed`-style internal errors for certain accounts.
- This is consistent with the new fail-safe: the system would rather **stop before contacting eBay** than send `ENC:` and get `invalid_grant`.
- The **Admin token HTTP logs modal** shows recent HTTP exchanges for token refresh flows; those payloads now have `refresh_token` values that are **masked** but still allow you to verify the prefix:
  - For successful calls you should see masking consistent with `v^…`-style tokens.
  - You should **not** see new entries where the masked prefix begins with `ENC:`.

Given the combination of:

- the strengthened request builder,
- the explicit `decrypt_failed` behavior,
- and the nature of current worker errors,

the current system behavior is best summarized as:

> **We are no longer sending `ENC:` refresh tokens to eBay.**
>
> For accounts whose stored tokens cannot be decrypted into a valid `v^…` value, the worker fails locally with `decrypt_failed` and does **not** make an outbound HTTP call.

That said, for complete verification you can:

1. Open **Admin → Workers → Token HTTP logs (JSON)**.
2. Inspect several recent entries for `token_refreshed` / `token_refresh_failed`.
3. Confirm that the `refresh_token` field in the masked request body has a prefix that looks like `v^…` rather than `ENC:`.

---

## 7. Do we have a unified terminal that shows both manual and automatic runs?

**Short answer:** Not yet.

- Backend:
  - `/api/admin/ebay/tokens/terminal-logs` exposes exactly the data needed to build such a terminal:
    - Per-entry request + response + error,
    - `action` and `source` to distinguish **debug vs scheduled** calls.
- Frontend:
  - The current implementation of **Admin → Workers** includes:
    - Manual per-account terminal (**Refresh (debug)**).
    - JSON-based HTTP logs viewer (**Token HTTP logs**).
  - There is **no modal** that:
    - Calls `/api/admin/ebay/tokens/terminal-logs`, and
    - Renders the result in a **black terminal-style window**, and
    - Includes explicit labels like `source=scheduled` vs `source=debug` per call.

So the **button you expected on the Workers page to open that unified worker terminal was not implemented**. The closest elements today are:

- “Refresh (debug)” – full single-run terminal, but **only for manual debug**.
- “Token HTTP logs (JSON)” – multi-run history, but **JSON tables instead of a terminal** and **no one-click source filter**.

---

## 8. Logging expectations vs current behavior for the worker

Your expectation:

- The worker should:
  - Run **every 10 minutes**.
  - Even when **no account needs refresh**, it should **log a clear entry** saying it checked tokens and found nothing to do.
  - When accounts do need refresh, it should:
    - Log **each attempt**, including HTTP request and response details.
    - Leave a **structured trail** per account so expirations can be correlated with worker behavior.

Current behavior (from code + logs):

1. On each run, the worker:
   - Writes a heartbeat row in `BackgroundWorker` with `last_started_at`, `last_status`, etc.
   - Calls `get_accounts_needing_refresh(...)` with a 15-minute threshold and max-age filter.
2. If there are **no accounts** that need refresh:
   - It logs: `"No accounts need token refresh"`.
   - Sets worker status to `"ok"`.
   - Returns a JSON summary with `accounts_checked = 0` and `accounts_refreshed = 0`.
3. If there **are accounts** but refresh fails for all of them due to `decrypt_failed` or other errors:
   - It still logs the overall run summary with `accounts_checked = N`, `accounts_refreshed = 0`, and an `errors` list.
4. HTTP-level details for those runs are **not automatically surfaced in a terminal** today, but are:
   - Partially available via connect logs (if the failure happens after request building).
   - Fully available for manual debug flows.

So in terms of **logging frequency**, the worker is behaving as you requested: every run results in at least a heartbeat and run summary. The missing piece is:

- A **front-end view** that consolidates **low-level HTTP logs** for **both** scheduled and debug refreshes in one **terminal-style** interface.

---

## 9. Actionable conclusions

1. **Where is the manual debug terminal?**
   - On **Admin → Workers**, in the **“Per-account token status”** table, use the **“Refresh (debug)”** button in the Actions column.
   - This opens a **black terminal modal** showing the **exact HTTP request and response** for that run, including full headers and body.

2. **Where can you see historical HTTP-level logs?**
   - On the same page, in the **“Token refresh status”** card, use **“View token HTTP logs (JSON)”** or **“View raw HTTP token logs”**.
   - This opens a **JSON-based modal** with multiple token-related connect logs, each containing **request + response**. Refresh tokens are masked but still reveal whether they start with `v^` vs `ENC:`.

3. **Is the automatic token refresh worker running on Railway?**
   - Yes. The `atoken-refresh-worker` service is deployed, marked as `SUCCESS`, not stopped, and its logs confirm a **10-minute loop** is active.
   - The Admin **“Background loops”** card also shows fresh `last_finished_at` and `last_status` for `token_refresh`.

4. **Are we still sending encrypted (`ENC:`) tokens to eBay?**
   - Current code paths enforce a **hard fail** on any `ENC:` value that cannot be decrypted into a valid `v^…` token before sending HTTP.
   - Worker logs show **`decrypt_failed` internal errors** rather than `invalid_grant` responses with `ENC:` in the body, which matches the new behavior.
   - The available evidence indicates we are **no longer sending `ENC:` tokens** to eBay; failing accounts now stop at decryption.

5. **What is missing vs your original spec?**
   - The **unified, black-screen terminal on the Workers page** that:
     - Shows **both manual and automatic refresh HTTP calls**.
     - Distinguishes them clearly by `source` (e.g. `scheduled` vs `debug`).
     - Is opened via a **single button** (e.g. “Open token worker terminal”).
   - Backend support for this view exists (`/api/admin/ebay/tokens/terminal-logs`), but the **frontend modal and entrypoint button have not yet been implemented**.

---

## 10. Suggested next steps (for a follow-up task)

If you want to proceed, a focused follow-up task could:

1. **Add a “Token worker terminal” modal on the Workers page** that:
   - Calls `/api/admin/ebay/tokens/terminal-logs?env=production&limit=…`.
   - Renders entries in a **black terminal-style view** similar to the existing debug terminal.
   - Shows, per entry:
     - Timestamp, `action`, and `source` (`scheduled` vs `debug` vs `admin`).
     - Pretty-printed JSON body for the HTTP request and response.
2. **Add a button near the Token refresh status card header**, e.g.:
   - “Open token worker terminal”.
   - This would open the unified terminal instead of just the JSON log table.
3. **Optionally, highlight `source` visually**:
   - Color-code log lines (e.g. green for `scheduled`, blue for `debug`).
   - Allow basic filtering (show only `scheduled` vs only `debug`).

These changes would satisfy your original requirement of “one full-screen terminal that shows exact, precise calls we make to eBay to refresh tokens, with a clear distinction between manual and automatic runs,” while reusing the already-implemented connect-log infrastructure.
