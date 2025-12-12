from fastapi import Depends, HTTPException, status
from app.models.user import User
from app.services.auth import get_current_active_user
from app.utils.logger import logger


async def get_current_admin_user(current_user: User = Depends(get_current_active_user)) -> User:
    """
    Dependency to ensure only admin users can access certain endpoints
    """
    if current_user.role.value != 'admin':
        logger.warning(f"Non-admin user attempted to access admin endpoint: {current_user.email}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
    )
    return current_user


# Alias used by new modules (e.g. accounting) for clarity
require_admin_user = get_current_admin_user
