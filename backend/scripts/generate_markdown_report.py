import json
import os
import datetime

INPUT_FILE = "docs/ebay_tables_analytics.json"
OUTPUT_FILE = f"docs/ebay-workers-tables-analytics-{datetime.datetime.now().strftime('%Y%m%d')}.md"

WORKER_MAPPINGS = {
    "OrdersWorker": ["ebay_orders", "order_line_items", "purchases"],
    "TransactionsWorker": ["ebay_transactions"],
    "FinancesWorker": ["ebay_finances_transactions", "ebay_finances_fees"],
    "DisputesWorker": ["ebay_disputes"],
    "CasesWorker": ["ebay_cases"],
    "InquiriesWorker": ["ebay_inquiries"],
    "ReturnsWorker": ["ebay_returns"],
    "OffersWorker": ["ebay_offers"],
    "ActiveInventoryWorker": ["ebay_active_inventory", "inventory"],
    "MessagesWorker": ["ebay_messages", "emails_messages"],
    "System/Scheduler": ["ebay_sync_jobs", "ebay_events"]
}

def propose_business_keys(table_name, columns, unique_constraints, pk_constraint):
    candidates = []
    col_names = [c['name'] for c in columns]
    
    # Check existing unique constraints
    if unique_constraints:
        for uc in unique_constraints:
            candidates.append({
                "keys": uc['column_names'],
                "reason": "Existing Unique Constraint"
            })
            
    # Check PK
    if pk_constraint and pk_constraint['constrained_columns']:
        candidates.append({
            "keys": pk_constraint['constrained_columns'],
            "reason": "Primary Key"
        })

    # Heuristic proposals
    if "ebay_orders" in table_name:
        if "order_id" in col_names:
             candidates.append({"keys": ["order_id"], "reason": "eBay Order ID is usually unique globally."})
        if "ebay_account_id" in col_names and "order_id" in col_names:
             candidates.append({"keys": ["ebay_account_id", "order_id"], "reason": "Composite: Account + Order ID (safer for multi-account)."})

    elif "line_items" in table_name:
        if "line_item_id" in col_names:
            candidates.append({"keys": ["line_item_id"], "reason": "Line Item ID"})
        if "order_line_item_id" in col_names:
            candidates.append({"keys": ["order_line_item_id"], "reason": "Order Line Item ID"})

    elif "transactions" in table_name:
        if "transaction_id" in col_names:
            candidates.append({"keys": ["transaction_id"], "reason": "eBay Transaction ID"})
        if "ebay_account_id" in col_names and "transaction_id" in col_names:
             candidates.append({"keys": ["ebay_account_id", "transaction_id"], "reason": "Composite: Account + Transaction ID"})

    elif "inventory" in table_name:
        if "sku" in col_names:
            candidates.append({"keys": ["sku"], "reason": "SKU should be unique per account"})
        if "ebay_account_id" in col_names and "sku" in col_names:
             candidates.append({"keys": ["ebay_account_id", "sku"], "reason": "Composite: Account + SKU"})
        if "item_id" in col_names:
             candidates.append({"keys": ["item_id"], "reason": "eBay Item ID"})

    elif "messages" in table_name:
        if "message_id" in col_names:
            candidates.append({"keys": ["message_id"], "reason": "eBay Message ID"})
    
    elif "offers" in table_name:
        if "offer_id" in col_names:
            candidates.append({"keys": ["offer_id"], "reason": "eBay Offer ID"})

    # Deduplicate candidates
    unique_candidates = []
    seen = set()
    for c in candidates:
        key_tuple = tuple(sorted(c['keys']))
        if key_tuple not in seen:
            seen.add(key_tuple)
            unique_candidates.append(c)
            
    return unique_candidates

def generate_markdown():
    if not os.path.exists(INPUT_FILE):
        print(f"Input file {INPUT_FILE} not found.")
        return

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    md = []
    md.append(f"# eBay Workers Table Analytics ({datetime.datetime.now().strftime('%Y-%m-%d')})\n")
    
    md.append("## 1. Worker-Table Mappings\n")
    md.append("| Worker Name | Target Tables |")
    md.append("|---|---|")
    for worker, tables in WORKER_MAPPINGS.items():
        md.append(f"| **{worker}** | `{', '.join(tables)}` |")
    md.append("\n")

    md.append("## 2. Table Analysis\n")
    
    for table_name, info in data.items():
        if "error" in info:
            md.append(f"### Table: `{table_name}` (Error)\n")
            md.append(f"> Error: {info['error']}\n")
            continue

        md.append(f"### Table: `{table_name}`\n")
        md.append(f"- **Row Count**: {info.get('row_count', 'Unknown')}")
        
        # Schema
        md.append("\n#### Schema\n")
        md.append("| Column | Type | Nullable | Default |")
        md.append("|---|---|---|---|")
        for col in info.get('columns', []):
            default_val = col.get('default', '')
            if default_val is None: default_val = ''
            md.append(f"| `{col['name']}` | `{col['type']}` | {col['nullable']} | `{default_val}` |")
        
        # Keys
        md.append("\n#### Keys & Indexes\n")
        pk = info.get('primary_key')
        if pk and pk.get('constrained_columns'):
            md.append(f"- **Primary Key**: `{', '.join(pk['constrained_columns'])}`")
        
        unique = info.get('unique_constraints', [])
        if unique:
            md.append("- **Unique Constraints**:")
            for u in unique:
                md.append(f"  - `{', '.join(u['column_names'])}`")
        
        # Candidate Business Keys
        md.append("\n#### Candidate Business Keys\n")
        candidates = propose_business_keys(table_name, info.get('columns', []), unique, pk)
        if candidates:
            for c in candidates:
                md.append(f"- **Keys**: `{', '.join(c['keys'])}`")
                md.append(f"  - *Reason*: {c['reason']}")
        else:
            md.append("- *No obvious candidate keys found based on heuristics.*")

        # Sample Data
        md.append("\n#### Sample Data (Last 50 Rows)\n")
        samples = info.get('sample_rows', [])
        if samples:
            md.append("<details>")
            md.append("<summary>Click to expand JSON samples</summary>\n")
            md.append("```json")
            md.append(json.dumps(samples, indent=2, default=str))
            md.append("```\n")
            md.append("</details>\n")
        else:
            md.append("*No sample data available.*\n")
        
        md.append("---\n")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    
    print(f"Markdown report generated: {OUTPUT_FILE}")

if __name__ == "__main__":
    generate_markdown()
