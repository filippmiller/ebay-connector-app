"""Relax timesheets time constraint to allow open timers

Revision ID: timesheets_open_timer_20251124
Revises: user_must_change_password_20251124
Create Date: 2025-11-24

This migration updates the timesheets_consistent_time_chk constraint so that
rows representing an "open" timer (start_time NOT NULL, end_time NULL) are
considered valid. Closed timers still require end_time > start_time.
"""

from alembic import op
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision = "timesheets_open_timer_20251124"
down_revision = "user_must_change_password_20251124"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop the old constraint if it exists, then create the relaxed version.
    # The previous definition only allowed (NULL, NULL) or (NOT NULL, NOT NULL
    # with end_time > start_time), which rejected open timers.
    op.execute(
        text(
            """
            ALTER TABLE timesheets
            DROP CONSTRAINT IF EXISTS timesheets_consistent_time_chk;
            """
        )
    )

    op.execute(
        text(
            """
            ALTER TABLE timesheets
            ADD CONSTRAINT timesheets_consistent_time_chk
            CHECK (
                -- fully empty slot (likely unused)
                (start_time IS NULL AND end_time IS NULL)
                OR
                -- open timer: start set, end not yet known
                (start_time IS NOT NULL AND end_time IS NULL)
                OR
                -- closed timer: both set and end strictly after start
                (start_time IS NOT NULL AND end_time IS NOT NULL AND end_time > start_time)
            );
            """
        )
    )


def downgrade() -> None:
    # Restore the original stricter constraint definition: only allow
    # (NULL, NULL) or (NOT NULL, NOT NULL AND end_time > start_time).
    op.execute(
        text(
            """
            ALTER TABLE timesheets
            DROP CONSTRAINT IF EXISTS timesheets_consistent_time_chk;
            """
        )
    )

    op.execute(
        text(
            """
            ALTER TABLE timesheets
            ADD CONSTRAINT timesheets_consistent_time_chk
            CHECK (
                (start_time IS NULL AND end_time IS NULL)
                OR (start_time IS NOT NULL AND end_time IS NOT NULL AND end_time > start_time)
            );
            """
        )
    )
