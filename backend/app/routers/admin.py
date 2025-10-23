from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import Optional
from datetime import datetime, timedelta

from ..models_sqlalchemy import get_db
from ..models_sqlalchemy.models import SyncLog
from ..services.auth import admin_required, get_current_active_user
from ..models.user import User
from ..services.ebay import ebay_service
from ..services.database import db

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/sync-jobs")
async def get_sync_jobs(
    endpoint: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(admin_required),
    db: Session = Depends(get_db)
):
    """Get all sync jobs for admin dashboard"""
    query = db.query(SyncLog).filter(SyncLog.user_id == current_user.id)
    
    if endpoint:
        query = query.filter(SyncLog.endpoint == endpoint)
    if status:
        query = query.filter(SyncLog.status == status)
    
    total = query.count()
    jobs = query.order_by(desc(SyncLog.sync_started_at)).offset(offset).limit(limit).all()
    
    return {
        "jobs": [
            {
                "id": j.id,
                "job_id": j.job_id,
                "endpoint": j.endpoint,
                "status": j.status,
                "pages_fetched": j.pages_fetched or 0,
                "records_fetched": j.records_fetched or 0,
                "records_stored": j.records_stored or 0,
                "duration_ms": j.duration_ms or 0,
                "error_text": j.error_text,
                "started_at": j.sync_started_at.isoformat() if j.sync_started_at else None,
                "completed_at": j.sync_completed_at.isoformat() if j.sync_completed_at else None
            }
            for j in jobs
        ],
        "total": total,
        "limit": limit,
        "offset": offset
    }


@router.get("/ebay/identity")
async def get_ebay_identity(
    current_user: User = Depends(get_current_active_user)
):
    """Get eBay user identity and privileges"""
    if not current_user.ebay_connected or not current_user.ebay_access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="eBay account not connected"
        )
    
    try:
        identity = await ebay_service.fetch_user_identity(current_user.ebay_access_token)
        privileges = await ebay_service.fetch_user_privileges(current_user.ebay_access_token)
        
        db.update_user(current_user.id, {
            "ebay_username": identity.get("username"),
            "ebay_user_id": identity.get("userId")
        })
        
        return {
            "identity": identity,
            "privileges": privileges
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/ebay/orders/sample")
async def get_orders_sample(
    current_user: User = Depends(get_current_active_user)
):
    """Get sample orders to verify account connection"""
    if not current_user.ebay_connected or not current_user.ebay_access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="eBay account not connected"
        )
    
    try:
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=1095)  # 3 years
        
        filter_params = {
            "filter": f"creationdate:[{start_date.strftime('%Y-%m-%dT%H:%M:%S.000Z')}..{end_date.strftime('%Y-%m-%dT%H:%M:%S.000Z')}]",
            "limit": 10
        }
        
        orders_response = await ebay_service.fetch_orders(current_user.ebay_access_token, filter_params)
        
        orders = orders_response.get('orders', [])
        total = orders_response.get('total', 0)
        
        sample_orders = [
            {
                "orderId": order.get("orderId"),
                "creationDate": order.get("creationDate"),
                "orderFulfillmentStatus": order.get("orderFulfillmentStatus"),
                "totalAmount": order.get("pricingSummary", {}).get("total", {})
            }
            for order in orders[:5]
        ]
        
        return {
            "total_orders": total,
            "sample_orders": sample_orders,
            "warning": "Connected account has no orders in the period; verify you authorized the correct seller" if total == 0 else None
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/ebay/finances/check")
async def check_finances(
    marketplace: str = Query("EBAY_US", description="Marketplace ID"),
    current_user: User = Depends(get_current_active_user)
):
    """Check finances API with no filter and get payments program status"""
    if not current_user.ebay_connected or not current_user.ebay_access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="eBay account not connected"
        )
    
    try:
        filter_params = {
            "limit": 200
        }
        
        transactions_response = await ebay_service.fetch_transactions(
            current_user.ebay_access_token, 
            filter_params
        )
        
        try:
            payments_program = await ebay_service.fetch_payments_program(current_user.ebay_access_token)
        except Exception as e:
            payments_program = {"error": str(e)}
        
        return {
            "transactions_count": transactions_response.get('total', 0),
            "transactions_sample": transactions_response.get('transactions', [])[:5],
            "payments_program": payments_program,
            "marketplace": marketplace
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/ebay/token-health")
async def get_token_health(
    current_user: User = Depends(get_current_active_user)
):
    """Get eBay token health and expiry information"""
    if not current_user.ebay_connected:
        return {
            "connected": False,
            "status": "not_connected",
            "message": "eBay account not connected"
        }
    
    now = datetime.utcnow()
    expires_at = current_user.ebay_token_expires_at
    
    if not expires_at:
        return {
            "connected": True,
            "status": "unknown",
            "message": "Token expiry time not available"
        }
    
    time_until_expiry = expires_at - now
    seconds_until_expiry = time_until_expiry.total_seconds()
    
    if seconds_until_expiry < 0:
        status_str = "expired"
        health = "unhealthy"
    elif seconds_until_expiry < 300:  # 5 minutes
        status_str = "expiring_soon"
        health = "warning"
    else:
        status_str = "healthy"
        health = "healthy"
    
    return {
        "connected": True,
        "status": status_str,
        "health": health,
        "expires_at": expires_at.isoformat(),
        "expires_in_seconds": int(seconds_until_expiry),
        "expires_in_minutes": int(seconds_until_expiry / 60),
        "has_refresh_token": bool(current_user.ebay_refresh_token),
        "environment": current_user.ebay_environment
    }


@router.post("/ebay/refresh-token")
async def refresh_token_manually(
    current_user: User = Depends(get_current_active_user)
):
    """Manually refresh eBay access token"""
    if not current_user.ebay_connected or not current_user.ebay_refresh_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="eBay account not connected or no refresh token available"
        )
    
    try:
        token_response = await ebay_service.refresh_access_token(current_user.ebay_refresh_token)
        ebay_service.save_user_tokens(current_user.id, token_response)
        
        return {
            "success": True,
            "message": "Token refreshed successfully",
            "expires_at": (datetime.utcnow() + timedelta(seconds=token_response.expires_in)).isoformat()
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to refresh token: {str(e)}"
        )


@router.post("/ebay/refresh-all-tokens")
async def refresh_all_tokens(
    current_user: User = Depends(admin_required)
):
    """Background job to refresh all expiring tokens (admin only)"""
    try:
        from ..services.database import db as database_service
        
        now = datetime.utcnow()
        threshold = now + timedelta(minutes=5)
        
        refreshed_count = 0
        failed_count = 0
        errors = []
        
        all_users = database_service.get_all_users()
        
        for user in all_users:
            if not user.ebay_connected or not user.ebay_refresh_token:
                continue
            
            if not user.ebay_token_expires_at or user.ebay_token_expires_at <= threshold:
                try:
                    token_response = await ebay_service.refresh_access_token(user.ebay_refresh_token)
                    ebay_service.save_user_tokens(user.id, token_response)
                    refreshed_count += 1
                except Exception as e:
                    failed_count += 1
                    errors.append({
                        "user_id": user.id,
                        "email": user.email,
                        "error": str(e)
                    })
        
        return {
            "success": True,
            "refreshed_count": refreshed_count,
            "failed_count": failed_count,
            "errors": errors if errors else None
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to refresh tokens: {str(e)}"
        )
