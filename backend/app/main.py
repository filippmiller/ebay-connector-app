from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import auth, ebay, orders, messages, offers
from app.utils.logger import logger

app = FastAPI(title="eBay Connector API", version="1.0.0")

# Disable CORS. Do not remove this for full-stack development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

app.include_router(auth.router)
app.include_router(ebay.router)
app.include_router(orders.router)
app.include_router(messages.router)
app.include_router(offers.router)

@app.on_event("startup")
async def startup_event():
    logger.info("eBay Connector API starting up...")
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
