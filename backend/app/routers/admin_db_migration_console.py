from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.models.user import User
from app.services.admin_auth import get_current_admin_user
from app.services import mssql_client
from app.services.mssql_client import MssqlConnectionConfig, create_engine_for_session
from app.models_sqlalchemy import engine as pg_engine


router = APIRouter(prefix="/api/admin/db-migration", tags=["admin_db_migration_console"])


class MigrationEndpoint(BaseModel):
    db: str
    database: Optional[str] = None
    schema: Optional[str] = None
    table: str


class MappingRule(BaseModel):
    type: str
    source: Optional[str] = None
    sql: Optional[str] = None
    value: Optional[Any] = None


class RawPayloadConfig(BaseModel):
    enabled: bool = False
    target_column: str = "raw_payload"


class MigrationCommand(BaseModel):
    source: MigrationEndpoint
    target: MigrationEndpoint
    mode: str = "append"  # append | truncate_and_insert
    filter: Optional[str] = None
    batch_size: int = 1000
    mapping: Dict[str, MappingRule]
    raw_payload: Optional[RawPayloadConfig] = None
    dry_run: bool = False


class MigrationValidationResult(BaseModel):
    ok: bool
    issues: List[str] = Field(default_factory=list)
    estimated_rows: Optional[int] = None
    source: Dict[str, Any]
    target: Dict[str, Any]
    missing_target_columns: List[str] = Field(default_factory=list)


class MigrationRunResult(MigrationValidationResult):
    rows_inserted: int = 0
    batches: int = 0


SUPPORTED_SOURCE_DBS = {"mssql"}
SUPPORTED_TARGET_DBS = {"supabase"}


def _normalize_endpoint(ep: MigrationEndpoint, *, default_db: Optional[str] = None) -> MigrationEndpoint:
    table = ep.table
    schema = ep.schema
    if ep.db == "mssql":
        if "." in table and schema is None:
            schema, table = table.split(".", 1)
        if schema is None:
            schema = "dbo"
    else:
        if schema is None:
            schema = "public"
    database = ep.database or default_db
    return MigrationEndpoint(db=ep.db, database=database, schema=schema, table=table)


def _get_pg_columns(schema: str, table: str) -> List[Dict[str, Any]]:
    sql = text(
        """
        SELECT column_name, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema = :schema AND table_name = :table
        ORDER BY ordinal_position
        """
    )
    with pg_engine.connect() as conn:
        rows = conn.execute(sql, {"schema": schema, "table": table}).mappings().all()
    return [
        {
            "name": r["column_name"],
            "is_nullable": str(r["is_nullable"]).lower() == "yes",
            "has_default": r["column_default"] is not None,
        }
        for r in rows
    ]


def _validate_command(cmd: MigrationCommand) -> MigrationValidationResult:
    issues: List[str] = []

    source = _normalize_endpoint(cmd.source)
    target = _normalize_endpoint(cmd.target)

    if source.db not in SUPPORTED_SOURCE_DBS or target.db not in SUPPORTED_TARGET_DBS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Currently only migrations from MSSQL to Supabase/Postgres are supported.",
        )

    # Basic safety checks on filter and expressions
    if cmd.filter and ";" in cmd.filter:
        issues.append("Filter must not contain semicolons.")

    for tgt_col, rule in cmd.mapping.items():
        if rule.type not in {"column", "expression", "constant"}:
            issues.append(f"Unsupported mapping rule type for column {tgt_col!r}: {rule.type!r}.")
        if rule.type == "expression" and rule.sql and ";" in rule.sql:
            issues.append(f"Expression for {tgt_col} contains a semicolon, which is not allowed.")

    # Fetch target columns and ensure non-null, no-default columns are mapped
    pg_columns = _get_pg_columns(target.schema or "public", target.table)
    if not pg_columns:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Target table {target.schema}.{target.table} does not exist in Supabase.",
        )

    mapping_keys = set(cmd.mapping.keys())
    raw_col = None
    if cmd.raw_payload and cmd.raw_payload.enabled:
        raw_col = cmd.raw_payload.target_column or "raw_payload"

    missing_required: List[str] = []
    for col in pg_columns:
        name = col["name"]
        if name == raw_col:
            continue
        if name in mapping_keys:
            continue
        if not col["is_nullable"] and not col["has_default"]:
            missing_required.append(name)

    if missing_required:
        issues.append(
            "Target table is missing mapping rules for non-nullable columns without defaults: "
            + ", ".join(sorted(missing_required))
        )

    # Estimate row count on MSSQL source
    estimated_rows: Optional[int] = None
    mssql_cfg = MssqlConnectionConfig(
        host=None,
        port=1433,
        database=source.database or "",
        username=None,
        password=None,
        encrypt=True,
    )
    mssql_engine: Engine = create_engine_for_session(mssql_cfg)
    try:
        with mssql_engine.connect() as conn:
            where = ""
            if cmd.filter:
                where = f" WHERE {cmd.filter}"
            count_sql = text(
                f"SELECT COUNT(*) FROM [{source.schema}].[{source.table}]" + where
            )
            estimated_rows = int(conn.execute(count_sql).scalar() or 0)
    finally:
        mssql_engine.dispose()

    ok = not issues
    return MigrationValidationResult(
        ok=ok,
        issues=issues,
        estimated_rows=estimated_rows,
        source={"db": source.db, "schema": source.schema, "table": source.table},
        target={"db": target.db, "schema": target.schema, "table": target.table},
        missing_target_columns=missing_required,
    )


@router.post("/validate", response_model=MigrationValidationResult)
async def validate_migration_command(
    cmd: MigrationCommand,
    current_user: User = Depends(get_current_admin_user),
) -> MigrationValidationResult:
    """Validate a migration command and return estimated row counts and issues."""

    result = _validate_command(cmd)
    return result


@router.post("/run", response_model=MigrationRunResult)
async def run_migration_command(
    cmd: MigrationCommand,
    current_user: User = Depends(get_current_admin_user),
) -> MigrationRunResult:
    """Run a MSSQL → Supabase migration based on the provided command.

    This implementation is intentionally conservative and focuses on safety:
    - Only supports source.db == 'mssql' and target.db == 'supabase'.
    - Expressions are injected into the MSSQL SELECT but not into Postgres DDL.
    - Each batch is inserted in its own transaction on Postgres.
    """

    validation = _validate_command(cmd)
    if not validation.ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Validation failed; see issues for details.",
        )

    source = _normalize_endpoint(cmd.source)
    target = _normalize_endpoint(cmd.target)

    # Prepare MSSQL connection
    mssql_cfg = MssqlConnectionConfig(
        host=None,
        port=1433,
        database=source.database or "",
        username=None,
        password=None,
        encrypt=True,
    )
    mssql_engine: Engine = create_engine_for_session(mssql_cfg)

    # Discover MSSQL columns for raw_payload
    mssql_columns = mssql_client.get_table_columns(
        mssql_cfg,
        schema=source.schema or "dbo",
        table=source.table,
    )
    source_column_names = [c["name"] for c in mssql_columns]

    # Build MSSQL SELECT statement
    select_parts: List[str] = []
    for col in source_column_names:
        select_parts.append(f"[{source.schema}].[{source.table}].[{col}]")

    expr_columns: List[str] = []
    for target_col, rule in cmd.mapping.items():
        if rule.type == "expression" and rule.sql:
            expr_columns.append(target_col)
            select_parts.append(f"({rule.sql}) AS [{target_col}]")

    where = ""
    if cmd.filter:
        where = f" WHERE {cmd.filter}"

    select_sql = text(
        "SELECT "
        + ", ".join(select_parts)
        + f" FROM [{source.schema}].[{source.table}]"
        + where
        + " ORDER BY 1 OFFSET :offset ROWS FETCH NEXT :limit ROWS ONLY"
    )

    # Prepare Postgres INSERT
    target_schema = target.schema or "public"
    insert_columns = list(cmd.mapping.keys())
    raw_cfg = cmd.raw_payload or RawPayloadConfig(enabled=False)
    raw_col = raw_cfg.target_column if raw_cfg.enabled else None
    if raw_col:
        insert_columns.append(raw_col)

    col_list_sql = ", ".join(f'"{c}"' for c in insert_columns)
    values_placeholders = ", ".join(f":{c}" for c in insert_columns)
    insert_sql = text(
        f'INSERT INTO "{target_schema}"."{target.table}" ({col_list_sql}) '
        f"VALUES ({values_placeholders})"
    )

    # Optionally truncate target table first
    if cmd.mode == "truncate_and_insert":
        truncate_sql = text(
            f'TRUNCATE TABLE "{target_schema}"."{target.table}" RESTART IDENTITY CASCADE'
        )
        with pg_engine.begin() as pg_conn:
            pg_conn.execute(truncate_sql)

    rows_inserted = 0
    batches = 0
    batch_size = max(1, min(cmd.batch_size or 1000, 10_000))

    try:
        with mssql_engine.connect() as mssql_conn:
            offset = 0
            while True:
                result = mssql_conn.execute(select_sql, {"offset": offset, "limit": batch_size})
                batch_rows = [dict(r) for r in result.mappings().all()]
                if not batch_rows:
                    break

                payloads: List[Dict[str, Any]] = []
                for row in batch_rows:
                    payload: Dict[str, Any] = {}
                    for target_col, rule in cmd.mapping.items():
                        if rule.type == "column":
                            if not rule.source:
                                raise HTTPException(
                                    status_code=status.HTTP_400_BAD_REQUEST,
                                    detail=f"Mapping for {target_col} missing 'source' field.",
                                )
                            payload[target_col] = row.get(rule.source)
                        elif rule.type == "expression":
                            payload[target_col] = row.get(target_col)
                        elif rule.type == "constant":
                            payload[target_col] = rule.value
                        else:
                            raise HTTPException(
                                status_code=status.HTTP_400_BAD_REQUEST,
                                detail=f"Unsupported mapping rule type: {rule.type}",
                            )

                    if raw_col:
                        raw_obj = {col: row.get(col) for col in source_column_names}
                        payload[raw_col] = raw_obj

                    payloads.append(payload)

                with pg_engine.begin() as pg_conn:
                    pg_conn.execute(insert_sql, payloads)

                batch_count = len(batch_rows)
                rows_inserted += batch_count
                batches += 1
                offset += batch_count

    finally:
        mssql_engine.dispose()

    return MigrationRunResult(
        ok=True,
        issues=validation.issues,
        estimated_rows=validation.estimated_rows,
        source=validation.source,
        target=validation.target,
        missing_target_columns=validation.missing_target_columns,
        rows_inserted=rows_inserted,
        batches=batches,
    )
