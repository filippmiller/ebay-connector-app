# Messages normalization and ingestion (eBay Trading GetMyMessages)

This document explains how **eBay messages** are stored, parsed, normalized and
synced into Postgres/Supabase. It is written for a new agent who needs to extend
or debug the Messages subsystem.

The focus is on:

- The `public.ebay_messages` table (Postgres/Supabase).
- The SQLAlchemy model `Message` in `app.models_sqlalchemy.models`.
- The email/HTML parsers that build `parsed_body` and `parsed_body.normalized`.
- The Trading API worker `EbayService.sync_all_messages` that fills the table.
- The backfill script used to re-parse historical messages.

> NOTE: There is also an older **SQLite**-based Messages implementation
> (`app.db_models.Message`, `app/routers/messages.py`). That code powers the
> existing `/messages` UI, but it **does not** touch Supabase directly. The
> normalized pipeline described here is the Postgres/Supabase side that we use
> for cross-linking with cases, returns, disputes and finances.

---

## 1. Storage: public.ebay_messages (Postgres/Supabase)

### 1.1. Core columns

The canonical storage for eBay messages in Postgres is the `public.ebay_messages`
table. Its SQLAlchemy model lives in `backend/app/models_sqlalchemy/models.py` as
`class Message`.

Key columns (simplified):

- **Identity & account context**
  - `id :: varchar(36)` — primary key (UUID string).
  - `ebay_account_id :: varchar(36)` — FK to `ebay_accounts.id`.
  - `user_id :: varchar(36)` — FK to `users.id` (org user owning this account).
  - `house_name :: text` — human-friendly mailbox / account alias.

- **Message identifiers**
  - `message_id :: varchar(100)` — eBay/Gmail message id (unique per account+user).
  - `thread_id :: varchar(100)` — thread id (often `externalmessageid` from Trading API).

- **Participants & content**
  - `sender_username :: varchar(100)` — eBay sender username.
  - `recipient_username :: varchar(100)` — eBay recipient username.
  - `subject :: text` — subject line.
  - `body :: text` — HTML or plain text body as returned by GetMyMessages.
  - `message_type :: varchar(50)` — coarse type (`MEMBER_MESSAGE`, etc.).

- **Flags and direction**
  - `is_read :: boolean` — whether the message is read.
  - `is_flagged :: boolean` — flagged/starred.
  - `is_archived :: boolean` — archived.
  - `direction :: varchar(20)` — `INCOMING` / `OUTGOING` / `SYSTEM` (today mostly `INCOMING`).

- **Timestamps**
  - `message_date :: timestamptz` — parsed `ReceiveDate` from Trading API.
  - `message_at :: timestamptz` — **canonical** timestamp, filled by the worker
    (today equal to `message_date`, but intended as future-proof canonical field).
  - `read_date :: timestamptz` — when the message was marked as read in the app.
  - `created_at :: timestamptz` — when row was inserted into DB.
  - `updated_at :: timestamptz` — last update timestamp.

- **Order / item linkage**
  - `order_id :: varchar(100)` — eBay order id (e.g. `12-12345-67890`).
  - `listing_id :: varchar(100)` — canonical eBay `itemId` if available.

- **Raw + parsed body**
  - `raw_data :: text` — raw dict/string representation of the Trading API payload
    (for debugging/audit).
  - `parsed_body :: jsonb` — structured representation of the message, built by
    the HTML parsers (see below). This contains both legacy keys and a new
    `normalized` block.

### 1.2. Case / dispute linkage and classification

To support cross-linking with cases, returns, disputes and finances we added
normalized case/dispute fields and message classification flags:

- **Case/dispute linkage**
  - `case_id :: text` — Post-Order case id; should match `ebay_cases.case_id` when present.
  - `case_type :: text` — coarse case type (`CASE`, `RETURN`, `PAYMENT_DISPUTE`, etc.).
  - `inquiry_id :: text` — inquiry id (`INR` etc.), if present in message.
  - `return_id :: text` — return id from eBay (post-order return).
  - `payment_dispute_id :: text` — payment dispute id.
  - `transaction_id :: text` — transaction id (links to finances/transactions).

- **Classification**
  - `is_case_related :: boolean NOT NULL DEFAULT false` — true if message is
    about case/return/inquiry/payment dispute (not a generic system/order mail).
  - `message_topic :: text` — high-level category inferred from text:
    - `CASE`, `RETURN`, `INQUIRY`, `PAYMENT_DISPUTE`, `ORDER`, `OFFER`, `SYSTEM`, `OTHER`, ...
  - `case_event_type :: text` — finer-grained event type (`CASE_OPENED`, `CASE_CLOSED`,
    `RETURN_OPENED`, `REMINDER`, etc.; to be refined as parsers improve).

### 1.3. Attachments, preview and normalized time

- **Attachments**
  - `has_attachments :: boolean NOT NULL DEFAULT false` — true if we found
    any attachments/links (images, PDFs, etc.) in the normalized view.
  - `attachments_meta :: jsonb NOT NULL DEFAULT '[]'::jsonb` — list of attachment
    objects with fields like:
    - `kind` — `IMAGE`, `PDF`, `LINK`, `OTHER`.
    - `name`, `mimeType`, `size`, `url` — metadata for files or EPS/HTTP links.

- **Preview**
  - `preview_text :: text` — short preview (обычно последний реплай без длинной цитаты). Может
    приходить либо из rich‑парсера (`ParsedBody.previewText`), либо из
    `normalized.summaryText`.

- **Canonical timestamptz**
  - `message_at :: timestamptz` добавлен как потенциально каноническое поле; сейчас
    в воркере он заполняется равным `message_date`, но это отдельное поле на тот случай,
    если когда-нибудь потребуется другой источник тайминга.

### 1.4. Индексы

Основные индексы (по ORM и миграциям):

- `idx_ebay_messages_account_id (ebay_account_id)`
- `idx_ebay_messages_user_id (user_id)`
- `idx_ebay_messages_message_id (message_id)`
- `idx_ebay_messages_thread_id (thread_id)`
- `idx_ebay_messages_is_read (is_read)`
- `idx_ebay_messages_message_date (message_date)`
- Новые:
  - `idx_ebay_messages_case_id (case_id)`
  - `idx_ebay_messages_transaction_id (transaction_id)`
  - `idx_ebay_messages_listing_id (listing_id)`
  - `idx_ebay_messages_order_id (order_id)`
  - `idx_ebay_messages_user_account_case_at (user_id, ebay_account_id, case_id, message_date)`

---

## 2. SQLAlchemy model: app.models_sqlalchemy.models.Message

The Postgres `ebay_messages` table is mapped by `Message` in
`backend/app/models_sqlalchemy/models.py`.

Key excerpt (simplified to fields relevant for normalization):

```python
class Message(Base):
    __tablename__ = "ebay_messages"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    ebay_account_id = Column(String(36), ForeignKey('ebay_accounts.id', ondelete='CASCADE'), nullable=False)
    house_name = Column(Text, nullable=True)
    user_id = Column(String(36), ForeignKey('users.id'), nullable=False)
    message_id = Column(String(100), nullable=False)
    thread_id = Column(String(100), nullable=True)
    sender_username = Column(String(100), nullable=True)
    recipient_username = Column(String(100), nullable=True)
    subject = Column(Text, nullable=True)
    body = Column(Text, nullable=True)
    message_type = Column(String(50), nullable=True)

    # Flags and direction
    is_read = Column(Boolean, default=False)
    is_flagged = Column(Boolean, default=False)
    is_archived = Column(Boolean, default=False)
    direction = Column(String(20), nullable=True)

    # Timestamps
    message_date = Column(DateTime(timezone=True), nullable=True)
    message_at = Column(DateTime(timezone=True), nullable=True)
    read_date = Column(DateTime(timezone=True), nullable=True)

    # Order / item linkage
    order_id = Column(String(100), nullable=True)
    listing_id = Column(String(100), nullable=True)

    # Case / dispute linkage
    case_id = Column(Text, nullable=True)
    case_type = Column(Text, nullable=True)
    inquiry_id = Column(Text, nullable=True)
    return_id = Column(Text, nullable=True)
    payment_dispute_id = Column(Text, nullable=True)
    transaction_id = Column(Text, nullable=True)

    # Classification and topic
    is_case_related = Column(Boolean, nullable=False, default=False)
    message_topic = Column(Text, nullable=True)
    case_event_type = Column(Text, nullable=True)

    # Raw + parsed
    raw_data = Column(Text, nullable=True)
    parsed_body = Column(JSONB, nullable=True)

    # Attachments and preview
    has_attachments = Column(Boolean, nullable=False, default=False)
    attachments_meta = Column(JSONB, nullable=False, default=list)
    preview_text = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
```

This model is the **only** one that should be used when working with Postgres
`ebay_messages` (workers, admin endpoints, new APIs). The older SQLite message
model is separate and lives under `app.db_models`.

---

## 3. HTML parsing: message_body_parser and message_parser

We have two complementary parsers for eBay message HTML:

1. `app/services/message_parser.py` — rich parser used for UI threads.
2. `app/ebay/message_body_parser.py` — text + normalized parser used for
   normalized fields and case/order linking.

### 3.1. message_parser.parse_ebay_message_html (rich view)

- Input: `raw_html: str`, `our_account_username: Optional[str]`.
- Output: `ParsedBody` Pydantic model with fields:
  - `order` — includes `orderNumber`, `itemId`, `transactionId`, `title`, `imageUrl`, `itemUrl`, `status`, `viewOrderUrl`.
  - `history` / `currentMessage` — list of message parts with `direction`, `text`, `html`, `sentAt`, etc.
  - `previewText` — short text preview from the most recent part.
  - `richHtml` — sanitized HTML of the relevant message body.

This parser does **not** know about cases/returns/disputes; it is mainly for
building a readable message thread and preview for UI.

The result is converted to JSON via `.dict(exclude_none=True)` and stored in
`parsed_body` when available.

### 3.2. message_body_parser.parse_ebay_message_body (normalized view)

File: `backend/app/ebay/message_body_parser.py`.

- Input: `html: str`, `our_account_username: str`.
- Output: `Dict[str, Any]` with at least:
  - `buyer`, `currentMessage`, `history`, `order`, `meta` (legacy keys).
  - `normalized` — **new** block containing normalized identifiers and
    classification used to drive DB columns.

Important behavior:

- Extracts order/item/transaction information from `area7Container` (eBay layout).
- Extracts buyer username and feedback score.
- Classifies topic (CASE/RETURN/INQUIRY/PAYMENT_DISPUTE/ORDER/OFFER/OTHER)
  and subtype (currently `INR` for Item Not Received).
- Fills `normalized.orderId`, `normalized.itemId`, `normalized.transactionId`.
- Fills `normalized.buyerUsername` and `normalized.sellerUsername`.
- Fills `normalized.summaryText` from the latest inbound message.
- Has placeholders for and **tries** to populate:
  - `normalized.caseId`, `normalized.returnId`, `normalized.paymentDisputeId`.
  - `normalized.respondBy`, `normalized.amount`, `normalized.currency`.
  - `normalized.attachments` — list of structured attachments.

Any fields that cannot be reliably detected are left as `null` or omitted; this
ensures parsers are robust and ingestion never fails due to parsing issues.

---

## 4. Trading API Messages worker: EbayService.sync_all_messages

The Trading API worker is implemented in `backend/app/services/ebay.py` as
`EbayService.sync_all_messages`.

### 4.1. High-level flow

1. **Input parameters**:
   - `user_id` — org user id.
   - `access_token` — eBay OAuth token for the account.
   - `run_id` — optional run id for sync logs.
   - `ebay_account_id`, `ebay_user_id` — account context.
   - `window_from`, `window_to` — ISO timestamps for time window (passed through
     to headers calls).

2. **Logging & job management**:
   - Uses `SyncEventLogger` (`app/services/sync_event_logger.py`) to log start,
     progress, HTTP requests and completion.
   - Registers a sync job in Postgres using `ebay_db.create_sync_job`.

3. **Folder discovery**:
   - Calls `get_message_folders(access_token)` (Trading API GetMyMessages with
     `ReturnSummary` mode).
   - Builds `folder_specs` list that always includes:
     - `Inbox (0)`
     - `Sent (1)`
     - plus any custom folders from summary.

4. **Header pagination per folder**:
   - For each folder in `folder_specs`:
     - Paginate via `get_message_headers(access_token, folder_id, page_number, entries_per_page, start_time_from, start_time_to)`.
     - Collect `message_ids` and `alert_ids` into `all_message_ids`.

5. **Bodies in batches of 10**:
   - Split `all_message_ids` into batches of size `MESSAGES_BODIES_BATCH` (10).
   - For each batch, call `get_message_bodies(access_token, batch_ids)`.
   - For each returned message dict, build a `SqlMessage` row in `ebay_messages`.

6. **Idempotence**:
   - For each message, check if a row already exists:

     ```python
     existing = (
         db_session.query(SqlMessage)
         .filter(
             SqlMessage.message_id == message_id,
             SqlMessage.user_id == user_id,
             SqlMessage.ebay_account_id == ebay_account_id,
         )
         .first()
     )
     if existing:
         continue
     ```

7. **Finalization**:
   - On success: marks job as `completed`, logs summary.
   - On failure: logs error and marks job as `failed`.

### 4.2. Enrichment and column mapping

The most important part for normalization is how we transform HTML into
`parsed_body` and columns on `SqlMessage`.

**Step 1 — compute `message_date`**

```python
receive_date_str = msg.get("receivedate", "")
message_date = datetime.utcnow()
if receive_date_str:
    try:
        message_date = datetime.fromisoformat(receive_date_str.replace("Z", "+00:00"))
    except Exception:
        pass
```

**Step 2 — run rich parser**

```python
body_html = msg.get("text", "") or ""
parsed_body = None
normalized = {}
preview_text = None
listing_id = msg.get("itemid")
order_id = None
transaction_id = None
is_case_related = False
message_topic = None
case_event_type = None
has_attachments = False
attachments_meta = []

try:
    if body_html:
        parsed = parse_ebay_message_html(
            body_html,
            our_account_username=ebay_user_id or "seller",
        )
        parsed_body = parsed.dict(exclude_none=True)
        preview_text = parsed.previewText or None
except Exception as parse_err:
    logger.warning(
        f"Failed to parse eBay message body for {message_id} via rich parser: {parse_err}"
    )
```

**Step 3 — run normalized parser and merge**

```python
try:
    from app.ebay.message_body_parser import parse_ebay_message_body

    normalized_body = parse_ebay_message_body(
        body_html,
        our_account_username=ebay_user_id or "seller",
    )
    if parsed_body is None:
        parsed_body = normalized_body
    else:
        if normalized_body.get("normalized"):
            parsed_body["normalized"] = normalized_body["normalized"]

    norm = normalized_body.get("normalized") or {}
    normalized = norm
    # Map normalized fields into dedicated columns when present.
    order_id = norm.get("orderId") or order_id
    listing_id = norm.get("itemId") or listing_id
    transaction_id = norm.get("transactionId") or transaction_id

    message_topic = norm.get("topic") or None
    case_event_type = norm.get("caseEventType") or None
    # CASE/RETURN/INQUIRY/PAYMENT_DISPUTE → is_case_related
    if message_topic in {"CASE", "RETURN", "INQUIRY", "PAYMENT_DISPUTE"}:
        is_case_related = True

    # Attachments → attachments_meta
    attachments = norm.get("attachments") or []
    if isinstance(attachments, list) and attachments:
        has_attachments = True
        attachments_meta = attachments

    # Prefer normalized summaryText as preview when available.
    if norm.get("summaryText"):
        preview_text = norm.get("summaryText")
except Exception as parse_err:
    logger.warning(
        f"Failed to build normalized view for eBay message {message_id}: {parse_err}"
    )
```

**Step 4 — construct `SqlMessage`**

```python
db_message = SqlMessage(
    ebay_account_id=ebay_account_id,
    user_id=user_id,
    message_id=message_id,
    thread_id=msg.get("externalmessageid") or message_id,
    sender_username=sender,
    recipient_username=recipient,
    subject=msg.get("subject", ""),
    body=body_html,
    message_type="MEMBER_MESSAGE",
    is_read=msg.get("read", False),
    is_flagged=msg.get("flagged", False),
    is_archived=msg.get("folderid") == "2",
    direction=direction,
    message_date=message_date,
    message_at=message_date,
    order_id=order_id,
    listing_id=listing_id,
    case_id=normalized.get("caseId"),
    case_type=normalized.get("caseType"),
    inquiry_id=normalized.get("inquiryId"),
    return_id=normalized.get("ReturnId"),
    payment_dispute_id=normalized.get("paymentDisputeId"),
    transaction_id=transaction_id,
    is_case_related=is_case_related,
    message_topic=message_topic,
    case_event_type=case_event_type,
    raw_data=str(msg),
    parsed_body=parsed_body,
    has_attachments=has_attachments,
    attachments_meta=attachments_meta,
    preview_text=preview_text,
)
db_session.add(db_message)
```

> NOTE: there is a small detail where `return_id` is currently mapped from
> `normalized.get("ReturnId")` (capital `R`) — this is a typo and can be easily
> corrected to `"returnId"` once the parser is updated to fill that field.

---

## 5. Backfill: scripts/backfill_parsed_ebay_messages.py

The backfill script is used to re-parse **existing** `ebay_messages` rows and
populate new fields (`parsed_body.normalized`, `case_id`, `transaction_id`,
`message_topic`, `preview_text`, `attachments_meta`, etc.).

- Location: `backend/scripts/backfill_parsed_ebay_messages.py`.
- Run from `backend/` directory with:

```bash
cd backend
python scripts/backfill_parsed_ebay_messages.py
```

The script:

1. Reads `DATABASE_URL` (must point at the Supabase/Postgres instance).
2. Computes how many rows need work (based on `parsed_body`/`case_id`/
   `transaction_id`/`message_topic`/`preview_text` being `NULL`).
3. Batches over messages by `created_at` (size `BATCH_SIZE = 500`).
4. For each row:
   - Runs both `parse_ebay_message_html` and `parse_ebay_message_body`.
   - Merges normalized block into `parsed_body`.
   - Fills any missing normalized columns only when they are currently `NULL`.
   - Logs warnings for parse errors but continues.
5. Logs per-batch progress and a final summary.

Use this script after changing parsers or adding new normalized fields to
retrofit history.

---

## 6. How to use this for cross-linking

With the new schema and worker behavior, Messages can be cross-linked with
cases/returns/disputes and finances as follows:

- **Messages → Cases**
  - `ebay_messages.case_id` matches `ebay_cases.case_id`.
  - `ebay_messages.transaction_id` can be used to find the same case by
    transaction or to join to finances transactions.

- **Cases → Messages**

```sql
SELECT m.*
FROM ebay_messages m
WHERE m.case_id = :case_id
ORDER BY COALESCE(m.message_at, m.message_date);
```

- **Messages → Returns / Payment disputes**
  - `return_id` and `payment_dispute_id` can be used in a similar way once
    corresponding tables exist (`returns`, `payment_disputes`, etc.).

- **Classification for UI**
  - Use `message_topic` and `is_case_related` to drive filters in Messages grids
    (e.g. show only dispute/return/inquiry messages).
  - Use `preview_text` in the grid for a concise summary of the latest reply.

---

## 7. Things to keep in mind when extending

1. **There are two message stacks**:
   - **SQLite** stack (`app.db_models.Message`, `app/routers/messages.py`): powers
     current `/messages` UI but does not know about Supabase or normalized
     fields.
   - **Postgres/Supabase** stack (`app.models_sqlalchemy.models.Message`,
     `EbayService.sync_all_messages`, `backfill_parsed_ebay_messages.py`): this
     is the normalized, future-proof path and the one to extend.

2. **Adding new normalized fields**:
   - Add them to Alembic migration(s) on `ebay_messages`.
   - Extend `Message` SQLAlchemy model with matching columns.
   - Update `message_body_parser` to populate them in `normalized`.
   - Wire them into `sync_all_messages` (map from `normalized` → columns).
   - Update the backfill script if you want to retrofit history.

3. **Parser robustness**:
   - All parsers must be best-effort and never raise unhandled exceptions.
   - Missing fields should result in `null`/absent keys, not a broken ingestion.

4. **Cross-linking expectations**:
   - `case_id`, `transaction_id`, `return_id`, `payment_dispute_id` are the key
     “joins” into `ebay_cases`, returns, disputes and finances.
   - UI code should prefer these **normalized columns** over ad-hoc JSON parsing
     of `parsed_body`.

5. **Logs**:
   - Worker logs (`SyncEventLogger`) include per-run summaries:
     - `total_fetched`, `total_stored`, time window, etc.
   - Backfill logs show how many messages were processed and updated.

If you are a new agent picking this up, start by:

1. Skimming `app/ebay/message_body_parser.py` to understand current heuristics.
2. Skimming `EbayService.sync_all_messages` to see exactly how columns are
   filled from `normalized`.
3. Running `scripts/backfill_parsed_ebay_messages.py` against a dev database
   once you adjust parsers or schema.
4. Using `SELECT * FROM ebay_messages WHERE is_case_related = true` to
   inspect real-world samples and refine the parsing logic.
