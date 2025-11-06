"""
Utilities for working with eBay tokens and scopes.
"""
import re
from typing import Optional, List, Dict, Any
from datetime import datetime
from app.utils.logger import logger


def mask_token(token: str, show_start: int = 10, show_end: int = 10) -> str:
    """
    Mask eBay access token for display.
    eBay tokens format: v^1.1#i^1#r^0#I^3#f^0#p^1#t^H4sI...
    """
    if not token:
        return "None"
    
    if len(token) <= show_start + show_end:
        return token[:show_start] + "***"
    
    return token[:show_start] + "***" + token[-show_end:]


def extract_token_info(token: str) -> Dict[str, Any]:
    """
    Extract information from eBay token format.
    Format: v^1.1#i^1#r^0#I^3#f^0#p^1#t^H4sI...
    """
    if not token:
        return {"version": None, "format": None, "masked": "None"}
    
    # Try to extract version
    version_match = re.search(r'v\^([\d.]+)', token)
    version = version_match.group(1) if version_match else None
    
    return {
        "version": version,
        "format": "eBay OAuth Token",
        "masked": mask_token(token),
        "length": len(token)
    }


# Required scopes for different APIs
REQUIRED_SCOPES = {
    "identity": ["https://api.ebay.com/oauth/api_scope"],
    "orders": ["https://api.ebay.com/oauth/api_scope/sell.fulfillment"],
    "transactions": ["https://api.ebay.com/oauth/api_scope/sell.finances"],
    "inventory": ["https://api.ebay.com/oauth/api_scope/sell.inventory"],
    "offers": ["https://api.ebay.com/oauth/api_scope/sell.inventory"],
    "disputes": ["https://api.ebay.com/oauth/api_scope/sell.fulfillment"],
    "messages": ["https://api.ebay.com/oauth/api_scope/trading"],
}

# All available scopes (from Dev Portal)
ALL_AVAILABLE_SCOPES = [
    "https://api.ebay.com/oauth/api_scope",  # Base scope for Identity API
    "https://api.ebay.com/oauth/api_scope/sell.account",
    "https://api.ebay.com/oauth/api_scope/sell.fulfillment",
    "https://api.ebay.com/oauth/api_scope/sell.finances",
    "https://api.ebay.com/oauth/api_scope/sell.inventory",
    "https://api.ebay.com/oauth/api_scope/trading",
    "https://api.ebay.com/oauth/api_scope/commerce.identity.readonly",
]


def validate_scopes(user_scopes: List[str], api_name: str) -> Dict[str, Any]:
    """
    Validate if user has required scopes for specific API.
    
    Args:
        user_scopes: List of scopes from user's token
        api_name: Name of API (identity, orders, transactions, etc.)
    
    Returns:
        Dict with validation results
    """
    required = REQUIRED_SCOPES.get(api_name, [])
    user_scopes_set = set(user_scopes) if user_scopes else set()
    required_set = set(required)
    
    missing = required_set - user_scopes_set
    has_all = len(missing) == 0
    
    return {
        "has_all_required": has_all,
        "missing_scopes": list(missing),
        "required_scopes": required,
        "user_scopes": user_scopes,
        "api_name": api_name
    }


def format_scopes_for_display(scopes: List[str]) -> str:
    """
    Format scopes list for display (short names).
    """
    if not scopes:
        return "None"
    
    short_names = []
    for scope in scopes:
        if scope == "https://api.ebay.com/oauth/api_scope":
            short_names.append("base (Identity)")
        elif "/sell.fulfillment" in scope:
            short_names.append("sell.fulfillment")
        elif "/sell.finances" in scope:
            short_names.append("sell.finances")
        elif "/sell.inventory" in scope:
            short_names.append("sell.inventory")
        elif "/sell.account" in scope:
            short_names.append("sell.account")
        elif "/trading" in scope:
            short_names.append("trading")
        else:
            short_names.append(scope.split("/")[-1] if "/" in scope else scope)
    
    return ", ".join(short_names)


def get_scopes_from_user(user: Any) -> List[str]:
    """
    Get scopes from user object.
    Scopes might be stored in user.ebay_scopes or need to be retrieved from token.
    """
    # Check if scopes are stored directly
    if hasattr(user, 'ebay_scopes') and user.ebay_scopes:
        if isinstance(user.ebay_scopes, str):
            # If stored as string, split by comma or space
            return [s.strip() for s in user.ebay_scopes.replace(',', ' ').split() if s.strip()]
        elif isinstance(user.ebay_scopes, list):
            return user.ebay_scopes
    
    # If not stored, return empty list (will need to be retrieved from token or OAuth response)
    return []


def log_request_context(
    api_name: str,
    method: str,
    url: str,
    token: str,
    user_scopes: Optional[List[str]] = None,
    user_email: Optional[str] = None,
    user_id: Optional[str] = None,
    environment: Optional[str] = None,
    additional_headers: Optional[Dict[str, str]] = None
):
    """
    Log full request context for debugging.
    """
    token_info = extract_token_info(token)
    masked_token = token_info["masked"]
    
    # Validate scopes
    scope_validation = validate_scopes(user_scopes or [], api_name)
    
    logger.info(f"[DEBUG] → {method} {url}")
    logger.info(f"        Token: {masked_token} (version: {token_info.get('version', 'unknown')})")
    
    if user_scopes:
        scopes_display = format_scopes_for_display(user_scopes)
        logger.info(f"        Scopes: {scopes_display}")
        
        if scope_validation["missing_scopes"]:
            missing_display = format_scopes_for_display(scope_validation["missing_scopes"])
            logger.warning(f"        ⚠️ Missing required scopes for {api_name}: {missing_display}")
    else:
        logger.warning(f"        ⚠️ Scopes not available (cannot validate)")
    
    if user_email:
        logger.info(f"        User: {user_email} (ID: {user_id[:8] if user_id else 'unknown'}...)")
    
    if environment:
        logger.info(f"        Environment: {environment}")
    
    # Log headers
    headers = {
        "Authorization": f"Bearer {masked_token}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    if additional_headers:
        headers.update(additional_headers)
    
    logger.info(f"        Headers: {headers}")

