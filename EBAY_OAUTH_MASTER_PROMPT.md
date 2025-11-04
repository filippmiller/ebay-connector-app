# Master Prompt: eBay OAuth 2.0 Integration from Scratch

## Overview
This guide explains how to implement a complete eBay OAuth 2.0 integration with automatic token refresh, multi-account support, and production-ready architecture. This is based on real implementation that handles token lifecycle, API calls, and user authentication.

## Prerequisites
- eBay Developer Account with Production credentials
- Backend: FastAPI (Python) or similar REST framework
- Frontend: React/TypeScript or similar
- Database: PostgreSQL (for multi-account support)
- Understanding of OAuth 2.0 Authorization Code Grant flow

---

## Part 1: eBay Developer Setup

### Step 1: Get eBay API Credentials
1. Go to https://developer.ebay.com/my/keys
2. Create a Production Application Keyset
3. You'll receive:
   - **Client ID** (App ID)
   - **Client Secret** (Cert ID)
   - **Dev ID**
4. Create a **RuName** (Redirect URL Name):
   - This is eBay's way of whitelisting your OAuth callback URL
   - Format: `your-company-your-app-environment-randomstring`
   - Example: `filipp_miller-filippmi-better-iamftmmqf`
   - The RuName must be configured to redirect to your actual callback URL

### Step 2: Configure OAuth Scopes
Request these scopes for full marketplace functionality:
```
https://api.ebay.com/oauth/api_scope
https://api.ebay.com/oauth/api_scope/sell.account
https://api.ebay.com/oauth/api_scope/sell.fulfillment
https://api.ebay.com/oauth/api_scope/sell.inventory
https://api.ebay.com/oauth/api_scope/sell.finances
https://api.ebay.com/oauth/api_scope/sell.marketing
https://api.ebay.com/oauth/api_scope/sell.payment.dispute
https://api.ebay.com/oauth/api_scope/commerce.identity.readonly
```

---

## Part 2: Database Schema

### Multi-Account Architecture
Design for unlimited eBay accounts per organization:

```sql
-- Organizations (users)
CREATE TABLE users (
    id UUID PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    is_admin BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- eBay Accounts (one org can have many)
CREATE TABLE ebay_accounts (
    id UUID PRIMARY KEY,
    org_id UUID REFERENCES users(id) ON DELETE CASCADE,
    ebay_user_id TEXT NOT NULL,
    username TEXT,
    house_name TEXT NOT NULL,  -- Human-readable identifier like "Warehouse-A"
    purpose TEXT DEFAULT 'BOTH',  -- BUYING, SELLING, or BOTH
    marketplace_id TEXT,  -- e.g., "EBAY_US"
    site_id INTEGER,  -- e.g., 0 for US
    connected_at TIMESTAMP DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(org_id, ebay_user_id),
    UNIQUE(org_id, house_name) WHERE is_active = TRUE
);

-- eBay OAuth Tokens
CREATE TABLE ebay_tokens (
    id UUID PRIMARY KEY,
    ebay_account_id UUID REFERENCES ebay_accounts(id) ON DELETE CASCADE,
    access_token TEXT,  -- Valid for 2 hours
    refresh_token TEXT,  -- Valid for 90+ days
    token_type TEXT DEFAULT 'Bearer',
    expires_at TIMESTAMP,
    last_refreshed_at TIMESTAMP,
    refresh_error TEXT,  -- Store last error for debugging
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Authorization Scopes (track what permissions were granted)
CREATE TABLE ebay_authorizations (
    id UUID PRIMARY KEY,
    ebay_account_id UUID REFERENCES ebay_accounts(id) ON DELETE CASCADE,
    scopes TEXT[],  -- Array of granted scope URLs
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Health Check Events (monitor token validity)
CREATE TABLE ebay_health_events (
    id UUID PRIMARY KEY,
    ebay_account_id UUID REFERENCES ebay_accounts(id) ON DELETE CASCADE,
    checked_at TIMESTAMP DEFAULT NOW(),
    is_healthy BOOLEAN NOT NULL,
    http_status INTEGER,
    ack TEXT,  -- eBay API response status
    error_code TEXT,
    error_message TEXT,
    response_time_ms INTEGER
);

-- Sync Cursors (for incremental data fetching)
CREATE TABLE ebay_sync_cursors (
    id UUID PRIMARY KEY,
    ebay_account_id UUID REFERENCES ebay_accounts(id) ON DELETE CASCADE,
    resource TEXT NOT NULL,  -- e.g., "orders", "messages", "transactions"
    checkpoint JSONB,  -- Store last sync timestamp or pagination token
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(ebay_account_id, resource)
);
```

---

## Part 3: OAuth Flow Implementation

### Backend Service Structure

```python
# config.py
class Settings:
    EBAY_ENVIRONMENT = "production"  # or "sandbox"
    EBAY_PRODUCTION_CLIENT_ID = "your-client-id"
    EBAY_PRODUCTION_CERT_ID = "your-cert-id"
    EBAY_PRODUCTION_DEV_ID = "your-dev-id"
    EBAY_PRODUCTION_RUNAME = "your-runame"
    
    @property
    def ebay_client_id(self):
        return self.EBAY_PRODUCTION_CLIENT_ID if self.EBAY_ENVIRONMENT == "production" else self.EBAY_SANDBOX_CLIENT_ID
    
    @property
    def ebay_cert_id(self):
        return self.EBAY_PRODUCTION_CERT_ID if self.EBAY_ENVIRONMENT == "production" else self.EBAY_SANDBOX_CERT_ID

settings = Settings()
```

### Step 1: Generate Authorization URL

```python
# services/ebay_service.py
import base64
from urllib.parse import urlencode

class EbayService:
    def __init__(self):
        self.production_auth_url = "https://auth.ebay.com/oauth2/authorize"
        self.production_token_url = "https://api.ebay.com/identity/v1/oauth2/token"
    
    def get_authorization_url(self, redirect_uri: str, state: str = None) -> str:
        """
        Generate eBay OAuth authorization URL
        
        Args:
            redirect_uri: Your frontend callback URL (must match RuName configuration)
            state: Optional state parameter for CSRF protection
        
        Returns:
            Authorization URL to redirect user to
        """
        scopes = [
            "https://api.ebay.com/oauth/api_scope",
            "https://api.ebay.com/oauth/api_scope/sell.account",
            "https://api.ebay.com/oauth/api_scope/sell.fulfillment",
            "https://api.ebay.com/oauth/api_scope/sell.inventory",
            "https://api.ebay.com/oauth/api_scope/sell.finances",
            "https://api.ebay.com/oauth/api_scope/sell.marketing",
            "https://api.ebay.com/oauth/api_scope/sell.payment.dispute",
            "https://api.ebay.com/oauth/api_scope/commerce.identity.readonly"
        ]
        
        params = {
            "client_id": settings.ebay_client_id,
            "redirect_uri": settings.ebay_runame,  # Use RuName, not actual URL
            "response_type": "code",
            "scope": " ".join(scopes)
        }
        
        if state:
            params["state"] = state
        
        return f"{self.production_auth_url}?{urlencode(params)}"
```

### Step 2: Exchange Authorization Code for Tokens

```python
async def exchange_code_for_token(self, code: str, redirect_uri: str) -> dict:
    """
    Exchange authorization code for access and refresh tokens
    
    Args:
        code: Authorization code from eBay callback
        redirect_uri: Same redirect_uri used in authorization request
    
    Returns:
        {
            "access_token": "v^1.1#i^1#...",
            "refresh_token": "v^1.1#i^1#...",
            "expires_in": 7200,  # 2 hours in seconds
            "token_type": "Bearer"
        }
    """
    # Create Basic Auth header: base64(client_id:client_secret)
    credentials = f"{settings.ebay_client_id}:{settings.ebay_cert_id}"
    auth_header = base64.b64encode(credentials.encode()).decode()
    
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Basic {auth_header}"
    }
    
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.ebay_runame
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            self.production_token_url,
            headers=headers,
            data=data
        )
        
        if response.status_code != 200:
            raise Exception(f"Token exchange failed: {response.text}")
        
        return response.json()
```

### Step 3: Refresh Access Token (Critical!)

```python
async def refresh_access_token(self, refresh_token: str) -> dict:
    """
    Refresh expired access token using refresh token
    
    IMPORTANT: Access tokens expire after 2 hours
    Refresh tokens are valid for 90+ days
    
    Args:
        refresh_token: Valid refresh token
    
    Returns:
        Same format as exchange_code_for_token
    """
    credentials = f"{settings.ebay_client_id}:{settings.ebay_cert_id}"
    auth_header = base64.b64encode(credentials.encode()).decode()
    
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Basic {auth_header}"
    }
    
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "scope": " ".join([
            "https://api.ebay.com/oauth/api_scope",
            "https://api.ebay.com/oauth/api_scope/sell.account",
            "https://api.ebay.com/oauth/api_scope/sell.fulfillment",
            "https://api.ebay.com/oauth/api_scope/sell.inventory",
            "https://api.ebay.com/oauth/api_scope/sell.finances"
        ])
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            self.production_token_url,
            headers=headers,
            data=data
        )
        
        if response.status_code != 200:
            raise Exception(f"Token refresh failed: {response.text}")
        
        return response.json()
```

### Step 4: Save Tokens to Database

```python
def save_tokens(self, db: Session, account_id: str, access_token: str, 
                refresh_token: str, expires_in: int):
    """
    Save or update tokens for an eBay account
    
    Args:
        account_id: UUID of ebay_accounts record
        access_token: New access token
        refresh_token: New refresh token (may be same as old one)
        expires_in: Seconds until access token expires (typically 7200)
    """
    from datetime import datetime, timedelta
    
    expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
    
    # Find existing token record
    token = db.query(EbayToken).filter(
        EbayToken.ebay_account_id == account_id
    ).first()
    
    if token:
        # Update existing
        token.access_token = access_token
        token.refresh_token = refresh_token
        token.expires_at = expires_at
        token.last_refreshed_at = datetime.utcnow()
        token.refresh_error = None  # Clear any previous errors
    else:
        # Create new
        token = EbayToken(
            id=str(uuid.uuid4()),
            ebay_account_id=account_id,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
            last_refreshed_at=datetime.utcnow()
        )
        db.add(token)
    
    db.commit()
```

---

## Part 4: Automatic Token Refresh (Critical!)

### Background Worker Implementation

**Key Concept:** Access tokens expire after 2 hours. You MUST refresh them proactively before they expire to avoid API call failures.

```python
# workers/token_refresh_worker.py
import asyncio
from datetime import datetime, timedelta

async def run_token_refresh_worker_loop():
    """
    Background worker that runs every 10 minutes
    Refreshes tokens that will expire in the next 5 minutes
    """
    while True:
        try:
            await asyncio.sleep(600)  # 10 minutes
            
            logger.info("Starting token refresh worker...")
            
            # Get database session
            db = SessionLocal()
            
            try:
                # Find tokens expiring in next 5 minutes
                threshold = datetime.utcnow() + timedelta(minutes=5)
                
                tokens = db.query(EbayToken).join(EbayAccount).filter(
                    EbayAccount.is_active == True,
                    EbayToken.expires_at < threshold,
                    EbayToken.refresh_token.isnot(None)
                ).all()
                
                logger.info(f"Found {len(tokens)} tokens to refresh")
                
                for token in tokens:
                    try:
                        # Refresh the token
                        new_token_data = await ebay_service.refresh_access_token(
                            token.refresh_token
                        )
                        
                        # Save new tokens
                        ebay_account_service.save_tokens(
                            db,
                            token.ebay_account_id,
                            new_token_data["access_token"],
                            new_token_data.get("refresh_token", token.refresh_token),
                            new_token_data["expires_in"]
                        )
                        
                        logger.info(f"Refreshed token for account {token.ebay_account_id}")
                        
                    except Exception as e:
                        logger.error(f"Failed to refresh token for {token.ebay_account_id}: {e}")
                        
                        # Store error in database
                        token.refresh_error = str(e)
                        db.commit()
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Token refresh worker failed: {e}")
```

### Integrate Worker into App Startup

```python
# main.py
from fastapi import FastAPI
import asyncio

app = FastAPI()

@app.on_event("startup")
async def startup_event():
    logger.info("Starting background workers...")
    
    # Import workers
    from app.workers import run_token_refresh_worker_loop
    
    # Start as background task
    asyncio.create_task(run_token_refresh_worker_loop())
    logger.info("✅ Token refresh worker started (runs every 10 minutes)")
```

---

## Part 5: API Endpoints

### Connect eBay Account

```python
# routers/ebay.py
@router.get("/connect")
async def connect_ebay(
    current_user: User = Depends(get_current_user)
):
    """
    Step 1: Generate authorization URL and redirect user to eBay
    """
    # Generate state for CSRF protection
    state = str(uuid.uuid4())
    
    # Store state in session or database for validation
    
    # Generate authorization URL
    auth_url = ebay_service.get_authorization_url(
        redirect_uri=f"{FRONTEND_URL}/ebay/callback",
        state=state
    )
    
    return {"authorization_url": auth_url}
```

### OAuth Callback Handler

```python
@router.get("/callback")
async def ebay_callback(
    code: str,
    state: str = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Step 2: Handle OAuth callback from eBay
    Exchange code for tokens and create account record
    """
    # Validate state (CSRF protection)
    # ... validate state matches what you stored ...
    
    # Exchange code for tokens
    token_data = await ebay_service.exchange_code_for_token(
        code=code,
        redirect_uri=settings.ebay_runame
    )
    
    # Get eBay user info
    ebay_user_id = await ebay_service.get_ebay_user_id(token_data["access_token"])
    ebay_username = await ebay_service.get_ebay_username(token_data["access_token"])
    
    # Create or update eBay account
    account = EbayAccount(
        id=str(uuid.uuid4()),
        org_id=current_user.id,
        ebay_user_id=ebay_user_id,
        username=ebay_username,
        house_name=f"Account-{ebay_username}",  # Or let user customize
        purpose="BOTH",
        marketplace_id="EBAY_US",
        site_id=0,
        is_active=True
    )
    db.add(account)
    db.commit()
    
    # Save tokens
    ebay_account_service.save_tokens(
        db,
        account.id,
        token_data["access_token"],
        token_data["refresh_token"],
        token_data["expires_in"]
    )
    
    return {"status": "connected", "account_id": account.id}
```

---

## Part 6: Making API Calls

### Get Valid Access Token

```python
async def get_valid_access_token(db: Session, account_id: str) -> str:
    """
    Get a valid access token, refreshing if necessary
    
    This is the key function to use before ANY eBay API call
    """
    token = db.query(EbayToken).filter(
        EbayToken.ebay_account_id == account_id
    ).first()
    
    if not token:
        raise Exception("No token found for account")
    
    # Check if token expires in next 5 minutes
    if token.expires_at < datetime.utcnow() + timedelta(minutes=5):
        logger.info(f"Token expiring soon, refreshing for account {account_id}")
        
        # Refresh token
        new_token_data = await ebay_service.refresh_access_token(token.refresh_token)
        
        # Save new tokens
        ebay_account_service.save_tokens(
            db,
            account_id,
            new_token_data["access_token"],
            new_token_data.get("refresh_token", token.refresh_token),
            new_token_data["expires_in"]
        )
        
        return new_token_data["access_token"]
    
    return token.access_token
```

### Example: Fetch Orders

```python
async def fetch_orders(db: Session, account_id: str) -> dict:
    """
    Fetch orders from eBay Fulfillment API
    """
    # Get valid token
    access_token = await get_valid_access_token(db, account_id)
    
    # Get account details for marketplace
    account = db.query(EbayAccount).filter(EbayAccount.id == account_id).first()
    
    # Make API call
    headers = {
        "Authorization": f"Bearer {access_token}",
        "X-EBAY-C-MARKETPLACE-ID": account.marketplace_id or "EBAY_US",
        "Content-Type": "application/json"
    }
    
    url = "https://api.ebay.com/sell/fulfillment/v1/order"
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        
        if response.status_code == 401:
            # Token invalid, force refresh and retry
            logger.warning("Got 401, forcing token refresh")
            access_token = await force_refresh_token(db, account_id)
            headers["Authorization"] = f"Bearer {access_token}"
            response = await client.get(url, headers=headers)
        
        response.raise_for_status()
        return response.json()
```

---

## Part 7: Frontend Integration

### React Component Example

```typescript
// pages/EbayConnect.tsx
import { useState } from 'react';
import axios from 'axios';

export function EbayConnect() {
  const [connecting, setConnecting] = useState(false);
  
  const handleConnect = async () => {
    setConnecting(true);
    
    try {
      // Get authorization URL from backend
      const response = await axios.get('/api/ebay/connect', {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        }
      });
      
      // Redirect user to eBay
      window.location.href = response.data.authorization_url;
      
    } catch (error) {
      console.error('Failed to connect:', error);
      setConnecting(false);
    }
  };
  
  return (
    <div>
      <h2>Connect eBay Account</h2>
      <button onClick={handleConnect} disabled={connecting}>
        {connecting ? 'Connecting...' : 'Connect to eBay'}
      </button>
    </div>
  );
}
```

### OAuth Callback Handler

```typescript
// pages/EbayCallback.tsx
import { useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import axios from 'axios';

export function EbayCallback() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  
  useEffect(() => {
    const handleCallback = async () => {
      const code = searchParams.get('code');
      const state = searchParams.get('state');
      
      if (!code) {
        console.error('No authorization code received');
        navigate('/dashboard');
        return;
      }
      
      try {
        // Send code to backend
        await axios.get(`/api/ebay/callback?code=${code}&state=${state}`, {
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('access_token')}`
          }
        });
        
        // Success! Redirect to dashboard
        navigate('/dashboard?connected=true');
        
      } catch (error) {
        console.error('OAuth callback failed:', error);
        navigate('/dashboard?error=connection_failed');
      }
    };
    
    handleCallback();
  }, [searchParams, navigate]);
  
  return <div>Connecting to eBay...</div>;
}
```

---

## Part 8: Critical Implementation Details

### Token Lifecycle Summary

1. **Initial Connection:**
   - User clicks "Connect to eBay"
   - Backend generates authorization URL
   - User redirects to eBay, logs in, grants permissions
   - eBay redirects back with authorization code
   - Backend exchanges code for access_token (2hr) + refresh_token (90+ days)

2. **Token Storage:**
   - Store both tokens in database
   - Store expiration timestamp (current_time + 7200 seconds)
   - NEVER expose tokens in API responses or logs

3. **Token Refresh:**
   - Background worker runs every 10 minutes
   - Finds tokens expiring in next 5 minutes
   - Calls refresh endpoint with refresh_token
   - Updates access_token and expiration time
   - Refresh_token may or may not change (eBay decides)

4. **API Call Pattern:**
   - Before EVERY API call, check token expiration
   - If expires in < 5 minutes, refresh first
   - If API returns 401, force refresh and retry once
   - Never retry more than once to avoid loops

### Common Pitfalls

1. **RuName vs Redirect URI:**
   - eBay uses RuName (a string identifier) instead of actual URLs
   - You configure RuName in eBay Developer Portal to point to your callback URL
   - In OAuth requests, use RuName, not the actual URL

2. **Token Expiration:**
   - Access tokens expire EXACTLY after 2 hours
   - Don't wait until expiration - refresh 5 minutes early
   - If you miss the window, API calls will fail with 401

3. **Refresh Token Rotation:**
   - Sometimes eBay returns a NEW refresh_token when you refresh
   - Always save the new refresh_token if provided
   - If not provided, keep using the old one

4. **Scope Management:**
   - Request all scopes you need upfront
   - Can't add scopes later without re-authorization
   - Store granted scopes in database for debugging

5. **Multi-Account Support:**
   - One user can connect multiple eBay accounts
   - Each account has its own tokens
   - Use house_name for human-readable identification
   - Enforce uniqueness on (org_id, ebay_user_id)

### Security Best Practices

1. **Never Log Tokens:**
   ```python
   # BAD
   logger.info(f"Token: {access_token}")
   
   # GOOD
   logger.info(f"Token: {access_token[:4]}...{access_token[-4:]}")
   ```

2. **Use HTTPS Only:**
   - All OAuth redirects must use HTTPS in production
   - eBay will reject HTTP callback URLs

3. **Validate State Parameter:**
   - Generate random state in authorization request
   - Validate it matches in callback
   - Prevents CSRF attacks

4. **Store Tokens Securely:**
   - Encrypt tokens at rest if possible
   - Use database-level encryption
   - Restrict database access

---

## Part 9: Testing Strategy

### Local Development

1. **Use Sandbox First:**
   ```python
   EBAY_ENVIRONMENT = "sandbox"
   EBAY_SANDBOX_CLIENT_ID = "your-sandbox-client-id"
   ```

2. **Test Token Refresh:**
   - Set short expiration times for testing
   - Manually trigger refresh worker
   - Verify tokens update correctly

3. **Test 401 Handling:**
   - Invalidate token manually
   - Make API call
   - Verify automatic refresh and retry

### Production Deployment

1. **Monitor Token Health:**
   - Log all refresh attempts
   - Alert on refresh failures
   - Track token expiration times

2. **Health Check Endpoint:**
   ```python
   @router.get("/health")
   async def check_ebay_health(account_id: str, db: Session):
       token = get_token(db, account_id)
       
       return {
           "account_id": account_id,
           "token_expires_at": token.expires_at,
           "expires_in_minutes": (token.expires_at - datetime.utcnow()).total_seconds() / 60,
           "last_refresh": token.last_refreshed_at,
           "status": "healthy" if token.expires_at > datetime.utcnow() else "expired"
       }
   ```

---

## Part 10: Complete Prompt for AI Assistant

**Use this prompt to recreate the entire system:**

```
I need you to implement a complete eBay OAuth 2.0 integration with the following requirements:

ARCHITECTURE:
- Backend: FastAPI (Python 3.12+) with PostgreSQL database
- Frontend: React with TypeScript
- Multi-account support: One user can connect unlimited eBay accounts
- Each account has a "house_name" (human-readable identifier like "Warehouse-A")

DATABASE SCHEMA:
Create these tables:
1. users (id, email, password_hash, is_admin)
2. ebay_accounts (id, org_id, ebay_user_id, username, house_name, marketplace_id, site_id, is_active)
3. ebay_tokens (id, ebay_account_id, access_token, refresh_token, expires_at, last_refreshed_at, refresh_error)
4. ebay_authorizations (id, ebay_account_id, scopes[])
5. ebay_health_events (id, ebay_account_id, checked_at, is_healthy, error_message)

OAUTH FLOW:
1. Generate authorization URL with these scopes:
   - https://api.ebay.com/oauth/api_scope
   - https://api.ebay.com/oauth/api_scope/sell.account
   - https://api.ebay.com/oauth/api_scope/sell.fulfillment
   - https://api.ebay.com/oauth/api_scope/sell.inventory
   - https://api.ebay.com/oauth/api_scope/sell.finances

2. Handle OAuth callback:
   - Exchange authorization code for tokens
   - Get eBay user ID and username
   - Create ebay_accounts record
   - Save tokens with expiration (access_token expires in 2 hours)

3. Implement token refresh:
   - Access tokens expire after 2 hours
   - Refresh tokens valid for 90+ days
   - Create background worker that runs every 10 minutes
   - Refresh tokens that expire in next 5 minutes
   - Store refresh errors in database

BACKGROUND WORKER:
Create a worker that:
- Runs every 10 minutes as asyncio task
- Finds all active accounts with tokens expiring in < 5 minutes
- Calls eBay token refresh endpoint
- Updates tokens in database
- Logs all refresh attempts and errors

API ENDPOINTS:
1. GET /ebay/connect - Generate authorization URL
2. GET /ebay/callback?code=XXX - Handle OAuth callback
3. GET /ebay-accounts - List all accounts for current user
4. POST /ebay-accounts/{id}/refresh-token - Force refresh token
5. GET /ebay-accounts/{id}/health - Check token health

CRITICAL REQUIREMENTS:
- Use eBay Production environment (not sandbox)
- Use RuName (not direct callback URL) in OAuth requests
- Refresh tokens 5 minutes BEFORE expiration
- Handle 401 errors by refreshing token and retrying once
- Never log full tokens (only first/last 4 chars)
- Enforce unique constraint on (org_id, house_name) for active accounts
- Store all granted scopes in ebay_authorizations table

FRONTEND:
- Login page with email/password
- "Connect eBay Account" button that redirects to eBay
- OAuth callback page that handles the redirect
- Dashboard showing all connected accounts with:
  - House name
  - eBay username
  - Connection status
  - Token expiration time
  - Last refresh time

TESTING:
- Verify token refresh works automatically
- Test 401 handling and retry logic
- Verify multi-account support
- Test token expiration edge cases

Provide complete, production-ready code with proper error handling, logging, and security best practices.
```

---

## Summary

This master prompt captures the complete eBay OAuth integration including:
- ✅ OAuth 2.0 Authorization Code Grant flow
- ✅ Token lifecycle management (2-hour access tokens, 90-day refresh tokens)
- ✅ Automatic token refresh with background workers
- ✅ Multi-account architecture
- ✅ Database schema for production use
- ✅ Security best practices
- ✅ Error handling and retry logic
- ✅ Frontend integration
- ✅ Testing strategy

The key insight is that eBay's OAuth is standard OAuth 2.0, but with critical details:
1. Access tokens expire after EXACTLY 2 hours
2. Must refresh proactively (5 min before expiration)
3. RuName is eBay's way of whitelisting callback URLs
4. Refresh tokens can rotate (save new one if provided)
5. Background workers are essential for production reliability
