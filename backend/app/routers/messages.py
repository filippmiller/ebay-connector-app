from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from typing import List, Optional, Dict, Any
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
    # NOTE: Stored values in ebay_messages.message_date may be DATE or TEXT in
    # some environments. The frontend treats this as a string and parses it via
    # new Date(message_date), so we expose it as str here to avoid strict
    # datetime parsing errors from Pydantic when legacy rows are loaded.
    message_date: str
    order_id: Optional[str]
    listing_id: Optional[str]
    bucket: Optional[str] = None
    parsed_body: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


class MessagesListResponse(BaseModel):
    items: List[MessageResponse]
    total: int
    counts: Dict[str, int]

class MessageUpdate(BaseModel):
    is_read: Optional[bool] = None
    is_flagged: Optional[bool] = None
    is_archived: Optional[bool] = None

def _classify_bucket(msg: Message) -> str:
    """Classify a message into one of the Gmail-like buckets.

    OFFERS, CASES & DISPUTES, EBAY MESSAGES, OTHER.
    """
    mt = (msg.message_type or "").upper()
    subj = (msg.subject or "").lower()
    raw = (msg.raw_data or "").lower() if hasattr(msg, "raw_data") else ""
    sender = (msg.sender_username or "").lower()

    # OFFERS
    if mt in {"OFFER", "BEST_OFFER", "COUNTER_OFFER"} or "offer" in subj or "offer" in raw:
        return "offers"

    # CASES & DISPUTES
    if mt in {"CASE", "INQUIRY", "RETURN", "CANCELLATION", "CANCEL_REQUEST", "UNPAID_ITEM"}:
        return "cases"
    if any(k in subj for k in ["case", "dispute"]) or (
        ("opened" in subj or "closed" in subj) and "ebay" in sender
    ):
        return "cases"

    # EBAY MESSAGES
    if "ebay" in sender or mt == "EBAY_MESSAGE":
        return "ebay"

    return "other"


@router.get("/", response_model=MessagesListResponse)
async def get_messages(
    folder: str = Query("inbox", regex="^(inbox|sent|flagged|archived)$"),
    unread_only: bool = False,
    search: Optional[str] = None,
    bucket: Optional[str] = Query("all", regex="^(all|offers|cases|ebay)$"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    base_query = db.query(Message).filter(Message.user_id == current_user.id)

    # Folder filter
    # Inbox: show all incoming messages regardless of archived flag so that
    # badge counts and list contents line up. "Archived" can still be used to
    # focus on archived messages only.
    if folder == "inbox":
        base_query = base_query.filter(Message.direction == "INCOMING")
    elif folder == "sent":
        base_query = base_query.filter(Message.direction == "OUTGOING")
    elif folder == "flagged":
        base_query = base_query.filter(Message.is_flagged == True)
    elif folder == "archived":
        base_query = base_query.filter(Message.is_archived == True)

    # Unread filter
    if unread_only:
        base_query = base_query.filter(Message.is_read == False)

    # Search filter
    if search:
        like = f"%{search}%"
        base_query = base_query.filter(
            or_(
                Message.subject.ilike(like),
                Message.body.ilike(like),
                Message.sender_username.ilike(like),
            )
        )

    # For now, compute bucket classification in Python for current page and counts.
    # Fetch a superset (without bucket restriction) for counts, then page.
    all_msgs = base_query.order_by(Message.message_date.desc()).all()

    counts = {"all": 0, "offers": 0, "cases": 0, "ebay": 0}
    classified: List[Message] = []
    for m in all_msgs:
        b = _classify_bucket(m)
        counts["all"] += 1
        if b in counts:
            counts[b] += 1
        classified.append(m)

    # Apply bucket filter in-memory
    if bucket and bucket != "all":
        classified = [m for m in classified if _classify_bucket(m) == bucket]

    total = len(classified)
    page_items = classified[skip : skip + limit]

    # Attach bucket to each response object
    items: List[MessageResponse] = []
    for m in page_items:
        b = _classify_bucket(m)
        items.append(
            MessageResponse(
                id=m.id,
                message_id=m.message_id,
                thread_id=m.thread_id,
                sender_username=m.sender_username,
                recipient_username=m.recipient_username,
                subject=m.subject,
                body=m.body or "",
                message_type=m.message_type,
                is_read=m.is_read,
                is_flagged=m.is_flagged,
                is_archived=m.is_archived,
                direction=m.direction,
                message_date=m.message_date,
                order_id=m.order_id,
                listing_id=m.listing_id,
                bucket=b,
                parsed_body=getattr(m, "parsed_body", None),
            )
        )

    return MessagesListResponse(items=items, total=total, counts=counts)

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
        "flagged_count": flagged_count,
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
        from app.config import settings
        import asyncio
        from app.services.message_parser import parse_ebay_message_html
        
        event_logger.log_start(f"Starting Messages sync from eBay ({settings.EBAY_ENVIRONMENT})")
        event_logger.log_info(f"API Configuration: Trading API (XML), message headers limit=200, bodies batch=10")
        logger.info(f"Enumerating message folders for user {user_id}")
        
        await asyncio.sleep(0.5)
        
        event_logger.log_info(f"→ Requesting: POST /ws/eBayISAPI.dll (GetMyMessages - ReturnSummary)")
        
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
        
        event_logger.log_info(f"← Response: 200 OK ({request_duration}ms) - Received {len(folders)} folders")
        
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
        
        await asyncio.sleep(0.3)
        
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
            # Check for cancellation
            from app.services.sync_event_logger import is_cancelled
            if is_cancelled(run_id):
                logger.info(f"Messages sync cancelled for run_id {run_id}")
                event_logger.log_warning("Sync operation cancelled by user")
                duration_ms = int((time.time() - start_time) * 1000)
                event_logger.log_done(
                    f"Messages sync cancelled: {total_fetched} fetched, {total_stored} stored",
                    total_fetched,
                    total_stored,
                    duration_ms
                )
                event_logger.close()
                return
            
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
            max_pages = 1000  # Safety limit to prevent infinite loops
            consecutive_empty_pages = 0
            max_empty_pages = 3  # Stop if we get 3 consecutive empty pages
            
            while page_number <= max_pages:
                # Check for cancellation BEFORE each request
                from app.services.sync_event_logger import is_cancelled
                if is_cancelled(run_id):
                    logger.info(f"Messages sync cancelled for run_id {run_id}")
                    event_logger.log_warning("Sync operation cancelled by user")
                    duration_ms = int((time.time() - start_time) * 1000)
                    event_logger.log_done(
                        f"Messages sync cancelled: {total_fetched} fetched, {total_stored} stored",
                        total_fetched,
                        total_stored,
                        duration_ms
                    )
                    event_logger.close()
                    return
                
                event_logger.log_info(f"→ Requesting headers page {page_number}: POST /ws/eBayISAPI.dll (GetMyMessages - {folder_name})")
                logger.info(f"Fetching headers page {page_number} for folder {folder_name}")
                
                try:
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
                    
                    # Safety check: if total_pages is 0 or None, set it to 1
                    if not total_pages or total_pages < 1:
                        total_pages = 1
                        logger.warning(f"Invalid total_pages value, setting to 1 for folder {folder_name}")
                    
                    all_message_ids.extend(message_ids)
                    all_message_ids.extend(alert_ids)
                    
                    event_logger.log_http_request(
                        'POST',
                        f'/ws/eBayISAPI.dll (GetMyMessages - {folder_name} page {page_number})',
                        200,
                        request_duration,
                        len(message_ids) + len(alert_ids)
                    )
                    
                    event_logger.log_info(f"← Response: 200 OK ({request_duration}ms) - Page {page_number}/{total_pages}: {len(message_ids)} messages, {len(alert_ids)} alerts")
                    logger.info(f"Page {page_number}/{total_pages}: Found {len(message_ids)} messages, {len(alert_ids)} alerts")
                    
                    # Check if we got an empty page
                    if len(message_ids) == 0 and len(alert_ids) == 0:
                        consecutive_empty_pages += 1
                        if consecutive_empty_pages >= max_empty_pages:
                            logger.warning(f"Got {consecutive_empty_pages} consecutive empty pages, stopping pagination for folder {folder_name}")
                            event_logger.log_warning(f"Stopping pagination after {consecutive_empty_pages} consecutive empty pages")
                            break
                    else:
                        consecutive_empty_pages = 0  # Reset counter if we got results
                    
                    # Break if we've reached the last page
                    if page_number >= total_pages:
                        break
                    
                    page_number += 1
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    error_msg = f"Error fetching headers page {page_number} for folder {folder_name}: {str(e)}"
                    logger.error(error_msg)
                    event_logger.log_error(error_msg, e)
                    # Don't break on error - continue to next page, but log the error
                    page_number += 1
                    await asyncio.sleep(0.5)
                    continue
            
            if page_number > max_pages:
                logger.warning(f"Reached max_pages limit ({max_pages}) for folder {folder_name}, stopping pagination")
                event_logger.log_warning(f"Reached safety limit of {max_pages} pages, stopping pagination")
            
            event_logger.log_info(f"Folder {folder_name}: Collected {len(all_message_ids)} message IDs, fetching bodies...")
            logger.info(f"Folder {folder_name}: Collected {len(all_message_ids)} total message IDs")
            
            folder_fetched = 0
            folder_stored = 0
            total_batches = (len(all_message_ids) + 9) // 10
            
            for i in range(0, len(all_message_ids), 10):
                # Check for cancellation
                from app.services.sync_event_logger import is_cancelled
                if is_cancelled(run_id):
                    logger.info(f"Messages sync cancelled for run_id {run_id}")
                    event_logger.log_warning("Sync operation cancelled by user")
                    duration_ms = int((time.time() - start_time) * 1000)
                    event_logger.log_done(
                        f"Messages sync cancelled: {total_fetched} fetched, {total_stored} stored",
                        total_fetched,
                        total_stored,
                        duration_ms
                    )
                    event_logger.close()
                    return
                
                batch_ids = all_message_ids[i:i+10]
                batch_num = i//10 + 1
                event_logger.log_info(f"→ Requesting bodies batch {batch_num}/{total_batches}: POST /ws/eBayISAPI.dll (GetMyMessages - {len(batch_ids)} IDs)")
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
                    
                    event_logger.log_info(f"← Response: 200 OK ({request_duration}ms) - Received {len(messages)} message bodies")
                    
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
                        
                        body_html = msg.get("text", "") or ""
                        parsed_body = None
                        try:
                            if body_html:
                                parsed = parse_ebay_message_html(
                                    body_html,
                                    our_account_username=recipient or "seller",
                                )
                                parsed_body = parsed.dict(exclude_none=True)
                        except Exception as parse_err:
                            logger.warning(
                                f"Failed to parse eBay message body for {message_id}: {parse_err}"
                            )

                        message = Message(
                            user_id=user_id,
                            message_id=message_id,
                            thread_id=msg.get("externalmessageid") or message_id,
                            sender_username=sender,
                            recipient_username=recipient,
                            subject=msg.get("subject", ""),
                            body=body_html,
                            message_type="MEMBER_MESSAGE",
                            is_read=msg.get("read", False),
                            is_flagged=msg.get("flagged", False),
                            is_archived=msg.get("folderid") == "2",
                            direction=direction,
                            message_date=message_date,
                            order_id=None,
                            listing_id=msg.get("itemid"),
                            raw_data=str(msg),
                            parsed_body=parsed_body,
                        )
                        db.add(message)
                        folder_stored += 1
                    
                    db.commit()
                    event_logger.log_info(f"← Database: Stored {len(messages)} messages from batch {batch_num}")
                    
                    await asyncio.sleep(0.4)
                    
                except Exception as e:
                    logger.error(f"Failed to fetch/store batch {i//10 + 1}: {str(e)}")
                    event_logger.log_error(f"Batch {batch_num} failed: {str(e)}", e)
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
