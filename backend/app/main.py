import logging
import sys
import uuid
import traceback
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.routers import auth, ebay, orders, messages, offers, migration, buying, inventory, transactions, financials, admin, offers_v2, inventory_v2, ebay_accounts, ebay_workers, admin_db, grid_layouts, orders_api, grids_data, admin_mssql, ai_messages, timesheets, grid_preferences, admin_migration, tasks
from app.utils.logger import logger
import os
import asyncio
from sqlalchemy import create_engine, text, inspect

# Global logging configuration
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True,
)

app = FastAPI(title="eBay Connector API", version="1.0.0")

from app.config import settings

# CORS configuration - include Cloudflare Pages URL
origins = [o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()]
# Add Cloudflare Pages URL if not already included
cloudflare_url = os.getenv("FRONTEND_URL", "https://ebay-connector-frontend.pages.dev")
if cloudflare_url not in origins:
    origins.append(cloudflare_url)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600,
)

# Request logging middleware with request ID
@app.middleware("http")
async def request_logger(request: Request, call_next):
    rid = uuid.uuid4().hex[:8]
    request.state.rid = rid
    logging.info("→ %s %s rid=%s", request.method, request.url.path, rid)
    try:
        resp = await call_next(request)
        logging.info("← %s status=%s rid=%s", request.url.path, resp.status_code, rid)
        # Add Request ID to response headers for easier debugging
        resp.headers["X-Request-ID"] = rid
        return resp
    except Exception as e:
        logging.exception("Unhandled error rid=%s: %s", rid, str(e))
        error_resp = JSONResponse(
            {"error": "internal_error", "rid": rid, "message": str(e), "type": type(e).__name__},
            status_code=500
        )
        error_resp.headers["X-Request-ID"] = rid
        return error_resp

app.include_router(auth.router)
app.include_router(ebay.router)
app.include_router(ebay_accounts.router)
app.include_router(ebay_workers.router)
app.include_router(orders.router)
app.include_router(orders_api.router)
app.include_router(messages.router)
app.include_router(ai_messages.router)
app.include_router(timesheets.router)
app.include_router(offers.router)
app.include_router(migration.router)
app.include_router(buying.router)
app.include_router(inventory.router)
app.include_router(transactions.router)
app.include_router(financials.router)
app.include_router(admin.router)
app.include_router(admin_db.router)
app.include_router(admin_mssql.router)
app.include_router(admin_migration.router)
app.include_router(grid_layouts.router)
app.include_router(grids_data.router)
app.include_router(offers_v2.router)
app.include_router(inventory_v2.router)
app.include_router(grid_preferences.router)
app.include_router(tasks.router)

@app.on_event("startup")
async def startup_event():
    logger.info("eBay Connector API starting up...")
    
    from app.config import settings
    database_url = settings.DATABASE_URL
    
    if "postgresql" in database_url:
        import re
        masked_url = re.sub(r'://([^:]+):([^@]+)@', r'://\\1:****@', database_url)
        logger.info(f"📊 Database URL: {masked_url}")
    
    if "postgresql" in database_url:
        logger.info("🐘 Using PostgreSQL database (Supabase)")
        logger.info("📊 Running database migrations...")
        
        try:
            import signal
            import warnings
            
            def timeout_handler(signum, frame):
                raise TimeoutError("Database connection timeout")
            
            # Suppress all Alembic warnings globally
            warnings.filterwarnings("ignore", category=UserWarning, module="alembic")
            warnings.filterwarnings("ignore", message=".*revision.*not present.*", category=UserWarning)
            
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(10)
            
            try:
                from alembic.config import Config
                from alembic import command
                
                alembic_cfg = Config("/app/alembic.ini")
                alembic_cfg.set_main_option("sqlalchemy.url", database_url)
                
                # Suppress warnings during migration
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    command.upgrade(alembic_cfg, "head")
                
                logger.info("✅ Database migrations completed successfully!")
                
            except TimeoutError:
                logger.error("⏱️  Database connection timed out - migrations skipped")
            except Exception as e:
                logger.warning(f"⚠️  Alembic migration failed: {e}")
                logger.warning("⚠️  Continuing startup - tables may already exist or will be created manually")
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
            logger.warning("⚠️  Continuing startup despite migration errors - application may still work")
        
        logger.info("✅ PostgreSQL configured - attempting to connect...")
        start_workers = True
    else:
        logger.info("Using SQLite database - data persists between restarts")
        # In SQLite dev mode, skip background workers that depend on SQLAlchemy tables
        start_workers = False
        logger.info("⏭️  Skipping background workers in SQLite dev mode")
    
    if start_workers:
        logger.info("🔄 Starting background workers...")
        try:
            from app.workers import (
                run_token_refresh_worker_loop,
                run_health_check_worker_loop,
                run_ebay_workers_loop,
                run_tasks_reminder_worker_loop,
            )
            
            asyncio.create_task(run_token_refresh_worker_loop())
            logger.info("✅ Token refresh worker started (runs every 10 minutes)")
            
            asyncio.create_task(run_health_check_worker_loop())
            logger.info("✅ Health check worker started (runs every 15 minutes)")

            # eBay data workers loop – runs every 5 minutes and triggers all
            # enabled workers (orders, transactions, offers, messages, cases,
            # finances, active inventory) for all active accounts.
            asyncio.create_task(run_ebay_workers_loop())
            logger.info("✅ eBay workers loop started (runs every 5 minutes)")

            # Tasks & reminders worker – fires due reminders and snoozed reminders.
            asyncio.create_task(run_tasks_reminder_worker_loop())
            logger.info("✅ Tasks & reminders worker started (runs every 60 seconds)")
            
        except Exception as e:
            logger.error(f"⚠️  Failed to start background workers: {e}")
            logger.info("Workers can be run separately if needed")

@app.get("/healthz")
async def healthz():
    return {"status": "ok"}

@app.get("/healthz/db")
async def healthz_db():
    """Database health check endpoint"""
    from fastapi import HTTPException, status
    try:
        from app.models_sqlalchemy import engine
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            result.fetchone()
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        logger.exception("Database health check failed")
        error_detail = f"Database unavailable: {type(e).__name__}: {str(e)}"
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=error_detail
        )

@app.get("/")
async def root():
    return {
        "message": "eBay Connector API",
        "version": "1.0.0",
        "docs": "/docs"
    }
