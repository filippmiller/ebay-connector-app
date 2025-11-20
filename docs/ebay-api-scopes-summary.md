# eBay Connector App — eBay Authorization & Scopes Summary (Connections Management)

This document summarizes where and how the eBay Connector App builds its OAuth authorization URLs, manages scope sets (backend and frontend), and implements the “Review eBay Authorization Request” flow.

The goal is to make it easy to reason about:

- Where scopes are defined and applied
- How production vs sandbox is handled
- How the UI shows and manipulates scope lists
- Where to update things to move to a final, auditable scope set

---

## 1. Backend: Authorization URL & Scope Selection

### 1.1 Core service: `EbayService.get_authorization_url`

**File:**  
`backend/app/services/ebay.py`

**Role (1–2 sentences):**  
This method constructs the actual eBay OAuth authorization URL, choosing between sandbox and production endpoints, ensuring credentials (client ID, RuName) are set, and building the `scope` query parameter. If no `scopes` are provided, it falls back to a hardcoded default seller-ish scope list.

**Key properties & method:**

```python
class EbayService:
    ...

    @property
    def auth_url(self) -> str:
        is_sandbox = settings.EBAY_ENVIRONMENT == "sandbox"
        return self.sandbox_auth_url if is_sandbox else self.production_auth_url

    @property
    def token_url(self) -> str:
        is_sandbox = settings.EBAY_ENVIRONMENT == "sandbox"
        return self.sandbox_token_url if is_sandbox else self.production_token_url

    def get_authorization_url(
        self,
        redirect_uri: str,
        state: Optional[str] = None,
        scopes: Optional[List[str]] = None,
        environment: str = "production",
    ) -> str:
        """Generate eBay OAuth authorization URL."""
        # Temporarily set environment to get correct credentials
        original_env = settings.EBAY_ENVIRONMENT
        settings.EBAY_ENVIRONMENT = environment

        try:
            if not settings.ebay_client_id:
                ...
            if not settings.ebay_runame:
                ...

            if not scopes:
                scopes = [
                    "https://api.ebay.com/oauth/api_scope",  # Base scope for Identity API (MUST be first)
                    "https://api.ebay.com/oauth/api_scope/sell.account",
                    "https://api.ebay.com/oauth/api_scope/sell.fulfillment",  # For Orders
                    "https://api.ebay.com/oauth/api_scope/sell.finances",    # For Transactions
                    "https://api.ebay.com/oauth/api_scope/sell.inventory",    # For Inventory/Offers
                    "https://api.ebay.com/oauth/api_scope/sell.postorder",   # For Post-Order cases (INR/SNAD)
                    "https://api.ebay.com/oauth/api_scope/commerce.notification.subscription",  # For Notification API
                    # "https://api.ebay.com/oauth/api_scope/trading"  # REMOVED - not activated in app
                ]

            # Ensure base scope is first (required for Identity API)
            base_scope = "https://api.ebay.com/oauth/api_scope"
            if base_scope in scopes:
                scopes.remove(base_scope)
            scopes.insert(0, base_scope)

            # Clean scopes
            scopes = [s.strip() for s in scopes if s.strip()]

            params = {
                "client_id": settings.ebay_client_id,
                "redirect_uri": settings.ebay_runame,
                "response_type": "code",
                "scope": " ".join(scopes),
            }
            if state:
                params["state"] = state

            # Use correct auth URL based on environment
            if environment == "sandbox":
                auth_base_url = self.sandbox_auth_url
            else:
                auth_base_url = self.production_auth_url

            auth_url = f"{auth_base_url}?{urlencode(params)}"
            ...
            return auth_url
        finally:
            # Restore original environment
            settings.EBAY_ENVIRONMENT = original_env
```

**Environment behavior:**

- `environment` argument (`"sandbox"` or `"production"`) controls which auth base URL is used and which credentials are loaded (via `settings.EBAY_ENVIRONMENT`).
- The default scope list is currently identical for both sandbox and production unless a caller explicitly passes scopes.

---

### 1.2 Route that starts the OAuth flow: `/ebay/auth/start`

**File:**  
`backend/app/routers/ebay.py`

**Endpoint:**  
`POST /ebay/auth/start` → `start_ebay_auth`

**Role (1–2 sentences):**  
This is the main backend entry point to start an eBay OAuth connect flow. It chooses the effective scope list by preferring client-provided scopes and, if not provided, loading all active user-consent scopes from the `ebay_scope_definitions` catalog table, then passes that list into `get_authorization_url`.

**Relevant logic (simplified):**

```python
@router.post("/auth/start")
async def start_ebay_auth(
    auth_request: EbayAuthRequest,
    redirect_uri: str = Query(..., description="Redirect URI for OAuth callback"),
    environment: str = Query('production', description="eBay environment: sandbox or production"),
    house_name: Optional[str] = Query(None, description="Human-readable name for this eBay account"),
    purpose: str = Query('BOTH', description="Account purpose: BUYER, SELLER, or BOTH"),
    current_user: User = Depends(get_current_active_user),
):
    """Start eBay OAuth flow.

    If client does not explicitly pass scopes, we default to **all active user-consent scopes**
    from ebay_scope_definitions (grant_type in ['user', 'both']).
    """
    ...
    original_env = settings.EBAY_ENVIRONMENT
    settings.EBAY_ENVIRONMENT = environment

    # State for callback
    state_data = {
        "org_id": current_user.id,
        "nonce": str(uuid.uuid4()),
        "house_name": house_name,
        "purpose": purpose,
        "environment": environment,
    }
    state = json.dumps(state_data)

    # Determine effective scopes: prefer client-provided, otherwise all active user scopes from catalog
    effective_scopes = auth_request.scopes or []
    if not effective_scopes:
        db_session = next(get_db())
        try:
            rows = (
                db_session.query(EbayScopeDefinition)
                .filter(
                    EbayScopeDefinition.is_active == True,  # noqa: E712
                    EbayScopeDefinition.grant_type.in_(["user", "both"]),
                )
                .order_by(EbayScopeDefinition.scope)
                .all()
            )
            effective_scopes = [r.scope for r in rows] if rows else []
        except Exception as e:
            logger.error(f"Failed to load ebay_scope_definitions: {e}")
            # fall back to whatever client sent (empty → EbayService will apply its own defaults)
            effective_scopes = auth_request.scopes or []
        finally:
            db_session.close()

    auth_url = ebay_service.get_authorization_url(
        redirect_uri=redirect_uri,
        state=state,
        scopes=effective_scopes,
        environment=environment,
    )
    ...
    return {"authorization_url": auth_url, "state": state}
```

**Environment logic:**

- Accepts `environment` query param (`"sandbox" | "production"`, default `"production"`).
- Temporarily updates `settings.EBAY_ENVIRONMENT` and stores the chosen environment on the user record.
- Scope selection itself is not environment-specific today (same catalog for sandbox and production).

---

## 2. Backend Scope Catalog & Auditing

### 2.1 `EbayScopeDefinition` model

**File:**  
`backend/app/models_sqlalchemy/models.py`

```python
class EbayScopeDefinition(Base):
    __tablename__ = "ebay_scope_definitions"

    id = Column(String(36), primary_key=True)
    scope = Column(Text, nullable=False, unique=True)
    description = Column(Text, nullable=True)
    grant_type = Column(String(20), nullable=False, default="user")  # 'user', 'client', or 'both'
    is_active = Column(Boolean, nullable=False, default=True)
    meta = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('idx_ebay_scope_definitions_scope', 'scope', unique=True),
        Index('idx_ebay_scope_definitions_grant_type', 'grant_type'),
    )
```

**Role:** Holds the catalog of known eBay scopes, their descriptions, and grant types (`user`, `client`, or `both`). This catalog is used for defaulting user-consent scopes, feeding the frontend, and auditing.

---

### 2.2 Migration and seeded scope list

**File:**  
`backend/alembic/versions/20251114_add_ebay_scope_definitions.py`

**Role:** Creates the `ebay_scope_definitions` table and seeds it with a curated list of scopes (`SCOPES`).

**Excerpt from `SCOPES`:**

```python
SCOPES = [
    # User consent grant scopes
    {
        "scope": "https://api.ebay.com/oauth/api_scope",
        "description": "View public data from eBay",
        "grant_type": "both",  # available for both user-consent and client-credentials
    },
    {
        "scope": "https://api.ebay.com/oauth/api_scope/sell.marketing.readonly",
        "description": "View your eBay marketing activities, such as ad campaigns and listing promotions",
        "grant_type": "user",
    },
    {
        "scope": "https://api.ebay.com/oauth/api_scope/sell.marketing",
        "description": "View and manage your eBay marketing activities, such as ad campaigns and listing promotions",
        "grant_type": "user",
    },
    {
        "scope": "https://api.ebay.com/oauth/api_scope/sell.inventory.readonly",
        "description": "View your inventory and offers",
        "grant_type": "user",
    },
    {
        "scope": "https://api.ebay.com/oauth/api_scope/sell.inventory",
        "description": "View and manage your inventory and offers",
        "grant_type": "user",
    },
    ...,
    {
        "scope": "https://api.ebay.com/oauth/api_scope/commerce.feedback",
        "description": "Allows access to Feedback APIs.",
        "grant_type": "user",
    },
    {
        "scope": "https://api.ebay.com/oauth/api_scope/commerce.shipping",
        "description": "View and manage shipping information",
        "grant_type": "user",
    },
    # Client credentials only scopes
    {
        "scope": "https://api.ebay.com/oauth/api_scope/commerce.feedback.readonly",
        "description": "Allows readonly access to Feedback APIs.",
        "grant_type": "client",
    },
]
```

---

### 2.3 Public endpoints exposing the scope catalog

**File:**  
`backend/app/routers/ebay.py`

**Endpoints:**

- `GET /ebay/scopes` → returns the active catalog scopes (`user`/`both`)
- `GET /ebay/scopes/health` → basic health/summary view

**`/ebay/scopes` implementation:**

```python
@router.get("/scopes")
async def get_ebay_scopes(current_user: User = Depends(get_current_active_user)):
    """Return all active eBay scopes available for user-consent flows."""
    from app.models_sqlalchemy import get_db
    from app.models_sqlalchemy.models import EbayScopeDefinition

    db_session = next(get_db())
    try:
        rows = (
            db_session.query(EbayScopeDefinition)
            .filter(
                EbayScopeDefinition.is_active == True,  # noqa: E712
                EbayScopeDefinition.grant_type.in_(["user", "both"]),
            )
            .order_by(EbayScopeDefinition.scope)
            .all()
        )
        scopes = [
            {
                "scope": r.scope,
                "grant_type": r.grant_type,
                "description": r.description,
            }
            for r in rows
        ]
        return {"scopes": scopes}
    finally:
        db_session.close()
```

The frontend’s Connection page uses this to populate `availableScopes`.

---

### 2.4 Admin scope vs account audit endpoint

**File:**  
`backend/app/routers/admin.py`

**Endpoint:**  
`GET /api/admin/ebay/accounts/scopes` → `get_ebay_accounts_scopes`

**Role:** Returns both:

- `scope_catalog`: all active `user`/`both` scopes from the catalog
- `accounts`: each eBay account’s stored scopes + whether it has the full catalog or which scopes are missing

**Excerpt:**

```python
@router.get("/ebay/accounts/scopes")
async def get_ebay_accounts_scopes(
    current_user: User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    """Return eBay accounts for this org with their stored scopes vs scope catalog."""
    # Load catalog of available scopes (user-consent and both)
    catalog_rows = (
        db.query(EbayScopeDefinition)
        .filter(
            EbayScopeDefinition.is_active == True,  # noqa: E712
            EbayScopeDefinition.grant_type.in_(['user', 'both']),
        )
        .order_by(EbayScopeDefinition.scope)
        .all()
    )
    catalog_scopes = [r.scope for r in catalog_rows]

    # All accounts for current org
    accounts = (
        db.query(EbayAccount)
        .filter(EbayAccount.org_id == current_user.id)
        .order_by(desc(EbayAccount.connected_at))
        .all()
    )

    result_accounts = []
    for account in accounts:
        # All authorizations for this account
        auth_rows = (
            db.query(EbayAuthorization)
            .filter(EbayAuthorization.ebay_account_id == account.id)
            .order_by(EbayAuthorization.created_at.desc())
            .all()
        )
        scopes: list[str] = []
        for auth in auth_rows:
            if auth.scopes:
                scopes.extend(auth.scopes)
        unique_scopes = sorted(set(scopes))
        missing_catalog_scopes = [s for s in catalog_scopes if s not in unique_scopes]
        has_all_catalog_scopes = bool(catalog_scopes) and not missing_catalog_scopes
        ...

    return {
        "scope_catalog": [...],
        "accounts": result_accounts,
    }
```

This is the main “audit” view: catalog vs each account’s authorizations.

---

## 3. Frontend: eBay Connections Management Page

### 3.1 Main page component: `EbayConnectionPage`

**File:**  
`frontend/src/pages/EbayConnectionPage.tsx`

**Role (1–2 sentences):**  
The central admin UI for "eBay Connection Management." It handles connecting/reconnecting accounts, showing connection status, previewing authorization requests, managing accounts and tokens, running syncs, and exposing debugging/terminal views.

---

### 3.2 Default scopes & available scopes

**Default scopes constant (preview fallback):**

```ts
const DEFAULT_SCOPES = [
  'https://api.ebay.com/oauth/api_scope',
  'https://api.ebay.com/oauth/api_scope/sell.account',
  'https://api.ebay.com/oauth/api_scope/sell.fulfillment',
  'https://api.ebay.com/oauth/api_scope/sell.finances',
  'https://api.ebay.com/oauth/api_scope/sell.inventory',
];
```

**Available scopes loaded from backend catalog:**

```ts
// Available scopes loaded from backend catalog
const [availableScopes, setAvailableScopes] = useState<string[]>([]);

const loadAvailableScopes = async () => {
  try {
    const res = await ebayApi.getAvailableScopes();
    const scopes = (res.scopes || []).map((s) => s.scope);
    setAvailableScopes(scopes);
  } catch (err) {
    console.error('Failed to load available eBay scopes:', err);
  }
};
```

- `availableScopes` is the frontend projection of the backend `ebay_scope_definitions` table (active, `user`/`both`).
- `DEFAULT_SCOPES` is used only as a fallback when the backend catalog fails or is empty.

---

### 3.3 Starting a connect flow: `handleConnectEbay`

```ts
const handleConnectEbay = async () => {
  setError('');
  setLoading(true);

  try {
    const redirectUri = `${window.location.origin}/ebay/callback`;
    // For now always initiate auth in production
    const env: 'sandbox' | 'production' = 'production';
    localStorage.setItem('ebay_oauth_environment', env);

    const selectedAcc = accounts.find((a) => a.id === selectedConnectAccountId) || null;
    const houseName = selectedAcc?.house_name || selectedAcc?.username || undefined;

    const response = await ebayApi.startAuth(redirectUri, env, undefined, houseName);
    setPreflightUrl(response.authorization_url);

    // Parse scopes from URL for display
    try {
      const u = new URL(response.authorization_url);
      const scopeStr = (u.searchParams.get('scope') || '').trim();
      setPreflightScopes(scopeStr ? scopeStr.split(' ') : []);
    } catch {}

    setPreflightOpen(true);
  } catch (err) {
    setError(err instanceof Error ? err.message : 'Failed to start eBay authorization');
    setLoading(false);
  }
};
```

- Always initiates **production** auth from this page.
- `preflightUrl` and `preflightScopes` (parsed from the URL's `scope` query param) feed the "Review eBay Authorization Request" modal.

---

### 3.4 "Connection Request Preview" card

This card shows a synthesized view of what will be sent to eBay:

- Environment (sandbox vs production)
- Redirect URI
- Auth URL base (sandbox vs prod)
- Query parameters
- Raw authorization URL

Scopes in this preview come from `availableScopes` (preferred) or `DEFAULT_SCOPES`.

```tsx
<ScrollArea className="h-24 rounded border bg-gray-50 p-3 text-xs font-mono">
  {Array.from(
    new URLSearchParams({
      response_type: 'code',
      redirect_uri: typeof window !== 'undefined' ? `${window.location.origin}/ebay/callback` : '/ebay/callback',
      scope: (availableScopes.length ? availableScopes : DEFAULT_SCOPES).join(' '),
      state: 'generated server-side',
    }).entries(),
  ).map(([key, value]) => (
    <div key={key} className="text-gray-700">
      {key}: <span className="text-gray-900">{value}</span>
    </div>
  ))}
</ScrollArea>

...

const base = environment === 'production'
  ? 'https://auth.ebay.com/oauth2/authorize'
  : 'https://auth.sandbox.ebay.com/oauth2/authorize';
const qs = new URLSearchParams({
  response_type: 'code',
  redirect_uri: typeof window !== 'undefined' ? `${window.location.origin}/ebay/callback` : '/ebay/callback',
  scope: (availableScopes.length ? availableScopes : DEFAULT_SCOPES).join(' '),
  state: 'generated server-side',
  client_id: 'configured server-side',
}).toString();
return `GET ${base}?${qs}`;
```

This is **informational only**: the actual scopes used for the real redirect come from the pre-flight modal actions (see below).

---

## 4. Frontend: "Review eBay Authorization Request" Modal

**File:**  
`frontend/src/pages/EbayConnectionPage.tsx`

**Component:** The `Dialog` labelled "Pre-flight Authorization Modal".

**State used:**

- `preflightUrl: string` — full authorization URL returned from backend `/ebay/auth/start`.
- `preflightScopes: string[]` — scopes parsed from the `scope` query param of `preflightUrl`.
- `extraScopesInput: string` — text area where user can paste additional scopes.
- `availableScopes: string[]` / `DEFAULT_SCOPES` — base scope set for the *final* auth start call.

**UI implementation:**

```tsx
<Dialog open={preflightOpen} onOpenChange={(o) => {
  setPreflightOpen(o);
  if (!o) {
    setLoading(false);
    setPreflightSubmitting(false);
  }
}}>
  <DialogContent className="max-w-3xl max-h-[70vh] overflow-y-auto">
    <DialogHeader>
      <DialogTitle>Review eBay Authorization Request</DialogTitle>
    </DialogHeader>
    <div className="space-y-4 text-sm">
      <div className="p-3 bg-gray-50 rounded border font-mono text-xs overflow-x-auto whitespace-pre-wrap break-words">
        GET {preflightUrl}
      </div>

      <div>
        <div className="font-semibold mb-1">Scopes from URL</div>
        {preflightScopes.length > 0 ? (
          <div className="flex flex-wrap gap-1 max-h-40 overflow-y-auto">
            {preflightScopes.map((s, i) => (
              <span key={i} className="text-xs px-2 py-0.5 border rounded bg-gray-50 break-all">{s}</span>
            ))}
          </div>
        ) : (
          <div className="text-gray-600">(none parsed)</div>
        )}
      </div>

      <div>
        <div className="font-semibold mb-1">Additional scopes (space-separated)</div>
        <textarea
          className="w-full border rounded p-2 font-mono text-xs"
          rows={3}
          placeholder="Paste extra scopes here to request all whitelisted ones"
          value={extraScopesInput}
          onChange={(e) => setExtraScopesInput(e.target.value)}
        />
        <div className="text-xs text-gray-500 mt-1">
          We’ll merge these with the current list and request them in one authorization.
        </div>
      </div>
    </div>

    <DialogFooter>
      <Button
        variant="outline"
        onClick={() => {
          setPreflightOpen(false);
          setLoading(false);
          setPreflightSubmitting(false);
        }}
      >
        Cancel
      </Button>
      {/* Action buttons shown below */}
    </DialogFooter>
  </DialogContent>
</Dialog>
```

**Usability characteristics:**

- Raw URL is shown as a `GET {preflightUrl}` line in a mono, wrapping block.
- Scopes are displayed as individual, wrapped "chips" in a scrollable container (`max-h-40 overflow-y-auto`), so long lines don’t overflow.
- Additional scopes can be pasted as whitespace-separated values.

---

### 4.1 Final scope sets used for redirect

The modal uses **two** buttons for the actual redirect to eBay; both trigger a new `/ebay/auth/start` call with explicit scopes.

#### Button 1: "Request all my scopes"

```tsx
<Button
  variant="outline"
  disabled={preflightSubmitting}
  onClick={async () => {
    try {
      setPreflightSubmitting(true);
      const redirectUri = `${window.location.origin}/ebay/callback`;
      const baseScopes = (availableScopes.length ? availableScopes : DEFAULT_SCOPES);
      const union = Array.from(new Set(baseScopes));
      const { data } = await api.post(
        `/ebay/auth/start?redirect_uri=${encodeURIComponent(redirectUri)}&environment=${environment}`,
        { scopes: union },
      );
      setPreflightOpen(false);
      window.location.assign(data.authorization_url);
    } catch (e) {
      setLoading(false);
      setPreflightSubmitting(false);
    }
  }}
>
  Request all my scopes
</Button>
```

- Uses **only** `availableScopes` (from backend catalog `/ebay/scopes`) or `DEFAULT_SCOPES` if the catalog is empty.
- Does **not** use `preflightScopes` or `extraScopesInput`.
- Guarantees we request the full, admin-curated catalog.

#### Button 2: "Proceed to eBay" (with optional extras)

```tsx
<Button
  disabled={preflightSubmitting}
  onClick={async () => {
    try {
      setPreflightSubmitting(true);
      const redirectUri = `${window.location.origin}/ebay/callback`;
      const baseScopes = (availableScopes.length ? availableScopes : DEFAULT_SCOPES);
      const added = (extraScopesInput || '').trim().split(/\s+/).filter(Boolean);
      const union = added.length > 0
        ? Array.from(new Set([...baseScopes, ...added]))
        : Array.from(new Set(baseScopes));
      const { data } = await api.post(
        `/ebay/auth/start?redirect_uri=${encodeURIComponent(redirectUri)}&environment=${environment}`,
        { scopes: union },
      );
      setPreflightOpen(false);
      window.location.assign(data.authorization_url);
    } catch (e) {
      setLoading(false);
      setPreflightSubmitting(false);
    }
  }}
>
  {preflightSubmitting ? 'Redirecting…' : 'Proceed to eBay'}
</Button>
```

- Always starts from `baseScopes = availableScopes` or `DEFAULT_SCOPES`.
- If the user has typed additional scopes, they are parsed and unioned with `baseScopes`.
- Again, **`preflightUrl` and `preflightScopes` are preview-only**; the actual authorization URL for the redirect is regenerated from this final union of scopes.

---

## 5. Additional Frontend Scope References (Debugger)

### 5.1 Debugger “whitelisted” scope set: `MY_SCOPES`

**File:**  
`frontend/src/components/EbayDebugger.tsx`

```ts
const MY_SCOPES: string[] = [
  'https://api.ebay.com/oauth/api_scope',
  'https://api.ebay.com/oauth/api_scope/sell.marketing.readonly',
  'https://api.ebay.com/oauth/api_scope/sell.marketing',
  'https://api.ebay.com/oauth/api_scope/sell.inventory.readonly',
  'https://api.ebay.com/oauth/api_scope/sell.inventory',
  'https://api.ebay.com/oauth/api_scope/sell.account.readonly',
  'https://api.ebay.com/oauth/api_scope/sell.account',
  'https://api.ebay.com/oauth/api_scope/sell.fulfillment.readonly',
  'https://api.ebay.com/oauth/api_scope/sell.fulfillment',
  'https://api.ebay.com/oauth/api_scope/sell.analytics.readonly',
  'https://api.ebay.com/oauth/api_scope/sell.finances',
  'https://api.ebay.com/oauth/api_scope/sell.payment.dispute',
  'https://api.ebay.com/oauth/api_scope/commerce.identity.readonly',
  'https://api.ebay.com/oauth/api_scope/sell.reputation',
  'https://api.ebay.com/oauth/api_scope/sell.reputation.readonly',
  'https://api.ebay.com/oauth/api_scope/commerce.notification.subscription',
  'https://api.ebay.com/oauth/api_scope/commerce.notification.subscription.readonly',
  'https://api.ebay.com/oauth/api_scope/sell.stores',
  'https://api.ebay.com/oauth/api_scope/sell.stores.readonly',
  'https://api.ebay.com/oauth/scope/sell.edelivery',
  'https://api.ebay.com/oauth/api_scope/commerce.vero',
  'https://api.ebay.com/oauth/api_scope/sell.inventory.mapping',
  'https://api.ebay.com/oauth/api_scope/commerce.message',
  'https://api.ebay.com/oauth/api_scope/commerce.feedback',
  'https://api.ebay.com/oauth/api_scope/commerce.shipping',
];
```

**Reconnect behavior in Debugger:**

```ts
// When reconnect modal opens or scopes change, pre-generate the authorization URL.
// IMPORTANT: always request the full whitelisted scope set, not just the minimal missing scopes,
// so that reconnect from the Debugger never "shrinks" the token to a narrower scope set.
useEffect(() => {
  const gen = async () => {
    if (!showReconnect || reconnectScopes.length === 0) return;
    try {
      const redirectUri = `${window.location.origin}/ebay/callback`;
      const union = Array.from(new Set([...(reconnectScopes || []), ...MY_SCOPES]));
      const { data } = await api.post(
        `/ebay/auth/start?redirect_uri=${encodeURIComponent(redirectUri)}&environment=${environment}`,
        { scopes: union },
      );
      setReconnectUrl(data.authorization_url);
    } catch {
      // ignore
    }
  };
  void gen();
}, [showReconnect, reconnectScopes, environment]);
```

- The Debugger ensures reconnect **always** requests the full `MY_SCOPES` set plus any specifically missing scopes, rather than a reduced minimal set.

### 5.2 Required scopes per Debugger template

```ts
const REQUIRED_SCOPES_BY_TEMPLATE: Record<string, string[]> = {
  identity: ['https://api.ebay.com/oauth/api_scope'],
  orders: ['https://api.ebay.com/oauth/api_scope/sell.fulfillment'],
  transactions: ['https://api.ebay.com/oauth/api_scope/sell.finances'],
  inventory: ['https://api.ebay.com/oauth/api_scope/sell.inventory'],
  offers: ['https://api.ebay.com/oauth/api_scope/sell.inventory'],
  disputes: ['https://api.ebay.com/oauth/api_scope/sell.fulfillment'],
  messages: ['https://api.ebay.com/oauth/api_scope/trading'],
  seller_transactions: ['https://api.ebay.com/oauth/api_scope/trading'],
};
```

These are used to compute "missing scopes" warnings in the Debugger UI for each API template.

---

## 6. Frontend API Wrapper

**File:**  
`frontend/src/api/ebay.ts`

**Relevant method: `ebayApi.startAuth`**

```ts
export const ebayApi = {
  async startAuth(
    redirectUri: string,
    environment: 'sandbox' | 'production' = 'sandbox',
    scopes?: string[],
    houseName?: string,
  ): Promise<{ authorization_url: string; state: string }> {
    const params = new URLSearchParams({
      redirect_uri: redirectUri,
      environment: environment,
    });
    if (houseName) {
      params.set('house_name', houseName);
    }
    const body = scopes ? { scopes } : {};
    const response = await apiClient.post(`/ebay/auth/start?${params}`, body);
    return response.data;
  },
  ...
};
```

This is the thin wrapper used by both the Connection page and the Debugger to initiate `/ebay/auth/start` with or without an explicit `scopes` array.

---

## 7. High-Level Summary

- **Backend auth URL builder** (`backend/app/services/ebay.py`):
  - `EbayService.get_authorization_url` builds the actual eBay OAuth URL.
  - Has a **hardcoded default seller scope list** if no scopes are explicitly passed.
  - Switches sandbox vs production auth endpoints and credentials based on an `environment` argument and `settings.EBAY_ENVIRONMENT`.

- **Backend scope selection at connect start** (`backend/app/routers/ebay.py`):
  - `start_ebay_auth` is the main entry point.
  - If the client passes `scopes`, those are used directly.
  - Otherwise, it loads all active `user`/`both` scopes from `ebay_scope_definitions` and passes them to `get_authorization_url`.

- **Scope catalog and auditing**:
  - `EbayScopeDefinition` + Alembic migration define a DB-backed catalog of scopes (with descriptions & grant types).
  - `GET /ebay/scopes` exposes the catalog’s active user-consent scopes to the frontend as `availableScopes`.
  - `GET /api/admin/ebay/accounts/scopes` compares each account’s stored authorizations to the catalog and reports missing scopes.

- **Frontend “eBay Connection Management” page** (`EbayConnectionPage`):
  - Uses `DEFAULT_SCOPES` only as a fallback and prefers `availableScopes` from `/ebay/scopes` for previews.
  - `handleConnectEbay` always initiates **production** auth, then parses the `scope` query param from the returned URL for display in the pre-flight modal.
  - The "Connection Request Preview" card shows a synthetic request using `availableScopes` or `DEFAULT_SCOPES`.

- **“Review eBay Authorization Request” modal**:
  - Shows the raw `GET {preflightUrl}` line and "Scopes from URL" (parsed from that URL’s `scope` query param), plus an "Additional scopes" textarea.
  - The **actual redirect** always uses a new `/ebay/auth/start` call, computed from `availableScopes`/`DEFAULT_SCOPES` plus any extra scopes, not from the original `preflightUrl`.

- **Debugger + admin tooling**:
  - `MY_SCOPES` in `EbayDebugger` defines a front-end “whitelisted” scope set used for reconnect flows.
  - The Debugger unions required template scopes (`REQUIRED_SCOPES_BY_TEMPLATE`) with `MY_SCOPES` and calls `/ebay/auth/start` with that union, ensuring reconnects do not narrow the token.
  - Admin endpoints expose account vs catalog scopes (`/api/admin/ebay/accounts/scopes`) and token info/logs for deeper audits.
