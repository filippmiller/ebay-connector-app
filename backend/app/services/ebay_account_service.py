import uuid
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from app.models_sqlalchemy.models import (
    EbayAccount, EbayToken, EbayAuthorization, 
    EbaySyncCursor, EbayHealthEvent
)
from app.models.ebay_account import (
    EbayAccountCreate, EbayAccountUpdate, 
    EbayAccountWithToken, EbayTokenResponse
)
from app.utils.logger import logger


class EbayAccountService:
    
    def create_account(
        self, 
        db: Session, 
        org_id: str, 
        account_data: EbayAccountCreate
    ) -> EbayAccount:
        """Create or update an eBay account"""
        existing = db.query(EbayAccount).filter(
            and_(
                EbayAccount.org_id == org_id,
                EbayAccount.ebay_user_id == account_data.ebay_user_id
            )
        ).first()
        
        if existing:
            existing.username = account_data.username
            existing.house_name = account_data.house_name
            existing.purpose = account_data.purpose
            existing.marketplace_id = account_data.marketplace_id
            existing.site_id = account_data.site_id
            existing.is_active = True
            existing.connected_at = datetime.utcnow()
            existing.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(existing)
            logger.info(f"Updated existing eBay account: {existing.id} ({account_data.house_name})")
            return existing
        
        account_id = str(uuid.uuid4())
        account = EbayAccount(
            id=account_id,
            org_id=org_id,
            ebay_user_id=account_data.ebay_user_id,
            username=account_data.username,
            house_name=account_data.house_name,
            purpose=account_data.purpose,
            marketplace_id=account_data.marketplace_id,
            site_id=account_data.site_id,
            connected_at=datetime.utcnow(),
            is_active=True
        )
        db.add(account)
        db.commit()
        db.refresh(account)
        logger.info(f"Created new eBay account: {account_id} ({account_data.house_name})")
        return account
    
    def get_account(self, db: Session, account_id: str) -> Optional[EbayAccount]:
        """Get an eBay account by ID"""
        return db.query(EbayAccount).filter(EbayAccount.id == account_id).first()
    
    def get_accounts_by_org(
        self, 
        db: Session, 
        org_id: str, 
        active_only: bool = True
    ) -> List[EbayAccount]:
        """Get all eBay accounts for an organization"""
        query = db.query(EbayAccount).filter(EbayAccount.org_id == org_id)
        if active_only:
            query = query.filter(EbayAccount.is_active == True)
        # Prefer most recently connected accounts first
        query = query.order_by(EbayAccount.connected_at.desc(), EbayAccount.updated_at.desc())
        return query.all()
    
    def update_account(
        self, 
        db: Session, 
        account_id: str, 
        updates: EbayAccountUpdate
    ) -> Optional[EbayAccount]:
        """Update an eBay account"""
        account = self.get_account(db, account_id)
        if not account:
            return None
        
        if updates.house_name is not None:
            account.house_name = updates.house_name
        if updates.is_active is not None:
            account.is_active = updates.is_active
        if updates.purpose is not None:
            account.purpose = updates.purpose
        
        account.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(account)
        logger.info(f"Updated eBay account: {account_id}")
        return account
    
    def save_tokens(
        self, 
        db: Session, 
        account_id: str, 
        access_token: str,
        refresh_token: Optional[str],
        expires_in: int,
        token_type: str = "Bearer"
    ) -> EbayToken:
        """Save or update tokens for an account"""
        expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
        
        existing_token = db.query(EbayToken).filter(
            EbayToken.ebay_account_id == account_id
        ).first()
        
        if existing_token:
            existing_token.access_token = access_token
            if refresh_token:
                existing_token.refresh_token = refresh_token
            existing_token.token_type = token_type
            existing_token.expires_at = expires_at
            existing_token.last_refreshed_at = datetime.utcnow()
            existing_token.refresh_error = None
            existing_token.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(existing_token)
            logger.info(f"Updated tokens for account: {account_id}")
            return existing_token
        
        token_id = str(uuid.uuid4())
        token = EbayToken(
            id=token_id,
            ebay_account_id=account_id,
            access_token=access_token,
            refresh_token=refresh_token,
            token_type=token_type,
            expires_at=expires_at,
            last_refreshed_at=datetime.utcnow()
        )
        db.add(token)
        db.commit()
        db.refresh(token)
        logger.info(f"Created tokens for account: {account_id}")
        return token
    
    def get_token(self, db: Session, account_id: str) -> Optional[EbayToken]:
        """Get token for an account"""
        return db.query(EbayToken).filter(
            EbayToken.ebay_account_id == account_id
        ).first()
    
    def save_authorizations(
        self, 
        db: Session, 
        account_id: str, 
        scopes: List[str]
    ) -> EbayAuthorization:
        """Save authorization scopes for an account"""
        existing_auth = db.query(EbayAuthorization).filter(
            EbayAuthorization.ebay_account_id == account_id
        ).first()
        
        if existing_auth:
            existing_auth.scopes = scopes
            existing_auth.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(existing_auth)
            return existing_auth
        
        auth_id = str(uuid.uuid4())
        auth = EbayAuthorization(
            id=auth_id,
            ebay_account_id=account_id,
            scopes=scopes
        )
        db.add(auth)
        db.commit()
        db.refresh(auth)
        return auth
    
    def get_accounts_with_status(
        self, 
        db: Session, 
        org_id: str
    ) -> List[EbayAccountWithToken]:
        """Get all accounts with their token status"""
        accounts = self.get_accounts_by_org(db, org_id, active_only=False)
        result = []
        
        for account in accounts:
            token = self.get_token(db, account.id)
            
            status = self._calculate_status(token)
            expires_in_seconds = None
            
            if token and token.expires_at:
                expires_in_seconds = int((token.expires_at - datetime.utcnow()).total_seconds())
            
            last_health = db.query(EbayHealthEvent).filter(
                EbayHealthEvent.ebay_account_id == account.id
            ).order_by(EbayHealthEvent.checked_at.desc()).first()
            
            account_with_status = EbayAccountWithToken(
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
            result.append(account_with_status)
        
        return result
    
    def _calculate_status(self, token: Optional[EbayToken]) -> str:
        """Calculate account status based on token"""
        if not token:
            return "not_connected"
        
        if token.refresh_error:
            return "error"
        
        if not token.expires_at:
            return "unknown"
        
        now = datetime.utcnow()
        time_until_expiry = token.expires_at - now
        
        if time_until_expiry.total_seconds() < 0:
            return "expired"
        elif time_until_expiry.total_seconds() < 900:  # 15 minutes
            return "expiring_soon"
        else:
            return "healthy"
    
    def get_accounts_needing_refresh(
        self, 
        db: Session, 
        threshold_minutes: int = 5
    ) -> List[EbayAccount]:
        """Get accounts whose tokens need refresh"""
        threshold = datetime.utcnow() + timedelta(minutes=threshold_minutes)
        
        tokens = db.query(EbayToken).filter(
            or_(
                EbayToken.expires_at <= threshold,
                EbayToken.expires_at == None
            )
        ).all()
        
        account_ids = [t.ebay_account_id for t in tokens]
        
        if not account_ids:
            return []
        
        accounts = db.query(EbayAccount).filter(
            and_(
                EbayAccount.id.in_(account_ids),
                EbayAccount.is_active == True
            )
        ).all()
        
        return accounts
    
    def record_health_check(
        self, 
        db: Session, 
        account_id: str, 
        is_healthy: bool,
        http_status: Optional[int] = None,
        ack: Optional[str] = None,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
        response_time_ms: Optional[int] = None
    ) -> EbayHealthEvent:
        """Record a health check event"""
        event_id = str(uuid.uuid4())
        event = EbayHealthEvent(
            id=event_id,
            ebay_account_id=account_id,
            checked_at=datetime.utcnow(),
            is_healthy=is_healthy,
            http_status=http_status,
            ack=ack,
            error_code=error_code,
            error_message=error_message,
            response_time_ms=response_time_ms
        )
        db.add(event)
        db.commit()
        db.refresh(event)
        return event


ebay_account_service = EbayAccountService()
