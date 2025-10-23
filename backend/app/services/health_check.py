import time
from datetime import datetime
from typing import Dict, Any
from sqlalchemy.orm import Session

from app.services.ebay_account_service import ebay_account_service
from app.services.ebay import ebay_service
from app.utils.logger import logger


async def run_account_health_check(db: Session, account_id: str) -> Dict[str, Any]:
    """
    Run a health check for a specific eBay account.
    Makes a lightweight API call to verify token validity and API accessibility.
    """
    start_time = time.time()
    
    try:
        account = ebay_account_service.get_account(db, account_id)
        if not account:
            return {
                "status": "error",
                "message": "Account not found"
            }
        
        token = ebay_account_service.get_token(db, account_id)
        if not token or not token.access_token:
            ebay_account_service.record_health_check(
                db, account_id, False,
                error_message="No access token available"
            )
            return {
                "status": "error",
                "message": "No access token available"
            }
        
        import httpx
        
        xml_request = f"""<?xml version="1.0" encoding="utf-8"?>
<GetUserRequest xmlns="urn:ebay:apis:eBLBaseComponents">
    <RequesterCredentials>
        <eBayAuthToken>{token.access_token}</eBayAuthToken>
    </RequesterCredentials>
    <WarningLevel>High</WarningLevel>
</GetUserRequest>"""
        
        headers = {
            "X-EBAY-API-COMPATIBILITY-LEVEL": "967",
            "X-EBAY-API-CALL-NAME": "GetUser",
            "X-EBAY-API-SITEID": "0",
            "Content-Type": "text/xml"
        }
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                "https://api.ebay.com/ws/api.dll",
                content=xml_request,
                headers=headers
            )
        
        response_time_ms = int((time.time() - start_time) * 1000)
        
        import xml.etree.ElementTree as ET
        root = ET.fromstring(response.text)
        
        ack_elem = root.find(".//{urn:ebay:apis:eBLBaseComponents}Ack")
        ack = ack_elem.text if ack_elem is not None else None
        
        errors = root.findall(".//{urn:ebay:apis:eBLBaseComponents}Errors")
        
        is_healthy = ack in ["Success", "Warning"] and response.status_code == 200
        error_code = None
        error_message = None
        
        if errors:
            error_elem = errors[0]
            error_code_elem = error_elem.find("{urn:ebay:apis:eBLBaseComponents}ErrorCode")
            error_msg_elem = error_elem.find("{urn:ebay:apis:eBLBaseComponents}LongMessage")
            
            error_code = error_code_elem.text if error_code_elem is not None else None
            error_message = error_msg_elem.text if error_msg_elem is not None else None
            
            if error_code:
                is_healthy = False
        
        ebay_account_service.record_health_check(
            db, account_id, is_healthy,
            http_status=response.status_code,
            ack=ack,
            error_code=error_code,
            error_message=error_message,
            response_time_ms=response_time_ms
        )
        
        logger.info(f"Health check for account {account_id}: {ack}, {response_time_ms}ms")
        
        return {
            "status": "success" if is_healthy else "unhealthy",
            "account_id": account_id,
            "ack": ack,
            "http_status": response.status_code,
            "response_time_ms": response_time_ms,
            "error_code": error_code,
            "error_message": error_message,
            "checked_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        response_time_ms = int((time.time() - start_time) * 1000)
        
        ebay_account_service.record_health_check(
            db, account_id, False,
            error_message=str(e),
            response_time_ms=response_time_ms
        )
        
        logger.error(f"Health check failed for account {account_id}: {str(e)}")
        
        return {
            "status": "error",
            "account_id": account_id,
            "error": str(e),
            "response_time_ms": response_time_ms,
            "checked_at": datetime.utcnow().isoformat()
        }


async def run_all_health_checks(db: Session) -> Dict[str, Any]:
    """Run health checks for all active accounts"""
    from app.models_sqlalchemy.models import EbayAccount
    
    accounts = db.query(EbayAccount).filter(EbayAccount.is_active == True).all()
    
    results = []
    for account in accounts:
        result = await run_account_health_check(db, account.id)
        results.append(result)
    
    healthy_count = sum(1 for r in results if r.get("status") == "success")
    
    return {
        "total_accounts": len(accounts),
        "healthy": healthy_count,
        "unhealthy": len(accounts) - healthy_count,
        "results": results,
        "checked_at": datetime.utcnow().isoformat()
    }
