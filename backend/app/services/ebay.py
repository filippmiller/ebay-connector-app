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
                "https://api.ebay.com/oauth/api_scope",
                "https://api.ebay.com/oauth/api_scope/sell.account",
                "https://api.ebay.com/oauth/api_scope/sell.fulfillment",
                "https://api.ebay.com/oauth/api_scope/sell.inventory"
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
    
    async def fetch_transactions(self, access_token: str, filter_params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Fetch transaction records from eBay Finances API
        By default, fetches transactions from the last 90 days
        """
        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="eBay access token required"
            )
        
        api_url = f"{settings.ebay_api_base_url}/sell/finances/v1/transaction"
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        params = filter_params or {}
        
        if 'filter' not in params:
            from datetime import datetime, timedelta
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=90)
            params['filter'] = f"transactionDate:[{start_date.strftime('%Y-%m-%dT%H:%M:%S.000Z')}..{end_date.strftime('%Y-%m-%dT%H:%M:%S.000Z')}]"
        
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
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    api_url,
                    headers=headers,
                    params=params,
                    timeout=30.0
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
                    except:
                        pass
                    
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


    async def sync_all_orders(self, user_id: str, access_token: str) -> Dict[str, Any]:
        """
        Synchronize all orders from eBay to database with pagination (limit=200)
        """
        from app.services.ebay_database import ebay_db
        from app.services.sync_event_logger import SyncEventLogger
        import time
        
        event_logger = SyncEventLogger(user_id, 'orders')
        job_id = ebay_db.create_sync_job(user_id, 'orders')
        start_time = time.time()
        
        try:
            total_fetched = 0
            total_stored = 0
            limit = ORDERS_PAGE_LIMIT
            offset = 0
            has_more = True
            current_page = 0
            
            event_logger.log_start(f"Starting Orders sync from eBay ({settings.EBAY_ENVIRONMENT}) - using bulk limit={limit}")
            event_logger.log_info(f"API Configuration: Fulfillment API v1, max batch size: {limit} orders per request")
            logger.info(f"Starting full order sync for user {user_id} with limit={limit}")
            
            await asyncio.sleep(0.5)
            
            while has_more:
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
                filter_params = {
                    "limit": limit,
                    "offset": offset
                }
                
                event_logger.log_info(f"→ Requesting page {current_page}: GET /sell/fulfillment/v1/order?limit={limit}&offset={offset}")
                
                request_start = time.time()
                orders_response = await self.fetch_orders(access_token, filter_params)
                request_duration = int((time.time() - request_start) * 1000)
                
                orders = orders_response.get('orders', [])
                total = orders_response.get('total', 0)
                total_pages = (total + limit - 1) // limit if total > 0 else 1
                
                event_logger.log_http_request(
                    'GET',
                    f'/sell/fulfillment/v1/order?limit={limit}&offset={offset}',
                    200,
                    request_duration,
                    len(orders)
                )
                
                event_logger.log_info(f"← Response: 200 OK ({request_duration}ms) - Received {len(orders)} orders (Total available: {total})")
                
                total_fetched += len(orders)
                
                await asyncio.sleep(0.3)
                
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
                
                offset += limit
                has_more = len(orders) == limit and offset < total
                
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
        
        api_url = f"{settings.ebay_api_base_url}/sell/fulfillment/v1/payment_dispute_summary/search"
        
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
    
    async def fetch_offers(self, access_token: str, filter_params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Fetch offers from eBay Inventory API (listing offers, not buyer offers)
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
        
        params = filter_params or {}
        
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


    async def sync_all_transactions(self, user_id: str, access_token: str) -> Dict[str, Any]:
        """
        Synchronize all transactions from eBay to database with pagination (limit=200)
        """
        from app.services.ebay_database import ebay_db
        from app.services.sync_event_logger import SyncEventLogger
        import time
        
        event_logger = SyncEventLogger(user_id, 'transactions')
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
            
            event_logger.log_start(f"Starting Transactions sync from eBay ({settings.EBAY_ENVIRONMENT}) - using bulk limit={limit}")
            event_logger.log_info(f"API Configuration: Finances API v1, max batch size: {limit} transactions per request")
            event_logger.log_info(f"Date range: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')} (90 days)")
            logger.info(f"Starting transaction sync for user {user_id} with limit={limit}")
            
            await asyncio.sleep(0.5)
            
            while has_more:
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
                filter_params = {
                    'filter': f"transactionDate:[{start_date.strftime('%Y-%m-%dT%H:%M:%S.000Z')}..{end_date.strftime('%Y-%m-%dT%H:%M:%S.000Z')}]",
                    'limit': limit,
                    'offset': offset
                }
                
                event_logger.log_info(f"→ Requesting page {current_page}: GET /sell/finances/v1/transaction?limit={limit}&offset={offset}")
                
                request_start = time.time()
                transactions_response = await self.fetch_transactions(access_token, filter_params)
                request_duration = int((time.time() - request_start) * 1000)
                
                transactions = transactions_response.get('transactions', [])
                total = transactions_response.get('total', 0)
                total_pages = (total + limit - 1) // limit if total > 0 else 1
                
                event_logger.log_http_request(
                    'GET',
                    f'/sell/finances/v1/transaction?limit={limit}&offset={offset}',
                    200,
                    request_duration,
                    len(transactions)
                )
                
                event_logger.log_info(f"← Response: 200 OK ({request_duration}ms) - Received {len(transactions)} transactions (Total available: {total})")
                
                total_fetched += len(transactions)
                
                await asyncio.sleep(0.3)
                
                event_logger.log_info(f"→ Storing {len(transactions)} transactions in database...")
                store_start = time.time()
                for transaction in transactions:
                    if ebay_db.upsert_transaction(user_id, transaction):
                        total_stored += 1
                store_duration = int((time.time() - store_start) * 1000)
                
                event_logger.log_info(f"← Database: Stored {total_stored - (total_fetched - len(transactions))} transactions ({store_duration}ms)")
                
                event_logger.log_progress(
                    f"Page {current_page}/{total_pages} complete: {len(transactions)} fetched, {total_stored - (total_fetched - len(transactions))} stored | Running total: {total_fetched}/{total} fetched, {total_stored} stored",
                    current_page,
                    total_pages,
                    total_fetched,
                    total_stored
                )
                
                logger.info(f"Synced batch: {len(transactions)} transactions (total: {total_fetched}/{total}, stored: {total_stored})")
                
                offset += limit
                has_more = len(transactions) == limit and offset < total
                
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

    async def sync_all_disputes(self, user_id: str, access_token: str) -> Dict[str, Any]:
        """
        Synchronize all payment disputes from eBay to database with comprehensive logging
        """
        from app.services.ebay_database import ebay_db
        from app.services.sync_event_logger import SyncEventLogger
        import time
        
        event_logger = SyncEventLogger(user_id, 'disputes')
        job_id = ebay_db.create_sync_job(user_id, 'disputes')
        start_time = time.time()
        
        try:
            total_fetched = 0
            total_stored = 0
            
            event_logger.log_start(f"Starting Disputes sync from eBay ({settings.EBAY_ENVIRONMENT})")
            event_logger.log_info(f"API Configuration: Fulfillment API v1 payment_dispute_summary/search")
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
            
            event_logger.log_info(f"→ Requesting: GET /sell/fulfillment/v1/payment_dispute_summary/search")
            
            request_start = time.time()
            disputes_response = await self.fetch_payment_disputes(access_token)
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
                '/sell/fulfillment/v1/payment_dispute_summary/search',
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

    async def sync_all_offers(self, user_id: str, access_token: str) -> Dict[str, Any]:
        """
        Synchronize all offers from eBay to database with comprehensive logging
        """
        from app.services.ebay_database import ebay_db
        from app.services.sync_event_logger import SyncEventLogger
        import time
        
        event_logger = SyncEventLogger(user_id, 'offers')
        job_id = ebay_db.create_sync_job(user_id, 'offers')
        start_time = time.time()
        
        try:
            total_fetched = 0
            total_stored = 0
            
            event_logger.log_start(f"Starting Offers sync from eBay ({settings.EBAY_ENVIRONMENT})")
            event_logger.log_info(f"API Configuration: Inventory API v1, listing offers endpoint")
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
            
            event_logger.log_info(f"→ Requesting: GET /sell/inventory/v1/offer")
            
            request_start = time.time()
            offers_response = await self.fetch_offers(access_token)
            request_duration = int((time.time() - request_start) * 1000)
            
            # Check for cancellation after API call
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
            
            offers = offers_response.get('offers', [])
            total_fetched = len(offers)
            
            event_logger.log_http_request(
                'GET',
                '/sell/inventory/v1/offer',
                200,
                request_duration,
                total_fetched
            )
            
            event_logger.log_info(f"← Response: 200 OK ({request_duration}ms) - Received {total_fetched} offers")
            
            await asyncio.sleep(0.3)
            
            event_logger.log_info(f"→ Storing {total_fetched} offers in database...")
            store_start = time.time()
            for offer in offers:
                # Check for cancellation during storage
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
                
                if ebay_db.upsert_offer(user_id, offer):
                    total_stored += 1
            store_duration = int((time.time() - store_start) * 1000)
            
            event_logger.log_info(f"← Database: Stored {total_stored} offers ({store_duration}ms)")
            
            event_logger.log_progress(
                f"Offers sync complete: {total_fetched} fetched, {total_stored} stored",
                1,
                1,
                total_fetched,
                total_stored
            )
            
            duration_ms = int((time.time() - start_time) * 1000)
            ebay_db.update_sync_job(job_id, 'completed', total_fetched, total_stored)
            
            event_logger.log_done(
                f"Offers sync completed: {total_fetched} fetched, {total_stored} stored in {duration_ms}ms",
                total_fetched,
                total_stored,
                duration_ms
            )
            
            logger.info(f"Offers sync completed: fetched={total_fetched}, stored={total_stored}")
            
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
