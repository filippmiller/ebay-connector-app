"""add_sq_items_and_sq_dictionaries

Revision ID: dae483e3dc8c
Revises: e984eafc5e3a
Create Date: 2025-11-19 03:16:28.336607

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'dae483e3dc8c'
down_revision: Union[str, Sequence[str], None] = 'e984eafc5e3a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create sq_items catalog table and supporting dictionary tables.

    This schema is designed to be a 1:1-compatible destination for legacy
    [DB_A28F26_parts].[dbo].[tbl_parts_detail] rows, while also supporting
    new app-specific fields (title, brand, warehouse, storage_alias).
    """

    # --- sq_internal_categories -------------------------------------------------
    op.create_table(
        "sq_internal_categories",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(length=50), nullable=False, unique=True),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=True),
    )

    categories_table = sa.table(
        "sq_internal_categories",
        sa.column("code", sa.String(length=50)),
        sa.column("label", sa.Text()),
        sa.column("sort_order", sa.Integer()),
    )

    op.bulk_insert(
        categories_table,
        [
            {"code": "101", "label": "motherboards", "sort_order": 101},
            {"code": "102", "label": "motherboard AS-IS for parts", "sort_order": 102},
            {"code": "103", "label": "LCD complete", "sort_order": 103},
            {"code": "104", "label": "lcd back cover", "sort_order": 104},
            {"code": "105", "label": "lcd video cable", "sort_order": 105},
            {"code": "106", "label": "lcd front bezel", "sort_order": 106},
            {"code": "107", "label": "lcd inverter", "sort_order": 107},
            {"code": "108", "label": "bottom case", "sort_order": 108},
            {"code": "109", "label": "palmrest", "sort_order": 109},
            {"code": "110", "label": "keyboard", "sort_order": 110},
            {"code": "112", "label": "HDD", "sort_order": 112},
        ],
    )

    # --- sq_shipping_groups ------------------------------------------------------
    op.create_table(
        "sq_shipping_groups",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(length=50), nullable=False, unique=True),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=True),
    )

    shipping_table = sa.table(
        "sq_shipping_groups",
        sa.column("code", sa.String(length=50)),
        sa.column("label", sa.Text()),
        sa.column("sort_order", sa.Integer()),
    )

    op.bulk_insert(
        shipping_table,
        [
            {"code": "1", "label": "1group<80", "sort_order": 1},
            {"code": "2", "label": "2group<80", "sort_order": 2},
            {"code": "3", "label": "3group<80", "sort_order": 3},
            {"code": "4", "label": "no international", "sort_order": 4},
            {"code": "5", "label": "LCD Complete", "sort_order": 5},
            {"code": "6", "label": "BIG items", "sort_order": 6},
        ],
    )

    # --- item_conditions ---------------------------------------------------------
    op.create_table(
        "item_conditions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(length=50), nullable=False, unique=True),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=True),
    )

    conditions_table = sa.table(
        "item_conditions",
        sa.column("code", sa.String(length=50)),
        sa.column("label", sa.Text()),
        sa.column("sort_order", sa.Integer()),
    )

    op.bulk_insert(
        conditions_table,
        [
            {"code": "NEW", "label": "New", "sort_order": 10},
            {"code": "USED", "label": "Used", "sort_order": 20},
            {"code": "REFURBISHED", "label": "Refurbished", "sort_order": 30},
            {"code": "FOR_PARTS", "label": "For parts or not working", "sort_order": 40},
        ],
    )

    # --- sq_items ----------------------------------------------------------------
    op.create_table(
        "sq_items",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("part_id", sa.BigInteger(), nullable=True),
        sa.Column("sku", sa.String(length=100), nullable=True),
        sa.Column("sku2", sa.String(length=100), nullable=True),
        sa.Column("model_id", sa.BigInteger(), nullable=True),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("part", sa.Text(), nullable=True),
        # Pricing
        sa.Column("price", sa.Numeric(12, 2), nullable=True),
        sa.Column("previous_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("brutto", sa.Numeric(12, 2), nullable=True),
        sa.Column("price_updated", sa.DateTime(timezone=True), nullable=True),
        # Market & category
        sa.Column("market", sa.Text(), nullable=True),
        sa.Column("use_ebay_id", sa.Boolean(), nullable=True),
        sa.Column("category", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        # Shipping
        sa.Column("shipping_type", sa.Text(), nullable=True),
        sa.Column("shipping_group", sa.Text(), nullable=True),
        sa.Column("shipping_group_previous", sa.Text(), nullable=True),
        sa.Column("shipping_group_change_state", sa.Text(), nullable=True),
        sa.Column("shipping_group_change_state_updated", sa.DateTime(timezone=True), nullable=True),
        sa.Column("shipping_group_change_state_updated_by", sa.Text(), nullable=True),
        # Condition
        sa.Column("condition_id", sa.Integer(), nullable=True),
        sa.Column("manual_condition_value_flag", sa.Boolean(), nullable=True),
        # Images
        sa.Column("pic_url1", sa.Text(), nullable=True),
        sa.Column("pic_url2", sa.Text(), nullable=True),
        sa.Column("pic_url3", sa.Text(), nullable=True),
        sa.Column("pic_url4", sa.Text(), nullable=True),
        sa.Column("pic_url5", sa.Text(), nullable=True),
        sa.Column("pic_url6", sa.Text(), nullable=True),
        sa.Column("pic_url7", sa.Text(), nullable=True),
        sa.Column("pic_url8", sa.Text(), nullable=True),
        sa.Column("pic_url9", sa.Text(), nullable=True),
        sa.Column("pic_url10", sa.Text(), nullable=True),
        sa.Column("pic_url11", sa.Text(), nullable=True),
        sa.Column("pic_url12", sa.Text(), nullable=True),
        # Physical properties
        sa.Column("weight", sa.Numeric(12, 3), nullable=True),
        sa.Column("weight_major", sa.Numeric(12, 3), nullable=True),
        sa.Column("weight_minor", sa.Numeric(12, 3), nullable=True),
        sa.Column("package_depth", sa.Numeric(12, 2), nullable=True),
        sa.Column("package_length", sa.Numeric(12, 2), nullable=True),
        sa.Column("package_width", sa.Numeric(12, 2), nullable=True),
        sa.Column("size", sa.Text(), nullable=True),
        sa.Column("unit", sa.Text(), nullable=True),
        # Identification codes
        sa.Column("part_number", sa.Text(), nullable=True),
        sa.Column("mpn", sa.Text(), nullable=True),
        sa.Column("upc", sa.Text(), nullable=True),
        sa.Column("color_flag", sa.Boolean(), nullable=True),
        sa.Column("color_value", sa.Text(), nullable=True),
        sa.Column("epid_flag", sa.Boolean(), nullable=True),
        sa.Column("epid_value", sa.Text(), nullable=True),
        # Grades & packaging
        sa.Column("item_grade_id", sa.Integer(), nullable=True),
        sa.Column("basic_package_id", sa.Integer(), nullable=True),
        # Alert & status
        sa.Column("alert_flag", sa.Boolean(), nullable=True),
        sa.Column("alert_message", sa.Text(), nullable=True),
        sa.Column("record_status", sa.Text(), nullable=True),
        sa.Column("record_status_flag", sa.Boolean(), nullable=True),
        sa.Column("checked_status", sa.Text(), nullable=True),
        sa.Column("checked", sa.Boolean(), nullable=True),
        sa.Column("checked_by", sa.Text(), nullable=True),
        sa.Column("one_time_auction", sa.Boolean(), nullable=True),
        # Audit fields
        sa.Column("record_created_by", sa.Text(), nullable=True),
        sa.Column("record_created", sa.DateTime(timezone=True), nullable=True),
        sa.Column("record_updated_by", sa.Text(), nullable=True),
        sa.Column("record_updated", sa.DateTime(timezone=True), nullable=True),
        sa.Column("oc_export_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("oc_market_export_date", sa.DateTime(timezone=True), nullable=True),
        # Templates & listing metadata
        sa.Column("custom_template_flag", sa.Boolean(), nullable=True),
        sa.Column("custom_template_description", sa.Text(), nullable=True),
        sa.Column("condition_description", sa.Text(), nullable=True),
        sa.Column("domestic_only_flag", sa.Boolean(), nullable=True),
        sa.Column("external_category_flag", sa.Boolean(), nullable=True),
        sa.Column("external_category_id", sa.Text(), nullable=True),
        sa.Column("external_category_name", sa.Text(), nullable=True),
        sa.Column("listing_type", sa.Text(), nullable=True),
        sa.Column("listing_duration", sa.Text(), nullable=True),
        sa.Column("listing_duration_in_days", sa.Integer(), nullable=True),
        sa.Column("use_standard_template_for_external_category_flag", sa.Boolean(), nullable=True),
        sa.Column("use_ebay_motors_site_flag", sa.Boolean(), nullable=True),
        sa.Column("site_id", sa.Text(), nullable=True),
        # Clone SKU metadata
        sa.Column("clone_sku_flag", sa.Boolean(), nullable=True),
        sa.Column("clone_sku_updated", sa.DateTime(timezone=True), nullable=True),
        sa.Column("clone_sku_updated_by", sa.Text(), nullable=True),
        # New fields for modern app
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("brand", sa.String(length=100), nullable=True),
        sa.Column("warehouse_id", sa.Integer(), sa.ForeignKey("warehouses.id"), nullable=True),
        sa.Column("storage_alias", sa.String(length=100), nullable=True),
    )

    op.create_index("idx_sq_items_sku", "sq_items", ["sku"])
    op.create_index("idx_sq_items_category", "sq_items", ["category"])
    op.create_index("idx_sq_items_part_number", "sq_items", ["part_number"])
    op.create_index("idx_sq_items_model", "sq_items", ["model"])
    op.create_index("idx_sq_items_condition_id", "sq_items", ["condition_id"])
    op.create_index("idx_sq_items_shipping_group", "sq_items", ["shipping_group"])
    op.create_index("idx_sq_items_site_id", "sq_items", ["site_id"])


def downgrade() -> None:
    """Drop sq_items and SQ dictionary tables."""

    # Drop sq_items first due to FK to warehouses
    op.drop_index("idx_sq_items_site_id", table_name="sq_items")
    op.drop_index("idx_sq_items_shipping_group", table_name="sq_items")
    op.drop_index("idx_sq_items_condition_id", table_name="sq_items")
    op.drop_index("idx_sq_items_model", table_name="sq_items")
    op.drop_index("idx_sq_items_part_number", table_name="sq_items")
    op.drop_index("idx_sq_items_category", table_name="sq_items")
    op.drop_index("idx_sq_items_sku", table_name="sq_items")
    op.drop_table("sq_items")

    # Dictionary tables
    op.drop_table("item_conditions")
    op.drop_table("sq_shipping_groups")
    op.drop_table("sq_internal_categories")
