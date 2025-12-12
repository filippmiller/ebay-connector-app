"""Create classification codes table with initial data

Revision ID: classification_codes_20251206
Revises: fix_nullable_user_id_20251206
Create Date: 2025-12-06 16:30:00.000000

"""
from typing import Sequence, Union
from datetime import datetime

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'classification_codes_20251206'
down_revision: Union[str, Sequence[str], None] = 'fix_nullable_user_id_20251206'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Initial classification codes from our schema
INITIAL_CODES = [
    # Income
    {"code": "INCOME_EBAY_PAYOUT", "name": "eBay Marketplace Payout", "group": "INCOME", "description": "Deposits from eBay sales", "keywords": "ebay,marketplace,payout"},
    {"code": "INCOME_AMAZON_PAYOUT", "name": "Amazon Seller Payout", "group": "INCOME", "description": "Deposits from Amazon sales", "keywords": "amazon,seller,payout"},
    {"code": "INCOME_STRIPE", "name": "Stripe Deposit", "group": "INCOME", "description": "Stripe payment processing deposits", "keywords": "stripe"},
    {"code": "INCOME_PAYPAL", "name": "PayPal Transfer", "group": "INCOME", "description": "PayPal incoming transfers", "keywords": "paypal"},
    {"code": "INCOME_OTHER", "name": "Other Income", "group": "INCOME", "description": "Miscellaneous income", "keywords": None},
    
    # COGS
    {"code": "COGS_INVENTORY_PURCHASE", "name": "Inventory Purchase", "group": "COGS", "description": "Purchases of inventory for resale", "keywords": "inventory,purchase,supplier"},
    {"code": "COGS_SHIPPING_SUPPLY", "name": "Shipping Supplies", "group": "COGS", "description": "Boxes, tape, labels, etc.", "keywords": "shipping,supply,box,tape,label"},
    {"code": "COGS_SUPPLIER_PAYMENT", "name": "Supplier Payment", "group": "COGS", "description": "Payments to suppliers", "keywords": "supplier,vendor"},
    {"code": "COGS_OTHER", "name": "Other COGS", "group": "COGS", "description": "Other cost of goods sold", "keywords": None},
    
    # Operating Expenses
    {"code": "OPEX_SOFTWARE", "name": "Software & Subscriptions", "group": "OPERATING_EXPENSE", "description": "Software, SaaS subscriptions", "keywords": "software,subscription,app,saas"},
    {"code": "OPEX_RENT", "name": "Rent", "group": "OPERATING_EXPENSE", "description": "Office/warehouse rent", "keywords": "rent,lease"},
    {"code": "OPEX_UTILITIES", "name": "Utilities", "group": "OPERATING_EXPENSE", "description": "Electric, gas, water, internet", "keywords": "utility,electric,gas,water,internet"},
    {"code": "OPEX_INSURANCE", "name": "Insurance", "group": "OPERATING_EXPENSE", "description": "Business insurance", "keywords": "insurance"},
    {"code": "OPEX_SHIPPING", "name": "Outgoing Shipping", "group": "OPERATING_EXPENSE", "description": "Shipping costs to customers", "keywords": "shipping,usps,ups,fedex,dhl"},
    {"code": "OPEX_ADVERTISING", "name": "Advertising", "group": "OPERATING_EXPENSE", "description": "Marketing and advertising", "keywords": "advertising,marketing,ads,google,facebook"},
    {"code": "OPEX_OFFICE_SUPPLIES", "name": "Office Supplies", "group": "OPERATING_EXPENSE", "description": "Office supplies and equipment", "keywords": "office,supplies,staples"},
    {"code": "OPEX_PROFESSIONAL_SERVICES", "name": "Professional Services", "group": "OPERATING_EXPENSE", "description": "Accounting, legal, consulting", "keywords": "legal,accounting,consulting,cpa"},
    {"code": "OPEX_OTHER", "name": "Other Operating Expense", "group": "OPERATING_EXPENSE", "description": "Miscellaneous operating expenses", "keywords": None},
    
    # Bank Fees
    {"code": "FEE_BANK_SERVICE", "name": "Bank Service Fee", "group": "BANK_FEE", "description": "Monthly service charges", "keywords": "service,fee,charge,maintenance"},
    {"code": "FEE_WIRE_TRANSFER", "name": "Wire Transfer Fee", "group": "BANK_FEE", "description": "Wire transfer fees", "keywords": "wire,transfer"},
    {"code": "FEE_OVERDRAFT", "name": "Overdraft Fee", "group": "BANK_FEE", "description": "Overdraft charges", "keywords": "overdraft,nsf"},
    {"code": "FEE_INTERNATIONAL", "name": "International Transaction Fee", "group": "BANK_FEE", "description": "International/foreign transaction fees", "keywords": "international,foreign,intl"},
    {"code": "FEE_OTHER", "name": "Other Bank Fee", "group": "BANK_FEE", "description": "Other bank fees", "keywords": None},
    {"code": "INTEREST_EARNED", "name": "Interest Earned", "group": "INTEREST_INCOME", "description": "Interest income from bank", "keywords": "interest,earned"},
    
    # Payroll
    {"code": "PAYROLL_WAGE", "name": "Wages & Salaries", "group": "PAYROLL", "description": "Employee wages", "keywords": "payroll,wage,salary,paychex,adp,gusto"},
    {"code": "PAYROLL_TAX", "name": "Payroll Taxes", "group": "PAYROLL", "description": "Employer payroll taxes", "keywords": "payroll,tax,eftps,irs"},
    {"code": "PAYROLL_BENEFIT", "name": "Employee Benefits", "group": "PAYROLL", "description": "Health insurance, 401k, etc.", "keywords": "benefit,health,401k,insurance"},
    {"code": "PAYROLL_CONTRACTOR", "name": "Contractor Payments", "group": "PAYROLL", "description": "1099 contractor payments", "keywords": "contractor,1099"},
    
    # Taxes
    {"code": "TAX_SALES", "name": "Sales Tax", "group": "TAXES", "description": "Sales tax payments", "keywords": "sales,tax"},
    {"code": "TAX_INCOME", "name": "Income Tax", "group": "TAXES", "description": "Business income tax", "keywords": "income,tax,irs,federal,state"},
    {"code": "TAX_PROPERTY", "name": "Property Tax", "group": "TAXES", "description": "Property taxes", "keywords": "property,tax"},
    {"code": "TAX_OTHER", "name": "Other Taxes", "group": "TAXES", "description": "Other tax payments", "keywords": None},
    
    # Transfers
    {"code": "TRANSFER_INTERNAL", "name": "Internal Transfer", "group": "TRANSFER", "description": "Transfers between own accounts", "keywords": "transfer,internal"},
    {"code": "TRANSFER_OWNER_DRAW", "name": "Owner Draw", "group": "OWNER_DRAW", "description": "Owner/member distributions", "keywords": "owner,draw,distribution"},
    {"code": "TRANSFER_LOAN_PAYMENT", "name": "Loan Payment", "group": "TRANSFER", "description": "Business loan payments", "keywords": "loan,payment"},
    {"code": "TRANSFER_OTHER", "name": "Other Transfer", "group": "TRANSFER", "description": "Other transfers", "keywords": None},
    
    # Personal
    {"code": "PERSONAL_EXPENSE", "name": "Personal Expense", "group": "PERSONAL", "description": "Personal (non-business) expense - flagged for review", "keywords": None},
    
    # Unknown
    {"code": "UNKNOWN", "name": "Unknown / Needs Review", "group": "OTHER", "description": "Transaction needs manual classification", "keywords": None},
    {"code": "NEEDS_REVIEW", "name": "Flagged for Review", "group": "OTHER", "description": "Transaction flagged for manual review", "keywords": None},
]

# Accounting groups
ACCOUNTING_GROUPS = [
    {"code": "INCOME", "name": "Income", "description": "Revenue from sales and services", "color": "#22c55e"},
    {"code": "COGS", "name": "Cost of Goods Sold", "description": "Direct costs of products sold", "color": "#f97316"},
    {"code": "OPERATING_EXPENSE", "name": "Operating Expense", "description": "General business expenses", "color": "#ef4444"},
    {"code": "BANK_FEE", "name": "Bank Fees", "description": "Bank charges and fees", "color": "#6b7280"},
    {"code": "INTEREST_INCOME", "name": "Interest Income", "description": "Interest earned on deposits", "color": "#10b981"},
    {"code": "PAYROLL", "name": "Payroll", "description": "Wages, taxes, and benefits", "color": "#8b5cf6"},
    {"code": "TAXES", "name": "Taxes", "description": "Tax payments", "color": "#dc2626"},
    {"code": "TRANSFER", "name": "Transfer", "description": "Money movement between accounts", "color": "#3b82f6"},
    {"code": "OWNER_DRAW", "name": "Owner Draw", "description": "Owner/member distributions", "color": "#a855f7"},
    {"code": "PERSONAL", "name": "Personal", "description": "Personal expenses (non-business)", "color": "#ec4899"},
    {"code": "OTHER", "name": "Other", "description": "Uncategorized transactions", "color": "#9ca3af"},
]


def upgrade() -> None:
    # Create accounting_group table
    op.create_table(
        'accounting_group',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('code', sa.Text(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('color', sa.Text(), nullable=True, server_default='#6b7280'),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code', name='uq_accounting_group_code'),
    )
    op.create_index('idx_accounting_group_code', 'accounting_group', ['code'])
    
    # Create classification codes table
    op.create_table(
        'accounting_classification_code',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('code', sa.Text(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('accounting_group', sa.Text(), nullable=False),
        sa.Column('keywords', sa.Text(), nullable=True),  # Comma-separated keywords for auto-classification
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('is_system', sa.Boolean(), nullable=False, server_default='false'),  # System codes can't be deleted
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code', name='uq_classification_code'),
    )
    op.create_index('idx_classification_code_code', 'accounting_classification_code', ['code'])
    op.create_index('idx_classification_code_group', 'accounting_classification_code', ['accounting_group'])
    op.create_index('idx_classification_code_active', 'accounting_classification_code', ['is_active'])
    
    # Seed accounting groups
    groups_table = sa.table(
        'accounting_group',
        sa.column('code', sa.Text),
        sa.column('name', sa.Text),
        sa.column('description', sa.Text),
        sa.column('color', sa.Text),
        sa.column('sort_order', sa.Integer),
        sa.column('is_active', sa.Boolean),
    )
    
    op.bulk_insert(groups_table, [
        {
            "code": g["code"],
            "name": g["name"],
            "description": g["description"],
            "color": g["color"],
            "sort_order": i,
            "is_active": True,
        }
        for i, g in enumerate(ACCOUNTING_GROUPS)
    ])
    
    # Seed classification codes
    codes_table = sa.table(
        'accounting_classification_code',
        sa.column('code', sa.Text),
        sa.column('name', sa.Text),
        sa.column('description', sa.Text),
        sa.column('accounting_group', sa.Text),
        sa.column('keywords', sa.Text),
        sa.column('sort_order', sa.Integer),
        sa.column('is_active', sa.Boolean),
        sa.column('is_system', sa.Boolean),
    )
    
    op.bulk_insert(codes_table, [
        {
            "code": c["code"],
            "name": c["name"],
            "description": c["description"],
            "accounting_group": c["group"],
            "keywords": c["keywords"],
            "sort_order": i,
            "is_active": True,
            "is_system": True,  # Initial codes are system codes
        }
        for i, c in enumerate(INITIAL_CODES)
    ])


def downgrade() -> None:
    op.drop_table('accounting_classification_code')
    op.drop_table('accounting_group')
