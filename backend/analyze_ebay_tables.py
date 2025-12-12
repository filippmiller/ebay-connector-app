import os
import json
from sqlalchemy import create_engine, text, inspect
from dotenv import load_dotenv
from decimal import Decimal
from datetime import datetime

# Load environment variables
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    print(json.dumps({"error": "DATABASE_URL not found in .env"}))
    exit(1)

# Create engine
engine = create_engine(DATABASE_URL)
inspector = inspect(engine)

# Helper to serialize results
def json_serial(obj):
    if isinstance(obj, (datetime,)):
        return obj.isoformat()
    if isinstance(obj, (Decimal,)):
        return float(obj)
    raise TypeError(f"Type {type(obj)} not serializable")

def analyze_table(table_name, proposed_keys):
    result = {
        "table_name": table_name,
        "exists": False,
        "row_count": 0,
        "columns": [],
        "constraints": [],
        "duplicate_analysis": []
    }

    if not inspector.has_table(table_name):
        return result

    result["exists"] = True

    # Row count
    with engine.connect() as conn:
        try:
            result["row_count"] = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar()
        except Exception as e:
            result["error"] = str(e)
            return result

    # Columns
    columns = inspector.get_columns(table_name)
    result["columns"] = [{"name": c["name"], "type": str(c["type"]), "nullable": c["nullable"]} for c in columns]
    col_names = set(c["name"] for c in result["columns"])

    # Constraints
    pk = inspector.get_pk_constraint(table_name)
    result["constraints"].append({"type": "PK", "columns": pk["constrained_columns"]})
    
    unique_constraints = inspector.get_unique_constraints(table_name)
    for uc in unique_constraints:
        result["constraints"].append({"type": "UNIQUE", "columns": uc["column_names"]})

    # Duplicate Analysis
    for key_tuple in proposed_keys:
        # Check if all columns exist
        if not all(k in col_names for k in key_tuple):
            result["duplicate_analysis"].append({
                "key": key_tuple,
                "status": "SKIPPED_MISSING_COLUMNS"
            })
            continue

        key_str = ", ".join(key_tuple)
        
        with engine.connect() as conn:
            # Count duplicate groups
            sql = f"""
                SELECT {key_str}, COUNT(*) as cnt 
                FROM {table_name} 
                GROUP BY {key_str} 
                HAVING COUNT(*) > 1
            """
            duplicates = conn.execute(text(sql)).fetchall()
            
            num_groups = len(duplicates)
            total_rows_in_dupes = sum(row.cnt for row in duplicates)
            
            analysis = {
                "key": key_tuple,
                "status": "OK",
                "num_duplicate_groups": num_groups,
                "total_rows_in_duplicates": total_rows_in_dupes,
                "examples": []
            }

            # Get examples (top 3 groups)
            if num_groups > 0:
                top_dupes = sorted(duplicates, key=lambda x: x.cnt, reverse=True)[:3]
                for dupe in top_dupes:
                    # Construct WHERE clause for this group
                    where_clauses = []
                    params = {}
                    for i, col in enumerate(key_tuple):
                        val = dupe[i]
                        # Handle NULLs in key (though unlikely for business keys)
                        if val is None:
                            where_clauses.append(f"{col} IS NULL")
                        else:
                            where_clauses.append(f"{col} = :p_{i}")
                            params[f"p_{i}"] = val
                    
                    where_str = " AND ".join(where_clauses)
                    example_sql = f"SELECT * FROM {table_name} WHERE {where_str} LIMIT 5"
                    example_rows = conn.execute(text(example_sql), params).fetchall()
                    
                    # Convert rows to dicts
                    row_dicts = []
                    for r in example_rows:
                        row_dicts.append(dict(r._mapping))

                    analysis["examples"].append({
                        "key_values": {k: v for k, v in zip(key_tuple, dupe)},
                        "count": dupe.cnt,
                        "rows": row_dicts
                    })

            result["duplicate_analysis"].append(analysis)

    return result

# Define tables and keys to analyze
targets = [
    ("ebay_orders", [("order_id", "user_id"), ("order_id", "ebay_account_id")]),
    ("order_line_items", [("order_id", "line_item_id")]),
    ("ebay_transactions", [("transaction_id", "user_id"), ("transaction_id", "ebay_account_id")]),
    ("ebay_finances_transactions", [("transaction_id", "transaction_type", "ebay_account_id")]),
    ("ebay_finances_fees", [("transaction_id", "fee_type", "amount_value", "ebay_account_id")]),
    ("ebay_disputes", [("dispute_id", "user_id")]),
    ("ebay_cases", [("case_id", "user_id")]),
    ("ebay_inquiries", [("inquiry_id", "user_id")]),
    ("ebay_returns", [("return_id", "user_id")]),
    ("ebay_offers", [("offer_id", "user_id")]),
    ("ebay_active_inventory", [("sku", "ebay_account_id")]),
    ("ebay_messages", [("message_id", "user_id")]),
    ("emails_messages", [("external_id", "integration_account_id")]),
    ("ebay_sync_jobs", []), # Just structure
    ("ebay_events", [])     # Just structure
]

output = []
for table, keys in targets:
    print(f"Analyzing {table}...")
    output.append(analyze_table(table, keys))

# Write to file
with open("analysis_results.json", "w") as f:
    json.dump(output, f, default=json_serial, indent=2)

print("Analysis complete. Results written to analysis_results.json")
