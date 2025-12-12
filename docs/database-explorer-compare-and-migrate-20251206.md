# Database Explorer: Table Compare & Migrate

**Date**: 2025-12-06  
**Status**: In Progress  
**Author**: AI Assistant

---

## 1. Overview

This document describes the **Table Compare & Migrate** feature for the Admin Database Explorer. This feature allows administrators to:

1. **Compare any two tables** across MSSQL and Supabase databases
2. **Analyze schema differences** (columns, types, nullable, defaults)
3. **Analyze data differences** (missing keys, changed rows, ranges)
4. **Safely migrate missing data** from Source → Target with dry-run support

---

## 2. Current Infrastructure Analysis

### 2.1 Frontend Components

| File | Purpose |
|------|---------|
| `frontend/src/pages/AdminDbExplorerPage.tsx` | Main DB Explorer page with table list, schema view, data view, and existing migration console |

### 2.2 Backend - Supabase/Postgres

| File | Purpose |
|------|---------|
| `backend/app/routers/admin_db.py` | Supabase endpoints: `/api/admin/db/tables`, `/api/admin/db/tables/{name}/schema`, `/api/admin/db/tables/{name}/rows` |

**Key Functions:**
- `_get_known_tables()` - Returns tables with row_estimate from pg_class
- `get_table_schema()` - Returns column metadata including PK/FK detection
- `get_table_rows()` - Returns paginated rows with optional column search

### 2.3 Backend - MSSQL

| File | Purpose |
|------|---------|
| `backend/app/routers/admin_mssql.py` | MSSQL endpoints: `/api/admin/mssql/schema-tree`, `/api/admin/mssql/table-columns`, `/api/admin/mssql/table-preview` |
| `backend/app/services/mssql_client.py` | MSSQL connection management and query execution |

**Key Functions:**
- `get_schema_tree()` - Returns database → schemas → tables tree with row_estimate
- `get_table_columns()` - Returns column metadata with PK detection
- `get_table_preview()` - Returns paginated rows

### 2.4 Existing Migration Infrastructure

| File | Purpose |
|------|---------|
| `backend/app/routers/admin_db_migration_console.py` | Advanced migration console with worker management, batch processing, and JSON mapping |

**Key Features Already Implemented:**
- `MigrationCommand` - Full migration configuration with mapping rules
- `_get_pg_columns()` / `_get_mssql_single_pk_column()` - Column/PK detection
- `_pg_column_has_unique_or_pk()` - Constraint detection for ON CONFLICT
- Batch processing with progress logging
- Worker state management in `db_migration_workers` table

---

## 3. TODO Checklist

### 3.1 Analysis (Current Infrastructure) ✅

- [x] Locate frontend Database Explorer component
- [x] Locate backend Supabase endpoints
- [x] Locate backend MSSQL endpoints
- [x] Document existing migration infrastructure

### 3.2 UI: Compare & Migrate Mode ✅

- [x] Add "Compare & Migrate" tab/mode to AdminDbExplorerPage
- [x] Create source/target selection form
  - [x] Source DB dropdown (MSSQL / Supabase)
  - [x] Source table dropdown
  - [x] Target DB dropdown
  - [x] Target table dropdown
  - [x] Key column selection with auto-detection
- [x] Add Compare button and result panels
- [x] Add Schema diff panel
- [x] Add Data diff summary panel
- [x] Add Migration panel with dry-run support

### 3.3 Backend: Schema Comparison ✅

- [x] Create `/api/db-compare/schema` endpoint
- [x] Implement column normalization for cross-DB comparison
- [x] Return: common_columns, missing_in_target, extra_in_target, type_mismatches

### 3.4 Backend: Key Detection ✅

- [x] Create `detect_key_column()` function for both DBs
- [x] Handle composite PK with warning
- [x] Fallback heuristics (id, <table>_id, etc.)

### 3.5 Backend: Data Summary ✅

- [x] Create `/api/db-compare/data-summary` endpoint
- [x] Calculate row counts, min/max keys
- [x] Identify keys_only_in_source, keys_only_in_target, keys_in_both
- [x] Group missing keys into ranges for numeric keys

### 3.6 Backend: Data Details

- [ ] Create `/api/db-compare/data-details` endpoint
- [ ] Compare rows by common columns
- [ ] Return IDENTICAL vs CHANGED status with different_columns

### 3.7 Backend: Migration ✅

- [x] Create `/api/db-compare/migrate` endpoint
- [x] Implement INSERT_MISSING_ONLY mode
- [x] Support dry_run flag
- [x] Batch processing with progress
- [x] ON CONFLICT DO NOTHING for safety

### 3.8 Audit Tables

- [ ] Create `db_compare_audit` table
- [ ] Create `db_compare_migration_log` table
- [ ] Link operations to audit records

### 3.9 Verification

- [ ] Unit tests for schema diff
- [ ] Unit tests for range grouping
- [ ] Unit tests for data comparison
- [ ] Manual testing with real tables

---

## 4. API Design

### 4.1 Schema Comparison

```
POST /api/db-compare/schema
Request:
{
  "source_db": "mssql" | "supabase",
  "source_schema": "dbo",
  "source_table": "tbl_parts_inventory",
  "target_db": "supabase",
  "target_schema": "public",
  "target_table": "inventory"
}

Response:
{
  "source_column_count": 129,
  "target_column_count": 116,
  "source_columns": [...],
  "target_columns": [...],
  "common_columns": ["id", "sku", "title", ...],
  "missing_in_target_columns": ["legacy_field1", ...],
  "extra_in_target_columns": ["created_at", ...],
  "type_mismatch_columns": [
    {"column": "price", "source_type": "money", "target_type": "numeric"}
  ],
  "auto_detected_key": "id"
}
```

### 4.2 Data Summary

```
POST /api/db-compare/data-summary
Request:
{
  "source_db": "mssql",
  "source_schema": "dbo",
  "source_table": "tbl_parts_inventory",
  "target_db": "supabase",
  "target_schema": "public",
  "target_table": "inventory",
  "key_column": "id",
  "key_from": null,
  "key_to": null
}

Response:
{
  "source_row_count": 265354,
  "target_row_count": 264714,
  "source_key_min": 1,
  "source_key_max": 265354,
  "target_key_min": 1,
  "target_key_max": 264714,
  "keys_only_in_source_count": 640,
  "keys_only_in_target_count": 0,
  "keys_in_both_count": 264714,
  "missing_in_target_ranges": [
    {"start": 264715, "end": 265354, "count": 640}
  ],
  "missing_in_source_ranges": []
}
```

### 4.3 Migrate

```
POST /api/db-compare/migrate
Request:
{
  "source_db": "mssql",
  "source_schema": "dbo",
  "source_table": "tbl_parts_inventory",
  "target_db": "supabase",
  "target_schema": "public",
  "target_table": "inventory",
  "key_column": "id",
  "mode": "INSERT_MISSING_ONLY",
  "ranges": [{"start": 264715, "end": 265354}],
  "dry_run": true
}

Response (dry_run=true):
{
  "dry_run": true,
  "planned_inserts_count": 640,
  "columns_to_insert": ["id", "sku", "title", ...],
  "potential_issues": []
}

Response (dry_run=false):
{
  "dry_run": false,
  "inserted_count": 640,
  "skipped_conflicts_count": 0,
  "errors_count": 0,
  "migration_log_id": 123
}
```

---

## 5. Database Schema

### 5.1 db_compare_audit

```sql
CREATE TABLE db_compare_audit (
  id SERIAL PRIMARY KEY,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  user_id UUID REFERENCES auth.users(id),
  
  source_db TEXT NOT NULL,
  source_schema TEXT,
  source_table TEXT NOT NULL,
  target_db TEXT NOT NULL,
  target_schema TEXT,
  target_table TEXT NOT NULL,
  key_column TEXT,
  
  source_row_count INTEGER,
  target_row_count INTEGER,
  keys_only_in_source_count INTEGER,
  keys_only_in_target_count INTEGER,
  keys_in_both_count INTEGER,
  
  schema_diff_json JSONB,
  data_diff_json JSONB,
  
  status TEXT DEFAULT 'SUCCESS',
  error_message TEXT
);
```

### 5.2 db_compare_migration_log

```sql
CREATE TABLE db_compare_migration_log (
  id SERIAL PRIMARY KEY,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  user_id UUID REFERENCES auth.users(id),
  audit_id INTEGER REFERENCES db_compare_audit(id),
  
  mode TEXT NOT NULL,
  dry_run BOOLEAN NOT NULL,
  keys_scope_json JSONB,
  
  planned_inserts_count INTEGER,
  inserted_count INTEGER,
  skipped_conflicts_count INTEGER,
  errors_count INTEGER,
  
  status TEXT DEFAULT 'SUCCESS',
  error_message TEXT
);
```

---

## 6. Security Considerations

1. **Read-only Source**: Source database is never modified
2. **Insert-only Target**: Only INSERT operations, no UPDATE/DELETE
3. **Parameterized Queries**: All SQL uses parameterized queries
4. **Admin-only Access**: All endpoints require admin authentication
5. **Audit Trail**: All operations are logged to audit tables
6. **Dry-run First**: UI encourages dry-run before real migration

---

## 7. Implementation Progress

### Phase 1: Backend Core ✅ COMPLETE

- [x] Create db_compare router (`backend/app/routers/db_compare.py`)
- [x] Implement schema comparison with type normalization
- [x] Implement key detection with heuristics
- [x] Implement data summary with range grouping

### Phase 2: Backend Migration ✅ COMPLETE

- [x] Implement migrate endpoint with INSERT_MISSING_ONLY mode
- [x] Dry-run support
- [x] Batch processing with progress logging
- [ ] Audit tables (pending)

### Phase 3: Frontend UI ✅ COMPLETE

- [x] Add Compare & Migrate mode toggle
- [x] Create TableCompareAndMigrate component (`frontend/src/components/admin/TableCompareAndMigrate.tsx`)
- [x] Source/Target selection with table dropdowns
- [x] Schema diff panel with column stats
- [x] Data diff panel with key ranges
- [x] Migration panel with dry-run and real execution

### Phase 4: Testing & Polish

- [ ] Unit tests
- [ ] Integration tests
- [ ] Manual testing with real tables
- [ ] Documentation updates

---

## 8. Files Created/Modified

### New Files

| File | Purpose |
|------|---------|
| `backend/app/routers/db_compare.py` | New router with schema, data-summary, and migrate endpoints |
| `frontend/src/components/admin/TableCompareAndMigrate.tsx` | React component for Compare & Migrate UI |
| `docs/database-explorer-compare-and-migrate-20251206.md` | This documentation file |

### Modified Files

| File | Changes |
|------|---------|
| `backend/app/routers/__init__.py` | Added db_compare import |
| `backend/app/main.py` | Added db_compare router registration |
| `frontend/src/pages/AdminDbExplorerPage.tsx` | Added pageMode toggle and TableCompareAndMigrate integration |

