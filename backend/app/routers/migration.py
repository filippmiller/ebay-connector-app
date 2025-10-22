from fastapi import APIRouter, Depends, HTTPException
from app.services.auth import get_current_active_user
from app.models.user import User
from sqlalchemy import create_engine, text, inspect
from app.config import settings

router = APIRouter(prefix="/migration", tags=["migration"])

@router.post("/add-normalized-columns")
async def add_normalized_columns(current_user: User = Depends(get_current_active_user)):
    """Manually add normalized columns to ebay_orders table"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    
    engine = create_engine(settings.DATABASE_URL)
    inspector = inspect(engine)
    
    if 'ebay_orders' not in inspector.get_table_names():
        raise HTTPException(status_code=500, detail="ebay_orders table not found")
    
    existing = {col['name'] for col in inspector.get_columns('ebay_orders')}
    
    columns_to_add = [
        ("buyer_registered", "VARCHAR(100)"),
        ("order_total_value", "NUMERIC(14,2)"),
        ("order_total_currency", "CHAR(3)"),
        ("line_items_count", "INTEGER DEFAULT 0"),
        ("tracking_number", "VARCHAR(100)"),
        ("ship_to_name", "VARCHAR(255)"),
        ("ship_to_city", "VARCHAR(100)"),
        ("ship_to_state", "VARCHAR(100)"),
        ("ship_to_postal_code", "VARCHAR(20)"),
        ("ship_to_country_code", "CHAR(2)"),
        ("raw_payload", "TEXT"),
    ]
    
    added = []
    skipped = []
    
    with engine.connect() as conn:
        for col_name, col_type in columns_to_add:
            if col_name not in existing:
                sql = f"ALTER TABLE ebay_orders ADD COLUMN {col_name} {col_type}"
                conn.execute(text(sql))
                conn.commit()
                added.append(col_name)
            else:
                skipped.append(col_name)
        
        # Create line_items table
        if 'order_line_items' not in inspector.get_table_names():
            conn.execute(text("""
                CREATE TABLE order_line_items (
                    id BIGSERIAL PRIMARY KEY,
                    order_id VARCHAR(100) NOT NULL,
                    line_item_id VARCHAR(100) NOT NULL,
                    sku VARCHAR(100),
                    title TEXT,
                    quantity INTEGER DEFAULT 0,
                    total_value NUMERIC(14,2),
                    currency CHAR(3),
                    raw_payload TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    UNIQUE(order_id, line_item_id)
                )
            """))
            conn.execute(text("CREATE INDEX idx_line_items_order_id ON order_line_items(order_id)"))
            conn.commit()
            added.append("order_line_items table")
        else:
            skipped.append("order_line_items table")
    
    return {
        "status": "success",
        "added": added,
        "skipped": skipped,
        "total_columns": len(added) + len(skipped)
    }
