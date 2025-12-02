# eBay Token Refresh Logic

## Overview

The eBay Token Refresh system is designed to keep OAuth access tokens valid for all connected eBay accounts. It uses a **Worker -> Proxy -> Service** architecture to ensure tokens are decrypted and refreshed securely within the main Web App environment.

## Architecture

1.  **Background Worker (`token_refresh_worker`)**:
    *   Runs on Railway as a separate process (or thread).
    *   **Frequency**: Every 10 minutes.
    *   **Role**: Acts as a scheduler/trigger only. It does *not* process tokens directly because it may lack the correct environment keys to decrypt them.
    *   **Action**: Calls the internal API endpoint `POST /api/admin/internal/refresh-tokens` on the main Web App.

2.  **Web App API (Proxy)**:
    *   **Endpoint**: `/api/admin/internal/refresh-tokens`
    *   **Role**: Receives the trigger, validates the internal API key, and calls the shared service logic.
    *   **Context**: Runs within the main application context, so it has access to the correct `JWT_SECRET` / `SECRET_KEY` to decrypt refresh tokens.

3.  **Service Logic (`ebay_token_refresh_service`)**:
    *   **Function**: `run_token_refresh_job`
    *   **Logic**: Checks all active accounts to see if they need refreshing.

## Refresh Criteria

An account's token is refreshed if **EITHER** of the following conditions is met:

1.  **Expiring Soon**: The current access token expires in **15 minutes or less**.
2.  **Stale**: The token has not been refreshed for **60 minutes or more** (failsafe).

## Logging

The system produces logs in two places:

1.  **Application Logs (Stdout)**:
    *   Visible in Railway logs.
    *   Contains detailed info: `[token-refresh-worker] Triggering refresh...`, `[token-refresh-job] SUCCESS...`.

2.  **Token Refresh Terminal (Admin UI)**:
    *   Visible in the "eBay Workers" dashboard -> "Token refresh terminal".
    *   **Events Logged**:
        *   `token_refreshed`: Successful refresh.
        *   `token_refresh_failed`: Failed refresh (e.g., invalid grant, network error).
        *   `worker_heartbeat`: **(NEW)** Logged every 10 minutes if the worker runs but finds no accounts needing refresh. This confirms the worker is alive.

## Troubleshooting

*   **Worker not running**: Check Railway "Background Loops" status.
*   **"Decrypt failed" errors**: Ensure the Worker and Web App share the exact same `SECRET_KEY` / `JWT_SECRET` environment variables.
*   **No logs in terminal**: If "Last run" is recent but terminal is empty, it likely meant the worker was running but finding nothing to do (fixed by `worker_heartbeat`).
