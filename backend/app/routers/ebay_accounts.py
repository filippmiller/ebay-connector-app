from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timezone

from app.database import get_db
from app.services.auth import get_current_user
from app.models_sqlalchemy.models import User
from app.models.ebay_account import (
    EbayAccountResponse, EbayAccountWithToken, 
    EbayAccountUpdate, EbayAuthorizationResponse,
    EbayHealthEventResponse
)
from app.services.ebay_account_service import ebay_account_service
from app.utils.logger import logger

router = APIRouter(prefix="/ebay-accounts", tags=["eBay Accounts"])


@router.get("/", response_model=List[EbayAccountWithToken])
async def get_accounts(
    active_only: bool = Query(True, description="Only return active accounts"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all eBay accounts for the current organization"""
    try:
        accounts = ebay_account_service.get_accounts_with_status(db, current_user.id)
        
        if active_only:
            accounts = [acc for acc in accounts if acc.is_active]
        
        logger.info(f"Retrieved {len(accounts)} eBay accounts for org: {current_user.id}")
        return accounts
    except Exception as e:
        logger.error(f"Error retrieving eBay accounts: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{account_id}", response_model=EbayAccountWithToken)
async def get_account(
    account_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a specific eBay account"""
    try:
        account = ebay_account_service.get_account(db, account_id)
        
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")
        
        if account.org_id != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        token = ebay_account_service.get_token(db, account_id)
        status = ebay_account_service._calculate_status(token)
        expires_in_seconds = None
        
        if token and token.expires_at:
            from app.services.ebay_account_service import ebay_account_service as svc
            expires_at_utc = svc._to_utc(token.expires_at)
            now_utc = datetime.now(timezone.utc)
            expires_in_seconds = int((expires_at_utc - now_utc).total_seconds())
        
        from app.models_sqlalchemy.models import EbayHealthEvent
        last_health = db.query(EbayHealthEvent).filter(
            EbayHealthEvent.ebay_account_id == account_id
        ).order_by(EbayHealthEvent.checked_at.desc()).first()
        
        from app.models.ebay_account import EbayTokenResponse
        return EbayAccountWithToken(
            id=account.id,
            org_id=account.org_id,
            ebay_user_id=account.ebay_user_id,
            username=account.username,
            house_name=account.house_name,
            purpose=account.purpose,
            marketplace_id=account.marketplace_id,
            site_id=account.site_id,
            connected_at=account.connected_at,
            is_active=account.is_active,
            created_at=account.created_at,
            updated_at=account.updated_at,
            token=EbayTokenResponse(
                id=token.id,
                ebay_account_id=token.ebay_account_id,
                expires_at=token.expires_at,
                last_refreshed_at=token.last_refreshed_at,
                refresh_error=token.refresh_error
            ) if token else None,
            status=status,
            expires_in_seconds=expires_in_seconds,
            last_health_check=last_health.checked_at if last_health else None,
            health_status="healthy" if last_health and last_health.is_healthy else "unhealthy" if last_health else "unknown"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving eBay account {account_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{account_id}", response_model=EbayAccountResponse)
async def update_account(
    account_id: str,
    updates: EbayAccountUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update an eBay account"""
    try:
        account = ebay_account_service.get_account(db, account_id)
        
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")
        
        if account.org_id != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        updated_account = ebay_account_service.update_account(db, account_id, updates)
        
        if not updated_account:
            raise HTTPException(status_code=500, detail="Failed to update account")
        
        logger.info(f"Updated eBay account {account_id}")
        return updated_account
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating eBay account {account_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{account_id}/deactivate")
async def deactivate_account(
    account_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Deactivate an eBay account"""
    try:
        account = ebay_account_service.get_account(db, account_id)
        
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")
        
        if account.org_id != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        updates = EbayAccountUpdate(is_active=False)
        ebay_account_service.update_account(db, account_id, updates)
        
        logger.info(f"Deactivated eBay account {account_id}")
        return {"status": "success", "message": "Account deactivated"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deactivating eBay account {account_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{account_id}/refresh-token")
async def force_refresh_token(
    account_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Force refresh the access token for an account"""
    try:
        account = ebay_account_service.get_account(db, account_id)
        
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")
        
        if account.org_id != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        token = ebay_account_service.get_token(db, account_id)
        
        if not token or not token.refresh_token:
            raise HTTPException(status_code=400, detail="No refresh token available")
        
        from app.services.ebay import ebay_service
        
        new_token_data = await ebay_service.refresh_access_token(token.refresh_token)
        
        ebay_account_service.save_tokens(
            db,
            account_id,
            new_token_data["access_token"],
            new_token_data.get("refresh_token", token.refresh_token),
            new_token_data["expires_in"]
        )
        
        logger.info(f"Force refreshed token for account {account_id}")
        return {"status": "success", "message": "Token refreshed successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error refreshing token for account {account_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{account_id}/health-check")
async def run_health_check(
    account_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Run a health check for an account"""
    try:
        account = ebay_account_service.get_account(db, account_id)
        
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")
        
        if account.org_id != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        from app.services.health_check import run_account_health_check
        
        result = await run_account_health_check(db, account_id)
        
        logger.info(f"Health check completed for account {account_id}: {result}")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error running health check for account {account_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{account_id}/authorizations", response_model=List[EbayAuthorizationResponse])
async def get_account_authorizations(
    account_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get authorization scopes for an account"""
    try:
        account = ebay_account_service.get_account(db, account_id)
        
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")
        
        if account.org_id != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        from app.models_sqlalchemy.models import EbayAuthorization
        authorizations = db.query(EbayAuthorization).filter(
            EbayAuthorization.ebay_account_id == account_id
        ).all()
        
        return authorizations
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving authorizations for account {account_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{account_id}/health-events", response_model=List[EbayHealthEventResponse])
async def get_health_events(
    account_id: str,
    limit: int = Query(10, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get recent health check events for an account"""
    try:
        account = ebay_account_service.get_account(db, account_id)
        
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")
        
        if account.org_id != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        from app.models_sqlalchemy.models import EbayHealthEvent
        events = db.query(EbayHealthEvent).filter(
            EbayHealthEvent.ebay_account_id == account_id
        ).order_by(EbayHealthEvent.checked_at.desc()).limit(limit).all()
        
        return events
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving health events for account {account_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
