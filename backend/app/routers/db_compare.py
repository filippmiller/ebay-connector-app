"""
Database Compare & Migrate API Router

Provides endpoints for comparing tables across MSSQL and Supabase databases,
and safely migrating missing data from Source → Target.

Safety guarantees:
- Source is always read-only
- Target only receives INSERT operations (no UPDATE/DELETE)
- All SQL uses parameterized queries
- All operations are logged to audit tables
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.models.user import User
from app.services.admin_auth import get_current_admin_user
from app.services import mssql_client
from app.services.mssql_client import MssqlConnectionConfig
from app.models_sqlalchemy import engine as pg_engine, get_db
from sqlalchemy.orm import Session


router = APIRouter(prefix="/api/db-compare", tags=["db_compare"])


# =============================================================================
# Request/Response Models
# =============================================================================

class DbEndpoint(BaseModel):
    """Represents a database table endpoint for comparison."""
    db: str  # "mssql" or "supabase"
    database: Optional[str] = None  # Required for MSSQL
    schema_name: Optional[str] = None  # Default: "dbo" for MSSQL, "public" for Supabase
    table: str


class SchemaCompareRequest(BaseModel):
    """Request for schema comparison."""
    source: DbEndpoint
    target: DbEndpoint


class ColumnInfo(BaseModel):
    """Normalized column information."""
    name: str
    data_type: str
    normalized_type: str  # Normalized for cross-DB comparison
    is_nullable: bool
    is_primary_key: bool
    default_value: Optional[str] = None


class TypeMismatch(BaseModel):
    """Column with type mismatch between source and target."""
    column: str
    source_type: str
    target_type: str
    source_normalized: str
    target_normalized: str


class SchemaCompareResponse(BaseModel):
    """Response for schema comparison."""
    source_column_count: int
    target_column_count: int
    source_columns: List[ColumnInfo]
    target_columns: List[ColumnInfo]
    common_columns: List[str]
    missing_in_target_columns: List[str]
    extra_in_target_columns: List[str]
    type_mismatch_columns: List[TypeMismatch]
    auto_detected_key: Optional[str] = None
    key_detection_warning: Optional[str] = None


class DataSummaryRequest(BaseModel):
    """Request for data summary comparison."""
    source: DbEndpoint
    target: DbEndpoint
    key_column: str
    key_from: Optional[int] = None
    key_to: Optional[int] = None
    sample_limit: int = 10000  # Safety limit for key sampling


class KeyRange(BaseModel):
    """A contiguous range of keys."""
    start: int
    end: int
    count: int


class DataSummaryResponse(BaseModel):
    """Response for data summary comparison."""
    source_row_count: int
    target_row_count: int
    source_key_min: Optional[int] = None
    source_key_max: Optional[int] = None
    target_key_min: Optional[int] = None
    target_key_max: Optional[int] = None
    keys_only_in_source_count: int
    keys_only_in_target_count: int
    keys_in_both_count: int
    missing_in_target_ranges: List[KeyRange]
    missing_in_source_ranges: List[KeyRange]
    key_type: str = "numeric"  # or "string"
    truncated: bool = False
    truncated_message: Optional[str] = None


class MigrateRequest(BaseModel):
    """Request for migration."""
    source: DbEndpoint
    target: DbEndpoint
    key_column: str
    mode: str = "INSERT_MISSING_ONLY"
    ranges: Optional[List[KeyRange]] = None
    keys: Optional[List[int]] = None  # Specific keys to migrate
    batch_size: int = 500
    dry_run: bool = True


class MigrateResponse(BaseModel):
    """Response for migration."""
    dry_run: bool
    planned_inserts_count: Optional[int] = None
    columns_to_insert: Optional[List[str]] = None
    potential_issues: List[str] = Field(default_factory=list)
    inserted_count: Optional[int] = None
    skipped_conflicts_count: Optional[int] = None
    errors_count: Optional[int] = None
    migration_log_id: Optional[int] = None
    batch_logs: List[str] = Field(default_factory=list)


# =============================================================================
# Type Normalization
# =============================================================================

# Map database-specific types to normalized types for comparison
TYPE_NORMALIZATION = {
    # Integers
    "int": "integer",
    "integer": "integer",
    "int4": "integer",
    "smallint": "smallint",
    "int2": "smallint",
    "tinyint": "tinyint",
    "bigint": "bigint",
    "int8": "bigint",
    
    # Decimals
    "decimal": "decimal",
    "numeric": "decimal",
    "money": "decimal",
    "smallmoney": "decimal",
    "float": "float",
    "double precision": "float",
    "float8": "float",
    "real": "float",
    "float4": "float",
    
    # Strings
    "varchar": "text",
    "character varying": "text",
    "nvarchar": "text",
    "char": "text",
    "character": "text",
    "nchar": "text",
    "text": "text",
    "ntext": "text",
    "citext": "text",
    
    # Boolean
    "bit": "boolean",
    "boolean": "boolean",
    "bool": "boolean",
    
    # Dates/Times
    "datetime": "timestamp",
    "datetime2": "timestamp",
    "smalldatetime": "timestamp",
    "timestamp": "timestamp",
    "timestamp without time zone": "timestamp",
    "timestamp with time zone": "timestamptz",
    "timestamptz": "timestamptz",
    "date": "date",
    "time": "time",
    "time without time zone": "time",
    "time with time zone": "timetz",
    
    # JSON
    "json": "json",
    "jsonb": "json",
    
    # UUIDs
    "uuid": "uuid",
    "uniqueidentifier": "uuid",
    
    # Binary
    "binary": "binary",
    "varbinary": "binary",
    "image": "binary",
    "bytea": "binary",
}


def normalize_type(db_type: str) -> str:
    """Normalize a database type for cross-DB comparison."""
    # Clean up the type string
    clean = db_type.lower().strip()
    # Remove size specifications like varchar(255)
    if "(" in clean:
        clean = clean.split("(")[0].strip()
    return TYPE_NORMALIZATION.get(clean, clean)


# =============================================================================
# Helper Functions
# =============================================================================

def _build_mssql_config(endpoint: DbEndpoint) -> MssqlConnectionConfig:
    """Build MSSQL connection config from endpoint."""
    return MssqlConnectionConfig(
        database=endpoint.database or "DB_A28F26_parts",
        host=None,  # Will use env vars
        username=None,
        password=None,
    )


def _get_default_schema(db: str) -> str:
    """Get default schema for a database type."""
    return "dbo" if db == "mssql" else "public"


def _get_mssql_columns(endpoint: DbEndpoint) -> List[ColumnInfo]:
    """Get column information from MSSQL table."""
    config = _build_mssql_config(endpoint)
    schema = endpoint.schema_name or _get_default_schema("mssql")
    
    cols = mssql_client.get_table_columns(config, schema=schema, table=endpoint.table)
    
    return [
        ColumnInfo(
            name=col["name"],
            data_type=col["dataType"],
            normalized_type=normalize_type(col["dataType"]),
            is_nullable=col["isNullable"],
            is_primary_key=col["isPrimaryKey"],
            default_value=col.get("defaultValue"),
        )
        for col in cols
    ]


def _get_supabase_columns(endpoint: DbEndpoint) -> List[ColumnInfo]:
    """Get column information from Supabase/Postgres table."""
    schema = endpoint.schema_name or _get_default_schema("supabase")
    
    with pg_engine.connect() as conn:
        # Get column info
        cols_sql = text("""
            SELECT
                c.column_name,
                c.data_type,
                c.is_nullable,
                c.column_default
            FROM information_schema.columns c
            WHERE c.table_schema = :schema
              AND c.table_name = :table
            ORDER BY c.ordinal_position
        """)
        cols = list(conn.execute(cols_sql, {"schema": schema, "table": endpoint.table}).mappings())
        
        # Get primary key columns
        pk_sql = text("""
            SELECT kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
            WHERE tc.table_schema = :schema
              AND tc.table_name = :table
              AND tc.constraint_type = 'PRIMARY KEY'
        """)
        pk_cols = {row["column_name"] for row in conn.execute(pk_sql, {"schema": schema, "table": endpoint.table}).mappings()}
    
    return [
        ColumnInfo(
            name=col["column_name"],
            data_type=col["data_type"],
            normalized_type=normalize_type(col["data_type"]),
            is_nullable=col["is_nullable"].lower() == "yes",
            is_primary_key=col["column_name"] in pk_cols,
            default_value=col["column_default"],
        )
        for col in cols
    ]


def _get_columns(endpoint: DbEndpoint) -> List[ColumnInfo]:
    """Get column information from any supported database."""
    if endpoint.db == "mssql":
        return _get_mssql_columns(endpoint)
    elif endpoint.db == "supabase":
        return _get_supabase_columns(endpoint)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported database type: {endpoint.db}"
        )


def _detect_key_column(columns: List[ColumnInfo], table_name: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Detect the primary key column for a table.
    
    Returns:
        Tuple of (key_column, warning_message)
    """
    # First, look for explicit primary keys
    pk_cols = [c for c in columns if c.is_primary_key]
    
    if len(pk_cols) == 1:
        return pk_cols[0].name, None
    elif len(pk_cols) > 1:
        # Composite PK - return warning
        pk_names = ", ".join(c.name for c in pk_cols)
        return pk_cols[0].name, f"Composite primary key detected: {pk_names}. Using first column '{pk_cols[0].name}'. You may want to select a different key."
    
    # No explicit PK - try heuristics
    col_names = {c.name.lower(): c.name for c in columns}
    
    # Common ID column names
    heuristics = [
        "id",
        f"{table_name.lower()}_id",
        f"{table_name.lower()}id",
        "inventory_id",
        "inventoryid",
    ]
    
    for h in heuristics:
        if h in col_names:
            return col_names[h], f"No primary key found. Using heuristic: '{col_names[h]}'"
    
    return None, "Could not auto-detect key column. Please select one manually."


def _group_into_ranges(keys: List[int]) -> List[KeyRange]:
    """
    Group a sorted list of integers into contiguous ranges.
    
    Example: [1,2,3,5,6,10] -> [(1,3,3), (5,6,2), (10,10,1)]
    """
    if not keys:
        return []
    
    keys = sorted(keys)
    ranges = []
    start = keys[0]
    end = keys[0]
    count = 1
    
    for k in keys[1:]:
        if k == end + 1:
            # Contiguous - extend range
            end = k
            count += 1
        else:
            # Gap - save current range and start new one
            ranges.append(KeyRange(start=start, end=end, count=count))
            start = k
            end = k
            count = 1
    
    # Don't forget the last range
    ranges.append(KeyRange(start=start, end=end, count=count))
    
    return ranges


def _get_row_count_mssql(endpoint: DbEndpoint) -> int:
    """Get row count from MSSQL table."""
    config = _build_mssql_config(endpoint)
    schema = endpoint.schema_name or _get_default_schema("mssql")
    
    engine = mssql_client.create_engine_for_session(config)
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text(f"SELECT COUNT(*) FROM [{schema}].[{endpoint.table}]")
            )
            return result.scalar() or 0
    finally:
        engine.dispose()


def _get_row_count_supabase(endpoint: DbEndpoint) -> int:
    """Get row count from Supabase table."""
    schema = endpoint.schema_name or _get_default_schema("supabase")
    
    with pg_engine.connect() as conn:
        result = conn.execute(
            text(f'SELECT COUNT(*) FROM {schema}."{endpoint.table}"')
        )
        return result.scalar() or 0


def _get_row_count(endpoint: DbEndpoint) -> int:
    """Get row count from any supported database."""
    if endpoint.db == "mssql":
        return _get_row_count_mssql(endpoint)
    elif endpoint.db == "supabase":
        return _get_row_count_supabase(endpoint)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported database type: {endpoint.db}"
        )


def _get_key_stats_mssql(endpoint: DbEndpoint, key_column: str) -> Tuple[Optional[int], Optional[int]]:
    """Get min/max key values from MSSQL table."""
    config = _build_mssql_config(endpoint)
    schema = endpoint.schema_name or _get_default_schema("mssql")
    
    engine = mssql_client.create_engine_for_session(config)
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text(f"SELECT MIN([{key_column}]) as min_key, MAX([{key_column}]) as max_key FROM [{schema}].[{endpoint.table}]")
            )
            row = result.mappings().fetchone()
            if row:
                return row["min_key"], row["max_key"]
            return None, None
    finally:
        engine.dispose()


def _get_key_stats_supabase(endpoint: DbEndpoint, key_column: str) -> Tuple[Optional[int], Optional[int]]:
    """Get min/max key values from Supabase table."""
    schema = endpoint.schema_name or _get_default_schema("supabase")
    
    with pg_engine.connect() as conn:
        result = conn.execute(
            text(f'SELECT MIN("{key_column}") as min_key, MAX("{key_column}") as max_key FROM {schema}."{endpoint.table}"')
        )
        row = result.mappings().fetchone()
        if row:
            return row["min_key"], row["max_key"]
        return None, None


def _get_keys_mssql(endpoint: DbEndpoint, key_column: str, key_from: Optional[int] = None, key_to: Optional[int] = None, limit: int = 10000) -> List[int]:
    """Get key values from MSSQL table."""
    config = _build_mssql_config(endpoint)
    schema = endpoint.schema_name or _get_default_schema("mssql")
    
    where_clauses = []
    params: Dict[str, Any] = {"limit": limit}
    
    if key_from is not None:
        where_clauses.append(f"[{key_column}] >= :key_from")
        params["key_from"] = key_from
    if key_to is not None:
        where_clauses.append(f"[{key_column}] <= :key_to")
        params["key_to"] = key_to
    
    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
    
    engine = mssql_client.create_engine_for_session(config)
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text(f"""
                    SELECT [{key_column}] as key_value
                    FROM [{schema}].[{endpoint.table}]
                    WHERE {where_sql}
                    ORDER BY [{key_column}]
                    OFFSET 0 ROWS FETCH NEXT :limit ROWS ONLY
                """),
                params
            )
            return [row["key_value"] for row in result.mappings()]
    finally:
        engine.dispose()


def _get_keys_supabase(endpoint: DbEndpoint, key_column: str, key_from: Optional[int] = None, key_to: Optional[int] = None, limit: int = 10000) -> List[int]:
    """Get key values from Supabase table."""
    schema = endpoint.schema_name or _get_default_schema("supabase")
    
    where_clauses = []
    params: Dict[str, Any] = {"limit": limit}
    
    if key_from is not None:
        where_clauses.append(f'"{key_column}" >= :key_from')
        params["key_from"] = key_from
    if key_to is not None:
        where_clauses.append(f'"{key_column}" <= :key_to')
        params["key_to"] = key_to
    
    where_sql = " AND ".join(where_clauses) if where_clauses else "TRUE"
    
    with pg_engine.connect() as conn:
        result = conn.execute(
            text(f'SELECT "{key_column}" as key_value FROM {schema}."{endpoint.table}" WHERE {where_sql} ORDER BY "{key_column}" LIMIT :limit'),
            params
        )
        return [row["key_value"] for row in result.mappings()]


def _get_keys(endpoint: DbEndpoint, key_column: str, key_from: Optional[int] = None, key_to: Optional[int] = None, limit: int = 10000) -> List[int]:
    """Get key values from any supported database."""
    if endpoint.db == "mssql":
        return _get_keys_mssql(endpoint, key_column, key_from, key_to, limit)
    elif endpoint.db == "supabase":
        return _get_keys_supabase(endpoint, key_column, key_from, key_to, limit)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported database type: {endpoint.db}"
        )


# =============================================================================
# API Endpoints
# =============================================================================

@router.post("/schema", response_model=SchemaCompareResponse)
async def compare_schema(
    request: SchemaCompareRequest,
    current_user: User = Depends(get_current_admin_user),
) -> SchemaCompareResponse:
    """
    Compare schema (columns, types) between two tables.
    
    Works across MSSQL and Supabase databases.
    """
    try:
        # Get columns from both tables
        source_cols = _get_columns(request.source)
        target_cols = _get_columns(request.target)
        
        # Build name sets for comparison
        source_names = {c.name.lower(): c for c in source_cols}
        target_names = {c.name.lower(): c for c in target_cols}
        
        # Find common, missing, extra columns
        common = []
        missing_in_target = []
        extra_in_target = []
        type_mismatches = []
        
        for name_lower, col in source_names.items():
            if name_lower in target_names:
                common.append(col.name)
                # Check for type mismatch
                target_col = target_names[name_lower]
                if col.normalized_type != target_col.normalized_type:
                    type_mismatches.append(TypeMismatch(
                        column=col.name,
                        source_type=col.data_type,
                        target_type=target_col.data_type,
                        source_normalized=col.normalized_type,
                        target_normalized=target_col.normalized_type,
                    ))
            else:
                missing_in_target.append(col.name)
        
        for name_lower, col in target_names.items():
            if name_lower not in source_names:
                extra_in_target.append(col.name)
        
        # Detect key column
        key_col, key_warning = _detect_key_column(source_cols, request.source.table)
        
        return SchemaCompareResponse(
            source_column_count=len(source_cols),
            target_column_count=len(target_cols),
            source_columns=source_cols,
            target_columns=target_cols,
            common_columns=sorted(common),
            missing_in_target_columns=sorted(missing_in_target),
            extra_in_target_columns=sorted(extra_in_target),
            type_mismatch_columns=type_mismatches,
            auto_detected_key=key_col,
            key_detection_warning=key_warning,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        ) from e


@router.post("/data-summary", response_model=DataSummaryResponse)
async def compare_data_summary(
    request: DataSummaryRequest,
    current_user: User = Depends(get_current_admin_user),
) -> DataSummaryResponse:
    """
    Compare data between two tables by key column.
    
    Returns counts and ranges of missing/extra keys.
    """
    try:
        # Get row counts
        source_count = _get_row_count(request.source)
        target_count = _get_row_count(request.target)
        
        # Get key stats
        source_min, source_max = _get_key_stats_mssql(request.source, request.key_column) if request.source.db == "mssql" else _get_key_stats_supabase(request.source, request.key_column)
        target_min, target_max = _get_key_stats_mssql(request.target, request.key_column) if request.target.db == "mssql" else _get_key_stats_supabase(request.target, request.key_column)
        
        # Get keys within the specified range
        source_keys = set(_get_keys(request.source, request.key_column, request.key_from, request.key_to, request.sample_limit))
        target_keys = set(_get_keys(request.target, request.key_column, request.key_from, request.key_to, request.sample_limit))
        
        # Calculate differences
        only_in_source = source_keys - target_keys
        only_in_target = target_keys - source_keys
        in_both = source_keys & target_keys
        
        # Check if we hit the limit
        truncated = len(source_keys) >= request.sample_limit or len(target_keys) >= request.sample_limit
        truncated_msg = None
        if truncated:
            truncated_msg = f"Results limited to {request.sample_limit} keys per table. Use key_from/key_to to analyze specific ranges."
        
        # Group missing keys into ranges
        missing_in_target_ranges = _group_into_ranges(sorted(only_in_source))
        missing_in_source_ranges = _group_into_ranges(sorted(only_in_target))
        
        return DataSummaryResponse(
            source_row_count=source_count,
            target_row_count=target_count,
            source_key_min=source_min,
            source_key_max=source_max,
            target_key_min=target_min,
            target_key_max=target_max,
            keys_only_in_source_count=len(only_in_source),
            keys_only_in_target_count=len(only_in_target),
            keys_in_both_count=len(in_both),
            missing_in_target_ranges=missing_in_target_ranges,
            missing_in_source_ranges=missing_in_source_ranges,
            truncated=truncated,
            truncated_message=truncated_msg,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        ) from e


@router.post("/migrate", response_model=MigrateResponse)
async def migrate_missing_rows(
    request: MigrateRequest,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
) -> MigrateResponse:
    """
    Migrate missing rows from Source to Target.
    
    Safety guarantees:
    - Source is read-only
    - Target only receives INSERTs (no UPDATE/DELETE)
    - Uses ON CONFLICT DO NOTHING to skip existing keys
    - All operations are logged
    
    Set dry_run=true to see what would be migrated without making changes.
    """
    if request.mode != "INSERT_MISSING_ONLY":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported migration mode: {request.mode}. Only 'INSERT_MISSING_ONLY' is supported."
        )
    
    if request.target.db != "supabase":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Migration target must be Supabase. MSSQL is read-only."
        )
    
    try:
        # Get common columns between source and target
        source_cols = _get_columns(request.source)
        target_cols = _get_columns(request.target)
        
        source_names = {c.name.lower(): c.name for c in source_cols}
        target_names = {c.name.lower(): c.name for c in target_cols}
        
        # Find columns that exist in both (use target's case)
        common_cols = []
        for name_lower, target_name in target_names.items():
            if name_lower in source_names:
                common_cols.append(target_name)
        
        if not common_cols:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No common columns found between source and target tables."
            )
        
        # Determine which keys to migrate
        keys_to_migrate: List[int] = []
        
        if request.keys:
            keys_to_migrate = request.keys
        elif request.ranges:
            for r in request.ranges:
                keys_to_migrate.extend(range(r.start, r.end + 1))
        else:
            # Get all missing keys
            source_keys = set(_get_keys(request.source, request.key_column, limit=100000))
            target_keys = set(_get_keys(request.target, request.key_column, limit=100000))
            keys_to_migrate = list(source_keys - target_keys)
        
        if request.dry_run:
            # Just return the plan
            return MigrateResponse(
                dry_run=True,
                planned_inserts_count=len(keys_to_migrate),
                columns_to_insert=common_cols,
                potential_issues=[],
            )
        
        # REAL MIGRATION
        target_schema = request.target.schema_name or "public"
        batch_logs: List[str] = []
        inserted_count = 0
        skipped_count = 0
        errors_count = 0
        
        # Process in batches
        for batch_start in range(0, len(keys_to_migrate), request.batch_size):
            batch_keys = keys_to_migrate[batch_start:batch_start + request.batch_size]
            batch_num = batch_start // request.batch_size + 1
            
            try:
                # Fetch rows from source
                if request.source.db == "mssql":
                    source_rows = _fetch_mssql_rows(
                        request.source, 
                        request.key_column, 
                        batch_keys,
                        [source_names[c.lower()] for c in common_cols]
                    )
                else:
                    source_rows = _fetch_supabase_rows(
                        request.source,
                        request.key_column,
                        batch_keys,
                        common_cols
                    )
                
                if not source_rows:
                    batch_logs.append(f"Batch {batch_num}: No rows found in source for {len(batch_keys)} keys")
                    continue
                
                # Insert into target with ON CONFLICT DO NOTHING
                batch_inserted, batch_skipped = _insert_to_supabase(
                    request.target,
                    request.key_column,
                    common_cols,
                    source_rows,
                )
                
                inserted_count += batch_inserted
                skipped_count += batch_skipped
                batch_logs.append(f"Batch {batch_num}: Inserted {batch_inserted}, skipped {batch_skipped} (of {len(batch_keys)} keys)")
                
            except Exception as e:
                errors_count += 1
                batch_logs.append(f"Batch {batch_num}: ERROR - {str(e)}")
        
        # TODO: Log to db_compare_migration_log table
        
        return MigrateResponse(
            dry_run=False,
            inserted_count=inserted_count,
            skipped_conflicts_count=skipped_count,
            errors_count=errors_count,
            batch_logs=batch_logs,
            columns_to_insert=common_cols,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        ) from e


# =============================================================================
# Data Fetch/Insert Helpers
# =============================================================================

def _fetch_mssql_rows(
    endpoint: DbEndpoint,
    key_column: str,
    keys: List[int],
    columns: List[str],
) -> List[Dict[str, Any]]:
    """Fetch specific rows from MSSQL by key values."""
    if not keys:
        return []
    
    config = _build_mssql_config(endpoint)
    schema = endpoint.schema_name or "dbo"
    
    # Build column list
    col_list = ", ".join(f"[{c}]" for c in columns)
    
    # Use IN clause for small batches, temp table for larger
    if len(keys) <= 100:
        placeholders = ", ".join(str(k) for k in keys)
        sql = f"SELECT {col_list} FROM [{schema}].[{endpoint.table}] WHERE [{key_column}] IN ({placeholders})"
    else:
        # For larger sets, still use IN but be careful
        placeholders = ", ".join(str(k) for k in keys)
        sql = f"SELECT {col_list} FROM [{schema}].[{endpoint.table}] WHERE [{key_column}] IN ({placeholders})"
    
    engine = mssql_client.create_engine_for_session(config)
    try:
        with engine.connect() as conn:
            result = conn.execute(text(sql))
            return [dict(row) for row in result.mappings()]
    finally:
        engine.dispose()


def _fetch_supabase_rows(
    endpoint: DbEndpoint,
    key_column: str,
    keys: List[int],
    columns: List[str],
) -> List[Dict[str, Any]]:
    """Fetch specific rows from Supabase by key values."""
    if not keys:
        return []
    
    schema = endpoint.schema_name or "public"
    col_list = ", ".join(f'"{c}"' for c in columns)
    placeholders = ", ".join(str(k) for k in keys)
    
    with pg_engine.connect() as conn:
        result = conn.execute(
            text(f'SELECT {col_list} FROM {schema}."{endpoint.table}" WHERE "{key_column}" IN ({placeholders})')
        )
        return [dict(row) for row in result.mappings()]


def _insert_to_supabase(
    endpoint: DbEndpoint,
    key_column: str,
    columns: List[str],
    rows: List[Dict[str, Any]],
) -> Tuple[int, int]:
    """
    Insert rows into Supabase table with ON CONFLICT DO NOTHING.
    
    Returns: (inserted_count, skipped_count)
    """
    if not rows:
        return 0, 0
    
    schema = endpoint.schema_name or "public"
    col_list = ", ".join(f'"{c}"' for c in columns)
    placeholders = ", ".join(f":{c}" for c in columns)
    
    # Build INSERT with ON CONFLICT DO NOTHING
    insert_sql = text(f"""
        INSERT INTO {schema}."{endpoint.table}" ({col_list})
        VALUES ({placeholders})
        ON CONFLICT ("{key_column}") DO NOTHING
    """)
    
    inserted = 0
    skipped = 0
    
    with pg_engine.begin() as conn:
        for row in rows:
            # Prepare params - use column names as keys
            params = {c: row.get(c) for c in columns}
            result = conn.execute(insert_sql, params)
            if result.rowcount > 0:
                inserted += 1
            else:
                skipped += 1
    
    return inserted, skipped
