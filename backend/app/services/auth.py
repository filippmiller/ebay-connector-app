from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
import hashlib
import os
import binascii
from fastapi import Depends, HTTPException, status, Query, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.config import settings
from app.models.user import User as UserModel, UserCreate
from app.services.database import db
from app.utils.logger import logger

security = HTTPBearer()

# New default password hashing scheme: PBKDF2-HMAC-SHA256 with salt and iterations.
# Stored format: "pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>".
_PBKDF2_ALGO_PREFIX = "pbkdf2_sha256"
_PBKDF2_ITERATIONS = 100_000
_PBKDF2_SALT_BYTES = 16


def _pbkdf2_hash_password(password: str) -> str:
    """Return a PBKDF2-SHA256 hash string for the given password.

    The raw key is derived using a random salt and a fixed number of iterations.
    """
    if not isinstance(password, str):
        raise TypeError("password must be a string")

    salt = os.urandom(_PBKDF2_SALT_BYTES)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    salt_hex = binascii.hexlify(salt).decode("ascii")
    hash_hex = binascii.hexlify(dk).decode("ascii")
    return f"{_PBKDF2_ALGO_PREFIX}${_PBKDF2_ITERATIONS}${salt_hex}${hash_hex}"


def _pbkdf2_verify_password(password: str, encoded: str) -> bool:
    """Verify a password against a PBKDF2-SHA256 encoded hash.

    Returns False if the hash is malformed.
    """
    try:
        prefix, iter_str, salt_hex, hash_hex = encoded.split("$", 3)
        if prefix != _PBKDF2_ALGO_PREFIX:
            return False
        iterations = int(iter_str)
        salt = binascii.unhexlify(salt_hex.encode("ascii"))
        expected = binascii.unhexlify(hash_hex.encode("ascii"))
    except Exception:
        return False

    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    # Constant-time comparison
    return hashlib.sha256(dk).hexdigest() == hashlib.sha256(expected).hexdigest()


def _is_legacy_sha256_hash(stored: str) -> bool:
    """Return True if the stored hash looks like the old plain SHA-256 hex value.

    The legacy format was simply sha256(password).hexdigest() with no prefix.
    Anything that is not our PBKDF2 prefix we treat as legacy.
    """
    return not (isinstance(stored, str) and stored.startswith(_PBKDF2_ALGO_PREFIX + "$"))


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against either the new PBKDF2 hash or legacy SHA-256.

    New hashes use the pbkdf2_sha256$... format. Legacy hashes are plain
    SHA-256 hex digests without a prefix.
    """
    if not hashed_password:
        return False

    # New format first
    if isinstance(hashed_password, str) and hashed_password.startswith(_PBKDF2_ALGO_PREFIX + "$"):
        return _pbkdf2_verify_password(plain_password, hashed_password)

    # Fallback to legacy SHA-256 comparison
    return hashlib.sha256(plain_password.encode("utf-8")).hexdigest() == hashed_password


def get_password_hash(password: str) -> str:
    """Return a password hash for storage.

    New users and password resets always use PBKDF2-SHA256. Legacy SHA-256
    hashes are only kept for backwards compatibility with existing accounts.
    """
    return _pbkdf2_hash_password(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=settings.ALGORITHM)
    return encoded_jwt


def authenticate_user(email: str, password: str) -> Optional[UserModel]:
    """Authenticate a user by email and password.

    Supports both legacy SHA-256 hashes and the new PBKDF2-SHA256 scheme.
    On successful authentication with a legacy hash, the stored hash is
    transparently upgraded to PBKDF2-SHA256.
    """
    user = db.get_user_by_email(email)
    if not user:
        logger.warning(f"Authentication failed: User not found - {email}")
        return None

    stored_hash = getattr(user, "hashed_password", None)
    if not verify_password(password, stored_hash):
        logger.warning(f"Authentication failed: Invalid password - {email}")
        return None

    # On successful authentication, upgrade legacy SHA-256 hashes in-place.
    try:
        if _is_legacy_sha256_hash(stored_hash):
            new_hash = get_password_hash(password)
            db.update_user(user.id, {"hashed_password": new_hash})
            # Refresh user object if the DB layer returns an ORM instance.
            try:
                user.hashed_password = new_hash  # type: ignore[assignment]
            except Exception:
                # Best-effort; not critical if the in-memory object is stale.
                pass
            logger.info(f"Password hash upgraded to PBKDF2 for user: {email}")
    except Exception as e:
        # Do not fail login if re-hash fails; just log the error.
        logger.warning(f"Password hash upgrade failed for {email}: {type(e).__name__}: {e}")

    logger.info(f"User authenticated successfully: {email}")
    return user


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> UserModel:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        token = credentials.credentials
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError as e:
        logger.error(f"JWT validation error: {str(e)}")
        raise credentials_exception
    
    user = db.get_user_by_id(user_id)
    if user is None:
        logger.error(f"User not found for token: {user_id}")
        raise credentials_exception
    
    return user


async def get_current_active_user(current_user: UserModel = Depends(get_current_user)) -> UserModel:
    if not current_user.is_active:
        logger.warning(f"Inactive user attempted access: {current_user.email}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive"
        )
    return current_user


async def admin_required(current_user: UserModel = Depends(get_current_user)) -> UserModel:
    from app.models.user import UserRole
    if current_user.role != UserRole.ADMIN:
        logger.warning(f"Non-admin user attempted admin action: {current_user.email}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user


async def get_user_from_header_or_query(
    request: Request,
    token: Optional[str] = Query(None, description="JWT token for SSE authentication")
) -> UserModel:
    """
    Authentication dependency that accepts JWT from either:
    1. Authorization header (standard for most endpoints)
    2. Query parameter 'token' (for SSE/EventSource which can't send custom headers)
    
    This is specifically designed for SSE endpoints where EventSource API
    doesn't support custom headers.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    jwt_token = None
    
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        jwt_token = auth_header.replace("Bearer ", "")
    elif token:
        jwt_token = token
    
    if not jwt_token:
        logger.warning("SSE authentication failed: No token provided in header or query")
        raise credentials_exception
    
    try:
        payload = jwt.decode(jwt_token, settings.secret_key, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError as e:
        logger.error(f"SSE JWT validation error: {str(e)}")
        raise credentials_exception
    
    user = db.get_user_by_id(user_id)
    if user is None:
        logger.error(f"SSE: User not found for token: {user_id}")
        raise credentials_exception
    
    if not user.is_active:
        logger.warning(f"SSE: Inactive user attempted access: {user.email}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive"
        )
    
    return user


def register_user(user_data: UserCreate) -> UserModel:
    existing_user = db.get_user_by_email(user_data.email)
    if existing_user:
        logger.warning(f"Registration failed: Email already exists - {user_data.email}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    ADMIN_EMAILS = [
        "filippmiller@gmail.com",
        "mylifeis0plus1@gmail.com",
        "nikitin.sergei.v@gmail.com"
    ]
    
    from app.models.user import UserRole
    if user_data.email.lower() in [email.lower() for email in ADMIN_EMAILS]:
        user_data.role = UserRole.ADMIN
        logger.info(f"Admin role assigned to: {user_data.email}")
    else:
        user_data.role = UserRole.USER
        logger.info(f"User role assigned to: {user_data.email}")
    
    hashed_password = get_password_hash(user_data.password)
    user = db.create_user(user_data, hashed_password)
    logger.info(f"New user registered: {user.email} with role: {user.role}")
    return user
