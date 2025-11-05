from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
from app.database import get_db
from app.db_models import Message
from app.services.auth import get_current_user
from app.models.user import User as UserModel
from app.services.ebay import ebay_service
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/messages", tags=["messages"])

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

@router.post("/sync", status_code=202)
async def sync_messages(
    background_tasks: BackgroundTasks,
    dry_run: bool = Query(False, alias="dryRun"),
    current_user: UserModel = Depends(get_current_user)
):
    """
    Start messages sync in background and return run_id immediately.
    Client can use run_id to stream live progress via SSE endpoint.
    """
    if not current_user.ebay_connected or not current_user.ebay_access_token:
        raise HTTPException(status_code=400, detail="eBay account not connected")
    
    from app.services.sync_event_logger import SyncEventLogger
    
    event_logger = SyncEventLogger(current_user.id, 'messages')
    run_id = event_logger.run_id
    
    logger.info(f"Allocated run_id {run_id} for messages sync, user: {current_user.email}")
    
    background_tasks.add_task(
        _run_messages_sync,
        current_user.id,
        current_user.ebay_access_token,
        dry_run,
        run_id
    )
    
    return {
        "run_id": run_id,
        "status": "started",
        "message": "Messages sync started in background"
    }


async def _run_messages_sync(user_id: str, access_token: str, dry_run: bool, run_id: str):
    """Background task to run messages sync with error handling"""
    from app.services.sync_event_logger import SyncEventLogger
    from app.database import get_db
    import time
    
    event_logger = SyncEventLogger(user_id, 'messages')
    event_logger.run_id = run_id
    start_time = time.time()
    
    db = next(get_db())
    
    try:
        event_logger.log_start("Starting Messages sync from eBay")
        logger.info(f"Enumerating message folders for user {user_id}")
        
        request_start = time.time()
        folders_response = await ebay_service.get_message_folders(access_token)
        request_duration = int((time.time() - request_start) * 1000)
        folders = folders_response.get("folders", [])
        
        event_logger.log_http_request(
            'POST',
            '/ws/eBayISAPI.dll (GetMyMessages - ReturnSummary)',
            200,
            request_duration,
            len(folders)
        )
        
        if not folders:
            logger.warning(f"No message folders found for user {user_id}")
            event_logger.log_warning("No message folders found")
            duration_ms = int((time.time() - start_time) * 1000)
            event_logger.log_done("Messages sync completed: no folders found", 0, 0, duration_ms)
            event_logger.close()
            return
        
        total_messages = sum(f["total_count"] for f in folders)
        event_logger.log_info(f"Found {len(folders)} folders with {total_messages} total messages: {[f['folder_name'] for f in folders]}")
        logger.info(f"Found {len(folders)} folders: {[f['folder_name'] for f in folders]}")
        
        if dry_run:
            folder_counts = {f["folder_name"]: f["total_count"] for f in folders}
            total_count = sum(f["total_count"] for f in folders)
            event_logger.log_done(f"Dry run completed: {total_count} messages found", 0, 0, 0)
            event_logger.close()
            return
        
        total_fetched = 0
        total_stored = 0
        folder_stats = {}
        folder_index = 0
        
        for folder in folders:
            folder_index += 1
            folder_id = folder["folder_id"]
            folder_name = folder["folder_name"]
            folder_total = folder["total_count"]
            
            event_logger.log_progress(
                f"Processing folder {folder_index}/{len(folders)}: {folder_name} ({folder_total} messages)",
                folder_index,
                len(folders),
                total_fetched,
                total_stored
            )
            logger.info(f"Processing folder {folder_name} (ID: {folder_id}) with {folder_total} messages")
            
            if folder_total == 0:
                folder_stats[folder_name] = {"fetched": 0, "stored": 0}
                continue
            
            all_message_ids = []
            page_number = 1
            
            while True:
                logger.info(f"Fetching headers page {page_number} for folder {folder_name}")
                
                request_start = time.time()
                headers_response = await ebay_service.get_message_headers(
                    access_token,
                    folder_id,
                    page_number=page_number,
                    entries_per_page=200
                )
                request_duration = int((time.time() - request_start) * 1000)
                
                message_ids = headers_response.get("message_ids", [])
                alert_ids = headers_response.get("alert_ids", [])
                total_pages = headers_response.get("total_pages", 1)
                
                all_message_ids.extend(message_ids)
                all_message_ids.extend(alert_ids)
                
                event_logger.log_http_request(
                    'POST',
                    f'/ws/eBayISAPI.dll (GetMyMessages - {folder_name} page {page_number})',
                    200,
                    request_duration,
                    len(message_ids) + len(alert_ids)
                )
                
                logger.info(f"Page {page_number}/{total_pages}: Found {len(message_ids)} messages, {len(alert_ids)} alerts")
                
                if page_number >= total_pages:
                    break
                
                page_number += 1
            
            event_logger.log_info(f"Folder {folder_name}: Collected {len(all_message_ids)} message IDs, fetching bodies...")
            logger.info(f"Folder {folder_name}: Collected {len(all_message_ids)} total message IDs")
            
            folder_fetched = 0
            folder_stored = 0
            total_batches = (len(all_message_ids) + 9) // 10
            
            for i in range(0, len(all_message_ids), 10):
                batch_ids = all_message_ids[i:i+10]
                batch_num = i//10 + 1
                logger.info(f"Fetching bodies for batch {batch_num} ({len(batch_ids)} messages)")
                
                try:
                    request_start = time.time()
                    messages = await ebay_service.get_message_bodies(
                        access_token,
                        batch_ids
                    )
                    request_duration = int((time.time() - request_start) * 1000)
                    
                    event_logger.log_http_request(
                        'POST',
                        f'/ws/eBayISAPI.dll (GetMyMessages - {folder_name} batch {batch_num}/{total_batches})',
                        200,
                        request_duration,
                        len(messages)
                    )
                    
                    folder_fetched += len(messages)
                    
                    for msg in messages:
                        message_id = msg.get("messageid") or msg.get("externalmessageid")
                        
                        if not message_id:
                            logger.warning(f"Message missing ID, skipping: {msg}")
                            continue
                        
                        existing = db.query(Message).filter(
                            Message.message_id == message_id,
                            Message.user_id == user_id
                        ).first()
                        
                        if existing:
                            logger.debug(f"Message {message_id} already exists, skipping")
                            continue
                        
                        sender = msg.get("sender", "")
                        recipient = msg.get("recipientuserid", "")
                        direction = "INCOMING"
                        
                        receive_date_str = msg.get("receivedate", "")
                        message_date = datetime.utcnow()
                        if receive_date_str:
                            try:
                                message_date = datetime.fromisoformat(receive_date_str.replace("Z", "+00:00"))
                            except Exception as e:
                                logger.warning(f"Failed to parse date {receive_date_str}: {e}")
                        
                        message = Message(
                            user_id=user_id,
                            message_id=message_id,
                            thread_id=msg.get("externalmessageid") or message_id,
                            sender_username=sender,
                            recipient_username=recipient,
                            subject=msg.get("subject", ""),
                            body=msg.get("text", ""),
                            message_type="MEMBER_MESSAGE",
                            is_read=msg.get("read", False),
                            is_flagged=msg.get("flagged", False),
                            is_archived=msg.get("folderid") == "2",
                            direction=direction,
                            message_date=message_date,
                            order_id=None,
                            listing_id=msg.get("itemid"),
                            raw_data=str(msg)
                        )
                        db.add(message)
                        folder_stored += 1
                    
                    db.commit()
                    
                except Exception as e:
                    logger.error(f"Failed to fetch/store batch {i//10 + 1}: {str(e)}")
                    db.rollback()
                    continue
            
            folder_stats[folder_name] = {
                "fetched": folder_fetched,
                "stored": folder_stored
            }
            total_fetched += folder_fetched
            total_stored += folder_stored
            
            event_logger.log_info(f"Folder {folder_name} complete: {folder_fetched} fetched, {folder_stored} stored")
            logger.info(f"Folder {folder_name} complete: {folder_fetched} fetched, {folder_stored} stored")
        
        duration_ms = int((time.time() - start_time) * 1000)
        event_logger.log_done(
            f"Messages sync completed: {total_fetched} fetched, {total_stored} stored across {len(folders)} folders",
            total_fetched,
            total_stored,
            duration_ms
        )
    
    except Exception as e:
        error_msg = str(e)
        event_logger.log_error(f"Messages sync failed: {error_msg}", e)
        logger.error(f"Background messages sync failed for run_id {run_id}: {error_msg}")
        db.rollback()
    finally:
        event_logger.close()
        db.close()
