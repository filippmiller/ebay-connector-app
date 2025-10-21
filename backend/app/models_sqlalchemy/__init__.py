from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

POSTGRES_URL = "postgresql://postgres:EVfiVxDuuwRa8hAx@db.nrpfahjygulsfxmbmfzv.supabase.co:5432/postgres?sslmode=require"
DATABASE_URL = os.getenv("DATABASE_URL", POSTGRES_URL)

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
    echo=False
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
