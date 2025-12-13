"""Add ebay_scope_definitions catalog table

Revision ID: ebay_scope_definitions_20251114
Revises: add_refresh_expires_at_20251113
Create Date: 2025-11-14

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = 'ebay_scope_definitions_20251114'
down_revision = 'add_refresh_expires_at_20251113'
branch_labels = None
depends_on = None


SCOPES = [
    # User consent grant scopes (canonical full seller set)
    {
        "scope": "https://api.ebay.com/oauth/api_scope",
        "description": "Base scope for Identity API and public data from eBay",
        "grant_type": "both",  # available for both user-consent and client-credentials
    },
    # Account / seller profile
    {
        "scope": "https://api.ebay.com/oauth/api_scope/sell.account.readonly",
        "description": "View your account settings",
        "grant_type": "user",
    },
    {
        "scope": "https://api.ebay.com/oauth/api_scope/sell.account",
        "description": "View and manage your account settings",
        "grant_type": "user",
    },
    # Fulfillment, orders, and returns
    {
        "scope": "https://api.ebay.com/oauth/api_scope/sell.fulfillment.readonly",
        "description": "View your order fulfillments",
        "grant_type": "user",
    },
    {
        "scope": "https://api.ebay.com/oauth/api_scope/sell.fulfillment",
        "description": "View and manage your order fulfillments",
        "grant_type": "user",
    },
    {
        "scope": "https://api.ebay.com/oauth/api_scope/sell.fulfillment.return.readonly",
        "description": "View return-related fulfillment details",
        "grant_type": "user",
    },
    # Buyer orders (read-only visibility for diagnostics)
    {
        "scope": "https://api.ebay.com/oauth/api_scope/buy.order.readonly",
        "description": "View buyer orders in a read-only diagnostic context",
        "grant_type": "user",
    },
    # Finances
    {
        "scope": "https://api.ebay.com/oauth/api_scope/sell.finances.readonly",
        "description": "View your payment and order-related financial information",
        "grant_type": "user",
    },
    {
        "scope": "https://api.ebay.com/oauth/api_scope/sell.finances",
        "description": "View and manage your payment and order information, including initiating refunds",
        "grant_type": "user",
    },
    # Payment disputes and cases
    {
        "scope": "https://api.ebay.com/oauth/api_scope/sell.payment.dispute.readonly",
        "description": "View payment disputes and related details",
        "grant_type": "user",
    },
    {
        "scope": "https://api.ebay.com/oauth/api_scope/sell.payment.dispute",
        "description": "View and manage payment disputes and related details",
        "grant_type": "user",
    },
    {
        "scope": "https://api.ebay.com/oauth/api_scope/sell.case.readonly",
        "description": "View case details (INR/SNAD, post-order cases)",
        "grant_type": "user",
    },
    {
        "scope": "https://api.ebay.com/oauth/api_scope/sell.case",
        "description": "View and manage case details (INR/SNAD, post-order cases)",
        "grant_type": "user",
    },
    # Inventory and offers
    {
        "scope": "https://api.ebay.com/oauth/api_scope/sell.inventory.readonly",
        "description": "View your inventory and offers",
        "grant_type": "user",
    },
    {
        "scope": "https://api.ebay.com/oauth/api_scope/sell.inventory",
        "description": "View and manage your inventory and offers",
        "grant_type": "user",
    },
    {
        "scope": "https://api.ebay.com/oauth/api_scope/sell.offer.readonly",
        "description": "View your offers and their details",
        "grant_type": "user",
    },
    {
        "scope": "https://api.ebay.com/oauth/api_scope/sell.offer",
        "description": "View and manage your offers",
        "grant_type": "user",
    },
    # Marketing
    {
        "scope": "https://api.ebay.com/oauth/api_scope/sell.marketing.readonly",
        "description": "View your eBay marketing activities, such as ad campaigns and listing promotions",
        "grant_type": "user",
    },
    {
        "scope": "https://api.ebay.com/oauth/api_scope/sell.marketing",
        "description": "View and manage your eBay marketing activities, such as ad campaigns and listing promotions",
        "grant_type": "user",
    },
    # Analytics
    {
        "scope": "https://api.ebay.com/oauth/api_scope/sell.analytics.readonly",
        "description": "View your selling analytics data, such as performance reports",
        "grant_type": "user",
    },
    # Notifications
    {
        "scope": "https://api.ebay.com/oauth/api_scope/commerce.notification.subscription",
        "description": "View and manage your event notification subscriptions",
        "grant_type": "user",
    },
    {
        "scope": "https://api.ebay.com/oauth/api_scope/commerce.notification.subscription.readonly",
        "description": "View your event notification subscriptions",
        "grant_type": "user",
    },
    # Feedback
    {
        "scope": "https://api.ebay.com/oauth/api_scope/commerce.feedback",
        "description": "Allows access to Feedback APIs.",
        "grant_type": "user",
    },
    # Messaging (new commerce.messaging scopes)
    {
        "scope": "https://api.ebay.com/oauth/api_scope/commerce.messaging.readonly",
        "description": "View your eBay messages and conversations",
        "grant_type": "user",
    },
    {
        "scope": "https://api.ebay.com/oauth/api_scope/commerce.messaging",
        "description": "View and manage your eBay messages and conversations",
        "grant_type": "user",
    },
    # Existing commerce.message scope (kept for backwards-compat or alternative APIs)
    {
        "scope": "https://api.ebay.com/oauth/api_scope/commerce.message",
        "description": "Allows access to legacy or alternate eBay Message APIs.",
        "grant_type": "user",
    },
    # Stores / reputation / identity / shipping / extras kept in catalog
    {
        "scope": "https://api.ebay.com/oauth/api_scope/commerce.identity.readonly",
        "description": "View a user's basic information, such as username or business account details, from their eBay member account",
        "grant_type": "user",
    },
    {
        "scope": "https://api.ebay.com/oauth/api_scope/sell.reputation",
        "description": "View and manage your reputation data, such as feedback",
        "grant_type": "user",
    },
    {
        "scope": "https://api.ebay.com/oauth/api_scope/sell.reputation.readonly",
        "description": "View your reputation data, such as feedback",
        "grant_type": "user",
    },
    {
        "scope": "https://api.ebay.com/oauth/api_scope/sell.stores",
        "description": "View and manage eBay stores",
        "grant_type": "user",
    },
    {
        "scope": "https://api.ebay.com/oauth/api_scope/sell.stores.readonly",
        "description": "View eBay stores",
        "grant_type": "user",
    },
    {
        "scope": "https://api.ebay.com/oauth/scope/sell.edelivery",
        "description": "Allows access to eDelivery International Shipping APIs.",
        "grant_type": "user",
    },
    {
        "scope": "https://api.ebay.com/oauth/api_scope/commerce.vero",
        "description": "Allows access to APIs that are related to eBay's Verified Rights Owner (VeRO) program.",
        "grant_type": "user",
    },
    {
        "scope": "https://api.ebay.com/oauth/api_scope/sell.inventory.mapping",
        "description": "Enables applications to manage and enhance inventory listings through the Inventory Mapping Public API.",
        "grant_type": "user",
    },
    {
        "scope": "https://api.ebay.com/oauth/api_scope/commerce.shipping",
        "description": "View and manage shipping information",
        "grant_type": "user",
    },
    # Client credentials only scopes (not requested via user-consent flows)
    {
        "scope": "https://api.ebay.com/oauth/api_scope/commerce.feedback.readonly",
        "description": "Allows readonly access to Feedback APIs.",
        "grant_type": "client",
    },
]


def upgrade():
    conn = op.get_bind()
    inspector = inspect(conn)
    tables = inspector.get_table_names()

    if 'ebay_scope_definitions' not in tables:
        op.create_table(
            'ebay_scope_definitions',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('scope', sa.Text(), nullable=False, unique=True),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('grant_type', sa.String(20), nullable=False, server_default='user'),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('meta', JSONB, nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index('idx_ebay_scope_definitions_scope', 'ebay_scope_definitions', ['scope'], unique=True)
        op.create_index('idx_ebay_scope_definitions_grant_type', 'ebay_scope_definitions', ['grant_type'])

    # Seed initial rows if table is empty
    existing = conn.execute(sa.text("SELECT COUNT(*) FROM ebay_scope_definitions")).scalar()
    if existing == 0:
        from uuid import uuid4
        rows = []
        for s in SCOPES:
            rows.append({
                'id': str(uuid4()),
                'scope': s['scope'],
                'description': s['description'],
                'grant_type': s['grant_type'],
                'is_active': True,
                'meta': None,
            })
        op.bulk_insert(sa.table(
            'ebay_scope_definitions',
            sa.column('id', sa.String(36)),
            sa.column('scope', sa.Text()),
            sa.column('description', sa.Text()),
            sa.column('grant_type', sa.String(20)),
            sa.column('is_active', sa.Boolean()),
            sa.column('meta', JSONB),
        ), rows)


def downgrade():
    conn = op.get_bind()
    inspector = inspect(conn)
    tables = inspector.get_table_names()
    if 'ebay_scope_definitions' in tables:
        op.drop_index('idx_ebay_scope_definitions_scope', table_name='ebay_scope_definitions')
        op.drop_index('idx_ebay_scope_definitions_grant_type', table_name='ebay_scope_definitions')
        op.drop_table('ebay_scope_definitions')
