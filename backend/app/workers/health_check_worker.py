"""
Health Check Worker
Runs every 15 minutes to check the health of all active eBay accounts.
"""
import asyncio
from datetime import datetime
from sqlalchemy.orm import Session

from app.database import get_db
from app.models_sqlalchemy.models import EbayAccount
from app.services.health_check import run_account_health_check
from app.utils.logger import logger


async def run_all_health_checks():
    """
    Run health checks for all active eBay accounts.
    This should be called every 15 minutes.
    """
    logger.info("Starting health check worker...")
    
    db = next(get_db())
    try:
        accounts = db.query(EbayAccount).filter(EbayAccount.is_active == True).all()
        
        if not accounts:
            logger.info("No active accounts to check")
            return {
                "status": "completed",
                "accounts_checked": 0,
                "healthy": 0,
                "unhealthy": 0,
                "errors": []
            }
        
        logger.info(f"Running health checks for {len(accounts)} accounts")
        
        healthy_count = 0
        unhealthy_count = 0
        errors = []
        
        for account in accounts:
            try:
                logger.info(f"Health check for account {account.id} ({account.house_name})")
                
                result = await run_account_health_check(db, account.id)
                
                if result.get("status") == "success":
                    healthy_count += 1
                else:
                    unhealthy_count += 1
                    errors.append({
                        "account_id": account.id,
                        "house_name": account.house_name,
                        "error": result.get("error") or result.get("error_message")
                    })
                
                logger.info(f"Health check result for {account.house_name}: {result.get('status')}")
                
            except Exception as e:
                error_msg = str(e)
                logger.error(f"Health check failed for account {account.id} ({account.house_name}): {error_msg}")
                unhealthy_count += 1
                errors.append({
                    "account_id": account.id,
                    "house_name": account.house_name,
                    "error": error_msg
                })
        
        logger.info(f"Health check worker completed: {healthy_count} healthy, {unhealthy_count} unhealthy")
        
        return {
            "status": "completed",
            "accounts_checked": len(accounts),
            "healthy": healthy_count,
            "unhealthy": unhealthy_count,
            "errors": errors,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Health check worker failed: {str(e)}")
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }
    finally:
        db.close()


async def run_health_check_worker_loop():
    """
    Run the health check worker in a loop every 15 minutes.
    This is the main entry point for the background worker.
    """
    logger.info("Health check worker loop started")
    
    while True:
        try:
            result = await run_all_health_checks()
            logger.info(f"Health check cycle completed: {result}")
        except Exception as e:
            logger.error(f"Health check worker loop error: {str(e)}")
        
        await asyncio.sleep(900)


if __name__ == "__main__":
    asyncio.run(run_health_check_worker_loop())
