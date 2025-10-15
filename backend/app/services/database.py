from typing import Dict, Optional
from datetime import datetime
import uuid
from app.models.user import User, UserCreate, UserRole
from app.utils.logger import logger


class InMemoryDatabase:
    
    def __init__(self):
        self.users: Dict[str, User] = {}
        self.password_reset_tokens: Dict[str, str] = {}
        logger.info("Initialized in-memory database")
    
    def create_user(self, user_data: UserCreate, hashed_password: str) -> User:
        user_id = str(uuid.uuid4())
        user = User(
            id=user_id,
            email=user_data.email,
            username=user_data.username,
            hashed_password=hashed_password,
            role=user_data.role,
            created_at=datetime.utcnow()
        )
        self.users[user_id] = user
        logger.info(f"Created user: {user.email} with role: {user.role}")
        return user
    
    def get_user_by_email(self, email: str) -> Optional[User]:
        for user in self.users.values():
            if user.email == email:
                return user
        return None
    
    def get_user_by_id(self, user_id: str) -> Optional[User]:
        return self.users.get(user_id)
    
    def update_user(self, user_id: str, updates: dict) -> Optional[User]:
        user = self.users.get(user_id)
        if user:
            for key, value in updates.items():
                if hasattr(user, key):
                    setattr(user, key, value)
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


db = InMemoryDatabase()
