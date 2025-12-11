from sqlalchemy import Column, BigInteger, String, DateTime, Text, Boolean, Integer, Numeric, ForeignKey
from sqlalchemy.sql import func

from app.database import Base


class Timesheet(Base):
    __tablename__ = "tbl_timesheet"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    username = Column(String(50), nullable=False)

    start_time = Column(DateTime(timezone=True), nullable=True)
    end_time = Column(DateTime(timezone=True), nullable=True)
    duration_minutes = Column(Integer, nullable=True)

    rate = Column(Numeric(18, 2), nullable=True)
    description = Column(Text, nullable=True)

    delete_flag = Column(Boolean, nullable=False, server_default="false")

    record_created = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    record_created_by = Column(String(50), nullable=True)
    record_updated = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    record_updated_by = Column(String(50), nullable=True)

    legacy_id = Column(Numeric(18, 0), nullable=True)
