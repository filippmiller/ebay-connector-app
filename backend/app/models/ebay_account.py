from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class EbayAccountBase(BaseModel):
    house_name: str
    purpose: str = "BOTH"
    marketplace_id: Optional[str] = None
    site_id: Optional[int] = None


class EbayAccountCreate(EbayAccountBase):
    ebay_user_id: str
    username: Optional[str] = None


class EbayAccountUpdate(BaseModel):
    house_name: Optional[str] = None
    is_active: Optional[bool] = None
    purpose: Optional[str] = None


class EbayAccountResponse(EbayAccountBase):
    id: str
    org_id: str
    ebay_user_id: str
    username: Optional[str]
    connected_at: datetime
    is_active: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class EbayTokenResponse(BaseModel):
    id: str
    ebay_account_id: str
    expires_at: Optional[datetime]
    last_refreshed_at: Optional[datetime]
    refresh_error: Optional[str]
    
    class Config:
        from_attributes = True


class EbayAccountWithToken(EbayAccountResponse):
    token: Optional[EbayTokenResponse]
    status: str
    expires_in_seconds: Optional[int]
    last_health_check: Optional[datetime]
    health_status: Optional[str]


class EbayAuthorizationResponse(BaseModel):
    id: str
    ebay_account_id: str
    scopes: List[str]
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class EbayHealthEventResponse(BaseModel):
    id: str
    ebay_account_id: str
    checked_at: datetime
    is_healthy: bool
    http_status: Optional[int]
    error_code: Optional[str]
    error_message: Optional[str]
    response_time_ms: Optional[int]
    
    class Config:
        from_attributes = True
