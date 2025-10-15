from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import Optional, List
from app.models.ebay import EbayAuthRequest, EbayAuthCallback, EbayConnectionStatus
from app.services.auth import get_current_active_user
from app.services.ebay import ebay_service
from app.models.user import User
from app.utils.logger import logger, ebay_logger

router = APIRouter(prefix="/ebay", tags=["ebay"])


@router.post("/auth/start")
async def start_ebay_auth(
    auth_request: EbayAuthRequest,
    redirect_uri: str = Query(..., description="Redirect URI for OAuth callback"),
    current_user: User = Depends(get_current_active_user)
):
    logger.info(f"Starting eBay OAuth for user: {current_user.email}")
    
    try:
        auth_url = ebay_service.get_authorization_url(
            redirect_uri=redirect_uri,
            state=current_user.id,
            scopes=auth_request.scopes
        )
        
        return {
            "authorization_url": auth_url,
            "state": current_user.id
        }
    except Exception as e:
        logger.error(f"Error starting eBay auth: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/auth/callback")
async def ebay_auth_callback(
    callback_data: EbayAuthCallback,
    redirect_uri: str = Query(..., description="Redirect URI used in OAuth start"),
    current_user: User = Depends(get_current_active_user)
):
    logger.info(f"Processing eBay OAuth callback for user: {current_user.email}")
    
    if callback_data.state and callback_data.state != current_user.id:
        logger.warning(f"State mismatch in OAuth callback for user: {current_user.email}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid state parameter"
        )
    
    try:
        token_response = await ebay_service.exchange_code_for_token(
            code=callback_data.code,
            redirect_uri=redirect_uri
        )
        
        ebay_service.save_user_tokens(current_user.id, token_response)
        
        return {
            "message": "Successfully connected to eBay",
            "expires_in": token_response.expires_in
        }
    except Exception as e:
        logger.error(f"Error in eBay OAuth callback: {str(e)}")
        raise


@router.get("/status", response_model=EbayConnectionStatus)
async def get_ebay_status(current_user: User = Depends(get_current_active_user)):
    return EbayConnectionStatus(
        connected=current_user.ebay_connected,
        user_id=current_user.id if current_user.ebay_connected else None,
        expires_at=current_user.ebay_token_expires_at
    )


@router.post("/disconnect")
async def disconnect_ebay(current_user: User = Depends(get_current_active_user)):
    logger.info(f"Disconnecting eBay for user: {current_user.email}")
    
    from app.services.database import db
    db.update_user(current_user.id, {
        "ebay_connected": False,
        "ebay_access_token": None,
        "ebay_refresh_token": None,
        "ebay_token_expires_at": None
    })
    
    ebay_logger.log_ebay_event(
        "user_disconnected",
        f"User {current_user.id} disconnected from eBay",
        status="success"
    )
    
    return {"message": "Successfully disconnected from eBay"}


@router.get("/logs")
async def get_ebay_logs(
    limit: Optional[int] = Query(100, description="Number of logs to retrieve"),
    current_user: User = Depends(get_current_active_user)
):
    logs = ebay_logger.get_logs(limit=limit)
    return {
        "logs": logs,
        "total": len(logs)
    }


@router.delete("/logs")
async def clear_ebay_logs(current_user: User = Depends(get_current_active_user)):
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can clear logs"
        )
    
    ebay_logger.clear_logs()
    return {"message": "Logs cleared successfully"}
