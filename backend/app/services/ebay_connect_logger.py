from typing import Optional, Dict, Any, List
from app.services.database import db
from app.utils.logger import logger


class EbayConnectLogger:
    def log_event(
        self,
        *,
        user_id: Optional[str],
        environment: str,
        action: str,
        request: Optional[Dict[str, Any]] = None,
        response: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> None:
        try:
            db.create_connect_log(
                user_id=user_id,
                environment=environment,
                action=action,
                request=request,
                response=response,
                error=error,
            )
        except Exception as e:
            logger.error(f"Failed to log eBay connect event {action}: {type(e).__name__}: {str(e)}")

    def get_logs(
        self,
        user_id: str,
        environment: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        try:
            return db.get_connect_logs(user_id, environment, limit)
        except Exception as e:
            logger.error(f"Failed to fetch eBay connect logs: {type(e).__name__}: {str(e)}")
            return []


ebay_connect_logger = EbayConnectLogger()

