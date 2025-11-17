"""Add users timesheet fields and public.timesheets table

Revision ID: timesheets_001
Revises: fix_ebay_messages_id_column_001
Create Date: 2025-11-17

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text


# revision identifiers, used by Alembic.
revision = "timesheets_001"
down_revision = "fix_ebay_messages_id_column_001"
branch_labels = None
depends_on = None


def _column_exists(inspector, table_name: str, column_name: str) -> bool:
    cols = [c["name"] for c in inspector.get_columns(table_name)]
    return column_name in cols


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)

    # 1) Ensure helper function for record_updated is present
    op.execute(
        text(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_proc
                    WHERE proname = 'set_record_updated_timestamp'
                ) THEN
                    CREATE OR REPLACE FUNCTION public.set_record_updated_timestamp()
                    RETURNS trigger AS $$
                    BEGIN
                        NEW.record_updated := now();
                        RETURN NEW;
                    END;
                    $$ LANGUAGE plpgsql;
                END IF;
            END$$;
            """
        )
    )

    # 2) Extend existing users table with timesheet-related fields
    if "users" in inspector.get_table_names():
        existing_columns = [c["name"] for c in inspector.get_columns("users")]

        if "legacy_id" not in existing_columns:
            op.add_column("users", sa.Column("legacy_id", sa.Numeric(18, 0), nullable=True))

        if "full_name" not in existing_columns:
            op.add_column("users", sa.Column("full_name", sa.String(255), nullable=True))

        if "hourly_rate" not in existing_columns:
            op.add_column("users", sa.Column("hourly_rate", sa.Numeric(18, 2), nullable=True))

        if "auth_user_id" not in existing_columns:
            op.add_column("users", sa.Column("auth_user_id", sa.dialects.postgresql.UUID(), nullable=True))

        if "record_created" not in existing_columns:
            op.add_column(
                "users",
                sa.Column(
                    "record_created",
                    sa.DateTime(timezone=True),
                    nullable=True,
                    server_default=sa.func.now(),
                ),
            )
        if "record_created_by" not in existing_columns:
            op.add_column("users", sa.Column("record_created_by", sa.String(50), nullable=True))

        if "record_updated" not in existing_columns:
            op.add_column(
                "users",
                sa.Column(
                    "record_updated",
                    sa.DateTime(timezone=True),
                    nullable=True,
                    server_default=sa.func.now(),
                ),
            )
        if "record_updated_by" not in existing_columns:
            op.add_column("users", sa.Column("record_updated_by", sa.String(50), nullable=True))

        # Backfill record_created/record_updated for existing rows, then enforce NOT NULL
        op.execute(
            text(
                """
                UPDATE users
                SET
                    record_created = COALESCE(record_created, NOW()),
                    record_updated = COALESCE(record_updated, NOW())
                WHERE
                    record_created IS NULL
                    OR record_updated IS NULL;
                """
            )
        )

        op.alter_column("users", "record_created", nullable=False)
        op.alter_column("users", "record_updated", nullable=False)

        # Index on (role, is_active) if both columns exist
        if "role" in existing_columns and "is_active" in existing_columns:
            op.execute(
                "CREATE INDEX IF NOT EXISTS idx_users_role_active ON users (role, is_active)"
            )

        # Partial unique index on auth_user_id when not null
        op.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_indexes
                    WHERE schemaname = 'public'
                      AND indexname = 'users_auth_user_id_key'
                ) THEN
                    CREATE UNIQUE INDEX users_auth_user_id_key
                        ON users (auth_user_id)
                        WHERE auth_user_id IS NOT NULL;
                END IF;
            END$$;
            """
        )

        # Trigger to keep record_updated fresh
        op.execute(
            text(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_trigger
                        WHERE tgname = 'trg_users_set_record_updated'
                    ) THEN
                        CREATE TRIGGER trg_users_set_record_updated
                        BEFORE UPDATE ON users
                        FOR EACH ROW
                        EXECUTE FUNCTION public.set_record_updated_timestamp();
                    END IF;
                END$$;
                """
            )
        )

    # 3) Create public.timesheets table
    if "timesheets" not in inspector.get_table_names():
        op.create_table(
            "timesheets",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("username", sa.String(50), nullable=False),
            sa.Column("start_time", sa.DateTime(timezone=True), nullable=True),
            sa.Column("end_time", sa.DateTime(timezone=True), nullable=True),
            sa.Column("duration_minutes", sa.Integer(), nullable=True),
            sa.Column("rate", sa.Numeric(18, 2), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("delete_flag", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("record_created", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("record_created_by", sa.String(50), nullable=True),
            sa.Column("record_updated", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("record_updated_by", sa.String(50), nullable=True),
            sa.Column("legacy_id", sa.Numeric(18, 0), nullable=True),
        )

        # Time consistency check constraint
        op.execute(
            """
            ALTER TABLE timesheets
            ADD CONSTRAINT timesheets_consistent_time_chk
            CHECK (
                (start_time IS NULL AND end_time IS NULL)
                OR (start_time IS NOT NULL AND end_time IS NOT NULL AND end_time > start_time)
            );
            """
        )

        # Indexes
        op.execute(
            "CREATE INDEX idx_timesheets_user_start ON timesheets (user_id, start_time DESC)"
        )
        op.execute(
            "CREATE INDEX idx_timesheets_delete_flag ON timesheets (delete_flag)"
        )

        # Trigger to update record_updated
        op.execute(
            text(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_trigger
                        WHERE tgname = 'trg_timesheets_set_record_updated'
                    ) THEN
                        CREATE TRIGGER trg_timesheets_set_record_updated
                        BEFORE UPDATE ON timesheets
                        FOR EACH ROW
                        EXECUTE FUNCTION public.set_record_updated_timestamp();
                    END IF;
                END$$;
                """
            )
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)

    # Drop timesheets table and related artifacts
    if "timesheets" in inspector.get_table_names():
        op.execute("DROP TRIGGER IF EXISTS trg_timesheets_set_record_updated ON timesheets")
        op.execute("ALTER TABLE timesheets DROP CONSTRAINT IF EXISTS timesheets_consistent_time_chk")
        op.drop_index("idx_timesheets_delete_flag", table_name="timesheets")
        op.drop_index("idx_timesheets_user_start", table_name="timesheets")
        op.drop_table("timesheets")

    # Optionally drop added users columns (keep indexes and trigger for safety)
    if "users" in inspector.get_table_names():
        existing_columns = [c["name"] for c in inspector.get_columns("users")]
        for col in [
            "legacy_id",
            "full_name",
            "hourly_rate",
            "auth_user_id",
            "record_created",
            "record_created_by",
            "record_updated",
            "record_updated_by",
        ]:
            if col in existing_columns:
                op.drop_column("users", col)
