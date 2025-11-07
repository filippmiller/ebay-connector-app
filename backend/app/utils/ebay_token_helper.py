"""
Helper utilities for managing eBay tokens across sandbox and production environments.
"""
from typing import Optional
from app.models.user import User
from datetime import datetime


def get_user_ebay_token(user: User, environment: Optional[str] = None) -> Optional[str]:
    """
    Get eBay access token for user based on environment.
    If environment is None, uses user.ebay_environment.
    
    Args:
        user: User object
        environment: 'sandbox' or 'production'. If None, uses user.ebay_environment
    
    Returns:
        Access token string or None
    """
    env = environment or user.ebay_environment or "sandbox"
    
    if env == "sandbox":
        return user.ebay_sandbox_access_token if hasattr(user, 'ebay_sandbox_access_token') else None
    else:
        return user.ebay_access_token


def get_user_ebay_refresh_token(user: User, environment: Optional[str] = None) -> Optional[str]:
    """
    Get eBay refresh token for user based on environment.
    If environment is None, uses user.ebay_environment.
    
    Args:
        user: User object
        environment: 'sandbox' or 'production'. If None, uses user.ebay_environment
    
    Returns:
        Refresh token string or None
    """
    env = environment or user.ebay_environment or "sandbox"
    
    if env == "sandbox":
        return user.ebay_sandbox_refresh_token if hasattr(user, 'ebay_sandbox_refresh_token') else None
    else:
        return user.ebay_refresh_token


def get_user_ebay_token_expires_at(user: User, environment: Optional[str] = None) -> Optional[datetime]:
    """
    Get eBay token expiration time for user based on environment.
    If environment is None, uses user.ebay_environment.
    
    Args:
        user: User object
        environment: 'sandbox' or 'production'. If None, uses user.ebay_environment
    
    Returns:
        Expiration datetime or None
    """
    env = environment or user.ebay_environment or "sandbox"
    
    if env == "sandbox":
        return user.ebay_sandbox_token_expires_at if hasattr(user, 'ebay_sandbox_token_expires_at') else None
    else:
        return user.ebay_token_expires_at


def is_user_ebay_connected(user: User, environment: Optional[str] = None) -> bool:
    """
    Check if user is connected to eBay in specified environment.
    
    Args:
        user: User object
        environment: 'sandbox' or 'production'. If None, uses user.ebay_environment
    
    Returns:
        True if connected, False otherwise
    """
    env = environment or user.ebay_environment or "sandbox"
    token = get_user_ebay_token(user, env)
    return token is not None and len(token) > 0

