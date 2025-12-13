# eBay Token Refresh Inspector

This document describes the Admin UI inspector that shows a **sanitized** preview
of how the backend refreshes eBay access tokens for each connected account.

## Backend

Endpoint: `GET /api/admin/ebay/token/refresh-preview/{ebay_account_id}`

- Access: Admin-only (same guard as other `/api/admin/ebay/*` endpoints).
- Uses the same decrypted `refresh_token` and HTTP shape as the
  `token_refresh_worker` when it calls eBay.
- Does **not** perform a real HTTP request – it only builds the request
  components and returns a masked preview.

Response shape (example):

```json
{
  "method": "POST",
  "url": "https://api.ebay.com/identity/v1/oauth2/token",
  "headers": {
    "Content-Type": "application/x-www-form-urlencoded"
  },
  "body_form": {
    "grant_type": "refresh_token",
    "refresh_token": {
      "prefix": "v^1.1#i^1#",
      "suffix": "...Q==",
      "length": 312,
      "starts_with_v": true,
      "contains_enc_prefix": false
    }
  },
  "account": {
    "id": "…",
    "house_name": "mil_243",
    "username": "mil_243",
    "ebay_user_id": "…"
  }
}
```

Notes:

- Full `refresh_token` is **never** returned.
- Only a small prefix/suffix, total length, and booleans are exposed.
- Any Authorization or secret-like headers are stripped from `headers`.

## Frontend

On the Admin → Workers page, inside the eBay Workers panel:

- There is an **"Inspect token format"** button in the Workers command control
  header.
- Clicking it calls `/api/admin/ebay/token/refresh-preview/{account_id}` for the
  currently selected account and opens a small modal.
- The modal shows:
  - HTTP method and URL.
  - `grant_type` (`refresh_token`).
  - Sanitized headers (no Authorization).
  - Masked `refresh_token` info: prefix, suffix, length, `starts_with_v`,
    `contains_enc_prefix`.

This inspector is safe to use in production and is intended for confirming that
workers are sending **plain** `v^1.1…` refresh tokens (not `ENC:…`) via the same
code path as the background token-refresh worker.
