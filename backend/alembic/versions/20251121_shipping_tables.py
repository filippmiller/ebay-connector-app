"""Add shipping tables for SHIPPING module

Revision ID: shipping_tables_20251121
Revises: ebay_events_processing_20251121
Create Date: 2025-11-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = "shipping_tables_20251121"
down_revision: Union[str, Sequence[str], None] = "ebay_events_processing_20251121"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SHIPPING_JOB_STATUS_ENUM = "shipping_job_status"
SHIPPING_LABEL_PROVIDER_ENUM = "shipping_label_provider"
SHIPPING_STATUS_SOURCE_ENUM = "shipping_status_source"


def upgrade() -> None:
    """Create shipping_jobs, shipping_packages, shipping_labels, shipping_status_log.

    The migration is written defensively so it can be applied even if run
    multiple times in slightly different environments.
    """

    conn = op.get_bind()
    inspector = sa.inspect(conn)

    existing_tables = set(inspector.get_table_names())

    # Create enums; checkfirst makes these calls idempotent even if the
    # types already exist in the target database.
    sa.Enum(
        "NEW",
        "PICKING",
        "PACKED",
        "SHIPPED",
        "CANCELLED",
        "ERROR",
        name=SHIPPING_JOB_STATUS_ENUM,
    ).create(conn, checkfirst=True)

    sa.Enum(
        "EBAY_LOGISTICS",
        "EXTERNAL",
        "MANUAL",
        name=SHIPPING_LABEL_PROVIDER_ENUM,
    ).create(conn, checkfirst=True)

    sa.Enum(
        "WAREHOUSE_SCAN",
        "API",
        "MANUAL",
        name=SHIPPING_STATUS_SOURCE_ENUM,
    ).create(conn, checkfirst=True)

    # shipping_jobs
    if "shipping_jobs" not in existing_tables:
        op.create_table(
            "shipping_jobs",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("ebay_account_id", sa.String(length=36), sa.ForeignKey("ebay_accounts.id", ondelete="SET NULL"), nullable=True),
            sa.Column("ebay_order_id", sa.Text(), nullable=True),
            sa.Column("ebay_order_line_item_ids", JSONB, nullable=True),
            sa.Column("buyer_user_id", sa.Text(), nullable=True),
            sa.Column("buyer_name", sa.Text(), nullable=True),
            sa.Column("ship_to_address", JSONB, nullable=True),
            sa.Column("warehouse_id", sa.Text(), nullable=True),
            sa.Column("storage_ids", JSONB, nullable=True),
            sa.Column("status", sa.Enum(
                "NEW",
                "PICKING",
                "PACKED",
                "SHIPPED",
                "CANCELLED",
                "ERROR",
                name=SHIPPING_JOB_STATUS_ENUM,
            ), nullable=False, server_default="NEW"),
            # Optional pointer to a primary label for this job. Implemented as a
            # simple string column to avoid circular FK with shipping_labels.
            sa.Column("label_id", sa.String(length=36), nullable=True),
            sa.Column("paid_time", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("created_by", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        )

    existing_indexes = {ix["name"] for ix in inspector.get_indexes("shipping_jobs")} if "shipping_jobs" in existing_tables else set()
    if "idx_shipping_jobs_status_warehouse" not in existing_indexes and "shipping_jobs" in existing_tables:
        op.create_index(
            "idx_shipping_jobs_status_warehouse",
            "shipping_jobs",
            ["status", "warehouse_id"],
        )
    if "idx_shipping_jobs_ebay_order_id" not in existing_indexes and "shipping_jobs" in existing_tables:
        op.create_index(
            "idx_shipping_jobs_ebay_order_id",
            "shipping_jobs",
            ["ebay_order_id"],
        )

    # shipping_labels
    if "shipping_labels" not in existing_tables:
        op.create_table(
            "shipping_labels",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("shipping_job_id", sa.String(length=36), sa.ForeignKey("shipping_jobs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("provider", sa.Enum(
                "EBAY_LOGISTICS",
                "EXTERNAL",
                "MANUAL",
                name=SHIPPING_LABEL_PROVIDER_ENUM,
            ), nullable=False),
            sa.Column("provider_shipment_id", sa.Text(), nullable=True),
            sa.Column("tracking_number", sa.Text(), nullable=True),
            sa.Column("carrier", sa.Text(), nullable=True),
            sa.Column("service_name", sa.Text(), nullable=True),
            sa.Column("label_url", sa.Text(), nullable=True),
            sa.Column("label_file_type", sa.Text(), nullable=True),
            sa.Column("label_cost_amount", sa.Numeric(12, 2), nullable=True),
            sa.Column("label_cost_currency", sa.CHAR(length=3), nullable=False, server_default="USD"),
            sa.Column("purchased_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("voided", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )

    if "shipping_labels" in inspector.get_table_names():
        existing_indexes = {ix["name"] for ix in inspector.get_indexes("shipping_labels")}
        if "ix_shipping_labels_tracking_number" not in existing_indexes:
            op.create_index("ix_shipping_labels_tracking_number", "shipping_labels", ["tracking_number"])
        if "idx_shipping_labels_provider_shipment" not in existing_indexes:
            op.create_index("idx_shipping_labels_provider_shipment", "shipping_labels", ["provider", "provider_shipment_id"])

    # shipping_packages
    if "shipping_packages" not in existing_tables:
        op.create_table(
            "shipping_packages",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("shipping_job_id", sa.String(length=36), sa.ForeignKey("shipping_jobs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("combined_for_buyer", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("weight_oz", sa.Numeric(10, 2), nullable=True),
            sa.Column("length_in", sa.Numeric(10, 2), nullable=True),
            sa.Column("width_in", sa.Numeric(10, 2), nullable=True),
            sa.Column("height_in", sa.Numeric(10, 2), nullable=True),
            sa.Column("package_type", sa.Text(), nullable=True),
            sa.Column("carrier_preference", sa.Text(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_shipping_packages_job_id", "shipping_packages", ["shipping_job_id"])

    # shipping_status_log
    if "shipping_status_log" not in existing_tables:
        op.create_table(
            "shipping_status_log",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("shipping_job_id", sa.String(length=36), sa.ForeignKey("shipping_jobs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("status_before", sa.Enum(
                "NEW",
                "PICKING",
                "PACKED",
                "SHIPPED",
                "CANCELLED",
                "ERROR",
                name=SHIPPING_JOB_STATUS_ENUM,
            ), nullable=True),
            sa.Column("status_after", sa.Enum(
                "NEW",
                "PICKING",
                "PACKED",
                "SHIPPED",
                "CANCELLED",
                "ERROR",
                name=SHIPPING_JOB_STATUS_ENUM,
            ), nullable=False),
            sa.Column("source", sa.Enum(
                "WAREHOUSE_SCAN",
                "API",
                "MANUAL",
                name=SHIPPING_STATUS_SOURCE_ENUM,
            ), nullable=False, server_default="MANUAL"),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index(
            "idx_shipping_status_log_job_created",
            "shipping_status_log",
            ["shipping_job_id", "created_at"],
        )


def downgrade() -> None:
    """Drop shipping tables and enums (best-effort)."""

    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    # Drop status log
    if "shipping_status_log" in existing_tables:
        existing_indexes = {ix["name"] for ix in inspector.get_indexes("shipping_status_log")}
        if "idx_shipping_status_log_job_created" in existing_indexes:
            op.drop_index("idx_shipping_status_log_job_created", table_name="shipping_status_log")
        op.drop_table("shipping_status_log")

    # Drop packages
    if "shipping_packages" in existing_tables:
        existing_indexes = {ix["name"] for ix in inspector.get_indexes("shipping_packages")}
        if "ix_shipping_packages_job_id" in existing_indexes:
            op.drop_index("ix_shipping_packages_job_id", table_name="shipping_packages")
        op.drop_table("shipping_packages")

    # Drop labels
    if "shipping_labels" in existing_tables:
        existing_indexes = {ix["name"] for ix in inspector.get_indexes("shipping_labels")}
        if "ix_shipping_labels_tracking_number" in existing_indexes:
            op.drop_index("ix_shipping_labels_tracking_number", table_name="shipping_labels")
        if "idx_shipping_labels_provider_shipment" in existing_indexes:
            op.drop_index("idx_shipping_labels_provider_shipment", table_name="shipping_labels")
        op.drop_table("shipping_labels")

    # Drop jobs
    if "shipping_jobs" in existing_tables:
        existing_indexes = {ix["name"] for ix in inspector.get_indexes("shipping_jobs")}
        if "idx_shipping_jobs_status_warehouse" in existing_indexes:
            op.drop_index("idx_shipping_jobs_status_warehouse", table_name="shipping_jobs")
        if "idx_shipping_jobs_ebay_order_id" in existing_indexes:
            op.drop_index("idx_shipping_jobs_ebay_order_id", table_name="shipping_jobs")
        op.drop_table("shipping_jobs")

    # Drop enums (if present)
    for enum_name in [
        SHIPPING_STATUS_SOURCE_ENUM,
        SHIPPING_LABEL_PROVIDER_ENUM,
        SHIPPING_JOB_STATUS_ENUM,
    ]:
        try:
            sa.Enum(name=enum_name).drop(conn, checkfirst=True)
        except Exception:
            # Best-effort; enum might be shared or already dropped.
            pass
