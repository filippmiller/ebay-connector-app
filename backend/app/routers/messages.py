print("🟡 [startup] messages router import STARTED")

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

print("🟡 [startup] basic imports done")

from app.database import get_db
from app.db_models import Message
from app.services.auth import get_current_user
from app.models.user import User as UserModel

print("🟡 [startup] app imports done")

from app.services.ebay import ebay_service
from pydantic import BaseModel
import logging

print("🟡 [startup] ebay service and logging imports done")

logger = logging.getLogger(__name__)
logger.info("🟡 messages router module importing dependencies")

router = APIRouter(prefix="/messages", tags=["messages"])

print("🟡 [startup] router created")

@router.get("/ping")
async def ping():
    """Simple ping endpoint to verify router is working"""
    return {"ok": True, "message": "messages router alive"}

print("🟡 [startup] ping route registered")

@router.get("/_t0")
async def t0():
    """Control test - no deps, no model"""
    return {"ok": True, "stage": "no_deps_no_model_get"}

class TResp(BaseModel):
    ok: bool
    stage: str

@router.get("/_t1", response_model=TResp)
async def t1():
    """Test with response_model"""
    return {"ok": True, "stage": "response_model_get"}

@router.post("/_t2")
async def t2():
    """Test POST with empty body"""
    return {"ok": True, "stage": "no_deps_post_empty_body"}

@router.get("/_t3")
async def t3(user: UserModel = Depends(get_current_user)):
    """Test with auth dependency"""
    return {"ok": True, "user_id": str(user.id), "stage": "with_auth_dep"}

class MessageResponse(BaseModel):
    id: str
    message_id: str
    thread_id: Optional[str]
    sender_username: Optional[str]
    recipient_username: Optional[str]
    subject: Optional[str]
    body: str
    message_type: Optional[str]
    is_read: bool
    is_flagged: bool
    is_archived: bool
    direction: str
    message_date: datetime
    order_id: Optional[str]
    listing_id: Optional[str]

    class Config:
        from_attributes = True

class MessageUpdate(BaseModel):
    is_read: Optional[bool] = None
    is_flagged: Optional[bool] = None
    is_archived: Optional[bool] = None

@router.get("/", response_model=List[MessageResponse])
async def get_messages(
    folder: str = Query("inbox", regex="^(inbox|sent|flagged|archived)$"),
    unread_only: bool = False,
    search: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = db.query(Message).filter(Message.user_id == current_user.id)
    
    if folder == "inbox":
        query = query.filter(Message.direction == "INCOMING", Message.is_archived == False)
    elif folder == "sent":
        query = query.filter(Message.direction == "OUTGOING")
    elif folder == "flagged":
        query = query.filter(Message.is_flagged == True)
    elif folder == "archived":
        query = query.filter(Message.is_archived == True)
    
    if unread_only:
        query = query.filter(Message.is_read == False)
    
    if search:
        query = query.filter(
            (Message.subject.contains(search)) |
            (Message.body.contains(search)) |
            (Message.sender_username.contains(search))
        )
    
    messages = query.order_by(Message.message_date.desc()).offset(skip).limit(limit).all()
    return messages

@router.get("/stats/summary")
async def get_message_stats(
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    from sqlalchemy import func
    
    unread_count = db.query(func.count(Message.id)).filter(
        Message.user_id == current_user.id,
        Message.is_read == False,
        Message.direction == "INCOMING"
    ).scalar()
    
    flagged_count = db.query(func.count(Message.id)).filter(
        Message.user_id == current_user.id,
        Message.is_flagged == True
    ).scalar()
    
    return {
        "unread_count": unread_count,
        "flagged_count": flagged_count
    }

@router.get("/diagnostics-simple")
async def get_messages_diagnostics_simple():
    """Simple diagnostics endpoint without dependencies"""
    return {"ok": True, "message": "diagnostics endpoint alive", "test": "no dependencies"}

@router.get("/diagnostics-auth-only")
async def get_messages_diagnostics_auth_only(
    current_user: UserModel = Depends(get_current_user)
):
    """Test diagnostics with only auth dependency"""
    return {
        "ok": True,
        "message": "auth dependency works",
        "user_id": str(current_user.id),
        "ebay_connected": current_user.ebay_connected
    }

@router.get("/diagnostics")
async def get_messages_diagnostics(
    mode: str = Query("summary", regex="^(summary|folders)$"),
    verbose: int = Query(0, ge=0, le=1),
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get diagnostics for messages sync (no DB writes)"""
    logger.info(f"Diagnostics endpoint called: mode={mode}, verbose={verbose}, user_id={current_user.id}")
    
    if not current_user.ebay_connected:
        logger.warning(f"User {current_user.id} not connected to eBay")
        return {
            "ok": False,
            "where": "diagnostics:auth",
            "status": 401,
            "hint": "eBay account not connected - reconnect required"
        }
    
    logger.info(f"User {current_user.id} is connected to eBay, ensuring valid token...")
    
    try:
        if mode == "folders":
            logger.info(f"Fetching message folders for user {current_user.id}")
            folders_response = await ebay_service.call_ebay_api_with_retry(
                current_user.id,
                ebay_service.fetch_message_folders,
                verbose=verbose
            )
            logger.info(f"Folders response received: {len(folders_response.get('folders', []))} folders")
            
            result = {
                "ok": True,
                "account_id": str(current_user.id),
                "ebay_username": getattr(current_user, 'ebay_username', None),
                "ebay_user_id": getattr(current_user, 'ebay_user_id', None),
                "mode": "folders",
                "folders": folders_response.get('folders', []),
                "summary": folders_response.get('summary', {})
            }
            
            if verbose and 'debug' in folders_response:
                result['debug'] = folders_response['debug']
            
            return result
        else:
            messages_response = await ebay_service.call_ebay_api_with_retry(
                current_user.id,
                ebay_service.fetch_messages,
                {'page_number': 1, 'entries_per_page': 1}
            )
            
            result = {
                "ok": True,
                "account_id": str(current_user.id),
                "ebay_username": getattr(current_user, 'ebay_username', None),
                "ebay_user_id": getattr(current_user, 'ebay_user_id', None),
                "mode": "summary",
                "call_options": {
                    "time_window": "2015-01-01 to now",
                    "folder_filter": "all folders",
                    "pagination": "200 per page"
                },
                "summary": messages_response.get('summary', {}),
                "total_entries": messages_response.get('total_entries', 0),
                "total_pages": messages_response.get('total_pages', 0)
            }
            
            raw_snippet = messages_response.get('raw_response_snippet')
            if raw_snippet:
                result["raw_response_snippet"] = raw_snippet
            
            return result
    except HTTPException as http_exc:
        return {
            "ok": False,
            "where": f"diagnostics:{mode}",
            "status": http_exc.status_code,
            "hint": str(http_exc.detail)[:200]
        }
    except Exception as e:
        import traceback
        logger.error(f"Diagnostics error: {str(e)}\n{traceback.format_exc()}")
        return {
            "ok": False,
            "where": f"diagnostics:{mode}",
            "status": 500,
            "hint": str(e)[:200]
        }

@router.post("/sync")
async def sync_messages(
    dry_run: bool = Query(False, alias="dryRun"),
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Sync messages from eBay"""
    if not current_user.ebay_connected or not current_user.ebay_access_token:
        raise HTTPException(status_code=400, detail="eBay account not connected")
    
    if dry_run:
        try:
            folder_counts = {}
            total_count = 0
            
            for folder_id in [0, 1, 2]:
                try:
                    messages_response = await ebay_service.call_ebay_api_with_retry(
                        current_user.id,
                        ebay_service.fetch_messages,
                        {'folder_id': folder_id, 'page_number': 1, 'entries_per_page': 1}
                    )
                    folder_name = {0: 'inbox', 1: 'sent', 2: 'archived'}.get(folder_id, f'folder_{folder_id}')
                    count = messages_response.get('total_entries', 0)
                    folder_counts[folder_name] = count
                    total_count += count
                except:
                    pass
            
            return {
                "dry_run": True,
                "folders": folder_counts,
                "total": total_count
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    try:
        total_fetched = 0
        total_stored = 0
        page_number = 1
        
        while True:
            messages_response = await ebay_service.call_ebay_api_with_retry(
                current_user.id,
                ebay_service.fetch_messages,
                {
                    'page_number': page_number,
                    'entries_per_page': 200,
                    'start_time': '2015-01-01T00:00:00.000Z'
                }
            )
            
            messages = messages_response.get('messages', [])
            total_pages = messages_response.get('total_pages', 1)
            
            if not messages:
                break
            
            for msg in messages:
                message_id = msg.get('externalMessageId') or msg.get('messageId')
                
                if not message_id:
                    continue
                
                existing = db.query(Message).filter(
                    Message.message_id == message_id,
                    Message.user_id == current_user.id
                ).first()
                
                if not existing:
                    sender = msg.get('sender', '')
                    recipient = msg.get('recipientUserID', '')
                    
                    direction = 'INCOMING'
                    ebay_username = getattr(current_user, 'ebay_username', None)
                    if sender and ebay_username and sender.lower() == ebay_username.lower():
                        direction = 'OUTGOING'
                    
                    receive_date_str = msg.get('receiveDate', '')
                    message_date = datetime.utcnow()
                    if receive_date_str:
                        try:
                            message_date = datetime.fromisoformat(receive_date_str.replace('Z', '+00:00'))
                        except:
                            pass
                    
                    message = Message(
                        user_id=current_user.id,
                        message_id=message_id,
                        thread_id=msg.get('externalMessageId') or message_id,
                        sender_username=sender,
                        recipient_username=recipient,
                        subject=msg.get('subject', ''),
                        body=msg.get('body', ''),
                        message_type=msg.get('messageType', 'MEMBER_MESSAGE'),
                        is_read=msg.get('read', False),
                        is_flagged=msg.get('flagged', False),
                        is_archived=msg.get('folderId') == '2',
                        direction=direction,
                        message_date=message_date,
                        order_id=None,
                        listing_id=msg.get('itemID'),
                        raw_data=str(msg)
                    )
                    db.add(message)
                    total_stored += 1
            
            total_fetched += len(messages)
            
            if page_number >= total_pages:
                break
            
            page_number += 1
        
        db.commit()
        
        return {
            "status": "completed",
            "total_fetched": total_fetched,
            "total_stored": total_stored,
            "pages_processed": page_number
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{message_id}", response_model=MessageResponse)
async def get_message(
    message_id: str,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    message = db.query(Message).filter(
        Message.id == message_id,
        Message.user_id == current_user.id
    ).first()
    
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    
    return message

@router.patch("/{message_id}")
async def update_message(
    message_id: str,
    update: MessageUpdate,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    message = db.query(Message).filter(
        Message.id == message_id,
        Message.user_id == current_user.id
    ).first()
    
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    
    if update.is_read is not None:
        message.is_read = update.is_read
        if update.is_read:
            message.read_date = datetime.utcnow()
    
    if update.is_flagged is not None:
        message.is_flagged = update.is_flagged
    
    if update.is_archived is not None:
        message.is_archived = update.is_archived
    
    db.commit()
    db.refresh(message)
    
    return {"message": "Message updated successfully"}

@router.post("/sync-old-implementation-backup")
async def sync_messages(
    dry_run: bool = Query(False, alias="dryRun"),
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Sync messages from eBay"""
    if not current_user.ebay_connected or not current_user.ebay_access_token:
        raise HTTPException(status_code=400, detail="eBay account not connected")
    
    if dry_run:
        try:
            folder_counts = {}
            total_count = 0
            
            for folder_id in [0, 1, 2]:
                try:
                    messages_response = await ebay_service.call_ebay_api_with_retry(
                        current_user.id,
                        ebay_service.fetch_messages,
                        {'folder_id': folder_id, 'page_number': 1, 'entries_per_page': 1}
                    )
                    folder_name = {0: 'inbox', 1: 'sent', 2: 'archived'}.get(folder_id, f'folder_{folder_id}')
                    count = messages_response.get('total_entries', 0)
                    folder_counts[folder_name] = count
                    total_count += count
                except:
                    pass
            
            return {
                "dry_run": True,
                "folders": folder_counts,
                "total": total_count
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    try:
        total_fetched = 0
        total_stored = 0
        page_number = 1
        
        while True:
            messages_response = await ebay_service.call_ebay_api_with_retry(
                current_user.id,
                ebay_service.fetch_messages,
                {
                    'page_number': page_number,
                    'entries_per_page': 200,
                    'start_time': '2015-01-01T00:00:00.000Z'
                }
            )
            
            messages = messages_response.get('messages', [])
            total_pages = messages_response.get('total_pages', 1)
            
            if not messages:
                break
            
            for msg in messages:
                message_id = msg.get('externalMessageId') or msg.get('messageId')
                
                if not message_id:
                    continue
                
                existing = db.query(Message).filter(
                    Message.message_id == message_id,
                    Message.user_id == current_user.id
                ).first()
                
                if not existing:
                    sender = msg.get('sender', '')
                    recipient = msg.get('recipientUserID', '')
                    
                    direction = 'INCOMING'
                    ebay_username = getattr(current_user, 'ebay_username', None)
                    if sender and ebay_username and sender.lower() == ebay_username.lower():
                        direction = 'OUTGOING'
                    
                    receive_date_str = msg.get('receiveDate', '')
                    message_date = datetime.utcnow()
                    if receive_date_str:
                        try:
                            message_date = datetime.fromisoformat(receive_date_str.replace('Z', '+00:00'))
                        except:
                            pass
                    
                    message = Message(
                        user_id=current_user.id,
                        message_id=message_id,
                        thread_id=msg.get('externalMessageId') or message_id,
                        sender_username=sender,
                        recipient_username=recipient,
                        subject=msg.get('subject', ''),
                        body=msg.get('body', ''),
                        message_type=msg.get('messageType', 'MEMBER_MESSAGE'),
                        is_read=msg.get('read', False),
                        is_flagged=msg.get('flagged', False),
                        is_archived=msg.get('folderId') == '2',
                        direction=direction,
                        message_date=message_date,
                        order_id=None,
                        listing_id=msg.get('itemID'),
                        raw_data=str(msg)
                    )
                    db.add(message)
                    total_stored += 1
            
            total_fetched += len(messages)
            
            if page_number >= total_pages:
                break
            
            page_number += 1
        
        db.commit()
        
        return {
            "status": "completed",
            "total_fetched": total_fetched,
            "total_stored": total_stored,
            "pages_processed": page_number
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

print("🟢 [startup] messages router import COMPLETED")
