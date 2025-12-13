"""Add parts_detail and parts_detail_log tables for listing worker

Revision ID: parts_detail_20251125
Revises: ebay_snipes_fire_at_comment_20251125
Create Date: 2025-11-25

This migration introduces two Supabase/Postgres tables that replace the
legacy MSSQL tbl_parts_detail / tbl_parts_detail_log pair. Only the subset of
columns required for the first eBay listing worker implementation are
modelled here; additional legacy columns can be added incrementally in
follow-up migrations.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "parts_detail_20251125"
down_revision: Union[str, Sequence[str], None] = "ebay_snipes_fire_at_comment_20251125"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # parts_detail – main listing/inventory table (Postgres mirror of legacy tbl_parts_detail)
    op.create_table(
        "parts_detail",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        # Identity & warehouse
        sa.Column("sku", sa.String(length=100), nullable=True),
        sa.Column("sku2", sa.String(length=100), nullable=True),
        sa.Column("override_sku", sa.String(length=100), nullable=True),
        sa.Column("storage", sa.String(length=100), nullable=True),
        sa.Column("alt_storage", sa.String(length=100), nullable=True),
        sa.Column("storage_alias", sa.String(length=100), nullable=True),
        sa.Column("warehouse_id", sa.Integer(), sa.ForeignKey("warehouses.id"), nullable=True),
        # eBay account & linkage
        sa.Column("item_id", sa.String(length=100), nullable=True),
        sa.Column("ebay_id", sa.String(length=64), nullable=True),
        sa.Column("username", sa.String(length=100), nullable=True),
        sa.Column("global_ebay_id_for_relist", sa.String(length=64), nullable=True),
        sa.Column("global_ebay_id_for_relist_flag", sa.Boolean(), nullable=True),
        # Status fields (string enum in app code)
        sa.Column("status_sku", sa.String(length=32), nullable=True),
        sa.Column("listing_status", sa.String(length=50), nullable=True),
        sa.Column("status_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status_updated_by", sa.String(length=100), nullable=True),
        sa.Column("listing_status_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("listing_status_updated_by", sa.String(length=100), nullable=True),
        # Listing lifetime
        sa.Column("listing_start_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("listing_end_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("listing_time_updated", sa.DateTime(timezone=True), nullable=True),
        sa.Column("item_listed_at", sa.DateTime(timezone=True), nullable=True),
        # Prices & overrides
        sa.Column("override_price", sa.Numeric(14, 2), nullable=True),
        sa.Column("price_to_change", sa.Numeric(14, 2), nullable=True),
        sa.Column("price_to_change_one_time", sa.Numeric(14, 2), nullable=True),
        sa.Column("override_price_flag", sa.Boolean(), nullable=True),
        sa.Column("price_to_change_flag", sa.Boolean(), nullable=True),
        sa.Column("price_to_change_one_time_flag", sa.Boolean(), nullable=True),
        # Best Offer (subset)
        sa.Column("best_offer_enabled_flag", sa.Boolean(), nullable=True),
        sa.Column("best_offer_auto_accept_price_flag", sa.Boolean(), nullable=True),
        sa.Column("best_offer_auto_accept_price_value", sa.Numeric(14, 2), nullable=True),
        sa.Column("best_offer_auto_accept_price_percent", sa.Numeric(5, 2), nullable=True),
        sa.Column("best_offer_min_price_flag", sa.Boolean(), nullable=True),
        sa.Column("best_offer_min_price_value", sa.Numeric(14, 2), nullable=True),
        sa.Column("best_offer_min_price_percent", sa.Numeric(5, 2), nullable=True),
        sa.Column("best_offer_mode", sa.String(length=20), nullable=True),
        sa.Column("best_offer_to_change_flag", sa.Boolean(), nullable=True),
        sa.Column("active_best_offer_flag", sa.Boolean(), nullable=True),
        sa.Column("active_best_offer_manual_flag", sa.Boolean(), nullable=True),
        # Title, description, pictures
        sa.Column("override_title", sa.Text(), nullable=True),
        sa.Column("override_description", sa.Text(), nullable=True),
        sa.Column("override_condition_id", sa.Integer(), nullable=True),
        sa.Column("condition_description_to_change", sa.Text(), nullable=True),
        sa.Column("override_pic_url_1", sa.Text(), nullable=True),
        sa.Column("override_pic_url_2", sa.Text(), nullable=True),
        sa.Column("override_pic_url_3", sa.Text(), nullable=True),
        sa.Column("override_pic_url_4", sa.Text(), nullable=True),
        sa.Column("override_pic_url_5", sa.Text(), nullable=True),
        sa.Column("override_pic_url_6", sa.Text(), nullable=True),
        sa.Column("override_pic_url_7", sa.Text(), nullable=True),
        sa.Column("override_pic_url_8", sa.Text(), nullable=True),
        sa.Column("override_pic_url_9", sa.Text(), nullable=True),
        sa.Column("override_pic_url_10", sa.Text(), nullable=True),
        sa.Column("override_pic_url_11", sa.Text(), nullable=True),
        sa.Column("override_pic_url_12", sa.Text(), nullable=True),
        # eBay API ACK / errors
        sa.Column("verify_ack", sa.String(length=20), nullable=True),
        sa.Column("verify_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verify_error", sa.Text(), nullable=True),
        sa.Column("add_ack", sa.String(length=20), nullable=True),
        sa.Column("add_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("add_error", sa.Text(), nullable=True),
        sa.Column("revise_ack", sa.String(length=20), nullable=True),
        sa.Column("revise_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revise_error", sa.Text(), nullable=True),
        # Batch / queue flags
        sa.Column("batch_error_flag", sa.Boolean(), nullable=True),
        sa.Column("batch_error_message", JSONB, nullable=True),
        sa.Column("batch_success_flag", sa.Boolean(), nullable=True),
        sa.Column("batch_success_message", JSONB, nullable=True),
        sa.Column("mark_as_listed_queue_flag", sa.Boolean(), nullable=True),
        sa.Column("mark_as_listed_queue_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("mark_as_listed_queue_updated_by", sa.String(length=100), nullable=True),
        sa.Column("listing_price_batch_flag", sa.Boolean(), nullable=True),
        sa.Column("cancel_listing_queue_flag", sa.Boolean(), nullable=True),
        sa.Column("cancel_listing_queue_flag_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_listing_queue_flag_updated_by", sa.String(length=100), nullable=True),
        sa.Column("relist_listing_queue_flag", sa.Boolean(), nullable=True),
        sa.Column("relist_listing_queue_flag_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("relist_listing_queue_flag_updated_by", sa.String(length=100), nullable=True),
        sa.Column("freeze_listing_queue_flag", sa.Boolean(), nullable=True),
        # Event flags
        sa.Column("relist_flag", sa.Boolean(), nullable=True),
        sa.Column("relist_quantity", sa.Integer(), nullable=True),
        sa.Column("relist_listing_flag", sa.Boolean(), nullable=True),
        sa.Column("relist_listing_flag_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("relist_listing_flag_updated_by", sa.String(length=100), nullable=True),
        sa.Column("cancel_listing_flag", sa.Boolean(), nullable=True),
        sa.Column("cancel_listing_status_sku", sa.String(length=50), nullable=True),
        sa.Column("cancel_listing_interface", sa.String(length=50), nullable=True),
        sa.Column("freeze_listing_flag", sa.Boolean(), nullable=True),
        sa.Column("phantom_cancel_listing_flag", sa.Boolean(), nullable=True),
        sa.Column("ended_for_relist_flag", sa.Boolean(), nullable=True),
        sa.Column("just_sold_flag", sa.Boolean(), nullable=True),
        sa.Column("return_flag", sa.Boolean(), nullable=True),
        sa.Column("loss_flag", sa.Boolean(), nullable=True),
        # Audit
        sa.Column(
            "record_created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("record_created_by", sa.String(length=100), nullable=True),
        sa.Column("record_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("record_updated_by", sa.String(length=100), nullable=True),
    )

    op.create_index("idx_parts_detail_sku", "parts_detail", ["sku"])
    op.create_index("idx_parts_detail_item_id", "parts_detail", ["item_id"])
    op.create_index("idx_parts_detail_status_sku", "parts_detail", ["status_sku"])
    op.create_index("idx_parts_detail_listing_status", "parts_detail", ["listing_status"])
    op.create_index("idx_parts_detail_username", "parts_detail", ["username"])
    op.create_index("idx_parts_detail_ebay_id", "parts_detail", ["ebay_id"])
    op.create_index(
        "idx_parts_detail_batch_error_flag",
        "parts_detail",
        ["batch_error_flag"],
    )
    op.create_index(
        "idx_parts_detail_batch_success_flag",
        "parts_detail",
        ["batch_success_flag"],
    )

    # parts_detail_log – high-level audit log (Postgres mirror of legacy tbl_parts_detail_log)
    op.create_table(
        "parts_detail_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "part_detail_id",
            sa.Integer(),
            sa.ForeignKey("parts_detail.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Linkage / snapshot identifiers
        sa.Column("sku", sa.String(length=100), nullable=True),
        sa.Column("model_id", sa.Integer(), nullable=True),
        # Product snapshot
        sa.Column("part", sa.Text(), nullable=True),
        sa.Column("price", sa.Numeric(14, 2), nullable=True),
        sa.Column("previous_price", sa.Numeric(14, 2), nullable=True),
        sa.Column("price_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("market", sa.String(length=50), nullable=True),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("shipping_type", sa.String(length=50), nullable=True),
        sa.Column("shipping_group", sa.String(length=50), nullable=True),
        sa.Column("condition_id", sa.Integer(), nullable=True),
        sa.Column("pic_url_1", sa.Text(), nullable=True),
        sa.Column("pic_url_2", sa.Text(), nullable=True),
        sa.Column("pic_url_3", sa.Text(), nullable=True),
        sa.Column("pic_url_4", sa.Text(), nullable=True),
        sa.Column("pic_url_5", sa.Text(), nullable=True),
        sa.Column("pic_url_6", sa.Text(), nullable=True),
        sa.Column("pic_url_7", sa.Text(), nullable=True),
        sa.Column("pic_url_8", sa.Text(), nullable=True),
        sa.Column("pic_url_9", sa.Text(), nullable=True),
        sa.Column("pic_url_10", sa.Text(), nullable=True),
        sa.Column("pic_url_11", sa.Text(), nullable=True),
        sa.Column("pic_url_12", sa.Text(), nullable=True),
        sa.Column("weight", sa.Numeric(12, 3), nullable=True),
        sa.Column("part_number", sa.String(length=100), nullable=True),
        # Flags & statuses
        sa.Column("alert_flag", sa.Boolean(), nullable=True),
        sa.Column("alert_message", sa.Text(), nullable=True),
        sa.Column("record_status", sa.String(length=50), nullable=True),
        sa.Column("record_status_flag", sa.Boolean(), nullable=True),
        sa.Column("checked_status", sa.String(length=50), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("checked_by", sa.String(length=100), nullable=True),
        sa.Column("one_time_auction", sa.Boolean(), nullable=True),
        # Audit
        sa.Column("record_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("record_created_by", sa.String(length=100), nullable=True),
        sa.Column("record_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("record_updated_by", sa.String(length=100), nullable=True),
        sa.Column(
            "log_created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("log_created_by", sa.String(length=100), nullable=True),
    )

    op.create_index(
        "idx_parts_detail_log_part_detail_id",
        "parts_detail_log",
        ["part_detail_id"],
    )
    op.create_index("idx_parts_detail_log_sku", "parts_detail_log", ["sku"])
    op.create_index(
        "idx_parts_detail_log_checked_status",
        "parts_detail_log",
        ["checked_status"],
    )


def downgrade() -> None:
    op.drop_index("idx_parts_detail_log_checked_status", table_name="parts_detail_log")
    op.drop_index("idx_parts_detail_log_sku", table_name="parts_detail_log")
    op.drop_index("idx_parts_detail_log_part_detail_id", table_name="parts_detail_log")
    op.drop_table("parts_detail_log")

    op.drop_index("idx_parts_detail_batch_success_flag", table_name="parts_detail")
    op.drop_index("idx_parts_detail_batch_error_flag", table_name="parts_detail")
    op.drop_index("idx_parts_detail_ebay_id", table_name="parts_detail")
    op.drop_index("idx_parts_detail_username", table_name="parts_detail")
    op.drop_index("idx_parts_detail_listing_status", table_name="parts_detail")
    op.drop_index("idx_parts_detail_status_sku", table_name="parts_detail")
    op.drop_index("idx_parts_detail_item_id", table_name="parts_detail")
    op.drop_index("idx_parts_detail_sku", table_name="parts_detail")
    op.drop_table("parts_detail")
