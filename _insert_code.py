import sys

# Read the file
with open('backend/app/routers/grids_data.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the line with "return row" inside _serialize function (around line 1484)
insert_index = None
for i, line in enumerate(lines):
    if i > 1400 and i < 1500 and line.strip() == 'return row':
        # Check if this is inside _serialize by checking previous lines
        if any('def _serialize' in lines[j] for j in range(max(0, i-100), i)):
            insert_index = i
            break

if insert_index is None:
    print("Could not find insertion point")
    sys.exit(1)

# Code to insert
new_code = """        
        # Add formatted SKU with counts if requested
        if 'SKU_with_counts' in selected_cols and sku_col:
            sku_value = mapping.get(sku_col.key)
            if sku_value is not None:
                counts = sku_counts.get(sku_value, (0, 0))
                row['SKU_with_counts'] = f"{sku_value} ({counts[0]}/{counts[1]})"
        
        # Add formatted ItemID with counts if requested
        if 'ItemID_with_counts' in selected_cols and itemid_col:
            itemid_value = mapping.get(itemid_col.key)
            if itemid_value is not None:
                counts = itemid_counts.get(itemid_value, (0, 0))
                row['ItemID_with_counts'] = f"{itemid_value} ({counts[0]}/{counts[1]})"
        
"""

# Insert the code before "return row"
lines.insert(insert_index, new_code)

# Write back
with open('backend/app/routers/grids_data.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print(f"Successfully inserted code at line {insert_index + 1}")
