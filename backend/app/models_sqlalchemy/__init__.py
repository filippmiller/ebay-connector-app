from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.config import settings
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

DATABASE_URL = settings.DATABASE_URL

# Normalize DATABASE_URL for Supabase PostgreSQL
# Ensure sslmode=require is present for Supabase connections
if "postgresql" in DATABASE_URL or "postgres" in DATABASE_URL:
    parsed = urlparse(DATABASE_URL)
    query_params = parse_qs(parsed.query)
    
    # Add sslmode=require if not present (required for Supabase)
    if "sslmode" not in query_params:
        query_params["sslmode"] = ["require"]
    
    # Ensure postgresql+psycopg2:// scheme (not just postgres://)
    if parsed.scheme == "postgres":
        scheme = "postgresql+psycopg2"
    elif parsed.scheme == "postgresql":
        scheme = "postgresql+psycopg2"
    else:
        scheme = parsed.scheme
    
    # Reconstruct URL with normalized scheme and sslmode
    normalized_query = urlencode(query_params, doseq=True)
    DATABASE_URL = urlunparse((
        scheme,
        parsed.netloc,
        parsed.path,
        parsed.params,
        normalized_query,
        parsed.fragment
    ))

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {"connect_timeout": 5},
    echo=True,  # Enable SQL query logging for debugging
    pool_pre_ping=True  # Verify connections before using
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
