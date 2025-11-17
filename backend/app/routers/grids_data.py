from __future__ import annotations

from typing import Dict, Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, asc
from sqlalchemy.orm import Session
import enum

from app.database import get_db
from app.db_models import Order, OrderLineItem, Transaction as EbayLegacyTransaction
from app.models_sqlalchemy import get_db as get_db_sqla
from app.models_sqlalchemy.models import Message as EbayMessage, Offer as OfferModel, OfferState, OfferDirection, ActiveInventory
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
        default_sort_col = "created_at"
    elif grid_key == "transactions":
        default_sort_col = "transaction_date"
    elif grid_key == "messages":
        default_sort_col = "message_date"
    elif grid_key == "offers":
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
    """Unified INR/SNAD Cases & Disputes grid backed by ebay_disputes + ebay_cases.

    We materialize rows for the current user and filter to INR/SNAD-like items
    in application code – expected volume is low so this stays cheap and avoids
    schema coupling.
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
        if not issue:
            continue

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
                "issue_type": issue,
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
