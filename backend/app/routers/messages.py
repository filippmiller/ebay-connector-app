from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
from app.database import get_db
from app.db_models import Message
from app.services.auth import get_current_user
from app.models.user import User as UserModel
from pydantic import BaseModel

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
