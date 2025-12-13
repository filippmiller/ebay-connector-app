from __future__ import annotations

from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, asc
from sqlalchemy.orm import Session

from app.database import get_db
from app.db_models.order import Order
from app.services.auth import get_current_user
from app.models.user import User as UserModel

router = APIRouter(prefix="/api/orders", tags=["orders_api"])

# Whitelist of columns that can be selected / sorted on
ORDERS_ALLOWED_COLUMNS: List[str] = [
    "id",
    "created_at",
    "order_id",
    "order_status",
    "order_date",
    "last_modified_date",
    "buyer_username",
    "buyer_email",
    "total_amount",
    "shipping_cost",
    "tax_amount",
    "currency_code",
    "shipping_carrier",
    "tracking_number",
    "payment_date",
    "payout_date",
]

DEFAULT_ORDERS_COLUMNS: List[str] = [
    "created_at",
    "order_id",
    "order_status",
    "buyer_username",
    "buyer_email",
    "total_amount",
    "shipping_cost",
    "tax_amount",
    "shipping_carrier",
    "tracking_number",
]


@router.get("")
async def list_orders(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    sort_by: str = Query("order_date", pattern="^(order_date|created_at|total_amount|buyer_username|order_id)$"),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    columns: Optional[str] = Query(None, description="Comma-separated list of columns to include"),
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Paginated listing of orders for current user.

    - Only whitelisted columns can be requested.
    - Response is shape: { rows, limit, offset, total }.
    """

    base_query = db.query(Order).filter(Order.user_id == current_user.id)
    total = base_query.count()

    order_col = getattr(Order, sort_by)
    if sort_dir == "desc":
        base_query = base_query.order_by(desc(order_col))
    else:
        base_query = base_query.order_by(asc(order_col))

    rows_db: List[Order] = base_query.offset(offset).limit(limit).all()

    # Determine which columns to include
    if columns:
        requested = [c.strip() for c in columns.split(",") if c.strip()]
        selected_cols = [c for c in requested if c in ORDERS_ALLOWED_COLUMNS]
        if not selected_cols:
            selected_cols = DEFAULT_ORDERS_COLUMNS
    else:
        selected_cols = DEFAULT_ORDERS_COLUMNS

    def _serialize(order: Order) -> Dict[str, Any]:
        row: Dict[str, Any] = {}
        for col in selected_cols:
            value = getattr(order, col, None)
            # Normalize datetimes and decimals
            from datetime import datetime as dt_type
            from decimal import Decimal

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
    }