from __future__ import annotations

from typing import Dict, Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, asc
from sqlalchemy.orm import Session
import enum

from app.database import get_db
from app.db_models.order import Order
from app.models_sqlalchemy import get_db as get_db_sqla
from app.models_sqlalchemy.models import Transaction, Message as EbayMessage, Offer as OfferModel, OfferState, OfferDirection
from app.services.auth import get_current_user
from app.models.user import User as UserModel
from app.routers.grid_layouts import _allowed_columns_for_grid

router = APIRouter(prefix="/api/grids", tags=["grids_data"])


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
        default_sort_col = "order_date"
    elif grid_key == "transactions":
        default_sort_col = "sale_date"
    elif grid_key == "messages":
        default_sort_col = "message_date"
    elif grid_key == "offers":
        default_sort_col = "created_at"

    sort_column = sort_by if sort_by in allowed_cols else default_sort_col

    if grid_key == "orders":
        return await _get_orders_data(db, current_user, requested_cols, limit, offset, sort_column, sort_dir)
    elif grid_key == "transactions":
        # Use separate SQLAlchemy session for models_sqlalchemy
        db_sqla = next(get_db_sqla())
        try:
            return _get_transactions_data(db_sqla, current_user, requested_cols, limit, offset, sort_column, sort_dir)
        finally:
            db_sqla.close()
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
    query = db.query(Order).filter(Order.user_id == current_user.id)
    total = query.count()

    if sort_column:
        order_attr = getattr(Order, sort_column)
        if sort_dir == "desc":
            query = query.order_by(desc(order_attr))
        else:
            query = query.order_by(asc(order_attr))

    rows_db: List[Order] = query.offset(offset).limit(limit).all()

    from datetime import datetime as dt_type
    from decimal import Decimal

    def _serialize(o: Order) -> Dict[str, Any]:
        row: Dict[str, Any] = {}
        for col in selected_cols:
            value = getattr(o, col, None)
            if isinstance(value, dt_type):
                row[col] = value.isoformat()
            elif isinstance(value, Decimal):
                row[col] = float(value)
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


def _get_transactions_data(
    db: Session,
    current_user: UserModel,
    selected_cols: List[str],
    limit: int,
    offset: int,
    sort_column: Optional[str],
    sort_dir: str,
) -> Dict[str, Any]:
    query = db.query(Transaction).filter(Transaction.user_id == current_user.id)
    total = query.count()

    if sort_column:
        order_attr = getattr(Transaction, sort_column)
        if sort_dir == "desc":
            query = query.order_by(desc(order_attr))
        else:
            query = query.order_by(asc(order_attr))

    rows_db: List[Transaction] = query.offset(offset).limit(limit).all()

    from datetime import datetime as dt_type
    from decimal import Decimal

    def _serialize(t: Transaction) -> Dict[str, Any]:
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

    if actual_folder == "inbox":
        query = query.filter(EbayMessage.direction == "INCOMING", EbayMessage.is_archived == False)  # noqa: E712
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
