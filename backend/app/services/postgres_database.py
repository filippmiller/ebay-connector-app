from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid
from sqlalchemy.orm import Session
from app.models.user import User as UserModel, UserCreate, UserRole
from app.models_sqlalchemy.models import User as UserDB, EbayConnectLog
from app.models_sqlalchemy import get_db
from app.utils.logger import logger


class PostgresDatabase:
    
    def create_user(self, user_data: UserCreate, hashed_password: str) -> UserModel:
        user_id = str(uuid.uuid4())
        created_at = datetime.utcnow()
        
        db: Session = next(get_db())
        try:
            db_user = UserDB(
                id=user_id,
                email=user_data.email,
                username=user_data.username,
                hashed_password=hashed_password,
                role=user_data.role.value,
                is_active=True,
                must_change_password=False,
                created_at=created_at,
                updated_at=created_at,
                ebay_connected=False,
                ebay_environment='sandbox'
            )
            db.add(db_user)
            db.commit()
            db.refresh(db_user)
            
            user = UserModel(
                id=db_user.id,
                email=db_user.email,
                username=db_user.username,
                hashed_password=db_user.hashed_password,
                role=UserRole(db_user.role),
                created_at=db_user.created_at,
                ebay_connected=db_user.ebay_connected or False,
                ebay_access_token=db_user.ebay_access_token,
                ebay_refresh_token=db_user.ebay_refresh_token,
                ebay_token_expires_at=db_user.ebay_token_expires_at,
                ebay_environment=db_user.ebay_environment or 'sandbox',
                ebay_sandbox_access_token=getattr(db_user, 'ebay_sandbox_access_token', None),
                ebay_sandbox_refresh_token=getattr(db_user, 'ebay_sandbox_refresh_token', None),
                ebay_sandbox_token_expires_at=getattr(db_user, 'ebay_sandbox_token_expires_at', None)
            )
            
            logger.info(f"Created user: {user.email} with role: {user.role}")
            return user
        finally:
            db.close()
    
    def get_user_by_email(self, email: str) -> Optional[UserModel]:
        db: Session = next(get_db())
        try:
            db_user = db.query(UserDB).filter(UserDB.email == email).first()
            if db_user:
                return self._db_to_model(db_user)
            return None
        except Exception as e:
            logger.error(f"Database error in get_user_by_email for {email}: {type(e).__name__}: {str(e)}")
            raise
        finally:
            db.close()
    
    def get_user_by_id(self, user_id: str) -> Optional[UserModel]:
        db: Session = next(get_db())
        try:
            db_user = db.query(UserDB).filter(UserDB.id == user_id).first()
            if db_user:
                return self._db_to_model(db_user)
            return None
        finally:
            db.close()
    
    def update_user(self, user_id: str, updates: dict) -> Optional[UserModel]:
        if not updates:
            return self.get_user_by_id(user_id)
        
        db: Session = next(get_db())
        try:
            db_user = db.query(UserDB).filter(UserDB.id == user_id).first()
            if not db_user:
                return None
            
            for key, value in updates.items():
                if hasattr(db_user, key):
                    setattr(db_user, key, value)
            
            db_user.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(db_user)
            
            user = self._db_to_model(db_user)
            logger.info(f"Updated user: {user.email}")
            return user
        finally:
            db.close()
    
    def create_password_reset_token(self, email: str) -> str:
        reset_token = str(uuid.uuid4())
        logger.info(f"Created password reset token for: {email}")
        return reset_token
    
    def verify_password_reset_token(self, token: str) -> Optional[str]:
        return None
    
    def delete_password_reset_token(self, token: str):
        pass
    
    def _db_to_model(self, db_user: UserDB) -> UserModel:
        return UserModel(
            id=db_user.id,
            email=db_user.email,
            username=db_user.username,
            hashed_password=db_user.hashed_password,
            role=UserRole(db_user.role.value if hasattr(db_user.role, 'value') else db_user.role),
            is_active=getattr(db_user, 'is_active', True),
            must_change_password=getattr(db_user, 'must_change_password', False),
            created_at=db_user.created_at,
            ebay_connected=db_user.ebay_connected or False,
            ebay_access_token=db_user.ebay_access_token,
            ebay_refresh_token=db_user.ebay_refresh_token,
            ebay_token_expires_at=db_user.ebay_token_expires_at,
            ebay_environment=db_user.ebay_environment or 'sandbox',
            ebay_sandbox_access_token=getattr(db_user, 'ebay_sandbox_access_token', None),
            ebay_sandbox_refresh_token=getattr(db_user, 'ebay_sandbox_refresh_token', None),
            ebay_sandbox_token_expires_at=getattr(db_user, 'ebay_sandbox_token_expires_at', None)
        )

    def create_connect_log(
        self,
        *,
        user_id: Optional[str],
        environment: str,
        action: str,
        request: Optional[Dict[str, Any]] = None,
        response: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> None:
        db: Session = next(get_db())
        try:
            log_entry = EbayConnectLog(
                id=str(uuid.uuid4()),
                user_id=user_id,
                environment=environment or 'sandbox',
                action=action,
                request_method=(request or {}).get('method'),
                request_url=(request or {}).get('url'),
                request_headers=(request or {}).get('headers'),
                request_body=(request or {}).get('body'),
                response_status=(response or {}).get('status'),
                response_headers=(response or {}).get('headers'),
                response_body=(response or {}).get('body'),
                error=error,
                created_at=datetime.utcnow()
            )
            db.add(log_entry)
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to create connect log: {type(e).__name__}: {str(e)}")
        finally:
            db.close()

    def get_connect_logs(
        self,
        user_id: str,
        environment: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        db: Session = next(get_db())
        try:
            query = db.query(EbayConnectLog).filter(EbayConnectLog.user_id == user_id)
            if environment:
                query = query.filter(EbayConnectLog.environment == environment)

            logs = (
                query
                .order_by(EbayConnectLog.created_at.desc())
                .limit(limit)
                .all()
            )

            results: List[Dict[str, Any]] = []
            for log in logs:
                results.append({
                    "id": log.id,
                    "user_id": log.user_id,
                    "environment": log.environment,
                    "action": log.action,
                    "request": {
                        "method": log.request_method,
                        "url": log.request_url,
                        "headers": log.request_headers,
                        "body": log.request_body,
                    },
                    "response": {
                        "status": log.response_status,
                        "headers": log.response_headers,
                        "body": log.response_body,
                    },
                    "error": log.error,
                    "created_at": log.created_at.isoformat() if log.created_at else None,
                })

            return results
        finally:
            db.close()
