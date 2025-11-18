# DB Migration Console

The DB Migration Console is an admin-only tool that lives inside **Admin → DB Explorer**.
It lets you describe complex MSSQL → Supabase migrations as JSON commands, validate them,
and then run them in batches.

> NOTE: The first version supports **MSSQL (legacy) → Supabase/Postgres** only.

---

## Where to find it

1. Open **Admin → DB Explorer**.
2. Use the database switch at the top to browse:
   - **Supabase (Postgres)** tables, or
   - **MSSQL (legacy)** tables.
3. At the bottom of the screen you will see a **Migration Console** panel with:
   - a JSON text box for the command,
   - a **Target mode** selector (`append` or `truncate_and_insert`),
   - buttons **Validate** and **Run migration**, and
   - a log area for validation and run results.

When you click a table in **MSSQL**, the console will pre-fill the `source` section.
When you click a table in **Supabase**, the console will pre-fill the `target` section.

For specific pairs (e.g. `dbo.tbl_ebay_fees` → `public.ebay_finances_fees`), the
console pre-populates a richer example command.

---

## Command format

The console uses JSON with the following shape:

```json
{
  "source": {
    "db": "mssql",
    "database": "DB_A28F26_parts",
    "schema": "dbo",
    "table": "tbl_ebay_fees"
  },
  "target": {
    "db": "supabase",
    "schema": "public",
    "table": "ebay_finances_fees"
  },
  "mode": "append",
  "batch_size": 1000,
  "filter": "",          // optional MSSQL WHERE clause (without the word WHERE)
  "mapping": {
    "target_column": {
      "type": "column" | "expression" | "constant",
      "source": "ColumnName",             // for type=column
      "sql": "SQL_EXPRESSION",           // for type=expression
      "value": "literal or number"       // for type=constant
    }
  },
  "raw_payload": {
    "enabled": true,
    "target_column": "raw_payload"
  }
}
```

**Rules:**

- `source.db` must be `"mssql"` and `target.db` must be `"supabase"`.
- `mode` is either:
  - `"append"` – insert rows into the existing table, or
  - `"truncate_and_insert"` – truncate target table then insert.
- `filter` is appended as `WHERE <filter>` to the MSSQL `SELECT`. It must not
  contain semicolons.
- `mapping` describes how each **target** column is built:
  - `type = "column"` – copy from a single MSSQL column (`source`).
  - `type = "expression"` – MSSQL expression (`sql`) that can reference source columns.
  - `type = "constant"` – literal value applied to all rows.
- If `raw_payload.enabled` is true, all source columns are captured into a JSON
  object and stored in `raw_payload.target_column` on the target table.

If a target column is **non-nullable** and has **no default** in Postgres and is
missing from `mapping`, validation will fail.

---

## Example 1 – Fees: `dbo.tbl_ebay_fees` → `public.ebay_finances_fees`

```json
{
  "source": {
    "db": "mssql",
    "database": "DB_A28F26_parts",
    "schema": "dbo",
    "table": "tbl_ebay_fees"
  },
  "target": {
    "db": "supabase",
    "schema": "public",
    "table": "ebay_finances_fees"
  },
  "mode": "append",
  "batch_size": 1000,
  "mapping": {
    "ebay_account_id": { "type": "column", "source": "EbayID" },
    "transaction_id": {
      "type": "expression",
      "sql": "COALESCE(TransactionID, OrderLineItemID, RefNumber)"
    },
    "fee_type": { "type": "column", "source": "AccountDetailsEntryType" },
    "amount_value": {
      "type": "expression",
      "sql": "COALESCE(NetDetailAmount, GrossDetailAmount)"
    },
    "amount_currency": {
      "type": "constant",
      "value": "USD"
    },
    "created_at": {
      "type": "expression",
      "sql": "COALESCE([Date], record_created)"
    },
    "updated_at": {
      "type": "expression",
      "sql": "COALESCE(record_updated, [Date], record_created)"
    }
  },
  "raw_payload": {
    "enabled": true,
    "target_column": "raw_payload"
  }
}
```

- **Validate** shows an estimated row count and ensures that all required columns
  in `public.ebay_finances_fees` are mapped.
- **Run migration** inserts rows in batches of 1000.

---

## Example 2 – Simple table copy (append)

Copy all columns from an MSSQL table into a structurally identical Supabase
 table:

```json
{
  "source": {
    "db": "mssql",
    "database": "DB_A28F26_parts",
    "schema": "dbo",
    "table": "tbl_simple_source"
  },
  "target": {
    "db": "supabase",
    "schema": "public",
    "table": "tbl_simple_target"
  },
  "mode": "append",
  "batch_size": 2000,
  "mapping": {
    "id": { "type": "column", "source": "ID" },
    "name": { "type": "column", "source": "Name" },
    "created_at": { "type": "column", "source": "CreatedAt" }
  },
  "raw_payload": {
    "enabled": false
  }
}
```

This treats the target table as append-only and does not store the raw payload.

---

## Example 3 – Truncate and insert with raw payload

```json
{
  "source": {
    "db": "mssql",
    "database": "DB_A28F26_parts",
    "schema": "dbo",
    "table": "tbl_workers"
  },
  "target": {
    "db": "supabase",
    "schema": "public",
    "table": "workers"
  },
  "mode": "truncate_and_insert",
  "batch_size": 1000,
  "filter": "IsActive = 1",
  "mapping": {
    "worker_id": { "type": "column", "source": "WorkerId" },
    "full_name": { "type": "expression", "sql": "WorkerFirstName + ' ' + WorkerLastName" },
    "created_at": { "type": "column", "source": "CreatedAt" }
  },
  "raw_payload": {
    "enabled": true,
    "target_column": "raw_payload"
  }
}
```

This command:

- truncates `public.workers` before inserting,
- only migrates active workers (`IsActive = 1`), and
- preserves all original MSSQL columns as JSON in `workers.raw_payload`.

---

## Workflow summary

1. Use DB Explorer to inspect MSSQL and Supabase tables.
2. Compose or adjust a JSON command in the Migration Console.
3. Click **Validate** to check schemas and estimate row counts.
4. If validation passes, click **Run migration** to copy data in batches.
5. Review the log area for per-run issues and the final summary.
