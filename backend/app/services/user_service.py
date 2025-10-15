from typing import Optional
from datetime import datetime
from sqlalchemy.orm import Session
import uuid
from app.db_models.user import User
from app.models.user import UserCreate
from app.utils.logger import logger

class UserService:
    
    def __init__(self, db: Session):
        self.db = db
        self.password_reset_tokens = {}
    
    def create_user(self, user_data: UserCreate, hashed_password: str) -> User:
        user = User(
            id=str(uuid.uuid4()),
            email=user_data.email,
            username=user_data.username,
            hashed_password=hashed_password,
            role=user_data.role,
            created_at=datetime.utcnow()
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        logger.info(f"Created user: {user.email} with role: {user.role}")
        return user
    
    def get_user_by_email(self, email: str) -> Optional[User]:
        return self.db.query(User).filter(User.email == email).first()
    
    def get_user_by_id(self, user_id: str) -> Optional[User]:
        return self.db.query(User).filter(User.id == user_id).first()
    
    def update_user(self, user_id: str, updates: dict) -> Optional[User]:
        user = self.get_user_by_id(user_id)
        if user:
            for key, value in updates.items():
                if hasattr(user, key):
                    setattr(user, key, value)
            self.db.commit()
            self.db.refresh(user)
            logger.info(f"Updated user: {user.email}")
            return user
        return None
    
    def create_password_reset_token(self, email: str) -> str:
        reset_token = str(uuid.uuid4())
        self.password_reset_tokens[reset_token] = email
        logger.info(f"Created password reset token for: {email}")
        return reset_token
    
    def verify_password_reset_token(self, token: str) -> Optional[str]:
        return self.password_reset_tokens.get(token)
    
    def delete_password_reset_token(self, token: str):
        if token in self.password_reset_tokens:
            del self.password_reset_tokens[token]
