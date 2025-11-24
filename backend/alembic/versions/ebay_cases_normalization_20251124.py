"""Normalize ebay_cases with explicit columns for Post-Order cases

Revision ID: ebay_cases_normalization_20251124
Revises: 47a2e7eb9e6f
Create Date: 2025-11-24

This migration adds normalized columns to ebay_cases and backfills them from
existing case_data JSON payloads. The backfill is implemented row-by-row in
Python so that a single malformed JSON payload cannot abort the entire
migration; rows that fail JSON parsing are logged and left with NULLs in the
new columns.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Sequence, Union
from decimal import Decimal
from datetime import datetime
import json
import logging

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text as sa_text


# revision identifiers, used by Alembic.
revision: str = "ebay_cases_normalization_20251124"
down_revision: Union[str, Sequence[str], None] = "47a2e7eb9e6f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


LOGGER = logging.getLogger(__name__)
TABLE_NAME = "ebay_cases"


def _get_inspector() -> sa.Inspector:
    conn = op.get_bind()
    return sa.inspect(conn)


def _add_column_if_missing(table: str, column: sa.Column) -> None:
    """Idempotently add a column to a table if it does not already exist."""

    inspector = _get_inspector()
    existing_tables = set(inspector.get_table_names())
    if table not in existing_tables:
        return

    existing_cols = {c["name"] for c in inspector.get_columns(table)}
    if column.name in existing_cols:
        return

    op.add_column(table, column)


def _create_index_if_missing(table: str, index_name: str, *columns: str) -> None:
    """Idempotently create an index if it does not already exist."""

    inspector = _get_inspector()
    existing_tables = set(inspector.get_table_names())
    if table not in existing_tables:
        return

    existing_indexes = {ix["name"] for ix in inspector.get_indexes(table)}
    if index_name in existing_indexes:
        return

    op.create_index(index_name, table, list(columns))


def _drop_index_if_exists(table: str, index_name: str) -> None:
    inspector = _get_inspector()
    existing_tables = set(inspector.get_table_names())
    if table not in existing_tables:
        return

    existing_indexes = {ix["name"] for ix in inspector.get_indexes(table)}
    if index_name not in existing_indexes:
        return

    op.drop_index(index_name, table_name=table)


def _drop_column_if_exists(table: str, column_name: str) -> None:
    inspector = _get_inspector()
    existing_tables = set(inspector.get_table_names())
    if table not in existing_tables:
        return

    existing_cols = {c["name"] for c in inspector.get_columns(table)}
    if column_name not in existing_cols:
        return

    op.drop_column(table, column_name)


def _parse_money(money_obj: Optional[Dict[str, Any]]) -> tuple[Optional[Decimal], Optional[str]]:
    """Parse an eBay Money-like object into (value, currency)."""

    if not money_obj or not isinstance(money_obj, dict):
        return None, None
    value = money_obj.get("value")
    currency = money_obj.get("currency")
    if value is None:
        return None, currency
    try:
        return Decimal(str(value)), currency
    except Exception:
        return None, currency


def _parse_datetime(dt_string: Optional[str]) -> Optional[datetime]:
    """Parse ISO8601 datetime (possibly with trailing Z) into aware datetime.

    Mirrors the helper used in PostgresEbayDatabase so that timestamps stored
    here behave consistently with other ingestion pipelines.
    """

    if not dt_string:
        return None
    try:
        from dateutil import parser  # type: ignore[import]

        return parser.isoparse(dt_string)
    except Exception:
        try:
            # Fallback: basic fromisoformat with Z→+00:00 shim.
            return datetime.fromisoformat(dt_string.replace("Z", "+00:00"))
        except Exception:
            LOGGER.warning("Failed to parse datetime '%s' in ebay_cases backfill", dt_string)
            return None


def upgrade() -> None:
    """Add normalized columns to ebay_cases and backfill from case_data."""

    # 1) Schema changes – add nullable columns + indexes in an idempotent way.
    _add_column_if_missing(
        TABLE_NAME,
        sa.Column("item_id", sa.String(length=100), nullable=True),
    )
    _add_column_if_missing(
        TABLE_NAME,
        sa.Column("transaction_id", sa.String(length=100), nullable=True),
    )
    _add_column_if_missing(
        TABLE_NAME,
        sa.Column("buyer_username", sa.Text(), nullable=True),
    )
    _add_column_if_missing(
        TABLE_NAME,
        sa.Column("seller_username", sa.Text(), nullable=True),
    )
    _add_column_if_missing(
        TABLE_NAME,
        sa.Column("case_status_enum", sa.Text(), nullable=True),
    )
    _add_column_if_missing(
        TABLE_NAME,
        sa.Column("claim_amount_value", sa.Numeric(12, 2), nullable=True),
    )
    _add_column_if_missing(
        TABLE_NAME,
        sa.Column("claim_amount_currency", sa.String(length=10), nullable=True),
    )
    _add_column_if_missing(
        TABLE_NAME,
        sa.Column("respond_by", sa.DateTime(timezone=True), nullable=True),
    )
    _add_column_if_missing(
        TABLE_NAME,
        sa.Column("creation_date_api", sa.DateTime(timezone=True), nullable=True),
    )
    _add_column_if_missing(
        TABLE_NAME,
        sa.Column("last_modified_date_api", sa.DateTime(timezone=True), nullable=True),
    )
    # Optional issue_type column intentionally omitted for now; if future
    # payloads expose a stable field (e.g. issueType or caseReason), we can
    # add it in a follow-up migration.

    _create_index_if_missing(TABLE_NAME, "idx_ebay_cases_transaction_id", "transaction_id")
    _create_index_if_missing(TABLE_NAME, "idx_ebay_cases_item_id", "item_id")
    _create_index_if_missing(TABLE_NAME, "idx_ebay_cases_buyer_username", "buyer_username")
    _create_index_if_missing(TABLE_NAME, "idx_ebay_cases_respond_by", "respond_by")

    # 2) Data backfill – populate new columns from existing JSON payloads.
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())
    if TABLE_NAME not in existing_tables:
        return

    # Fetch case_id, user_id, and raw JSON payload for all rows.
    rows = conn.execute(
        sa_text(
            f"SELECT case_id, user_id, case_data FROM {TABLE_NAME} WHERE case_data IS NOT NULL",
        ),
    ).mappings().all()

    if not rows:
        return

    update_stmt = sa_text(
        """
        UPDATE ebay_cases
        SET
            item_id = :item_id,
            transaction_id = :transaction_id,
            buyer_username = :buyer_username,
            seller_username = :seller_username,
            case_status_enum = :case_status_enum,
            claim_amount_value = :claim_amount_value,
            claim_amount_currency = :claim_amount_currency,
            respond_by = :respond_by,
            creation_date_api = :creation_date_api,
            last_modified_date_api = :last_modified_date_api
        WHERE case_id = :case_id AND user_id = :user_id
        """
    )

    def _nested(obj: Dict[str, Any], *keys: str) -> Optional[Any]:
        cur: Any = obj
        for key in keys:
            if not isinstance(cur, dict):
                return None
            cur = cur.get(key)
        return cur

    for row in rows:
        case_id = row["case_id"]
        user_id = row["user_id"]
        raw = row["case_data"]

        try:
            payload = json.loads(raw) if isinstance(raw, str) else (raw or {})
        except Exception as exc:  # pragma: no cover - defensive logging
            LOGGER.warning(
                "ebay_cases backfill: failed to parse case_data JSON for case_id=%s user_id=%s: %s",
                case_id,
                user_id,
                exc,
            )
            continue

        if not isinstance(payload, dict):
            # Some legacy rows may contain a primitive JSON value; skip them.
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

        params = {
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
        }

        try:
            conn.execute(update_stmt, params)
        except Exception as exc:  # pragma: no cover - defensive logging
            LOGGER.warning(
                "ebay_cases backfill: failed to update normalized fields for case_id=%s user_id=%s: %s",
                case_id,
                user_id,
                exc,
            )


def downgrade() -> None:
    """Best-effort downgrade: drop indexes and columns if they exist."""

    _drop_index_if_exists(TABLE_NAME, "idx_ebay_cases_transaction_id")
    _drop_index_if_exists(TABLE_NAME, "idx_ebay_cases_item_id")
    _drop_index_if_exists(TABLE_NAME, "idx_ebay_cases_buyer_username")
    _drop_index_if_exists(TABLE_NAME, "idx_ebay_cases_respond_by")

    _drop_column_if_exists(TABLE_NAME, "item_id")
    _drop_column_if_exists(TABLE_NAME, "transaction_id")
    _drop_column_if_exists(TABLE_NAME, "buyer_username")
    _drop_column_if_exists(TABLE_NAME, "seller_username")
    _drop_column_if_exists(TABLE_NAME, "case_status_enum")
    _drop_column_if_exists(TABLE_NAME, "claim_amount_value")
    _drop_column_if_exists(TABLE_NAME, "claim_amount_currency")
    _drop_column_if_exists(TABLE_NAME, "respond_by")
    _drop_column_if_exists(TABLE_NAME, "creation_date_api")
    _drop_column_if_exists(TABLE_NAME, "last_modified_date_api")
