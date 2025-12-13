"""Schema discovery module for AI Assistant.

Reads database schema from information_schema and populates
ai_schema_tables and ai_schema_columns for AI context.
"""

from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.utils.logger import logger

# Tables to exclude from schema discovery
DEFAULT_BLACKLIST = [
    'alembic_version',
    'pg_%',  # PostgreSQL system tables
    'sql_%',  # SQL standard tables
]


async def refresh_schema_catalog(
    db: Session,
    whitelist: Optional[List[str]] = None,
    blacklist: Optional[List[str]] = None,
) -> Dict[str, int]:
    """Discover schema from information_schema and populate catalog.
    
    Args:
        db: Database session
        whitelist: If provided, ONLY include these tables (exact match)
        blacklist: Tables/patterns to exclude (supports % wildcard)
    
    Returns:
        {"tables": count, "columns": count}
    """
    
    if blacklist is None:
        blacklist = DEFAULT_BLACKLIST.copy()
    
    # Build WHERE clause for table filtering
    where_clauses = ["table_schema = 'public'"]
    
    if whitelist:
        # Exact match for whitelist
        table_list = "', '".join(whitelist)
        where_clauses.append(f"table_name IN ('{table_list}')")
    else:
        # Exclude blacklisted patterns
        for pattern in blacklist:
            if '%' in pattern:
                where_clauses.append(f"table_name NOT LIKE '{pattern}'")
            else:
                where_clauses.append(f"table_name != '{pattern}'")
    
    where_sql = " AND ".join(where_clauses)
    
    # Query tables
    tables_query = f"""
        SELECT 
            table_schema,
            table_name
        FROM information_schema.tables
        WHERE {where_sql}
        ORDER BY table_name
    """
    
    result = db.execute(text(tables_query))
    discovered_tables = result.fetchall()
    
    logger.info(f"Schema discovery: found {len(discovered_tables)} tables")
    
    tables_upserted = 0
    columns_upserted = 0
    
    for schema_name, table_name in discovered_tables:
        # Generate human-friendly title
        human_title = _generate_human_title(table_name)
        human_description = f"Table: {table_name}"
        
        # Upsert table
        upsert_table_sql = """
            INSERT INTO ai_schema_tables (schema_name, table_name, human_title, human_description, is_active)
            VALUES (:schema_name, :table_name, :human_title, :human_description, true)
            ON CONFLICT (schema_name, table_name) 
            DO UPDATE SET 
                human_title = EXCLUDED.human_title,
                human_description = EXCLUDED.human_description,
                updated_at = NOW()
            RETURNING id
        """
        
        table_result = db.execute(
            text(upsert_table_sql),
            {
                "schema_name": schema_name,
                "table_name": table_name,
                "human_title": human_title,
                "human_description": human_description,
            }
        )
        table_id = table_result.scalar()
        tables_upserted += 1
        
        # Query columns for this table
        columns_query = """
            SELECT 
                column_name,
                data_type,
                is_nullable
            FROM information_schema.columns
            WHERE table_schema = :schema_name
              AND table_name = :table_name
            ORDER BY ordinal_position
        """
        
        columns_result = db.execute(
            text(columns_query),
            {"schema_name": schema_name, "table_name": table_name}
        )
        columns = columns_result.fetchall()
        
        for column_name, data_type, is_nullable_str in columns:
            is_nullable = is_nullable_str == 'YES'
            column_human_title = _generate_human_title(column_name)
            
            # Upsert column
            upsert_column_sql = """
                INSERT INTO ai_schema_columns (
                    table_id, column_name, data_type, is_nullable,
                    human_title, human_description
                )
                VALUES (
                    :table_id, :column_name, :data_type, :is_nullable,
                    :human_title, :human_description
                )
                ON CONFLICT (table_id, column_name)
                DO UPDATE SET
                    data_type = EXCLUDED.data_type,
                    is_nullable = EXCLUDED.is_nullable,
                    human_title = EXCLUDED.human_title,
                    updated_at = NOW()
            """
            
            db.execute(
                text(upsert_column_sql),
                {
                    "table_id": table_id,
                    "column_name": column_name,
                    "data_type": data_type,
                    "is_nullable": is_nullable,
                    "human_title": column_human_title,
                    "human_description": f"{data_type} column",
                }
            )
            columns_upserted += 1
    
    db.commit()
    
    logger.info(
        f"Schema catalog refreshed: {tables_upserted} tables, {columns_upserted} columns"
    )
    
    return {
        "tables": tables_upserted,
        "columns": columns_upserted,
    }


def _generate_human_title(identifier: str) -> str:
    """Generate human-friendly title from table/column name.
    
    Examples:
        tbl_orders → Orders
        user_id → User ID
        created_at → Created At
        ebay_item_id → eBay Item ID
    """
    
    # Remove common prefixes
    name = identifier
    for prefix in ['tbl_', 'idx_', 'fk_', 'uq_']:
        if name.startswith(prefix):
            name = name[len(prefix):]
    
    # Split by underscore
    words = name.split('_')
    
    # Capitalize each word
    titled_words = []
    for word in words:
        if word.upper() in ['ID', 'URL', 'API', 'SKU', 'UUID', 'JSON']:
            titled_words.append(word.upper())
        elif word.lower() == 'ebay':
            titled_words.append('eBay')
        else:
            titled_words.append(word.capitalize())
    
    return ' '.join(titled_words)
