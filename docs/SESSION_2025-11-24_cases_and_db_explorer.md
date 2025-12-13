# 2025-11-24 – Admin DB Explorer + eBay cases normalization

This document summarizes all backend and frontend changes implemented during the
2025-11-24 session so that future contributors (agents) can quickly understand
what was done and how the pieces fit together.

High-level goals:

- Improve the **Admin → DB Explorer** grid UX (sticky header + resizable
  columns).
- Normalize **eBay Post-Order cases** into explicit columns in
  `public.ebay_cases` instead of relying only on raw JSON.
- Expose normalized case fields through the **Cases & Disputes** grid and
  through an **admin-only cases sync endpoint**.

The sections below are grouped by feature area and include code pointers.

## 1. Admin → DB Explorer grid improvements

### 1.1 Feature

On the **Admin → DB Explorer** page (`/admin/db-explorer`) we changed the
"Data" tab grid so that:

- The **header row is sticky**: when you scroll the data vertically, the column
  header stays visible.
- **Columns are resizable** by dragging the right edge of each header cell.

This is intentionally scoped only to the DB Explorer page (not to the shared
`DataGridPage`/AG Grid infrastructure).

### 1.2 Implementation

**File:** `frontend/src/pages/AdminDbExplorerPage.tsx`

Key pieces (line numbers are approximate):

- We introduced local state to track per-column widths:

```ts path=/C:/Users/filip/.gemini/antigravity/playground/silent-spirit/frontend/src/pages/AdminDbExplorerPage.tsx start=150
const [mssqlDatabase, setMssqlDatabase] = useState('DB_A28F26_parts');
// Per-column pixel widths for the DB Explorer data grid only.
const [columnWidths, setColumnWidths] = useState<Record<string, number>>({});
```

- In `renderData()` we added a `beginColumnResize` helper that listens to
  `mousemove`/`mouseup` on `window` and updates `columnWidths[colName]`.

```ts path=/C:/Users/filip/.gemini/antigravity/playground/silent-spirit/frontend/src/pages/AdminDbExplorerPage.tsx start=345
const beginColumnResize = (columnName: string, clientX: number) => {
  const MIN_WIDTH = 80;
  const MAX_WIDTH = 600;

  // Start from the last saved width if present, otherwise a default.
  const startWidth = columnWidths[columnName] ?? 160;
  const startX = clientX;

  const handleMouseMove = (event: MouseEvent) => {
    const delta = event.clientX - startX;
    const next = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, startWidth + delta));
    setColumnWidths((prev) => ({ ...prev, [columnName]: next }));
  };

  const handleMouseUp = () => {
    window.removeEventListener('mousemove', handleMouseMove);
    window.removeEventListener('mouseup', handleMouseUp);
  };

  window.addEventListener('mousemove', handleMouseMove);
  window.addEventListener('mouseup', handleMouseUp);
};
```

- The table header (`thead`) is now sticky and each `<th>` uses
  `position: relative` with a narrow resize handle on the right:

```tsx path=/C:/Users/filip/.gemini/antigravity/playground/silent-spirit/frontend/src/pages/AdminDbExplorerPage.tsx start=614
<div className="overflow-auto border rounded max-h-[60vh]">
  <table
    id="db-explorer-data-table"
    className="min-w-full text-xs table-auto"
  >
    <thead className="bg-gray-100 sticky top-0 z-10">
      <tr>
        {columns.map((col) => {
          const width = columnWidths[col];
          return (
            <th
              key={col}
              data-column-name={col}
              className="relative px-2 py-1 border text-left font-mono text-[11px] cursor-pointer select-none bg-gray-100"
              style={width ? { width } : undefined}
              onClick={() => handleDataHeaderClick(col)}
            >
              <div className="flex items-center justify-between gap-1">
                <span className="truncate">
                  {col}
                  {dataSortColumn === col && (dataSortDirection === 'asc' ? ' ▲' : ' ▼')}
                </span>
                <span
                  className="absolute top=0 right-0 h-full w-1.5 cursor-col-resize select-none"
                  onMouseDown={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    beginColumnResize(col, e.clientX);
                  }}
                />
              </div>
            </th>
          );
        })}
      </tr>
    </thead>
    <tbody>
      {sortedRows.map((row, idx) => (
        <tr key={idx} className="border-t">
          {columns.map((col) => {
            const width = columnWidths[col];
            return (
              <td
                key={col}
                className="px-2 py-1 border whitespace-nowrap max-w-xs overflow-x-auto text-[11px] font-mono"
                style={width ? { width } : undefined}
              >
                <div className="inline-block whitespace-pre select-text">
                  {row[col] === null || row[col] === undefined
                    ? ''
                    : typeof row[col] === 'object'
                    ? JSON.stringify(row[col], null, 2)
                    : String(row[col])}
                </div>
              </td>
            );
          })}
        </tr>
      ))}
    </tbody>
  </table>
</div>
```

Notes:

- The resize behavior is purely client-side and scoped to this page.
- Column widths are not yet persisted to the backend; they reset on reload.


## 2. eBay cases normalization in Postgres

### 2.1 Schema changes (Alembic migration)

**File:** `backend/alembic/versions/ebay_cases_normalization_20251124.py`

**Purpose:**

- Add explicit normalized columns to `public.ebay_cases` for key Post-Order
  case fields.
- Backfill existing rows by parsing `case_data` JSON.
- Make the DDL and backfill idempotent and resilient to bad JSON.

**New columns (all nullable):**

- `item_id` (`varchar(100)`) – from `case_data.itemId`.
- `transaction_id` (`varchar(100)`) – from `case_data.transactionId`.
- `buyer_username` (`text`) – from `case_data.buyer`.
- `seller_username` (`text`) – from `case_data.seller`.
- `case_status_enum` (`text`) – from `case_data.caseStatusEnum`
  (e.g. `CS_OPEN`, `CS_CLOSED`).
- `claim_amount_value` (`numeric(12,2)`) – from `case_data.claimAmount.value`.
- `claim_amount_currency` (`varchar(10)`) – from
  `case_data.claimAmount.currency`.
- `respond_by` (`timestamptz`) – from `case_data.respondByDate.value`.
- `creation_date_api` (`timestamptz`) – from `case_data.creationDate.value`.
- `last_modified_date_api` (`timestamptz`) – from
  `case_data.lastModifiedDate.value`.

**Indexes:**

- `idx_ebay_cases_transaction_id` on `transaction_id`.
- `idx_ebay_cases_item_id` on `item_id`.
- `idx_ebay_cases_buyer_username` on `buyer_username`.
- `idx_ebay_cases_respond_by` on `respond_by`.

**Backfill logic (simplified):**

```py path=/C:/Users/filip/.gemini/antigravity/playground/silent-spirit/backend/alembic/versions/ebay_cases_normalization_20251124.py start=188
conn = op.get_bind()
rows = conn.execute(
    sa_text(
        f"SELECT case_id, user_id, case_data FROM {TABLE_NAME} WHERE case_data IS NOT NULL",
    ),
).mappings().all()
...
for row in rows:
    case_id = row["case_id"]
    user_id = row["user_id"]
    raw = row["case_data"]

    try:
        payload = json.loads(raw) if isinstance(raw, str) else (raw or {})
    except Exception as exc:
        LOGGER.warning(
            "ebay_cases backfill: failed to parse case_data JSON for case_id=%s user_id=%s: %s",
            case_id,
            user_id,
            exc,
        )
        continue

    if not isinstance(payload, dict):
        continue

    item_id = payload.get("itemId") or payload.get("item_id")
    transaction_id = payload.get("transactionId") or payload.get("transaction_id")
    buyer_username = payload.get("buyer") or payload.get("buyer_username")
    seller_username = payload.get("seller") or payload.get("seller_username")
    case_status_enum = payload.get("caseStatusEnum") or payload.get("case_status_enum")

    claim_amount_obj = payload.get("claimAmount") or payload.get("claim_amount")
    claim_amount_value, claim_amount_currency = _parse_money(
        claim_amount_obj if isinstance(claim_amount_obj, dict) else None,
    )

    respond_by_raw = _nested(payload, "respondByDate", "value") or payload.get("respondByDate")
    creation_raw = _nested(payload, "creationDate", "value") or payload.get("creationDate")
    last_modified_raw = _nested(payload, "lastModifiedDate", "value") or payload.get("lastModifiedDate")

    respond_by = _parse_datetime(respond_by_raw if isinstance(respond_by_raw, str) else None)
    creation_date_api = _parse_datetime(creation_raw if isinstance(creation_raw, str) else None)
    last_modified_date_api = _parse_datetime(
        last_modified_raw if isinstance(last_modified_raw, str) else None,
    )

    conn.execute(
        update_stmt,
        {
            "case_id": case_id,
            "user_id": user_id,
            "item_id": str(item_id) if item_id is not None else None,
            "transaction_id": str(transaction_id) if transaction_id is not None else None,
            "buyer_username": buyer_username,
            "seller_username": seller_username,
            "case_status_enum": case_status_enum,
            "claim_amount_value": claim_amount_value,
            "claim_amount_currency": claim_amount_currency,
            "respond_by": respond_by,
            "creation_date_api": creation_date_api,
            "last_modified_date_api": last_modified_date_api,
        },
    )
```

Errors during parsing or updating are logged and do **not** abort the
migration; problematic rows are left with `NULL` in new columns.


### 2.2 Upserting normalized cases

**File:** `backend/app/services/postgres_ebay_database.py`

Method `PostgresEbayDatabase.upsert_case` was extended to always populate the
new columns when the Post-Order cases worker runs.

Simplified shape of the method:

```py path=/C:/Users/filip/.gemini/antigravity/playground/silent-spirit/backend/app/services/postgres_ebay_database.py start=680
def upsert_case(
    self,
    user_id: str,
    case_data: Dict[str, Any],
    ebay_account_id: Optional[str] = None,
    ebay_user_id: Optional[str] = None,
) -> bool:
    """Insert or update a Post-Order case in ebay_cases.

    Pipeline overview (Post-Order cases only): the cases worker calls
    ``EbayService.sync_postorder_cases``, which fetches cases from
    ``GET /post-order/v2/casemanagement/search`` and passes each payload
    here. This helper normalizes identifiers, buyer/seller usernames,
    monetary amounts and key timestamps into explicit ebay_cases columns
    while also storing the full raw JSON payload in ``case_data``.
    """

    case_id = case_data.get("caseId") or case_data.get("case_id")
    ...
    order_id = case_data.get("orderId") or case_data.get("order_id")
    case_type = case_data.get("caseType") or case_data.get("case_type")
    case_status = case_data.get("status") or case_data.get("caseStatus")
    open_date = case_data.get("openDate") or case_data.get("open_date")
    close_date = case_data.get("closeDate") or case_data.get("close_date")

    # Normalized identifiers and denormalized API fields.
    item_id = case_data.get("itemId") or case_data.get("item_id")
    if item_id is not None:
        item_id = str(item_id)

    transaction_id = case_data.get("transactionId") or case_data.get("transaction_id")
    if transaction_id is not None:
        transaction_id = str(transaction_id)

    buyer_username = case_data.get("buyer") or case_data.get("buyer_username")
    seller_username = case_data.get("seller") or case_data.get("seller_username")

    case_status_enum = case_data.get("caseStatusEnum") or case_data.get("case_status_enum")

    claim_amount_obj = case_data.get("claimAmount") or case_data.get("claim_amount")
    if isinstance(claim_amount_obj, dict):
        claim_amount_value, claim_amount_currency = self._parse_money(claim_amount_obj)
    else:
        claim_amount_value, claim_amount_currency = (None, None)

    respond_by_raw = self._safe_get(case_data, "respondByDate", "value") or case_data.get("respondByDate")
    creation_raw = self._safe_get(case_data, "creationDate", "value") or case_data.get("creationDate")
    last_modified_raw = self._safe_get(case_data, "lastModifiedDate", "value") or case_data.get("lastModifiedDate")

    respond_by = self._parse_datetime(respond_by_raw if isinstance(respond_by_raw, str) else None)
    creation_date_api = self._parse_datetime(creation_raw if isinstance(creation_raw, str) else None)
    last_modified_date_api = self._parse_datetime(
        last_modified_raw if isinstance(last_modified_raw, str) else None,
    )

    if item_id is None or transaction_id is None:
        logger.warning(
            "Post-Order case %s missing itemId or transactionId (item_id=%r, transaction_id=%r)",
            case_id,
            item_id,
            transaction_id,
        )

    # INSERT ... ON CONFLICT (case_id, user_id) DO UPDATE ...
    query = text(
        """
        INSERT INTO ebay_cases
        (case_id, user_id, ebay_account_id, ebay_user_id,
         order_id, case_type, case_status,
         open_date, close_date, case_data,
         item_id, transaction_id,
         buyer_username, seller_username,
         case_status_enum,
         claim_amount_value, claim_amount_currency,
         respond_by, creation_date_api, last_modified_date_api,
         created_at, updated_at)
        VALUES (...)
        ON CONFLICT (case_id, user_id) DO UPDATE SET
          order_id = EXCLUDED.order_id,
          ...,
          item_id = EXCLUDED.item_id,
          transaction_id = EXCLUDED.transaction_id,
          buyer_username = EXCLUDED.buyer_username,
          seller_username = EXCLUDED.seller_username,
          case_status_enum = EXCLUDED.case_status_enum,
          claim_amount_value = EXCLUDED.claim_amount_value,
          claim_amount_currency = EXCLUDED.claim_amount_currency,
          respond_by = EXCLUDED.respond_by,
          creation_date_api = EXCLUDED.creation_date_api,
          last_modified_date_api = EXCLUDED.last_modified_date_api,
          ebay_account_id = EXCLUDED.ebay_account_id,
          ebay_user_id = EXCLUDED.ebay_user_id,
          updated_at = EXCLUDED.updated_at
        """
    )
```

This guarantees that every new or updated Post-Order case has normalized data
ready for joining with messages, finances, etc.


## 3. Cases worker and admin trigger

### 3.1 Worker: `sync_postorder_cases`

**File:** `backend/app/services/ebay.py`

The method `EbayService.sync_postorder_cases` orchestrates the Post-Order API
polling and calls `upsert_case` for each result. We extended it with
normalization metrics and better logging.

Key counters (initialized at the top of `try` block):

```py path=/C:/Users/filip/.gemini/antigravity/playground/silent-spirit/backend/app/services/ebay.py start=3280
total_fetched = 0
total_stored = 0
normalized_full = 0
normalized_partial = 0
normalization_errors = 0
```

Inside the storage loop:

```py path=/C:/Users/filip/.gemini/antigravity/playground/silent-spirit/backend/app/services/ebay.py start=3381
for c in cases:
    ...
    # Store all Post-Order cases (no filtering by issue type)
    try:
        ok = ebay_db.upsert_case(
            user_id,
            c,
            ebay_account_id=ebay_account_id,
            ebay_user_id=ebay_user_id,
        )
    except Exception as exc:  # defensive
        normalization_errors += 1
        logger.warning(
            "Cases sync: failed to upsert case payload (case data error): %s",
            exc,
            exc_info=True,
        )
        ok = False

    if ok:
        stored += 1
        # Heuristic: treat rows with both itemId and transactionId present as
        # fully normalized; otherwise mark as partial.
        item_id = c.get("itemId") or c.get("item_id")
        txn_id = c.get("transactionId") or c.get("transaction_id")
        if item_id and txn_id:
            normalized_full += 1
        else:
            normalized_partial += 1
    else:
        normalization_errors += 1
```

At the end we log a richer summary and return the metrics to callers:

```py path=/C:/Users/filip/.gemini\antigravity\playground\silent-spirit\backend\app\services\ebay.py start=3415
event_logger.log_done(
    f"Cases sync completed: {total_fetched} fetched, {total_stored} stored in {duration_ms}ms"
    f" (normalized_full={normalized_full}, normalized_partial={normalized_partial}, "
    f"normalization_errors={normalization_errors})",
    total_fetched,
    total_stored,
    duration_ms,
)
logger.info(
    "Cases sync completed: fetched=%s, stored=%s, normalized_full=%s, "
    "normalized_partial=%s, normalization_errors=%s",
    total_fetched,
    total_stored,
    normalized_full,
    normalized_partial,
    normalization_errors,
)

return {
    "status": "completed",
    "total_fetched": total_fetched,
    "total_stored": total_stored,
    "normalized_full": normalized_full,
    "normalized_partial": normalized_partial,
    "normalization_errors": normalization_errors,
    "job_id": job_id,
    "run_id": event_logger.run_id,
}
```

### 3.2 Worker wrapper: `run_cases_worker_for_account`

**File:** `backend/app/services/ebay_workers/cases_worker.py`

The worker function `run_cases_worker_for_account(ebay_account_id)` already
existed; we updated it to propagate the new metrics into the worker run summary
stored in `ebay_worker_run.summary_json`.

Relevant portion:

```py path=/C:/Users/filip/.gemini/antigravity/playground/silent-spirit/backend/app/services/ebay_workers/cases_worker.py start=108
result = await ebay_service.sync_postorder_cases(
    user_id=user_id,
    access_token=token.access_token,
    run_id=sync_run_id,
    ebay_account_id=ebay_account_id,
    ebay_user_id=ebay_user_id,
    window_from=from_iso,
    window_to=to_iso,
)

total_fetched = int(result.get("total_fetched", 0))
total_stored = int(result.get("total_stored", 0))
normalized_full = int(result.get("normalized_full", 0))
normalized_partial = int(result.get("normalized_partial", 0))
normalization_errors = int(result.get("normalization_errors", 0))
...
complete_run(
    db,
    run,
    summary={
        "total_fetched": total_fetched,
        "total_stored": total_stored,
        "duration_ms": duration_ms,
        "window_from": from_iso,
        "window_to": to_iso,
        "sync_run_id": sync_run_id,
        "normalized_full": normalized_full,
        "normalized_partial": normalized_partial,
        "normalization_errors": normalization_errors,
    },
)
```

These summary fields are visible via `GET /api/ebay-workers/runs` and via the
new admin endpoint described below.

### 3.3 Admin endpoint: `/api/admin/cases/sync`

**File:** `backend/app/routers/admin.py`

We added an admin-only HTTP endpoint to trigger a single run of the cases
worker for a specific eBay account and to return its summary.

Signature and behavior:

```py path=/C:/Users/filip/.gemini/antigravity/playground/silent-spirit/backend/app/routers/admin.py start=182
@router.post("/cases/sync")
async def admin_run_cases_sync_for_account(
    account_id: str = Query(..., description="eBay account id"),
    current_user: User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    """Run the Post-Order cases worker once for an account (admin-only).

    This wraps ``run_cases_worker_for_account`` so admins can trigger a cases
    sync directly from the Admin area and immediately see the resulting
    worker-run summary, including normalization statistics.
    """

    # Ensure the account belongs to the current org.
    account: Optional[EbayAccount] = (
        db.query(EbayAccount)
        .filter(EbayAccount.id == account_id, EbayAccount.org_id == current_user.id)
        .first()
    )
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="account_not_found")

    from app.services.ebay_workers.cases_worker import run_cases_worker_for_account

    run_id = await run_cases_worker_for_account(account_id)
    if not run_id:
        return {"status": "skipped", "reason": "not_started"}

    worker_run: Optional[EbayWorkerRun] = db.query(EbayWorkerRun).filter(EbayWorkerRun.id == run_id).first()
    if not worker_run:
        return {"status": "started", "run_id": run_id, "summary": None}

    return {
        "status": worker_run.status,
        "run_id": worker_run.id,
        "api_family": worker_run.api_family,
        "started_at": worker_run.started_at.isoformat() if worker_run.started_at else None,
        "finished_at": worker_run.finished_at.isoformat() if worker_run.finished_at else None,
        "summary": worker_run.summary_json or {},
    }
```

Usage example (pseudo HTTP):

- `POST /api/admin/cases/sync?account_id={EBAY_ACCOUNT_ID}`
- Response contains `status`, `run_id`, and `summary` with the normalization
  counters.

This endpoint is separate from (but complementary to)
`POST /api/ebay-workers/run?api=cases&account_id=...` and is intended for
manual control from the Admin UI.


## 4. Cases & Disputes grid updates

### 4.1 Grid data source

**File:** `backend/app/routers/grids_data.py`, function `_get_cases_data(...)`.

This function builds the unified **Cases & Disputes** grid by `UNION ALL`-ом:

- `ebay_disputes` – legacy payment disputes.
- `ebay_cases` – Post-Order cases (normalized by the changes above).

We updated the SQL projection from `ebay_cases` to include normalized fields
and to use them where possible.

Key part of the union query:

```py path=/C:/Users/filip/.gemini/antigravity/playground/silent-spirit/backend/app/routers/grids_data.py start=1121
union_sql = sa_text(
    """
    SELECT
        'payment_dispute' AS kind,
        d.dispute_id      AS external_id,
        d.order_id        AS order_id,
        d.dispute_reason  AS reason,
        d.dispute_status  AS status,
        d.open_date       AS open_date,
        d.respond_by_date AS respond_by_date,
        d.dispute_data    AS raw_payload,
        d.ebay_account_id AS ebay_account_id,
        d.ebay_user_id    AS ebay_user_id,
        NULL::text        AS buyer_username,
        NULL::numeric     AS amount_value,
        NULL::text        AS amount_currency,
        NULL::timestamptz AS creation_date_api,
        NULL::timestamptz AS last_modified_date_api,
        NULL::text        AS case_status_enum,
        NULL::text        AS item_id,
        NULL::text        AS transaction_id
    FROM ebay_disputes d
    WHERE d.user_id = :user_id
    UNION ALL
    SELECT
        'postorder_case'  AS kind,
        c.case_id         AS external_id,
        c.order_id        AS order_id,
        c.case_type       AS reason,
        c.case_status     AS status,
        COALESCE(c.creation_date_api::text, c.open_date)  AS open_date,
        COALESCE(c.respond_by::text, c.close_date)        AS respond_by_date,
        c.case_data       AS raw_payload,
        c.ebay_account_id AS ebay_account_id,
        c.ebay_user_id    AS ebay_user_id,
        c.buyer_username  AS buyer_username,
        c.claim_amount_value    AS amount_value,
        c.claim_amount_currency AS amount_currency,
        c.creation_date_api     AS creation_date_api,
        c.last_modified_date_api AS last_modified_date_api,
        c.case_status_enum      AS case_status_enum,
        c.item_id          AS item_id,
        c.transaction_id   AS transaction_id
    FROM ebay_cases c
    WHERE c.user_id = :user_id
    """
)
```

The in-memory assembly step then prefers normalized columns and only falls back
to parsing `raw_payload` when necessary:

```py path=/C:/Users/filip/.gemini/antigravity/playground/silent-spirit/backend/app/routers/grids_data.py start=1179
rows_all: List[Dict[str, Any]] = []
for row in result:
    issue = _issue_type(row.reason)

    # Prefer normalized columns from ebay_cases for Post-Order cases, but
    # fall back to parsing raw_payload for legacy rows or disputes.
    buyer_username = getattr(row, "buyer_username", None)
    amount = getattr(row, "amount_value", None)
    currency = getattr(row, "amount_currency", None)
    creation_date_api = getattr(row, "creation_date_api", None)
    last_modified_date_api = getattr(row, "last_modified_date_api", None)
    case_status_enum = getattr(row, "case_status_enum", None)
    item_id = getattr(row, "item_id", None)
    transaction_id = getattr(row, "transaction_id", None)
    ...
    rows_all.append(
        {
            "kind": row.kind,
            "external_id": row.external_id,
            "order_id": row.order_id,
            "status": row.status,
            "issue_type": issue or "OTHER",
            "buyer_username": buyer_username,
            "amount": amount,
            "currency": currency,
            "open_date": open_date,
            "respond_by_date": respond_by_date,
            "ebay_account_id": row.ebay_account_id,
            "ebay_user_id": row.ebay_user_id,
            "item_id": item_id,
            "transaction_id": transaction_id,
            "case_status_enum": case_status_enum,
            "creation_date_api": creation_date_api_str,
            "last_modified_date_api": last_modified_date_api_str,
        }
    )
```

These keys are what the grid layer (`DataGridPage`) exposes as columns.

### 4.2 Grid column metadata and eBay user ID

**File:** `backend/app/routers/grid_layouts.py`

We augmented `CASES_COLUMNS_META` to include normalized fields and to show
**eBay user ID** instead of the raw `ebay_account_id` UUID.

```py path=/C:/Users/filip/.gemini/antigravity/playground/silent-spirit/backend/app/routers/grid_layouts.py start=190
CASES_COLUMNS_META: List[ColumnMeta] = [
  ColumnMeta(name="open_date", label="Opened at", type="datetime", width_default=180),
  ColumnMeta(name="external_id", label="Case/Dispute ID", type="string", width_default=220),
  ColumnMeta(name="kind", label="Kind", type="string", width_default=120),
  ColumnMeta(name="issue_type", label="Issue type", type="string", width_default=140),
  ColumnMeta(name="status", label="Status", type="string", width_default=140),
  ColumnMeta(name="buyer_username", label="Buyer", type="string", width_default=200),
  ColumnMeta(name="order_id", label="Order ID", type="string", width_default=200),
  ColumnMeta(name="amount", label="Amount", type="money", width_default=120),
  ColumnMeta(name="currency", label="Currency", type="string", width_default=80),
  ColumnMeta(name="respond_by_date", label="Respond by", type="datetime", width_default=180),
  ColumnMeta(name="ebay_user_id", label="eBay user ID", type="string", width_default=220),
  # Normalized Post-Order case fields (ebay_cases)
  ColumnMeta(name="item_id", label="Item ID", type=" string", width_default=200),
  ColumnMeta(name="transaction_id", label="Transaction ID", type="string", width_default=220),
  ColumnMeta(name="case_status_enum", label="Case status (API)", type="string", width_default=160),
  ColumnMeta(name="creation_date_api", label="Created (API)", type="datetime", width_default=200),
  ColumnMeta(name="last_modified_date_api", label="Updated (API)", type="datetime", width_default=200),
]
```

And we updated the default visible columns for the `cases` grid so that
`ebay_user_id` is shown by default:

```py path=/C:/Users/filip/.gemini/antigravity/playground/silent-spirit/backend/app/routers/grid_layouts.py start=346
"cases": {
    "visible_columns": [
        "open_date",
        "external_id",
        "kind",
        "issue_type",
        "status",
        "buyer_username",
        "order_id",
        "amount",
        "currency",
        "respond_by_date",
        "ebay_user_id",
    ],
    "sort": {"column": "open_date", "direction": "desc"},
},
```

As a result, the **Cases & Disputes** grid displays eBay user IDs instead of
raw account IDs, while still retaining the latter in the data payload for
potential joins.


## 5. Existing docs and where to look next

- **`docs/CASES_NORMALIZATION.md`** – high-level documentation of the
  `ebay_cases` schema, JSON mappings, and how to run the cases worker.
- **`backend/app/services/postgres_ebay_database.py`** – low-level SQL-based
  persistence logic for eBay data (orders, disputes, cases, finances, etc.).
- **`backend/app/services/ebay.py`** – high-level eBay API orchestration and
  sync jobs (orders, finances, offers, messages, cases, etc.).
- **`backend/app/services/ebay_workers/*_worker.py`** – per-API workers used by
  the background scheduler and by admin/worker endpoints.
- **`backend/app/routers/grids_data.py` + `grid_layouts.py`** – backends for
  all DataGrid-based admin pages.
- **`frontend/src/pages/AdminDbExplorerPage.tsx`** – bespoke UI for the DB
  Explorer; uses simple `<table>` markup and now has sticky, resizable
  headers.

This session introduced the key plumbing to treat Post-Order cases as
first-class, normalized entities in the database and UI, while keeping the raw
`case_data` JSON for archival and advanced debugging. Future work (if needed)
can build on this to join cases to messages, orders, finances, and shipping
modules via `item_id`, `transaction_id`, `order_id`, and `ebay_user_id`.
