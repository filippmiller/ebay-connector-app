"""
Token Refresh Worker
Runs every 10 minutes to check for tokens expiring within 5 minutes and refreshes them.
"""
import asyncio
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.ebay_account_service import ebay_account_service
from app.services.ebay import ebay_service
from app.utils.logger import logger


async def refresh_expiring_tokens():
    """
    Check for tokens expiring within 5 minutes and refresh them.
    This should be called every 10 minutes.
    """
    logger.info("Starting token refresh worker...")
    
    db = next(get_db())
    try:
        accounts = ebay_account_service.get_accounts_needing_refresh(db, threshold_minutes=5)
        
        if not accounts:
            logger.info("No accounts need token refresh")
            return {
                "status": "completed",
                "accounts_checked": 0,
                "accounts_refreshed": 0,
                "errors": []
            }
        
        logger.info(f"Found {len(accounts)} accounts needing token refresh")
        
        refreshed_count = 0
        errors = []
        
        for account in accounts:
            try:
                token = ebay_account_service.get_token(db, account.id)
                
                if not token or not token.refresh_token:
                    logger.warning(f"Account {account.id} ({account.house_name}) has no refresh token")
                    errors.append({
                        "account_id": account.id,
                        "house_name": account.house_name,
                        "error": "No refresh token available"
                    })
                    continue
                
                logger.info(f"Refreshing token for account {account.id} ({account.house_name})")
                
                new_token_data = await ebay_service.refresh_access_token(token.refresh_token)
                
                ebay_account_service.save_tokens(
                    db,
                    account.id,
                    new_token_data["access_token"],
                    new_token_data.get("refresh_token", token.refresh_token),
                    new_token_data["expires_in"]
                )
                
                refreshed_count += 1
                logger.info(f"Successfully refreshed token for account {account.id} ({account.house_name})")
                
            except Exception as e:
                error_msg = str(e)
                logger.error(f"Failed to refresh token for account {account.id} ({account.house_name}): {error_msg}")
                
                if token:
                    token.refresh_error = error_msg
                    db.commit()
                
                errors.append({
                    "account_id": account.id,
                    "house_name": account.house_name,
                    "error": error_msg
                })
        
        logger.info(f"Token refresh worker completed: {refreshed_count}/{len(accounts)} accounts refreshed")
        
        return {
            "status": "completed",
            "accounts_checked": len(accounts),
            "accounts_refreshed": refreshed_count,
            "errors": errors,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Token refresh worker failed: {str(e)}")
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }
    finally:
        db.close()


async def run_token_refresh_worker_loop():
    """
    Run the token refresh worker in a loop every 10 minutes.
    This is the main entry point for the background worker.
    """
    logger.info("Token refresh worker loop started")
    
    while True:
        try:
            result = await refresh_expiring_tokens()
            logger.info(f"Token refresh cycle completed: {result}")
        except Exception as e:
            logger.error(f"Token refresh worker loop error: {str(e)}")
        
        await asyncio.sleep(600)


if __name__ == "__main__":
    asyncio.run(run_token_refresh_worker_loop())
