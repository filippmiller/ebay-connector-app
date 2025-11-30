"""Normalize ebay_messages with case, topic, and attachment fields

Revision ID: ebay_messages_normalization_20251124
Revises: ebay_cases_normalization_20251124
Create Date: 2025-11-24

This migration extends ebay_messages with additional columns needed to
reliably link messages to cases/returns/disputes, classify message topics,
track attachments, and (optionally) store a canonical timestamptz for
message time. The DDL is written to be idempotent and safe to re-run.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "ebay_messages_normalization_20251124"
down_revision: Union[str, Sequence[str], None] = "ebay_cases_normalization_20251124"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = "ebay_messages"


def _get_inspector():
    conn = op.get_bind()
    return inspect(conn)


def _add_column_if_missing(table: str, column: sa.Column) -> None:
    inspector = _get_inspector()
    if table not in inspector.get_table_names():
        return

    existing_cols = {c["name"] for c in inspector.get_columns(table)}
    if column.name in existing_cols:
        return

    op.add_column(table, column)


def _create_index_if_missing(table: str, index_name: str, *columns: str) -> None:
    inspector = _get_inspector()
    if table not in inspector.get_table_names():
        return

    existing_indexes = {ix["name"] for ix in inspector.get_indexes(table)}
    if index_name in existing_indexes:
        return

    op.create_index(index_name, table, list(columns))


def _drop_index_if_exists(table: str, index_name: str) -> None:
    inspector = _get_inspector()
    if table not in inspector.get_table_names():
        return

    existing_indexes = {ix["name"] for ix in inspector.get_indexes(table)}
    if index_name not in existing_indexes:
        return

    op.drop_index(index_name, table_name=table)


def _drop_column_if_exists(table: str, column_name: str) -> None:
    inspector = _get_inspector()
    if table not in inspector.get_table_names():
        return

    existing_cols = {c["name"] for c in inspector.get_columns(table)}
    if column_name not in existing_cols:
        return

    op.drop_column(table, column_name)


def upgrade() -> None:
    """Extend ebay_messages with normalized case/topic/attachment fields."""

    # Core case / dispute linkage
    _add_column_if_missing(
        TABLE_NAME,
        sa.Column("case_id", sa.Text(), nullable=True),
    )
    _add_column_if_missing(
        TABLE_NAME,
        sa.Column("case_type", sa.Text(), nullable=True),
    )
    _add_column_if_missing(
        TABLE_NAME,
        sa.Column("inquiry_id", sa.Text(), nullable=True),
    )
    _add_column_if_missing(
        TABLE_NAME,
        sa.Column("return_id", sa.Text(), nullable=True),
    )
    _add_column_if_missing(
        TABLE_NAME,
        sa.Column("payment_dispute_id", sa.Text(), nullable=True),
    )
    _add_column_if_missing(
        TABLE_NAME,
        sa.Column("transaction_id", sa.Text(), nullable=True),
    )

    # Classification / topic
    _add_column_if_missing(
        TABLE_NAME,
        sa.Column(
            "is_case_related",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    _add_column_if_missing(
        TABLE_NAME,
        sa.Column("message_topic", sa.Text(), nullable=True),
    )
    _add_column_if_missing(
        TABLE_NAME,
        sa.Column("case_event_type", sa.Text(), nullable=True),
    )

    # Attachments & preview
    _add_column_if_missing(
        TABLE_NAME,
        sa.Column(
            "has_attachments",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    _add_column_if_missing(
        TABLE_NAME,
        sa.Column(
            "attachments_meta",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    _add_column_if_missing(
        TABLE_NAME,
        sa.Column("preview_text", sa.Text(), nullable=True),
    )

    # Optional canonical timestamptz, only if message_date is not already timestamptz
    inspector = _get_inspector()
    cols = {c["name"]: c for c in inspector.get_columns(TABLE_NAME)}
    message_date_col = cols.get("message_date")
    if message_date_col is not None:
        col_type = message_date_col.get("type")
        # If type is not DateTime(timezone=True), introduce message_at for canonical usage
        if not isinstance(col_type, sa.DateTime) or not getattr(col_type, "timezone", False):
            _add_column_if_missing(
                TABLE_NAME,
                sa.Column("message_at", sa.DateTime(timezone=True), nullable=True),
            )
    else:
        _add_column_if_missing(
            TABLE_NAME,
            sa.Column("message_at", sa.DateTime(timezone=True), nullable=True),
        )

    # Indexes for efficient lookups
    _create_index_if_missing(TABLE_NAME, "idx_ebay_messages_case_id", "case_id")
    _create_index_if_missing(
        TABLE_NAME,
        "idx_ebay_messages_transaction_id",
        "transaction_id",
    )
    _create_index_if_missing(TABLE_NAME, "idx_ebay_messages_listing_id", "listing_id")
    _create_index_if_missing(TABLE_NAME, "idx_ebay_messages_order_id", "order_id")

    # Composite index to speed up user/account + case timelines
    _create_index_if_missing(
        TABLE_NAME,
        "idx_ebay_messages_user_account_case_at",
        "user_id",
        "ebay_account_id",
        "case_id",
        "message_date",
    )


def downgrade() -> None:
    """Best-effort downgrade: drop indexes and columns if they exist."""

    _drop_index_if_exists(TABLE_NAME, "idx_ebay_messages_user_account_case_at")
    _drop_index_if_exists(TABLE_NAME, "idx_ebay_messages_order_id")
    _drop_index_if_exists(TABLE_NAME, "idx_ebay_messages_listing_id")
    _drop_index_if_exists(TABLE_NAME, "idx_ebay_messages_transaction_id")
    _drop_index_if_exists(TABLE_NAME, "idx_ebay_messages_case_id")

    _drop_column_if_exists(TABLE_NAME, "message_at")
    _drop_column_if_exists(TABLE_NAME, "preview_text")
    _drop_column_if_exists(TABLE_NAME, "attachments_meta")
    _drop_column_if_exists(TABLE_NAME, "has_attachments")
    _drop_column_if_exists(TABLE_NAME, "case_event_type")
    _drop_column_if_exists(TABLE_NAME, "message_topic")
    _drop_column_if_exists(TABLE_NAME, "is_case_related")
    _drop_column_if_exists(TABLE_NAME, "transaction_id")
    _drop_column_if_exists(TABLE_NAME, "payment_dispute_id")
    _drop_column_if_exists(TABLE_NAME, "return_id")
    _drop_column_if_exists(TABLE_NAME, "inquiry_id")
    _drop_column_if_exists(TABLE_NAME, "case_type")
    _drop_column_if_exists(TABLE_NAME, "case_id")
