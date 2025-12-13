import os
import json
import datetime
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import URL

# List of tables to analyze
TABLES = [
    "ebay_orders",
    "order_line_items",
    "ebay_transactions",
    "ebay_finances_transactions",
    "ebay_finances_fees",
    "ebay_disputes",
    "ebay_cases",
    "ebay_inquiries",
    "ebay_returns",
    "ebay_offers",
    "inventory",
    "ebay_messages",
    "ebay_sync_jobs",
    "ebay_events",
    "ebay_active_inventory",
    "purchases",
    "emails_messages"
]

def get_database_url():
    # Try to get from env var first
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    
    # Fallback to reading from railway_vars_dump.json if available
    try:
        with open("railway_vars_dump.json", "r", encoding="utf-16") as f:
            data = json.load(f)
            return data.get("DATABASE_URL")
    except Exception as e:
        print(f"Error reading railway_vars_dump.json: {e}")
        return None

def json_serial(obj):
    """JSON serializer for objects not serializable by default json code"""
    if isinstance(obj, (datetime.datetime, datetime.date)):
        return obj.isoformat()
    if isinstance(obj, bytes):
        return "<binary>"
    return str(obj)

def analyze_table(inspector, engine, table_name):
    print(f"Analyzing {table_name}...")
    try:
        # Schema
        columns = inspector.get_columns(table_name)
        pk_constraint = inspector.get_pk_constraint(table_name)
        unique_constraints = inspector.get_unique_constraints(table_name)
        indexes = inspector.get_indexes(table_name)
        
        # Row count
        with engine.connect() as conn:
            try:
                count_result = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
                row_count = count_result.scalar()
            except Exception as e:
                print(f"Error counting rows for {table_name}: {e}")
                row_count = -1

            # Sample rows (last 50)
            # Try to find a good sort column
            sort_col = None
            col_names = [c['name'] for c in columns]
            if 'created_at' in col_names:
                sort_col = 'created_at'
            elif 'id' in col_names:
                sort_col = 'id'
            
            sample_rows = []
            if sort_col:
                try:
                    query = text(f"SELECT * FROM {table_name} ORDER BY {sort_col} DESC LIMIT 50")
                    result = conn.execute(query)
                    keys = list(result.keys())
                    for row in result:
                        row_dict = {}
                        for i, val in enumerate(row):
                            row_dict[keys[i]] = val
                        sample_rows.append(row_dict)
                except Exception as e:
                    print(f"Error fetching samples for {table_name}: {e}")
            else:
                # Fallback to no sort
                try:
                    query = text(f"SELECT * FROM {table_name} LIMIT 50")
                    result = conn.execute(query)
                    keys = list(result.keys())
                    for row in result:
                        row_dict = {}
                        for i, val in enumerate(row):
                            row_dict[keys[i]] = val
                        sample_rows.append(row_dict)
                except Exception as e:
                    print(f"Error fetching samples for {table_name}: {e}")

        return {
            "table_name": table_name,
            "row_count": row_count,
            "columns": columns,
            "primary_key": pk_constraint,
            "unique_constraints": unique_constraints,
            "indexes": indexes,
            "sample_rows": sample_rows
        }
    except Exception as e:
        print(f"Error analyzing {table_name}: {e}")
        return {
            "table_name": table_name,
            "error": str(e)
        }

def main():
    db_url = get_database_url()
    if not db_url:
        print("DATABASE_URL not found.")
        return

    print(f"Connecting to database...")
    engine = create_engine(db_url)
    inspector = inspect(engine)

    results = {}
    
    # Verify tables exist
    existing_tables = inspector.get_table_names()
    print(f"Found {len(existing_tables)} tables in database.")
    
    for table in TABLES:
        if table in existing_tables:
            results[table] = analyze_table(inspector, engine, table)
        else:
            print(f"Table {table} not found in database.")
            results[table] = {"error": "Table not found"}

    # Output to JSON
    output_path = "docs/ebay_tables_analytics.json"
    os.makedirs("docs", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, default=json_serial, indent=2)
    
    print(f"Analysis complete. Results saved to {output_path}")

if __name__ == "__main__":
    main()
