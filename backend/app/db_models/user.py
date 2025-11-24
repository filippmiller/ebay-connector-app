from sqlalchemy import Column, String, Boolean, DateTime, Text, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.database import Base


class User(Base):
    """Legacy ORM mapping for the `users` table.

    This model is used by older routers (timesheets, legacy grids, etc.) that
    still rely on `app.database` / `app.db_models`. It must match the *actual*
    production schema closely enough to support read/write operations without
    selecting non-existent columns.

    Newer code paths use `app.models_sqlalchemy.models.User` instead; keep this
    class minimal and compatible rather than feature-rich.
    """

    __tablename__ = "users"

    # Core identity / auth fields
    id = Column(String(36), primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(100), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    # When True, user must change password on next successful login.
    must_change_password = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    # eBay connection flags + tokens (single-account legacy layout)
    ebay_connected = Column(Boolean, nullable=False, default=False)
    ebay_access_token = Column(Text, nullable=True)
    ebay_refresh_token = Column(Text, nullable=True)
    ebay_token_expires_at = Column(DateTime(timezone=True), nullable=True)
    ebay_environment = Column(String(20), nullable=True)

    # Sandbox tokens (used by some legacy flows)
    ebay_sandbox_access_token = Column(Text, nullable=True)
    ebay_sandbox_refresh_token = Column(Text, nullable=True)
    ebay_sandbox_token_expires_at = Column(DateTime(timezone=True), nullable=True)

    # Timesheet / HR extensions
    legacy_id = Column(Numeric(18, 0), nullable=True)
    full_name = Column(String(255), nullable=True)
    hourly_rate = Column(Numeric(18, 2), nullable=True)

    # Optional external auth linkage
    auth_user_id = Column(UUID(as_uuid=True), nullable=True)

    # Audit fields (shared pattern across several tables)
    record_created = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    record_created_by = Column(String(50), nullable=True)
    record_updated = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    record_updated_by = Column(String(50), nullable=True)
