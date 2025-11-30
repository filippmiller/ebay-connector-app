"""Add generic integrations and email/AI training tables

Revision ID: gmail_integrations_20251125
Revises: ai_ebay_actions_20251125
Create Date: 2025-11-25

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = "gmail_integrations_20251125"
down_revision: Union[str, Sequence[str], None] = "ai_ebay_actions_20251125"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create integrations + email/AI training tables.

    The schema is intentionally generic so that additional providers
    (Slack, Telegram, bank APIs, etc.) can reuse the same core tables.
    """

    # Catalog of integration providers (gmail, ebay, slack, ...)
    op.create_table(
        "integrations_providers",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("auth_type", sa.String(length=32), nullable=False),
        sa.Column("default_scopes", JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "uq_integrations_providers_code",
        "integrations_providers",
        ["code"],
        unique=True,
    )

    # Individual connected accounts (per user/tenant) for each provider
    op.create_table(
        "integrations_accounts",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column(
            "provider_id",
            sa.String(length=36),
            sa.ForeignKey("integrations_providers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "owner_user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("external_account_id", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("meta", JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "idx_integrations_accounts_provider_id",
        "integrations_accounts",
        ["provider_id"],
    )
    op.create_index(
        "idx_integrations_accounts_owner_user_id",
        "integrations_accounts",
        ["owner_user_id"],
    )

    # Encrypted credentials per integration account (access/refresh tokens)
    op.create_table(
        "integrations_credentials",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column(
            "integration_account_id",
            sa.String(length=36),
            sa.ForeignKey("integrations_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("access_token", sa.Text(), nullable=True),
        sa.Column("refresh_token", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scopes", JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "idx_integrations_credentials_account_id",
        "integrations_credentials",
        ["integration_account_id"],
    )

    # Normalized email messages pulled from external providers (Gmail first)
    op.create_table(
        "emails_messages",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column(
            "integration_account_id",
            sa.String(length=36),
            sa.ForeignKey("integrations_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column("thread_id", sa.Text(), nullable=True),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("from_address", sa.Text(), nullable=True),
        sa.Column("to_addresses", JSONB, nullable=True),
        sa.Column("cc_addresses", JSONB, nullable=True),
        sa.Column("bcc_addresses", JSONB, nullable=True),
        sa.Column("subject", sa.Text(), nullable=True),
        sa.Column("body_text", sa.Text(), nullable=True),
        sa.Column("body_html", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_headers", JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    # Uniqueness per provider account and provider message id
    op.create_index(
        "uq_emails_messages_account_external_id",
        "emails_messages",
        ["integration_account_id", "external_id"],
        unique=True,
    )
    op.create_index(
        "idx_emails_messages_account",
        "emails_messages",
        ["integration_account_id"],
    )
    op.create_index(
        "idx_emails_messages_thread",
        "emails_messages",
        ["thread_id"],
    )
    op.create_index(
        "idx_emails_messages_sent_at",
        "emails_messages",
        ["sent_at"],
    )

    # AI training pairs: client question -> our reply, built from email threads
    op.create_table(
        "ai_training_pairs",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column(
            "integration_account_id",
            sa.String(length=36),
            sa.ForeignKey("integrations_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("thread_id", sa.Text(), nullable=True),
        sa.Column(
            "client_message_id",
            sa.String(length=36),
            sa.ForeignKey("emails_messages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "our_reply_message_id",
            sa.String(length=36),
            sa.ForeignKey("emails_messages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("client_text", sa.Text(), nullable=False),
        sa.Column("our_reply_text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="new"),
        sa.Column("labels", JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "idx_ai_training_pairs_status",
        "ai_training_pairs",
        ["status"],
    )
    op.create_index(
        "idx_ai_training_pairs_integration_account",
        "ai_training_pairs",
        ["integration_account_id"],
    )
    op.create_index(
        "idx_ai_training_pairs_thread",
        "ai_training_pairs",
        ["thread_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_ai_training_pairs_thread", table_name="ai_training_pairs")
    op.drop_index(
        "idx_ai_training_pairs_integration_account",
        table_name="ai_training_pairs",
    )
    op.drop_index("idx_ai_training_pairs_status", table_name="ai_training_pairs")
    op.drop_table("ai_training_pairs")

    op.drop_index("idx_emails_messages_sent_at", table_name="emails_messages")
    op.drop_index("idx_emails_messages_thread", table_name="emails_messages")
    op.drop_index("idx_emails_messages_account", table_name="emails_messages")
    op.drop_index(
        "uq_emails_messages_account_external_id",
        table_name="emails_messages",
    )
    op.drop_table("emails_messages")

    op.drop_index(
        "idx_integrations_credentials_account_id",
        table_name="integrations_credentials",
    )
    op.drop_table("integrations_credentials")

    op.drop_index(
        "idx_integrations_accounts_owner_user_id",
        table_name="integrations_accounts",
    )
    op.drop_index(
        "idx_integrations_accounts_provider_id",
        table_name="integrations_accounts",
    )
    op.drop_table("integrations_accounts")

    op.drop_index(
        "uq_integrations_providers_code",
        table_name="integrations_providers",
    )
    op.drop_table("integrations_providers")
