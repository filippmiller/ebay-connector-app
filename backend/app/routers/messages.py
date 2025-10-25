from fastapi import APIRouter, Depends, HTTPException, Query
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

@router.post("/sync")
async def sync_messages(
    dry_run: bool = Query(False, alias="dryRun"),
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Comprehensive message sync using GetMyMessages API
    - Enumerates folders first (ReturnSummary)
    - Two-phase retrieval per folder (headers → bodies)
    - Batches message body fetches (≤10 IDs at a time)
    """
    if not current_user.ebay_connected or not current_user.ebay_access_token:
        raise HTTPException(status_code=400, detail="eBay account not connected")
    
    try:
        logger.info(f"Enumerating message folders for user {current_user.id}")
        folders_response = await ebay_service.get_message_folders(current_user.ebay_access_token)
        folders = folders_response.get("folders", [])
        
        if not folders:
            logger.warning(f"No message folders found for user {current_user.id}")
            return {
                "status": "completed",
                "folders": {},
                "total_fetched": 0,
                "total_stored": 0,
                "message": "No message folders found"
            }
        
        logger.info(f"Found {len(folders)} folders: {[f['folder_name'] for f in folders]}")
        
        if dry_run:
            folder_counts = {f["folder_name"]: f["total_count"] for f in folders}
            total_count = sum(f["total_count"] for f in folders)
            return {
                "dry_run": True,
                "folders": folder_counts,
                "total": total_count
            }
        
        total_fetched = 0
        total_stored = 0
        folder_stats = {}
        
        for folder in folders:
            folder_id = folder["folder_id"]
            folder_name = folder["folder_name"]
            folder_total = folder["total_count"]
            
            logger.info(f"Processing folder {folder_name} (ID: {folder_id}) with {folder_total} messages")
            
            if folder_total == 0:
                folder_stats[folder_name] = {"fetched": 0, "stored": 0}
                continue
            
            all_message_ids = []
            page_number = 1
            
            while True:
                logger.info(f"Fetching headers page {page_number} for folder {folder_name}")
                headers_response = await ebay_service.get_message_headers(
                    current_user.ebay_access_token,
                    folder_id,
                    page_number=page_number,
                    entries_per_page=200
                )
                
                message_ids = headers_response.get("message_ids", [])
                alert_ids = headers_response.get("alert_ids", [])
                total_pages = headers_response.get("total_pages", 1)
                
                all_message_ids.extend(message_ids)
                all_message_ids.extend(alert_ids)
                
                logger.info(f"Page {page_number}/{total_pages}: Found {len(message_ids)} messages, {len(alert_ids)} alerts")
                
                if page_number >= total_pages:
                    break
                
                page_number += 1
            
            logger.info(f"Folder {folder_name}: Collected {len(all_message_ids)} total message IDs")
            
            folder_fetched = 0
            folder_stored = 0
            
            for i in range(0, len(all_message_ids), 10):
                batch_ids = all_message_ids[i:i+10]
                logger.info(f"Fetching bodies for batch {i//10 + 1} ({len(batch_ids)} messages)")
                
                try:
                    messages = await ebay_service.get_message_bodies(
                        current_user.ebay_access_token,
                        batch_ids
                    )
                    
                    folder_fetched += len(messages)
                    
                    for msg in messages:
                        message_id = msg.get("messageid") or msg.get("externalmessageid")
                        
                        if not message_id:
                            logger.warning(f"Message missing ID, skipping: {msg}")
                            continue
                        
                        existing = db.query(Message).filter(
                            Message.message_id == message_id,
                            Message.user_id == current_user.id
                        ).first()
                        
                        if existing:
                            logger.debug(f"Message {message_id} already exists, skipping")
                            continue
                        
                        sender = msg.get("sender", "")
                        recipient = msg.get("recipientuserid", "")
                        direction = "INCOMING"
                        
                        ebay_username = getattr(current_user, "ebay_username", None)
                        if sender and ebay_username and sender.lower() == ebay_username.lower():
                            direction = "OUTGOING"
                        
                        receive_date_str = msg.get("receivedate", "")
                        message_date = datetime.utcnow()
                        if receive_date_str:
                            try:
                                message_date = datetime.fromisoformat(receive_date_str.replace("Z", "+00:00"))
                            except Exception as e:
                                logger.warning(f"Failed to parse date {receive_date_str}: {e}")
                        
                        message = Message(
                            user_id=current_user.id,
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
            
            logger.info(f"Folder {folder_name} complete: {folder_fetched} fetched, {folder_stored} stored")
        
        return {
            "status": "completed",
            "folders": folder_stats,
            "total_fetched": total_fetched,
            "total_stored": total_stored
        }
    
    except Exception as e:
        logger.error(f"Message sync failed: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Message sync failed: {str(e)}")
