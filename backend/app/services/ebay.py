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
            f"Generated eBay authorization URL ({settings.EBAY_ENVIRONMENT}) for redirect_uri: {settings.ebay_runame}",
            request_data={
                "environment": settings.EBAY_ENVIRONMENT,
                "redirect_uri": settings.ebay_runame,
                "scopes": scopes,
                "state": state
            },
            status="success"
        )
        
        logger.info(f"Generated eBay {settings.EBAY_ENVIRONMENT} authorization URL with RuName: {settings.ebay_runame}")
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


ebay_service = EbayService()
