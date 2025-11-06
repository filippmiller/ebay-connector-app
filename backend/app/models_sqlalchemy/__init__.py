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

# Configure connection args based on database type
if "sqlite" in DATABASE_URL:
    connect_args = {"check_same_thread": False}
else:
    # Supabase/PostgreSQL connection settings
    connect_args = {
        "connect_timeout": 10,  # Increased timeout for Supabase
        "keepalives": 1,  # Enable TCP keepalive
        "keepalives_idle": 30,  # Start keepalive after 30s idle
        "keepalives_interval": 10,  # Send keepalive every 10s
        "keepalives_count": 5,  # Max 5 keepalive packets before considering dead
    }

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    echo=True,  # Enable SQL query logging for debugging
    pool_pre_ping=True,  # Verify connections before using
    pool_size=5,  # Reduced pool size for Supabase (free tier limit ~60 connections)
    max_overflow=10,  # Allow up to 10 additional connections
    pool_recycle=3600,  # Recycle connections after 1 hour (Supabase idle timeout)
    pool_timeout=30,  # Wait up to 30s for a connection from pool
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
