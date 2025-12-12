from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class WorkerDebugHttp(BaseModel):
    """HTTP request/response details for a worker step.

    Sensitive values (tokens, secrets) must be masked before populating this
    object; the backend never exposes raw OAuth tokens to the frontend via
    this model.
    """

    method: str
    url: str
    headers: Dict[str, Any] = Field(default_factory=dict)
    body: Any | None = None
    status_code: Optional[int] = None
    duration_ms: Optional[int] = None


class ColumnChange(BaseModel):
    old: Any | None = None
    new: Any | None = None


class WorkerDebugDbChange(BaseModel):
    table_name: Literal["parts_detail", "parts_detail_log"]
    row_id: int
    changes: Dict[str, ColumnChange] = Field(default_factory=dict)


WorkerDebugStepType = Literal[
    "info",
    "db-select",
    "db-update",
    "log-insert",
    "ebay-request",
    "ebay-response",
    "error",
]


class WorkerDebugStep(BaseModel):
    timestamp: datetime
    type: WorkerDebugStepType
    label: Optional[str] = None
    message: str
    http: Optional[WorkerDebugHttp] = None
    db_change: Optional[WorkerDebugDbChange] = None
    extra: Dict[str, Any] = Field(default_factory=dict)


class WorkerDebugTrace(BaseModel):
    """Full in-memory trace for a single eBay listing worker run."""

    job_id: str
    account: Optional[str] = None
    items_count: int
    steps: List[WorkerDebugStep]


class EbayListingDebugRequest(BaseModel):
    """Request body for POST /api/debug/ebay/list-once."""

    ids: Optional[List[int]] = Field(
        default=None,
        description="Optional explicit list of parts_detail.id values to process",
    )
    dry_run: bool = Field(
        default=False,
        description="If true, compute payloads and DB diffs but do not call eBay or write to DB.",
    )
    max_items: int = Field(
        default=25,
        ge=1,
        le=200,
        description="Safety cap for number of items to process in this debug run.",
    )


class EbayListingDebugSummary(BaseModel):
    items_selected: int
    items_processed: int
    items_success: int
    items_failed: int
    accounts: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Per-account summary (username / ebay_id and batch stats).",
    )


class EbayListingDebugResponse(BaseModel):
    trace: WorkerDebugTrace
    summary: EbayListingDebugSummary
