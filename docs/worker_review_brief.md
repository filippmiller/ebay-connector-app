# Worker Review Brief – eBay Connector / Railway Workers Session

> Note: This file is a transcript-style brief of the relevant user–assistant communication in this session, including the reasoning about Railway workers and token refresh. Tool-only outputs and internal system messages are omitted.

---

## Conversation Transcript

### 1. Linking `ebay-connector-app` to Railway

**User:**

> please check railway connection to ebay-connector-app session

**Assistant:**

> Here’s what I can see about the Railway connection for `ebay-connector-app`:
>
> 1. **Railway config entry exists**
>
>    In `C:\\Users\\filip\\.railway\\config.json` there is a project entry:
>
>    - `projectPath`: `C:\\dev\\ebay-connector-app`
>    - `name`: `pretty-exploration`
>    - `project`: `e2a4908d-6e01-46fa-a3ab-aa99ef3befdf`
>    - `environment`: `524635cb-8338-482e-b9d6-002af8a12bcd`
>    - `environmentName`: `production`
>    - `service`: `31ec6c36-62b8-4f9c-b880-77476b8d340c`
>
>    So `C:\\dev\\ebay-connector-app` is **linked to a Railway project** and a specific service in the `production` environment.
>
> 2. **Frontend subfolder linkage**
>
>    There is a separate entry for the frontend:
>
>    - `projectPath`: `C:\\dev\\ebay-connector-app\\frontend`
>    - Same `project` and `environment`
>    - But `"service": null`
>
>    That means the frontend directory is linked to the same Railway project and environment, but **is not currently linked to a specific service**. It’s “connected” to the project, but not bound to a running service.
>
> 3. **What this implies for your “session”**
>
>    - From the Railway CLI’s point of view, if you `cd` into `C:\\dev\\ebay-connector-app` and run `railway status` or `railway env`, it should operate against:
>      - project: `pretty-exploration`
>      - environment: `production`
>      - service: the backend service `31ec6c36-62b8-4f9c-b880-77476b8d340c`
>    - If you `cd` into `C:\\dev\\ebay-connector-app\\frontend` and run Railway commands, they’ll still target the same project+environment, but **no service is selected**. Some commands that require a service (e.g. deploy, logs) may ask you to choose one or fail until you link or create a service.
>
> 4. **How to manually verify from your side**
>
>    In a PowerShell session, you can run:
>
>    ```powershell
>    cd C:\\dev\\ebay-connector-app
>    railway status
>    ```
>
>    and
>
>    ```powershell
>    cd C:\\dev\\ebay-connector-app\\frontend
>    railway status
>    ```
>
>    to confirm which project/environment/service each directory is bound to.
>
> ---
>
> If you tell me what exactly you mean by “check session” (e.g. “see if I’m logged in”, “see active environment”, “check logs for this service”), I can give you the exact commands and what output to look for.

---

### 2. New workers and missing token refresh

**User:**

> nice! Yesterday we made 2 workers and put them on railway, tey are atoken-refresh-worker and aebay-worker-loop. they were supposed to refresh ebay token and to keep ebay workers running. I want yo uto read related docs now and get latest logs from ebay to see why token refresh worker did not refresh token at needed time

**Assistant (summary of initial investigation):**

> I’ll inspect your project’s Railway status and worker services, then pull recent logs for `atoken-refresh-worker` and `aebay-worker-loop` to see what happened around the expected refresh time.
>
> [...] (after running `railway status` and `railway logs` on `ebay-connector-app`)
>
> From `C:\\dev\\ebay-connector-app`:
>
> - `railway status` shows:
>   - **Project**: `pretty-exploration`
>   - **Environment**: `production`
>   - **Service**: `ebay-connector-app`
>
> I pulled logs with various filters (`token`, `ebay`, `token_refresh`, worker names) and the last 400 lines. The logs show:
>
> - Container and app startup
> - Alembic migration `token_refresh_visibility_20251129` (“Add background worker + token refresh log tables”)
> - Migrations running successfully
> - Uvicorn server start and app initialization
>
> But **no explicit logs for**:
>
> - `atoken-refresh-worker`
> - `aebay-worker-loop`
> - nor obvious token-refresh events
>
> This suggested either the workers were in another Railway service, weren’t running, or their logs didn’t match the names we were searching for.

**Assistant (options proposed):**

> To go further, I suggested:
>
> - Pulling a larger chunk of logs (e.g. `railway logs --lines 2000`).
> - Searching the codebase for the worker implementations and token-refresh logic.
> - Checking if there is a separate worker service.
> - Inspecting any token-refresh DB log tables exposed in the admin UI.

**User:**

> yes run railway 2000 and also run logs for these specific sessions atoken-refresh-worker and aebay-worker-loop

**Assistant (after running `railway logs --lines 2000` on `ebay-connector-app`):**

> The large 2000-line logs came through; they show successful startup, migrations, and app initialization, but still no explicit token-refresh or worker-loop entries.
>
> Filtered logs for the strings `atoken-refresh-worker` and `aebay-worker-loop` returned nothing in this service.
>
> Conclusion at this stage: token-refresh issues were not visible in the main `ebay-connector-app` service logs; likely they live in dedicated worker services.

---

### 3. Verifying Railway services and worker status

**User:**

> yes verify these services and verify that they were started, then find logs

**Assistant (discovering services):**

> I ran:
>
> ```powershell
> cd C:\\dev\\ebay-connector-app
> railway service
> ```
>
> The project has several services configured, including (paraphrased from the selection menu):
>
> - `chestno.ru`
> - `ebay-connector-app`
> - `marvelous-achievement`
> - `echocare`
> - `aebay-workers-loop`
> - `Postgres`
> - `echocity`
>
> Then I selected the workers loop service:
>
> ```powershell
> railway service aebay-workers-loop
> railway status
> ```
>
> `railway status` showed:
>
> - Project: `pretty-exploration`
> - Environment: `production`
> - Service: `aebay-workers-loop`

**Assistant (logs for `aebay-workers-loop`):**

> I pulled logs:
>
> ```powershell
> railway logs --lines 2000
> ```
>
> These logs showed:
>
> - Container startup
> - Pydantic v2 config warnings (`orm_mode` renamed to `from_attributes`)
> - Warnings about `schema` field shadowing in `admin_mssql` and `admin_db_migration_console`
> - A `RuntimeWarning` from `runpy`:
>
>   > `'app.workers.ebay_workers_loop' found in sys.modules after import of package 'app.workers', but prior to execution of 'app.workers.ebay_workers_loop'; this may result in unpredictable behaviour`
>
> Importantly:
>
> - No `"eBay workers loop started"` log line
> - No per-account worker cycle logs
>
> This suggested that the `aebay-workers-loop` container starts, but the actual loop function is never invoked.

**Assistant (deployment logs for `aebay-workers-loop`):**

> Running:
>
> ```powershell
> railway logs --lines 2000 --deployment
> ```
>
> produced essentially the same output (startup warnings and the `runpy` warning), confirming there was no visible crash/traceback but also no evidence of the loop running.

**Assistant (intermediate conclusion):**

> From these checks:
>
> - `aebay-workers-loop` **exists and is deployed**.
> - Its container **starts**, but logs only warnings; the loop doesn’t appear to run.
> - No token-refresh or eBay sync activity is visible in its logs.
>
> Therefore, the token-refresh issue had to be in another service (`atoken-refresh-worker`) or in the token logic itself.

---

### 4. Code search for workers and token-refresh logic

**User:**

> yes ,search codebase

**Assistant (grep + file inspection):**

> I searched the codebase for worker-related terms (`ebay_workers_loop`, `token_refresh`, `atoken-refresh-worker`, etc.) and opened the key worker files.
>
> **File:** `backend/app/workers/ebay_workers_loop.py`
>
> ```python
> """eBay data workers background loop.
>
> Runs the generic ebay_workers scheduler every 5 minutes to trigger all
> per-account workers (orders, transactions, offers, messages, cases,
> finances, active inventory).
> """
>
> import asyncio
>
> from app.services.ebay_workers import run_cycle_for_all_accounts
> from app.utils.logger import logger
>
>
> async def run_ebay_workers_once() -> None:
>     """Run one full workers cycle for all active accounts."""
>     try:
>         await run_cycle_for_all_accounts()
>     except Exception as exc:
>         logger.error("eBay workers cycle failed: %s", exc, exc_info=True)
>
>
> async def run_ebay_workers_loop(interval_seconds: int = 300) -> None:
>     """Run eBay workers in a loop.
>
>     Default interval is 300 seconds (5 minutes).
>     """
>     logger.info("eBay workers loop started (interval=%s seconds)", interval_seconds)
>
>     while True:
>         await run_ebay_workers_once()
>         await asyncio.sleep(interval_seconds)
> ```
>
> **Key point:** there is **no** `if __name__ == "__main__"` block here, so running `python -m app.workers.ebay_workers_loop` just imports the module and never calls `run_ebay_workers_loop`.
>
> **File:** `backend/app/workers/token_refresh_worker.py`
>
> ```python
> """
> Token Refresh Worker
> Runs every 10 minutes to check for tokens expiring within 5 minutes and refreshes them.
> """
> import asyncio
> from datetime import datetime, timedelta
> from sqlalchemy.orm import Session
>
> from app.config import settings
> from app.database import get_db
> from app.services.ebay_account_service import ebay_account_service
> from app.services.ebay import ebay_service
> from app.utils.logger import logger
>
>
> async def refresh_expiring_tokens():
>     """
>     Check for tokens expiring within 5 minutes and refresh them.
>     This should be called every 10 minutes.
>     """
>     logger.info("Starting token refresh worker...")
>
>     db = next(get_db())
>     try:
>         accounts = ebay_account_service.get_accounts_needing_refresh(db, threshold_minutes=5)
>
>         if not accounts:
>             logger.info("No accounts need token refresh")
>             return {
>                 "status": "completed",
>                 "accounts_checked": 0,
>                 "accounts_refreshed": 0,
>                 "errors": []
>             }
>
>         logger.info(f"Found {len(accounts)} accounts needing token refresh")
>
>         refreshed_count = 0
>         errors = []
>
>         for account in accounts:
>             try:
>                 token = ebay_account_service.get_token(db, account.id)
>
>                 if not token or not token.refresh_token:
>                     logger.warning(f"Account {account.id} ({account.house_name}) has no refresh token")
>                     errors.append({
>                         "account_id": account.id,
>                         "house_name": account.house_name,
>                         "error": "No refresh token available",
>                     })
>                     continue
>
>                 logger.info(f"Refreshing token for account {account.id} ({account.house_name})")
>
>                 # Use org_id as the logical user_id for connect logs
>                 org_id = getattr(account, "org_id", None)
>                 env = settings.EBAY_ENVIRONMENT or "sandbox"
>
>                 new_token_data = await ebay_service.refresh_access_token(
>                     token.refresh_token,
>                     user_id=org_id,
>                     environment=env,
>                 )
>
>                 # Defensive log: type and public attributes only (no secrets)
>                 try:
>                     attrs = [a for a in dir(new_token_data) if not a.startswith("_")]
>                     logger.info(
>                         "Token refresh response: type=%s, attrs=%s, has_refresh=%s",
>                         type(new_token_data).__name__,
>                         attrs,
>                         bool(getattr(new_token_data, "refresh_token", None)),
>                     )
>                 except Exception:
>                     logger.debug("Could not introspect token refresh response")
>
>                 ebay_account_service.save_tokens(
>                     db,
>                     account.id,
>                     new_token_data.access_token,
>                     getattr(new_token_data, "refresh_token", None) or token.refresh_token,
>                     new_token_data.expires_in,
>                 )
>
>                 refreshed_count += 1
>                 logger.info(f"Successfully refreshed token for account {account.id} ({account.house_name})")
>
>             except Exception as e:
>                 error_msg = str(e)
>                 logger.error(f"Failed to refresh token for account {account.id} ({account.house_name}): {error_msg}")
>
>                 if token:
>                     token.refresh_error = error_msg
>                     db.commit()
>
>                 errors.append({
>                     "account_id": account.id,
>                     "house_name": account.house_name,
>                     "error": error_msg
>                 })
>
>         logger.info(f"Token refresh worker completed: {refreshed_count}/{len(accounts)} accounts refreshed")
>
>         return {
>             "status": "completed",
>             "accounts_checked": len(accounts),
>             "accounts_refreshed": refreshed_count,
>             "errors": errors,
>             "timestamp": datetime.utcnow().isoformat()
>         }
>
>     except Exception as e:
>         logger.error(f"Token refresh worker failed: {str(e)}")
>         return {
>             "status": "error",
>             "error": str(e),
>             "timestamp": datetime.utcnow().isoformat()
>         }
>     finally:
>         db.close()
>
>
> async def run_token_refresh_worker_loop():
>     """
>     Run the token refresh worker in a loop every 10 minutes.
>     This is the main entry point for the background worker.
>     """
>     logger.info("Token refresh worker loop started")
>
>     while True:
>         try:
>             result = await refresh_expiring_tokens()
>             logger.info(f"Token refresh cycle completed: {result}")
>         except Exception as e:
>             logger.error(f"Token refresh worker loop error: {str(e)}")
>
>         await asyncio.sleep(600)
>
>
> if __name__ == "__main__":
>     asyncio.run(run_token_refresh_worker_loop())
> ```
>
> **Key points:**
>
> - `ebay_workers_loop.py` defines the loop but never calls it by default (no `__main__`).
> - `token_refresh_worker.py` *does* have an entrypoint and runs the loop when executed as a module/script.

**Assistant (inspecting scheduler):**

> I also inspected `backend/app/services/ebay_workers/scheduler.py`, which defines `run_cycle_for_all_accounts` and per-account workers (`orders`, `transactions`, `offers`, `messages`, `active_inventory`, `buyer`). This is what `run_ebay_workers_loop` should be driving every 5 minutes.

---

### 5. Selecting `atoken-refresh-worker` and analyzing logs

**Assistant:**

> I selected the token refresh worker service:
>
> ```powershell
> railway service atoken-refresh-worker
> railway status
> ```
>
> `railway status` showed:
>
> - Project: `pretty-exploration`
> - Environment: `production`
> - Service: `atoken-refresh-worker`
>
> Then I pulled its logs:
>
> ```powershell
> railway logs --lines 2000
> ```
>
> The summarized logs for `atoken-refresh-worker` clearly show:
>
> - **Loop starting:**
>   - `Token refresh worker loop started` (e.g. at 2025-11-29 12:27:23)
> - **Repeated cycles:**
>   - `Starting token refresh worker...`
>   - `Found N accounts needing token refresh`
> - **Every token refresh attempt fails** with the same error from eBay:
>   - HTTP call: `POST https://api.ebay.com/identity/v1/oauth2/token`
>   - Response: `400 Bad Request`
>   - Error body (as logged):
>     - `{"error":"invalid_grant","error_description":"the provided authorization refresh token is invalid or was issued to another client"}`
>   - Logged per account, e.g.:
>     - `Failed to refresh token for account e524cb1f-87c2-4eda-9518-721fc66bd0c (better_planet_computers): 400: Failed to refresh token: {"error":"invalid_grant","error_description":"the provided authorization refresh token is invalid or was issued to another client"}`
>     - `Failed to refresh token for account c38f2c13-b675-46a2-b7f5-b5009da5ac6c (mil_243): 400: Failed to refresh token: {"error":"invalid_grant","error_description":"the provided authorization refresh token is invalid or was issued to another client"}`
>     - `Failed to refresh token for account b7881f89-8da3-4059-be15-24f4662deb20 (betterplanetsales): 400: Failed to refresh token: {"error":"invalid_grant","error_description":"the provided authorization refresh token is invalid or was issued to another client"}`
> - Cycle summaries consistently show **zero successes**, e.g.:
>   - `Token refresh worker completed: 0/3 accounts refreshed`
>   - `Token refresh cycle completed: {'status': 'completed', 'accounts_checked': X, 'accounts_refreshed': 0, 'errors': [...]}`
> - Some cycles also log `No accounts need token refresh` when nothing is near expiry.
>
> Additional warnings appearing in logs:
>
> - `RuntimeWarning: 'app.workers.token_refresh_worker' found in sys.modules ...`
> - Pydantic v2 config warnings (`'orm_mode' has been renamed to 'from_attributes'`)
> - A deprecation warning for `datetime.datetime.utcnow()`.

**Assistant (high-level conclusion):**

> So:
>
> - The **token refresh worker did start and run on schedule**.
> - It **did try** to refresh tokens for your accounts.
> - eBay **rejected every refresh** with `invalid_grant`, so **no new tokens were saved**.
> - That is exactly why your tokens were not refreshed at the needed time.
>
> This is not a scheduling problem; it is an **OAuth/token validity problem**.

---

### 6. Why eBay returns `invalid_grant` in this context

**Assistant:**

> `invalid_grant` with that description means:
>
> > “the provided authorization refresh token is invalid or was issued to another client”
>
> Common concrete causes in your situation:
>
> 1. **Refresh tokens were created under a different eBay App ID / credentials**
>    - You may have:
>      - Switched to a new eBay application (new client ID/secret),
>      - But kept old refresh tokens.
>    - eBay refuses to let client B use a refresh token minted for client A.
>
> 2. **Refresh tokens have been revoked or expired**
>    - eBay user revoked consent in their account.
>    - Or the refresh token timed out according to eBay’s rules (e.g. after long inactivity).
>
> 3. **Environment mismatch (sandbox vs production)**
>    - Using a sandbox refresh token against `https://api.ebay.com/identity/v1/oauth2/token` (production), or vice versa.
>
> 4. **Tokens stored incorrectly in DB**
>    - If the DB contains truncated, corrupted, or mixed-up refresh tokens, eBay will treat them as invalid.
>
> Given the error is the same across multiple accounts, the most likely root cause is **#1 (new app credentials or mis-matched client)** or **#3 (environment mismatch)** rather than user-by-user revocation.

---

### 7. Concrete next steps to fix token refreshing

**Assistant:**

> **Step 1: Re-authorize one account and test**
>
> For a single affected account:
>
> 1. Go through your existing **eBay OAuth connect flow** again for that account in the **correct environment** (production vs sandbox).
> 2. Confirm the backend stores:
>    - `ebay_refresh_token`
>    - `ebay_access_token`
>    - `ebay_token_expires_at`
>    - and that they line up with the correct app credentials (client ID/secret) you’re using in production.
>
> Then either:
>
> - Manually trigger `refresh_expiring_tokens()` in dev (or via a one-off CLI command), or  
> - Wait for the `atoken-refresh-worker` loop to hit that account again and watch its logs:
>
>   ```bash
>   # (example) attach logs and filter for token refresh activity
>   railway logs --lines 200 --service atoken-refresh-worker --filter "Token refresh"
>   ```
>
> If the refresh token is valid for this client, you should see:
>
> - `Successfully refreshed token for account ...`
> - Summary showing `accounts_refreshed: 1` for that cycle.
>
> **Step 2: Verify eBay client credentials and environment**
>
> In your backend config (`app.config.settings`):
>
> - Confirm the production deployment is using **the same eBay app** that was used to generate the stored refresh tokens.
> - Check environment:
>   - `EBAY_ENVIRONMENT` (or equivalent) must match how the tokens were created.
>   - Production tokens → `https://api.ebay.com/identity/v1/oauth2/token`.
>   - Sandbox tokens → sandbox token endpoint.
>
> If you recently rotated or changed eBay credentials, all tokens generated under the old app may now be invalid.
>
> **Step 3: Decide how to handle invalid tokens at scale**
>
> Since the worker already logs `invalid_grant` and writes `token.refresh_error`, you can:
>
> - Surface a clear status in your UI: “Token refresh failed: please reconnect your eBay account”.
> - Offer an admin/user re-connect flow that:
>   - Clears the invalid refresh token,
>   - Sends the user through OAuth again,
>   - Saves the new valid tokens.
>
> Until that happens, automated refresh will keep failing in the background.

---

### 8. Summary diagnosis

**Assistant (final summarized diagnosis):**

> - **`aebay-workers-loop` service**: Exists but its loop never starts in production because `ebay_workers_loop.py` lacks an entrypoint (`if __name__ == "__main__": ...`). This impacts scheduled eBay workers.
> - **`atoken-refresh-worker` service**: Runs correctly and calls `refresh_expiring_tokens()` every 10 minutes.
> - **Observed behaviour**: Every refresh attempt fails with eBay `400 invalid_grant`, so tokens are **never** updated.
> - **Root cause class**: OAuth / token validity misconfiguration (app credentials / environment / revoked or mismatched refresh tokens), **not** a scheduling bug.
>
> Recommended path forward: re-authorize at least one account in the correct environment using the actual production eBay client, verify one successful refresh in logs, then roll out a re-connect flow or migration for all affected accounts.

---

End of brief.
