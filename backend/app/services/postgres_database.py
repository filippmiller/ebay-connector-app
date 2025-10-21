from typing import Optional
from datetime import datetime
import uuid
from sqlalchemy.orm import Session
from app.models.user import User as UserModel, UserCreate, UserRole
from app.models_sqlalchemy.models import User as UserDB
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
                ebay_environment=db_user.ebay_environment or 'sandbox'
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
            role=UserRole(db_user.role),
            created_at=db_user.created_at,
            ebay_connected=db_user.ebay_connected or False,
            ebay_access_token=db_user.ebay_access_token,
            ebay_refresh_token=db_user.ebay_refresh_token,
            ebay_token_expires_at=db_user.ebay_token_expires_at,
            ebay_environment=db_user.ebay_environment or 'sandbox'
        )
