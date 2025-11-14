from pydantic_settings import BaseSettings
from typing import Optional
import os


class Settings(BaseSettings):
    SECRET_KEY: str = "your-secret-key-change-in-production"
    JWT_SECRET: Optional[str] = None
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    DEBUG: bool = False
    
    @property
    def secret_key(self) -> str:
        return self.JWT_SECRET or self.SECRET_KEY
    
    EBAY_ENVIRONMENT: str = "sandbox"
    
    EBAY_SANDBOX_CLIENT_ID: Optional[str] = None
    EBAY_SANDBOX_DEV_ID: Optional[str] = None
    EBAY_SANDBOX_CERT_ID: Optional[str] = None
    EBAY_SANDBOX_REDIRECT_URI: Optional[str] = None
    EBAY_SANDBOX_RUNAME: Optional[str] = None
    
    EBAY_PRODUCTION_CLIENT_ID: Optional[str] = None
    EBAY_PRODUCTION_DEV_ID: Optional[str] = None
    EBAY_PRODUCTION_CERT_ID: Optional[str] = None
    EBAY_PRODUCTION_REDIRECT_URI: Optional[str] = None
    EBAY_PRODUCTION_RUNAME: Optional[str] = None
    
    # DATABASE_URL must be provided via environment from Railway (Supabase/Postgres)
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    
    ALLOWED_ORIGINS: str = "http://localhost:5173,http://localhost:3000"
    FRONTEND_URL: str = "http://localhost:5173"
    
    class Config:
        # Do not silently read .env in CI; Railway injects env
        env_file = None
        env_file_encoding = "utf-8"
        extra = "ignore"
    
    @property
    def ebay_client_id(self) -> Optional[str]:
        if self.EBAY_ENVIRONMENT == "sandbox":
            return self.EBAY_SANDBOX_CLIENT_ID
        return self.EBAY_PRODUCTION_CLIENT_ID
    
    @property
    def ebay_cert_id(self) -> Optional[str]:
        if self.EBAY_ENVIRONMENT == "sandbox":
            return self.EBAY_SANDBOX_CERT_ID
        return self.EBAY_PRODUCTION_CERT_ID
    
    @property
    def ebay_dev_id(self) -> Optional[str]:
        if self.EBAY_ENVIRONMENT == "sandbox":
            return self.EBAY_SANDBOX_DEV_ID
        return self.EBAY_PRODUCTION_DEV_ID
    
    @property
    def ebay_redirect_uri(self) -> Optional[str]:
        if self.EBAY_ENVIRONMENT == "sandbox":
            return self.EBAY_SANDBOX_REDIRECT_URI
        return self.EBAY_PRODUCTION_REDIRECT_URI
    
    @property
    def ebay_api_base_url(self) -> str:
        if self.EBAY_ENVIRONMENT == "sandbox":
            return "https://api.sandbox.ebay.com"
        return "https://api.ebay.com"
    
    @property
    def ebay_finances_base_url(self) -> str:
        """Base URL for Finances API (uses apiz.* host in production).

        See eBay Finances API docs: production endpoints are served from
        https://apiz.ebay.com, while sandbox uses https://apiz.sandbox.ebay.com.
        """
        if self.EBAY_ENVIRONMENT == "sandbox":
            return "https://apiz.sandbox.ebay.com"
        return "https://apiz.ebay.com"
    
    @property
    def ebay_auth_base_url(self) -> str:
        if self.EBAY_ENVIRONMENT == "sandbox":
            return "https://auth.sandbox.ebay.com"
        return "https://auth.ebay.com"
    
    @property
    def ebay_runame(self) -> Optional[str]:
        if self.EBAY_ENVIRONMENT == "sandbox":
            return self.EBAY_SANDBOX_RUNAME
        return self.EBAY_PRODUCTION_RUNAME


# Enforce no-SQLite policy immediately on import
_db_url = os.getenv("DATABASE_URL")
if not _db_url:
    raise RuntimeError("DATABASE_URL is required (Supabase/Postgres). No SQLite fallback.")
if _db_url.startswith("sqlite"):
    raise RuntimeError("SQLite is not allowed in this project.")

settings = Settings()
