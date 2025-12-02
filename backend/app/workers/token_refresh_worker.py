"""
Token Refresh Worker (API Proxy Mode)

This worker acts as a scheduler that delegates the actual token refresh work
to the main Web App via an internal API endpoint.

WHY: The worker was unable to decrypt tokens due to environment configuration
issues. The Web App can successfully decrypt tokens, so we proxy through it.
"""
import asyncio
import httpx
import os
from datetime import datetime, timezone
from app.utils.logger import logger

WORKER_INTERVAL_SECONDS = 600  # 10 minutes


async def refresh_expiring_tokens():
    """
    Trigger token refresh by calling the Web App's internal endpoint.
    The Web App handles all the decryption and eBay API calls.
    """
    logger.info("[token-refresh-worker] Triggering refresh via Web App API...")
    
    # Get environment configuration
    web_app_url = os.getenv("WEB_APP_URL", "").rstrip("/")
    internal_api_key = os.getenv("INTERNAL_API_KEY", "")
    
    if not web_app_url:
        error_msg = "WEB_APP_URL not configured"
        logger.error(f"[token-refresh-worker] {error_msg}")
        return {
            "status": "error",
            "error": error_msg,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    
    if not internal_api_key:
        error_msg = "INTERNAL_API_KEY not configured"
        logger.error(f"[token-refresh-worker] {error_msg}")
        return {
            "status": "error",
            "error": error_msg,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    
    endpoint = f"{web_app_url}/api/admin/internal/refresh-tokens"
    
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(
                endpoint,
                json={"internal_api_key": internal_api_key},
            )
            
            if response.status_code == 200:
                data = response.json()
                logger.info(
                    "[token-refresh-worker] SUCCESS: refreshed=%s failed=%s",
                    data.get("refreshed_count", 0),
                    data.get("failed_count", 0),
                )
                return {
                    "status": "completed",
                    "refreshed_count": data.get("refreshed_count", 0),
                    "failed_count": data.get("failed_count", 0),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            else:
                error_msg = f"HTTP {response.status_code}: {response.text}"
                logger.error(f"[token-refresh-worker] API call failed: {error_msg}")
                return {
                    "status": "error",
                    "error": error_msg,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                
    except Exception as e:
        error_msg = str(e)
        logger.error(f"[token-refresh-worker] Exception: {error_msg}", exc_info=True)
        return {
            "status": "error",
            "error": error_msg,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


async def run_token_refresh_worker_loop():
    """
    Run the token refresh worker in a loop every 10 minutes.
    This is the main entry point for the background worker.
    """
    logger.info("Token refresh worker loop started (API Proxy Mode)")
    
    while True:
        try:
            result = await refresh_expiring_tokens()
            logger.info(f"Token refresh cycle completed: {result}")
        except Exception as e:
            logger.error(f"Token refresh worker loop error: {str(e)}")
        
        await asyncio.sleep(WORKER_INTERVAL_SECONDS)


if __name__ == "__main__":
    asyncio.run(run_token_refresh_worker_loop())
