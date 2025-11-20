from __future__ import annotations

from typing import Dict, Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
import uuid

from app.models_sqlalchemy import get_db
from app.models_sqlalchemy.models import UserGridLayout
from app.services.auth import get_current_active_user
from app.models.user import User


router = APIRouter(prefix="/api/grids", tags=["grids"])


class ColumnMeta(BaseModel):
  name: str
  label: str
  type: str = "string"
  width_default: int = 150
  sortable: bool = True


# Column definitions per grid
# Orders grid: one row per order_line_items record (public.order_line_items).
ORDERS_COLUMNS_META: List[ColumnMeta] = [
  ColumnMeta(name="created_at", label="Created at", type="datetime", width_default=180),
  ColumnMeta(name="order_id", label="Order ID", type="string", width_default=220),
  ColumnMeta(name="line_item_id", label="Line item ID", type="string", width_default=220),
  ColumnMeta(name="sku", label="SKU", type="string", width_default=160),
  ColumnMeta(name="title", label="Title", type="string", width_default=260),
  ColumnMeta(name="quantity", label="Qty", type="number", width_default=80),
  ColumnMeta(name="total_value", label="Total value", type="money", width_default=140),
  ColumnMeta(name="currency", label="Currency", type="string", width_default=80),
  ColumnMeta(name="ebay_account_id", label="eBay account", type="string", width_default=200),
  ColumnMeta(name="ebay_user_id", label="eBay user", type="string", width_default=200),
]

# Transactions grid: backed by public.ebay_transactions.
TRANSACTIONS_COLUMNS_META: List[ColumnMeta] = [
  ColumnMeta(name="transaction_date", label="Transaction date", type="string", width_default=200),
  ColumnMeta(name="transaction_id", label="Transaction ID", type="string", width_default=220),
  ColumnMeta(name="order_id", label="Order ID", type="string", width_default=200),
  ColumnMeta(name="transaction_type", label="Type", type="string", width_default=140),
  ColumnMeta(name="transaction_status", label="Status", type="string", width_default=140),
  ColumnMeta(name="amount", label="Amount", type="money", width_default=120),
  ColumnMeta(name="currency", label="Currency", type="string", width_default=80),
  ColumnMeta(name="created_at", label="Created at", type="datetime", width_default=180),
  ColumnMeta(name="updated_at", label="Updated at", type="datetime", width_default=180),
  ColumnMeta(name="ebay_account_id", label="eBay account", type="string", width_default=200),
  ColumnMeta(name="ebay_user_id", label="eBay user", type="string", width_default=200),
]

MESSAGES_COLUMNS_META: List[ColumnMeta] = [
  ColumnMeta(name="created_at", label="Created at", type="datetime", width_default=180),
  ColumnMeta(name="message_date", label="Message date", type="datetime", width_default=180),
  ColumnMeta(name="direction", label="Direction", type="string", width_default=100),
  ColumnMeta(name="message_type", label="Type", type="string", width_default=120),
  ColumnMeta(name="sender_username", label="From", type="string", width_default=180),
  ColumnMeta(name="recipient_username", label="To", type="string", width_default=180),
  ColumnMeta(name="subject", label="Subject", type="string", width_default=260),
  ColumnMeta(name="is_read", label="Read", type="boolean", width_default=80),
  ColumnMeta(name="is_flagged", label="Flagged", type="boolean", width_default=90),
  ColumnMeta(name="is_archived", label="Archived", type="boolean", width_default=90),
  ColumnMeta(name="order_id", label="Order ID", type="string", width_default=160),
  ColumnMeta(name="listing_id", label="Listing ID", type="string", width_default=160),
]

OFFERS_COLUMNS_META: List[ColumnMeta] = [
  ColumnMeta(name="created_at", label="Created at", type="datetime", width_default=180),
  ColumnMeta(name="offer_id", label="Offer ID", type="string", width_default=220),
  ColumnMeta(name="direction", label="Direction", type="string", width_default=100),
  ColumnMeta(name="state", label="State", type="string", width_default=120),
  ColumnMeta(name="item_id", label="Item ID", type="string", width_default=160),
  ColumnMeta(name="sku", label="SKU", type="string", width_default=140),
  ColumnMeta(name="buyer_username", label="Buyer", type="string", width_default=180),
  ColumnMeta(name="quantity", label="Qty", type="number", width_default=80),
  ColumnMeta(name="price_value", label="Price", type="money", width_default=120),
  ColumnMeta(name="price_currency", label="Currency", type="string", width_default=80),
  ColumnMeta(name="original_price_value", label="Original price", type="money", width_default=140),
  ColumnMeta(name="original_price_currency", label="Original currency", type="string", width_default=120),
  ColumnMeta(name="expires_at", label="Expires at", type="datetime", width_default=180),
]

# SKU catalog grid: logical view over the SQ catalog (sq_items) table.
# Used by the LISTING tab and the main SKU tab.
SKU_CATALOG_COLUMNS_META: List[ColumnMeta] = [
  ColumnMeta(name="id", label="ID", type="number", width_default=60),
  ColumnMeta(name="sku_code", label="SKU", type="string", width_default=160),
  ColumnMeta(name="sku", label="SKU (raw)", type="string", width_default=160),
  ColumnMeta(name="sku2", label="SKU2", type="string", width_default=160),
  ColumnMeta(name="model", label="Model", type="string", width_default=180),
  ColumnMeta(name="model_id", label="Model ID", type="number", width_default=120),
  ColumnMeta(name="part", label="Part", type="string", width_default=220),
  ColumnMeta(name="category", label="Category", type="string", width_default=140),
  ColumnMeta(name="condition_id", label="Condition ID", type="number", width_default=120),
  ColumnMeta(name="condition_description", label="Condition desc", type="string", width_default=220),
  ColumnMeta(name="part_number", label="Part #", type="string", width_default=160),
  ColumnMeta(name="mpn", label="MPN", type="string", width_default=160),
  ColumnMeta(name="upc", label="UPC", type="string", width_default=160),
  ColumnMeta(name="price", label="Price", type="money", width_default=120),
  ColumnMeta(name="previous_price", label="Prev price", type="money", width_default=120),
  ColumnMeta(name="brutto", label="Brutto", type="money", width_default=120),
  ColumnMeta(name="shipping_type", label="Shipping type", type="string", width_default=140),
  ColumnMeta(name="shipping_group", label="Shipping group", type="string", width_default=140),
  ColumnMeta(name="shipping_group_previous", label="Prev ship group", type="string", width_default=160),
  ColumnMeta(name="alert_flag", label="Alert", type="boolean", width_default=80),
  ColumnMeta(name="alert_message", label="Alert message", type="string", width_default=260),
  ColumnMeta(name="record_status", label="Record status", type="string", width_default=140),
  ColumnMeta(name="record_status_flag", label="Status flag", type="boolean", width_default=100),
  ColumnMeta(name="checked_status", label="Checked status", type="string", width_default=140),
  ColumnMeta(name="checked", label="Checked", type="boolean", width_default=80),
  ColumnMeta(name="checked_by", label="Checked by", type="string", width_default=140),
  ColumnMeta(name="title", label="Title", type="string", width_default=260),
  ColumnMeta(name="brand", label="Brand", type="string", width_default=160),
  ColumnMeta(name="warehouse_id", label="Warehouse", type="number", width_default=120),
  ColumnMeta(name="storage_alias", label="Storage alias", type="string", width_default=140),
  ColumnMeta(name="pic_url1", label="Pic 1", type="string", width_default=200),
  ColumnMeta(name="pic_url2", label="Pic 2", type="string", width_default=200),
  ColumnMeta(name="pic_url3", label="Pic 3", type="string", width_default=200),
  ColumnMeta(name="image_url", label="Image URL", type="string", width_default=220),
  ColumnMeta(name="description", label="Description", type="string", width_default=260),
  ColumnMeta(name="record_created_by", label="Created by", type="string", width_default=160),
  ColumnMeta(name="rec_created", label="Created", type="datetime", width_default=180),
  ColumnMeta(name="record_updated_by", label="Updated by", type="string", width_default=160),
  ColumnMeta(name="rec_updated", label="Updated", type="datetime", width_default=180),
]

ACTIVE_INVENTORY_COLUMNS_META: List[ColumnMeta] = [
  ColumnMeta(name="last_seen_at", label="Last seen", type="datetime", width_default=180),
  ColumnMeta(name="sku", label="SKU", type="string", width_default=160),
  ColumnMeta(name="item_id", label="Item ID", type="string", width_default=180),
  ColumnMeta(name="title", label="Title", type="string", width_default=260),
  ColumnMeta(name="quantity_available", label="Qty", type="number", width_default=80),
  ColumnMeta(name="price", label="Price", type="money", width_default=120),
  ColumnMeta(name="currency", label="Currency", type="string", width_default=80),
  ColumnMeta(name="listing_status", label="Status", type="string", width_default=120),
  ColumnMeta(name="ebay_account_id", label="eBay account", type="string", width_default=200),
]

# Inventory grid: direct view over the main inventory table (tbl.parts_inventory equivalent).
INVENTORY_COLUMNS_META: List[ColumnMeta] = [
  ColumnMeta(name="id", label="ID", type="number", width_default=70),
  ColumnMeta(name="sku_id", label="SKU ID", type="number", width_default=90),
  ColumnMeta(name="sku_code", label="SKU", type="string", width_default=150),
  ColumnMeta(name="model", label="Model", type="string", width_default=200),
  ColumnMeta(name="category", label="Category", type="string", width_default=140),
  ColumnMeta(name="condition", label="Condition", type="string", width_default=120),
  ColumnMeta(name="part_number", label="Part #", type="string", width_default=140),
  ColumnMeta(name="title", label="Title", type="string", width_default=260),
  ColumnMeta(name="price_value", label="Price", type="money", width_default=120),
  ColumnMeta(name="price_currency", label="Currency", type="string", width_default=80),
  ColumnMeta(name="ebay_listing_id", label="eBay listing ID", type="string", width_default=180),
  ColumnMeta(name="ebay_status", label="eBay status", type="string", width_default=130),
  ColumnMeta(name="status", label="Status", type="string", width_default=120),
  ColumnMeta(name="photo_count", label="Photos", type="number", width_default=80),
  ColumnMeta(name="notes", label="Notes", type="string", width_default=220),
  ColumnMeta(name="storage_id", label="Storage ID", type="string", width_default=120),
  ColumnMeta(name="storage", label="Storage", type="string", width_default=120),
  ColumnMeta(name="warehouse_id", label="Warehouse ID", type="number", width_default=110),
  ColumnMeta(name="quantity", label="Qty", type="number", width_default=70),
  ColumnMeta(name="rec_created", label="Created", type="datetime", width_default=180),
  ColumnMeta(name="rec_updated", label="Updated", type="datetime", width_default=180),
  ColumnMeta(name="author", label="Author", type="string", width_default=140),
  ColumnMeta(name="buyer_info", label="Buyer info", type="string", width_default=220),
  ColumnMeta(name="tracking_number", label="Tracking #", type="string", width_default=160),
  ColumnMeta(name="raw_payload", label="Raw payload", type="string", width_default=260),
]

ACCOUNTING_BANK_STATEMENTS_COLUMNS_META: List[ColumnMeta] = [
  ColumnMeta(name="id", label="ID", type="number", width_default=80),
  ColumnMeta(name="statement_period_start", label="Period start", type="date", width_default=140),
  ColumnMeta(name="statement_period_end", label="Period end", type="date", width_default=140),
  ColumnMeta(name="bank_name", label="Bank", type="string", width_default=160),
  ColumnMeta(name="account_last4", label="Last4", type="string", width_default=80),
  ColumnMeta(name="currency", label="Currency", type="string", width_default=80),
  ColumnMeta(name="rows_count", label="Rows", type="number", width_default=80),
  ColumnMeta(name="status", label="Status", type="string", width_default=120),
  ColumnMeta(name="created_at", label="Created at", type="datetime", width_default=180),
]

ACCOUNTING_CASH_EXPENSES_COLUMNS_META: List[ColumnMeta] = [
  ColumnMeta(name="id", label="ID", type="number", width_default=80),
  ColumnMeta(name="date", label="Date", type="date", width_default=140),
  ColumnMeta(name="amount", label="Amount", type="money", width_default=120),
  ColumnMeta(name="currency", label="Currency", type="string", width_default=80),
  ColumnMeta(name="expense_category_id", label="Category", type="string", width_default=140),
  ColumnMeta(name="counterparty", label="Counterparty", type="string", width_default=200),
  ColumnMeta(name="description", label="Description", type="string", width_default=260),
  ColumnMeta(name="storage_id", label="Storage", type="string", width_default=140),
  ColumnMeta(name="paid_by_user_id", label="Paid by", type="string", width_default=160),
  ColumnMeta(name="created_by_user_id", label="Created by", type="string", width_default=160),
]

ACCOUNTING_TRANSACTIONS_COLUMNS_META: List[ColumnMeta] = [
  ColumnMeta(name="id", label="ID", type="number", width_default=80),
  ColumnMeta(name="date", label="Date", type="date", width_default=140),
  ColumnMeta(name="direction", label="Direction", type="string", width_default=100),
  ColumnMeta(name="amount", label="Amount", type="money", width_default=120),
  ColumnMeta(name="account_name", label="Account", type="string", width_default=180),
  ColumnMeta(name="counterparty", label="Counterparty", type="string", width_default=200),
  ColumnMeta(name="expense_category_id", label="Category", type="string", width_default=140),
  ColumnMeta(name="storage_id", label="Storage", type="string", width_default=140),
  ColumnMeta(name="source_type", label="Source type", type="string", width_default=140),
  ColumnMeta(name="is_personal", label="Personal", type="boolean", width_default=100),
  ColumnMeta(name="is_internal_transfer", label="Internal transfer", type="boolean", width_default=150),
  ColumnMeta(name="description", label="Description", type="string", width_default=260),
]

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
  ColumnMeta(name="ebay_account_id", label="eBay account", type="string", width_default=200),
]

FINANCES_COLUMNS_META: List[ColumnMeta] = [
  ColumnMeta(name="booking_date", label="Date", type="datetime", width_default=180),
  ColumnMeta(name="ebay_account_id", label="eBay account", type="string", width_default=200),
  ColumnMeta(name="transaction_type", label="Type", type="string", width_default=140),
  ColumnMeta(name="transaction_status", label="Status", type="string", width_default=140),
  ColumnMeta(name="order_id", label="Order ID", type="string", width_default=200),
  ColumnMeta(name="transaction_id", label="Transaction ID", type="string", width_default=220),
  ColumnMeta(name="transaction_amount_value", label="Amount", type="money", width_default=140),
  ColumnMeta(name="transaction_amount_currency", label="Currency", type="string", width_default=80),
  ColumnMeta(name="final_value_fee", label="Final value fee", type="money", width_default=140),
  ColumnMeta(name="promoted_listing_fee", label="Promoted listing fee", type="money", width_default=160),
  ColumnMeta(name="shipping_label_fee", label="Shipping label fee", type="money", width_default=160),
  ColumnMeta(name="other_fees", label="Other fees", type="money", width_default=140),
  ColumnMeta(name="total_fees", label="Total fees", type="money", width_default=140),
]

FINANCES_FEES_COLUMNS_META: List[ColumnMeta] = [
  ColumnMeta(name="id", label="ID", type="number", width_default=80),
  ColumnMeta(name="created_at", label="Created at", type="datetime", width_default=180),
  ColumnMeta(name="updated_at", label="Updated at", type="datetime", width_default=180),
  ColumnMeta(name="ebay_account_id", label="eBay account", type="string", width_default=200),
  ColumnMeta(name="transaction_id", label="Transaction ID", type="string", width_default=220),
  ColumnMeta(name="fee_type", label="Fee type", type="string", width_default=200),
  ColumnMeta(name="amount_value", label="Amount", type="money", width_default=140),
  ColumnMeta(name="amount_currency", label="Currency", type="string", width_default=80),
  ColumnMeta(name="raw_payload", label="Raw payload", type="string", width_default=400),
]

# Buying grid: logical view over ebay_buyer (legacy tbl_ebay_buyer equivalent).
BUYING_COLUMNS_META: List[ColumnMeta] = [
  ColumnMeta(name="id", label="ID", type="number", width_default=80),
  ColumnMeta(name="tracking_number", label="Tracking #", type="string", width_default=180),
  ColumnMeta(name="refund_flag", label="Refund", type="boolean", width_default=80),
  ColumnMeta(name="storage", label="Storage", type="string", width_default=120),
  ColumnMeta(name="profit", label="Profit", type="money", width_default=120),
  ColumnMeta(name="buyer_id", label="Buyer (eBay)", type="string", width_default=160),
  ColumnMeta(name="seller_id", label="Seller ID", type="string", width_default=160),
  ColumnMeta(name="paid_time", label="Paid time", type="datetime", width_default=180),
  ColumnMeta(name="amount_paid", label="Amount paid", type="money", width_default=140),
  ColumnMeta(name="days_since_paid", label="Days", type="number", width_default=80),
  ColumnMeta(name="status_label", label="Status", type="string", width_default=160),
  ColumnMeta(name="record_created_at", label="Rec created", type="datetime", width_default=180),
  ColumnMeta(name="title", label="Title", type="string", width_default=260),
  ColumnMeta(name="comment", label="Comment", type="string", width_default=260),
]


GRID_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "orders": {
        "visible_columns": [
            "created_at",
            "order_id",
            "line_item_id",
            "sku",
            "title",
            "quantity",
            "total_value",
            "currency",
        ],
        "sort": {"column": "created_at", "direction": "desc"},
    },
    "transactions": {
        "visible_columns": [
            "transaction_date",
            "transaction_id",
            "order_id",
            "transaction_type",
            "transaction_status",
            "amount",
            "currency",
        ],
        "sort": {"column": "transaction_date", "direction": "desc"},
    },
    "messages": {
        "visible_columns": [
            "message_date",
            "direction",
            "message_type",
            "sender_username",
            "recipient_username",
            "subject",
            "is_read",
            "is_flagged",
        ],
        "sort": {"column": "message_date", "direction": "desc"},
    },
    "offers": {
        "visible_columns": [
            "created_at",
            "offer_id",
            "direction",
            "state",
            "item_id",
            "sku",
            "buyer_username",
            "quantity",
            "price_value",
            "price_currency",
            "expires_at",
        ],
        "sort": {"column": "created_at", "direction": "desc"},
    },
    "sku_catalog": {
        "visible_columns": [
            "id",
            "sku_code",
            "model",
            "category",
            "condition_id",
            "part",
            "part_number",
            "price",
            "shipping_group",
            "alert_flag",
            "title",
            "brand",
            "pic_url1",
            "rec_created",
            "rec_updated",
        ],
        "sort": {"column": "rec_updated", "direction": "desc"},
    },
    "active_inventory": {
        "visible_columns": [
            "last_seen_at",
            "sku",
            "item_id",
            "title",
            "quantity_available",
            "price",
            "currency",
            "listing_status",
            "ebay_account_id",
        ],
        "sort": {"column": "last_seen_at", "direction": "desc"},
    },
    "inventory": {
        "visible_columns": [
            "id",
            "sku_code",
            "status",
            "ebay_status",
            "storage_id",
            "model",
            "category",
            "part_number",
            "title",
            "price_value",
            "price_currency",
            "quantity",
            "rec_created",
            "author",
        ],
        "sort": {"column": "rec_created", "direction": "desc"},
    },
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
            "ebay_account_id",
        ],
        "sort": {"column": "open_date", "direction": "desc"},
    },
    "finances": {
        "visible_columns": [
            "booking_date",
            "ebay_account_id",
            "transaction_type",
            "transaction_status",
            "order_id",
            "transaction_id",
            "transaction_amount_value",
            "transaction_amount_currency",
            "final_value_fee",
            "promoted_listing_fee",
            "shipping_label_fee",
            "total_fees",
        ],
        "sort": {"column": "booking_date", "direction": "desc"},
    },
    "finances_fees": {
        "visible_columns": [
            "created_at",
            "ebay_account_id",
            "transaction_id",
            "fee_type",
            "amount_value",
            "amount_currency",
            "raw_payload",
        ],
        "sort": {"column": "created_at", "direction": "desc"},
    },
    "buying": {
        "visible_columns": [
            "id",
            "tracking_number",
            "refund_flag",
            "storage",
            "profit",
            "buyer_id",
            "seller_id",
            "paid_time",
            "amount_paid",
            "days_since_paid",
            "status_label",
            "record_created_at",
            "title",
            "comment",
        ],
        "sort": {"column": "paid_time", "direction": "desc"},
    },
    "accounting_bank_statements": {
        "visible_columns": [
            "statement_period_start",
            "statement_period_end",
            "bank_name",
            "account_last4",
            "currency",
            "rows_count",
            "status",
            "created_at",
        ],
        "sort": {"column": "statement_period_start", "direction": "desc"},
    },
    "accounting_cash_expenses": {
        "visible_columns": [
            "date",
            "amount",
            "currency",
            "expense_category_id",
            "counterparty",
            "description",
            "storage_id",
            "paid_by_user_id",
        ],
        "sort": {"column": "date", "direction": "desc"},
    },
    "accounting_transactions": {
        "visible_columns": [
            "date",
            "direction",
            "amount",
            "account_name",
            "counterparty",
            "expense_category_id",
            "storage_id",
            "source_type",
            "is_personal",
            "is_internal_transfer",
            "description",
        ],
        "sort": {"column": "date", "direction": "desc"},
    },
}



def _columns_meta_for_grid(grid_key: str) -> List[ColumnMeta]:
    if grid_key == "orders":
        return ORDERS_COLUMNS_META
    if grid_key == "transactions":
        return TRANSACTIONS_COLUMNS_META
    if grid_key == "messages":
        return MESSAGES_COLUMNS_META
    if grid_key == "offers":
        return OFFERS_COLUMNS_META
    if grid_key == "sku_catalog":
        return SKU_CATALOG_COLUMNS_META
    if grid_key == "active_inventory":
        return ACTIVE_INVENTORY_COLUMNS_META
    if grid_key == "inventory":
        return INVENTORY_COLUMNS_META
    if grid_key == "cases":
        return CASES_COLUMNS_META
    if grid_key == "finances":
        return FINANCES_COLUMNS_META
    if grid_key == "finances_fees":
        return FINANCES_FEES_COLUMNS_META
    if grid_key == "buying":
        return BUYING_COLUMNS_META
    if grid_key == "accounting_bank_statements":
        return ACCOUNTING_BANK_STATEMENTS_COLUMNS_META
    if grid_key == "accounting_cash_expenses":
        return ACCOUNTING_CASH_EXPENSES_COLUMNS_META
    if grid_key == "accounting_transactions":
        return ACCOUNTING_TRANSACTIONS_COLUMNS_META
    return []

def _allowed_columns_for_grid(grid_key: str) -> List[str]:
    return [c.name for c in _columns_meta_for_grid(grid_key)]


class GridSort(BaseModel):
    column: str
    direction: str = Field("desc", pattern="^(asc|desc)$")


class GridLayoutResponse(BaseModel):
    grid_key: str
    available_columns: List[ColumnMeta]
    visible_columns: List[str]
    column_widths: Dict[str, int]
    sort: Optional[GridSort] = None
    is_default: bool = False


class GridLayoutUpdate(BaseModel):
    visible_columns: List[str]
    column_widths: Dict[str, int] = {}
    sort: Optional[GridSort] = None


@router.get("/{grid_key}/layout", response_model=GridLayoutResponse)
async def get_grid_layout(
    grid_key: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> GridLayoutResponse:
    allowed_cols = _allowed_columns_for_grid(grid_key)
    if not allowed_cols:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown grid_key")

    layout: UserGridLayout | None = (
        db.query(UserGridLayout)
        .filter(UserGridLayout.user_id == current_user.id, UserGridLayout.grid_key == grid_key)
        .first()
    )

    available_columns = _columns_meta_for_grid(grid_key)

    if layout:
        return GridLayoutResponse(
            grid_key=grid_key,
            available_columns=available_columns,
            visible_columns=layout.visible_columns or allowed_cols,
            column_widths=layout.column_widths or {},
            sort=layout.sort or GRID_DEFAULTS.get(grid_key, {}).get("sort"),
            is_default=False,
        )

    # No user-specific layout yet -> return defaults
    defaults = GRID_DEFAULTS.get(grid_key, {})
    visible_columns = [c for c in defaults.get("visible_columns", allowed_cols) if c in allowed_cols]
    sort_cfg = defaults.get("sort")
    return GridLayoutResponse(
        grid_key=grid_key,
        available_columns=available_columns,
        visible_columns=visible_columns or allowed_cols,
        column_widths={},
        sort=sort_cfg,
        is_default=True,
    )


@router.put("/{grid_key}/layout", response_model=GridLayoutResponse)
async def update_grid_layout(
    grid_key: str,
    payload: GridLayoutUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> GridLayoutResponse:
    allowed_cols = _allowed_columns_for_grid(grid_key)
    if not allowed_cols:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown grid_key")

    # Validate visible_columns
    invalid = [c for c in payload.visible_columns if c not in allowed_cols]
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid columns for grid {grid_key}: {', '.join(invalid)}",
        )

    # Filter column_widths against allowed columns
    filtered_widths: Dict[str, int] = {
        k: int(v)
        for k, v in payload.column_widths.items()
        if k in allowed_cols
    }

    # Validate sort
    sort_dict: Optional[Dict[str, Any]] = None
    if payload.sort:
        if payload.sort.column not in allowed_cols:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid sort column: {payload.sort.column}",
            )
        sort_dict = payload.sort.dict()

    layout: UserGridLayout | None = (
        db.query(UserGridLayout)
        .filter(UserGridLayout.user_id == current_user.id, UserGridLayout.grid_key == grid_key)
        .first()
    )

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)

    if layout:
        layout.visible_columns = payload.visible_columns
        layout.column_widths = filtered_widths
        layout.sort = sort_dict
        layout.updated_at = now
    else:
        layout = UserGridLayout(
            id=str(uuid.uuid4()),
            user_id=current_user.id,
            grid_key=grid_key,
            visible_columns=payload.visible_columns,
            column_widths=filtered_widths,
            sort=sort_dict,
            created_at=now,
            updated_at=now,
        )
        db.add(layout)

    db.commit()
    db.refresh(layout)

    available_columns = _columns_meta_for_grid(grid_key)

    return GridLayoutResponse(
        grid_key=grid_key,
        available_columns=available_columns,
        visible_columns=layout.visible_columns or allowed_cols,
        column_widths=layout.column_widths or {},
        sort=layout.sort,
        is_default=False,
    )
