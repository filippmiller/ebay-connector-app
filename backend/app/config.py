from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    EBAY_CLIENT_ID: Optional[str] = None
    EBAY_CLIENT_SECRET: Optional[str] = None
    EBAY_REDIRECT_URI: Optional[str] = None
    EBAY_ENVIRONMENT: str = "sandbox"
    
    DATABASE_URL: str = "sqlite:///./ebay_connector.db"
    
    class Config:
        env_file = ".env"


settings = Settings()
