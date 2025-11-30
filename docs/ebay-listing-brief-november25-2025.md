# ebay listing worker brief Nov 25 2025

## 1. Purpose

This brief documents the first implementation of the **eBay listing worker** and **debug terminal** wired against **Supabase Postgres only** (no MSSQL). It covers:

- New Postgres tables and ORM models (`parts_detail`, `parts_detail_log`).
- A debug-only listing worker that:
  - selects candidate rows from `parts_detail`,
  - simulates bulk eBay listing calls,
  - computes and (optionally) applies DB updates,
  - writes audit rows into `parts_detail_log`,
  - returns a structured debug trace.
- A FastAPI debug endpoint.
- Frontend debug terminal modal and Listing page integration.

The current worker uses **stubbed eBay calls** (no live HTTP) to validate the data model and trace plumbing. It is safe to run in dev without touching real eBay inventory.

---

## 2. Data model: Postgres-only `parts_detail` & `parts_detail_log`

### 2.1 SQLAlchemy models

**File:** `backend/app/models_sqlalchemy/models.py`

#### 2.1.1 Status enum helper

```python path=null start=null
class PartsDetailStatus(str, enum.Enum):
    """High-level business status for parts_detail.sku/listing lifecycle.

    This is a thin semantic layer over the legacy numeric StatusSKU codes from
    the historical MSSQL schema. We intentionally keep the enum small and map
    concrete numeric codes in application logic where needed.
    """

    AWAITING_MODERATION = "AwaitingModeration"
    CHECKED = "Checked"
    LISTED_ACTIVE = "ListedActive"
    ENDED = "Ended"
    CANCELLED = "Cancelled"
    PUBLISH_ERROR = "PublishError"
```

> Note: `status_sku` is stored as a `String(32)` column; this enum provides semantic values (`PartsDetailStatus.CHECKED.value`, etc).

#### 2.1.2 `PartsDetail` (main listing table)

```python path=C:\Users\filip\.gemini\antigravity\playground\silent-spirit\backend\app\models_sqlalchemy\models.py start=466
class PartsDetail(Base):
    """Supabase/Postgres equivalent of legacy dbo.tbl_parts_detail.

    Only the core columns required by the first implementation of the eBay
    listing worker are modelled here. Additional legacy columns can be added
    incrementally as we migrate more behaviour.
    """

    __tablename__ = "parts_detail"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Identity & warehouse
    sku = Column(String(100), nullable=True, index=True)
    sku2 = Column(String(100), nullable=True)
    override_sku = Column(String(100), nullable=True)
    storage = Column(String(100), nullable=True, index=True)
    alt_storage = Column(String(100), nullable=True)
    storage_alias = Column(String(100), nullable=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=True)

    # eBay account & linkage
    item_id = Column(String(100), nullable=True, index=True)
    ebay_id = Column(String(64), nullable=True, index=True)  # internal account/site id
    username = Column(String(100), nullable=True, index=True)  # eBay username
    global_ebay_id_for_relist = Column(String(64), nullable=True)
    global_ebay_id_for_relist_flag = Column(Boolean, nullable=True)

    # Status fields (stored as string; PartsDetailStatus is a semantic helper enum)
    status_sku = Column(String(32), nullable=True, index=True)
    listing_status = Column(String(50), nullable=True, index=True)
    status_updated_at = Column(DateTime(timezone=True), nullable=True)
    status_updated_by = Column(String(100), nullable=True)
    listing_status_updated_at = Column(DateTime(timezone=True), nullable=True)
    listing_status_updated_by = Column(String(100), nullable=True)

    # Listing lifetime
    listing_start_time = Column(DateTime(timezone=True), nullable=True)
    listing_end_time = Column(DateTime(timezone=True), nullable=True)
    listing_time_updated = Column(DateTime(timezone=True), nullable=True)
    item_listed_at = Column(DateTime(timezone=True), nullable=True)

    # Prices & overrides
    override_price = Column(Numeric(14, 2), nullable=True)
    price_to_change = Column(Numeric(14, 2), nullable=True)
    price_to_change_one_time = Column(Numeric(14, 2), nullable=True)
    override_price_flag = Column(Boolean, nullable=True)
    price_to_change_flag = Column(Boolean, nullable=True)
    price_to_change_one_time_flag = Column(Boolean, nullable=True)

    # Best Offer (subset)
    best_offer_enabled_flag = Column(Boolean, nullable=True)
    best_offer_auto_accept_price_flag = Column(Boolean, nullableTrue)
    best_offer_auto_accept_price_value = Column(Numeric(14, 2), nullable=True)
    best_offer_auto_accept_price_percent = Column(Numeric(5, 2), nullable=True)
    best_offer_min_price_flag = Column(Boolean, nullable=True)
    best_offer_min_price_value = Column(Numeric(14, 2), nullable=True)
    best_offer_min_price_percent = Column(Numeric(5, 2), nullable=True)
    best_offer_mode = Column(String(20), nullable=True)
    best_offer_to_change_flag = Column(Boolean, nullable=True)
    active_best_offer_flag = Column(Boolean, nullable=True)
    active_best_offer_manual_flag = Column(Boolean, nullable=True)

    # Title, description, pictures
    override_title = Column(Text, nullable=True)
    override_description = Column(Text, nullableTrue)
    override_condition_id = Column(Integer, nullable=True)
    condition_description_to_change = Column(Text, nullable=True)
    override_pic_url_1 = Column(Text, nullable=True)
    override_pic_url_2 = Column(Text, nullable=True)
    override_pic_url_3 = Column(Text, nullable=True)
    override_pic_url_4 = Column(Text, nullable=True)
    override_pic_url_5 = Column(Text, nullable=True)
    override_pic_url_6 = Column(Text, nullable=True)
    override_pic_url_7 = Column(Text, nullable=True)
    override_pic_url_8 = Column(Text, nullable=True)
    override_pic_url_9 = Column(Text, nullable=True)
    override_pic_url_10 = Column(Text, nullable=True)
    override_pic_url_11 = Column(Text, nullable=True)
    override_pic_url_12 = Column(Text, nullable=True)

    # eBay API ACK / errors
    verify_ack = Column(String(20), nullable=True)
    verify_timestamp = Column(DateTime(timezone=True), nullable=True)
    verify_error = Column(Text, nullable=True)
    add_ack = Column(String(20), nullable=True)
    add_timestamp = Column(DateTime(timezone=True), nullable=True)
    add_error = Column(Text, nullable=True)
    revise_ack = Column(String(20), nullable=True)
    revise_timestamp = Column(DateTime(timezone=True), nullable=True)
    revise_error = Column(Text, nullable=True)

    # Batch / queue flags
    batch_error_flag = Column(Boolean, nullable=True, index=True)
    batch_error_message = Column(JSONB, nullable=True)
    batch_success_flag = Column(Boolean, nullable=True, index=True)
    batch_success_message = Column(JSONB, nullable=True)
    mark_as_listed_queue_flag = Column(Boolean, nullable=True, index=True)
    mark_as_listed_queue_updated_at = Column(DateTime(timezone=True), nullable=True)
    mark_as_listed_queue_updated_by = Column(String(100), nullable=True)
    listing_price_batch_flag = Column(Boolean, nullable=True)
    cancel_listing_queue_flag = Column(Boolean, nullable=True)
    cancel_listing_queue_flag_updated_at = Column(DateTime(timezone=True), nullable=True)
    cancel_listing_queue_flag_updated_by = Column(String(100), nullable=True)
    relist_listing_queue_flag = Column(Boolean, nullable=True)
    relist_listing_queue_flag_updated_at = Column(DateTime(timezone=True), nullable=True)
    relist_listing_queue_flag_updated_by = Column(String(100), nullable=True)
    freeze_listing_queue_flag = Column(Boolean, nullable=True)

    # Event flags
    relist_flag = Column(Boolean, nullable=True)
    relist_quantity = Column(Integer, nullable=True)
    relist_listing_flag = Column(Boolean, nullable=True)
    relist_listing_flag_updated_at = Column(DateTime(timezone=True), nullableTrue)
    relist_listing_flag_updated_by = Column(String(100), nullable=True)
    cancel_listing_flag = Column(Boolean, nullable=True)
    cancel_listing_status_sku = Column(String(50), nullableTrue)
    cancel_listing_interface = Column(String(50), nullable=True)
    freeze_listing_flag = Column(Boolean, nullableTrue)
    phantom_cancel_listing_flag = Column(Boolean, nullable=True)
    ended_for_relist_flag = Column(Boolean, nullable=True)
    just_sold_flag = Column(Boolean, nullable=True)
    return_flag = Column(Boolean, nullableTrue)
    loss_flag = Column(Boolean, nullable=True)

    # Audit
    record_created_at = Column(DateTime(timezone=True), nullable=False, server_default=datetime.utcnow)
    record_created_by = Column(String(100), nullable=True)
    record_updated_at = Column(DateTime(timezone=True), nullableTrue)
    record_updated_by = Column(String(100), nullable=True)

    logs = relationship("PartsDetailLog", back_populates="part_detail", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_parts_detail_sku", "sku"),
        Index("idx_parts_detail_item_id", "item_id"),
        Index("idx_parts_detail_status_sku", "status_sku"),
        Index("idx_parts_detail_listing_status", "listing_status"),
        Index("idx_parts_detail_username", "username"),
        Index("idx_parts_detail_ebay_id", "ebay_id"),
    )
```

#### 2.1.3 `PartsDetailLog` (audit log)

```python path=C:\Users\filip\.gemini\antigravity\playground\silent-spirit\backend\app\models_sqlalchemy\models.py start=609
class PartsDetailLog(Base):
    """High-level audit log for PartsDetail changes and worker events."""

    __tablename__ = "parts_detail_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    part_detail_id = Column(Integer, ForeignKey("parts_detail.id", ondelete="CASCADE"), nullable=False, index=True)

    # Linkage / snapshot identifiers
    sku = Column(String(100), nullable=True, index=True)
    model_id = Column(Integer, nullable=True)

    # Product snapshot
    part = Column(Text, nullable=True)
    price = Column(Numeric(14, 2), nullable=True)
    previous_price = Column(Numeric(14, 2), nullable=True)
    price_updated_at = Column(DateTime(timezone=True), nullable=True)
    market = Column(String(50), nullable=True)
    category = Column(String(100), nullable=True)
    description = Column(Text, nullable=True)
    shipping_type = Column(String(50), nullable=True)
    shipping_group = Column(String(50), nullable=True)
    condition_id = Column(Integer, nullable=True)
    pic_url_1 = Column(Text, nullableTrue)
    ...
    pic_url_12 = Column(Text, nullable=True)
    weight = Column(Numeric(12, 3), nullable=True)
    part_number = Column(String(100), nullable=True)

    # Flags & statuses
    alert_flag = Column(Boolean, nullable=True)
    alert_message = Column(Text, nullable=True)
    record_status = Column(String(50), nullableTrue)
    record_status_flag = Column(Boolean, nullable=True)
    checked_status = Column(String(50), nullable=True)
    checked_at = Column(DateTime(timezone=True), nullable=True)
    checked_by = Column(String(100), nullable=True)
    one_time_auction = Column(Boolean, nullable=True)

    # Audit
    record_created_at = Column(DateTime(timezone=True), nullable=True)
    record_created_by = Column(String(100), nullable=True)
    record_updated_at = Column(DateTime(timezone=True), nullable=True)
    record_updated_by = Column(String(100), nullable=True)
    log_created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    log_created_by = Column(String(100), nullable=True)

    part_detail = relationship("PartsDetail", back_populates="logs")

    __table_args__ = (
        Index("idx_parts_detail_log_part_detail_id", "part_detail_id"),
        Index("idx_parts_detail_log_sku", "sku"),
        Index("idx_parts_detail_log_checked_status", "checked_status"),
    )
```

*(ellipsis `...` only omits repetitive pic_url fields for brevity; they are present in code.)*

### 2.2 Alembic migration

**File:** `backend/alembic/versions/parts_detail_20251125.py`  
Creates `parts_detail` and `parts_detail_log` with the columns and indexes shown above, **using only Postgres types and the existing engine**.

---

## 3. Worker debug models (backend)

**File:** `backend/app/models/ebay_worker_debug.py`

```python path=C:\Users\filip\.gemini\antigravity\playground\silent-spirit\backend\app\models\ebay_worker_debug.py start=9
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
```

```python path=C:\Users\filip\.gemini\antigravity\playground\silent-spirit\backend\app\models\ebay_worker_debug.py start=25
class ColumnChange(BaseModel):
    old: Any | None = None
    new: Any | None = None


class WorkerDebugDbChange(BaseModel):
    table_name: Literal["parts_detail", "parts_detail_log"]
    row_id: int
    changes: Dict[str, ColumnChange] = Field(default_factory=dict)
```

```python path=C:\Users\filip\.gemini\antigravity\playground\silent-spirit\backend\app\models\ebay_worker_debug.py start=36
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
```

```python path=C:\Users\filip\.gemini\antigravity\playground\silent-spirit\backend\app\models\ebay_worker_debug.py start=57
class WorkerDebugTrace(BaseModel):
    """Full in-memory trace for a single eBay listing worker run."""

    job_id: str
    account: Optional[str] = None
    items_count: int
    steps: List[WorkerDebugStep]
```

```python path=C:\Users\filip\.gemini\antigravity\playground\silent-spirit\backend\app\models\ebay_worker_debug.py start=66
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
```

```python path=C:\Users\filip\.gemini\antigravity\playground\silent-spirit\backend\app\models\ebay_worker_debug.py start=85
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
```

---

## 4. Listing worker service (stubbed eBay calls, real Postgres writes)

**File:** `backend/app/services/ebay_listing_service.py`

### 4.1 Candidate selection & grouping

```python path=C:\Users\filip\.gemini\antigravity\playground\silent-spirit\backend\app\services\ebay_listing_service.py start=69
def _select_candidates_for_listing(
    db: Session,
    req: EbayListingDebugRequest,
) -> List[PartsDetail]:
    """Select candidate PartsDetail rows from Postgres.

    Selection rules (first approximation):
    - status_sku = CHECKED
    - item_id IS NULL
    - not frozen/cancelled
    - optional explicit ID filter from req.ids
    """

    q = db.query(PartsDetail)

    if req.ids:
        q = q.filter(PartsDetail.id.in_(req.ids))

    q = q.filter(
        PartsDetail.status_sku == PartsDetailStatus.CHECKED.value,
        PartsDetail.item_id.is_(None),
        (PartsDetail.freeze_listing_flag.is_(None)) | (PartsDetail.freeze_listing_flag.is_(False)),
        (PartsDetail.cancel_listing_flag.is_(None)) | (PartsDetail.cancel_listing_flag.is_(False)),
    )

    q = q.order_by(PartsDetail.id.asc()).limit(req.max_items)
    return list(q.all())
```

Grouping by account:

```python path=C:\Users\filip\.gemini\antigravity\playground\silent-spirit\backend\app\services\ebay_listing_service.py start=61
def _group_by_account(parts: Iterable[PartsDetail]) -> Dict[Tuple[str, str], List[PartsDetail]]:
    groups: Dict[Tuple[str, str], List[PartsDetail]] = defaultdict(list)
    for row in parts:
        key = (row.username or "", row.ebay_id or "")
        groups[key].append(row)
    return groups
```

### 4.2 Success/failure change computation

Success changes:

```python path=C:\Users\filip\.gemini\antigravity\playground\silent-spirit\backend\app\services\ebay_listing_service.py start=98
def _build_success_changes(
    row: PartsDetail,
    *,
    listing_id: str,
    now: datetime,
) -> Dict[str, ColumnChange]:
    """Compute column-level changes for a successful publish."""

    changes: Dict[str, ColumnChange] = {}

    def add(name: str, new: Any) -> None:
        old = getattr(row, name)
        if old != new:
            changes[name] = ColumnChange(old=old, new=new)

    add("item_id", listing_id)
    add("add_ack", "Success")
    add("add_timestamp", now)
    add("add_error", None)
    add("listing_status", "Active")
    add("item_listed_at", now)
    add("batch_success_flag", True)
    add("batch_success_message", {"operation": "bulkPublishOffer", "listingId": listing_id})
    add("batch_error_flag", False)
    add("batch_error_message", None)
    add("status_sku", PartsDetailStatus.LISTED_ACTIVE.value)
    add("status_updated_at", now)
    add("status_updated_by", "EBAY_WORKER")
    add("mark_as_listed_queue_flag", False)

    return changes
```

Failure changes:

```python path=C:\Users\filip\.gemini\antigravity\playground\silent-spirit\backend\app\services\ebay_listing_service.py start=135
def _build_publish_failed_changes(
    row: PartsDetail,
    *,
    error_message: str,
    error_payload: Dict[str, Any],
    now: datetime,
) -> Dict[str, ColumnChange]:
    """Compute column-level changes for a failed publish (business/transport)."""

    changes: Dict[str, ColumnChange] = {}

    def add(name: str, new: Any) -> None:
        old = getattr(row, name)
        if old != new:
            changes[name] = ColumnChange(old=old, new=new)

    add("add_ack", "Failure")
    add("add_timestamp", now)
    add("add_error", error_message[:2000])
    add("batch_error_flag", True)
    add("batch_error_message", error_payload)
    add("batch_success_flag", False)
    add("batch_success_message", None)
    # Keep item_id NULL on failure.
    # Conservative default: mark as PublishError so worker does not loop forever.
    add("status_sku", PartsDetailStatus.PUBLISH_ERROR.value)
    add("status_updated_at", now)
    add("status_updated_by", "EBAY_WORKER")
    add("mark_as_listed_queue_flag", False)

    return changes
```

Apply changes:

```python path=C:\Users\filip\.gemini\antigravity\playground\silent-spirit\backend\app\services\ebay_listing_service.py start=168
def _apply_changes(row: PartsDetail, changes: Dict[str, ColumnChange]) -> None:
    for name, change in changes.items():
        setattr(row, name, change.new)
```

Log rows:

```python path=C:\Users\filip\.gemini\antigravity\playground\silent-spirit\backend\app\services\ebay_listing_service.py start=173
def _build_log_row_for_success(row: PartsDetail, listing_id: str, now: datetime) -> PartsDetailLog:
    return PartsDetailLog(
        part_detail_id=row.id,
        sku=row.override_sku or row.sku,
        part=row.override_title,
        price=row.override_price or row.price_to_change,
        previous_price=row.price_to_change_one_time,
        price_updated_at=row.listing_time_updated,
        category=None,
        description=row.override_description,
        checked_status="EBAY_LISTED",
        checked_at=now,
        checked_by="EBAY_WORKER",
        record_status="ActiveListing",
        alert_flag=False,
        alert_message=f"Published to eBay, ItemID={listing_id}",
        log_created_at=now,
        log_created_by="EBAY_WORKER",
    )
```

### 4.3 Main entry: `run_listing_worker_debug`

```python path=C:\Users\filip\.gemini\antigravity\playground\silent-spirit\backend\app\services\ebay_listing_service.py start=215
async def run_listing_worker_debug(
    db: Session,
    req: EbayListingDebugRequest,
) -> EbayListingDebugResponse:
    """Run a single debug pass of the eBay listing worker.

    NOTE: The current implementation uses a **stubbed** eBay bulk publish
    flow: it does not yet call the real Inventory/Offer APIs.
    """

    job_id = uuid4().hex
    trace = WorkerDebugTrace(job_id=job_id, account=None, items_count=0, steps=[])

    # 1) Select candidates
    candidates = _select_candidates_for_listing(db, req)
    trace.items_count = len(candidates)
    trace.steps.append(
        _make_step(
            step_type="db-select",
            label="select candidates",
            message=f"Selected {len(candidates)} parts_detail rows for listing",
            extra={"ids": [c.id for c in candidates]},
        )
    )

    if not candidates:
        summary = EbayListingDebugSummary(
            items_selected=0,
            items_processed=0,
            items_success=0,
            items_failed=0,
            accounts=[],
        )
        return EbayListingDebugResponse(trace=trace, summary=summary)

    groups = _group_by_account(candidates)
    if len(groups) == 1:
        (username, ebay_id), _ = next(iter(groups.items()))
        trace.account = f"{username or 'UNKNOWN'} (ebay_id={ebay_id or 'N/A'})"
```

Stubbed request/response and DB updates:

```python path=C:\Users\filip\.gemini\antigravity\playground\silent-spirit\backend\app\services\ebay_listing_service.py start=263
    for (username, ebay_id), rows in groups.items():
        account_label = f"{username or 'UNKNOWN'} (ebay_id={ebay_id or 'N/A'})"
        batches: List[List[PartsDetail]] = [
            rows[i : i + MAX_ITEMS_PER_EBAY_BULK_CALL]
            for i in range(0, len(rows), MAX_ITEMS_PER_EBAY_BULK_CALL)
        ]

        acct_success = 0
        acct_failed = 0

        for batch_idx, batch in enumerate(batches, start=1):
            trace.steps.append(
                _make_step(
                    step_type="info",
                    label="batch",
                    message=f"Processing batch {batch_idx}/{len(batches)} for {account_label}",
                    extra={"batch_size": len(batch)},
                )
            )

            # 2) Build stubbed eBay payload and response
            request_body = {
                "requests": [
                    {
                        "sku": (p.override_sku or p.sku),
                        "title": p.override_title,
                        "price": float(p.override_price or p.price_to_change or 0)
                        if (p.override_price or p.price_to_change) is not None
                        else None,
                    }
                    for p in batch
                ]
            }
            http_req = WorkerDebugHttp(
                method="POST",
                url="/sell/inventory/v1/bulk_publish_offer (stub)",
                headers=_mask_headers({"Authorization": "Bearer ***", "Content-Type": "application/json"}),
                body=request_body,
            )
            trace.steps.append(
                _make_step(
                    step_type="ebay-request",
                    label="bulkPublishOffer",
                    message=f"Stubbed bulk publish request for {len(batch)} offers",
                    http=http_req,
                )
            )

            now = _utc_now()
            fake_response_body: Dict[str, Any] = {
                "results": [
                    {
                        "sku": (p.override_sku or p.sku),
                        "offerId": f"OFFER-{p.id}",
                        "listingId": f"STUB-{p.id}",
                        "status": "SUCCESS",
                    }
                    for p in batch
                ]
            }
            http_res = WorkerDebugHttp(
                method="POST",
                url="/sell/inventory/v1/bulk_publish_offer (stub)",
                headers=_mask_headers({"Content-Type": "application/json"}),
                body=fake_response_body,
                status_code=200,
                duration_ms=0,
            )
            trace.steps.append(
                _make_step(
                    step_type="ebay-response",
                    label="bulkPublishOffer",
                    message="Stubbed 200 OK bulk publish response",
                    http=http_res,
                )
            )

            # 3) For each item, compute DB changes and optionally apply them.
            for p in batch:
                listing_id = f"STUB-{p.id}"
                success_changes = _build_success_changes(p, listing_id=listing_id, now=now)

                db_change = WorkerDebugDbChange(
                    table_name="parts_detail",
                    row_id=p.id,
                    changes=success_changes,
                )
                trace.steps.append(
                    _make_step(
                        step_type="db-update",
                        label="parts_detail",
                        message=f"Update parts_detail id={p.id} for publish success",
                        db_change=db_change,
                    )
                )

                log_row = _build_log_row_for_success(p, listing_id=listing_id, now=now)
                if not req.dry_run:
                    _apply_changes(p, success_changes)
                    db.add(log_row)

                log_change = WorkerDebugDbChange(
                    table_name="parts_detail_log",
                    row_id=0 if req.dry_run else -1,  # concrete id only known after flush
                    changes={
                        "sku": ColumnChange(old=None, new=log_row.sku),
                        "checked_status": ColumnChange(old=None, new=log_row.checked_status),
                        "record_status": ColumnChange(old=None, new=log_row.record_status),
                        "alert_flag": ColumnChange(old=None, new=log_row.alert_flag),
                        "alert_message": ColumnChange(old=None, new=log_row.alert_message),
                    },
                )
                trace.steps.append(
                    _make_step(
                        step_type="log-insert",
                        label="parts_detail_log",
                        message=f"Insert publish-success log for part_detail_id={p.id}",
                        db_change=log_change,
                    )
                )

                acct_success += 1
                total_success += 1
                total_processed += 1
```

Commit & summary:

```python path=C:\Users\filip\.gemini\antigravity\playground\silent-spirit\backend\app\services\ebay_listing_service.py start=399
    if not req.dry_run:
        db.flush()
        db.commit()

    summary = EbayListingDebugSummary(
        items_selected=len(candidates),
        items_processed=total_processed,
        items_success=total_success,
        items_failed=total_failed,
        accounts=account_summaries,
    )

    trace.steps.append(
        _make_step(
            step_type="info",
            label="summary",
            message=(
                f"Job complete: selected={len(candidates)} processed={total_processed} "
                f"success={total_success} failed={total_failed}"
            ),
        )
    )

    return EbayListingDebugResponse(trace=trace, summary=summary)
```

---

## 5. Debug endpoint: `POST /api/debug/ebay/list-once`

**File:** `backend/app/routers/ebay_listing_debug.py`

```python path=C:\Users\filip\.gemini\antigravity\playground\silent-spirit\backend\app\routers\ebay_listing_debug.py start=19
router = APIRouter(prefix="/api/debug/ebay", tags=["ebay_listing_debug"])


@router.post("/list-once", response_model=EbayListingDebugResponse)
async def run_listing_once_debug(
    payload: EbayListingDebugRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> EbayListingDebugResponse:
    """Run the eBay listing worker once in debug mode and return a full trace.

    This endpoint is intended for development and internal debugging. It
    selects candidate rows from parts_detail in Supabase Postgres, simulates
    (or in the future performs) bulk eBay listing calls, computes the exact DB
    updates/inserts that would be performed, and returns a structured
    WorkerDebugTrace that the frontend renders in a terminal-like modal.
    """

    # Hard safety cap regardless of what the client sends.
    if payload.max_items > 200:
        payload.max_items = 200

    try:
        return await run_listing_worker_debug(db, payload)
    except HTTPException:
        # Let FastAPI propagate explicit HTTP errors unchanged.
        raise
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.exception("Listing debug worker failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Listing debug worker failed; see server logs for details.",
        ) from exc
```

Wired into FastAPI in `backend/app/main.py`:

```python path=C:\Users\filip\.gemini\antigravity\playground\silent-spirit\backend\app\main.py start=7
from app.routers import auth, ebay, orders, messages, offers, migration, buying, inventory, transactions, financials, admin, offers_v2, inventory_v2, ebay_accounts, ebay_workers, admin_db, grid_layouts, orders_api, grids_data, admin_mssql, ai_messages, timesheets, grid_preferences, admin_migration, admin_db_migration_console, tasks, listing, sq_catalog, ebay_notifications, shipping, ui_tweak, security_center, admin_users, sniper, ebay_listing_debug
...
app.include_router(ebay_notifications.router)
app.include_router(ebay_listing_debug.router)
```

---

## 6. Frontend: API and terminal modal

### 6.1 API client

**File:** `frontend/src/api/ebayListingWorker.ts`

```ts path=C:\Users\filip\.gemini\antigravity\playground\silent-spirit\frontend\src\api\ebayListingWorker.ts start=1
import { apiClient } from './client';

export type WorkerDebugStepType =
  | 'info'
  | 'db-select'
  | 'db-update'
  | 'log-insert'
  | 'ebay-request'
  | 'ebay-response'
  | 'error';

export interface WorkerDebugHttp {
  method: string;
  url: string;
  headers: Record<string, any>;
  body?: any;
  status_code?: number | null;
  duration_ms?: number | null;
}

export interface ColumnChange {
  old: any | null;
  new: any | null;
}

export interface WorkerDebugDbChange {
  table_name: 'parts_detail' | 'parts_detail_log';
  row_id: number;
  changes: Record<string, ColumnChange>;
}

export interface WorkerDebugStep {
  timestamp: string; // ISO string from backend
  type: WorkerDebugStepType;
  label?: string | null;
  message: string;
  http?: WorkerDebugHttp | null;
  db_change?: WorkerDebugDbChange | null;
  extra?: Record<string, any>;
}

export interface WorkerDebugTrace {
  job_id: string;
  account?: string | null;
  items_count: number;
  steps: WorkerDebugStep[];
}
...
export interface EbayListingDebugRequest {
  ids?: number[];
  dry_run?: boolean;
  max_items?: number;
}

export interface EbayListingDebugResponse {
  trace: WorkerDebugTrace;
  summary: EbayListingDebugSummary;
}

export async function runEbayListingDebug(
  payload: EbayListingDebugRequest,
): Promise<EbayListingDebugResponse> {
  const response = await apiClient.post<EbayListingDebugResponse>(
    '/api/debug/ebay/list-once',
    payload,
  );
  return response.data;
}
```

### 6.2 Debug modal

**File:** `frontend/src/components/WorkerDebugTerminalModal.tsx`

```tsx path=C:\Users\filip\.gemini\antigravity\playground\silent-spirit\frontend\src\components\WorkerDebugTerminalModal.tsx start=1
import React, { useEffect, useMemo, useRef } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog';
import { ScrollArea } from './ui/scroll-area';
import { Button } from './ui/button';
import type {
  WorkerDebugTrace,
  WorkerDebugStep,
  WorkerDebugDbChange,
  WorkerDebugHttp,
} from '@/api/ebayListingWorker';

export interface WorkerDebugTerminalModalProps {
  isOpen: boolean;
  onClose: () => void;
  trace: WorkerDebugTrace | null;
}

function formatTime(ts: string): string {
  try {
    const d = new Date(ts);
    return d.toLocaleTimeString(undefined, {
      hour12: false,
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  } catch {
    return ts;
  }
}
...
export const WorkerDebugTerminalModal: React.FC<WorkerDebugTerminalModalProps> = ({
  isOpen,
  onClose,
  trace,
}) => {
  const scrollRef = useRef<HTMLDivElement | null>(null);

  const steps = trace?.steps ?? [];

  const startEnd = useMemo(() => {
    if (!steps.length) return { start: null as string | null, end: null as string | null };
    return { start: steps[0].timestamp, end: steps[steps.length - 1].timestamp };
  }, [steps]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [steps.length, isOpen]);

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-5xl h-[70vh] flex flex-col bg-black text-gray-100">
        <DialogHeader>
          <DialogTitle className="flex items-center justify-between text-sm font-mono">
            <span>
              eBay Listing Worker Debug
              {trace && (
                <span className="ml-2 text-xs text-gray-400">
                  job_id={trace.job_id}
                </span>
              )}
            </span>
            <span className="text-xs text-gray-400 flex items-center gap-3">
              {trace?.account && <span>account={trace.account}</span>}
              {typeof trace?.items_count === 'number' && (
                <span>items={trace.items_count}</span>
              )}
              {startEnd.start && (
                <span>
                  window=
                  {formatTime(startEnd.start)}
                  {' → '}
                  {startEnd.end ? formatTime(startEnd.end) : '—'}
                </span>
              )}
            </span>
          </DialogTitle>
        </DialogHeader>
        <div className="flex-1 flex flex-col border border-gray-700 bg-black/80 rounded-md overflow-hidden">
          <div
            ref={scrollRef}
            className="flex-1 overflow-auto font-mono text-[11px] leading-snug p-2"
          >
            <ScrollArea className="h-full w-full">
              <div className="space-y-1">
                {steps.map((step, idx) => {
                  const time = formatTime(step.timestamp);
                  return (
                    <div key={idx} className="whitespace-pre-wrap break-all">
                      <span className="text-gray-500 mr-2">[{time}]</span>
                      <span className={`mr-2 ${stepColor(step.type)}`}>[{step.type}]</span>
                      {step.label && (
                        <span className="text-purple-300 mr-1">{step.label}</span>
                      )}
                      <span>{step.message}</span>
                      {step.http && (
                        <div className="mt-1">
                          {renderHttp(step.http, step.type === 'ebay-response' ? 'response' : 'request')}
                        </div>
                      )}
                      {step.db_change && (
                        <div className="mt-1">
                          <div className="ml-4 text-[11px] text-gray-300 mb-0.5">
                            table=
                            {step.db_change.table_name} row_id=
                            {step.db_change.row_id}
                          </div>
                          {renderDbChange(step.db_change)}
                        </div>
                      )}
                    </div>
                  );
                })}
                {!steps.length && (
                  <div className="text-gray-400">No debug steps recorded.</div>
                )}
              </div>
            </ScrollArea>
          </div>
          <div className="border-t border-gray-700 px-2 py-1 flex items-center justify-between bg-black/70 text-xs">
            <span className="text-gray-500">
              Debug mode only. Sensitive headers and tokens are masked in this view.
            </span>
            <Button size="xs" variant="outline" onClick={onClose}>
              Close
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};
```

---

## 7. ListingPage integration: debug panel + modal (dev only)

**File:** `frontend/src/pages/ListingPage.tsx`

Feature flag and state:

```tsx path=C:\Users\filip\.gemini\antigravity\playground\silent-spirit\frontend\src\pages\ListingPage.tsx start=29
const DEBUG_EBAY_LISTING = import.meta.env.VITE_DEBUG_EBAY_LISTING === 'true';

export default function ListingPage() {
  const { toast } = useToast();

  const [draftItems, setDraftItems] = useState<DraftListingItem[]>([]);
  ...
  // Debug listing worker (parts_detail) – dev only
  const [debugIds, setDebugIds] = useState('');
  const [debugTrace, setDebugTrace] = useState<WorkerDebugTrace | null>(null);
  const [debugOpen, setDebugOpen] = useState(false);
  const [debugLoading, setDebugLoading] = useState(false);
  const [debugError, setDebugError] = useState<string | null>(null);
```

Handler to invoke worker:

```tsx path=C:\Users\filip\.gemini\antigravity\playground\silent-spirit\frontend\src\pages\ListingPage.tsx start=193
  const handleRunDebugWorker = async () => {
    if (!DEBUG_EBAY_LISTING) return;
    const raw = debugIds.trim();
    if (!raw) {
      toast({ title: 'No IDs provided', description: 'Enter parts_detail IDs (comma separated).', variant: 'destructive' });
      return;
    }

    const ids = Array.from(
      new Set(
        raw
          .split(/[\s,]+/)
          .map((s) => s.trim())
          .filter(Boolean)
          .map((s) => Number(s))
          .filter((n) => Number.isFinite(n) && n > 0),
      ),
    );

    if (!ids.length) {
      toast({ title: 'Invalid IDs', description: 'Could not parse any numeric IDs from input.', variant: 'destructive' });
      return;
    }

    try {
      setDebugLoading(true);
      setDebugError(null);
      const resp = await runEbayListingDebug({ ids, dry_run: false, max_items: 50 });
      setDebugTrace(resp.trace);
      setDebugOpen(true);
    } catch (e: any) {
      const detail = e?.response?.data?.detail ?? e?.message ?? 'Debug worker failed';
      setDebugError(String(detail));
      toast({ title: 'Debug worker error', description: String(detail), variant: 'destructive' });
    } finally {
      setDebugLoading(false);
    }
  };
```

Debug control panel:

```tsx path=C:\Users\filip\.gemini\antigravity\playground\silent-spirit\frontend\src\pages\ListingPage.tsx start=381
        {DEBUG_EBAY_LISTING && (
          <div className="mt-4 border rounded-lg bg-white p-3 text-xs font-mono text-gray-700">
            <div className="flex items-center justify-between mb-2">
              <div className="font-semibold text-gray-800">eBay Listing Worker Debug (parts_detail)</div>
              {debugLoading && <span className="text-blue-600">Running…</span>}
            </div>
            <div className="flex flex-wrap items-center gap-2 mb-2">
              <input
                className="border rounded px-2 py-1 text-xs min-w-[260px]"
                placeholder="parts_detail IDs (e.g. 101, 102, 103)"
                value={debugIds}
                onChange={(e) => setDebugIds(e.target.value)}
              />
              <button
                className="px-3 py-1 text-xs rounded bg-black text-white hover:bg-gray-800 disabled:bg-gray-300 disabled:cursor-not-allowed"
                onClick={handleRunDebugWorker}
                disabled={debugLoading}
              >
                Run listing worker (debug)
              </button>
              <span className="text-[11px] text-gray-500">
                Uses POST /api/debug/ebay/list-once against Supabase parts_detail.
              </span>
            </div>
            {debugError && <div className="text-red-600 text-[11px]">Error: {debugError}</div>}
          </div>
        )}
```

Modal wiring:

```tsx path=C:\Users\filip\.gemini\antigravity\playground\silent-spirit\frontend\src\pages\ListingPage.tsx start=408
      </div>

      {DEBUG_EBAY_LISTING && (
        <WorkerDebugTerminalModal
          isOpen={debugOpen}
          onClose={() => setDebugOpen(false)}
          trace={debugTrace}
        />
      )}
    </div>
  );
}
```

This gives a **manual, dev-only** way to:

- Input `parts_detail.id` values,
- Trigger the debug worker,
- See the full step-by-step trace in the modal.

---

## 8. Notes and next steps

- All persistence uses **Supabase Postgres** via the existing SQLAlchemy engine (`DATABASE_URL`). The legacy MSSQL schema is used only as a conceptual source for column naming.
- `run_listing_worker_debug` currently uses **stubbed eBay calls**:
  - Logs what would be sent to `bulkPublishOffer`.
  - Simulates per-item success to test `parts_detail` and `parts_detail_log` writes.
- Follow-up tasks could:
  - Add real eBay bulk Inventory/Offer/Publish integration (in `EbayService`), keyed by `EbayAccount`/`EbayToken`.
  - Use real responses to drive `_build_publish_failed_changes` / `_build_log_row_for_failure`.
  - Tie `parts_detail` into your existing listing flow so “Commit selected” populates `parts_detail`, and automatically call the debug endpoint on Save/List in debug mode.
  - Optionally integrate this worker into the generic `ebay_workers` scheduler for non-debug batch runs.
