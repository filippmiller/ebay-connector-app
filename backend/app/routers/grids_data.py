from __future__ import annotations

from typing import Dict, Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, asc
from sqlalchemy.orm import Session
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
    ItemCondition,
    SKU,
)
from app.services.auth import get_current_user
from app.models.user import User as UserModel
from app.routers.grid_layouts import _allowed_columns_for_grid

router = APIRouter(prefix="/api/grids", tags=["grids_data"])


@router.get("/buying/rows")
async def get_buying_rows(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    sort_by: Optional[str] = Query("paid_time"),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
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
        )
        return {
            "rows": data.get("rows", []),
            "total": data.get("total", 0),
            "page": page,
            "page_size": page_size,
        }
    finally:
        db_sqla.close()


@router.get("/{grid_key}/data")
async def get_grid_data(
    grid_key: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    sort_by: Optional[str] = Query(None),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    columns: Optional[str] = Query(None, description="Comma-separated list of columns to include"),
    # Offers-specific filters (mirroring /offers)
    state: Optional[str] = Query(None),
    direction: Optional[str] = Query(None),
    buyer: Optional[str] = Query(None),
    item_id: Optional[str] = Query(None),
    sku: Optional[str] = Query(None),
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
    # Finances-specific filters
    transaction_type: Optional[str] = Query(None),
    # Messages-specific filters (mirroring /messages)
    folder: Optional[str] = Query(None),
    unread_only: bool = False,
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

    # Determine sort column
    default_sort_col = None
    if grid_key == "orders":
        default_sort_col = "created_at"
    elif grid_key == "transactions":
        default_sort_col = "transaction_date"
    elif grid_key == "messages":
        default_sort_col = "message_date"
    elif grid_key == "offers":
        default_sort_col = "created_at"
    elif grid_key == "finances":
        default_sort_col = "booking_date"
    elif grid_key == "finances_fees":
        default_sort_col = "created_at"

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
            )
        finally:
            db_sqla.close()
    elif grid_key == "accounting_bank_statements":
        db_sqla = next(get_db_sqla())
        try:
            return _get_accounting_bank_statements_data(
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
            value = getattr(li, col, None)
            if isinstance(value, dt_type):
                row[col] = value.isoformat()
            elif isinstance(value, Decimal):
                row[col] = float(value)
            else:
                row[col] = value
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
) -> Dict[str, Any]:
    """Buying grid backed by ebay_buyer joined to ebay_status_buyer.

    Exposes one row per ebay_buyer record (per account) filtered by the current
    org/user's eBay accounts. This is the backend for the BUYING tab grid.
    """
    from datetime import datetime as dt_type
    from decimal import Decimal

    from app.models_sqlalchemy.models import EbayBuyer, EbayStatusBuyer, EbayAccount

    # Scope rows to ebay_accounts that belong to the current org/user.
    query = (
        db.query(EbayBuyer, EbayStatusBuyer)
        .join(EbayAccount, EbayBuyer.ebay_account_id == EbayAccount.id)
        .outerjoin(EbayStatusBuyer, EbayBuyer.item_status_id == EbayStatusBuyer.id)
        .filter(EbayAccount.org_id == current_user.id)
    )

    total = query.count()

    # Sorting: allow a small, safe subset of real columns.
    allowed_sort_cols = {
        "paid_time": EbayBuyer.paid_time,
        "record_created_at": EbayBuyer.record_created_at,
        "buyer_id": EbayBuyer.buyer_id,
        "seller_id": EbayBuyer.seller_id,
        "profit": EbayBuyer.profit,
    }
    sort_attr = allowed_sort_cols.get(sort_column or "")
    if sort_attr is None:
        sort_attr = EbayBuyer.paid_time
    if sort_dir == "desc":
        query = query.order_by(desc(sort_attr))
    else:
        query = query.order_by(asc(sort_attr))

    rows_db: List[tuple] = query.offset(offset).limit(limit).all()

    def _serialize(buyer: EbayBuyer, status: Optional[EbayStatusBuyer]) -> Dict[str, Any]:
        row: Dict[str, Any] = {}

        # Derived fields for the grid
        days_since_paid: Optional[int] = None
        if buyer.paid_time:
            delta = dt_type.utcnow().replace(tzinfo=None) - buyer.paid_time.replace(tzinfo=None)
            days_since_paid = max(int(delta.days), 0)

        amount_paid = buyer.total_transaction_price or buyer.current_price

        base_values: Dict[str, Any] = {
            "id": buyer.id,
            "tracking_number": buyer.tracking_number,
            "refund_flag": buyer.refund_flag,
            "storage": buyer.storage,
            "profit": float(buyer.profit) if isinstance(buyer.profit, Decimal) else buyer.profit,
            "buyer_id": buyer.buyer_id,
            "seller_id": buyer.seller_id,
            "paid_time": buyer.paid_time,
            "amount_paid": float(amount_paid) if isinstance(amount_paid, Decimal) else amount_paid,
            "days_since_paid": days_since_paid,
            "status_label": status.label if status else None,
            "record_created_at": buyer.record_created_at,
            "title": buyer.title,
            "comment": buyer.comment,
        }

        for col in selected_cols:
            value = base_values.get(col)
            if isinstance(value, dt_type):
                row[col] = value.isoformat()
            else:
                row[col] = value
        return row

    rows = [_serialize(b, s) for (b, s) in rows_db]

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
) -> Dict[str, Any]:
    """SKU catalog grid backed by sq_items table.

    Simple read-only listing used by LISTING tab (and SKU tab), exposing a
    logical view over the richer SQ catalog data.
    """
    from datetime import datetime as dt_type
    from decimal import Decimal

    # Join to item_conditions to expose human-readable condition labels when
    # available, but keep the query cheap (simple left join, no extra filters).
    query = db.query(SqItem, ItemCondition).outerjoin(
        ItemCondition, SqItem.condition_id == ItemCondition.id
    )

    total = query.count()

    # Allow sorting on a small, safe subset of real columns.
    allowed_sort_cols = {
        "id": SqItem.id,
        "sku_code": SqItem.sku,
        "model": SqItem.model,
        "category": SqItem.category,
        "price": SqItem.price,
        "rec_updated": SqItem.record_updated,
    }
    sort_attr = allowed_sort_cols.get(sort_column or "rec_updated")
    if sort_attr is None:
        sort_attr = SqItem.record_updated
    if sort_dir == "desc":
        query = query.order_by(desc(sort_attr))
    else:
        query = query.order_by(asc(sort_attr))

    rows_db: List[tuple] = query.offset(offset).limit(limit).all()

    def _serialize(item: SqItem, cond: Optional[ItemCondition]) -> Dict[str, Any]:
        row: Dict[str, Any] = {}
        base_values: Dict[str, Any] = {
            "id": item.id,
            "sku_code": item.sku,
            "model": item.model,
            "category": item.category,
            "condition": cond.label if cond else None,
            "part_number": item.part_number,
            "price": item.price,
            "title": item.title,
            "description": item.description,
            "brand": item.brand,
            "rec_created": item.record_created,
            "rec_updated": item.record_updated,
        }
        for col in selected_cols:
            value = base_values.get(col)
            if isinstance(value, dt_type):
                row[col] = value.isoformat()
            elif isinstance(value, Decimal):
                row[col] = float(value)
            else:
                row[col] = value
        return row

    rows = [_serialize(item, cond) for (item, cond) in rows_db]

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
            value = getattr(t, col, None)
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
            value = getattr(o, col, None)
            if isinstance(value, dt_type):
                row[col] = value.isoformat()
            elif isinstance(value, Decimal):
                row[col] = float(value)
            elif isinstance(value, enum.Enum):
                row[col] = value.value
            else:
                row[col] = value
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
            d.ebay_user_id    AS ebay_user_id
        FROM ebay_disputes d
        WHERE d.user_id = :user_id
        UNION ALL
        SELECT
            'postorder_case'  AS kind,
            c.case_id         AS external_id,
            c.order_id        AS order_id,
            c.case_type       AS reason,
            c.case_status     AS status,
            c.open_date       AS open_date,
            c.close_date      AS respond_by_date,
            c.case_data       AS raw_payload,
            c.ebay_account_id AS ebay_account_id,
            c.ebay_user_id    AS ebay_user_id
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

        raw_payload = row.raw_payload
        try:
            payload = json.loads(raw_payload) if isinstance(raw_payload, str) else raw_payload or {}
        except Exception:
            payload = {}

        buyer_username = (
            payload.get("buyerUsername")
            or (payload.get("buyer") or {}).get("username")
            or (payload.get("buyer") or {}).get("userId")
        )

        amount = None
        currency = None
        try:
            mt_list = payload.get("monetaryTransactions") or []
            if mt_list:
                total_price = (mt_list[0] or {}).get("totalPrice") or {}
                amount = total_price.get("value")
                currency = total_price.get("currency")
        except Exception:
            pass

        if amount is None:
            claim = payload.get("claimAmount") or payload.get("disputeAmount") or {}
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
                "ebay_account_id": row.ebay_account_id,
                "ebay_user_id": row.ebay_user_id,
            }
        )

    # Simple filters
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
            value = getattr(ai, col, None)
            if isinstance(value, dt_type):
                row[col] = value.isoformat()
            elif isinstance(value, Decimal):
                row[col] = float(value)
            else:
                row[col] = value
        return row

    rows = [_serialize(ai) for ai in rows_db]

    return {
        "rows": rows,
        "limit": limit,
        "offset": offset,
        "total": total,
        "sort": {"column": sort_column, "direction": sort_dir} if sort_column else None,
    }
