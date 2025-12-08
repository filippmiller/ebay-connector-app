from __future__ import annotations

from typing import Dict, Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, asc, or_
from sqlalchemy.orm import Session
from sqlalchemy.sql import text as sa_text
import enum

from app.database import get_db
from app.db_models import Order, OrderLineItem, Transaction as EbayLegacyTransaction
from app.models_sqlalchemy import get_db as get_db_sqla
from app.models_sqlalchemy.models import (
    Message as EbayMessage,
    Offer as OfferModel,
    OfferState,
    OfferDirection,
    ActiveInventory,
    Purchase,
    AccountingBankStatement,
    AccountingCashExpense,
    AccountingTransaction as AccountingTxn,
    SqItem,
    TblPartsInventory,
    EbaySnipe,
)
from app.services.auth import get_current_user
from app.models.user import User as UserModel
from app.routers.grid_layouts import _allowed_columns_for_grid

router = APIRouter(prefix="/api/grids", tags=["grids_data"])


@router.get("/inventory/statuses")
async def get_inventory_statuses(db: Session = Depends(get_db)):
    """Expose inventory status list (id, label, color) for filters/dropdowns."""
    try:
        sql = sa_text(
            'SELECT "InventoryStatus_ID" AS id, "InventoryShortStatus_Name" AS label, "Color" AS color '
            'FROM "tbl_parts_inventorystatus" ORDER BY "InventoryStatus_ID"'
        )
        result = db.execute(sql)
        items = []
        for row in result:
            items.append(
                {
                    "id": int(row.id),
                    "label": str(row.label) if row.label is not None else "",
                    "color": str(row.color) if row.color is not None else None,
                }
            )
        return {"items": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load statuses: {e}")


@router.get("/cases/detail")
async def get_case_detail(
    kind: str = Query(..., description="Entity kind: inquiry | postorder_case | payment_dispute"),
    external_id: str = Query(..., alias="id", description="External id: inquiryId / caseId / disputeId"),
    current_user: UserModel = Depends(get_current_user),
):
    """Return a single unified case/dispute/inquiry row plus messages and events.

    This endpoint reuses the unified Cases grid projection so that the
    "entity" payload matches a row from the /api/grids/cases grid. It then
    augments it with related ebay_messages and ebay_events rows.
    """
    db_sqla = next(get_db_sqla())
    try:
        # 1) Fetch unified entity row via the same projection as the Cases grid.
        from app.models_sqlalchemy.models import Message as EbayMessage, EbayEvent

        selected_cols = _allowed_columns_for_grid("cases")
        data = _get_cases_data(
            db_sqla,
            current_user,
            selected_cols,
            limit=1,
            offset=0,
            sort_column=None,
            sort_dir="desc",
            state=None,
            buyer=None,
            from_date=None,
            to_date=None,
            kind_filter=kind,
            external_id_filter=external_id,
        )
        rows = data.get("rows") or []
        if not rows:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case/inquiry/dispute not found")

        entity = rows[0]

        # 2) Load related messages from ebay_messages.
        messages: List[Dict[str, Any]] = []
        try:
            from datetime import datetime as dt_type
            from decimal import Decimal

            q = db_sqla.query(EbayMessage).filter(EbayMessage.user_id == current_user.id)

            if kind == "inquiry":
                q = q.filter(
                    or_(
                        EbayMessage.inquiry_id == external_id,
                        EbayMessage.order_id == entity.get("order_id"),
                    )
                )
            elif kind == "postorder_case":
                q = q.filter(
                    or_(
                        EbayMessage.case_id == external_id,
                        EbayMessage.order_id == entity.get("order_id"),
                    )
                )
            elif kind == "payment_dispute":
                q = q.filter(
                    or_(
                        EbayMessage.payment_dispute_id == external_id,
                        EbayMessage.order_id == entity.get("order_id"),
                    )
                )

            q = q.order_by(EbayMessage.message_date.desc())
            rows_msg: List[EbayMessage] = q.limit(500).all()

            def _ser_msg(m: EbayMessage) -> Dict[str, Any]:
                out: Dict[str, Any] = {}
                for attr in [
                    "id",
                    "message_id",
                    "thread_id",
                    "sender_username",
                    "recipient_username",
                    "subject",
                    "body",
                    "message_type",
                    "direction",
                    "is_read",
                    "is_flagged",
                    "is_archived",
                    "order_id",
                    "listing_id",
                    "case_id",
                    "inquiry_id",
                    "return_id",
                    "payment_dispute_id",
                    "transaction_id",
                    "message_topic",
                    "case_event_type",
                    "preview_text",
                ]:
                    val = getattr(m, attr, None)
                    if isinstance(val, dt_type):
                        out[attr] = val.isoformat()
                    elif isinstance(val, Decimal):
                        out[attr] = float(val)
                    else:
                        out[attr] = val
                out["message_date"] = m.message_date.isoformat() if m.message_date else None
                out["message_at"] = m.message_at.isoformat() if getattr(m, "message_at", None) else None
                out["has_attachments"] = bool(getattr(m, "has_attachments", False))
                out["attachments_meta"] = getattr(m, "attachments_meta", None)
                return out

            messages = [_ser_msg(m) for m in rows_msg]
        except Exception:
            messages = []

        # 3) Load related events from ebay_events.
        events: List[Dict[str, Any]] = []
        try:
            from datetime import datetime as dt_type

            entity_type = None
            if kind == "inquiry":
                entity_type = "INQUIRY"
            elif kind == "postorder_case":
                entity_type = "CASE"
            elif kind == "payment_dispute":
                entity_type = "DISPUTE"

            ev_q = db_sqla.query(EbayEvent)
            if entity_type:
                ev_q = ev_q.filter(EbayEvent.entity_type == entity_type)
            ev_q = ev_q.filter(EbayEvent.entity_id == external_id)

            account_key = entity.get("ebay_user_id") or entity.get("ebay_account_id")
            if account_key:
                ev_q = ev_q.filter(EbayEvent.ebay_account == account_key)

            ev_q = ev_q.order_by(EbayEvent.event_time.asc().nulls_last(), EbayEvent.created_at.asc())
            rows_ev: List[EbayEvent] = ev_q.limit(500).all()

            for ev in rows_ev:
                item: Dict[str, Any] = {
                    "id": ev.id,
                    "source": ev.source,
                    "channel": ev.channel,
                    "topic": ev.topic,
                    "entity_type": ev.entity_type,
                    "entity_id": ev.entity_id,
                    "ebay_account": ev.ebay_account,
                }
                for fn in ["event_time", "publish_time", "created_at", "processed_at"]:
                    dtv = getattr(ev, fn, None)
                    if isinstance(dtv, dt_type):
                        item[fn] = dtv.isoformat()
                    else:
                        item[fn] = None
                item["status"] = ev.status
                item["error"] = ev.error
                item["headers"] = ev.headers
                item["payload"] = ev.payload
                events.append(item)
        except Exception:
            events = []

        return {
            "entity": entity,
            "messages": messages,
            "events": events,
        }
    finally:
        db_sqla.close()


@router.get("/buying/rows")
async def get_buying_rows(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    sort_by: Optional[str] = Query("id"),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    # Filters
    buyer_id: Optional[str] = Query(None),
    status_id: Optional[int] = Query(None),
    paid_from: Optional[str] = Query(None),
    paid_to: Optional[str] = Query(None),
    created_from: Optional[str] = Query(None),
    created_to: Optional[str] = Query(None),
    seller_id: Optional[str] = Query(None),
    storage_mode: Optional[str] = Query(None, description="any|exact|section"),
    storage_value: Optional[str] = Query(None),
    title: Optional[str] = Query(None),
    tracking_number: Optional[str] = Query(None),
    item_id: Optional[str] = Query(None),
    id_filter: Optional[str] = Query(None, alias="id"),
    current_user: UserModel = Depends(get_current_user),
):
    """Specialized endpoint for the BUYING grid rows.

    Thin wrapper around :func:`_get_buying_data` that adapts pagination to the
    explicit ``page`` / ``page_size`` contract expected by the new BUYING tab.
    """
    db_sqla = next(get_db_sqla())
    try:
        from app.routers.grid_layouts import _allowed_columns_for_grid

        selected_cols = _allowed_columns_for_grid("buying")
        offset = (page - 1) * page_size
        data = _get_buying_data(
            db_sqla,
            current_user,
            selected_cols,
            page_size,
            offset,
            sort_by,
            sort_dir,
            # Pass filters
            buyer_id=buyer_id,
            status_id=status_id,
            paid_from=paid_from,
            paid_to=paid_to,
            created_from=created_from,
            created_to=created_to,
            seller_id=seller_id,
            storage_mode=storage_mode,
            storage_value=storage_value,
            title=title,
            tracking_number=tracking_number,
            item_id=item_id,
            id_filter=id_filter,
        )
        return {
            "rows": data.get("rows", []),
            "total": data.get("total", 0),
            "page": page,
            "page_size": page_size,
        }
    finally:
        db_sqla.close()


@router.get("/buying/{buyer_id}/logs")
async def get_buying_logs(
    buyer_id: int,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db_sqla),
):
    """Return status/comment change logs for a BUYING row (tbl_ebay_buyer_log)."""
    sql = sa_text(
        """
        SELECT
            l."ID" AS id,
            l."ChangeType" AS change_type,
            l."OldStatusID" AS old_status_id,
            l."NewStatusID" AS new_status_id,
            l."OldComment" AS old_comment,
            l."NewComment" AS new_comment,
            l."ChangedByUserName" AS changed_by_username,
            l."ChangedAt" AS changed_at,
            sb_old."StatusName" AS old_status_label,
            sb_new."StatusName" AS new_status_label
        FROM "tbl_ebay_buyer_log" l
        JOIN "tbl_ebay_buyer" b ON l."EbayBuyerID" = b."ID"
        JOIN ebay_accounts ea ON b."EbayAccountID" = ea.id
        LEFT JOIN (SELECT DISTINCT "Status", "StatusName" FROM "tbl_ebay_status_buyer") sb_old ON l."OldStatusID" = sb_old."Status"
        LEFT JOIN (SELECT DISTINCT "Status", "StatusName" FROM "tbl_ebay_status_buyer") sb_new ON l."NewStatusID" = sb_new."Status"
        WHERE l."EbayBuyerID" = :buyer_id
          AND ea.org_id = :org_id
        ORDER BY l."ChangedAt" DESC, l."ID" DESC
        """
    )
    rows = db.execute(sql, {"buyer_id": buyer_id, "org_id": current_user.id}).fetchall()
    logs = []
    for r in rows:
        item: Dict[str, Any] = {}
        for key in [
            "id",
            "change_type",
            "old_status_id",
            "new_status_id",
            "old_comment",
            "new_comment",
            "changed_by_username",
            "old_status_label",
            "new_status_label",
        ]:
            item[key] = getattr(r, key, None)
        dtv = getattr(r, "changed_at", None)
        if isinstance(dtv, dt_type):
            item["changed_at"] = dtv.isoformat()
        else:
            item["changed_at"] = None
        logs.append(item)
    return {"logs": logs}


@router.get("/{grid_key}/data")
async def get_grid_data(
    grid_key: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    sort_by: Optional[str] = Query(None),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    columns: Optional[str] = Query(None, description="Comma-separated list of columns to include"),
    # Offers-specific filters (mirroring /offers) and reused for sniper status filter
    state: Optional[str] = Query(None),
    direction: Optional[str] = Query(None),
    buyer: Optional[str] = Query(None),
    item_id: Optional[str] = Query(None),
    sku: Optional[str] = Query(None),
    ebay_account_id: Optional[str] = Query(None),
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
    # Finances-specific filters
    transaction_type: Optional[str] = Query(None),
    # Finances fees-specific filters
    fee_type: Optional[str] = Query(None),
    # Messages-specific filters (mirroring /messages)
    folder: Optional[str] = Query(None),
    unread_only: bool = False,
    # Accounting / generic filters
    source_type: Optional[str] = Query(None),
    storage_id: Optional[str] = Query(None, alias="storageID"),
    category_id: Optional[int] = Query(None),
    min_amount: Optional[float] = Query(None),
    max_amount: Optional[float] = Query(None),
    account_name: Optional[str] = Query(None),
    is_personal: Optional[bool] = Query(None),
    is_internal_transfer: Optional[bool] = Query(None),
    # Inventory-specific filters
    ebay_status: Optional[str] = Query(None),
    # SKU Catalog specific filters
    model: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    part_number: Optional[str] = Query(None),
    title: Optional[str] = Query(None),
    # Inventory column-specific filters
    inv_id: Optional[str] = Query(None, alias="inv_id"),
    inv_sku: Optional[str] = Query(None, alias="inv_sku"),
    inv_item_id: Optional[str] = Query(None, alias="inv_item_id"),
    inv_title: Optional[str] = Query(None, alias="inv_title"),
    inv_statussku: Optional[str] = Query(None, alias="inv_statussku"),
    inv_storage: Optional[str] = Query(None, alias="inv_storage"),
    inv_serial_number: Optional[str] = Query(None, alias="inv_serial_number"),
    # Buying-specific filters
    buyer_id: Optional[str] = Query(None),
    status_id: Optional[int] = Query(None),
    seller_id: Optional[str] = Query(None),
    tracking_number: Optional[str] = Query(None),
    storage_mode: Optional[str] = Query(None),
    storage_value: Optional[str] = Query(None),
    id_filter: Optional[str] = Query(None, alias="id"),
    search: Optional[str] = None,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Generic grid data endpoint for orders/transactions/messages/offers."""

    allowed_cols = _allowed_columns_for_grid(grid_key)
    if not allowed_cols:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown grid_key")

    requested_cols: List[str]
    if columns:
        requested = [c.strip() for c in columns.split(",") if c.strip()]
        requested_cols = [c for c in requested if c in allowed_cols]
        if not requested_cols:
            requested_cols = allowed_cols
    else:
        requested_cols = allowed_cols

    # Determine default sort column for each grid. We prefer stable identifiers
    # or creation timestamps so that with sort_dir="desc" newest records appear
    # first. When users pick an explicit sort_by, that takes precedence.
    default_sort_col = None
    if grid_key == "orders":
        # Order line items: newest orders first.
        default_sort_col = "created_at"
    elif grid_key == "transactions":
        # Legacy ebay_transactions: fall back to created_at when present.
        default_sort_col = "created_at" if "created_at" in allowed_cols else "transaction_date"
    elif grid_key == "messages":
        default_sort_col = "message_date"
    elif grid_key == "offers":
        default_sort_col = "created_at"
    elif grid_key == "finances":
        default_sort_col = "booking_date"
    elif grid_key == "finances_fees":
        default_sort_col = "created_at"
    elif grid_key == "inventory":
        # Default to the numeric ID column so newest rows (highest IDs)
        # appear first when sort_dir is "desc".
        default_sort_col = "ID"
    elif grid_key == "buying":
        # Buying grid (purchases): newest purchases first.
        # We prefer ID DESC as requested by the user.
        default_sort_col = "id"
    elif grid_key in {"sku_catalog", "active_inventory", "accounting_bank_statements", "accounting_cash_expenses", "accounting_transactions", "ledger_transactions"}:
        # These all have a real numeric/id or primary timestamp column named "id"
        # (or similar) in their ColumnMeta; prefer that when available.
        if "id" in allowed_cols:
            default_sort_col = "id"

    sort_column = sort_by if sort_by in allowed_cols else default_sort_col

    if grid_key == "orders":
        return await _get_orders_data(db, current_user, requested_cols, limit, offset, sort_column, sort_dir)
    elif grid_key == "transactions":
        # Use main DB session and legacy ebay_transactions table
        return _get_transactions_data(db, current_user, requested_cols, limit, offset, sort_column, sort_dir)
    elif grid_key == "messages":
        db_sqla = next(get_db_sqla())
        try:
            return _get_messages_data(
                db_sqla,
                current_user,
                requested_cols,
                limit,
                offset,
                sort_column,
                sort_dir,
                folder=folder,
                unread_only=unread_only,
                search=search,
            )
        finally:
            db_sqla.close()
    elif grid_key == "offers":
        db_sqla = next(get_db_sqla())
        try:
            return _get_offers_data(
                db_sqla,
                current_user,
                requested_cols,
                limit,
                offset,
                sort_column,
                sort_dir,
                state=state,
                direction=direction,
                buyer=buyer,
                item_id=item_id,
                sku=sku,
                from_date=from_date,
                to_date=to_date,
            )
        finally:
            db_sqla.close()
    elif grid_key == "active_inventory":
        db_sqla = next(get_db_sqla())
        try:
            return _get_active_inventory_data(
                db_sqla,
                current_user,
                requested_cols,
                limit,
                offset,
                sort_column,
                sort_dir,
            )
        finally:
            db_sqla.close()
    elif grid_key == "inventory":
        db_sqla = next(get_db_sqla())
        try:
            return _get_inventory_data(
                db_sqla,
                current_user,
                requested_cols,
                limit,
                offset,
                sort_column,
                sort_dir,
                storage_id=storage_id,
                ebay_status=ebay_status,
                search=search,
                inv_id=inv_id,
                inv_sku=inv_sku,
                inv_item_id=inv_item_id,
                inv_title=inv_title,
                inv_statussku=inv_statussku,
                inv_storage=inv_storage,
                inv_serial_number=inv_serial_number,
            )
        finally:
            db_sqla.close()
    elif grid_key == "sniper_snipes":
        db_sqla = next(get_db_sqla())
        try:
            return _get_sniper_snipes_data(
                db_sqla,
                current_user,
                requested_cols,
                limit,
                offset,
                sort_column,
                sort_dir,
                status_filter=state,
                ebay_account_id=ebay_account_id,
                search=search,
            )
        finally:
            db_sqla.close()
    elif grid_key == "cases":
        # Cases & disputes live in the Postgres-backed ebay_cases / ebay_disputes
        # tables, so we must use the SQLAlchemy session from app.models_sqlalchemy.
        db_sqla = next(get_db_sqla())
        try:
            return _get_cases_data(
                db_sqla,
                current_user,
                requested_cols,
                limit,
                offset,
                sort_column,
                sort_dir,
                state=state,
                buyer=buyer,
                from_date=from_date,
                to_date=to_date,
            )
        finally:
            db_sqla.close()
    elif grid_key == "finances":
        # Finances transactions live in ebay_finances_transactions / ebay_finances_fees
        # and are always backed by the Postgres SQLAlchemy session.
        db_sqla = next(get_db_sqla())
        try:
            return _get_finances_data(
                db_sqla,
                current_user,
                requested_cols,
                limit,
                offset,
                sort_column,
                sort_dir,
                transaction_type=transaction_type,
                from_date=from_date,
                to_date=to_date,
            )
        finally:
            db_sqla.close()
    elif grid_key == "finances_fees":
        # Per-fee breakdown backed directly by ebay_finances_fees.
        db_sqla = next(get_db_sqla())
        try:
            return _get_finances_fees_data(
                db_sqla,
                current_user,
                requested_cols,
                limit,
                offset,
                sort_column,
                sort_dir,
                from_date=from_date,
                to_date=to_date,
                fee_type=fee_type,
                search=search,
            )
        finally:
            db_sqla.close()
    elif grid_key == "buying":
        # Buying grid is backed by the purchases table (derived from tbl_ebay_buyer).
        db_sqla = next(get_db_sqla())
        try:
            return _get_buying_data(
                db_sqla,
                current_user,
                requested_cols,
                limit,
                offset,
                sort_column,
                sort_dir,
                # Buying filter parameters
                buyer_id=buyer_id,
                status_id=status_id,
                paid_from=from_date,
                paid_to=to_date,
                created_from=None,  # No longer used
                created_to=None,  # No longer used
                seller_id=seller_id,
                storage_mode=storage_mode,
                storage_value=storage_value,
                title=title,
                tracking_number=tracking_number,
                item_id=item_id,
                id_filter=id_filter,
            )
        finally:
            db_sqla.close()
    elif grid_key == "sku_catalog":
        # SKU catalog grid backed directly by sku table.
        db_sqla = next(get_db_sqla())
        try:
            return _get_sku_catalog_data(
                db_sqla,
                current_user,
                requested_cols,
                limit,
                offset,
                sort_column,
                sort_dir,
                search=search,
                sku=sku,
                model=model,
                category=category,
                part_number=part_number,
                title=title,
            )
        finally:
            db_sqla.close()
    elif grid_key == "accounting_cash_expenses":
        db_sqla = next(get_db_sqla())
        try:
            return _get_accounting_cash_expenses_data(
                db_sqla,
                current_user,
                requested_cols,
                limit,
                offset,
                sort_column,
                sort_dir,
                date_from=from_date,
                date_to=to_date,
            )
        finally:
            db_sqla.close()
    elif grid_key == "accounting_transactions":
        db_sqla = next(get_db_sqla())
        try:
            return _get_accounting_transactions_grid_data(
                db_sqla,
                current_user,
                requested_cols,
                limit,
                offset,
                sort_column,
                sort_dir,
                date_from=from_date,
                date_to=to_date,
                source_type=source_type,
                storage_id=storage_id,
                category_id=category_id,
                min_amount=min_amount,
                max_amount=max_amount,
                account_name=account_name,
                direction=direction,
                is_personal=is_personal,
                is_internal_transfer=is_internal_transfer,
                search=search,
            )
        finally:
            db_sqla.close()
    elif grid_key == "ledger_transactions":
        # Ledger grid is a thin wrapper over accounting_transactions, but wired
        # as a separate grid_key so that it can evolve independently in the UI
        # (columns, layout, etc.).
        db_sqla = next(get_db_sqla())
        try:
            return _get_accounting_transactions_grid_data(
                db_sqla,
                current_user,
                requested_cols,
                limit,
                offset,
                sort_column,
                sort_dir,
                date_from=from_date,
                date_to=to_date,
                source_type=source_type,
                storage_id=storage_id,
                category_id=category_id,
                min_amount=min_amount,
                max_amount=max_amount,
                account_name=account_name,
                direction=direction,
                is_personal=is_personal,
                is_internal_transfer=is_internal_transfer,
                search=search,
            )
        finally:
            db_sqla.close()

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Grid not implemented yet")


async def _get_orders_data(
    db: Session,
    current_user: UserModel,
    selected_cols: List[str],
    limit: int,
    offset: int,
    sort_column: Optional[str],
    sort_dir: str,
) -> Dict[str, Any]:
    """Minimal Orders grid backed only by public.order_line_items.

    No joins or derived fields – this is designed to be schema-safe and to stop
    500s caused by undefined columns. We can add enrichments later.
    """
    from datetime import datetime as dt_type
    from decimal import Decimal

    # Base query – for now we do not filter by user/account to avoid relying on
    # columns that may not exist in all environments.
    query = db.query(OrderLineItem)

    total = query.count()

    # Allow sorting only on a safe whitelist of real columns.
    allowed_sort_cols = {
        "created_at",
        "order_id",
        "line_item_id",
        "sku",
        "title",
        "quantity",
        "total_value",
        "currency",
    }
    if sort_column in allowed_sort_cols and hasattr(OrderLineItem, sort_column):
        sort_attr = getattr(OrderLineItem, sort_column)
        if sort_dir == "desc":
            query = query.order_by(desc(sort_attr))
        else:
            query = query.order_by(asc(sort_attr))

    rows_db: List[OrderLineItem] = query.offset(offset).limit(limit).all()

    def _serialize(li: OrderLineItem) -> Dict[str, Any]:
        row: Dict[str, Any] = {}
        for col in selected_cols:
            try:
                value = getattr(li, col, None)
                if value is None:
                    # Column doesn't exist or is None - skip it
                    continue
                if isinstance(value, dt_type):
                    row[col] = value.isoformat()
                elif isinstance(value, Decimal):
                    row[col] = float(value)
                else:
                    row[col] = value
            except Exception:
                # Skip columns that cause errors
                continue
        return row

    rows = [_serialize(li) for li in rows_db]

    return {
        "rows": rows,
        "limit": limit,
        "offset": offset,
        "total": total,
        "sort": {"column": sort_column, "direction": sort_dir} if sort_column else None,
    }


def _get_buying_data(
    db: Session,
    current_user: UserModel,
    selected_cols: List[str],
    limit: int,
    offset: int,
    sort_column: Optional[str],
    sort_dir: str,
    # Filters
    buyer_id: Optional[str] = None,
    status_id: Optional[int] = None,
    paid_from: Optional[str] = None,
    paid_to: Optional[str] = None,
    created_from: Optional[str] = None,
    created_to: Optional[str] = None,
    seller_id: Optional[str] = None,
    storage_mode: Optional[str] = None,
    storage_value: Optional[str] = None,
    title: Optional[str] = None,
    tracking_number: Optional[str] = None,
    item_id: Optional[str] = None,
    id_filter: Optional[str] = None,
) -> Dict[str, Any]:
    """Buying grid backed by legacy Supabase table tbl_ebay_buyer (quoted column names).

    Note: tbl_ebay_buyer has no ebay_account FK; we do NOT join ebay_accounts and
    simply return all rows in the table. Upstream auth should already scope access.
    """
    from datetime import datetime as dt_type
    from decimal import Decimal

    # Fixed column names from Supabase (PascalCase / mixed):
    status_id_col = "Status"
    status_label_col = "StatusName"

    # Map allowed sort columns to quoted SQL fragments; default newest by ID.
    sort_map = {
        "paid_time": 'b."PaidTime"',
        "record_created_at": 'b."record_created"',
        "buyer_id": 'b."BuyerID"',
        "seller_id": 'b."SellerID"',
        "profit": 'b."Profit"',
        "id": 'b."ID"',
    }
    sort_col_sql = sort_map.get((sort_column or "").lower(), 'b."ID"')
    sort_dir_sql = "asc" if (sort_dir or "").lower() == "asc" else "desc"

    # Building filters
    filters = []
    params = {"limit": limit, "offset": offset}

    if buyer_id:
        filters.append('b."BuyerID" = :buyer_id')
        params["buyer_id"] = buyer_id
    
    if status_id is not None:
        filters.append('b."ItemStatus" = :status_id')
        params["status_id"] = status_id
    
    if seller_id:
        filters.append('b."SellerID" ILIKE :seller_id')
        params["seller_id"] = f"%{seller_id}%"

    if title:
        filters.append('b."Title" ILIKE :title')
        params["title"] = f"%{title}%"

    if tracking_number:
        filters.append('b."TrackingNumber" ILIKE :tracking_number')
        params["tracking_number"] = f"%{tracking_number}%"
    
    if item_id:
        filters.append('b."ItemID" ILIKE :item_id')
        params["item_id"] = f"%{item_id}%"
    
    if id_filter:
        # Cast to text for loose searching
        filters.append('CAST(b."ID" AS TEXT) ILIKE :id_filter')
        params["id_filter"] = f"%{id_filter}%"

    # Dates: PaidTime is text (ISO), record_created is timestamp
    if paid_from:
        filters.append('b."PaidTime" >= :paid_from')
        params["paid_from"] = paid_from
    if paid_to:
        filters.append('b."PaidTime" <= :paid_to')
        params["paid_to"] = paid_to
    
    if created_from:
        filters.append('b."record_created" >= :created_from')
        params["created_from"] = created_from
    if created_to:
        filters.append('b."record_created" <= :created_to')
        params["created_to"] = created_to

    # Storage logic
    if storage_value:
        if storage_mode == "exact":
            filters.append('b."Storage" = :storage_value')
            params["storage_value"] = storage_value
        elif storage_mode == "section":
            filters.append('b."Storage" ILIKE :storage_value_pattern')
            params["storage_value_pattern"] = f"{storage_value}%"
        else:
            # Any matches (default)
            filters.append('b."Storage" ILIKE :storage_value_pattern')
            params["storage_value_pattern"] = f"%{storage_value}%"

    where_clause = "WHERE " + " AND ".join(filters) if filters else ""

    data_sql = f"""
        SELECT
            b."ID" AS id,
            b."TrackingNumber" AS tracking_number,
            b."RefundFlag" AS refund_flag,
            b."Storage" AS storage,
            b."Profit" AS profit,
            b."BuyerID" AS buyer_id,
            b."SellerID" AS seller_id,
            b."PaidTime" AS paid_time,
            COALESCE(b."TotalTransactionPrice", b."CurrentPrice") AS amount_paid,
            CASE
                WHEN b."PaidTime" IS NULL OR b."PaidTime" = '' THEN NULL
                ELSE GREATEST(CAST(EXTRACT(DAY FROM (NOW() - CAST(b."PaidTime" AS TIMESTAMP))) AS INT), 0)
            END AS days_since_paid,
            sb."{status_label_col}" AS status_label,
            b."record_created" AS record_created_at,
            b."Title" AS title,
            b."Comment" AS comment,
            b."ItemID" AS item_id,
            b."TransactionID" AS transaction_id,
            b."OrderLineItemID" AS order_line_item_id,
            b."GlobalBuyerID" AS global_buyer_id,
            b."ConditionDisplayName" AS condition_display_name,
            b."QuantityPurchased" AS quantity_purchased,
            b."TotalPrice" AS total_price,
            b."ShippingCarrier" AS shipping_carrier,
            b."ShippingService" AS shipping_service,
            b."ShippingServiceCost" AS shipping_service_cost,
            b."ShippedTime" AS shipped_time,
            b."feedback" AS feedback,
            b."Author" AS author,
            b."payment_email" AS payment_email,
            b."SellerEmail" AS seller_email,
            b."SellerLocation" AS seller_location,
            b."SellerSite" AS seller_site,
            b."BuyerCheckoutMessage" AS buyer_checkout_message,
            b."Description" AS description,
            b."GalleryURL" AS gallery_url,
            b."PictureURL0" AS picture_url0,
            b."PictureURL1" AS picture_url1,
            b."PictureURL2" AS picture_url2,
            b."PictureURL3" AS picture_url3,
            b."PictureURL4" AS picture_url4,
            b."PictureURL5" AS picture_url5,
            b."PictureURL6" AS picture_url6,
            b."PictureURL7" AS picture_url7,
            b."PictureURL8" AS picture_url8,
            b."PictureURL9" AS picture_url9,
            b."PictureURL10" AS picture_url10,
            b."PictureURL11" AS picture_url11,
            COALESCE(b."Model_ID", b."ModelID") AS model_id,
            m."Model" AS model,
            b."record_updated" AS record_updated,
            b."record_updated_by" AS record_updated_by
        FROM "tbl_ebay_buyer" b
        LEFT JOIN (
            SELECT DISTINCT "Status", "StatusName" FROM "tbl_ebay_status_buyer"
        ) sb ON b."ItemStatus" = sb."{status_id_col}"
        LEFT JOIN "tbl_parts_models" m ON COALESCE(b."Model_ID", b."ModelID") = m."Model_ID"
        {where_clause}
        ORDER BY {sort_col_sql} {sort_dir_sql}
        LIMIT :limit OFFSET :offset
    """
    
    count_sql = f"""
        SELECT COUNT(*) AS total
        FROM "tbl_ebay_buyer" b
        {where_clause}
    """

    total = db.execute(sa_text(count_sql), params).scalar() or 0
    result = db.execute(sa_text(data_sql), params)

    rows: List[Dict[str, Any]] = []
    for r in result:
        row: Dict[str, Any] = {}
        for col in selected_cols:
            value = getattr(r, col, None)
            if value is None:
                continue
            if isinstance(value, dt_type):
                row[col] = value.isoformat()
            elif isinstance(value, Decimal):
                row[col] = float(value)
            else:
                row[col] = value
        rows.append(row)

    return {
        "rows": rows,
        "limit": limit,
        "offset": offset,
        "total": total,
        "sort": {"column": sort_column, "direction": sort_dir} if sort_column else None,
    }


def _get_sku_catalog_data(
    db: Session,
    current_user: UserModel,
    selected_cols: List[str],
    limit: int,
    offset: int,
    sort_column: Optional[str],
    sort_dir: str,
    search: Optional[str] = None,
    sku: Optional[str] = None,
    model: Optional[str] = None,
    category: Optional[str] = None,
    part_number: Optional[str] = None,
    title: Optional[str] = None,
) -> Dict[str, Any]:
    """SKU catalog grid backed by the SQ catalog table (sq_items).

    Exposes a logical view used by the LISTING tab and the SKU tab. Columns are
    direct projections of the underlying sq_items table so that all real
    database fields can be inspected from the UI.
    """
    from datetime import datetime as dt_type
    from decimal import Decimal

    query = db.query(SqItem)


    if sku:
        query = query.filter(SqItem.sku.ilike(f"%{sku}%"))
    if model:
        # В SKU_catalog нет текстовой колонки "Model", только numeric Model_ID.
        # Для фильтрации по модели используем эвристику: ищем подстроку в Title /
        # Description / Part, где обычно фигурирует модель ноутбука.
        like = f"%{model}%"
        query = query.filter(
            or_(
                SqItem.title.ilike(like),
                SqItem.description.ilike(like),
                SqItem.part.ilike(like),
            )
        )
    if category:
        query = query.filter(SqItem.category.ilike(f"%{category}%"))
    if part_number:
        query = query.filter(SqItem.part_number.ilike(f"%{part_number}%"))
    if title:
        query = query.filter(SqItem.title.ilike(f"%{title}%"))

    if search:
        like = f"%{search}%"
        query = query.filter(
            or_(
                SqItem.sku.ilike(like),
                SqItem.title.ilike(like),
                SqItem.description.ilike(like),
                SqItem.part.ilike(like),
                SqItem.part_number.ilike(like),
                SqItem.mpn.ilike(like),
                SqItem.upc.ilike(like),
            )
        )

    total = query.count()

    # Allow sorting on a subset of real columns using SqItem fields.
    allowed_sort_cols = {
        "id": SqItem.id,
        "sku_code": SqItem.sku,
        "sku": SqItem.sku,
        # "model" текстовой колонки нет; оставляем ключ для совместимости,
        # но сортировать будем по numeric Model_ID либо по ID.
        "model": SqItem.model_id,
        "category": SqItem.category,
        "price": SqItem.price,
        "record_created": SqItem.record_created,
        "record_updated": SqItem.record_updated,
        "rec_created": SqItem.record_created,
        "rec_updated": SqItem.record_updated,
    }
    # По умолчанию сортируем по ID (новые записи сверху при sort_dir="desc").
    sort_attr = allowed_sort_cols.get(sort_column or "id")
    if sort_attr is None:
        sort_attr = SqItem.id
    if sort_dir == "desc":
        query = query.order_by(desc(sort_attr))
    else:
        query = query.order_by(asc(sort_attr))

    rows_db: List[SqItem] = query.offset(offset).limit(limit).all()

    def _serialize(item: SqItem) -> Dict[str, Any]:
        """Serialize a SqItem row into the logical sku_catalog columns.

        We expose a wide set of fields so that the grid can show as much of the
        actual SKU_catalog / SQ catalog data as needed. Any column not present
        in `selected_cols` is ignored at runtime.
        """
        base_values: Dict[str, Any] = {
            # Core identifiers
            "id": item.id,
            "sku_code": item.sku,
            "sku": item.sku,
            "sku2": item.sku2,
            "model_id": item.model_id,
            "model": item.model,
            "part": item.part,
            # Pricing
            "price": item.price,
            "previous_price": item.previous_price,
            "brutto": item.brutto,
            # Market & category
            "market": item.market,
            "use_ebay_id": item.use_ebay_id,
            "category": item.category,
            "description": item.description,
            # Shipping
            "shipping_type": item.shipping_type,
            "shipping_group": item.shipping_group,
            "shipping_group_previous": item.shipping_group_previous,
            # Condition
            "condition_id": item.condition_id,
            "condition_description": item.condition_description,
            # Identification
            "part_number": item.part_number,
            "mpn": item.mpn,
            "upc": item.upc,
            # Alerts & status
            "alert_flag": item.alert_flag,
            "alert_message": item.alert_message,
            "record_status": item.record_status,
            "record_status_flag": item.record_status_flag,
            "checked_status": item.checked_status,
            "checked": item.checked,
            "checked_by": item.checked_by,
            # Images (first picture exposed via image_url as well)
            "pic_url1": item.pic_url1,
            "pic_url2": item.pic_url2,
            "pic_url3": item.pic_url3,
            "image_url": item.pic_url1,
            # New app-specific fields
            "title": item.title,
            "brand": item.brand,
            "warehouse_id": item.warehouse_id,
            "storage_alias": item.storage_alias,
            # Audit
            "record_created_by": item.record_created_by,
            "record_created": item.record_created,
            "record_updated_by": item.record_updated_by,
            "record_updated": item.record_updated,
            # Aliases for metadata column names (rec_created/rec_updated)
            "rec_created": item.record_created,
            "rec_updated": item.record_updated,
        }

        row: Dict[str, Any] = {}
        for col in selected_cols:
            value = base_values.get(col)
            if value is None:
                # Column not in base_values - skip it
                continue
            if isinstance(value, dt_type):
                row[col] = value.isoformat()
            elif isinstance(value, Decimal):
                row[col] = float(value)
            else:
                row[col] = value
        return row

    rows = [_serialize(item) for item in rows_db]

    return {
        "rows": rows,
        "limit": limit,
        "offset": offset,
        "total": total,
        "sort": {"column": sort_column, "direction": sort_dir} if sort_column else None,
    }


def _get_inventory_data(
    db: Session,
    current_user: UserModel,
    selected_cols: List[str],
    limit: int,
    offset: int,
    sort_column: Optional[str],
    sort_dir: str,
    storage_id: Optional[str],
    ebay_status: Optional[str],
    search: Optional[str],
    inv_id: Optional[str],
    inv_sku: Optional[str],
    inv_item_id: Optional[str],
    inv_title: Optional[str],
    inv_statussku: Optional[str],
    inv_storage: Optional[str],
    inv_serial_number: Optional[str],
) -> Dict[str, Any]:
    """Inventory grid backed directly by the Supabase table tbl_parts_inventory.

    This uses the reflected TblPartsInventory.__table__ so that all real
    columns from the underlying table are available without hardcoding a
    schema in the code.
    """
    from datetime import datetime as dt_type
    from decimal import Decimal
    from sqlalchemy.sql import text as sa_text
    from sqlalchemy.sql.sqltypes import String, Text, CHAR, VARCHAR, Unicode, UnicodeText

    table = TblPartsInventory.__table__
    if table is None or not list(table.columns):
        # Table missing in this environment – return empty result set but do not crash.
        return {
            "rows": [],
            "limit": limit,
            "offset": offset,
            "total": 0,
            "sort": None,
        }

    # Map columns by key and by lowercase key for flexible lookup.
    cols_by_key = {c.key: c for c in table.columns}
    cols_by_lower = {c.key.lower(): c for c in table.columns}

    # Query rows as plain row mappings using the reflected table columns.
    columns = list(table.columns)
    query = db.query(*columns)

    def _apply_ilike_filter(value: Optional[str], candidate_keys: List[str]) -> None:
        nonlocal query
        if not value:
            return
        v = value.strip()
        if not v:
            return
        like = f"%{v}%"
        for name in candidate_keys:
            key = name.lower()
            col = cols_by_lower.get(key)
            if col is not None and isinstance(
                col.type, (String, Text, CHAR, VARCHAR, Unicode, UnicodeText)
            ):
                query = query.filter(col.ilike(like))
                return

    # Optional filters: Storage ID / Storage location
    if storage_id:
        like = f"%{storage_id}%"
        # Support a range of legacy column names seen in tbl_parts_inventory.
        candidate_keys = [
            "storageid",
            "storage_id",
            "storage",
            "alternativestorage",
            "alternative_storage",
            "storagealias",
            "storage_alias",
        ]
        storage_cols = [
            cols_by_lower[name]
            for name in candidate_keys
            if name in cols_by_lower
            and isinstance(
                cols_by_lower[name].type,
                (String, Text, CHAR, VARCHAR, Unicode, UnicodeText),
            )
        ]
        if storage_cols:
            query = query.filter(or_(*[col.ilike(like) for col in storage_cols]))

    # Optional filters: eBay status
    if ebay_status:
        ebay_status_col = (
            cols_by_lower.get("ebay_status")
            or cols_by_lower.get("ebaystatus")
            or cols_by_lower.get("ebay_status_id")
        )
        if ebay_status_col is not None and isinstance(ebay_status_col.type, (String, Text, CHAR, VARCHAR, Unicode, UnicodeText)):
            like = f"%{ebay_status}%"
            query = query.filter(ebay_status_col.ilike(like))

    # Global search across all string-like columns when provided.
    if search:
        like = f"%{search}%"
        string_cols = [
            c
            for c in table.columns
            if isinstance(c.type, (String, Text, CHAR, VARCHAR, Unicode, UnicodeText))
        ]
        if string_cols:
            query = query.filter(or_(*[c.ilike(like) for c in string_cols]))

    # Column-specific filters (applied individually, Enter-driven on FE).
    _apply_ilike_filter(inv_id, ["id"])
    _apply_ilike_filter(inv_sku, ["sku", "sku_code"])
    _apply_ilike_filter(inv_item_id, ["itemid", "item_id"])
    _apply_ilike_filter(inv_title, ["overridetitle", "override_title", "title"])
    _apply_ilike_filter(inv_statussku, ["statussku", "status_sku"])
    _apply_ilike_filter(inv_storage, ["storage", "storageid", "storage_id", "storagealias", "storage_alias"])
    _apply_ilike_filter(inv_serial_number, ["serialnumber", "serial_number"])

    total = query.count()

    # Determine sort column dynamically. Prefer an explicit request if valid,
    # otherwise fall back to primary key or the first column.
    sort_attr = None
    if sort_column and sort_column in cols_by_key:
        sort_attr = cols_by_key[sort_column]
    else:
        pk_cols = list(table.primary_key.columns)
        if pk_cols:
            sort_attr = pk_cols[0]
        elif cols_by_key:
            sort_attr = next(iter(cols_by_key.values()))

    if sort_attr is not None:
        if sort_dir == "asc":
            query = query.order_by(asc(sort_attr))
        else:
            query = query.order_by(desc(sort_attr))

    rows_db = query.offset(offset).limit(limit).all()

    # Efficient SKU/ItemID counting for displayed rows only
    sku_col = cols_by_lower.get('sku')
    itemid_col = cols_by_lower.get('itemid') or cols_by_lower.get('item_id')
    statussku_col = cols_by_lower.get('statussku') or cols_by_lower.get('status_sku')
    
    sku_counts = {}
    itemid_counts = {}
    
    if sku_col and statussku_col and rows_db:
        # Extract unique SKUs from displayed rows
        unique_skus = []
        for row in rows_db:
            mapping = getattr(row, "_mapping", row)
            sku_value = mapping.get(sku_col.key)
            if sku_value is not None:
                unique_skus.append(sku_value)
        
        if unique_skus:
            try:
                # Count active/sold for these SKUs only
                count_sql = sa_text(f"""
                    SELECT "{sku_col.name}" AS sku,
                           COUNT(*) FILTER (WHERE "{statussku_col.name}" = 3) AS active_count,
                           COUNT(*) FILTER (WHERE "{statussku_col.name}" = 5) AS sold_count
                    FROM "{table.name}"
                    WHERE "{sku_col.name}" = ANY(:sku_list)
                    GROUP BY "{sku_col.name}"
                """)
                result = db.execute(count_sql, {'sku_list': unique_skus})
                for row in result:
                    sku_counts[row.sku] = (int(row.active_count or 0), int(row.sold_count or 0))
            except Exception:
                pass
    
    if itemid_col and statussku_col and rows_db:
        # Extract unique ItemIDs from displayed rows
        unique_itemids = []
        for row in rows_db:
            mapping = getattr(row, "_mapping", row)
            itemid_value = mapping.get(itemid_col.key)
            if itemid_value is not None and str(itemid_value).strip():
                unique_itemids.append(itemid_value)
        
        if unique_itemids:
            try:
                # Count active/sold for these ItemIDs only
                count_sql = sa_text(f"""
                    SELECT "{itemid_col.name}" AS itemid,
                           COUNT(*) FILTER (WHERE "{statussku_col.name}" = 3) AS active_count,
                           COUNT(*) FILTER (WHERE "{statussku_col.name}" = 5) AS sold_count
                    FROM "{table.name}"
                    WHERE "{itemid_col.name}" = ANY(:itemid_list)
                    GROUP BY "{itemid_col.name}"
                """)
                result = db.execute(count_sql, {'itemid_list': unique_itemids})
                for row in result:
                    itemid_counts[row.itemid] = (int(row.active_count or 0), int(row.sold_count or 0))
            except Exception:
                pass

    # Optional mapping of StatusSKU numeric codes to human-readable names from
    # tbl_parts_inventorystatus. If the lookup table is missing in this
    # environment, we silently fall back to showing the raw numeric code.
    status_label_by_id: Dict[int, Dict[str, Any]] = {}
    try:
        status_sql = sa_text(
            'SELECT "InventoryStatus_ID" AS id, "InventoryShortStatus_Name" AS label, "Color" AS color '
            'FROM "tbl_parts_inventorystatus"'
        )
        result = db.execute(status_sql)
        for row in result:
            try:
                status_label_by_id[int(row.id)] = {
                    "label": str(row.label) if row.label is not None else None,
                    "color": str(row.color) if row.color is not None else None,
                }
            except Exception:
                continue
    except Exception:
        status_label_by_id = {}

    def _serialize(row_) -> Dict[str, Any]:
        mapping = getattr(row_, "_mapping", row_)
        row: Dict[str, Any] = {}
        for col in selected_cols:
            try:
                # mapping keys are column keys (names) when querying *table.c
                value = mapping.get(col)
                if value is None:
                    # Column not in mapping - skip it
                    continue
                # Special case: map StatusSKU numeric ID to friendly name when available.
                if col == "StatusSKU" and status_label_by_id:
                    try:
                        key = int(value)
                        meta = status_label_by_id.get(key) or {}
                        label = meta.get("label")
                        color = meta.get("color")
                        if label is not None:
                            row[col] = label
                            if color:
                                row["StatusSKU_color"] = color
                            continue
                        if color:
                            row["StatusSKU_color"] = color
                    except Exception:
                        # Fall through to generic serialization on failure.
                        pass
                if isinstance(value, dt_type):
                    row[col] = value.isoformat()
                elif isinstance(value, Decimal):
                    row[col] = float(value)
                elif isinstance(value, enum.Enum):
                    row[col] = value.value
                else:
                    row[col] = value
            except Exception:
                 # Skip columns that cause errors
                continue
        
        # Add formatted SKU/ItemID columns with counts
        if 'SKU_with_counts' in selected_cols:
            if sku_col and sku_col.key in mapping:
                sku_value = mapping.get(sku_col.key)
                if sku_value is not None:
                    counts = sku_counts.get(sku_value, (0, 0))
                    row['SKU_with_counts'] = f"{sku_value} ({counts[0]}/{counts[1]})"
        
        if 'ItemID_with_counts' in selected_cols:
            if itemid_col and itemid_col.key in mapping:
                itemid_value = mapping.get(itemid_col.key)
                if itemid_value is not None:
                    counts = itemid_counts.get(itemid_value, (0, 0))
                    row['ItemID_with_counts'] = f"{itemid_value} ({counts[0]}/{counts[1]})"
        
        return row

    rows = [_serialize(item) for item in rows_db]

    return {
        "rows": rows,
        "limit": limit,
        "offset": offset,
        "total": total,
        "sort": {"column": sort_column, "direction": sort_dir} if sort_column else None,
    }


def _get_sniper_snipes_data(
    db: Session,
    current_user: UserModel,
    selected_cols: List[str],
    limit: int,
    offset: int,
    sort_column: Optional[str],
    sort_dir: str,
    status_filter: Optional[str],
    ebay_account_id: Optional[str],
    search: Optional[str],
) -> Dict[str, Any]:
    """Sniper grid backed by ebay_snipes.

    This powers the SNIPER tab and is deliberately simple: one row per snipe
    scoped to the current user, with optional filters on status, account and a
    lightweight search over item_id/title.
    """
    from datetime import datetime as dt_type
    from decimal import Decimal

    query = db.query(EbaySnipe).filter(EbaySnipe.user_id == current_user.id)

    if status_filter:
        # Accept either a single status or a comma-separated list.
        raw = [s.strip() for s in status_filter.split(",") if s.strip()]
        if raw:
            query = query.filter(EbaySnipe.status.in_(raw))

    if ebay_account_id:
        query = query.filter(EbaySnipe.ebay_account_id == ebay_account_id)

    if search:
        like = f"%{search}%"
        query = query.filter(
            or_(EbaySnipe.item_id.ilike(like), EbaySnipe.title.ilike(like))
        )

    total = query.count()

    # Allow sorting on a safe subset of real columns, default to created_at.
    allowed_sort_cols = {
        "created_at": EbaySnipe.created_at,
        "end_time": EbaySnipe.end_time,
        "fire_at": EbaySnipe.fire_at,
        "status": EbaySnipe.status,
        "max_bid_amount": EbaySnipe.max_bid_amount,
    }
    sort_attr = allowed_sort_cols.get(sort_column or "created_at")
    if sort_dir == "desc":
        query = query.order_by(desc(sort_attr))
    else:
        query = query.order_by(asc(sort_attr))

    rows_db: List[EbaySnipe] = query.offset(offset).limit(limit).all()

    def _serialize(snipe: EbaySnipe) -> Dict[str, Any]:
        row: Dict[str, Any] = {}
        for col in selected_cols:
            try:
                value = getattr(snipe, col, None)
                if value is None:
                    continue
                if isinstance(value, dt_type):
                    row[col] = value.isoformat()
                elif isinstance(value, Decimal):
                    row[col] = float(value)
                else:
                    row[col] = value
            except Exception:
                # Skip unexpected/legacy columns without failing the entire grid.
                continue
        return row

    rows = [_serialize(s) for s in rows_db]

    return {
        "rows": rows,
        "limit": limit,
        "offset": offset,
        "total": total,
        "sort": {"column": sort_column, "direction": sort_dir} if sort_column else None,
    }


def _get_transactions_data(
    db: Session,
    current_user: UserModel,
    selected_cols: List[str],
    limit: int,
    offset: int,
    sort_column: Optional[str],
    sort_dir: str,
) -> Dict[str, Any]:
    """Minimal Transactions grid backed by public.ebay_transactions.

    Uses only existing columns, no joins or derived fields.
    """
    from datetime import datetime as dt_type
    from decimal import Decimal

    query = db.query(EbayLegacyTransaction)

    total = query.count()

    allowed_sort_cols = {
        "transaction_date",
        "transaction_type",
        "transaction_status",
        "amount",
        "currency",
        "created_at",
        "updated_at",
    }
    if sort_column in allowed_sort_cols and hasattr(EbayLegacyTransaction, sort_column):
        sort_attr = getattr(EbayLegacyTransaction, sort_column)
        if sort_dir == "desc":
            query = query.order_by(desc(sort_attr))
        else:
            query = query.order_by(asc(sort_attr))

    rows_db: List[EbayLegacyTransaction] = query.offset(offset).limit(limit).all()

    def _serialize(t: EbayLegacyTransaction) -> Dict[str, Any]:
        row: Dict[str, Any] = {}
        for col in selected_cols:
            try:
                value = getattr(t, col, None)
                if value is None:
                    continue
                if isinstance(value, dt_type):
                    row[col] = value.isoformat()
                elif isinstance(value, Decimal):
                    row[col] = float(value)
                else:
                    row[col] = value
            except Exception:
                continue
        return row

    rows = [_serialize(t) for t in rows_db]

    return {
        "rows": rows,
        "limit": limit,
        "offset": offset,
        "total": total,
        "sort": {"column": sort_column, "direction": sort_dir} if sort_column else None,
    }


def _get_messages_data(
    db: Session,
    current_user: UserModel,
    selected_cols: List[str],
    limit: int,
    offset: int,
    sort_column: Optional[str],
    sort_dir: str,
    folder: Optional[str],
    unread_only: bool,
    search: Optional[str],
) -> Dict[str, Any]:
    # Default folder behavior mirrors /messages endpoint
    actual_folder = folder or "inbox"

    query = db.query(EbayMessage).filter(EbayMessage.user_id == current_user.id)

    # Inbox: show all incoming messages regardless of archived flag so counts
    # and UI remain consistent. Archived view can still be used to focus on
    # archived messages only.
    if actual_folder == "inbox":
        query = query.filter(EbayMessage.direction == "INCOMING")
    elif actual_folder == "sent":
        query = query.filter(EbayMessage.direction == "OUTGOING")
    elif actual_folder == "flagged":
        query = query.filter(EbayMessage.is_flagged == True)  # noqa: E712
    elif actual_folder == "archived":
        query = query.filter(EbayMessage.is_archived == True)  # noqa: E712

    if unread_only:
        query = query.filter(EbayMessage.is_read == False)  # noqa: E712

    if search:
        from sqlalchemy import or_

        like = f"%{search}%"
        query = query.filter(
            or_(
                EbayMessage.subject.ilike(like),
                EbayMessage.body.ilike(like),
                EbayMessage.sender_username.ilike(like),
            )
        )

    total = query.count()

    if sort_column:
        order_attr = getattr(EbayMessage, sort_column)
        if sort_dir == "desc":
            query = query.order_by(desc(order_attr))
        else:
            query = query.order_by(asc(order_attr))

    rows_db: List[EbayMessage] = query.offset(offset).limit(limit).all()

    from datetime import datetime as dt_type
    from decimal import Decimal

    def _serialize(m: EbayMessage) -> Dict[str, Any]:
        row: Dict[str, Any] = {}
        for col in selected_cols:
            value = getattr(m, col, None)
            if isinstance(value, dt_type):
                row[col] = value.isoformat()
            elif isinstance(value, Decimal):
                row[col] = float(value)
            elif isinstance(value, enum.Enum):
                row[col] = value.value
            else:
                row[col] = value
        return row

    rows = [_serialize(m) for m in rows_db]

    return {
        "rows": rows,
        "limit": limit,
        "offset": offset,
        "total": total,
        "sort": {"column": sort_column, "direction": sort_dir} if sort_column else None,
    }


def _get_offers_data(
    db: Session,
    current_user: UserModel,
    selected_cols: List[str],
    limit: int,
    offset: int,
    sort_column: Optional[str],
    sort_dir: str,
    state: Optional[str],
    direction: Optional[str],
    buyer: Optional[str],
    item_id: Optional[str],
    sku: Optional[str],
    from_date: Optional[str],
    to_date: Optional[str],
) -> Dict[str, Any]:
    from datetime import datetime as dt_type
    from decimal import Decimal

    query = db.query(OfferModel).filter(OfferModel.user_id == current_user.id)

    if state:
        try:
            offer_state = OfferState[state.upper()]
            query = query.filter(OfferModel.state == offer_state)
        except KeyError:
            pass

    if direction:
        try:
            offer_dir = OfferDirection[direction.upper()]
            query = query.filter(OfferModel.direction == offer_dir)
        except KeyError:
            pass

    if buyer:
        query = query.filter(OfferModel.buyer_username.ilike(f"%{buyer}%"))

    if item_id:
        query = query.filter(OfferModel.item_id == item_id)

    if sku:
        query = query.filter(OfferModel.sku.ilike(f"%{sku}%"))

    if from_date:
        try:
            from_dt = dt_type.fromisoformat(from_date.replace("Z", "+00:00"))
            query = query.filter(OfferModel.created_at >= from_dt)
        except Exception:
            pass

    if to_date:
        try:
            to_dt = dt_type.fromisoformat(to_date.replace("Z", "+00:00"))
            query = query.filter(OfferModel.created_at <= to_dt)
        except Exception:
            pass

    total = query.count()

    if sort_column:
        order_attr = getattr(OfferModel, sort_column)
        if sort_dir == "desc":
            query = query.order_by(desc(order_attr))
        else:
            query = query.order_by(asc(order_attr))

    rows_db: List[OfferModel] = query.offset(offset).limit(limit).all()

    def _serialize(o: OfferModel) -> Dict[str, Any]:
        row: Dict[str, Any] = {}
        for col in selected_cols:
            try:
                value = getattr(o, col, None)
                if value is None:
                    continue
                if isinstance(value, dt_type):
                    row[col] = value.isoformat()
                elif isinstance(value, Decimal):
                    row[col] = float(value)
                elif isinstance(value, enum.Enum):
                    row[col] = value.value
                else:
                    row[col] = value
            except Exception:
                continue
        return row

    rows = [_serialize(o) for o in rows_db]

    return {
        "rows": rows,
        "limit": limit,
        "offset": offset,
        "total": total,
        "sort": {"column": sort_column, "direction": sort_dir} if sort_column else None,
    }




def _get_cases_data(
    db: Session,
    current_user: UserModel,
    selected_cols: List[str],
    limit: int,
    offset: int,
    sort_column: Optional[str],
    sort_dir: str,
    state: Optional[str],
    buyer: Optional[str],
    from_date: Optional[str],
    to_date: Optional[str],
    kind_filter: Optional[str] = None,
    external_id_filter: Optional[str] = None,
) -> Dict[str, Any]:
    """Unified Cases & Disputes grid backed by ebay_disputes + ebay_cases.

    We materialize rows for the current user and enrich them with an inferred
    ``issue_type`` (INR/SNAD/OTHER). Expected volume is low so this stays cheap
    and avoids tight schema coupling.
    """
    import json
    from datetime import datetime as dt_type
    from sqlalchemy import text as sa_text

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
            'inquiry'         AS kind,
            i.inquiry_id      AS external_id,
            i.order_id        AS order_id,
            i.issue_type      AS reason,
            i.status          AS status,
            i.opened_at::text AS open_date,
            i.last_update_at::text AS respond_by_date,
            i.raw_json        AS raw_payload,
            i.ebay_account_id AS ebay_account_id,
            i.ebay_user_id    AS ebay_user_id,
            i.buyer_username  AS buyer_username,
            i.claim_amount_value    AS amount_value,
            i.claim_amount_currency AS amount_currency,
            NULL::timestamptz AS creation_date_api,
            NULL::timestamptz AS last_modified_date_api,
            NULL::text        AS case_status_enum,
            i.item_id         AS item_id,
            i.transaction_id  AS transaction_id
        FROM ebay_inquiries i
        WHERE i.user_id = :user_id
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

    result = db.execute(union_sql, {"user_id": current_user.id})

    def _issue_type(reason: Optional[str]) -> Optional[str]:
        if not reason:
            return None
        r = reason.upper()
        if "NOT_RECEIVED" in r:
            return "INR"
        if "NOT_AS_DESCRIBED" in r or "SNAD" in r:
            return "SNAD"
        return None

    rows_all: List[Dict[str, Any]] = []
    for row in result:
        issue = _issue_type(row.reason)

        # Prefer normalized columns from ebay_cases for Post-Order cases, but
        # fall back to parsing raw_payload for legacy rows or disputes where
        # those fields are not available.
        buyer_username = getattr(row, "buyer_username", None)
        amount = getattr(row, "amount_value", None)
        currency = getattr(row, "amount_currency", None)
        creation_date_api = getattr(row, "creation_date_api", None)
        last_modified_date_api = getattr(row, "last_modified_date_api", None)
        case_status_enum = getattr(row, "case_status_enum", None)
        item_id = getattr(row, "item_id", None)
        transaction_id = getattr(row, "transaction_id", None)

        raw_payload = row.raw_payload
        payload: Dict[str, Any] = {}
        if buyer_username is None or amount is None or currency is None:
            try:
                payload = json.loads(raw_payload) if isinstance(raw_payload, str) else raw_payload or {}
            except Exception:
                payload = {}

            # Some legacy rows may store a primitive JSON value (e.g. a string)
            # in the JSONB column. Normalize to a dict so grid rendering is
            # resilient to those rows.
            if not isinstance(payload, dict):
                payload = {}

        if buyer_username is None and isinstance(payload, dict):
            # Buyer username – tolerate various shapes for the "buyer" field.
            buyer_field = payload.get("buyer")
            if isinstance(buyer_field, dict):
                buyer_obj = buyer_field
            else:
                buyer_obj = {}

            buyer_username = (
                payload.get("buyerUsername")
                or buyer_obj.get("username")
                or buyer_obj.get("userId")
            )

        if amount is None and isinstance(payload, dict):
            try:
                mt_list = payload.get("monetaryTransactions")
                if isinstance(mt_list, list) and mt_list:
                    first_txn = mt_list[0] or {}
                    if isinstance(first_txn, dict):
                        total_price = first_txn.get("totalPrice") or {}
                        if isinstance(total_price, dict):
                            amount = total_price.get("value")
                            currency = total_price.get("currency") or currency
            except Exception:
                # If the payload shape is unexpected, just leave amount/currency as None.
                pass

        if amount is None and isinstance(payload, dict):
            claim = payload.get("claimAmount") or payload.get("disputeAmount") or {}
            if isinstance(claim, dict):
                amount = claim.get("value")
                currency = currency or claim.get("currency")

        def _normalize_dt(value: Any) -> Optional[str]:
            if not value:
                return None
            if isinstance(value, dt_type):
                return value.isoformat()
            if isinstance(value, str):
                try:
                    v = value.replace("Z", "+00:00") if "Z" in value else value
                    dt = dt_type.fromisoformat(v)
                    return dt.isoformat()
                except Exception:
                    return value
            return str(value)

        open_date = _normalize_dt(row.open_date)
        respond_by_date = _normalize_dt(row.respond_by_date)
        creation_date_api_str = _normalize_dt(creation_date_api)
        last_modified_date_api_str = _normalize_dt(last_modified_date_api)

        rows_all.append(
            {
                "kind": row.kind,
                "external_id": row.external_id,
                "order_id": row.order_id,
                "status": row.status,
                # Preserve INR/SNAD labels but keep non-matching cases visible as OTHER.
                "issue_type": issue or "OTHER",
                "buyer_username": buyer_username,
                "amount": amount,
                "currency": currency,
                "open_date": open_date,
                "respond_by_date": respond_by_date,
                # Also expose normalized fields for API consumers that need
                # richer joins (messages, finances, etc.).
                "ebay_account_id": row.ebay_account_id,
                "ebay_user_id": row.ebay_user_id,
                "item_id": item_id,
                "transaction_id": transaction_id,
                "case_status_enum": case_status_enum,
                "creation_date_api": creation_date_api_str,
                "last_modified_date_api": last_modified_date_api_str,
            }
        )

    # Simple filters
    if kind_filter:
        rows_all = [r for r in rows_all if (r.get("kind") or "") == kind_filter]

    if external_id_filter:
        rows_all = [r for r in rows_all if (r.get("external_id") or "") == external_id_filter]

    if state:
        rows_all = [r for r in rows_all if (r.get("status") or "").lower() == state.lower()]
    if buyer:
        rows_all = [r for r in rows_all if buyer.lower() in (r.get("buyer_username") or "").lower()]

    if from_date or to_date:
        def _within_window(r: Dict[str, Any]) -> bool:
            od = r.get("open_date")
            if not isinstance(od, str):
                return True
            try:
                v = od.replace("Z", "+00:00") if "Z" in od else od
                dt = dt_type.fromisoformat(v)
            except Exception:
                return True
            if from_date:
                try:
                    f = dt_type.fromisoformat(from_date.replace("Z", "+00:00"))
                    if dt < f:
                        return False
                except Exception:
                    pass
            if to_date:
                try:
                    t = dt_type.fromisoformat(to_date.replace("Z", "+00:00"))
                    if dt > t:
                        return False
                except Exception:
                    pass
            return True

        rows_all = [r for r in rows_all if _within_window(r)]

    # Sort
    if sort_column and sort_column in {"open_date", "status", "buyer_username", "amount", "respond_by_date"}:
        reverse = sort_dir == "desc"
        rows_all.sort(key=lambda r: r.get(sort_column) or "", reverse=reverse)
    else:
        rows_all.sort(key=lambda r: r.get("open_date") or "", reverse=True)

    total = len(rows_all)
    page_rows = rows_all[offset : offset + limit]

    projected: List[Dict[str, Any]] = []
    for r in page_rows:
        projected.append({col: r.get(col) for col in selected_cols})

    return {
        "rows": projected,
        "limit": limit,
        "offset": offset,
        "total": total,
        "sort": {"column": sort_column, "direction": sort_dir} if sort_column else None,
    }


def _get_finances_data(
    db: Session,
    current_user: UserModel,
    selected_cols: List[str],
    limit: int,
    offset: int,
    sort_column: Optional[str],
    sort_dir: str,
    transaction_type: Optional[str],
    from_date: Optional[str],
    to_date: Optional[str],
) -> Dict[str, Any]:
    """Finances ledger grid backed by ebay_finances_transactions + fees.

    This endpoint exposes raw Finances transactions with per-transaction fee
    aggregates, filtered to the current user's eBay accounts.
    """
    from decimal import Decimal
    from datetime import datetime as dt_type
    from sqlalchemy import text as sa_text

    # Build dynamic WHERE clause joined to ebay_accounts for org-level scoping
    where_clauses = ["a.org_id = :user_id"]
    params: Dict[str, Any] = {"user_id": current_user.id}

    if transaction_type:
        where_clauses.append("t.transaction_type = :txn_type")
        params["txn_type"] = transaction_type

    if from_date:
        where_clauses.append("t.booking_date >= :from_date")
        params["from_date"] = from_date

    if to_date:
        where_clauses.append("t.booking_date <= :to_date")
        params["to_date"] = to_date

    where_sql = " AND ".join(where_clauses)

    # Count query
    count_sql = sa_text(
        f"""
        SELECT COUNT(*) AS cnt
        FROM ebay_finances_transactions t
        JOIN ebay_accounts a ON a.id = t.ebay_account_id
        WHERE {where_sql}
        """
    )
    total = db.execute(count_sql, params).scalar() or 0

    # Sorting
    allowed_sort_cols = {
        "booking_date",
        "transaction_type",
        "transaction_status",
        "transaction_amount_value",
        "transaction_amount_currency",
        "order_id",
        "transaction_id",
    }
    order_clause = ""
    if sort_column in allowed_sort_cols:
        direction = "DESC" if sort_dir == "desc" else "ASC"
        order_clause = f"ORDER BY t.{sort_column} {direction}"

    data_sql = sa_text(
        f"""
        SELECT
            t.ebay_account_id,
            t.ebay_user_id,
            t.transaction_id,
            t.transaction_type,
            t.transaction_status,
            t.booking_date,
            t.transaction_amount_value,
            t.transaction_amount_currency,
            t.order_id,
            t.order_line_item_id,
            t.payout_id,
            t.seller_reference,
            t.transaction_memo
        FROM ebay_finances_transactions t
        JOIN ebay_accounts a ON a.id = t.ebay_account_id
        WHERE {where_sql}
        {order_clause}
        LIMIT :limit OFFSET :offset
        """
    )

    params_with_paging = dict(params)
    params_with_paging["limit"] = limit
    params_with_paging["offset"] = offset

    result = db.execute(data_sql, params_with_paging)
    rows_db = [dict(row._mapping) for row in result]

    # Collect transaction_ids for fee lookup
    txn_ids = [r["transaction_id"] for r in rows_db]
    fees_by_txn: Dict[str, List[Dict[str, Any]]] = {}
    if txn_ids:
        placeholders = ",".join(f":tid{i}" for i in range(len(txn_ids)))
        fee_sql = sa_text(
            f"""
            SELECT transaction_id, fee_type, amount_value, amount_currency
            FROM ebay_finances_fees
            WHERE transaction_id IN ({placeholders})
            """
        )
        fee_params = {f"tid{i}": txn_ids[i] for i in range(len(txn_ids))}
        fee_result = db.execute(fee_sql, fee_params)
        for row in fee_result:
            m = row._mapping
            tid = m["transaction_id"]
            fees_by_txn.setdefault(tid, []).append(dict(m))

    def _aggregate_fees(tid: str) -> Dict[str, Optional[float]]:
        rows = fees_by_txn.get(tid, [])
        final_value = Decimal("0")
        promoted = Decimal("0")
        shipping = Decimal("0")
        other = Decimal("0")

        for f in rows:
            ftype = (f.get("fee_type") or "").upper()
            val = f.get("amount_value")
            if val is None:
                continue
            if not isinstance(val, Decimal):
                try:
                    val = Decimal(str(val))
                except Exception:
                    continue

            if "FINAL_VALUE_FEE" in ftype:
                final_value += val
            elif "PROMOTED_LISTING" in ftype:
                promoted += val
            elif "SHIPPING_LABEL" in ftype:
                shipping += val
            else:
                other += val

        total_local = final_value + promoted + shipping + other

        def _to_float(d: Decimal) -> Optional[float]:
            return float(d) if d != 0 else None

        return {
            "final_value_fee": _to_float(final_value),
            "promoted_listing_fee": _to_float(promoted),
            "shipping_label_fee": _to_float(shipping),
            "other_fees": _to_float(other),
            "total_fees": _to_float(total_local),
        }

    def _serialize(row: Dict[str, Any]) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for col in selected_cols:
            if col in {
                "final_value_fee",
                "promoted_listing_fee",
                "shipping_label_fee",
                "other_fees",
                "total_fees",
            }:
                # Filled from fee aggregates below
                continue
            value = row.get(col)
            if isinstance(value, dt_type):
                out[col] = value.isoformat()
            elif isinstance(value, Decimal):
                out[col] = float(value)
            else:
                out[col] = value

        agg = _aggregate_fees(row["transaction_id"])
        for k, v in agg.items():
            if k in selected_cols:
                out[k] = v

        return out

    rows = [_serialize(r) for r in rows_db]

    return {
        "rows": rows,
        "limit": limit,
        "offset": offset,
        "total": total,
        "sort": {"column": sort_column, "direction": sort_dir} if sort_column else None,
    }


def _get_finances_fees_data(
    db: Session,
    current_user: UserModel,
    selected_cols: List[str],
    limit: int,
    offset: int,
    sort_column: Optional[str],
    sort_dir: str,
    from_date: Optional[str],
    to_date: Optional[str],
    fee_type: Optional[str] = None,
    search: Optional[str] = None,
) -> Dict[str, Any]:
    """Finances fees grid backed by ebay_finances_fees.

    Shows one row per fee line for accounts belonging to the current org/user.
    """
    from decimal import Decimal
    from datetime import datetime as dt_type
    from sqlalchemy import text as sa_text

    where_clauses = ["a.org_id = :user_id"]
    params: Dict[str, Any] = {"user_id": current_user.id}

    if from_date:
        where_clauses.append("f.created_at >= :from_date")
        params["from_date"] = from_date

    if to_date:
        where_clauses.append("f.created_at <= :to_date")
        params["to_date"] = to_date

    if fee_type:
        where_clauses.append("f.fee_type ILIKE :fee_type")
        params["fee_type"] = f"%{fee_type}%"

    if search:
        # Lightweight global search across fee_type and transaction_id so the generic grid search
        # box can locate rows by human-readable type or id.
        where_clauses.append("(f.fee_type ILIKE :search OR f.transaction_id ILIKE :search)")
        params["search"] = f"%{search}%"

    where_sql = " AND ".join(where_clauses)

    count_sql = sa_text(
        f"""
        SELECT COUNT(*) AS cnt
        FROM ebay_finances_fees f
        JOIN ebay_accounts a ON a.id = f.ebay_account_id
        WHERE {where_sql}
        """
    )
    total = db.execute(count_sql, params).scalar() or 0

    allowed_sort_cols = {
        "created_at",
        "updated_at",
        "fee_type",
        "amount_value",
        "amount_currency",
        "transaction_id",
    }
    order_clause = ""
    if sort_column in allowed_sort_cols:
        direction = "DESC" if sort_dir == "desc" else "ASC"
        order_clause = f"ORDER BY f.{sort_column} {direction}"

    data_sql = sa_text(
        f"""
        SELECT
            f.id,
            f.ebay_account_id,
            f.transaction_id,
            f.fee_type,
            f.amount_value,
            f.amount_currency,
            f.raw_payload,
            f.created_at,
            f.updated_at
        FROM ebay_finances_fees f
        JOIN ebay_accounts a ON a.id = f.ebay_account_id
        WHERE {where_sql}
        {order_clause}
        LIMIT :limit OFFSET :offset
        """
    )

    params_with_paging = dict(params)
    params_with_paging["limit"] = limit
    params_with_paging["offset"] = offset

    result = db.execute(data_sql, params_with_paging)
    rows_db = [dict(row._mapping) for row in result]

    def _serialize(row: Dict[str, Any]) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for col in selected_cols:
            value = row.get(col)
            if isinstance(value, dt_type):
                out[col] = value.isoformat()
            elif isinstance(value, Decimal):
                out[col] = float(value)
            else:
                out[col] = value
        return out

    rows = [_serialize(r) for r in rows_db]

    return {
        "rows": rows,
        "limit": limit,
        "offset": offset,
        "total": total,
        "sort": {"column": sort_column, "direction": sort_dir} if sort_column else None,
    }


def _get_accounting_transactions_grid_data(
    db: Session,
    current_user: UserModel,
    selected_cols: List[str],
    limit: int,
    offset: int,
    sort_column: Optional[str],
    sort_dir: str,
    date_from: Optional[str],
    date_to: Optional[str],
    source_type: Optional[str],
    storage_id: Optional[str],
    category_id: Optional[int] = None,
    min_amount: Optional[float] = None,
    max_amount: Optional[float] = None,
    account_name: Optional[str] = None,
    direction: Optional[str] = None,
    is_personal: Optional[bool] = None,
    is_internal_transfer: Optional[bool] = None,
    search: Optional[str] = None,
) -> Dict[str, Any]:
    from datetime import datetime as dt_type
    from decimal import Decimal

    query = db.query(AccountingTxn)

    if date_from:
        try:
            from_dt = dt_type.fromisoformat(date_from.replace("Z", "+00:00"))
            query = query.filter(AccountingTxn.date >= from_dt.date())
        except Exception:
            pass
    if date_to:
        try:
            to_dt = dt_type.fromisoformat(date_to.replace("Z", "+00:00"))
            query = query.filter(AccountingTxn.date <= to_dt.date())
        except Exception:
            pass
    if source_type:
        query = query.filter(AccountingTxn.source_type == source_type)
    if storage_id:
        query = query.filter(AccountingTxn.storage_id == storage_id)
    if category_id is not None:
        query = query.filter(AccountingTxn.expense_category_id == category_id)
    if direction:
        query = query.filter(AccountingTxn.direction == direction)
    if min_amount is not None:
        query = query.filter(AccountingTxn.amount >= min_amount)
    if max_amount is not None:
        query = query.filter(AccountingTxn.amount <= max_amount)
    if account_name:
        query = query.filter(AccountingTxn.account_name.ilike(f"%{account_name}%"))
    if is_personal is not None:
        query = query.filter(AccountingTxn.is_personal == is_personal)
    if is_internal_transfer is not None:
        query = query.filter(AccountingTxn.is_internal_transfer == is_internal_transfer)
    if search:
        like = f"%{search}%"
        query = query.filter(
            or_(
                AccountingTxn.description.ilike(like),
                AccountingTxn.account_name.ilike(like),
                AccountingTxn.counterparty.ilike(like),
            )
        )

    total = query.count()

    if sort_column and hasattr(AccountingTxn, sort_column):
        order_attr = getattr(AccountingTxn, sort_column)
        if sort_dir == "desc":
            query = query.order_by(desc(order_attr))
        else:
            query = query.order_by(asc(order_attr))

    rows_db: List[AccountingTxn] = query.offset(offset).limit(limit).all()

    def _serialize(txn: AccountingTxn) -> Dict[str, Any]:
        row: Dict[str, Any] = {}
        for col in selected_cols:
            if col == "signed_amount":
                # Synthetic signed amount: positive for direction="in",
                # negative for direction="out". This powers Ledger coloring
                # without changing the underlying schema.
                base = txn.amount or Decimal("0")
                sign = 1 if txn.direction == "in" else -1
                value = base * sign
            else:
                value = getattr(txn, col, None)
            if isinstance(value, dt_type):
                row[col] = value.isoformat()
            elif isinstance(value, Decimal):
                row[col] = float(value)
            else:
                row[col] = value
        return row

    rows = [_serialize(t) for t in rows_db]

    return {
        "rows": rows,
        "limit": limit,
        "offset": offset,
        "total": total,
        "sort": {"column": sort_column, "direction": sort_dir} if sort_column else None,
    }


def _get_active_inventory_data(
    db: Session,
    current_user: UserModel,
    selected_cols: List[str],
    limit: int,
    offset: int,
    sort_column: Optional[str],
    sort_dir: str,
) -> Dict[str, Any]:
    """Active Inventory grid backed by ebay_active_inventory snapshot.

    For now this is a simple per-org view: show rows for all accounts belonging
    to the current user/org. We can refine account scoping later.
    """
    from datetime import datetime as dt_type
    from decimal import Decimal

    # Filter by org via join on ebay_accounts.org_id if needed; for MVP, we
    # filter by accounts that belong to this user/org using a simple join.
    from app.models_sqlalchemy.models import EbayAccount

    query = (
        db.query(ActiveInventory)
        .join(EbayAccount, ActiveInventory.ebay_account_id == EbayAccount.id)
        .filter(EbayAccount.org_id == current_user.id)
    )

    total = query.count()

    if sort_column and hasattr(ActiveInventory, sort_column):
        order_attr = getattr(ActiveInventory, sort_column)
        if sort_dir == "desc":
            query = query.order_by(desc(order_attr))
        else:
            query = query.order_by(asc(order_attr))

    rows_db: List[ActiveInventory] = query.offset(offset).limit(limit).all()

    def _serialize(ai: ActiveInventory) -> Dict[str, Any]:
        row: Dict[str, Any] = {}
        for col in selected_cols:
            try:
                value = getattr(ai, col, None)
                if isinstance(value, dt_type):
                    row[col] = value.isoformat()
                elif isinstance(value, Decimal):
                    row[col] = float(value)
                else:
                    row[col] = value
            except Exception:
                row[col] = None
        return row

    rows = [_serialize(ai) for ai in rows_db]

    return {
        "rows": rows,
        "limit": limit,
        "offset": offset,
        "total": total,
        "sort": {"column": sort_column, "direction": sort_dir} if sort_column else None,
    }


def _get_accounting_bank_statements_data(
    db: Session,
    current_user: UserModel,
    selected_cols: List[str],
    limit: int,
    offset: int,
    sort_column: Optional[str],
    sort_dir: str,
) -> Dict[str, Any]:
    from datetime import datetime as dt_type
    from decimal import Decimal

    query = db.query(AccountingBankStatement)
    total = query.count()

    if sort_column and hasattr(AccountingBankStatement, sort_column):
        order_attr = getattr(AccountingBankStatement, sort_column)
        if sort_dir == "desc":
            query = query.order_by(desc(order_attr))
        else:
            query = query.order_by(asc(order_attr))

    rows_db = query.offset(offset).limit(limit).all()

    # Preload row counts
    stmt_ids = [r.id for r in rows_db]
    counts_map = {}
    if stmt_ids:
        from sqlalchemy import func
        from app.models_sqlalchemy.models import AccountingBankRow
        counts = (
            db.query(AccountingBankRow.bank_statement_id, func.count(AccountingBankRow.id))
            .filter(AccountingBankRow.bank_statement_id.in_(stmt_ids))
            .group_by(AccountingBankRow.bank_statement_id)
            .all()
        )
        counts_map = {bid: c for bid, c in counts}

    def _serialize(stmt: AccountingBankStatement) -> Dict[str, Any]:
        row: Dict[str, Any] = {}
        for col in selected_cols:
            if col == "rows_count":
                row[col] = counts_map.get(stmt.id, 0)
                continue
            
            try:
                value = getattr(stmt, col, None)
                if isinstance(value, dt_type):
                    row[col] = value.isoformat()
                elif isinstance(value, Decimal):
                    row[col] = float(value)
                else:
                    row[col] = value
            except Exception:
                row[col] = None
        return row

    rows = [_serialize(r) for r in rows_db]
    
    import logging
    logger = logging.getLogger(__name__)
    logger.info("🔍 [BANK_STATEMENTS] total=%d rows_returned=%d", total, len(rows))
    if rows:
        logger.info("🔍 [BANK_STATEMENTS] first_row_keys=%s", list(rows[0].keys()))
        logger.info("🔍 [BANK_STATEMENTS] first_row=%s", rows[0])

    return {
        "rows": rows,
        "limit": limit,
        "offset": offset,
        "total": total,
        "sort": {"column": sort_column, "direction": sort_dir} if sort_column else None,
    }


def _get_accounting_cash_expenses_data(
    db: Session,
    current_user: UserModel,
    selected_cols: List[str],
    limit: int,
    offset: int,
    sort_column: Optional[str],
    sort_dir: str,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> Dict[str, Any]:
    from datetime import datetime as dt_type
    from decimal import Decimal

    query = db.query(AccountingCashExpense)

    if date_from:
        try:
            from_dt = dt_type.fromisoformat(date_from.replace("Z", "+00:00"))
            query = query.filter(AccountingCashExpense.date >= from_dt.date())
        except Exception:
            pass
    if date_to:
        try:
            to_dt = dt_type.fromisoformat(date_to.replace("Z", "+00:00"))
            query = query.filter(AccountingCashExpense.date <= to_dt.date())
        except Exception:
            pass

    total = query.count()

    if sort_column and hasattr(AccountingCashExpense, sort_column):
        order_attr = getattr(AccountingCashExpense, sort_column)
        if sort_dir == "desc":
            query = query.order_by(desc(order_attr))
        else:
            query = query.order_by(asc(order_attr))

    rows_db = query.offset(offset).limit(limit).all()

    def _serialize(cash: AccountingCashExpense) -> Dict[str, Any]:
        row: Dict[str, Any] = {}
        for col in selected_cols:
            try:
                value = getattr(cash, col, None)
                if isinstance(value, dt_type):
                    row[col] = value.isoformat()
                elif isinstance(value, Decimal):
                    row[col] = float(value)
                else:
                    row[col] = value
            except Exception:
                row[col] = None
        return row

    rows = [_serialize(r) for r in rows_db]

    return {
        "rows": rows,
        "limit": limit,
        "offset": offset,
        "total": total,
        "sort": {"column": sort_column, "direction": sort_dir} if sort_column else None,
    }
