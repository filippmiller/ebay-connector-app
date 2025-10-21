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
    environment: str = Query('sandbox', description="eBay environment: sandbox or production"),
    current_user: User = Depends(get_current_active_user)
):
    logger.info(f"Starting eBay OAuth for user: {current_user.email} in {environment} mode")
    
    from app.config import settings
    original_env = settings.EBAY_ENVIRONMENT
    settings.EBAY_ENVIRONMENT = environment
    
    from app.services.database import db
    db.update_user(current_user.id, {"ebay_environment": environment})
    
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
    finally:
        settings.EBAY_ENVIRONMENT = original_env


@router.post("/auth/callback")
async def ebay_auth_callback(
    callback_data: EbayAuthCallback,
    redirect_uri: str = Query(..., description="Redirect URI used in OAuth start"),
    environment: str = Query('sandbox', description="eBay environment: sandbox or production"),
    current_user: User = Depends(get_current_active_user)
):
    logger.info(f"Processing eBay OAuth callback for user: {current_user.email} in {environment} mode")
    
    if callback_data.state and callback_data.state != current_user.id:
        logger.warning(f"State mismatch in OAuth callback for user: {current_user.email}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid state parameter"
        )
    
    from app.config import settings
    original_env = settings.EBAY_ENVIRONMENT
    settings.EBAY_ENVIRONMENT = environment
    
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
    finally:
        settings.EBAY_ENVIRONMENT = original_env


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


@router.get("/test/orders")
async def test_fetch_orders(
    limit: int = Query(10, description="Number of orders to fetch"),
    current_user: User = Depends(get_current_active_user)
):
    if not current_user.ebay_connected or not current_user.ebay_access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="eBay account not connected. Please connect to eBay first."
        )
    
    logger.info(f"Testing orders fetch for user: {current_user.email}")
    
    from app.config import settings
    original_env = settings.EBAY_ENVIRONMENT
    settings.EBAY_ENVIRONMENT = current_user.ebay_environment
    
    try:
        orders = await ebay_service.fetch_orders(current_user.ebay_access_token, {"limit": limit})
        return orders
    except Exception as e:
        logger.error(f"Error fetching orders: {str(e)}")
        raise
    finally:
        settings.EBAY_ENVIRONMENT = original_env


@router.get("/test/transactions")
async def test_fetch_transactions(
    limit: int = Query(10, description="Number of transactions to fetch"),
    current_user: User = Depends(get_current_active_user)
):
    if not current_user.ebay_connected or not current_user.ebay_access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="eBay account not connected. Please connect to eBay first."
        )
    
    logger.info(f"Testing transactions fetch for user: {current_user.email}")
    
    from app.config import settings
    original_env = settings.EBAY_ENVIRONMENT
    settings.EBAY_ENVIRONMENT = current_user.ebay_environment
    
    try:
        transactions = await ebay_service.fetch_transactions(current_user.ebay_access_token, {"limit": limit})
        return transactions
    except Exception as e:
        logger.error(f"Error fetching transactions: {str(e)}")
        raise
    finally:
        settings.EBAY_ENVIRONMENT = original_env


@router.post("/sync/orders")
async def sync_all_orders(current_user: User = Depends(get_current_active_user)):
    if not current_user.ebay_connected or not current_user.ebay_access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="eBay account not connected. Please connect to eBay first."
        )
    
    logger.info(f"Starting order sync for user: {current_user.email}")
    
    from app.config import settings
    original_env = settings.EBAY_ENVIRONMENT
    settings.EBAY_ENVIRONMENT = current_user.ebay_environment
    
    try:
        result = await ebay_service.sync_all_orders(
            current_user.id,
            current_user.ebay_access_token
        )
        return result
    except Exception as e:
        logger.error(f"Error syncing orders: {str(e)}")
        raise
    finally:
        settings.EBAY_ENVIRONMENT = original_env


@router.get("/orders")
async def get_orders(
    limit: int = Query(100, description="Number of orders to return"),
    offset: int = Query(0, description="Offset for pagination"),
    current_user: User = Depends(get_current_active_user)
):
    from app.services.ebay_database import ebay_db
    
    orders = ebay_db.get_orders(current_user.id, limit, offset)
    total = ebay_db.get_order_count(current_user.id)
    
    return {
        "orders": orders,
        "total": total,
        "limit": limit,
        "offset": offset
    }


@router.get("/sync/jobs")
async def get_sync_jobs(
    limit: int = Query(10, description="Number of sync jobs to return"),
    current_user: User = Depends(get_current_active_user)
):
    from app.services.ebay_database import ebay_db
    
    jobs = ebay_db.get_sync_jobs(current_user.id, limit)
    
    return {
        "jobs": jobs,
        "total": len(jobs)
    }


@router.post("/sync/transactions")
async def sync_all_transactions(current_user: User = Depends(get_current_active_user)):
    if not current_user.ebay_connected or not current_user.ebay_access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="eBay account not connected. Please connect to eBay first."
        )
    
    logger.info(f"Starting transaction sync for user: {current_user.email}")
    
    from app.config import settings
    original_env = settings.EBAY_ENVIRONMENT
    settings.EBAY_ENVIRONMENT = current_user.ebay_environment
    
    try:
        result = await ebay_service.sync_all_transactions(
            current_user.id,
            current_user.ebay_access_token
        )
        return result
    except Exception as e:
        logger.error(f"Error syncing transactions: {str(e)}")
        raise
    finally:
        settings.EBAY_ENVIRONMENT = original_env


@router.post("/sync/disputes")
async def sync_all_disputes(current_user: User = Depends(get_current_active_user)):
    if not current_user.ebay_connected or not current_user.ebay_access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="eBay account not connected. Please connect to eBay first."
        )
    
    logger.info(f"Starting disputes sync for user: {current_user.email}")
    
    from app.config import settings
    original_env = settings.EBAY_ENVIRONMENT
    settings.EBAY_ENVIRONMENT = current_user.ebay_environment
    
    try:
        result = await ebay_service.sync_all_disputes(
            current_user.id,
            current_user.ebay_access_token
        )
        return result
    except Exception as e:
        logger.error(f"Error syncing disputes: {str(e)}")
        raise
    finally:
        settings.EBAY_ENVIRONMENT = original_env


@router.post("/sync/offers")
async def sync_all_offers(current_user: User = Depends(get_current_active_user)):
    if not current_user.ebay_connected or not current_user.ebay_access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="eBay account not connected. Please connect to eBay first."
        )
    
    logger.info(f"Starting offers sync for user: {current_user.email}")
    
    from app.config import settings
    original_env = settings.EBAY_ENVIRONMENT
    settings.EBAY_ENVIRONMENT = current_user.ebay_environment
    
    try:
        result = await ebay_service.sync_all_offers(
            current_user.id,
            current_user.ebay_access_token
        )
        return result
    except Exception as e:
        logger.error(f"Error syncing offers: {str(e)}")
        raise
    finally:
        settings.EBAY_ENVIRONMENT = original_env


@router.get("/export/all")
async def export_all_data(current_user: User = Depends(get_current_active_user)):
    from app.services.ebay_database import ebay_db
    from datetime import datetime
    
    orders = ebay_db.get_orders(current_user.id, limit=10000)
    
    export_data = {
        "export_date": datetime.utcnow().isoformat(),
        "user_email": current_user.email,
        "orders": orders,
        "total_orders": len(orders)
    }
    
    return export_data


@router.get("/orders/filter")
async def filter_orders(
    buyer_username: str = Query(None, description="Filter by buyer username"),
    order_status: str = Query(None, description="Filter by order status"),
    start_date: str = Query(None, description="Filter by creation date (start)"),
    end_date: str = Query(None, description="Filter by creation date (end)"),
    limit: int = Query(100, description="Number of orders to return"),
    offset: int = Query(0, description="Offset for pagination"),
    current_user: User = Depends(get_current_active_user)
):
    from app.services.ebay_database import ebay_db
    
    orders = ebay_db.get_filtered_orders(
        current_user.id, 
        buyer_username=buyer_username,
        order_status=order_status,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset
    )
    total = ebay_db.get_order_count(current_user.id)
    
    return {
        "orders": orders,
        "total": total,
        "filtered_count": len(orders),
        "limit": limit,
        "offset": offset
    }


@router.get("/analytics/summary")
async def get_analytics_summary(current_user: User = Depends(get_current_active_user)):
    from app.services.ebay_database import ebay_db
    
    analytics = ebay_db.get_analytics_summary(current_user.id)
    
    return analytics
