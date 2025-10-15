from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class EbayAuthRequest(BaseModel):
    scopes: Optional[List[str]] = None


class EbayAuthCallback(BaseModel):
    code: str
    state: Optional[str] = None


class EbayTokenResponse(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    expires_in: int
    token_type: str


class EbayConnectionStatus(BaseModel):
    connected: bool
    user_id: Optional[str] = None
    expires_at: Optional[datetime] = None
    scopes: Optional[List[str]] = None
