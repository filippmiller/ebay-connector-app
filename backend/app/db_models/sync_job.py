from sqlalchemy import Column, String, DateTime, Integer, Text, ForeignKey
from sqlalchemy.sql import func
from app.database import Base
import uuid

class SyncJob(Base):
    __tablename__ = "sync_jobs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    
    job_type = Column(String(50), nullable=False)
    job_status = Column(String(50), nullable=False, index=True)
    
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    records_synced = Column(Integer, default=0)
    records_failed = Column(Integer, default=0)
    
    error_message = Column(Text)
    error_details = Column(Text)
    
    sync_params = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
