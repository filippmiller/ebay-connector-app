import logging
import sys
from datetime import datetime
from typing import Any, Dict, Optional
import json

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger("ebay_connector")


class EbayConnectionLogger:
    
    def __init__(self):
        self.logs = []
        self.max_logs = 1000
    
    def log_ebay_event(
        self,
        event_type: str,
        description: str,
        request_data: Optional[Dict[str, Any]] = None,
        response_data: Optional[Dict[str, Any]] = None,
        status: str = "info",
        error: Optional[str] = None
    ):
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "event_type": event_type,
            "description": description,
            "request_data": self._sanitize_credentials(request_data) if request_data else None,
            "response_data": self._sanitize_credentials(response_data) if response_data else None,
            "status": status,
            "error": error
        }
        
        self.logs.append(log_entry)
        
        if len(self.logs) > self.max_logs:
            self.logs.pop(0)
        
        log_msg = f"[{event_type}] {description}"
        if error:
            logger.error(f"{log_msg} - Error: {error}")
        else:
            logger.info(log_msg)
        
        return log_entry
    
    def _sanitize_credentials(self, data: Dict[str, Any]) -> Dict[str, Any]:
        if not data:
            return {}
        
        sanitized = data.copy()
        sensitive_keys = [
            "client_secret", "access_token", "refresh_token", 
            "password", "authorization", "client_id"
        ]
        
        for key in sensitive_keys:
            if key in sanitized:
                value = str(sanitized[key])
                if len(value) > 8:
                    sanitized[key] = f"{value[:4]}...{value[-4:]}"
                else:
                    sanitized[key] = "***"
        
        return sanitized
    
    def get_logs(self, limit: Optional[int] = None) -> list:
        if limit:
            return self.logs[-limit:]
        return self.logs
    
    def clear_logs(self):
        self.logs = []
        logger.info("Cleared eBay connection logs")


ebay_logger = EbayConnectionLogger()
