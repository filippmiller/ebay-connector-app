from sqlalchemy import Column, String, Boolean, DateTime, Integer, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.models_sqlalchemy import Base


class EbaySyncState(Base):
    """Per-account, per-API worker configuration and cursor state.

    This controls whether a given worker (orders, finances, messages, etc.) is
    enabled for a particular eBay account and tracks the last successful sync
    cursor so we can resume safely on the next run.
    """

    __tablename__ = "ebay_sync_state"

    id = Column(String(36), primary_key=True)
    ebay_account_id = Column(String(36), nullable=False, index=True)
    ebay_user_id = Column(String(64), nullable=False, index=True)
    # e.g. "orders", "finances", "messages", "seller_transactions"
    api_family = Column(String(64), nullable=False, index=True)

    enabled = Column(Boolean, nullable=False, server_default="true")
    backfill_completed = Column(Boolean, nullable=False, server_default="false")

    cursor_type = Column(String(64), nullable=True)  # e.g. "lastModifiedDate", "transactionDate"
    cursor_value = Column(String(64), nullable=True)  # ISO8601 timestamp or other cursor representation

    last_run_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)

    meta = Column(JSONB, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class EbayWorkerRun(Base):
    """Single execution of a worker for an account + API family.

    Used for locking (only one active run per account+API) and for high-level
    status reporting in the UI.
    """

    __tablename__ = "ebay_worker_run"

    id = Column(String(36), primary_key=True)
    ebay_account_id = Column(String(36), nullable=False, index=True)
    ebay_user_id = Column(String(64), nullable=False, index=True)
    api_family = Column(String(64), nullable=False, index=True)

    status = Column(String(32), nullable=False, index=True)  # running, completed, error, cancelled, stale

    started_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    finished_at = Column(DateTime(timezone=True), nullable=True)
    heartbeat_at = Column(DateTime(timezone=True), nullable=True)

    summary_json = Column(JSONB, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class EbayApiWorkerLog(Base):
    """Structured log entries for worker runs.

    This is separate from the existing ebay_connect_logger so that long-running
    background sync jobs do not spam the main connection / token logs.
    """

    __tablename__ = "ebay_api_worker_log"

    id = Column(String(36), primary_key=True)
    run_id = Column(String(36), ForeignKey("ebay_worker_run.id", ondelete="CASCADE"), nullable=False, index=True)

    ebay_account_id = Column(String(36), nullable=False, index=True)
    ebay_user_id = Column(String(64), nullable=False, index=True)
    api_family = Column(String(64), nullable=False, index=True)

    event_type = Column(String(32), nullable=False, index=True)  # start, page, done, error
    timestamp = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    details_json = Column(JSONB, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class EbayWorkerGlobalConfig(Base):
    """Global kill-switch and defaults for all workers.

    There is typically a single row in this table controlling whether workers
    are allowed to run at all. This supports the "big red button" in the UI
    that turns off ALL jobs (e.g. during maintenance or data migration).
    """

    __tablename__ = "ebay_worker_global_config"

    id = Column(String(36), primary_key=True)

    workers_enabled = Column(Boolean, nullable=False, server_default="true")

    # Optional: default overlap window in minutes, default initial backfill days, etc.
    defaults_json = Column(JSONB, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class BackgroundWorker(Base):
    """Heartbeat + status row for long-running background workers.

    This is intentionally generic so we can track not only the eBay token
    refresh worker, but also other loops (health checks, Gmail ingest, etc.).
    """

    __tablename__ = "background_workers"

    id = Column(String(36), primary_key=True)

    worker_name = Column(String(128), nullable=False, unique=True, index=True)
    interval_seconds = Column(Integer, nullable=True)

    last_started_at = Column(DateTime(timezone=True), nullable=True)
    last_finished_at = Column(DateTime(timezone=True), nullable=True)
    last_status = Column(String(32), nullable=True)
    last_error_message = Column(Text, nullable=True)

    runs_ok_in_row = Column(Integer, nullable=False, server_default="0")
    runs_error_in_row = Column(Integer, nullable=False, server_default="0")

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class EbayTokenRefreshLog(Base):
    """Per-account token refresh attempts for observability/debugging.

    Each row represents a single attempt to refresh an eBay OAuth token for a
    given EbayAccount. This powers the admin UI for seeing recent refresh
    history and diagnosing failures (e.g. invalid_grant, 401, no refresh
    token, etc.).
    """

    __tablename__ = "ebay_token_refresh_log"

    id = Column(String(36), primary_key=True)

    ebay_account_id = Column(
        String(36),
        ForeignKey("ebay_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    started_at = Column(DateTime(timezone=True), nullable=False)
    finished_at = Column(DateTime(timezone=True), nullable=True)

    success = Column(Boolean, nullable=True)
    error_code = Column(String(64), nullable=True)
    error_message = Column(Text, nullable=True)

    old_expires_at = Column(DateTime(timezone=True), nullable=True)
    new_expires_at = Column(DateTime(timezone=True), nullable=True)

    triggered_by = Column(String(32), nullable=False, server_default="scheduled")

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
