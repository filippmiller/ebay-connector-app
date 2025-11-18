"""Add ebay_buyer, ebay_status_buyer, and tbl_ebay_buyer_log tables

Revision ID: ebay_buyer_001
Revises: ebay_tables_001
Create Date: 2025-11-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text


# revision identifiers, used by Alembic.
revision: str = "ebay_buyer_001"
down_revision: Union[str, Sequence[str], None] = "ebay_tables_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create BUYING-related tables if they do not already exist."""
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_tables = set(inspector.get_table_names())

    # 1) Status dictionary table
    if "ebay_status_buyer" not in existing_tables:
        op.create_table(
            "ebay_status_buyer",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("code", sa.Text(), nullable=False, unique=True),
            sa.Column("label", sa.Text(), nullable=False),
            sa.Column("sort_order", sa.Integer(), nullable=False),
            sa.Column("color_hex", sa.Text(), nullable=True),
            sa.Column("text_color_hex", sa.Text(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )

        # Seed legacy statuses (idempotent via ON CONFLICT)
        seed_sql = text(
            """
            INSERT INTO ebay_status_buyer (code, label, sort_order, color_hex, text_color_hex, is_active)
            VALUES
              ('RECEIVED_AS_DESCRIBED', '1. Received as described', 1, '#008000', '#000000', TRUE),
              ('WEEK_DELAY_CONTACT_SELLER', '2. Week delay-contact the seller', 2, '#FF0000', '#FFFFFF', TRUE),
              ('NEED_OPEN_CASE_INR', '3. Need open Case-INR', 3, '#0000FF', '#FFFFFF', TRUE),
              ('NEED_OPEN_CASE_SNAD', '4. Need open Case-SNAD', 4, '#0000FF', '#FFFFFF', TRUE),
              ('TRACK_NOT_VERIFIED', '5. Track number NOT verified', 5, '#FF0000', '#FFFFFF', TRUE),
              ('IN_TRANSIT', '6. In transit', 6, '#008000', '#000000', TRUE),
              ('DELIVERED', '7. Delivered', 7, '#008000', '#000000', TRUE),
              ('TXN_CANCELLED', '8. Transaction canceled', 8, '#808080', '#FFFFFF', TRUE),
              ('CASE_OPENED_CANCEL', '9. Case opened-CANCEL trans.', 9, '#808080', '#FFFFFF', TRUE),
              ('TRANSFERRED_TO_ANOTHER_WAREHOUSE', '10. Transfered To Another Warehouse', 10, '#808080', '#FFFFFF', TRUE),
              ('SCANNED', '11. Scanned', 11, '#0000FF', '#FFFFFF', TRUE),
              ('RELEASE_SECTION', '12. Release Section', 12, '#808080', '#FFFFFF', TRUE)
            ON CONFLICT (code) DO NOTHING
            """
        )
        conn.execute(seed_sql)

    # 2) Main purchases table (legacy tbl_ebay_buyer equivalent)
    if "ebay_buyer" not in existing_tables:
        op.create_table(
            "ebay_buyer",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("ebay_account_id", sa.String(36), sa.ForeignKey("ebay_accounts.id", ondelete="CASCADE"), nullable=False),
            sa.Column("item_id", sa.Text(), nullable=True),
            sa.Column("title", sa.Text(), nullable=True),
            sa.Column("transaction_id", sa.Text(), nullable=True),
            sa.Column("order_line_item_id", sa.Text(), nullable=True),
            sa.Column("shipping_carrier", sa.Text(), nullable=True),
            sa.Column("tracking_number", sa.Text(), nullable=True),
            sa.Column("buyer_checkout_message", sa.Text(), nullable=True),
            sa.Column("condition_display_name", sa.Text(), nullable=True),
            sa.Column("seller_email", sa.Text(), nullable=True),
            sa.Column("seller_id", sa.Text(), nullable=True),
            sa.Column("seller_site", sa.Text(), nullable=True),
            sa.Column("seller_location", sa.Text(), nullable=True),
            sa.Column("quantity_purchased", sa.Integer(), nullable=True),
            sa.Column("current_price", sa.Numeric(18, 2), nullable=True),
            sa.Column("shipping_service_cost", sa.Numeric(18, 2), nullable=True),
            sa.Column("total_price", sa.Numeric(18, 2), nullable=True),
            sa.Column("total_transaction_price", sa.Numeric(18, 2), nullable=True),
            sa.Column("payment_hold_status", sa.Text(), nullable=True),
            sa.Column("buyer_paid_status", sa.Text(), nullable=True),
            sa.Column("paid_time", sa.DateTime(timezone=True), nullable=True),
            sa.Column("shipped_time", sa.DateTime(timezone=True), nullable=True),
            sa.Column("platform", sa.Text(), nullable=True),
            sa.Column("buyer_id", sa.Text(), nullable=True),
            sa.Column("item_url", sa.Text(), nullable=True),
            sa.Column("gallery_url", sa.Text(), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("private_notes", sa.Text(), nullable=True),
            sa.Column("my_comment", sa.Text(), nullable=True),
            sa.Column("storage", sa.Text(), nullable=True),
            sa.Column("model_id", sa.BigInteger(), nullable=True),
            sa.Column("item_status_id", sa.Integer(), sa.ForeignKey("ebay_status_buyer.id", ondelete="SET NULL"), nullable=True),
            sa.Column("item_status_updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("item_status_updated_by", sa.Text(), nullable=True),
            sa.Column("comment", sa.Text(), nullable=True),
            sa.Column("comment_updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("comment_updated_by", sa.Text(), nullable=True),
            sa.Column("record_created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("record_created_by", sa.Text(), nullable=True),
            sa.Column("record_updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("record_updated_by", sa.Text(), nullable=True),
            sa.Column("refund_flag", sa.Boolean(), nullable=True),
            sa.Column("refund_amount", sa.Numeric(18, 2), nullable=True),
            sa.Column("profit", sa.Numeric(18, 2), nullable=True),
            sa.Column("profit_updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("profit_updated_by", sa.Text(), nullable=True),
            sa.Column("legacy_comment", sa.Text(), nullable=True, comment="Optional mapping hook for legacy Comment column"),
            sa.Column("legacy_my_comment", sa.Text(), nullable=True, comment="Optional mapping hook for legacy MyComment column"),
            sa.Column("legacy_storage", sa.Text(), nullable=True, comment="Optional mapping hook for legacy Storage column"),
            sa.Comment("Legacy tbl_ebay_buyer equivalent"),
        )

        # Core indexes, including de-duplication key for upserts
        op.create_index(
            "idx_ebay_buyer_account",
            "ebay_buyer",
            ["ebay_account_id"],
        )
        op.create_index(
            "idx_ebay_buyer_tracking",
            "ebay_buyer",
            ["tracking_number"],
        )
        op.create_index(
            "idx_ebay_buyer_paid_time",
            "ebay_buyer",
            ["paid_time"],
        )
        op.create_index(
            "idx_ebay_buyer_seller_id",
            "ebay_buyer",
            ["seller_id"],
        )
        op.create_index(
            "idx_ebay_buyer_buyer_id",
            "ebay_buyer",
            ["buyer_id"],
        )
        op.create_index(
            "uq_ebay_buyer_account_item_txn",
            "ebay_buyer",
            ["ebay_account_id", "item_id", "transaction_id", "order_line_item_id"],
            unique=True,
        )

    # 3) Change log table
    if "tbl_ebay_buyer_log" not in existing_tables:
        op.create_table(
            "tbl_ebay_buyer_log",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("ebay_buyer_id", sa.BigInteger(), sa.ForeignKey("ebay_buyer.id", ondelete="CASCADE"), nullable=False),
            sa.Column("change_type", sa.Text(), nullable=False),
            sa.Column("old_status_id", sa.Integer(), sa.ForeignKey("ebay_status_buyer.id", ondelete="SET NULL"), nullable=True),
            sa.Column("new_status_id", sa.Integer(), sa.ForeignKey("ebay_status_buyer.id", ondelete="SET NULL"), nullable=True),
            sa.Column("old_comment", sa.Text(), nullable=True),
            sa.Column("new_comment", sa.Text(), nullable=True),
            sa.Column("changed_by_user_id", sa.String(36), nullable=True),
            sa.Column("changed_by_username", sa.Text(), nullable=True),
            sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("meta", sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        )
        op.create_index(
            "idx_tbl_ebay_buyer_log_buyer_changed_at",
            "tbl_ebay_buyer_log",
            ["ebay_buyer_id", "changed_at"],
        )


def downgrade() -> None:
    """Drop BUYING-related tables (logs first to satisfy FKs)."""
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_tables = set(inspector.get_table_names())

    if "tbl_ebay_buyer_log" in existing_tables:
        op.drop_index("idx_tbl_ebay_buyer_log_buyer_changed_at", table_name="tbl_ebay_buyer_log")
        op.drop_table("tbl_ebay_buyer_log")

    if "ebay_buyer" in existing_tables:
        op.drop_index("uq_ebay_buyer_account_item_txn", table_name="ebay_buyer")
        op.drop_index("idx_ebay_buyer_buyer_id", table_name="ebay_buyer")
        op.drop_index("idx_ebay_buyer_seller_id", table_name="ebay_buyer")
        op.drop_index("idx_ebay_buyer_paid_time", table_name="ebay_buyer")
        op.drop_index("idx_ebay_buyer_tracking", table_name="ebay_buyer")
        op.drop_index("idx_ebay_buyer_account", table_name="ebay_buyer")
        op.drop_table("ebay_buyer")

    if "ebay_status_buyer" in existing_tables:
        op.drop_table("ebay_status_buyer")
