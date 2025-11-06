import base64
import httpx
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from urllib.parse import urlencode
from fastapi import HTTPException, status
from app.config import settings
from app.models.ebay import EbayTokenResponse
from app.services.database import db
from app.utils.logger import logger, ebay_logger

ORDERS_PAGE_LIMIT = 200          # Fulfillment API max
TRANSACTIONS_PAGE_LIMIT = 200    # Finances API max
DISPUTES_PAGE_LIMIT = 100        # Fulfillment API max
OFFERS_PAGE_LIMIT = 100          # Inventory API max
MESSAGES_HEADERS_LIMIT = 200     # Trading API max for headers
MESSAGES_BODIES_BATCH = 10       # Trading API hard limit for bodies

ORDERS_CONCURRENCY = 6
TRANSACTIONS_CONCURRENCY = 5
DISPUTES_CONCURRENCY = 5
OFFERS_CONCURRENCY = 6
MESSAGES_CONCURRENCY = 5


class EbayService:
    
    def __init__(self):
        self.sandbox_auth_url = "https://auth.sandbox.ebay.com/oauth2/authorize"
        self.sandbox_token_url = "https://api.sandbox.ebay.com/identity/v1/oauth2/token"
        
        self.production_auth_url = "https://auth.ebay.com/oauth2/authorize"
        self.production_token_url = "https://api.ebay.com/identity/v1/oauth2/token"
    
    @property
    def auth_url(self) -> str:
        is_sandbox = settings.EBAY_ENVIRONMENT == "sandbox"
        return self.sandbox_auth_url if is_sandbox else self.production_auth_url
    
    @property
    def token_url(self) -> str:
        is_sandbox = settings.EBAY_ENVIRONMENT == "sandbox"
        return self.sandbox_token_url if is_sandbox else self.production_token_url
    
    def get_authorization_url(self, redirect_uri: str, state: Optional[str] = None, scopes: Optional[List[str]] = None) -> str:
        if not settings.ebay_client_id:
            ebay_logger.log_ebay_event(
                "authorization_url_error",
                "eBay Client ID not configured",
                status="error",
                error="EBAY_CLIENT_ID not set in environment"
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="eBay credentials not configured"
            )
        
        if not settings.ebay_runame:
            ebay_logger.log_ebay_event(
                "authorization_url_error",
                "eBay RuName not configured",
                status="error",
                error="EBAY_RUNAME not set in environment"
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="eBay RuName not configured"
            )
        
        if not scopes:
            scopes = [
                "https://api.ebay.com/oauth/api_scope",  # Base scope for Identity API
                "https://api.ebay.com/oauth/api_scope/sell.account",
                "https://api.ebay.com/oauth/api_scope/sell.fulfillment",  # For Orders
                "https://api.ebay.com/oauth/api_scope/sell.finances",  # For Transactions
                "https://api.ebay.com/oauth/api_scope/sell.inventory",  # For Inventory/Offers
                # "https://api.ebay.com/oauth/api_scope/trading"  # REMOVED - not activated in app, use commerce.message for Messages API instead
            ]
        
        params = {
            "client_id": settings.ebay_client_id,
            "redirect_uri": settings.ebay_runame,
            "response_type": "code",
            "scope": " ".join(scopes)
        }
        
        if state:
            params["state"] = state
        
        auth_url = f"{self.auth_url}?{urlencode(params)}"
        
        ebay_logger.log_ebay_event(
            "authorization_url_generated",
            f"Generated eBay authorization URL ({settings.EBAY_ENVIRONMENT}) with RuName: {settings.ebay_runame}",
            request_data={
                "environment": settings.EBAY_ENVIRONMENT,
                "redirect_uri": settings.ebay_runame,
                "frontend_callback": redirect_uri,
                "scopes": scopes,
                "state": state
            },
            status="success"
        )
        
        logger.info(f"Generated eBay {settings.EBAY_ENVIRONMENT} authorization URL with RuName: {settings.ebay_runame} (frontend callback: {redirect_uri})")
        return auth_url
    
    async def exchange_code_for_token(self, code: str, redirect_uri: str) -> EbayTokenResponse:
        if not settings.ebay_client_id or not settings.ebay_cert_id:
            ebay_logger.log_ebay_event(
                "token_exchange_error",
                "eBay credentials not configured",
                status="error",
                error="EBAY_CLIENT_ID or EBAY_CERT_ID not set"
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="eBay credentials not configured"
            )
        
        credentials = f"{settings.ebay_client_id}:{settings.ebay_cert_id}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {encoded_credentials}"
        }
        
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": settings.ebay_runame
        }
        
        ebay_logger.log_ebay_event(
            "token_exchange_request",
            f"Exchanging authorization code for access token ({settings.EBAY_ENVIRONMENT})",
            request_data={
                "environment": settings.EBAY_ENVIRONMENT,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
                "code": code[:10] + "..." if len(code) > 10 else code,
                "client_id": settings.ebay_client_id
            }
        )
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.token_url,
                    headers=headers,
                    data=data,
                    timeout=30.0
                )
                
                ebay_logger.log_ebay_event(
                    "token_exchange_response",
                    f"Received token exchange response with status {response.status_code}",
                    response_data={
                        "status_code": response.status_code,
                        "response_body": response.text
                    }
                )
                
                if response.status_code != 200:
                    error_detail = response.text
                    ebay_logger.log_ebay_event(
                        "token_exchange_failed",
                        f"Token exchange failed with status {response.status_code}",
                        response_data={"error": error_detail},
                        status="error",
                        error=error_detail
                    )
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Failed to exchange code for token: {error_detail}"
                    )
                
                token_data = response.json()
                
                ebay_logger.log_ebay_event(
                    "token_exchange_success",
                    "Successfully obtained eBay access token",
                    response_data={
                        "access_token": token_data.get("access_token"),
                        "token_type": token_data.get("token_type"),
                        "expires_in": token_data.get("expires_in"),
                        "has_refresh_token": "refresh_token" in token_data
                    },
                    status="success"
                )
                
                logger.info("Successfully exchanged authorization code for eBay access token")
                
                return EbayTokenResponse(**token_data)
                
        except httpx.RequestError as e:
            error_msg = f"HTTP request failed: {str(e)}"
            ebay_logger.log_ebay_event(
                "token_exchange_error",
                "HTTP request error during token exchange",
                status="error",
                error=error_msg
            )
            logger.error(error_msg)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_msg
            )
    
    async def refresh_access_token(self, refresh_token: str) -> EbayTokenResponse:
        if not settings.ebay_client_id or not settings.ebay_cert_id:
            ebay_logger.log_ebay_event(
                "token_refresh_error",
                "eBay credentials not configured",
                status="error",
                error="EBAY_CLIENT_ID or EBAY_CERT_ID not set"
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="eBay credentials not configured"
            )
        
        credentials = f"{settings.ebay_client_id}:{settings.ebay_cert_id}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {encoded_credentials}"
        }
        
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token
        }
        
        ebay_logger.log_ebay_event(
            "token_refresh_request",
            "Refreshing eBay access token",
            request_data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token
            }
        )
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.token_url,
                    headers=headers,
                    data=data,
                    timeout=30.0
                )
                
                if response.status_code != 200:
                    error_detail = response.text
                    ebay_logger.log_ebay_event(
                        "token_refresh_failed",
                        f"Token refresh failed with status {response.status_code}",
                        response_data={"error": error_detail},
                        status="error",
                        error=error_detail
                    )
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Failed to refresh token: {error_detail}"
                    )
                
                token_data = response.json()
                
                ebay_logger.log_ebay_event(
                    "token_refresh_success",
                    "Successfully refreshed eBay access token",
                    response_data={
                        "access_token": token_data.get("access_token"),
                        "expires_in": token_data.get("expires_in")
                    },
                    status="success"
                )
                
                logger.info("Successfully refreshed eBay access token")
                
                return EbayTokenResponse(**token_data)
                
        except httpx.RequestError as e:
            error_msg = f"HTTP request failed: {str(e)}"
            ebay_logger.log_ebay_event(
                "token_refresh_error",
                "HTTP request error during token refresh",
                status="error",
                error=error_msg
            )
            logger.error(error_msg)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_msg
            )
    
    def save_user_tokens(self, user_id: str, token_response: EbayTokenResponse):
        expires_at = datetime.utcnow() + timedelta(seconds=token_response.expires_in)
        
        updates = {
            "ebay_connected": True,
            "ebay_access_token": token_response.access_token,
            "ebay_refresh_token": token_response.refresh_token,
            "ebay_token_expires_at": expires_at,
            "ebay_environment": settings.EBAY_ENVIRONMENT
        }
        
        db.update_user(user_id, updates)
        
        ebay_logger.log_ebay_event(
            "user_tokens_saved",
            f"Saved eBay tokens for user {user_id}",
            request_data={
                "user_id": user_id,
                "expires_at": expires_at.isoformat()
            },
            status="success"
        )
        
        logger.info(f"Saved eBay tokens for user: {user_id}")
    
    async def fetch_orders(self, access_token: str, filter_params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Fetch orders from eBay Fulfillment API
        """
        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="eBay access token required"
            )
        
        api_url = f"{settings.ebay_api_base_url}/sell/fulfillment/v1/order"
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        params = filter_params or {}
        
        ebay_logger.log_ebay_event(
            "fetch_orders_request",
            f"Fetching orders from eBay ({settings.EBAY_ENVIRONMENT})",
            request_data={
                "environment": settings.EBAY_ENVIRONMENT,
                "api_url": api_url,
                "params": params
            }
        )
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    api_url,
                    headers=headers,
                    params=params,
                    timeout=30.0
                )
                
                if response.status_code != 200:
                    error_detail = response.text
                    try:
                        error_json = response.json()
                        error_detail = str(error_json)
                        logger.error(f"Orders API error {response.status_code}: {error_json}")
                    except:
                        logger.error(f"Orders API error {response.status_code}: {error_detail}")
                    ebay_logger.log_ebay_event(
                        "fetch_orders_failed",
                        f"Failed to fetch orders: {response.status_code}",
                        response_data={"error": error_detail},
                        status="error",
                        error=error_detail
                    )
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=f"Failed to fetch orders: {error_detail}"
                    )
                
                orders_data = response.json()
                
                ebay_logger.log_ebay_event(
                    "fetch_orders_success",
                    f"Successfully fetched {orders_data.get('total', 0)} orders from eBay",
                    response_data={
                        "total_orders": orders_data.get('total', 0),
                        "orders_count": len(orders_data.get('orders', []))
                    },
                    status="success"
                )
                
                logger.info(f"Successfully fetched {orders_data.get('total', 0)} orders from eBay")
                
                return orders_data
                
        except httpx.RequestError as e:
            error_msg = f"HTTP request failed: {str(e)}"
            ebay_logger.log_ebay_event(
                "fetch_orders_error",
                "HTTP request error during orders fetch",
                status="error",
                error=error_msg
            )
            logger.error(error_msg)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_msg
            )
    
    async def get_user_identity(self, access_token: str) -> Dict[str, Any]:
        """
        Get eBay user identity (username, userId) from access token using Identity API
        """
        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="eBay access token required"
            )
        
        api_url = f"{settings.ebay_api_base_url}/identity/v1/oauth2/userinfo"
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json"
        }
        
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=5.0)) as client:
                response = await client.get(api_url, headers=headers)
                
                logger.info(f"Identity API response status: {response.status_code}")
                logger.info(f"Identity API response headers: {dict(response.headers)}")
                
                if response.status_code != 200:
                    error_detail = response.text
                    try:
                        error_json = response.json()
                        error_detail = str(error_json)
                        logger.error(f"Identity API error {response.status_code}: {error_json}")
                    except:
                        logger.error(f"Identity API error {response.status_code}: {error_detail}")
                    logger.warning(f"Failed to get user identity: {response.status_code} - {error_detail}")
                    return {"username": None, "userId": None, "error": error_detail}
                
                # Log raw response for debugging
                response_text = response.text
                logger.info(f"Identity API raw response: {response_text[:500]}")  # First 500 chars
                
                try:
                    identity_data = response.json()
                    logger.info(f"Identity API parsed JSON: {identity_data}")
                except Exception as json_error:
                    logger.error(f"Failed to parse Identity API response as JSON: {json_error}, raw: {response_text[:200]}")
                    return {"username": None, "userId": None, "error": f"Invalid JSON response: {str(json_error)}"}
                
                # eBay Identity API returns user_id (not userId) and username
                username = identity_data.get("username")
                user_id = identity_data.get("user_id") or identity_data.get("userId")
                
                logger.info(f"Extracted from Identity API - username: {username}, userId: {user_id}")
                
                return {
                    "username": username,
                    "userId": user_id,
                    "accountType": identity_data.get("accountType"),
                    "registrationMarketplaceId": identity_data.get("registrationMarketplaceId"),
                    "raw_response": identity_data  # Include for debugging
                }
        except Exception as e:
            logger.error(f"Error getting user identity: {str(e)}", exc_info=True)
            return {"username": None, "userId": None, "error": str(e)}

    async def fetch_transactions(self, access_token: str, filter_params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Fetch transaction records from eBay Finances API
        By default, fetches transactions from the last 90 days
        
        FIXED: Use RSQL filter format: filter=transactionDate:[...] (correct Finances API format)
        """
        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="eBay access token required"
            )
        
        api_url = f"{settings.ebay_api_base_url}/sell/finances/v1/transaction"
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"  # Optional but recommended
        }
        
        params = filter_params or {}
        
        # FIXED: Use RSQL filter format: filter=transactionDate:[...]
        if 'filter' not in params:
            from datetime import datetime, timedelta
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=90)
            # Format: YYYY-MM-DDTHH:MM:SS.000Z (RSQL format with brackets)
            params['filter'] = f"transactionDate:[{start_date.strftime('%Y-%m-%dT%H:%M:%S.000Z')}..{end_date.strftime('%Y-%m-%dT%H:%M:%S.000Z')}]"
        
        # Optional: filter by transaction type
        if 'transactionType' not in params:
            # params['transactionType'] = 'SALE'  # Uncomment if you want only sales
            pass
        
        ebay_logger.log_ebay_event(
            "fetch_transactions_request",
            f"Fetching transactions from eBay ({settings.EBAY_ENVIRONMENT})",
            request_data={
                "environment": settings.EBAY_ENVIRONMENT,
                "api_url": api_url,
                "params": params
            }
        )
        
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=5.0)) as client:
                response = await client.get(
                    api_url,
                    headers=headers,
                    params=params
                )
                
                if response.status_code == 204:
                    ebay_logger.log_ebay_event(
                        "fetch_transactions_empty",
                        "No transactions found matching the criteria",
                        status="success"
                    )
                    return {"transactions": [], "total": 0}
                
                if response.status_code != 200:
                    error_detail = response.text
                    try:
                        error_json = response.json()
                        error_detail = str(error_json)
                        logger.error(f"Transactions API error {response.status_code}: {error_json}")
                    except:
                        logger.error(f"Transactions API error {response.status_code}: {error_detail}")
                    
                    ebay_logger.log_ebay_event(
                        "fetch_transactions_failed",
                        f"Failed to fetch transactions: {response.status_code}",
                        response_data={
                            "status_code": response.status_code,
                            "error": error_detail,
                            "headers": dict(response.headers)
                        },
                        status="error",
                        error=error_detail
                    )
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=f"Failed to fetch transactions (HTTP {response.status_code}): {error_detail}"
                    )
                
                transactions_data = response.json()
                
                ebay_logger.log_ebay_event(
                    "fetch_transactions_success",
                    f"Successfully fetched transactions from eBay",
                    response_data={
                        "total_transactions": transactions_data.get('total', 0)
                    },
                    status="success"
                )
                
                logger.info(f"Successfully fetched {transactions_data.get('total', 0)} transactions from eBay")
                
                return transactions_data
                
        except httpx.RequestError as e:
            error_msg = f"HTTP request failed: {str(e)}"
            ebay_logger.log_ebay_event(
                "fetch_transactions_error",
                "HTTP request error during transactions fetch",
                status="error",
                error=error_msg
            )
            logger.error(error_msg)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_msg
            )


    async def sync_all_orders(self, user_id: str, access_token: str, run_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Synchronize all orders from eBay to database with pagination (limit=200)
        
        Args:
            user_id: User ID
            access_token: eBay OAuth access token
            run_id: Optional run_id for sync event logging
        """
        from app.services.ebay_database import ebay_db
        from app.services.sync_event_logger import SyncEventLogger
        import time
        
        # Use provided run_id if available, otherwise create new one
        event_logger = SyncEventLogger(user_id, 'orders', run_id=run_id)
        job_id = ebay_db.create_sync_job(user_id, 'orders')
        start_time = time.time()
        
        try:
            total_fetched = 0
            total_stored = 0
            limit = ORDERS_PAGE_LIMIT
            offset = 0
            has_more = True
            current_page = 0
            max_pages = 200  # Safety limit to prevent infinite loops
            
            # Get user identity for logging "who we are"
            identity = await self.get_user_identity(access_token)
            username = identity.get("username", "unknown")
            ebay_user_id = identity.get("userId", "unknown")
            
            # Date window with 5-10 minute cushion
            from datetime import datetime, timedelta
            until_date = datetime.utcnow()
            since_date = until_date - timedelta(days=90)  # Default 90 days, can be adjusted
            # Add 5 minute cushion
            since_date = since_date - timedelta(minutes=5)
            
            event_logger.log_start(f"Starting Orders sync from eBay ({settings.EBAY_ENVIRONMENT}) - using bulk limit={limit}")
            event_logger.log_info(f"=== WHO WE ARE ===")
            event_logger.log_info(f"Connected as: {username} (eBay UserID: {ebay_user_id})")
            event_logger.log_info(f"Environment: {settings.EBAY_ENVIRONMENT}")
            event_logger.log_info(f"API Configuration: Fulfillment API v1, max batch size: {limit} orders per request")
            event_logger.log_info(f"Date window: {since_date.strftime('%Y-%m-%dT%H:%M:%S.000Z')}..{until_date.strftime('%Y-%m-%dT%H:%M:%S.000Z')}")
            event_logger.log_info(f"Safety limit: max {max_pages} pages")
            logger.info(f"Starting full order sync for user {user_id} ({username}) with limit={limit}")
            
            await asyncio.sleep(0.5)
            
            while has_more:
                # Safety check: max pages limit
                if current_page >= max_pages:
                    event_logger.log_warning(f"Reached safety limit of {max_pages} pages. Stopping to prevent infinite loop.")
                    logger.warning(f"Order sync reached max_pages limit ({max_pages}) for run_id {event_logger.run_id}")
                    break
                
                # Check for cancellation
                from app.services.sync_event_logger import is_cancelled
                if is_cancelled(event_logger.run_id):
                    logger.info(f"Order sync cancelled for run_id {event_logger.run_id}")
                    event_logger.log_warning("Sync operation cancelled by user")
                    event_logger.log_done(
                        f"Orders sync cancelled: {total_fetched} fetched, {total_stored} stored",
                        total_fetched,
                        total_stored,
                        int((time.time() - start_time) * 1000)
                    )
                    event_logger.close()
                    return {
                        "status": "cancelled",
                        "total_fetched": total_fetched,
                        "total_stored": total_stored,
                        "job_id": job_id,
                        "run_id": event_logger.run_id
                    }
                
                current_page += 1
                # Use orderStatus filter instead of date filter (lastModifiedDate and createdDate are not supported)
                # For date filtering, we'll fetch all orders and filter client-side if needed
                filter_params = {
                    "filter": "orderStatus:COMPLETED",  # Filter by order status instead of date
                    "limit": limit,
                    "offset": offset,
                    "fieldGroups": "TAX_BREAKDOWN"
                }
                
                # Check for cancellation BEFORE making the API request
                from app.services.sync_event_logger import is_cancelled
                if is_cancelled(event_logger.run_id):
                    logger.info(f"Order sync cancelled for run_id {event_logger.run_id} (before API request)")
                    event_logger.log_warning("Sync operation cancelled by user")
                    event_logger.log_done(
                        f"Orders sync cancelled: {total_fetched} fetched, {total_stored} stored",
                        total_fetched,
                        total_stored,
                        int((time.time() - start_time) * 1000)
                    )
                    event_logger.close()
                    return {
                        "status": "cancelled",
                        "total_fetched": total_fetched,
                        "total_stored": total_stored,
                        "job_id": job_id,
                        "run_id": event_logger.run_id
                    }
                
                event_logger.log_info(f"→ Requesting page {current_page}: GET /sell/fulfillment/v1/order?limit={limit}&offset={offset}")
                
                request_start = time.time()
                try:
                    orders_response = await self.fetch_orders(access_token, filter_params)
                except Exception as e:
                    # Check for cancellation after error (in case error took a long time)
                    if is_cancelled(event_logger.run_id):
                        logger.info(f"Order sync cancelled for run_id {event_logger.run_id} (after API error)")
                        event_logger.log_warning("Sync operation cancelled by user")
                        event_logger.log_done(
                            f"Orders sync cancelled: {total_fetched} fetched, {total_stored} stored",
                            total_fetched,
                            total_stored,
                            int((time.time() - start_time) * 1000)
                        )
                        event_logger.close()
                        return {
                            "status": "cancelled",
                            "total_fetched": total_fetched,
                            "total_stored": total_stored,
                            "job_id": job_id,
                            "run_id": event_logger.run_id
                        }
                    raise  # Re-raise if not cancelled
                request_duration = int((time.time() - request_start) * 1000)
                
                # Check for cancellation AFTER the API request (in case request took a long time)
                if is_cancelled(event_logger.run_id):
                    logger.info(f"Order sync cancelled for run_id {event_logger.run_id} (after API request)")
                    event_logger.log_warning("Sync operation cancelled by user")
                    event_logger.log_done(
                        f"Orders sync cancelled: {total_fetched} fetched, {total_stored} stored",
                        total_fetched,
                        total_stored,
                        int((time.time() - start_time) * 1000)
                    )
                    event_logger.close()
                    return {
                        "status": "cancelled",
                        "total_fetched": total_fetched,
                        "total_stored": total_stored,
                        "job_id": job_id,
                        "run_id": event_logger.run_id
                    }
                
                orders = orders_response.get('orders', [])
                total = orders_response.get('total', 0) or 0  # Ensure total is always a number
                total_pages = (total + limit - 1) // limit if total > 0 else 1
                
                event_logger.log_http_request(
                    'GET',
                    f'/sell/fulfillment/v1/order?limit={limit}&offset={offset}',
                    200,
                    request_duration,
                    len(orders)
                )
                
                event_logger.log_info(f"← Response: 200 OK ({request_duration}ms) - Received {len(orders)} orders (Total available: {total})")
                
                # Early exit if total == 0 (no orders in window)
                if total == 0 and current_page == 1:
                    event_logger.log_info(f"✓ No orders found in date window. Total available: 0")
                    event_logger.log_warning("No orders in window - check date range, account, or environment")
                    break
                
                total_fetched += len(orders)
                
                await asyncio.sleep(0.3)
                
                # Check for cancellation before storing
                if is_cancelled(event_logger.run_id):
                    logger.info(f"Order sync cancelled for run_id {event_logger.run_id} (before storing)")
                    event_logger.log_warning("Sync operation cancelled by user")
                    event_logger.log_done(
                        f"Orders sync cancelled: {total_fetched} fetched, {total_stored} stored",
                        total_fetched,
                        total_stored,
                        int((time.time() - start_time) * 1000)
                    )
                    event_logger.close()
                    return {
                        "status": "cancelled",
                        "total_fetched": total_fetched,
                        "total_stored": total_stored,
                        "job_id": job_id,
                        "run_id": event_logger.run_id
                    }
                
                event_logger.log_info(f"→ Storing {len(orders)} orders in database...")
                store_start = time.time()
                batch_stored = ebay_db.batch_upsert_orders(user_id, orders)
                store_duration = int((time.time() - store_start) * 1000)
                total_stored += batch_stored
                
                event_logger.log_info(f"← Database: Stored {batch_stored} orders ({store_duration}ms)")
                
                event_logger.log_progress(
                    f"Page {current_page}/{total_pages} complete: {len(orders)} fetched, {batch_stored} stored | Running total: {total_fetched}/{total} fetched, {total_stored} stored",
                    current_page,
                    total_pages,
                    total_fetched,
                    total_stored
                )
                
                logger.info(f"Synced batch: {len(orders)} orders (total: {total_fetched}/{total}, stored: {total_stored})")
                
                # Check for cancellation before continuing to next page
                if is_cancelled(event_logger.run_id):
                    logger.info(f"Order sync cancelled for run_id {event_logger.run_id} (before next page)")
                    event_logger.log_warning("Sync operation cancelled by user")
                    event_logger.log_done(
                        f"Orders sync cancelled: {total_fetched} fetched, {total_stored} stored",
                        total_fetched,
                        total_stored,
                        int((time.time() - start_time) * 1000)
                    )
                    event_logger.close()
                    return {
                        "status": "cancelled",
                        "total_fetched": total_fetched,
                        "total_stored": total_stored,
                        "job_id": job_id,
                        "run_id": event_logger.run_id
                    }
                
                # Update has_more BEFORE incrementing offset to prevent infinite loops
                # Stop if: no more orders, or we've fetched all available, or offset would exceed total
                has_more = len(orders) > 0 and len(orders) == limit and (offset + limit) < total
                
                offset += limit
                
                if has_more:
                    await asyncio.sleep(0.8)
            
            duration_ms = int((time.time() - start_time) * 1000)
            ebay_db.update_sync_job(job_id, 'completed', total_fetched, total_stored)
            
            event_logger.log_done(
                f"Orders sync completed: {total_fetched} fetched, {total_stored} stored in {duration_ms}ms",
                total_fetched,
                total_stored,
                duration_ms
            )
            
            logger.info(f"Order sync completed: fetched={total_fetched}, stored={total_stored}")
            
            return {
                "status": "completed",
                "total_fetched": total_fetched,
                "total_stored": total_stored,
                "job_id": job_id,
                "run_id": event_logger.run_id
            }
            
        except Exception as e:
            error_msg = str(e)
            event_logger.log_error(f"Orders sync failed: {error_msg}", e)
            logger.error(f"Order sync failed: {error_msg}")
            ebay_db.update_sync_job(job_id, 'failed', error_message=error_msg)
            raise
        finally:
            event_logger.close()


    async def fetch_payment_disputes(self, access_token: str, filter_params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Fetch payment disputes from eBay Fulfillment API using search endpoint
        """
        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="eBay access token required"
            )
        
        # FIXED: Correct endpoint is /payment_dispute (not /payment_dispute_summary/search)
        api_url = f"{settings.ebay_api_base_url}/sell/fulfillment/v1/payment_dispute"
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        params = filter_params or {}
        
        ebay_logger.log_ebay_event(
            "fetch_disputes_request",
            f"Fetching payment disputes from eBay ({settings.EBAY_ENVIRONMENT})",
            request_data={
                "environment": settings.EBAY_ENVIRONMENT,
                "api_url": api_url,
                "method": "POST",
                "body": params
            }
        )
        
        try:
            async with httpx.AsyncClient() as client:
                # Payment dispute search requires POST with body, not GET
                search_body = {}
                if filter_params:
                    search_body.update(filter_params)
                
                response = await client.post(
                    api_url,
                    headers=headers,
                    json=search_body,
                    timeout=30.0
                )
                
                if response.status_code != 200:
                    error_detail = response.text
                    try:
                        error_json = response.json()
                        error_detail = str(error_json)
                    except:
                        pass
                    
                    ebay_logger.log_ebay_event(
                        "fetch_disputes_failed",
                        f"Failed to fetch disputes: {response.status_code}",
                        response_data={"error": error_detail},
                        status="error",
                        error=error_detail
                    )
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=f"Failed to fetch disputes: {error_detail}"
                    )
                
                disputes_data = response.json()
                
                ebay_logger.log_ebay_event(
                    "fetch_disputes_success",
                    f"Successfully fetched disputes from eBay",
                    response_data={
                        "total_disputes": disputes_data.get('total', 0)
                    },
                    status="success"
                )
                
                logger.info(f"Successfully fetched disputes from eBay")
                
                return disputes_data
                
        except httpx.RequestError as e:
            error_msg = f"HTTP request failed: {str(e)}"
            ebay_logger.log_ebay_event(
                "fetch_disputes_error",
                "HTTP request error during disputes fetch",
                status="error",
                error=error_msg
            )
            logger.error(error_msg)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_msg
            )
    
    async def fetch_inventory_items(self, access_token: str, limit: int = 200, offset: int = 0) -> Dict[str, Any]:
        """
        Fetch inventory items from eBay Inventory API
        According to eBay API docs: GET /sell/inventory/v1/inventory_item
        Parameters: limit (1-200, default 25), offset (default 0)
        """
        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="eBay access token required"
            )
        
        api_url = f"{settings.ebay_api_base_url}/sell/inventory/v1/inventory_item"
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"
        }
        
        # Validate limit (1-200 per eBay API docs)
        limit = max(1, min(200, limit))
        params = {
            "limit": str(limit),
            "offset": str(offset)
        }
        
        ebay_logger.log_ebay_event(
            "fetch_inventory_items_request",
            f"Fetching inventory items from eBay ({settings.EBAY_ENVIRONMENT})",
            request_data={
                "environment": settings.EBAY_ENVIRONMENT,
                "api_url": api_url,
                "params": params
            }
        )
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    api_url,
                    headers=headers,
                    params=params,
                    timeout=30.0
                )
                
                if response.status_code != 200:
                    error_detail = response.text
                    try:
                        error_json = response.json()
                        error_detail = str(error_json)
                    except:
                        pass
                    
                    ebay_logger.log_ebay_event(
                        "fetch_inventory_items_failed",
                        f"Failed to fetch inventory items: {response.status_code}",
                        response_data={"error": error_detail},
                        status="error",
                        error=error_detail
                    )
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=f"Failed to fetch inventory items: {error_detail}"
                    )
                
                inventory_data = response.json()
                
                ebay_logger.log_ebay_event(
                    "fetch_inventory_items_success",
                    f"Successfully fetched inventory items from eBay",
                    response_data={
                        "total": inventory_data.get('total', 0),
                        "count": len(inventory_data.get('inventoryItems', []))
                    },
                    status="success"
                )
                
                logger.info(f"Successfully fetched {len(inventory_data.get('inventoryItems', []))} inventory items from eBay")
                
                return inventory_data
                
        except httpx.RequestError as e:
            error_msg = f"HTTP request failed: {str(e)}"
            ebay_logger.log_ebay_event(
                "fetch_inventory_items_error",
                "HTTP request error during inventory items fetch",
                status="error",
                error=error_msg
            )
            logger.error(error_msg)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_msg
            )

    async def fetch_offers(self, access_token: str, sku: str, filter_params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Fetch offers from eBay Inventory API for a specific SKU
        According to eBay API docs: GET /sell/inventory/v1/offer requires 'sku' parameter (Required)
        Parameters: sku (required), limit (optional), offset (optional), format (optional), marketplace_id (optional)
        """
        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="eBay access token required"
            )
        
        api_url = f"{settings.ebay_api_base_url}/sell/inventory/v1/offer"
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"
        }
        
        # According to eBay API docs: sku is REQUIRED parameter
        # Allowed params: sku (required), limit (optional), offset (optional), format (optional), marketplace_id (optional)
        params = {
            "sku": sku
        }
        
        # Add optional params from filter_params
        if filter_params:
            allowed_optional_params = {'limit', 'offset', 'format', 'marketplace_id'}
            for key, value in filter_params.items():
                if key in allowed_optional_params and value is not None and value != '':
                    params[key] = value
        
        # Set defaults for pagination if not provided
        if 'limit' not in params:
            params['limit'] = 200  # Max allowed by eBay
        if 'offset' not in params:
            params['offset'] = 0
        
        logger.info(f"fetch_offers params: sku={sku}, limit={params.get('limit')}, offset={params.get('offset')}")
        
        ebay_logger.log_ebay_event(
            "fetch_offers_request",
            f"Fetching offers from eBay ({settings.EBAY_ENVIRONMENT})",
            request_data={
                "environment": settings.EBAY_ENVIRONMENT,
                "api_url": api_url,
                "params": params
            }
        )
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    api_url,
                    headers=headers,
                    params=params,
                    timeout=30.0
                )
                
                if response.status_code != 200:
                    error_detail = response.text
                    try:
                        error_json = response.json()
                        error_detail = str(error_json)
                    except:
                        pass
                    
                    ebay_logger.log_ebay_event(
                        "fetch_offers_failed",
                        f"Failed to fetch offers: {response.status_code}",
                        response_data={"error": error_detail},
                        status="error",
                        error=error_detail
                    )
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=f"Failed to fetch offers: {error_detail}"
                    )
                
                offers_data = response.json()
                
                ebay_logger.log_ebay_event(
                    "fetch_offers_success",
                    f"Successfully fetched offers from eBay",
                    response_data={
                        "total_offers": offers_data.get('total', 0)
                    },
                    status="success"
                )
                
                logger.info(f"Successfully fetched offers from eBay")
                
                return offers_data
                
        except httpx.RequestError as e:
            error_msg = f"HTTP request failed: {str(e)}"
            ebay_logger.log_ebay_event(
                "fetch_offers_error",
                "HTTP request error during offers fetch",
                status="error",
                error=error_msg
            )
            logger.error(error_msg)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_msg
            )


    async def sync_all_transactions(self, user_id: str, access_token: str, run_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Synchronize all transactions from eBay to database with pagination (limit=200)
        
        Args:
            user_id: User ID
            access_token: eBay OAuth access token
            run_id: Optional run_id for sync event logging
        """
        from app.services.ebay_database import ebay_db
        from app.services.sync_event_logger import SyncEventLogger
        import time
        
        # Use provided run_id if available, otherwise create new one
        event_logger = SyncEventLogger(user_id, 'transactions', run_id=run_id)
        job_id = ebay_db.create_sync_job(user_id, 'transactions')
        start_time = time.time()
        
        try:
            total_fetched = 0
            total_stored = 0
            
            from datetime import datetime, timedelta
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=90)
            
            limit = TRANSACTIONS_PAGE_LIMIT
            offset = 0
            has_more = True
            current_page = 0
            max_pages = 200  # Safety limit to prevent infinite loops
            
            # Get user identity for logging "who we are"
            identity = await self.get_user_identity(access_token)
            username = identity.get("username", "unknown")
            ebay_user_id = identity.get("userId", "unknown")
            
            event_logger.log_start(f"Starting Transactions sync from eBay ({settings.EBAY_ENVIRONMENT}) - using bulk limit={limit}")
            event_logger.log_info(f"=== WHO WE ARE ===")
            event_logger.log_info(f"Connected as: {username} (eBay UserID: {ebay_user_id})")
            event_logger.log_info(f"Environment: {settings.EBAY_ENVIRONMENT}")
            event_logger.log_info(f"API Configuration: Finances API v1, max batch size: {limit} transactions per request")
            event_logger.log_info(f"Date range: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')} (90 days)")
            event_logger.log_info(f"Window: {start_date.strftime('%Y-%m-%dT%H:%M:%S.000Z')}..{end_date.strftime('%Y-%m-%dT%H:%M:%S.000Z')}")
            event_logger.log_info(f"Safety limit: max {max_pages} pages")
            logger.info(f"Starting transaction sync for user {user_id} ({username}) with limit={limit}")
            
            await asyncio.sleep(0.5)
            
            while has_more:
                # Safety check: max pages limit
                if current_page >= max_pages:
                    event_logger.log_warning(f"Reached safety limit of {max_pages} pages. Stopping to prevent infinite loop.")
                    logger.warning(f"Transactions sync reached max_pages limit ({max_pages}) for run_id {event_logger.run_id}")
                    break
                # Check for cancellation
                from app.services.sync_event_logger import is_cancelled
                if is_cancelled(event_logger.run_id):
                    logger.info(f"Transaction sync cancelled for run_id {event_logger.run_id}")
                    event_logger.log_warning("Sync operation cancelled by user")
                    event_logger.log_done(
                        f"Transactions sync cancelled: {total_fetched} fetched, {total_stored} stored",
                        total_fetched,
                        total_stored,
                        int((time.time() - start_time) * 1000)
                    )
                    event_logger.close()
                    return {
                        "status": "cancelled",
                        "total_fetched": total_fetched,
                        "total_stored": total_stored,
                        "job_id": job_id,
                        "run_id": event_logger.run_id
                    }
                
                current_page += 1
                # FIXED: Use RSQL filter format: filter=transactionDate:[...]
                filter_params = {
                    'filter': f"transactionDate:[{start_date.strftime('%Y-%m-%dT%H:%M:%S.000Z')}..{end_date.strftime('%Y-%m-%dT%H:%M:%S.000Z')}]",
                    'limit': limit,
                    'offset': offset
                }
                
                # Check for cancellation BEFORE making the API request
                from app.services.sync_event_logger import is_cancelled
                if is_cancelled(event_logger.run_id):
                    logger.info(f"Transactions sync cancelled for run_id {event_logger.run_id} (before API request)")
                    event_logger.log_warning("Sync operation cancelled by user")
                    event_logger.log_done(
                        f"Transactions sync cancelled: {total_fetched} fetched, {total_stored} stored",
                        total_fetched,
                        total_stored,
                        int((time.time() - start_time) * 1000)
                    )
                    event_logger.close()
                    return {
                        "status": "cancelled",
                        "total_fetched": total_fetched,
                        "total_stored": total_stored,
                        "job_id": job_id,
                        "run_id": event_logger.run_id
                    }
                
                event_logger.log_info(f"→ Requesting page {current_page}: GET /sell/finances/v1/transaction?limit={limit}&offset={offset}")
                
                request_start = time.time()
                try:
                    transactions_response = await self.fetch_transactions(access_token, filter_params)
                except Exception as e:
                    # Check for cancellation after error
                    if is_cancelled(event_logger.run_id):
                        logger.info(f"Transactions sync cancelled for run_id {event_logger.run_id} (after API error)")
                        event_logger.log_warning("Sync operation cancelled by user")
                        event_logger.log_done(
                            f"Transactions sync cancelled: {total_fetched} fetched, {total_stored} stored",
                            total_fetched,
                            total_stored,
                            int((time.time() - start_time) * 1000)
                        )
                        event_logger.close()
                        return {
                            "status": "cancelled",
                            "total_fetched": total_fetched,
                            "total_stored": total_stored,
                            "job_id": job_id,
                            "run_id": event_logger.run_id
                        }
                    raise
                request_duration = int((time.time() - request_start) * 1000)
                
                # Check for cancellation AFTER the API request
                if is_cancelled(event_logger.run_id):
                    logger.info(f"Transactions sync cancelled for run_id {event_logger.run_id} (after API request)")
                    event_logger.log_warning("Sync operation cancelled by user")
                    event_logger.log_done(
                        f"Transactions sync cancelled: {total_fetched} fetched, {total_stored} stored",
                        total_fetched,
                        total_stored,
                        int((time.time() - start_time) * 1000)
                    )
                    event_logger.close()
                    return {
                        "status": "cancelled",
                        "total_fetched": total_fetched,
                        "total_stored": total_stored,
                        "job_id": job_id,
                        "run_id": event_logger.run_id
                    }
                
                transactions = transactions_response.get('transactions', [])
                total = transactions_response.get('total', 0) or 0  # Ensure total is always a number
                total_pages = (total + limit - 1) // limit if total > 0 else 1
                
                event_logger.log_http_request(
                    'GET',
                    f'/sell/finances/v1/transaction?limit={limit}&offset={offset}',
                    200,
                    request_duration,
                    len(transactions)
                )
                
                event_logger.log_info(f"← Response: 200 OK ({request_duration}ms) - Received {len(transactions)} transactions (Total available: {total})")
                
                # Early exit if total == 0 (no transactions in window)
                if total == 0 and current_page == 1:
                    event_logger.log_info(f"✓ No transactions found in date window. Total available: 0")
                    event_logger.log_warning("No transactions in window - check date range, account, or environment")
                    break
                
                total_fetched += len(transactions)
                
                await asyncio.sleep(0.3)
                
                # Check for cancellation before storing
                if is_cancelled(event_logger.run_id):
                    logger.info(f"Transactions sync cancelled for run_id {event_logger.run_id} (before storing)")
                    event_logger.log_warning("Sync operation cancelled by user")
                    event_logger.log_done(
                        f"Transactions sync cancelled: {total_fetched} fetched, {total_stored} stored",
                        total_fetched,
                        total_stored,
                        int((time.time() - start_time) * 1000)
                    )
                    event_logger.close()
                    return {
                        "status": "cancelled",
                        "total_fetched": total_fetched,
                        "total_stored": total_stored,
                        "job_id": job_id,
                        "run_id": event_logger.run_id
                    }
                
                event_logger.log_info(f"→ Storing {len(transactions)} transactions in database...")
                store_start = time.time()
                batch_stored = 0
                for transaction in transactions:
                    if ebay_db.upsert_transaction(user_id, transaction):
                        batch_stored += 1
                total_stored += batch_stored
                store_duration = int((time.time() - store_start) * 1000)
                
                event_logger.log_info(f"← Database: Stored {batch_stored} transactions ({store_duration}ms)")
                
                event_logger.log_progress(
                    f"Page {current_page}/{total_pages} complete: {len(transactions)} fetched, {batch_stored} stored | Running total: {total_fetched}/{total} fetched, {total_stored} stored",
                    current_page,
                    total_pages,
                    total_fetched,
                    total_stored
                )
                
                logger.info(f"Synced batch: {len(transactions)} transactions (total: {total_fetched}/{total}, stored: {total_stored})")
                
                # Check for cancellation before continuing to next page
                if is_cancelled(event_logger.run_id):
                    logger.info(f"Transactions sync cancelled for run_id {event_logger.run_id} (before next page)")
                    event_logger.log_warning("Sync operation cancelled by user")
                    event_logger.log_done(
                        f"Transactions sync cancelled: {total_fetched} fetched, {total_stored} stored",
                        total_fetched,
                        total_stored,
                        int((time.time() - start_time) * 1000)
                    )
                    event_logger.close()
                    return {
                        "status": "cancelled",
                        "total_fetched": total_fetched,
                        "total_stored": total_stored,
                        "job_id": job_id,
                        "run_id": event_logger.run_id
                    }
                
                # Update has_more BEFORE incrementing offset to prevent infinite loops
                # Stop if: no more transactions, or we've fetched all available, or offset would exceed total
                has_more = len(transactions) > 0 and len(transactions) == limit and (offset + limit) < total
                
                offset += limit
                
                if has_more:
                    await asyncio.sleep(0.8)
            
            duration_ms = int((time.time() - start_time) * 1000)
            ebay_db.update_sync_job(job_id, 'completed', total_fetched, total_stored)
            
            event_logger.log_done(
                f"Transactions sync completed: {total_fetched} fetched, {total_stored} stored in {duration_ms}ms",
                total_fetched,
                total_stored,
                duration_ms
            )
            
            logger.info(f"Transaction sync completed: fetched={total_fetched}, stored={total_stored}")
            
            return {
                "status": "completed",
                "total_fetched": total_fetched,
                "total_stored": total_stored,
                "job_id": job_id,
                "run_id": event_logger.run_id
            }
            
        except Exception as e:
            error_msg = str(e)
            event_logger.log_error(f"Transactions sync failed: {error_msg}", e)
            logger.error(f"Transaction sync failed: {error_msg}")
            ebay_db.update_sync_job(job_id, 'failed', error_message=error_msg)
            raise
        finally:
            event_logger.close()

    async def sync_all_disputes(self, user_id: str, access_token: str, run_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Synchronize all payment disputes from eBay to database with comprehensive logging
        
        Args:
            user_id: User ID
            access_token: eBay OAuth access token
            run_id: Optional run_id for sync event logging
        """
        from app.services.ebay_database import ebay_db
        from app.services.sync_event_logger import SyncEventLogger
        import time
        
        # Use provided run_id if available, otherwise create new one
        event_logger = SyncEventLogger(user_id, 'disputes', run_id=run_id)
        job_id = ebay_db.create_sync_job(user_id, 'disputes')
        start_time = time.time()
        
        try:
            total_fetched = 0
            total_stored = 0
            
            event_logger.log_start(f"Starting Disputes sync from eBay ({settings.EBAY_ENVIRONMENT})")
            event_logger.log_info(f"API Configuration: Fulfillment API v1 payment_dispute")
            logger.info(f"Starting disputes sync for user {user_id}")
            
            await asyncio.sleep(0.5)
            
            # Check for cancellation before starting
            from app.services.sync_event_logger import is_cancelled
            if is_cancelled(event_logger.run_id):
                logger.info(f"Disputes sync cancelled for run_id {event_logger.run_id}")
                event_logger.log_warning("Sync operation cancelled by user")
                event_logger.log_done(
                    f"Disputes sync cancelled: 0 fetched, 0 stored",
                    0,
                    0,
                    int((time.time() - start_time) * 1000)
                )
                event_logger.close()
                return {
                    "status": "cancelled",
                    "total_fetched": 0,
                    "total_stored": 0,
                    "job_id": job_id,
                    "run_id": event_logger.run_id
                }
            
            # Check for cancellation BEFORE making the API request
            if is_cancelled(event_logger.run_id):
                logger.info(f"Disputes sync cancelled for run_id {event_logger.run_id} (before API request)")
                event_logger.log_warning("Sync operation cancelled by user")
                event_logger.log_done(
                    f"Disputes sync cancelled: 0 fetched, 0 stored",
                    0,
                    0,
                    int((time.time() - start_time) * 1000)
                )
                event_logger.close()
                return {
                    "status": "cancelled",
                    "total_fetched": 0,
                    "total_stored": 0,
                    "job_id": job_id,
                    "run_id": event_logger.run_id
                }
            
            event_logger.log_info(f"→ Requesting: GET /sell/fulfillment/v1/payment_dispute")
            
            request_start = time.time()
            try:
                disputes_response = await self.fetch_payment_disputes(access_token)
            except Exception as e:
                # Check for cancellation after error
                if is_cancelled(event_logger.run_id):
                    logger.info(f"Disputes sync cancelled for run_id {event_logger.run_id} (after API error)")
                    event_logger.log_warning("Sync operation cancelled by user")
                    event_logger.log_done(
                        f"Disputes sync cancelled: 0 fetched, 0 stored",
                        0,
                        0,
                        int((time.time() - start_time) * 1000)
                    )
                    event_logger.close()
                    return {
                        "status": "cancelled",
                        "total_fetched": 0,
                        "total_stored": 0,
                        "job_id": job_id,
                        "run_id": event_logger.run_id
                    }
                raise
            request_duration = int((time.time() - request_start) * 1000)
            
            # Check for cancellation after API call
            if is_cancelled(event_logger.run_id):
                logger.info(f"Disputes sync cancelled for run_id {event_logger.run_id}")
                event_logger.log_warning("Sync operation cancelled by user")
                event_logger.log_done(
                    f"Disputes sync cancelled: 0 fetched, 0 stored",
                    0,
                    0,
                    int((time.time() - start_time) * 1000)
                )
                event_logger.close()
                return {
                    "status": "cancelled",
                    "total_fetched": 0,
                    "total_stored": 0,
                    "job_id": job_id,
                    "run_id": event_logger.run_id
                }
            
            disputes = disputes_response.get('paymentDisputeSummaries', [])
            total_fetched = len(disputes)
            
            event_logger.log_http_request(
                'GET',
                '/sell/fulfillment/v1/payment_dispute',
                200,
                request_duration,
                total_fetched
            )
            
            event_logger.log_info(f"← Response: 200 OK ({request_duration}ms) - Received {total_fetched} disputes")
            
            await asyncio.sleep(0.3)
            
            event_logger.log_info(f"→ Storing {total_fetched} disputes in database...")
            store_start = time.time()
            for dispute in disputes:
                # Check for cancellation during storage
                if is_cancelled(event_logger.run_id):
                    logger.info(f"Disputes sync cancelled for run_id {event_logger.run_id}")
                    event_logger.log_warning("Sync operation cancelled by user")
                    event_logger.log_done(
                        f"Disputes sync cancelled: {total_fetched} fetched, {total_stored} stored",
                        total_fetched,
                        total_stored,
                        int((time.time() - start_time) * 1000)
                    )
                    event_logger.close()
                    return {
                        "status": "cancelled",
                        "total_fetched": total_fetched,
                        "total_stored": total_stored,
                        "job_id": job_id,
                        "run_id": event_logger.run_id
                    }
                
                if ebay_db.upsert_dispute(user_id, dispute):
                    total_stored += 1
            store_duration = int((time.time() - store_start) * 1000)
            
            event_logger.log_info(f"← Database: Stored {total_stored} disputes ({store_duration}ms)")
            
            event_logger.log_progress(
                f"Disputes sync complete: {total_fetched} fetched, {total_stored} stored",
                1,
                1,
                total_fetched,
                total_stored
            )
            
            duration_ms = int((time.time() - start_time) * 1000)
            ebay_db.update_sync_job(job_id, 'completed', total_fetched, total_stored)
            
            event_logger.log_done(
                f"Disputes sync completed: {total_fetched} fetched, {total_stored} stored in {duration_ms}ms",
                total_fetched,
                total_stored,
                duration_ms
            )
            
            logger.info(f"Disputes sync completed: fetched={total_fetched}, stored={total_stored}")
            
            return {
                "status": "completed",
                "total_fetched": total_fetched,
                "total_stored": total_stored,
                "job_id": job_id,
                "run_id": event_logger.run_id
            }
            
        except Exception as e:
            error_msg = str(e)
            event_logger.log_error(f"Disputes sync failed: {error_msg}", e)
            logger.error(f"Disputes sync failed: {error_msg}")
            ebay_db.update_sync_job(job_id, 'failed', error_message=error_msg)
            raise
        finally:
            event_logger.close()

    async def sync_all_offers(self, user_id: str, access_token: str, run_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Synchronize all offers from eBay to database.
        
        According to eBay API documentation:
        - getOffers endpoint requires 'sku' parameter (Required)
        - To get all offers, we must:
          1. First get all inventory items via getInventoryItems (paginated)
          2. For each SKU, call getOffers to get offers for that SKU
        
        API Flow:
        1. GET /sell/inventory/v1/inventory_item?limit=200&offset=0 (get all SKUs)
        2. For each SKU: GET /sell/inventory/v1/offer?sku={sku}&limit=200&offset=0
        3. Store all offers in database
        
        Args:
            user_id: User ID
            access_token: eBay OAuth access token
            run_id: Optional run_id for sync event logging
            
        Returns:
            Dict with status, total_fetched, total_stored, job_id, run_id
        """
        from app.services.ebay_database import ebay_db
        from app.services.sync_event_logger import SyncEventLogger
        import time
        
        # Use provided run_id if available, otherwise create new one
        event_logger = SyncEventLogger(user_id, 'offers', run_id=run_id)
        job_id = ebay_db.create_sync_job(user_id, 'offers')
        start_time = time.time()
        
        try:
            total_fetched = 0
            total_stored = 0
            all_skus = []
            
            event_logger.log_start(f"Starting Offers sync from eBay ({settings.EBAY_ENVIRONMENT})")
            event_logger.log_info(f"API Configuration: Inventory API v1 - getInventoryItems → getOffers per SKU")
            event_logger.log_info(f"Step 1: Fetching all inventory items to get SKU list...")
            logger.info(f"Starting offers sync for user {user_id}")
            
            await asyncio.sleep(0.5)
            
            # Check for cancellation before starting
            from app.services.sync_event_logger import is_cancelled
            if is_cancelled(event_logger.run_id):
                logger.info(f"Offers sync cancelled for run_id {event_logger.run_id}")
                event_logger.log_warning("Sync operation cancelled by user")
                event_logger.log_done(
                    f"Offers sync cancelled: 0 fetched, 0 stored",
                    0,
                    0,
                    int((time.time() - start_time) * 1000)
                )
                event_logger.close()
                return {
                    "status": "cancelled",
                    "total_fetched": 0,
                    "total_stored": 0,
                    "job_id": job_id,
                    "run_id": event_logger.run_id
                }
            
            # Step 1: Get all inventory items (SKUs) with pagination
            limit = 200
            offset = 0
            has_more_items = True
            inventory_page = 0
            
            while has_more_items:
                inventory_page += 1
                
                # Check for cancellation
                if is_cancelled(event_logger.run_id):
                    logger.info(f"Offers sync cancelled for run_id {event_logger.run_id}")
                    event_logger.log_warning("Sync operation cancelled by user")
                    event_logger.log_done(
                        f"Offers sync cancelled: {total_fetched} fetched, {total_stored} stored",
                        total_fetched,
                        total_stored,
                        int((time.time() - start_time) * 1000)
                    )
                    event_logger.close()
                    return {
                        "status": "cancelled",
                        "total_fetched": total_fetched,
                        "total_stored": total_stored,
                        "job_id": job_id,
                        "run_id": event_logger.run_id
                    }
                
                # Check for cancellation BEFORE making the API request
                if is_cancelled(event_logger.run_id):
                    logger.info(f"Offers sync cancelled for run_id {event_logger.run_id} (before inventory API request)")
                    event_logger.log_warning("Sync operation cancelled by user")
                    event_logger.log_done(
                        f"Offers sync cancelled: {total_fetched} fetched, {total_stored} stored",
                        total_fetched,
                        total_stored,
                        int((time.time() - start_time) * 1000)
                    )
                    event_logger.close()
                    return {
                        "status": "cancelled",
                        "total_fetched": total_fetched,
                        "total_stored": total_stored,
                        "job_id": job_id,
                        "run_id": event_logger.run_id
                    }
                
                event_logger.log_info(f"→ Fetching inventory items page {inventory_page}: GET /sell/inventory/v1/inventory_item?limit={limit}&offset={offset}")
                
                request_start = time.time()
                try:
                    inventory_response = await self.fetch_inventory_items(access_token, limit=limit, offset=offset)
                except Exception as e:
                    # Check for cancellation after error
                    if is_cancelled(event_logger.run_id):
                        logger.info(f"Offers sync cancelled for run_id {event_logger.run_id} (after inventory API error)")
                        event_logger.log_warning("Sync operation cancelled by user")
                        event_logger.log_done(
                            f"Offers sync cancelled: {total_fetched} fetched, {total_stored} stored",
                            total_fetched,
                            total_stored,
                            int((time.time() - start_time) * 1000)
                        )
                        event_logger.close()
                        return {
                            "status": "cancelled",
                            "total_fetched": total_fetched,
                            "total_stored": total_stored,
                            "job_id": job_id,
                            "run_id": event_logger.run_id
                        }
                    raise
                request_duration = int((time.time() - request_start) * 1000)
                
                # Check for cancellation AFTER the API request
                if is_cancelled(event_logger.run_id):
                    logger.info(f"Offers sync cancelled for run_id {event_logger.run_id} (after inventory API request)")
                    event_logger.log_warning("Sync operation cancelled by user")
                    event_logger.log_done(
                        f"Offers sync cancelled: {total_fetched} fetched, {total_stored} stored",
                        total_fetched,
                        total_stored,
                        int((time.time() - start_time) * 1000)
                    )
                    event_logger.close()
                    return {
                        "status": "cancelled",
                        "total_fetched": total_fetched,
                        "total_stored": total_stored,
                        "job_id": job_id,
                        "run_id": event_logger.run_id
                    }
                
                inventory_items = inventory_response.get('inventoryItems', [])
                total_items = inventory_response.get('total', 0)
                
                # Extract SKUs from inventory items
                page_skus = [item.get('sku') for item in inventory_items if item.get('sku')]
                all_skus.extend(page_skus)
                
                event_logger.log_info(f"← Response: 200 OK ({request_duration}ms) - Received {len(inventory_items)} items, {len(page_skus)} SKUs (Total: {total_items})")
                
                # Check if more pages
                offset += limit
                has_more_items = len(inventory_items) == limit and offset < total_items
                
                if has_more_items:
                    await asyncio.sleep(0.3)
            
            event_logger.log_info(f"✓ Step 1 complete: Found {len(all_skus)} unique SKUs")
            
            if not all_skus:
                event_logger.log_warning("No SKUs found in inventory - no offers to sync")
                event_logger.log_done(
                    f"Offers sync completed: 0 SKUs found, 0 offers fetched, 0 stored",
                    0,
                    0,
                    int((time.time() - start_time) * 1000)
                )
                ebay_db.update_sync_job(job_id, 'completed', 0, 0)
                return {
                    "status": "completed",
                    "total_fetched": 0,
                    "total_stored": 0,
                    "job_id": job_id,
                    "run_id": event_logger.run_id
                }
            
            # Step 2: For each SKU, get offers
            event_logger.log_info(f"Step 2: Fetching offers for {len(all_skus)} SKUs...")
            sku_count = 0
            
            for sku in all_skus:
                sku_count += 1
                
                # Check for cancellation
                if is_cancelled(event_logger.run_id):
                    logger.info(f"Offers sync cancelled for run_id {event_logger.run_id}")
                    event_logger.log_warning("Sync operation cancelled by user")
                    event_logger.log_done(
                        f"Offers sync cancelled: {total_fetched} fetched, {total_stored} stored",
                        total_fetched,
                        total_stored,
                        int((time.time() - start_time) * 1000)
                    )
                    event_logger.close()
                    return {
                        "status": "cancelled",
                        "total_fetched": total_fetched,
                        "total_stored": total_stored,
                        "job_id": job_id,
                        "run_id": event_logger.run_id
                    }
                
                # Check for cancellation BEFORE making the API request
                if is_cancelled(event_logger.run_id):
                    logger.info(f"Offers sync cancelled for run_id {event_logger.run_id} (before offers API request)")
                    event_logger.log_warning("Sync operation cancelled by user")
                    event_logger.log_done(
                        f"Offers sync cancelled: {total_fetched} fetched, {total_stored} stored",
                        total_fetched,
                        total_stored,
                        int((time.time() - start_time) * 1000)
                    )
                    event_logger.close()
                    return {
                        "status": "cancelled",
                        "total_fetched": total_fetched,
                        "total_stored": total_stored,
                        "job_id": job_id,
                        "run_id": event_logger.run_id
                    }
                
                event_logger.log_info(f"→ [{sku_count}/{len(all_skus)}] Fetching offers for SKU: {sku}")
                
                try:
                    request_start = time.time()
                    offers_response = await self.fetch_offers(access_token, sku=sku)
                    request_duration = int((time.time() - request_start) * 1000)
                    
                    # Check for cancellation AFTER the API request
                    if is_cancelled(event_logger.run_id):
                        logger.info(f"Offers sync cancelled for run_id {event_logger.run_id} (after offers API request)")
                        event_logger.log_warning("Sync operation cancelled by user")
                        event_logger.log_done(
                            f"Offers sync cancelled: {total_fetched} fetched, {total_stored} stored",
                            total_fetched,
                            total_stored,
                            int((time.time() - start_time) * 1000)
                        )
                        event_logger.close()
                        return {
                            "status": "cancelled",
                            "total_fetched": total_fetched,
                            "total_stored": total_stored,
                            "job_id": job_id,
                            "run_id": event_logger.run_id
                        }
                    
                    offers = offers_response.get('offers', [])
                    total_fetched += len(offers)
                    
                    event_logger.log_info(f"← [{sku_count}/{len(all_skus)}] SKU {sku}: {len(offers)} offers ({request_duration}ms)")
                    
                    # Store offers
                    for offer in offers:
                        if ebay_db.upsert_offer(user_id, offer):
                            total_stored += 1
                    
                    # Rate limiting - small delay between SKU requests
                    await asyncio.sleep(0.2)
                    
                except Exception as e:
                    # Check for cancellation after error
                    if is_cancelled(event_logger.run_id):
                        logger.info(f"Offers sync cancelled for run_id {event_logger.run_id} (after offers API error)")
                        event_logger.log_warning("Sync operation cancelled by user")
                        event_logger.log_done(
                            f"Offers sync cancelled: {total_fetched} fetched, {total_stored} stored",
                            total_fetched,
                            total_stored,
                            int((time.time() - start_time) * 1000)
                        )
                        event_logger.close()
                        return {
                            "status": "cancelled",
                            "total_fetched": total_fetched,
                            "total_stored": total_stored,
                            "job_id": job_id,
                            "run_id": event_logger.run_id
                        }
                    error_msg = f"Failed to fetch offers for SKU {sku}: {str(e)}"
                    event_logger.log_warning(error_msg)
                    logger.warning(error_msg)
                    # Continue with next SKU
                    continue
            
            event_logger.log_info(f"✓ Step 2 complete: Processed {sku_count} SKUs")
            
            duration_ms = int((time.time() - start_time) * 1000)
            ebay_db.update_sync_job(job_id, 'completed', total_fetched, total_stored)
            
            event_logger.log_done(
                f"Offers sync completed: {total_fetched} offers fetched, {total_stored} stored from {sku_count} SKUs in {duration_ms}ms",
                total_fetched,
                total_stored,
                duration_ms
            )
            
            logger.info(f"Offers sync completed: fetched={total_fetched}, stored={total_stored} from {sku_count} SKUs")
            
            return {
                "status": "completed",
                "total_fetched": total_fetched,
                "total_stored": total_stored,
                "job_id": job_id,
                "run_id": event_logger.run_id
            }
            
        except Exception as e:
            error_msg = str(e)
            event_logger.log_error(f"Offers sync failed: {error_msg}", e)
            logger.error(f"Offers sync failed: {error_msg}")
            ebay_db.update_sync_job(job_id, 'failed', error_message=error_msg)
            raise
        finally:
            event_logger.close()
    
    async def sync_all_inventory(self, user_id: str, access_token: str, run_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Synchronize all inventory items from eBay to database with pagination and incremental sync support.
        
        According to eBay API documentation:
        - GET /sell/inventory/v1/inventory_item?limit=200&offset=0
        - Parameters: limit (1-200, default 25), offset (default 0)
        - Returns paginated list of inventory items
        
        API Flow:
        1. GET /sell/inventory/v1/inventory_item?limit=200&offset=0 (paginated)
        2. For each inventory item, extract and store in database
        3. Support incremental sync via cursor tracking (future enhancement)
        
        Args:
            user_id: User ID
            access_token: eBay OAuth access token
            run_id: Optional run_id for sync event logging
            
        Returns:
            Dict with status, total_fetched, total_stored, job_id, run_id
        """
        from app.services.postgres_ebay_database import PostgresEbayDatabase
        from app.services.sync_event_logger import SyncEventLogger
        import time
        
        ebay_db = PostgresEbayDatabase()
        
        # Use provided run_id if available, otherwise create new one
        event_logger = SyncEventLogger(user_id, 'inventory', run_id=run_id)
        job_id = ebay_db.create_sync_job(user_id, 'inventory')
        start_time = time.time()
        
        try:
            total_fetched = 0
            total_stored = 0
            
            event_logger.log_start(f"Starting Inventory sync from eBay ({settings.EBAY_ENVIRONMENT})")
            event_logger.log_info(f"API Configuration: Inventory API v1 - getInventoryItems with pagination")
            logger.info(f"Starting inventory sync for user {user_id}")
            
            await asyncio.sleep(0.5)
            
            # Check for cancellation before starting
            from app.services.sync_event_logger import is_cancelled
            if is_cancelled(event_logger.run_id):
                logger.info(f"Inventory sync cancelled for run_id {event_logger.run_id}")
                event_logger.log_warning("Sync operation cancelled by user")
                event_logger.log_done(
                    f"Inventory sync cancelled: 0 fetched, 0 stored",
                    0,
                    0,
                    int((time.time() - start_time) * 1000)
                )
                event_logger.close()
                return {
                    "status": "cancelled",
                    "total_fetched": 0,
                    "total_stored": 0,
                    "job_id": job_id,
                    "run_id": event_logger.run_id
                }
            
            # Pagination loop
            limit = 200  # Max allowed by eBay API
            offset = 0
            has_more = True
            current_page = 0
            
            while has_more:
                current_page += 1
                
                # Check for cancellation
                if is_cancelled(event_logger.run_id):
                    logger.info(f"Inventory sync cancelled for run_id {event_logger.run_id}")
                    event_logger.log_warning("Sync operation cancelled by user")
                    event_logger.log_done(
                        f"Inventory sync cancelled: {total_fetched} fetched, {total_stored} stored",
                        total_fetched,
                        total_stored,
                        int((time.time() - start_time) * 1000)
                    )
                    event_logger.close()
                    return {
                        "status": "cancelled",
                        "total_fetched": total_fetched,
                        "total_stored": total_stored,
                        "job_id": job_id,
                        "run_id": event_logger.run_id
                    }
                
                # Check for cancellation BEFORE making the API request
                if is_cancelled(event_logger.run_id):
                    logger.info(f"Inventory sync cancelled for run_id {event_logger.run_id} (before API request)")
                    event_logger.log_warning("Sync operation cancelled by user")
                    event_logger.log_done(
                        f"Inventory sync cancelled: {total_fetched} fetched, {total_stored} stored",
                        total_fetched,
                        total_stored,
                        int((time.time() - start_time) * 1000)
                    )
                    event_logger.close()
                    return {
                        "status": "cancelled",
                        "total_fetched": total_fetched,
                        "total_stored": total_stored,
                        "job_id": job_id,
                        "run_id": event_logger.run_id
                    }
                
                event_logger.log_info(f"→ Requesting page {current_page}: GET /sell/inventory/v1/inventory_item?limit={limit}&offset={offset}")
                
                request_start = time.time()
                try:
                    inventory_response = await self.fetch_inventory_items(access_token, limit=limit, offset=offset)
                except Exception as e:
                    # Check for cancellation after error
                    if is_cancelled(event_logger.run_id):
                        logger.info(f"Inventory sync cancelled for run_id {event_logger.run_id} (after API error)")
                        event_logger.log_warning("Sync operation cancelled by user")
                        event_logger.log_done(
                            f"Inventory sync cancelled: {total_fetched} fetched, {total_stored} stored",
                            total_fetched,
                            total_stored,
                            int((time.time() - start_time) * 1000)
                        )
                        event_logger.close()
                        return {
                            "status": "cancelled",
                            "total_fetched": total_fetched,
                            "total_stored": total_stored,
                            "job_id": job_id,
                            "run_id": event_logger.run_id
                        }
                    raise
                request_duration = int((time.time() - request_start) * 1000)
                
                # Check for cancellation AFTER the API request
                if is_cancelled(event_logger.run_id):
                    logger.info(f"Inventory sync cancelled for run_id {event_logger.run_id} (after API request)")
                    event_logger.log_warning("Sync operation cancelled by user")
                    event_logger.log_done(
                        f"Inventory sync cancelled: {total_fetched} fetched, {total_stored} stored",
                        total_fetched,
                        total_stored,
                        int((time.time() - start_time) * 1000)
                    )
                    event_logger.close()
                    return {
                        "status": "cancelled",
                        "total_fetched": total_fetched,
                        "total_stored": total_stored,
                        "job_id": job_id,
                        "run_id": event_logger.run_id
                    }
                
                inventory_items = inventory_response.get('inventoryItems', [])
                total_items = inventory_response.get('total', 0)
                total_pages = (total_items + limit - 1) // limit if total_items > 0 else 1
                
                event_logger.log_http_request(
                    'GET',
                    f'/sell/inventory/v1/inventory_item?limit={limit}&offset={offset}',
                    200,
                    request_duration,
                    len(inventory_items)
                )
                
                event_logger.log_info(f"← Response: 200 OK ({request_duration}ms) - Received {len(inventory_items)} items (Total available: {total_items})")
                
                total_fetched += len(inventory_items)
                
                await asyncio.sleep(0.3)
                
                event_logger.log_info(f"→ Storing {len(inventory_items)} inventory items in database...")
                store_start = time.time()
                
                for item in inventory_items:
                    # Check for cancellation during storage
                    if is_cancelled(event_logger.run_id):
                        logger.info(f"Inventory sync cancelled for run_id {event_logger.run_id}")
                        event_logger.log_warning("Sync operation cancelled by user")
                        event_logger.log_done(
                            f"Inventory sync cancelled: {total_fetched} fetched, {total_stored} stored",
                            total_fetched,
                            total_stored,
                            int((time.time() - start_time) * 1000)
                        )
                        event_logger.close()
                        return {
                            "status": "cancelled",
                            "total_fetched": total_fetched,
                            "total_stored": total_stored,
                            "job_id": job_id,
                            "run_id": event_logger.run_id
                        }
                    
                    if ebay_db.upsert_inventory_item(user_id, item):
                        total_stored += 1
                
                store_duration = int((time.time() - store_start) * 1000)
                
                event_logger.log_info(f"← Database: Stored {total_stored - (total_fetched - len(inventory_items))} items ({store_duration}ms)")
                
                event_logger.log_progress(
                    f"Page {current_page}/{total_pages} complete: {len(inventory_items)} fetched, {total_stored - (total_fetched - len(inventory_items))} stored | Running total: {total_fetched}/{total_items} fetched, {total_stored} stored",
                    current_page,
                    total_pages,
                    total_fetched,
                    total_stored
                )
                
                logger.info(f"Synced batch: {len(inventory_items)} items (total: {total_fetched}/{total_items}, stored: {total_stored})")
                
                # Check if more pages
                offset += limit
                has_more = len(inventory_items) == limit and offset < total_items
                
                if has_more:
                    await asyncio.sleep(0.8)
            
            duration_ms = int((time.time() - start_time) * 1000)
            ebay_db.update_sync_job(job_id, 'completed', total_fetched, total_stored)
            
            event_logger.log_done(
                f"Inventory sync completed: {total_fetched} fetched, {total_stored} stored in {duration_ms}ms",
                total_fetched,
                total_stored,
                duration_ms
            )
            
            logger.info(f"Inventory sync completed: fetched={total_fetched}, stored={total_stored}")
            
            return {
                "status": "completed",
                "total_fetched": total_fetched,
                "total_stored": total_stored,
                "job_id": job_id,
                "run_id": event_logger.run_id
            }
            
        except Exception as e:
            error_msg = str(e)
            event_logger.log_error(f"Inventory sync failed: {error_msg}", e)
            logger.error(f"Inventory sync failed: {error_msg}")
            ebay_db.update_sync_job(job_id, 'failed', error_message=error_msg)
            raise
        finally:
            event_logger.close()
    
    async def get_ebay_user_id(self, access_token: str) -> str:
        """Get eBay user ID from access token using GetUser Trading API call"""
        import xml.etree.ElementTree as ET
        
        api_url = "https://api.ebay.com/ws/api.dll" if settings.EBAY_ENVIRONMENT == "production" else "https://api.sandbox.ebay.com/ws/api.dll"
        
        xml_request = f"""<?xml version="1.0" encoding="utf-8"?>
<GetUserRequest xmlns="urn:ebay:apis:eBLBaseComponents">
    <RequesterCredentials>
        <eBayAuthToken>{access_token}</eBayAuthToken>
    </RequesterCredentials>
    <WarningLevel>High</WarningLevel>
</GetUserRequest>"""
        
        headers = {
            "X-EBAY-API-COMPATIBILITY-LEVEL": "967",
            "X-EBAY-API-CALL-NAME": "GetUser",
            "X-EBAY-API-SITEID": "0",
            "Content-Type": "text/xml"
        }
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(api_url, content=xml_request, headers=headers)
            
            root = ET.fromstring(response.text)
            user_id_elem = root.find(".//{urn:ebay:apis:eBLBaseComponents}UserID")
            
            if user_id_elem is not None and user_id_elem.text:
                return user_id_elem.text
            
            return "unknown"
        except Exception as e:
            logger.error(f"Failed to get eBay user ID: {str(e)}")
            return "unknown"
    
    async def get_ebay_username(self, access_token: str) -> Optional[str]:
        """Get eBay username from access token using GetUser Trading API call"""
        import xml.etree.ElementTree as ET
        
        api_url = "https://api.ebay.com/ws/api.dll" if settings.EBAY_ENVIRONMENT == "production" else "https://api.sandbox.ebay.com/ws/api.dll"
        
        xml_request = f"""<?xml version="1.0" encoding="utf-8"?>
<GetUserRequest xmlns="urn:ebay:apis:eBLBaseComponents">
    <RequesterCredentials>
        <eBayAuthToken>{access_token}</eBayAuthToken>
    </RequesterCredentials>
    <WarningLevel>High</WarningLevel>
</GetUserRequest>"""
        
        headers = {
            "X-EBAY-API-COMPATIBILITY-LEVEL": "967",
            "X-EBAY-API-CALL-NAME": "GetUser",
            "X-EBAY-API-SITEID": "0",
            "Content-Type": "text/xml"
        }
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(api_url, content=xml_request, headers=headers)
            
            root = ET.fromstring(response.text)
            user_id_elem = root.find(".//{urn:ebay:apis:eBLBaseComponents}UserID")
            
            if user_id_elem is not None and user_id_elem.text:
                return user_id_elem.text
            
            return None
        except Exception as e:
            logger.error(f"Failed to get eBay username: {str(e)}")
            return None
    
    async def get_message_folders(self, access_token: str) -> Dict[str, Any]:
        """Get message folders using GetMyMessages with ReturnSummary"""
        import xml.etree.ElementTree as ET
        
        api_url = "https://api.ebay.com/ws/api.dll"
        
        xml_request = f"""<?xml version="1.0" encoding="utf-8"?>
<GetMyMessagesRequest xmlns="urn:ebay:apis:eBLBaseComponents">
  <RequesterCredentials>
    <eBayAuthToken>{access_token}</eBayAuthToken>
  </RequesterCredentials>
  <DetailLevel>ReturnSummary</DetailLevel>
  <WarningLevel>High</WarningLevel>
</GetMyMessagesRequest>"""
        
        headers = {
            "X-EBAY-API-SITEID": "0",
            "X-EBAY-API-COMPATIBILITY-LEVEL": "1193",
            "X-EBAY-API-CALL-NAME": "GetMyMessages",
            "Content-Type": "text/xml"
        }
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(api_url, content=xml_request, headers=headers)
            
            root = ET.fromstring(response.text)
            ns = {"ebay": "urn:ebay:apis:eBLBaseComponents"}
            
            folders = []
            summary_elem = root.find(".//ebay:Summary", ns)
            if summary_elem is not None:
                for folder_elem in summary_elem.findall(".//ebay:FolderSummary", ns):
                    folder_id_elem = folder_elem.find("ebay:FolderID", ns)
                    folder_name_elem = folder_elem.find("ebay:FolderName", ns)
                    total_elem = folder_elem.find("ebay:TotalMessageCount", ns)
                    
                    if folder_id_elem is not None and folder_name_elem is not None:
                        folders.append({
                            "folder_id": folder_id_elem.text,
                            "folder_name": folder_name_elem.text,
                            "total_count": int(total_elem.text) if total_elem is not None else 0
                        })
            
            return {"folders": folders}
        except Exception as e:
            logger.error(f"Failed to get message folders: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to get message folders: {str(e)}")
    
    async def get_message_headers(self, access_token: str, folder_id: str, page_number: int = 1, entries_per_page: int = 200) -> Dict[str, Any]:
        """Get message headers (IDs only) using GetMyMessages with ReturnHeaders"""
        import xml.etree.ElementTree as ET
        
        api_url = "https://api.ebay.com/ws/api.dll"
        
        now_iso = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z")
        
        xml_request = f"""<?xml version="1.0" encoding="utf-8"?>
<GetMyMessagesRequest xmlns="urn:ebay:apis:eBLBaseComponents">
  <RequesterCredentials>
    <eBayAuthToken>{access_token}</eBayAuthToken>
  </RequesterCredentials>
  <DetailLevel>ReturnHeaders</DetailLevel>
  <FolderID>{folder_id}</FolderID>
  <WarningLevel>High</WarningLevel>
  <StartTimeFrom>2015-01-01T00:00:00.000Z</StartTimeFrom>
  <StartTimeTo>{now_iso}</StartTimeTo>
  <Pagination>
    <EntriesPerPage>{entries_per_page}</EntriesPerPage>
    <PageNumber>{page_number}</PageNumber>
  </Pagination>
</GetMyMessagesRequest>"""
        
        headers = {
            "X-EBAY-API-SITEID": "0",
            "X-EBAY-API-COMPATIBILITY-LEVEL": "1193",
            "X-EBAY-API-CALL-NAME": "GetMyMessages",
            "Content-Type": "text/xml"
        }
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(api_url, content=xml_request, headers=headers)
            
            root = ET.fromstring(response.text)
            ns = {"ebay": "urn:ebay:apis:eBLBaseComponents"}
            
            message_ids = []
            alert_ids = []
            
            messages_elem = root.find(".//ebay:Messages", ns)
            if messages_elem is not None:
                for msg_elem in messages_elem.findall("ebay:Message", ns):
                    msg_id_elem = msg_elem.find("ebay:MessageID", ns)
                    if msg_id_elem is not None and msg_id_elem.text:
                        message_ids.append(msg_id_elem.text)
                
                for alert_elem in messages_elem.findall("ebay:Alert", ns):
                    alert_id_elem = alert_elem.find("ebay:AlertID", ns)
                    if alert_id_elem is not None and alert_id_elem.text:
                        alert_ids.append(alert_id_elem.text)
            
            pagination_elem = root.find(".//ebay:PaginationResult", ns)
            total_pages = 1
            total_entries = 0
            if pagination_elem is not None:
                total_pages_elem = pagination_elem.find("ebay:TotalNumberOfPages", ns)
                total_entries_elem = pagination_elem.find("ebay:TotalNumberOfEntries", ns)
                if total_pages_elem is not None:
                    total_pages = int(total_pages_elem.text)
                if total_entries_elem is not None:
                    total_entries = int(total_entries_elem.text)
            
            return {
                "message_ids": message_ids,
                "alert_ids": alert_ids,
                "total_pages": total_pages,
                "total_entries": total_entries
            }
        except Exception as e:
            logger.error(f"Failed to get message headers: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to get message headers: {str(e)}")
    
    async def get_message_bodies(self, access_token: str, message_ids: List[str]) -> List[Dict[str, Any]]:
        """Get message bodies using GetMyMessages with ReturnMessages (batch of up to 10 IDs)"""
        import xml.etree.ElementTree as ET
        
        if not message_ids:
            return []
        
        if len(message_ids) > 10:
            raise ValueError("Cannot fetch more than 10 message IDs at once")
        
        api_url = "https://api.ebay.com/ws/api.dll"
        
        message_id_xml = "".join([f"<MessageID>{mid}</MessageID>" for mid in message_ids])
        
        xml_request = f"""<?xml version="1.0" encoding="utf-8"?>
<GetMyMessagesRequest xmlns="urn:ebay:apis:eBLBaseComponents">
  <RequesterCredentials>
    <eBayAuthToken>{access_token}</eBayAuthToken>
  </RequesterCredentials>
  <DetailLevel>ReturnMessages</DetailLevel>
  <WarningLevel>High</WarningLevel>
  {message_id_xml}
</GetMyMessagesRequest>"""
        
        headers = {
            "X-EBAY-API-SITEID": "0",
            "X-EBAY-API-COMPATIBILITY-LEVEL": "1193",
            "X-EBAY-API-CALL-NAME": "GetMyMessages",
            "Content-Type": "text/xml"
        }
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(api_url, content=xml_request, headers=headers)
            
            root = ET.fromstring(response.text)
            ns = {"ebay": "urn:ebay:apis:eBLBaseComponents"}
            
            messages = []
            messages_elem = root.find(".//ebay:Messages", ns)
            if messages_elem is not None:
                for msg_elem in messages_elem.findall("ebay:Message", ns):
                    message = {}
                    
                    for field in ["MessageID", "ExternalMessageID", "Subject", "Text", "Sender", "RecipientUserID", "ReceiveDate", "ExpirationDate", "ItemID", "FolderID"]:
                        elem = msg_elem.find(f"ebay:{field}", ns)
                        if elem is not None:
                            message[field.lower()] = elem.text
                    
                    read_elem = msg_elem.find("ebay:Read", ns)
                    flagged_elem = msg_elem.find("ebay:Flagged", ns)
                    
                    message["read"] = read_elem.text.lower() == "true" if read_elem is not None else False
                    message["flagged"] = flagged_elem.text.lower() == "true" if flagged_elem is not None else False
                    
                    messages.append(message)
            
            return messages
        except Exception as e:
            logger.error(f"Failed to get message bodies: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to get message bodies: {str(e)}")


ebay_service = EbayService()
