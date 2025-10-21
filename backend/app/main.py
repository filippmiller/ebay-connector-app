from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import auth, ebay, orders, messages, offers
from app.utils.logger import logger
import os
from sqlalchemy import create_engine, text, inspect

app = FastAPI(title="eBay Connector API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://ebay-connection-app-k0ge3h93.devinapps.com",
        "http://localhost:5173",
        "http://localhost:3000",
        "*"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600,
)

app.include_router(auth.router)
app.include_router(ebay.router)
app.include_router(orders.router)
app.include_router(messages.router)
app.include_router(offers.router)

@app.on_event("startup")
async def startup_event():
    logger.info("eBay Connector API starting up...")
    
    from app.config import settings
    database_url = settings.DATABASE_URL
    
    if "postgresql" in database_url:
        logger.info("🐘 Using PostgreSQL database (Supabase)")
        logger.info("📊 Running database migrations...")
        
        try:
            from alembic.config import Config
            from alembic import command
            
            alembic_cfg = Config("/app/alembic.ini")
            alembic_cfg.set_main_option("sqlalchemy.url", database_url)
            command.upgrade(alembic_cfg, "head")
            logger.info("✅ Database migrations completed successfully!")
            
        except Exception as e:
            logger.warning(f"⚠️  Alembic migration failed: {e}")
            logger.info("🔨 Creating tables manually...")
            
            try:
                engine = create_engine(database_url)
                from app.models_sqlalchemy.models import Base
                Base.metadata.create_all(bind=engine)
                logger.info("✅ Tables created successfully!")
                
            except Exception as e2:
                logger.error(f"❌ Failed to create tables: {e2}")
        
        logger.info("✅ PostgreSQL database ready - data persists permanently!")
        
    else:
        logger.info("Using SQLite database - data persists between restarts")

@app.get("/healthz")
async def healthz():
    return {"status": "ok"}

@app.get("/")
async def root():
    return {
        "message": "eBay Connector API",
        "version": "1.0.0",
        "docs": "/docs"
    }
