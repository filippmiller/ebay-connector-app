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
        
        self.is_sandbox = settings.EBAY_ENVIRONMENT == "sandbox"
    
    @property
    def auth_url(self) -> str:
        return self.sandbox_auth_url if self.is_sandbox else self.production_auth_url
    
    @property
    def token_url(self) -> str:
        return self.sandbox_token_url if self.is_sandbox else self.production_token_url
    
    def get_authorization_url(self, redirect_uri: str, state: Optional[str] = None, scopes: Optional[List[str]] = None) -> str:
        if not settings.EBAY_CLIENT_ID:
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
                "https://api.ebay.com/oauth/api_scope/sell.account"
            ]
        
        params = {
            "client_id": settings.EBAY_CLIENT_ID,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(scopes)
        }
        
        if state:
            params["state"] = state
        
        auth_url = f"{self.auth_url}?{urlencode(params)}"
        
        ebay_logger.log_ebay_event(
            "authorization_url_generated",
            f"Generated eBay authorization URL for redirect_uri: {redirect_uri}",
            request_data={
                "redirect_uri": redirect_uri,
                "scopes": scopes,
                "state": state
            },
            status="success"
        )
        
        logger.info(f"Generated eBay authorization URL with scopes: {scopes}")
        return auth_url
    
    async def exchange_code_for_token(self, code: str, redirect_uri: str) -> EbayTokenResponse:
        if not settings.EBAY_CLIENT_ID or not settings.EBAY_CLIENT_SECRET:
            ebay_logger.log_ebay_event(
                "token_exchange_error",
                "eBay credentials not configured",
                status="error",
                error="EBAY_CLIENT_ID or EBAY_CLIENT_SECRET not set"
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="eBay credentials not configured"
            )
        
        credentials = f"{settings.EBAY_CLIENT_ID}:{settings.EBAY_CLIENT_SECRET}"
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
            f"Exchanging authorization code for access token",
            request_data={
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
                "code": code[:10] + "..." if len(code) > 10 else code,
                "client_id": settings.EBAY_CLIENT_ID
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
        if not settings.EBAY_CLIENT_ID or not settings.EBAY_CLIENT_SECRET:
            ebay_logger.log_ebay_event(
                "token_refresh_error",
                "eBay credentials not configured",
                status="error",
                error="EBAY_CLIENT_ID or EBAY_CLIENT_SECRET not set"
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="eBay credentials not configured"
            )
        
        credentials = f"{settings.EBAY_CLIENT_ID}:{settings.EBAY_CLIENT_SECRET}"
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
            "ebay_token_expires_at": expires_at
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


ebay_service = EbayService()
