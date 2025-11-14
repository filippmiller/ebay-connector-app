# eBay Connector – Session Notes (2025-11-14)

**Purpose of this document:**
- Hands-off summary for the next Warp/agent session.
- Capture what we changed today, how we deploy, and what is still pending.

---

## 1. How we work in this project

- **Stack**:
  - Backend: Python FastAPI (folder `backend/`)
  - Frontend: React + Vite (folder `frontend/`)
  - DB: Postgres on **Supabase**, reached via `DATABASE_URL`.
  - Hosting: **Railway** for backend (and likely frontend).
- **Branching / deployment model**:
  - We work directly on `main`.
  - Railway is configured to deploy from `main` (push → build → deploy).
- **Config**:
  - All sensitive values are provided as environment variables in Railway / Supabase.
  - Backend explicitly **forbids SQLite** and requires `DATABASE_URL`:
    - `backend/app/config.py`:
      - Raises `RuntimeError` if `DATABASE_URL` is missing or starts with `sqlite`.
- **Typical workflow**:
  1. Modify backend / frontend files locally.
  2. Run basic checks (e.g., `python -m py_compile ...`, Vite build if needed).
  3. Commit to `main`.
  4. `git push origin main`.
  5. Wait for Railway to build and deploy.

### Railway / Supabase tag

- The application expects `DATABASE_URL` from **Railway/Supabase**.
- There is no `.env` checked in; config uses `os.getenv("DATABASE_URL")` and fails fast without it.
- For the next agent session, assume:
  - **Railway service**: backend FastAPI app (`ebay-connector-app` backend).
  - **Supabase project**: provides the Postgres instance; URL is injected into Railway as `DATABASE_URL`.

(If needed, the next session can open Railway dashboard to see the exact project name and tags.)

---

## 2. What we implemented / fixed today

### 2.1. Fix `/ebay/debug` backend error (IndentationError)

- File: `backend/app/utils/ebay_debugger.py`.
- Problem: broken `templates` dict (`orders` and `transactions` entries were malformed), causing:
  - `IndentationError: unexpected indent` around line 216.
  - As a result, `/ebay/debug` endpoint failed to import `EbayAPIDebugger` and returned "Failed to make debug request".
- Fix:
  - Corrected the `templates` mapping so it now contains:
    - `"identity"`, `"orders"`, `"transactions"`, `"inventory"`, `"offers"`, `"disputes"`, `"messages"` – all with proper indentation and keys.
  - Verified with:
    - `python -m py_compile backend/app/utils/ebay_debugger.py` → exit code 0.
- Result: `/ebay/debug` works again; Identity and Orders templates execute successfully.

### 2.2. Orders API (Sell Fulfillment `getOrders`) – minimal working request

- Goal: make Orders API work from the Debugger and later from the Worker.
- Status before: we experimented with invalid filters (`orderStatus`, then `orderfulfillmentstatus`), getting 400s.
- Today’s state:
  - Debugger template (backend `backend/app/routers/ebay.py`):
    - Template `"orders"`:
      ```json
      {
        "name": "Orders API - Get Orders",
        "description": "Fetch recent orders",
        "method": "GET",
        "path": "/sell/fulfillment/v1/order",
        "params": { "limit": "1" }
      }
      ```
    - No status/date filter is sent; we rely on eBay’s default time window.
  - Worker/service (`backend/app/services/ebay.py`):
    - `fetch_orders` and the orders sync routine now use this minimal approach (no filter, only `limit`, `offset`, `fieldGroups` for sync).
  - Production test:
    - `GET https://api.ebay.com/sell/fulfillment/v1/order?limit=1` → **200 OK**, `total=0`, `orders=[]`.
    - This confirms our call is valid and authorized, even if there are currently no orders in the default window.

### 2.3. Transactions API – correct Finances host (`apiz.ebay.com`)

- Problem observed:
  - `GET https://api.ebay.com/sell/finances/v1/transaction?limit=1` returned **404** with empty body.
  - Response headers (`server: ebay-proxy-server`, `content-length: 0`) showed this was the generic proxy, not the actual Finances service.
- Root cause:
  - Finances API lives on `apiz.ebay.com` / `apiz.sandbox.ebay.com`, **not** on `api.ebay.com`.
- Fixes implemented:

  1. **Config** (`backend/app/config.py`):

     - Added a dedicated base URL for Finances:

       ```python
       @property
       def ebay_finances_base_url(self) -> str:
           """Base URL for Finances API (uses apiz.* host in production)."""
           if self.EBAY_ENVIRONMENT == "sandbox":
               return "https://apiz.sandbox.ebay.com"
           return "https://apiz.ebay.com"
       ```

  2. **Service** (`backend/app/services/ebay.py`):

     - In `fetch_transactions` changed:

       ```python
       api_url = f"{settings.ebay_api_base_url}/sell/finances/v1/transaction"
       ```

       to:

       ```python
       api_url = f"{settings.ebay_finances_base_url}/sell/finances/v1/transaction"
       ```

  3. **Debugger endpoint** (`backend/app/routers/ebay.py`):

     - For `/ebay/debug` when `api_name == "transactions"`, override `base_url`:

       ```python
       base_url = debugger.base_url
       if api_name == "transactions":
           if env == "sandbox":
               base_url = "https://apiz.sandbox.ebay.com"
           else:
               base_url = "https://apiz.ebay.com"
       ```

  4. **CLI EbayAPIDebugger** (`backend/app/utils/ebay_debugger.py`):

       ```python
       base_url = self.base_url
       if "/sell/finances/" in path:
           if "sandbox" in base_url:
               base_url = "https://apiz.sandbox.ebay.com"
           else:
               base_url = "https://apiz.ebay.com"
       ```

- Result:
  - Next Transactions calls from both the Worker and Debugger will go to `https://apiz.ebay.com/sell/finances/v1/transaction`, eliminating the proxy 404.
  - We still need to capture and analyze the new response after deployment (see TODOs).

### 2.4. Messages – Trading API `GetMyMessages`

- Goal: align the Messages debug template with the real Trading XML API instead of a placeholder REST call.
- Spec (as per user):
  - Endpoint: `POST https://api.ebay.com/ws/api.dll`
  - Headers:
    - `Content-Type: text/xml`
    - `X-EBAY-API-CALL-NAME: GetMyMessages`
    - `X-EBAY-API-SITEID: 0`
    - `X-EBAY-API-COMPATIBILITY-LEVEL: 967`
    - `X-EBAY-API-IAF-TOKEN: <USER_ACCESS_TOKEN_OR_AUTH_TOKEN>`
  - XML body to fetch 5 latest messages, page 1.

#### Changes in `/ebay/debug/templates`

- File: `backend/app/routers/ebay.py`:

  ```python
  "messages": {
      "name": "Messages API - Get My Messages (Trading)",
      "description": "Fetch messages via Trading GetMyMessages",
      "method": "POST",
      "path": "/ws/api.dll",
      "params": {},
  },
  ```

#### Changes in CLI EbayAPIDebugger templates

- File: `backend/app/utils/ebay_debugger.py`:

  ```python
  "messages": {
      "name": "Messages API - Get My Messages (Trading)",
      "method": "POST",
      "path": "/ws/api.dll",
      "params": {},
      "headers": {
          "Content-Type": "text/xml",
          "X-EBAY-API-CALL-NAME": "GetMyMessages",
          "X-EBAY-API-SITEID": "0",
          "X-EBAY-API-COMPATIBILITY-LEVEL": "967"
          # X-EBAY-API-IAF-TOKEN will be injected from access token
      },
      "body": """<?xml version=\"1.0\" encoding=\"utf-8\"?>
  <GetMyMessagesRequest xmlns=\"urn:ebay:apis:eBLBaseComponents\">
    <DetailLevel>ReturnMessages</DetailLevel>
    <ErrorLanguage>en_US</ErrorLanguage>
    <Version>967</Version>
    <WarningLevel>High</WarningLevel>
    <Pagination>
      <EntriesPerPage>5</EntriesPerPage>
      <PageNumber>1</PageNumber>
    </Pagination>
  </GetMyMessagesRequest>""",
      "description": "Get My Messages via Trading GetMyMessages"
  }
  ```

#### Header handling in `/ebay/debug`

- File: `backend/app/routers/ebay.py` (inside `debug_ebay_api`):

  ```python
  request_headers = {
      "Authorization": f"Bearer {debugger.access_token}",
      "Accept": "application/json",
      "Content-Type": "application/json"
  }
  ...
  if headers_dict:
      request_headers.update(headers_dict)

  # Trading API - GetMyMessages uses XML + X-EBAY-API-IAF-TOKEN instead of JSON Bearer
  if template == "messages":
      request_headers["Content-Type"] = "text/xml"
      request_headers["X-EBAY-API-CALL-NAME"] = "GetMyMessages"
      request_headers["X-EBAY-API-SITEID"] = "0"
      request_headers["X-EBAY-API-COMPATIBILITY-LEVEL"] = "967"
      request_headers["X-EBAY-API-IAF-TOKEN"] = debugger.access_token
  ```

#### Header handling in CLI debugger

- File: `backend/app/utils/ebay_debugger.py` (`make_request`):

  ```python
  if headers:
      request_headers.update(headers)

  # Trading API - GetMyMessages uses XML + X-EBAY-API-IAF-TOKEN
  if "/ws/api.dll" in url:
      request_headers.setdefault("X-EBAY-API-IAF-TOKEN", self.access_token)
      request_headers["Content-Type"] = "text/xml"
  ```

- Result:
  - When using the **Messages** template in Debugger or CLI, the request matches the Trading `GetMyMessages` spec (XML over `ws/api.dll` with proper headers).

---

## 3. How to push and deploy (for the next session)

### 3.1. Local checks

- From project root (`C:\dev\ebay-connector-app`):

  ```bash
  # Backend syntax check (Python)
  python -m py_compile backend/app/config.py \
                     backend/app/services/ebay.py \
                     backend/app/utils/ebay_debugger.py \
                     backend/app/routers/ebay.py

  # Optional: run backend tests or FastAPI dev server if available
  ```

- Frontend build (if needed):

  ```bash
  cd frontend
  npm run build
  cd ..
  ```

### 3.2. Git workflow

- On `main`:

  ```bash
  git status
  git diff
  git add <changed files>
  git commit -m "<meaningful message>"
  git push origin main
  ```

- Railway is expected to auto-trigger a deploy on push to `main`.

### 3.3. Verifying production

- After deployment:
  - Open the app frontend.
  - Go to **API Debugger**.
  - Verify:
    - **Identity** template → 200 OK.
    - **Orders** template → 200 OK (`total` may be 0).
    - **Transactions** template → check that URL uses `apiz.ebay.com`; capture response.
    - **Messages** template → confirm that the request is `POST https://api.ebay.com/ws/api.dll` with XML body.

---

## 4. Problems encountered today and how we solved them

1. **Backend IndentationError in `ebay_debugger.py`**:
   - Cause: malformed `templates` dict.
   - Fix: corrected `orders` + `transactions` entries; py_compile now passes.

2. **Orders API 400s on filters**:
   - Cause: invalid filter name/value combinations (`orderStatus`, `orderfulfillmentstatus`).
   - Fix: removed filters for now; use only `limit` (and `offset` in Worker).
   - Result: 200 OK with `total=0` and `orders=[]`.

3. **Transactions API 404 with empty body**:
   - Cause: wrong host (`api.ebay.com` instead of `apiz.ebay.com`).
   - Fix: introduced `ebay_finances_base_url` and routed all Finances calls via `apiz.*` hosts.

4. **Messages template was a placeholder**:
   - Cause: Messages template pointed to a Fulfillment/REST path.
   - Fix: rewired to Trading `GetMyMessages` with XML and appropriate Trading headers.

---

## 5. Open issues / next steps for the next session

1. **Verify Transactions API on `apiz.ebay.com`**
   - After deployment, call Transactions template in Debugger (production).
   - Capture logs from `connect_logs_production_*.txt`.
   - Confirm:
     - URL uses `https://apiz.ebay.com/sell/finances/v1/transaction`.
     - Response is 200/204 or a structured JSON error (not proxy 404).
   - Adjust default `filter` (date range, types) if necessary.

2. **Orders sync Worker integration**
   - Ensure the Worker uses the minimal working query and correctly paginates all orders.
   - Confirm DB writes into orders-related tables via `ebay_db.batch_upsert_orders`.
   - Once data is flowing, consider reintroducing safe filters (`creationdate`/`lastmodifieddate`).

3. **Messages (Trading) behavior**
   - Test the new `GetMyMessages` template:
     - Verify the XML response.
     - Decide how/if to build a Worker or UI around these messages.
   - Trading API currently uses the OAuth access token as IAF token header; confirm this works for this app.

4. **Scope / token verification pass (sanity check)**
   - Re-check that the current production token has:
     - `sell.fulfillment`, `sell.finances`, `sell.inventory`, and base scope.
   - Confirm that Debugger scope guard (on the frontend) no longer produces false "Missing required scopes" warnings.

5. **eBay Operation Registry integration (future)**
   - We already have `backend/app/ebay_operation_registry.py` defining specs for Identity, Orders, Transactions, Inventory, Disputes, etc.
   - Next step (not done today):
     - Implement a `build_rest_request(op_id, ...)` helper.
     - Start using it inside `/ebay/debug` and Workers to centralize method/path/scopes.

---

## 6. Quick checklist for the next session

- [ ] Confirm that the latest changes are deployed to Railway (check last build on main).
- [ ] Run Transactions template in production Debugger; save logs.
- [ ] Run Messages (Trading) template; save logs.
- [ ] If Transactions/Orders look stable, start wiring full background sync flows (Orders, Transactions, Disputes, Inventory).
- [ ] Revisit eBay Operation Registry and plan how to route all REST calls through the registry + builder.

---

**End of session 2025-11-14 – ready for continuation in the next Warp/agent session.**

_Note: This line was touched to test Git integration and pushing from GitHub Desktop._
