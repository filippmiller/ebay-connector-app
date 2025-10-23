import base64
import httpx
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from urllib.parse import urlencode
from fastapi import HTTPException, status
from app.config import settings
from app.models.ebay import EbayTokenResponse
from app.services.database import db
from app.utils.logger import logger, ebay_logger


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
        
        if not scopes:
            scopes = [
                "https://api.ebay.com/oauth/api_scope",
                "https://api.ebay.com/oauth/api_scope/sell.account",
                "https://api.ebay.com/oauth/api_scope/sell.fulfillment",
                "https://api.ebay.com/oauth/api_scope/sell.inventory",
                "https://api.ebay.com/oauth/api_scope/sell.finances"
            ]
        
        params = {
            "client_id": settings.ebay_client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(scopes)
        }
        
        if state:
            params["state"] = state
        
        auth_url = f"{self.auth_url}?{urlencode(params)}"
        
        ebay_logger.log_ebay_event(
            "authorization_url_generated",
            f"Generated eBay authorization URL ({settings.EBAY_ENVIRONMENT}) for redirect_uri: {redirect_uri}",
            request_data={
                "environment": settings.EBAY_ENVIRONMENT,
                "redirect_uri": redirect_uri,
                "scopes": scopes,
                "state": state
            },
            status="success"
        )
        
        logger.info(f"Generated eBay {settings.EBAY_ENVIRONMENT} authorization URL with redirect_uri: {redirect_uri}")
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
            "redirect_uri": redirect_uri
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
    
    async def ensure_valid_token(self, user_id: str) -> str:
        """
        Ensures the user has a valid access token, refreshing if necessary.
        Returns the valid access token.
        """
        user = db.get_user_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        if not user.ebay_connected or not user.ebay_refresh_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="eBay account not connected"
            )
        
        now = datetime.utcnow()
        expires_at = user.ebay_token_expires_at
        
        if expires_at and now >= expires_at - timedelta(minutes=5):
            logger.info(f"Token expired or expiring soon for user {user_id}, refreshing...")
            try:
                token_response = await self.refresh_access_token(user.ebay_refresh_token)
                self.save_user_tokens(user_id, token_response)
                logger.info(f"Token refreshed successfully for user {user_id}")
                return token_response.access_token
            except Exception as e:
                logger.error(f"Failed to refresh token for user {user_id}: {str(e)}")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Failed to refresh eBay token. Please reconnect your eBay account."
                )
        
        return user.ebay_access_token
    
    async def call_ebay_api_with_retry(self, user_id: str, api_call_func, *args, **kwargs) -> Any:
        """
        Wrapper that calls an eBay API function with automatic token refresh on 401.
        """
        access_token = await self.ensure_valid_token(user_id)
        
        try:
            return await api_call_func(access_token, *args, **kwargs)
        except HTTPException as e:
            if e.status_code == 401 or (e.status_code == 400 and "expired" in str(e.detail).lower()):
                logger.info(f"Got 401/expired error, attempting token refresh for user {user_id}")
                try:
                    user = db.get_user_by_id(user_id)
                    if user and user.ebay_refresh_token:
                        token_response = await self.refresh_access_token(user.ebay_refresh_token)
                        self.save_user_tokens(user_id, token_response)
                        logger.info(f"Token refreshed after 401, retrying API call for user {user_id}")
                        return await api_call_func(token_response.access_token, *args, **kwargs)
                except Exception as refresh_error:
                    logger.error(f"Failed to refresh token after 401 for user {user_id}: {str(refresh_error)}")
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="eBay token expired and refresh failed. Please reconnect your eBay account."
                    )
            raise
    
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
        By default, fetches transactions from the last 90 days (or wide range for initial backfill)
        """
        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="eBay access token required"
            )
        
        api_url = f"{settings.ebay_finances_api_base_url}/sell/finances/v1/transaction"
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"
        }
        
        params = filter_params or {}
        
        if 'filter' not in params and 'limit' not in params:
            from datetime import datetime, timedelta
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=1095)
            params['filter'] = f"transactionDate:[{start_date.strftime('%Y-%m-%dT%H:%M:%S.000Z')}..{end_date.strftime('%Y-%m-%dT%H:%M:%S.000Z')}]"
            params['limit'] = 1000
        
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
        Synchronize all orders from eBay to database with pagination
        """
        from app.services.ebay_database import ebay_db
        
        job_id = ebay_db.create_sync_job(user_id, 'orders')
        
        try:
            total_fetched = 0
            total_stored = 0
            limit = 100
            offset = 0
            has_more = True
            
            logger.info(f"Starting full order sync for user {user_id}")
            
            while has_more:
                filter_params = {
                    "limit": limit,
                    "offset": offset
                }
                
                orders_response = await self.fetch_orders(access_token, filter_params)
                
                orders = orders_response.get('orders', [])
                total = orders_response.get('total', 0)
                
                total_fetched += len(orders)
                
                batch_stored = ebay_db.batch_upsert_orders(user_id, orders)
                total_stored += batch_stored
                
                logger.info(f"Synced batch: {len(orders)} orders (total: {total_fetched}/{total}, stored: {total_stored})")
                
                offset += limit
                has_more = len(orders) == limit and offset < total
            
            ebay_db.update_sync_job(job_id, 'completed', total_fetched, total_stored)
            
            logger.info(f"Order sync completed: fetched={total_fetched}, stored={total_stored}")
            
            return {
                "status": "completed",
                "total_fetched": total_fetched,
                "total_stored": total_stored,
                "job_id": job_id
            }
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Order sync failed: {error_msg}")
            ebay_db.update_sync_job(job_id, 'failed', error_message=error_msg)
            raise


    async def fetch_payment_disputes(self, access_token: str, filter_params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Fetch payment disputes from eBay Fulfillment API
        """
        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="eBay access token required"
            )
        
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
        Fetch offers from eBay Negotiation API
        """
        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="eBay access token required"
            )
        
        api_url = f"{settings.ebay_api_base_url}/sell/negotiation/v1/offer"
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
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
        Synchronize all transactions from eBay to database with pagination
        """
        from app.services.ebay_database import ebay_db
        
        job_id = ebay_db.create_sync_job(user_id, 'transactions')
        
        try:
            total_fetched = 0
            total_stored = 0
            
            from datetime import datetime, timedelta
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=90)
            
            filter_params = {
                'filter': f"transactionDate:[{start_date.strftime('%Y-%m-%dT%H:%M:%S.000Z')}..{end_date.strftime('%Y-%m-%dT%H:%M:%S.000Z')}]",
                'limit': 100
            }
            
            logger.info(f"Starting transaction sync for user {user_id}")
            
            transactions_response = await self.fetch_transactions(access_token, filter_params)
            transactions = transactions_response.get('transactions', [])
            total_fetched = len(transactions)
            
            for transaction in transactions:
                if ebay_db.upsert_transaction(user_id, transaction):
                    total_stored += 1
            
            ebay_db.update_sync_job(job_id, 'completed', total_fetched, total_stored)
            
            logger.info(f"Transaction sync completed: fetched={total_fetched}, stored={total_stored}")
            
            return {
                "status": "completed",
                "total_fetched": total_fetched,
                "total_stored": total_stored,
                "job_id": job_id
            }
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Transaction sync failed: {error_msg}")
            ebay_db.update_sync_job(job_id, 'failed', error_message=error_msg)
            raise

    async def sync_all_disputes(self, user_id: str, access_token: str) -> Dict[str, Any]:
        """
        Synchronize all payment disputes from eBay to database
        """
        from app.services.ebay_database import ebay_db
        
        job_id = ebay_db.create_sync_job(user_id, 'disputes')
        
        try:
            total_fetched = 0
            total_stored = 0
            
            logger.info(f"Starting disputes sync for user {user_id}")
            
            disputes_response = await self.fetch_payment_disputes(access_token)
            disputes = disputes_response.get('paymentDisputeSummaries', [])
            total_fetched = len(disputes)
            
            for dispute in disputes:
                if ebay_db.upsert_dispute(user_id, dispute):
                    total_stored += 1
            
            ebay_db.update_sync_job(job_id, 'completed', total_fetched, total_stored)
            
            logger.info(f"Disputes sync completed: fetched={total_fetched}, stored={total_stored}")
            
            return {
                "status": "completed",
                "total_fetched": total_fetched,
                "total_stored": total_stored,
                "job_id": job_id
            }
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Disputes sync failed: {error_msg}")
            ebay_db.update_sync_job(job_id, 'failed', error_message=error_msg)
            raise

    async def sync_all_offers(self, user_id: str, access_token: str) -> Dict[str, Any]:
        """
        Synchronize all offers from eBay to database
        """
        from app.services.ebay_database import ebay_db
        
        job_id = ebay_db.create_sync_job(user_id, 'offers')
        
        try:
            total_fetched = 0
            total_stored = 0
            
            logger.info(f"Starting offers sync for user {user_id}")
            
            offers_response = await self.fetch_offers(access_token)
            offers = offers_response.get('offers', [])
            total_fetched = len(offers)
            
            for offer in offers:
                if ebay_db.upsert_offer(user_id, offer):
                    total_stored += 1
            
            ebay_db.update_sync_job(job_id, 'completed', total_fetched, total_stored)
            
            logger.info(f"Offers sync completed: fetched={total_fetched}, stored={total_stored}")
            
            return {
                "status": "completed",
                "total_fetched": total_fetched,
                "total_stored": total_stored,
                "job_id": job_id
            }
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Offers sync failed: {error_msg}")
            ebay_db.update_sync_job(job_id, 'failed', error_message=error_msg)
            raise

    async def fetch_user_identity(self, access_token: str) -> Dict[str, Any]:
        """
        Fetch user identity from eBay Commerce Identity API
        """
        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="eBay access token required"
            )
        
        api_url = f"{settings.ebay_api_base_url}/commerce/identity/v1/user"
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json"
        }
        
        ebay_logger.log_ebay_event(
            "fetch_identity_request",
            f"Fetching user identity from eBay ({settings.EBAY_ENVIRONMENT})",
            request_data={
                "environment": settings.EBAY_ENVIRONMENT,
                "api_url": api_url
            }
        )
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    api_url,
                    headers=headers,
                    timeout=30.0
                )
                
                if response.status_code != 200:
                    error_detail = response.text
                    ebay_logger.log_ebay_event(
                        "fetch_identity_failed",
                        f"Failed to fetch identity: {response.status_code}",
                        response_data={"error": error_detail},
                        status="error",
                        error=error_detail
                    )
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=f"Failed to fetch identity: {error_detail}"
                    )
                
                identity_data = response.json()
                
                ebay_logger.log_ebay_event(
                    "fetch_identity_success",
                    f"Successfully fetched user identity",
                    response_data=identity_data,
                    status="success"
                )
                
                return identity_data
                
        except httpx.RequestError as e:
            error_msg = f"HTTP request failed: {str(e)}"
            ebay_logger.log_ebay_event(
                "fetch_identity_error",
                "HTTP request error during identity fetch",
                status="error",
                error=error_msg
            )
            logger.error(error_msg)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_msg
            )
    
    async def fetch_user_privileges(self, access_token: str) -> Dict[str, Any]:
        """
        Fetch user privileges from eBay Sell Account API
        """
        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="eBay access token required"
            )
        
        api_url = f"{settings.ebay_api_base_url}/sell/account/v1/privilege"
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json"
        }
        
        ebay_logger.log_ebay_event(
            "fetch_privileges_request",
            f"Fetching user privileges from eBay ({settings.EBAY_ENVIRONMENT})",
            request_data={
                "environment": settings.EBAY_ENVIRONMENT,
                "api_url": api_url
            }
        )
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    api_url,
                    headers=headers,
                    timeout=30.0
                )
                
                if response.status_code != 200:
                    error_detail = response.text
                    ebay_logger.log_ebay_event(
                        "fetch_privileges_failed",
                        f"Failed to fetch privileges: {response.status_code}",
                        response_data={"error": error_detail},
                        status="error",
                        error=error_detail
                    )
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=f"Failed to fetch privileges: {error_detail}"
                    )
                
                privileges_data = response.json()
                
                ebay_logger.log_ebay_event(
                    "fetch_privileges_success",
                    f"Successfully fetched user privileges",
                    response_data=privileges_data,
                    status="success"
                )
                
                return privileges_data
                
        except httpx.RequestError as e:
            error_msg = f"HTTP request failed: {str(e)}"
            ebay_logger.log_ebay_event(
                "fetch_privileges_error",
                "HTTP request error during privileges fetch",
                status="error",
                error=error_msg
            )
            logger.error(error_msg)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_msg
            )
    
    async def fetch_message_folders(self, access_token: str, verbose: int = 0) -> Dict[str, Any]:
        """
        Enumerate My Messages folders using ReturnSummary
        """
        logger.info(f"fetch_message_folders called with verbose={verbose}")
        
        if not access_token:
            logger.error("No access token provided")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="eBay access token required"
            )
        
        if settings.EBAY_ENVIRONMENT == "production":
            api_url = "https://api.ebay.com/ws/api.dll"
        else:
            api_url = "https://api.sandbox.ebay.com/ws/api.dll"
        
        logger.info(f"Using eBay API URL: {api_url}")
        
        xml_request = """<?xml version="1.0" encoding="utf-8"?>
<GetMyMessagesRequest xmlns="urn:ebay:apis:eBLBaseComponents">
  <RequesterCredentials>
    <eBayAuthToken>{}</eBayAuthToken>
  </RequesterCredentials>
  <DetailLevel>ReturnSummary</DetailLevel>
  <WarningLevel>High</WarningLevel>
</GetMyMessagesRequest>""".format(access_token)
        
        headers = {
            "X-EBAY-API-COMPATIBILITY-LEVEL": "1201",
            "X-EBAY-API-CALL-NAME": "GetMyMessages",
            "X-EBAY-API-SITEID": "0",
            "Content-Type": "text/xml",
            "Accept": "text/xml"
        }
        
        ebay_logger.log_ebay_event(
            "fetch_message_folders_request",
            f"Fetching message folders from eBay ({settings.EBAY_ENVIRONMENT})",
            request_data={
                "environment": settings.EBAY_ENVIRONMENT,
                "api_url": api_url
            }
        )
        
        try:
            logger.info("Making HTTP request to eBay API for folders")
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    api_url,
                    content=xml_request,
                    headers=headers,
                    timeout=30.0
                )
                
                logger.info(f"eBay API response status: {response.status_code}, content length: {len(response.text)}")
                
                if response.status_code != 200:
                    error_detail = response.text
                    logger.error(f"eBay API returned non-200 status: {response.status_code}")
                    ebay_logger.log_ebay_event(
                        "fetch_message_folders_failed",
                        f"Failed to fetch folders: {response.status_code}",
                        response_data={"status_code": response.status_code, "error": error_detail[:500]},
                        status="error",
                        error=error_detail[:500]
                    )
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=f"Failed to fetch folders: {error_detail[:200]}"
                    )
                
                logger.info("Parsing XML response")
                import xml.etree.ElementTree as ET
                root = ET.fromstring(response.text)
                logger.info("XML parsed successfully")
                
                ns = {'ns': 'urn:ebay:apis:eBLBaseComponents'}
                
                ack = root.findtext('{urn:ebay:apis:eBLBaseComponents}Ack', '')
                
                ebay_logger.log_ebay_event(
                    "fetch_message_folders_response",
                    f"eBay API response received with Ack={ack}",
                    response_data={"ack": ack, "response_length": len(response.text)}
                )
                
                if ack not in ['Success', 'Warning']:
                    errors = []
                    for error in root.findall('.//{urn:ebay:apis:eBLBaseComponents}Errors'):
                        error_code = error.findtext('{urn:ebay:apis:eBLBaseComponents}ErrorCode', '')
                        short_msg = error.findtext('{urn:ebay:apis:eBLBaseComponents}ShortMessage', '')
                        long_msg = error.findtext('{urn:ebay:apis:eBLBaseComponents}LongMessage', '')
                        errors.append({
                            "code": error_code,
                            "short": short_msg,
                            "long": long_msg
                        })
                    
                    error_detail = "; ".join([f"{e['code']}: {e['short']}" for e in errors]) if errors else "Unknown error"
                    ebay_logger.log_ebay_event(
                        "fetch_message_folders_api_error",
                        f"eBay API returned error: {error_detail}",
                        response_data={"errors": errors, "ack": ack},
                        status="error",
                        error=error_detail
                    )
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"eBay API error: {error_detail}"
                    )
                
                folders = []
                summary_elem = root.find('.//{urn:ebay:apis:eBLBaseComponents}Summary')
                
                if summary_elem is not None:
                    folder_summary = summary_elem.find('{urn:ebay:apis:eBLBaseComponents}FolderSummary')
                    if folder_summary is not None:
                        folder_elems = folder_summary.findall('{urn:ebay:apis:eBLBaseComponents}Folder')
                        for folder_elem in folder_elems:
                            folder_id = folder_elem.findtext('{urn:ebay:apis:eBLBaseComponents}FolderID', '')
                            folder_name = folder_elem.findtext('{urn:ebay:apis:eBLBaseComponents}FolderName', '')
                            new_count = folder_elem.findtext('{urn:ebay:apis:eBLBaseComponents}NewMessageCount', '0')
                            total_count = folder_elem.findtext('{urn:ebay:apis:eBLBaseComponents}TotalMessageCount', '0')
                            
                            folder = {
                                'id': int(folder_id) if folder_id else 0,
                                'name': folder_name,
                                'total': int(total_count) if total_count else 0,
                                'unread': int(new_count) if new_count else 0
                            }
                            folders.append(folder)
                
                summary = {}
                if summary_elem is not None:
                    summary = {
                        'totalMessages': int(summary_elem.findtext('{urn:ebay:apis:eBLBaseComponents}TotalMessages', '0') or '0'),
                        'newMessages': int(summary_elem.findtext('{urn:ebay:apis:eBLBaseComponents}NewMessageCount', '0') or '0'),
                        'flaggedMessages': int(summary_elem.findtext('{urn:ebay:apis:eBLBaseComponents}FlaggedMessageCount', '0') or '0'),
                        'totalHighPriorityMessages': int(summary_elem.findtext('{urn:ebay:apis:eBLBaseComponents}TotalHighPriorityCount', '0') or '0'),
                        'totalUnreadMessages': int(summary_elem.findtext('{urn:ebay:apis:eBLBaseComponents}TotalUnreadCount', '0') or '0')
                    }
                
                ebay_logger.log_ebay_event(
                    "fetch_message_folders_success",
                    f"Successfully fetched {len(folders)} folders from eBay",
                    response_data={"folders": folders, "summary": summary},
                    status="success"
                )
                
                logger.info(f"Successfully fetched {len(folders)} message folders from eBay")
                
                result = {
                    "folders": folders,
                    "summary": summary
                }
                
                if verbose:
                    result['debug'] = {
                        "ack": ack,
                        "headers_used": {k: v for k, v in headers.items() if k != "Authorization"},
                        "total_folders": len(folders),
                        "raw_xml_snippet": response.text[:300]
                    }
                
                return result
                
        except ET.ParseError as e:
            error_msg = f"XML parsing failed: {str(e)}"
            ebay_logger.log_ebay_event(
                "fetch_message_folders_parse_error",
                "XML parsing error during folders fetch",
                status="error",
                error=error_msg
            )
            logger.error(error_msg)
            logger.error(f"Response text: {response.text[:1000]}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_msg
            )
        except httpx.RequestError as e:
            error_msg = f"HTTP request failed: {str(e)}"
            ebay_logger.log_ebay_event(
                "fetch_message_folders_error",
                "HTTP request error during folders fetch",
                status="error",
                error=error_msg
            )
            logger.error(error_msg)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_msg
            )
    
    async def fetch_messages(self, access_token: str, filter_params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Fetch messages from eBay using Trading API GetMyMessages
        """
        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="eBay access token required"
            )
        
        if settings.EBAY_ENVIRONMENT == "production":
            api_url = "https://api.ebay.com/ws/api.dll"
        else:
            api_url = "https://api.sandbox.ebay.com/ws/api.dll"
        
        params = filter_params or {}
        folder_id = params.get('folder_id')
        start_time = params.get('start_time', '2015-01-01T00:00:00.000Z')
        end_time = params.get('end_time')
        page_number = params.get('page_number', 1)
        entries_per_page = params.get('entries_per_page', 200)
        
        folder_filter = f"<FolderID>{folder_id}</FolderID>" if folder_id is not None else ""
        time_filter = ""
        if start_time:
            time_filter += f"<StartCreationTime>{start_time}</StartCreationTime>"
        if end_time:
            time_filter += f"<EndCreationTime>{end_time}</EndCreationTime>"
        
        detail_level = params.get('detail_level', 'ReturnHeaders')
        
        xml_request = f"""<?xml version="1.0" encoding="utf-8"?>
<GetMyMessagesRequest xmlns="urn:ebay:apis:eBLBaseComponents">
  <RequesterCredentials>
    <eBayAuthToken>{access_token}</eBayAuthToken>
  </RequesterCredentials>
  <DetailLevel>{detail_level}</DetailLevel>
  <WarningLevel>High</WarningLevel>
  {folder_filter}
  {time_filter}
  <Pagination>
    <EntriesPerPage>{entries_per_page}</EntriesPerPage>
    <PageNumber>{page_number}</PageNumber>
  </Pagination>
</GetMyMessagesRequest>"""
        
        headers = {
            "X-EBAY-API-COMPATIBILITY-LEVEL": "1355",
            "X-EBAY-API-CALL-NAME": "GetMyMessages",
            "X-EBAY-API-SITEID": "0",
            "Content-Type": "text/xml"
        }
        
        ebay_logger.log_ebay_event(
            "fetch_messages_request",
            f"Fetching messages from eBay Trading API GetMyMessages ({settings.EBAY_ENVIRONMENT})",
            request_data={
                "environment": settings.EBAY_ENVIRONMENT,
                "api_url": api_url,
                "folder_id": folder_id,
                "start_time": start_time,
                "end_time": end_time,
                "page": page_number
            }
        )
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    api_url,
                    content=xml_request,
                    headers=headers,
                    timeout=30.0
                )
                
                if response.status_code != 200:
                    error_detail = response.text
                    ebay_logger.log_ebay_event(
                        "fetch_messages_failed",
                        f"Failed to fetch messages: {response.status_code}",
                        response_data={
                            "status_code": response.status_code,
                            "error": error_detail[:500]
                        },
                        status="error",
                        error=error_detail[:500]
                    )
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=f"Failed to fetch messages: {error_detail[:200]}"
                    )
                
                import xml.etree.ElementTree as ET
                root = ET.fromstring(response.text)
                
                ns = {'ns': 'urn:ebay:apis:eBLBaseComponents'}
                
                ack = root.findtext('ns:Ack', '', ns)
                if ack not in ['Success', 'Warning']:
                    errors = []
                    for error in root.findall('.//ns:Errors', ns):
                        error_code = error.findtext('ns:ErrorCode', '', ns)
                        error_msg = error.findtext('ns:LongMessage', '', ns)
                        errors.append(f"{error_code}: {error_msg}")
                    
                    error_detail = "; ".join(errors) if errors else "Unknown error"
                    ebay_logger.log_ebay_event(
                        "fetch_messages_api_error",
                        f"eBay API returned error: {error_detail}",
                        response_data={"errors": errors},
                        status="error",
                        error=error_detail
                    )
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"eBay API error: {error_detail}"
                    )
                
                summary = {}
                summary_elem = root.find('.//ns:Summary', ns)
                if summary_elem is not None:
                    summary = {
                        'totalMessages': int(summary_elem.findtext('ns:TotalMessages', '0', ns)),
                        'newMessages': int(summary_elem.findtext('ns:NewMessageCount', '0', ns)),
                        'flaggedMessages': int(summary_elem.findtext('ns:FlaggedMessageCount', '0', ns)),
                        'totalHighPriorityMessages': int(summary_elem.findtext('ns:TotalHighPriorityCount', '0', ns)),
                        'totalUnreadMessages': int(summary_elem.findtext('ns:TotalUnreadCount', '0', ns))
                    }
                
                messages = []
                for msg_elem in root.findall('.//ns:Messages', ns):
                    message = {
                        'messageId': msg_elem.findtext('ns:MessageID', '', ns),
                        'externalMessageId': msg_elem.findtext('ns:ExternalMessageID', '', ns),
                        'folderId': msg_elem.findtext('ns:FolderID', '', ns),
                        'sender': msg_elem.findtext('ns:Sender', '', ns),
                        'recipientUserID': msg_elem.findtext('ns:RecipientUserID', '', ns) or msg_elem.findtext('ns:ReceivingUserID', '', ns),
                        'subject': msg_elem.findtext('ns:Subject', '', ns),
                        'body': msg_elem.findtext('ns:Text', '', ns) or msg_elem.findtext('ns:Body', '', ns),
                        'messageType': msg_elem.findtext('ns:MessageType', '', ns),
                        'flagged': msg_elem.findtext('ns:Flagged', 'false', ns).lower() == 'true',
                        'read': msg_elem.findtext('ns:Read', 'false', ns).lower() == 'true',
                        'receiveDate': msg_elem.findtext('ns:ReceiveDate', '', ns),
                        'expirationDate': msg_elem.findtext('ns:ExpirationDate', '', ns),
                        'itemID': msg_elem.findtext('ns:ItemID', '', ns),
                        'responseEnabled': msg_elem.findtext('ns:ResponseEnabled', 'false', ns).lower() == 'true',
                        'highPriority': msg_elem.findtext('ns:HighPriority', 'false', ns).lower() == 'true'
                    }
                    messages.append(message)
                
                pagination_result = root.find('.//ns:PaginationResult', ns)
                total_pages = 1
                total_entries = len(messages)
                if pagination_result is not None:
                    total_pages = int(pagination_result.findtext('ns:TotalNumberOfPages', '1', ns))
                    total_entries = int(pagination_result.findtext('ns:TotalNumberOfEntries', str(len(messages)), ns))
                
                ebay_logger.log_ebay_event(
                    "fetch_messages_success",
                    f"Successfully fetched {len(messages)} messages from eBay (page {page_number}/{total_pages})",
                    response_data={
                        "total_messages": len(messages),
                        "total_entries": total_entries,
                        "total_pages": total_pages,
                        "summary": summary
                    },
                    status="success"
                )
                
                logger.info(f"Successfully fetched {len(messages)} messages from eBay (page {page_number}/{total_pages})")
                
                return {
                    "messages": messages,
                    "total": len(messages),
                    "total_entries": total_entries,
                    "total_pages": total_pages,
                    "current_page": page_number,
                    "summary": summary,
                    "raw_response_snippet": response.text[:1000] if len(messages) == 0 else None
                }
                
        except ET.ParseError as e:
            error_msg = f"XML parsing failed: {str(e)}"
            ebay_logger.log_ebay_event(
                "fetch_messages_parse_error",
                "XML parsing error during messages fetch",
                status="error",
                error=error_msg
            )
            logger.error(error_msg)
            logger.error(f"Response text: {response.text[:1000]}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_msg
            )
        except httpx.RequestError as e:
            error_msg = f"HTTP request failed: {str(e)}"
            ebay_logger.log_ebay_event(
                "fetch_messages_error",
                "HTTP request error during messages fetch",
                status="error",
                error=error_msg
            )
            logger.error(error_msg)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_msg
            )
    
    async def fetch_message_bodies(self, access_token: str, message_ids: List[str]) -> Dict[str, Any]:
        """
        Fetch message bodies by MessageIDs (max 10 per call)
        """
        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="eBay access token required"
            )
        
        if not message_ids or len(message_ids) == 0:
            return {"messages": []}
        
        if len(message_ids) > 10:
            raise ValueError("Maximum 10 MessageIDs per call")
        
        if settings.EBAY_ENVIRONMENT == "production":
            api_url = "https://api.ebay.com/ws/api.dll"
        else:
            api_url = "https://api.sandbox.ebay.com/ws/api.dll"
        
        message_id_xml = "\n    ".join([f"<MessageID>{mid}</MessageID>" for mid in message_ids])
        
        xml_request = f"""<?xml version="1.0" encoding="utf-8"?>
<GetMyMessagesRequest xmlns="urn:ebay:apis:eBLBaseComponents">
  <RequesterCredentials>
    <eBayAuthToken>{access_token}</eBayAuthToken>
  </RequesterCredentials>
  <DetailLevel>ReturnMessages</DetailLevel>
  <WarningLevel>High</WarningLevel>
  <MessageIDs>
    {message_id_xml}
  </MessageIDs>
</GetMyMessagesRequest>"""
        
        headers = {
            "X-EBAY-API-COMPATIBILITY-LEVEL": "1355",
            "X-EBAY-API-CALL-NAME": "GetMyMessages",
            "X-EBAY-API-SITEID": "0",
            "Content-Type": "text/xml"
        }
        
        ebay_logger.log_ebay_event(
            "fetch_message_bodies_request",
            f"Fetching {len(message_ids)} message bodies from eBay ({settings.EBAY_ENVIRONMENT})",
            request_data={
                "environment": settings.EBAY_ENVIRONMENT,
                "api_url": api_url,
                "message_count": len(message_ids)
            }
        )
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    api_url,
                    content=xml_request,
                    headers=headers,
                    timeout=30.0
                )
                
                if response.status_code != 200:
                    error_detail = response.text
                    ebay_logger.log_ebay_event(
                        "fetch_message_bodies_failed",
                        f"Failed to fetch message bodies: {response.status_code}",
                        response_data={"status_code": response.status_code, "error": error_detail[:500]},
                        status="error",
                        error=error_detail[:500]
                    )
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=f"Failed to fetch message bodies: {error_detail[:200]}"
                    )
                
                import xml.etree.ElementTree as ET
                root = ET.fromstring(response.text)
                
                ns = {'ns': 'urn:ebay:apis:eBLBaseComponents'}
                
                ack = root.findtext('ns:Ack', '', ns)
                if ack not in ['Success', 'Warning']:
                    errors = []
                    for error in root.findall('.//ns:Errors', ns):
                        error_code = error.findtext('ns:ErrorCode', '', ns)
                        error_msg = error.findtext('ns:LongMessage', '', ns)
                        errors.append(f"{error_code}: {error_msg}")
                    
                    error_detail = "; ".join(errors) if errors else "Unknown error"
                    ebay_logger.log_ebay_event(
                        "fetch_message_bodies_api_error",
                        f"eBay API returned error: {error_detail}",
                        response_data={"errors": errors},
                        status="error",
                        error=error_detail
                    )
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"eBay API error: {error_detail}"
                    )
                
                messages = []
                for msg_elem in root.findall('.//ns:Messages', ns):
                    message = {
                        'messageId': msg_elem.findtext('ns:MessageID', '', ns),
                        'externalMessageId': msg_elem.findtext('ns:ExternalMessageID', '', ns),
                        'folderId': msg_elem.findtext('ns:FolderID', '', ns),
                        'sender': msg_elem.findtext('ns:Sender', '', ns),
                        'recipientUserID': msg_elem.findtext('ns:RecipientUserID', '', ns) or msg_elem.findtext('ns:ReceivingUserID', '', ns),
                        'subject': msg_elem.findtext('ns:Subject', '', ns),
                        'body': msg_elem.findtext('ns:Text', '', ns) or msg_elem.findtext('ns:Body', '', ns),
                        'messageType': msg_elem.findtext('ns:MessageType', '', ns),
                        'flagged': msg_elem.findtext('ns:Flagged', 'false', ns).lower() == 'true',
                        'read': msg_elem.findtext('ns:Read', 'false', ns).lower() == 'true',
                        'receiveDate': msg_elem.findtext('ns:ReceiveDate', '', ns),
                        'expirationDate': msg_elem.findtext('ns:ExpirationDate', '', ns),
                        'itemID': msg_elem.findtext('ns:ItemID', '', ns),
                        'responseEnabled': msg_elem.findtext('ns:ResponseEnabled', 'false', ns).lower() == 'true',
                        'highPriority': msg_elem.findtext('ns:HighPriority', 'false', ns).lower() == 'true'
                    }
                    messages.append(message)
                
                ebay_logger.log_ebay_event(
                    "fetch_message_bodies_success",
                    f"Successfully fetched {len(messages)} message bodies from eBay",
                    response_data={"total_messages": len(messages)},
                    status="success"
                )
                
                logger.info(f"Successfully fetched {len(messages)} message bodies from eBay")
                
                return {
                    "messages": messages,
                    "total": len(messages)
                }
                
        except ET.ParseError as e:
            error_msg = f"XML parsing failed: {str(e)}"
            ebay_logger.log_ebay_event(
                "fetch_message_bodies_parse_error",
                "XML parsing error during message bodies fetch",
                status="error",
                error=error_msg
            )
            logger.error(error_msg)
            logger.error(f"Response text: {response.text[:1000]}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_msg
            )
        except httpx.RequestError as e:
            error_msg = f"HTTP request failed: {str(e)}"
            ebay_logger.log_ebay_event(
                "fetch_message_bodies_error",
                "HTTP request error during message bodies fetch",
                status="error",
                error=error_msg
            )
            logger.error(error_msg)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_msg
            )
    
    async def fetch_payments_program(self, access_token: str) -> Dict[str, Any]:
        """
        Fetch payments program enrollment status from eBay Sell Account API
        """
        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="eBay access token required"
            )
        
        api_url = f"{settings.ebay_api_base_url}/sell/account/v1/payments_program"
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"
        }
        
        ebay_logger.log_ebay_event(
            "fetch_payments_program_request",
            f"Fetching payments program enrollment from eBay ({settings.EBAY_ENVIRONMENT})",
            request_data={
                "environment": settings.EBAY_ENVIRONMENT,
                "api_url": api_url
            }
        )
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    api_url,
                    headers=headers,
                    timeout=30.0
                )
                
                if response.status_code != 200:
                    error_detail = response.text
                    ebay_logger.log_ebay_event(
                        "fetch_payments_program_failed",
                        f"Failed to fetch payments program: {response.status_code}",
                        response_data={"error": error_detail},
                        status="error",
                        error=error_detail
                    )
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=f"Failed to fetch payments program: {error_detail}"
                    )
                
                program_data = response.json()
                
                ebay_logger.log_ebay_event(
                    "fetch_payments_program_success",
                    f"Successfully fetched payments program enrollment",
                    response_data=program_data,
                    status="success"
                )
                
                return program_data
                
        except httpx.RequestError as e:
            error_msg = f"HTTP request failed: {str(e)}"
            ebay_logger.log_ebay_event(
                "fetch_payments_program_error",
                "HTTP request error during payments program fetch",
                status="error",
                error=error_msg
            )
            logger.error(error_msg)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_msg
            )


ebay_service = EbayService()
