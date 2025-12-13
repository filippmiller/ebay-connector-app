# Bank Statement Grid Empty Display - FIXED

## Problem
The bank statements grid was showing "Showing 1-2 of 2" but displaying empty rows. Console showed data was being fetched successfully, but the grid cells were blank.

## Root Cause
The backend serialization function in `grids_data.py` was **skipping columns with `None` values** using `continue` statements. This meant that when a bank statement had null values for certain fields (like `statement_period_start`, `bank_name`, etc.), those columns would be completely missing from the row object sent to the frontend.

AG Grid requires **all column fields to be present** in every row object, even if their value is `null`. When columns are missing from the data, AG Grid can't properly render the cells, resulting in empty rows.

## Solution
Modified the `_serialize` functions in three accounting grid endpoints:

1. **`_get_accounting_bank_statements_data`** (line 2480-2499)
2. **`_get_active_inventory_data`** (line 2414-2429)  
3. **`_get_accounting_cash_expenses_data`** (line 2552-2567)

### Changed From:
```python
if value is None:
    continue  # ❌ Skips the column entirely
```

### Changed To:
```python
# Always include the column, even if None
if isinstance(value, dt_type):
    row[col] = value.isoformat()
elif isinstance(value, Decimal):
    row[col] = float(value)
else:
    row[col] = value  # ✅ Includes None values
```

Also changed exception handling from `continue` to `row[col] = None` to ensure the column is always set.

## Result
Now all bank statement rows will have complete data structures with all columns present, allowing AG Grid to properly display the content in each cell.

## Testing
After deploying this fix:
1. Navigate to the Accounting → Statements tab
2. Bank statements should now display with all fields visible
3. Columns with no data will show as empty cells rather than causing the entire row to be blank

---
**Fixed Date**: 2025-12-07  
**Impact**: Also fixed potential issues in Active Inventory and Cash Expenses grids
