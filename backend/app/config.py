from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
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
    
    DATABASE_URL: str = "sqlite:///./ebay_connector.db"
    
    class Config:
        env_file = ".env"
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
    def ebay_auth_base_url(self) -> str:
        if self.EBAY_ENVIRONMENT == "sandbox":
            return "https://auth.sandbox.ebay.com"
        return "https://auth.ebay.com"
    
    @property
    def ebay_runame(self) -> Optional[str]:
        if self.EBAY_ENVIRONMENT == "sandbox":
            return self.EBAY_SANDBOX_RUNAME
        return self.EBAY_PRODUCTION_RUNAME


settings = Settings()
