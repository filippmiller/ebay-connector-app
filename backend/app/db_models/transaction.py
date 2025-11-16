from sqlalchemy import Column, String, DateTime, Numeric, Text, ForeignKey, Float
from sqlalchemy.sql import func
from app.database import Base
import uuid

class Transaction(Base):
    """Financial transactions mapped to public.ebay_transactions in Supabase.

    This model is trimmed to match the real production schema so that grid
    queries only reference existing columns.
    """

    __tablename__ = "ebay_transactions"

    transaction_id = Column(String(255), primary_key=True)
    user_id = Column(String(255), nullable=False, index=True)
    order_id = Column(String(255), nullable=False, index=True)

    transaction_date = Column(String(255), nullable=True, index=True)
    transaction_type = Column(String(255), nullable=True)
    transaction_status = Column(String(255), nullable=True)

    amount = Column(Float, nullable=True)
    currency = Column(String(50), nullable=True)

    transaction_data = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), index=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), index=True)

    ebay_account_id = Column(String(255), nullable=True, index=True)
    ebay_user_id = Column(String(255), nullable=True, index=True)
