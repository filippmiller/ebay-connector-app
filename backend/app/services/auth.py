from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.config import settings
from app.models.user import User as UserModel, UserCreate
from app.db_models.user import User
from app.database import get_db
from app.utils.logger import logger

ph = PasswordHasher()
security = HTTPBearer()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        ph.verify(hashed_password, plain_password)
        return True
    except VerifyMismatchError:
        return False


def get_password_hash(password: str) -> str:
    return ph.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def authenticate_user(email: str, password: str, db: Session) -> Optional[UserModel]:
    user = db.query(User).filter(User.email == email).first()
    if not user:
        logger.warning(f"Authentication failed: User not found - {email}")
        return None
    if not verify_password(password, user.hashed_password):
        logger.warning(f"Authentication failed: Invalid password - {email}")
        return None
    logger.info(f"User authenticated successfully: {email}")
    return UserModel(
        id=user.id,
        email=user.email,
        username=user.username,
        hashed_password=user.hashed_password,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
        ebay_connected=user.ebay_connected
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> UserModel:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        token = credentials.credentials
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError as e:
        logger.error(f"JWT validation error: {str(e)}")
        raise credentials_exception
    
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        logger.error(f"User not found for token: {user_id}")
        raise credentials_exception
    
    return UserModel(
        id=user.id,
        email=user.email,
        username=user.username,
        hashed_password=user.hashed_password,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
        ebay_connected=user.ebay_connected
    )


async def get_current_active_user(current_user: UserModel = Depends(get_current_user)) -> UserModel:
    if not current_user.is_active:
        logger.warning(f"Inactive user attempted access: {current_user.email}")
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


def register_user(user_data: UserCreate, db: Session) -> UserModel:
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        logger.warning(f"Registration failed: Email already exists - {user_data.email}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    hashed_password = get_password_hash(user_data.password)
    user = User(
        email=user_data.email,
        username=user_data.username,
        hashed_password=hashed_password,
        role=user_data.role,
        created_at=datetime.utcnow()
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info(f"New user registered: {user.email}")
    return UserModel(
        id=user.id,
        email=user.email,
        username=user.username,
        hashed_password=user.hashed_password,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
        ebay_connected=user.ebay_connected
    )
