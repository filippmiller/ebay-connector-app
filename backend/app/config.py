from pydantic_settings import BaseSettings
from typing import Optional
import os
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseSettings):
    SECRET_KEY: str = "your-secret-key-change-in-production"
    JWT_SECRET: Optional[str] = None
    ALGORITHM: str = "HS256"
    # Default token lifetime (in minutes). Adjust via ACCESS_TOKEN_EXPIRE_MINUTES env var.
    # Increased from 30 minutes to 300 minutes (~5 hours) to support long-running admin tasks.
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 300
    DEBUG: bool = False

    # Optional OpenAI configuration for internal analytics/AI features.
    # OPENAI_API_KEY must be provided via environment in production; when missing,
    # AI-driven admin features (AI Grid, AI Rules builder) will return a clear
    # error instead of failing with a generic 500.
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_API_BASE_URL: str = os.getenv("OPENAI_API_BASE_URL", "https://api.openai.com")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o")

    # Optional Deepgram API key for high-quality speech-to-text.
    # This key is ONLY used on the backend; it is never exposed to the frontend.
    DEEPGRAM_API_KEY: Optional[str] = None
    
    @property
    def secret_key(self) -> str:
        return self.JWT_SECRET or self.SECRET_KEY
    
    EBAY_ENVIRONMENT: str = "sandbox"

    # Mode for the eBay listing worker. When set to "stub" (default), the
    # worker uses in-memory stubbed responses and never calls live eBay APIs.
    # When set to "live", the worker will resolve eBay accounts/tokens and
    # call real Inventory/Offers APIs for debug runs.
    ebay_listing_mode: str = "stub"  # "stub" or "live"
    
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
    
    # Notification API configuration (destination + verification token)
    #
    # EBAY_NOTIFICATION_DESTINATION_URL should be the externally reachable URL
    # that eBay will call, e.g. "https://api.yourdomain.com/webhooks/ebay/events".
    # EBAY_NOTIFICATION_VERIFICATION_TOKEN is the opaque token used during
    # destination verification challenges (32–80 chars, [A-Za-z0-9_-]).
    EBAY_NOTIFICATION_DESTINATION_URL: Optional[str] = None
    EBAY_NOTIFICATION_VERIFICATION_TOKEN: Optional[str] = None

    # Gmail OAuth configuration for the Integrations module.
    #
    # GMAIL_OAUTH_REDIRECT_BASE_URL should be the public base URL for backend
    # API routes, typically including the /api prefix, e.g.
    #   https://api.yourdomain.com/api
    # The Gmail OAuth callback path will then be appended as
    #   {GMAIL_OAUTH_REDIRECT_BASE_URL}/integrations/gmail/callback
    GMAIL_CLIENT_ID: Optional[str] = None
    GMAIL_CLIENT_SECRET: Optional[str] = None
    GMAIL_OAUTH_REDIRECT_BASE_URL: Optional[str] = None
    # Space-separated list of scopes; default to read-only Gmail access.
    GMAIL_OAUTH_SCOPES: str = "https://www.googleapis.com/auth/gmail.readonly"

    # DATABASE_URL must be provided via environment from Railway (Supabase/Postgres)
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")

    # Supabase API Configuration
    SUPABASE_URL: Optional[str] = None
    SUPABASE_KEY: Optional[str] = None  # Anon key
    SUPABASE_SERVICE_ROLE_KEY: Optional[str] = None  # Service role key

    
    ALLOWED_ORIGINS: str = "http://localhost:5173,http://localhost:3000"
    FRONTEND_URL: str = "http://localhost:5173"

    # Comma-separated allowlists for admin override (for legacy users lacking role)
    ADMIN_EMAIL_ALLOWLIST: Optional[str] = None
    ADMIN_USERNAME_ALLOWLIST: Optional[str] = None
    
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
