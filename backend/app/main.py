from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import auth, ebay, orders, messages, offers, migration, buying, inventory, transactions, financials, admin, offers_v2, inventory_v2, ebay_accounts
from app.utils.logger import logger
import os
import asyncio
from sqlalchemy import create_engine, text, inspect

app = FastAPI(title="eBay Connector API", version="1.0.0")

from app.config import settings

origins = [o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600,
)

app.include_router(auth.router)
app.include_router(ebay.router)
app.include_router(ebay_accounts.router)
app.include_router(orders.router)
app.include_router(messages.router)
app.include_router(offers.router)
app.include_router(migration.router)
app.include_router(buying.router)
app.include_router(inventory.router)
app.include_router(transactions.router)
app.include_router(financials.router)
app.include_router(admin.router)
app.include_router(offers_v2.router)
app.include_router(inventory_v2.router)

@app.on_event("startup")
async def startup_event():
    logger.info("eBay Connector API starting up...")
    
    from app.config import settings
    database_url = settings.DATABASE_URL
    
    if "postgresql" in database_url:
        logger.info("🐘 Using PostgreSQL database (Supabase)")
        logger.info("📊 Running database migrations...")
        
        try:
            import signal
            
            def timeout_handler(signum, frame):
                raise TimeoutError("Database connection timeout")
            
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(10)
            
            try:
                from alembic.config import Config
                from alembic import command
                
                alembic_cfg = Config("/app/alembic.ini")
                alembic_cfg.set_main_option("sqlalchemy.url", database_url)
                command.upgrade(alembic_cfg, "head")
                logger.info("✅ Database migrations completed successfully!")
                
            except TimeoutError:
                logger.error("⏱️  Database connection timed out - migrations skipped")
            except Exception as e:
                logger.warning(f"⚠️  Alembic migration failed: {e}")
                logger.info("🔨 Creating tables manually...")
                
                try:
                    engine = create_engine(database_url, connect_args={"connect_timeout": 5})
                    from app.models_sqlalchemy.models import Base
                    Base.metadata.create_all(bind=engine)
                    logger.info("✅ Tables created successfully!")
                    
                except Exception as e2:
                    logger.error(f"❌ Failed to create tables: {e2}")
            finally:
                signal.alarm(0)  # Cancel alarm
        
        except Exception as outer_e:
            logger.error(f"❌ Startup database initialization failed: {outer_e}")
        
        logger.info("✅ PostgreSQL configured - attempting to connect...")
        
    else:
        logger.info("Using SQLite database - data persists between restarts")
    
    logger.info("🔄 Starting background workers...")
    try:
        from app.workers import run_token_refresh_worker_loop, run_health_check_worker_loop
        
        asyncio.create_task(run_token_refresh_worker_loop())
        logger.info("✅ Token refresh worker started (runs every 10 minutes)")
        
        asyncio.create_task(run_health_check_worker_loop())
        logger.info("✅ Health check worker started (runs every 15 minutes)")
        
    except Exception as e:
        logger.error(f"⚠️  Failed to start background workers: {e}")
        logger.info("Workers can be run separately if needed")

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
