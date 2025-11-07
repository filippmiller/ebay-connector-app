from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from fastapi.responses import StreamingResponse
from typing import Optional, List
from app.models.ebay import EbayAuthRequest, EbayAuthCallback, EbayConnectionStatus
from app.services.auth import get_current_active_user, get_user_from_header_or_query
from app.services.ebay import ebay_service
from app.models.user import User
from app.utils.logger import logger, ebay_logger

router = APIRouter(prefix="/ebay", tags=["ebay"])


@router.post("/auth/start")
async def start_ebay_auth(
    auth_request: EbayAuthRequest,
    redirect_uri: str = Query(..., description="Redirect URI for OAuth callback"),
    environment: str = Query('production', description="eBay environment: sandbox or production"),
    house_name: Optional[str] = Query(None, description="Human-readable name for this eBay account"),
    purpose: str = Query('BOTH', description="Account purpose: BUYER, SELLER, or BOTH"),
    current_user: User = Depends(get_current_active_user)
):
    logger.info(f"Starting eBay OAuth for user: {current_user.email} in {environment} mode, house_name: {house_name}")
    
    from app.config import settings
    import json
    import uuid
    
    original_env = settings.EBAY_ENVIRONMENT
    settings.EBAY_ENVIRONMENT = environment
    
    from app.services.database import db
    db.update_user(current_user.id, {"ebay_environment": environment})
    
    try:
        state_data = {
            "org_id": current_user.id,
            "nonce": str(uuid.uuid4()),
            "house_name": house_name,
            "purpose": purpose,
            "environment": environment
        }
        state = json.dumps(state_data)
        
        auth_url = ebay_service.get_authorization_url(
            redirect_uri=redirect_uri,
            state=state,
            scopes=auth_request.scopes,
            environment=environment
        )
        
        return {
            "authorization_url": auth_url,
            "state": state
        }
    except Exception as e:
        logger.error(f"Error starting eBay auth: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
    finally:
        settings.EBAY_ENVIRONMENT = original_env


@router.post("/auth/callback")
async def ebay_auth_callback(
    callback_data: EbayAuthCallback,
    redirect_uri: str = Query(..., description="Redirect URI used in OAuth start"),
    environment: str = Query('production', description="eBay environment: sandbox or production"),
    current_user: User = Depends(get_current_active_user)
):
    logger.info(f"Processing eBay OAuth callback for user: {current_user.email} in {environment} mode")
    
    import json
    from app.database import get_db
    from app.services.ebay_account_service import ebay_account_service
    from app.models.ebay_account import EbayAccountCreate
    
    state_data = None
    try:
        state_data = json.loads(callback_data.state) if callback_data.state else None
    except:
        pass
    
    if state_data:
        if state_data.get("org_id") != current_user.id:
            logger.warning(f"State org_id mismatch in OAuth callback for user: {current_user.email}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid state parameter"
            )
    
    from app.config import settings
    original_env = settings.EBAY_ENVIRONMENT
    settings.EBAY_ENVIRONMENT = environment
    
    try:
        token_response = await ebay_service.exchange_code_for_token(
            code=callback_data.code,
            redirect_uri=redirect_uri
        )
        
        ebay_user_id = await ebay_service.get_ebay_user_id(token_response.access_token)
        username = await ebay_service.get_ebay_username(token_response.access_token)
        
        house_name = state_data.get("house_name") if state_data else None
        if not house_name:
            house_name = username or ebay_user_id or f"Account-{ebay_user_id[:8]}"
        
        purpose = state_data.get("purpose", "BOTH") if state_data else "BOTH"
        
        db = next(get_db())
        try:
            account_data = EbayAccountCreate(
                ebay_user_id=ebay_user_id,
                username=username,
                house_name=house_name,
                purpose=purpose,
                marketplace_id="EBAY_US",
                site_id=0
            )
            
            account = ebay_account_service.create_account(db, current_user.id, account_data)
            
            ebay_account_service.save_tokens(
                db,
                account.id,
                token_response.access_token,
                token_response.refresh_token,
                token_response.expires_in
            )
            
            scopes = token_response.scope.split() if hasattr(token_response, 'scope') and token_response.scope else []
            if scopes:
                ebay_account_service.save_authorizations(db, account.id, scopes)
            
            ebay_service.save_user_tokens(current_user.id, token_response, environment=environment)
            
            logger.info(f"Successfully connected eBay account: {account.id} ({house_name})")
            
            return {
                "message": "Successfully connected to eBay",
                "account_id": account.id,
                "house_name": house_name,
                "ebay_user_id": ebay_user_id,
                "username": username,
                "expires_in": token_response.expires_in
            }
        finally:
            db.close()
        
    except Exception as e:
        logger.error(f"Error in eBay OAuth callback: {str(e)}")
        raise
    finally:
        settings.EBAY_ENVIRONMENT = original_env


@router.get("/status", response_model=EbayConnectionStatus)
async def get_ebay_status(current_user: User = Depends(get_current_active_user)):
    return EbayConnectionStatus(
        connected=current_user.ebay_connected,
        user_id=current_user.id if current_user.ebay_connected else None,
        expires_at=current_user.ebay_token_expires_at
    )


@router.get("/token-info")
async def get_token_info(
    environment: str = Query(None, description="eBay environment: sandbox or production (default: user's current environment)"),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get full token information for current user (for debugging).
    Returns unmasked token and all related data.
    """
    from app.utils.ebay_token_helper import get_user_ebay_token, is_user_ebay_connected, get_user_ebay_token_expires_at
    
    env = environment or current_user.ebay_environment or "sandbox"
    
    if not is_user_ebay_connected(current_user, env):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"User is not connected to eBay ({env})"
        )
    
    access_token = get_user_ebay_token(current_user, env)
    token_expires_at = get_user_ebay_token_expires_at(current_user, env)
    
    # Get scopes and account info from database
    user_scopes = []
    ebay_user_id = None
    ebay_username = None
    from app.services.ebay_account_service import ebay_account_service
    from app.models_sqlalchemy import get_db
    db_session = next(get_db())
    try:
        accounts = ebay_account_service.get_accounts_by_org(db_session, current_user.id)
        if accounts:
            account = accounts[0]
            ebay_user_id = account.ebay_user_id
            ebay_username = account.username
            
            from app.models_sqlalchemy.models import EbayAuthorization
            auths = db_session.query(EbayAuthorization).filter(
                EbayAuthorization.ebay_account_id == account.id
            ).all()
            user_scopes = [auth.scope for auth in auths] if auths else []
    except Exception as e:
        logger.error(f"Error getting account info: {e}")
    finally:
        db_session.close()
    
    # Get token info
    from app.utils.token_utils import extract_token_info, format_scopes_for_display
    token_info = extract_token_info(access_token) if access_token else {}
    
    return {
        "user_email": current_user.email,
        "user_id": current_user.id,
        "ebay_environment": env,
        "token_full": access_token,  # UNMASKED TOKEN
        "token_length": len(access_token) if access_token else 0,
        "token_version": token_info.get("version"),
        "token_expires_at": token_expires_at.isoformat() if token_expires_at else None,
        "scopes": user_scopes,
        "scopes_display": format_scopes_for_display(user_scopes),
        "scopes_count": len(user_scopes),
        "ebay_connected": is_user_ebay_connected(current_user, env),
        "ebay_user_id": ebay_user_id,
        "ebay_username": ebay_username
    }


@router.post("/disconnect")
async def disconnect_ebay(current_user: User = Depends(get_current_active_user)):
    logger.info(f"Disconnecting eBay for user: {current_user.email}")
    
    from app.services.database import db
    db.update_user(current_user.id, {
        "ebay_connected": False,
        "ebay_access_token": None,
        "ebay_refresh_token": None,
        "ebay_token_expires_at": None
    })
    
    ebay_logger.log_ebay_event(
        "user_disconnected",
        f"User {current_user.id} disconnected from eBay",
        status="success"
    )
    
    return {"message": "Successfully disconnected from eBay"}


@router.get("/logs")
async def get_ebay_logs(
    limit: Optional[int] = Query(100, description="Number of logs to retrieve"),
    current_user: User = Depends(get_current_active_user)
):
    logs = ebay_logger.get_logs(limit=limit)
    return {
        "logs": logs,
        "total": len(logs)
    }


@router.delete("/logs")
async def clear_ebay_logs(current_user: User = Depends(get_current_active_user)):
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can clear logs"
        )
    
    ebay_logger.clear_logs()
    return {"message": "Logs cleared successfully"}


@router.get("/test/orders")
async def test_fetch_orders(
    limit: int = Query(10, description="Number of orders to fetch"),
    current_user: User = Depends(get_current_active_user)
):
    if not current_user.ebay_connected or not current_user.ebay_access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="eBay account not connected. Please connect to eBay first."
        )
    
    logger.info(f"Testing orders fetch for user: {current_user.email}")
    
    from app.config import settings
    original_env = settings.EBAY_ENVIRONMENT
    settings.EBAY_ENVIRONMENT = current_user.ebay_environment
    
    try:
        orders = await ebay_service.fetch_orders(current_user.ebay_access_token, {"limit": limit})
        return orders
    except Exception as e:
        logger.error(f"Error fetching orders: {str(e)}")
        raise
    finally:
        settings.EBAY_ENVIRONMENT = original_env


@router.get("/test/transactions")
async def test_fetch_transactions(
    limit: int = Query(10, description="Number of transactions to fetch"),
    current_user: User = Depends(get_current_active_user)
):
    if not current_user.ebay_connected or not current_user.ebay_access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="eBay account not connected. Please connect to eBay first."
        )
    
    logger.info(f"Testing transactions fetch for user: {current_user.email}")
    
    from app.config import settings
    original_env = settings.EBAY_ENVIRONMENT
    settings.EBAY_ENVIRONMENT = current_user.ebay_environment
    
    try:
        transactions = await ebay_service.fetch_transactions(current_user.ebay_access_token, {"limit": limit})
        return transactions
    except Exception as e:
        logger.error(f"Error fetching transactions: {str(e)}")
        raise
    finally:
        settings.EBAY_ENVIRONMENT = original_env


@router.post("/sync/orders", status_code=status.HTTP_202_ACCEPTED)
async def sync_all_orders(
    background_tasks: BackgroundTasks,
    environment: str = Query(None, description="eBay environment: sandbox or production (default: user's current environment)"),
    current_user: User = Depends(get_current_active_user)
):
    """
    Start orders sync in background and return run_id immediately.
    Client can use run_id to stream live progress via SSE endpoint.
    """
    from app.services.sync_event_logger import SyncEventLogger
    from app.utils.ebay_token_helper import get_user_ebay_token, is_user_ebay_connected
    
    env = environment or current_user.ebay_environment or "sandbox"
    
    if not is_user_ebay_connected(current_user, env):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"eBay account not connected ({env}). Please connect to eBay first."
        )
    
    access_token = get_user_ebay_token(current_user, env)
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"eBay access token not found for {env} environment"
        )
    
    event_logger = SyncEventLogger(current_user.id, 'orders')
    run_id = event_logger.run_id
    
    logger.info(f"Allocated run_id {run_id} for order sync, user: {current_user.email}, environment: {env}")
    
    background_tasks.add_task(
        _run_orders_sync,
        current_user.id,
        access_token,
        env,
        run_id
    )
    
    return {
        "run_id": run_id,
        "status": "started",
        "message": f"Orders sync started in background ({env})"
    }


async def _run_orders_sync(user_id: str, access_token: str, ebay_environment: str, run_id: str):
    """Background task to run orders sync with error handling"""
    from app.config import settings
    
    original_env = settings.EBAY_ENVIRONMENT
    settings.EBAY_ENVIRONMENT = ebay_environment
    
    try:
        # Pass run_id to sync_all_orders so it uses the same run_id for events
        await ebay_service.sync_all_orders(user_id, access_token, run_id=run_id)
    except Exception as e:
        logger.error(f"Background orders sync failed for run_id {run_id}: {str(e)}")
    finally:
        settings.EBAY_ENVIRONMENT = original_env


@router.get("/orders")
async def get_orders(
    limit: int = Query(100, description="Number of orders to return"),
    offset: int = Query(0, description="Offset for pagination"),
    current_user: User = Depends(get_current_active_user)
):
    from app.services.ebay_database import ebay_db
    
    orders = ebay_db.get_orders(current_user.id, limit, offset)
    total = ebay_db.get_order_count(current_user.id)
    
    return {
        "orders": orders,
        "total": total,
        "limit": limit,
        "offset": offset
    }


@router.get("/sync/jobs")
async def get_sync_jobs(
    limit: int = Query(10, description="Number of sync jobs to return"),
    current_user: User = Depends(get_current_active_user)
):
    from app.services.ebay_database import ebay_db
    
    jobs = ebay_db.get_sync_jobs(current_user.id, limit)
    
    return {
        "jobs": jobs,
        "total": len(jobs)
    }


@router.post("/sync/transactions", status_code=status.HTTP_202_ACCEPTED)
async def sync_all_transactions(
    background_tasks: BackgroundTasks,
    environment: str = Query(None, description="eBay environment: sandbox or production (default: user's current environment)"),
    current_user: User = Depends(get_current_active_user)
):
    from app.utils.ebay_token_helper import get_user_ebay_token, is_user_ebay_connected
    
    env = environment or current_user.ebay_environment or "sandbox"
    
    if not is_user_ebay_connected(current_user, env):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"eBay account not connected ({env}). Please connect to eBay first."
        )
    
    access_token = get_user_ebay_token(current_user, env)
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"eBay access token not found for {env} environment"
        )
    
    from app.services.sync_event_logger import SyncEventLogger
    
    event_logger = SyncEventLogger(current_user.id, 'transactions')
    run_id = event_logger.run_id
    
    logger.info(f"Allocated run_id {run_id} for transaction sync, user: {current_user.email}, environment: {env}")
    
    background_tasks.add_task(
        _run_transactions_sync,
        current_user.id,
        access_token,
        env,
        run_id
    )
    
    return {
        "run_id": run_id,
        "status": "started",
        "message": f"Transactions sync started in background ({env})"
    }


async def _run_transactions_sync(user_id: str, access_token: str, ebay_environment: str, run_id: str):
    from app.config import settings
    
    original_env = settings.EBAY_ENVIRONMENT
    settings.EBAY_ENVIRONMENT = ebay_environment
    
    try:
        # Pass run_id to sync_all_transactions so it uses the same run_id for events
        await ebay_service.sync_all_transactions(user_id, access_token, run_id=run_id)
    except Exception as e:
        logger.error(f"Background transactions sync failed for run_id {run_id}: {str(e)}")
    finally:
        settings.EBAY_ENVIRONMENT = original_env


@router.post("/sync/disputes", status_code=status.HTTP_202_ACCEPTED)
async def sync_all_disputes(
    background_tasks: BackgroundTasks,
    environment: str = Query(None, description="eBay environment: sandbox or production (default: user's current environment)"),
    current_user: User = Depends(get_current_active_user)
):
    from app.services.sync_event_logger import SyncEventLogger
    from app.utils.ebay_token_helper import get_user_ebay_token, is_user_ebay_connected
    
    env = environment or current_user.ebay_environment or "sandbox"
    
    if not is_user_ebay_connected(current_user, env):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"eBay account not connected ({env}). Please connect to eBay first."
        )
    
    access_token = get_user_ebay_token(current_user, env)
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"eBay access token not found for {env} environment"
        )
    
    event_logger = SyncEventLogger(current_user.id, 'disputes')
    run_id = event_logger.run_id
    
    logger.info(f"Allocated run_id {run_id} for disputes sync, user: {current_user.email}, environment: {env}")
    
    background_tasks.add_task(
        _run_disputes_sync,
        current_user.id,
        access_token,
        env,
        run_id
    )
    
    return {
        "run_id": run_id,
        "status": "started",
        "message": f"Disputes sync started in background ({env})"
    }


async def _run_disputes_sync(user_id: str, access_token: str, ebay_environment: str, run_id: str):
    from app.config import settings
    
    original_env = settings.EBAY_ENVIRONMENT
    settings.EBAY_ENVIRONMENT = ebay_environment
    
    try:
        # Pass run_id to sync_all_disputes so it uses the same run_id for events
        await ebay_service.sync_all_disputes(user_id, access_token, run_id=run_id)
    except Exception as e:
        logger.error(f"Background disputes sync failed for run_id {run_id}: {str(e)}")
    finally:
        settings.EBAY_ENVIRONMENT = original_env


@router.get("/disputes")
async def get_disputes(
    limit: int = Query(100, description="Number of disputes to return"),
    offset: int = Query(0, description="Offset for pagination"),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get all disputes from database for the current user.
    """
    from app.services.ebay_database import ebay_db
    from sqlalchemy import text
    
    session = ebay_db._get_session()
    
    try:
        query = text("""
            SELECT 
                id,
                dispute_id,
                order_id,
                dispute_reason as reason,
                dispute_status as status,
                open_date,
                respond_by_date,
                dispute_data,
                created_at,
                updated_at
            FROM ebay_disputes
            WHERE user_id = :user_id
            ORDER BY open_date DESC
            LIMIT :limit OFFSET :offset
        """)
        
        result = session.execute(query, {
            'user_id': current_user.id,
            'limit': limit,
            'offset': offset
        })
        
        disputes = []
        for row in result:
            import json
            dispute_data = json.loads(row.dispute_data) if row.dispute_data else {}
            
            disputes.append({
                'id': row.id,
                'dispute_id': row.dispute_id,
                'order_id': row.order_id,
                'buyer_username': dispute_data.get('buyerUsername'),
                'open_date': row.open_date.isoformat() if row.open_date else None,
                'status': row.status,
                'amount': dispute_data.get('monetaryTransactions', [{}])[0].get('totalPrice', {}).get('value') if dispute_data.get('monetaryTransactions') else None,
                'currency': dispute_data.get('monetaryTransactions', [{}])[0].get('totalPrice', {}).get('currency') if dispute_data.get('monetaryTransactions') else None,
                'reason': row.reason,
                'respond_by_date': row.respond_by_date.isoformat() if row.respond_by_date else None,
            })
        
        return disputes
    finally:
        session.close()


@router.post("/sync/offers", status_code=status.HTTP_202_ACCEPTED)
async def sync_all_offers(
    background_tasks: BackgroundTasks,
    environment: str = Query(None, description="eBay environment: sandbox or production (default: user's current environment)"),
    current_user: User = Depends(get_current_active_user)
):
    from app.services.sync_event_logger import SyncEventLogger
    from app.utils.ebay_token_helper import get_user_ebay_token, is_user_ebay_connected
    
    env = environment or current_user.ebay_environment or "sandbox"
    
    if not is_user_ebay_connected(current_user, env):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"eBay account not connected ({env}). Please connect to eBay first."
        )
    
    access_token = get_user_ebay_token(current_user, env)
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"eBay access token not found for {env} environment"
        )
    
    event_logger = SyncEventLogger(current_user.id, 'offers')
    run_id = event_logger.run_id
    
    logger.info(f"Allocated run_id {run_id} for offers sync, user: {current_user.email}, environment: {env}")
    
    background_tasks.add_task(
        _run_offers_sync,
        current_user.id,
        access_token,
        env,
        run_id
    )
    
    return {
        "run_id": run_id,
        "status": "started",
        "message": f"Offers sync started in background ({env})"
    }


async def _run_offers_sync(user_id: str, access_token: str, ebay_environment: str, run_id: str):
    from app.config import settings
    
    original_env = settings.EBAY_ENVIRONMENT
    settings.EBAY_ENVIRONMENT = ebay_environment
    
    try:
        # Pass run_id to sync_all_offers so it uses the same run_id for events
        await ebay_service.sync_all_offers(user_id, access_token, run_id=run_id)
    except Exception as e:
        logger.error(f"Background offers sync failed for run_id {run_id}: {str(e)}")
    finally:
        settings.EBAY_ENVIRONMENT = original_env


@router.post("/sync/inventory", status_code=status.HTTP_202_ACCEPTED)
async def sync_all_inventory(
    background_tasks: BackgroundTasks,
    environment: str = Query(None, description="eBay environment: sandbox or production (default: user's current environment)"),
    current_user: User = Depends(get_current_active_user)
):
    """
    Start inventory sync from eBay to database.
    
    According to eBay API documentation:
    - GET /sell/inventory/v1/inventory_item?limit=200&offset=0
    - Fetches all inventory items with pagination
    - Stores items in inventory table
    
    Returns:
        Dict with run_id, status, message
    """
    from app.services.sync_event_logger import SyncEventLogger
    from app.utils.ebay_token_helper import get_user_ebay_token, is_user_ebay_connected
    
    env = environment or current_user.ebay_environment or "sandbox"
    
    if not is_user_ebay_connected(current_user, env):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"eBay account not connected ({env}). Please connect to eBay first."
        )
    
    access_token = get_user_ebay_token(current_user, env)
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"eBay access token not found for {env} environment"
        )
    
    event_logger = SyncEventLogger(current_user.id, 'inventory')
    run_id = event_logger.run_id
    
    logger.info(f"Allocated run_id {run_id} for inventory sync, user: {current_user.email}, environment: {env}")
    
    background_tasks.add_task(
        _run_inventory_sync,
        current_user.id,
        access_token,
        env,
        run_id
    )
    
    return {
        "run_id": run_id,
        "status": "started",
        "message": f"Inventory sync started in background ({env})"
    }


async def _run_inventory_sync(user_id: str, access_token: str, ebay_environment: str, run_id: str):
    from app.config import settings
    
    original_env = settings.EBAY_ENVIRONMENT
    settings.EBAY_ENVIRONMENT = ebay_environment
    
    try:
        # Pass run_id to sync_all_inventory so it uses the same run_id for events
        await ebay_service.sync_all_inventory(user_id, access_token, run_id=run_id)
    except Exception as e:
        logger.error(f"Background inventory sync failed for run_id {run_id}: {str(e)}")
    finally:
        settings.EBAY_ENVIRONMENT = original_env


@router.get("/export/all")
async def export_all_data(current_user: User = Depends(get_current_active_user)):
    from app.services.ebay_database import ebay_db
    from datetime import datetime
    
    orders = ebay_db.get_orders(current_user.id, limit=10000)
    
    export_data = {
        "export_date": datetime.utcnow().isoformat(),
        "user_email": current_user.email,
        "orders": orders,
        "total_orders": len(orders)
    }
    
    return export_data


@router.get("/orders/filter")
async def filter_orders(
    buyer_username: str = Query(None, description="Filter by buyer username"),
    order_status: str = Query(None, description="Filter by order status"),
    start_date: str = Query(None, description="Filter by creation date (start)"),
    end_date: str = Query(None, description="Filter by creation date (end)"),
    limit: int = Query(100, description="Number of orders to return"),
    offset: int = Query(0, description="Offset for pagination"),
    current_user: User = Depends(get_current_active_user)
):
    from app.services.ebay_database import ebay_db
    
    orders = ebay_db.get_filtered_orders(
        current_user.id, 
        buyer_username=buyer_username,
        order_status=order_status,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset
    )
    total = ebay_db.get_order_count(current_user.id)
    
    return {
        "orders": orders,
        "total": total,
        "filtered_count": len(orders),
        "limit": limit,
        "offset": offset
    }


@router.get("/analytics/summary")
async def get_analytics_summary(current_user: User = Depends(get_current_active_user)):
    from app.services.ebay_database import ebay_db
    
    analytics = ebay_db.get_analytics_summary(current_user.id)
    
    return analytics


@router.get("/sync/events/{run_id}")
async def stream_sync_events(
    run_id: str,
    current_user: User = Depends(get_user_from_header_or_query)
):
    """
    Stream sync events in real-time using Server-Sent Events (SSE).
    Continuously polls for new events and streams them until sync completes.
    
    NOTE: This endpoint supports token query parameter for EventSource compatibility.
    EventSource API cannot send custom headers, so we accept ?token=<jwt> as fallback.
    """
    from app.services.sync_event_logger import get_sync_events_from_db
    import json
    import asyncio
    
    async def event_generator():
        last_event_count = 0
        is_complete = False
        
        while not is_complete:
            events = get_sync_events_from_db(run_id, current_user.id)
            
            if len(events) > last_event_count:
                for event in events[last_event_count:]:
                    yield f"event: {event['event_type']}\n"
                    yield f"data: {json.dumps(event)}\n\n"
                    
                    if event['event_type'] in ['done', 'error', 'cancelled']:
                        is_complete = True
                
                last_event_count = len(events)
            
            if not is_complete:
                await asyncio.sleep(0.5)
        
        yield f"event: end\n"
        yield f"data: {json.dumps({'message': 'Stream complete'})}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.get("/sync/logs/{run_id}")
async def get_sync_logs(
    run_id: str,
    current_user: User = Depends(get_current_active_user)
):
    """
    Get all sync logs for a specific run_id.
    Used for viewing historical logs or downloading complete log files.
    """
    from app.services.sync_event_logger import get_sync_events_from_db
    
    events = get_sync_events_from_db(run_id, current_user.id)
    
    return {
        "run_id": run_id,
        "events": events,
        "total": len(events)
    }


@router.post("/sync/cancel/{run_id}")
async def cancel_sync_operation(
    run_id: str,
    current_user: User = Depends(get_current_active_user)
):
    """
    Cancel a running sync operation.
    Works even if sync hasn't started logging events yet.
    """
    from app.services.sync_event_logger import cancel_sync, get_sync_events_from_db
    
    # Try to get events, but don't fail if none exist yet (sync might not have started)
    events = get_sync_events_from_db(run_id, current_user.id)
    
    # If events exist, check if already complete
    # But allow cancellation even if complete (user might want to stop a new sync with same run_id pattern)
    if events:
        last_event = events[-1]
        if last_event and last_event.get('event_type') in ['done', 'error', 'cancelled']:
            # Operation is already complete, but we'll still mark it as cancelled for consistency
            logger.info(f"Sync operation {run_id} is already complete, but marking as cancelled per user request")
            # Don't raise error, just mark as cancelled
    
    # Cancel the sync (this will work even if no events exist yet)
    success = cancel_sync(run_id, current_user.id)
    if not success:
        # If cancellation failed, check if it's because operation is already complete
        if events:
            last_event = events[-1]
            if last_event and last_event.get('event_type') in ['done', 'error', 'cancelled']:
                return {
                    "message": "Sync operation was already complete",
                    "run_id": run_id,
                    "status": "already_complete"
                }
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to cancel sync operation"
        )
    
    return {
        "run_id": run_id,
        "status": "cancelled",
        "message": "Sync operation cancelled"
    }


@router.get("/sync/logs/{run_id}/export")
async def export_sync_logs(
    run_id: str,
    current_user: User = Depends(get_current_active_user)
):
    """
    Export sync logs as downloadable NDJSON file.
    """
    from app.services.sync_event_logger import get_sync_events_from_db
    import json
    
    events = get_sync_events_from_db(run_id, current_user.id)
    
    def generate_ndjson():
        for event in events:
            yield json.dumps(event) + "\n"
    
    return StreamingResponse(
        generate_ndjson(),
        media_type="application/x-ndjson",
        headers={
            "Content-Disposition": f"attachment; filename=sync_logs_{run_id}.ndjson"
        }
    )


@router.post("/debug")
async def debug_ebay_api(
    method: str = Query("GET", description="HTTP method"),
    path: str = Query(..., description="API path (e.g., /sell/fulfillment/v1/order)"),
    params: Optional[str] = Query(None, description="Query parameters (key1=value1&key2=value2)"),
    headers: Optional[str] = Query(None, description="Additional headers (Header1: Value1, Header2: Value2)"),
    body: Optional[str] = Query(None, description="Request body (JSON string)"),
    template: Optional[str] = Query(None, description="Use predefined template (identity, orders, transactions, etc.)"),
    environment: str = Query(None, description="eBay environment: sandbox or production (default: user's current environment)"),
    current_user: User = Depends(get_current_active_user)
):
    """Debug eBay API requests - make a test request and return full response."""
    from app.utils.ebay_debugger import EbayAPIDebugger
    from app.utils.ebay_token_helper import get_user_ebay_token, is_user_ebay_connected
    from urllib.parse import urlencode
    import time
    
    env = environment or current_user.ebay_environment or "sandbox"
    
    if not is_user_ebay_connected(current_user, env):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"User is not connected to eBay ({env})"
        )
    
    debugger = EbayAPIDebugger(current_user.id, raw_mode=False, save_history=False)
    
    # Set environment for debugger
    debugger.user.ebay_environment = env
    
    # Load user token
    if not debugger.load_user_token():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to load user token"
        )
    
    # Get user scopes from account
    user_scopes = []
    from app.services.ebay_account_service import ebay_account_service
    from app.models_sqlalchemy import get_db
    db_session = next(get_db())
    try:
        accounts = ebay_account_service.get_accounts_by_org(db_session, current_user.id)
        if accounts:
            from app.models_sqlalchemy.models import EbayAuthorization
            auths = db_session.query(EbayAuthorization).filter(
                EbayAuthorization.ebay_account_id == accounts[0].id
            ).all()
            user_scopes = [auth.scope for auth in auths] if auths else []
    except:
        pass
    finally:
        db_session.close()
    
    # Get token info
    from app.utils.token_utils import extract_token_info, mask_token, validate_scopes, format_scopes_for_display
    token_info = extract_token_info(debugger.access_token)
    masked_token = mask_token(debugger.access_token)
    
    # Determine API name from path
    api_name = "custom"
    if "identity" in path:
        api_name = "identity"
    elif "fulfillment" in path or "order" in path:
        api_name = "orders"
    elif "finances" in path or "transaction" in path:
        api_name = "transactions"
    elif "inventory" in path:
        api_name = "inventory"
    
    scope_validation = validate_scopes(user_scopes, api_name) if api_name != "custom" else None
    
    # Get template if specified
    if template:
        template_data = debugger.get_template(template)
        if not template_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown template: {template}"
            )
        method = method or template_data["method"]
        path = path or template_data["path"]
        params_dict = debugger.parse_params(params) if params else template_data["params"]
        headers_dict = debugger.parse_headers(headers) if headers else template_data["headers"]
        body_str = body or template_data["body"]
    else:
        params_dict = debugger.parse_params(params) if params else {}
        headers_dict = debugger.parse_headers(headers) if headers else {}
        body_str = body
    
    # Build URL
    base_url = debugger.base_url
    if path.startswith('/'):
        url = f"{base_url}{path}"
    elif path.startswith('http'):
        url = path
    else:
        url = f"{base_url}/{path}"
    
    # Add query parameters
    if params_dict:
        query_string = urlencode(params_dict)
        url = f"{url}?{query_string}" if query_string else url
    
    # Prepare headers
    request_headers = {
        "Authorization": f"Bearer {debugger.access_token}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    if headers_dict:
        request_headers.update(headers_dict)
    
    # Make request
    start_time = time.time()
    try:
        import httpx
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
            if method.upper() == "GET":
                response = await client.get(url, headers=request_headers)
            elif method.upper() == "POST":
                response = await client.post(url, headers=request_headers, content=body_str or "")
            elif method.upper() == "PUT":
                response = await client.put(url, headers=request_headers, content=body_str or "")
            elif method.upper() == "DELETE":
                response = await client.delete(url, headers=request_headers)
            elif method.upper() == "PATCH":
                response = await client.patch(url, headers=request_headers, content=body_str or "")
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Unsupported HTTP method: {method}"
                )
            
            response_time_ms = (time.time() - start_time) * 1000
            
            # Parse response body
            try:
                response_body = response.json()
            except:
                response_body = response.text
            
            # Get eBay headers
            ebay_headers = {k: v for k, v in response.headers.items() 
                           if k.lower().startswith('x-ebay')}
            
            # Show more of the token (first 30 and last 30 chars for visibility)
            def show_more_token(token: str) -> str:
                if len(token) <= 60:
                    return token
                return token[:30] + "..." + token[-30:]
            
            return {
                "request_context": {
                    "user_email": current_user.email,
                    "user_id": current_user.id[:8] + "..." if len(current_user.id) > 8 else current_user.id,
                    "token": show_more_token(debugger.access_token),  # Show more of token
                    "token_masked": masked_token,  # Fully masked version
                    "token_full": debugger.access_token,  # Full token (for display only, not in response by default)
                    "token_version": token_info.get("version"),
                    "token_expires_at": current_user.ebay_token_expires_at.isoformat() if current_user.ebay_token_expires_at else None,
                    "scopes": user_scopes,
                    "scopes_display": format_scopes_for_display(user_scopes),
                    "scopes_full": user_scopes,  # Full list of scopes
                    "environment": current_user.ebay_environment or "sandbox",
                    "missing_scopes": scope_validation["missing_scopes"] if scope_validation else [],
                    "has_all_required": scope_validation["has_all_required"] if scope_validation else None
                },
                "request": {
                    "method": method,
                    "url": url,
                    "url_full": url,  # Full URL in one line for copying
                    "headers": {k: (masked_token if k.lower() == "authorization" and "Bearer" in v else v) 
                               for k, v in request_headers.items()},
                    "headers_full": request_headers,  # Full headers with actual token (masked in display)
                    "params": params_dict,
                    "body": body_str,
                    "curl_command": f"curl -X {method} '{url}' " + 
                                   " ".join([f"-H '{k}: {v}'" for k, v in request_headers.items()]) +
                                   (f" -d '{body_str}'" if body_str else "")
                },
                "response": {
                    "status_code": response.status_code,
                    "status_text": response.reason_phrase,
                    "headers": dict(response.headers),
                    "ebay_headers": ebay_headers,
                    "body": response_body,
                    "response_time_ms": round(response_time_ms, 2)
                },
                "success": 200 <= response.status_code < 300
            }
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"HTTP error: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Error in debug endpoint: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error making request: {str(e)}"
        )


@router.get("/debug/templates")
async def get_debug_templates(
    current_user: User = Depends(get_current_active_user)
):
    """Get list of available debug templates."""
    from app.utils.ebay_debugger import EbayAPIDebugger
    
    debugger = EbayAPIDebugger(current_user.id)
    templates = {}
    
    for template_name in ["identity", "orders", "transactions", "inventory", "offers", "disputes", "messages"]:
        template = debugger.get_template(template_name)
        if template:
            templates[template_name] = {
                "name": template["name"],
                "description": template["description"],
                "method": template["method"],
                "path": template["path"],
                "params": template["params"]
            }
    
    return {"templates": templates}
