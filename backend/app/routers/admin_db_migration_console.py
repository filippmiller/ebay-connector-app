from __future__ import annotations

from typing import Any, Dict, List, Optional

import time
from datetime import datetime

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
    batch_logs: List[str] = Field(default_factory=list)


class MigrationWorkerConfig(BaseModel):
    """Configuration payload for a MSSQL→Supabase incremental worker.

    This describes a single append-only table pair keyed by a single PK.
    """

    id: Optional[int] = None
    source_database: str
    source_schema: str = "dbo"
    source_table: str
    target_schema: str = "public"
    target_table: str
    pk_column: Optional[str] = None
    worker_enabled: bool = True
    interval_seconds: int = 300

    # Optional owner and notification flags
    owner_user_id: Optional[str] = None
    notify_on_success: bool = False
    notify_on_error: bool = True


class MigrationWorkerState(MigrationWorkerConfig):
    """Full worker state as stored in db_migration_workers.

    We expose timestamps as datetimes; FastAPI/Pydantic will serialize them
    as ISO8601 strings for the frontend.
    """

    last_run_started_at: Optional[datetime] = None
    last_run_finished_at: Optional[datetime] = None
    last_run_status: Optional[str] = None
    last_error: Optional[str] = None
    last_source_row_count: Optional[int] = None
    last_target_row_count: Optional[int] = None
    last_inserted_count: Optional[int] = None
    last_max_pk_source: Optional[int] = None
    last_max_pk_target: Optional[int] = None


class MigrationWorkerRunOnceRequest(BaseModel):
    """Request to run a single incremental pass for one worker.

    Either id or the (source_database, source_schema, source_table,
    target_schema, target_table) composite key must be provided.
    """

    id: Optional[int] = None
    source_database: Optional[str] = None
    source_schema: Optional[str] = None
    source_table: Optional[str] = None
    target_schema: Optional[str] = None
    target_table: Optional[str] = None
    batch_size: int = 5000
    # Hard cap for how long a single HTTP-triggered run should take, in seconds.
    # The background worker loop is not limited; this is just to avoid CF/axios timeouts.
    max_seconds: int = 20


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


def _get_pg_column_names(schema: str, table: str) -> List[str]:
    """Return ordered list of column names for a Postgres table."""

    sql = text(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = :schema AND table_name = :table
        ORDER BY ordinal_position
        """
    )
    with pg_engine.connect() as conn:
        rows = conn.execute(sql, {"schema": schema, "table": table}).mappings().all()
    return [r["column_name"] for r in rows]


def _pg_column_has_unique_or_pk(schema: str, table: str, column: str) -> bool:
    """Return True if *column* participates in a UNIQUE or PRIMARY KEY constraint.

    This is used to decide whether it's safe to use ON CONFLICT(column) DO NOTHING.
    If there is no such constraint, Postgres will raise
    InvalidColumnReference, so we skip ON CONFLICT entirely in that case.

    NOTE (2025-11-27): this helper is critical for the ebay fees worker to avoid
    inserting duplicates when rerunning migrations. Do not remove this check
    unless you also change the ON CONFLICT strategy.
    """

    sql = text(
        """
        SELECT 1
        FROM pg_constraint c
        JOIN pg_class t ON c.conrelid = t.oid
        JOIN pg_namespace n ON t.relnamespace = n.oid
        JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY (c.conkey)
        WHERE n.nspname = :schema
          AND t.relname = :table
          AND a.attname = :column
          AND c.contype IN ('p', 'u')
        LIMIT 1
        """
    )
    with pg_engine.connect() as conn:
        return bool(
            conn.execute(sql, {"schema": schema, "table": table, "column": column}).scalar()
        )


def _get_mssql_single_pk_column(cfg: MssqlConnectionConfig, schema: str, table: str) -> Optional[str]:
    """Return the single-column primary key for a MSSQL table, if any.

    If there is no PK or it is composite, returns None.
    """

    cols = mssql_client.get_table_columns(cfg, schema=schema, table=table)
    pk_cols = [c["name"] for c in cols if c.get("isPrimaryKey")]
    if len(pk_cols) == 1:
        return pk_cols[0]
    return None


def _load_worker_by_identity(payload: MigrationWorkerConfig) -> Optional[Dict[str, Any]]:
    """Fetch an existing db_migration_workers row matching payload identity.

    Identity is either explicit id or the (source_database, source_schema,
    source_table, target_schema, target_table) composite key.
    """

    with pg_engine.connect() as conn:
        if payload.id is not None:
            sql = text(
                """
                SELECT * FROM db_migration_workers WHERE id = :id
                """
            )
            row = conn.execute(sql, {"id": payload.id}).mappings().first()
            return dict(row) if row else None

        sql = text(
            """
            SELECT *
            FROM db_migration_workers
            WHERE source_database = :source_database
              AND source_schema = :source_schema
              AND source_table = :source_table
              AND target_schema = :target_schema
              AND target_table = :target_table
            """
        )
        row = conn.execute(
            sql,
            {
                "source_database": payload.source_database,
                "source_schema": payload.source_schema,
                "source_table": payload.source_table,
                "target_schema": payload.target_schema,
                "target_table": payload.target_table,
            },
        ).mappings().first()
        return dict(row) if row else None


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

    # Make migrations idempotent for typical tables that have a primary key 'id'.
    conflict_cols: List[str] = []
    if "id" in insert_columns:
        conflict_cols = ["id"]

    conflict_clause = ""
    if conflict_cols:
        conflict_cols_sql = ", ".join(f'"{c}"' for c in conflict_cols)
        conflict_clause = f" ON CONFLICT ({conflict_cols_sql}) DO NOTHING"

    insert_sql = text(
        f'INSERT INTO "{target_schema}"."{target.table}" ({col_list_sql}) '
        f"VALUES ({values_placeholders}){conflict_clause}"
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
    batch_logs: List[str] = []
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
                batch_logs.append(
                    f"Batch {batches} inserted {batch_count} row(s); total so far {rows_inserted}."
                )

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
        batch_logs=batch_logs,
    )


def run_worker_incremental_sync(
    *,
    # NOTE (2025-11-27): this function is used both by the admin API and the
    # background db_migration_worker loop. It must remain idempotent with
    # respect to PK collisions so that reruns after timeouts are safe.
    source_database: str,
    source_schema: str,
    source_table: str,
    target_schema: str,
    target_table: str,
    pk_column: str,
    batch_size: int = 5000,
    worker_id: Optional[int] = None,
    max_seconds: Optional[int] = None,
) -> Dict[str, Any]:
    """Run a single incremental append-only sync for one table pair.

    This helper is synchronous and intended for use both by the admin API and
    the background db_migration_worker loop.
    """

    if not pk_column:
        raise RuntimeError("pk_column is required for incremental sync")

    # Normalize schemas
    source_schema = source_schema or "dbo"
    target_schema = target_schema or "public"

    # MSSQL connection config (host/user/pass from env, db from argument).
    mssql_cfg = MssqlConnectionConfig(
        host=None,
        port=1433,
        database=source_database,
        username=None,
        password=None,
        encrypt=True,
    )

    # Determine current max PK in target (Supabase).
    with pg_engine.begin() as pg_conn:
        max_pk_sql = text(
            f'SELECT COALESCE(MAX("{pk_column}"), 0) FROM "{target_schema}"."{target_table}"'
        )
        target_max_pk = int(pg_conn.execute(max_pk_sql).scalar() or 0)

    # Fetch MSSQL column list and verify PK column exists.
    mssql_cols = mssql_client.get_table_columns(
        mssql_cfg,
        schema=source_schema,
        table=source_table,
    )
    if not any(c["name"].lower() == pk_column.lower() for c in mssql_cols):
        raise RuntimeError(
            f"PK column {pk_column!r} not found in MSSQL table {source_schema}.{source_table}"
        )

    source_column_names = [c["name"] for c in mssql_cols]

    # Ensure that the target table has (at least) all MSSQL columns; we will
    # only insert into the intersection.
    target_columns = _get_pg_column_names(target_schema, target_table)
    if not target_columns:
        raise RuntimeError(
            f"Target table {target_schema}.{target_table} does not exist in Supabase"
        )

    # Intersection of column names, preserving MSSQL order.
    insert_columns: List[str] = [
        name
        for name in source_column_names
        if name in target_columns
    ]
    if pk_column not in insert_columns:
        insert_columns.append(pk_column)

    if not insert_columns:
        raise RuntimeError(
            "No overlapping columns between MSSQL source and Supabase target for incremental worker"
        )

    # Build MSSQL SELECT with PK filter and paging.
    select_cols_sql = ", ".join(f"[{name}]" for name in insert_columns)
    select_sql = text(
        f"SELECT {select_cols_sql} "
        f"FROM [{source_schema}].[{source_table}] "
        f"WHERE [{pk_column}] > :min_pk "
        f"ORDER BY [{pk_column}] OFFSET :offset ROWS FETCH NEXT :limit ROWS ONLY"
    )

    # Build Postgres INSERT. We prefer ON CONFLICT(pk) DO NOTHING for idempotency,
    # but Postgres requires a UNIQUE or PRIMARY KEY constraint on that column.
    col_list_sql = ", ".join(f'"{c}"' for c in insert_columns)
    values_placeholders = ", ".join(f":{c}" for c in insert_columns)

    conflict_clause = ""
    if _pg_column_has_unique_or_pk(target_schema, target_table, pk_column):
        conflict_clause = f' ON CONFLICT ("{pk_column}") DO NOTHING'

    insert_sql = text(
        f'INSERT INTO "{target_schema}"."{target_table}" ({col_list_sql}) '
        f"VALUES ({values_placeholders}){conflict_clause}"
    )

    batch_size = max(1, min(batch_size or 1000, 10_000))
    rows_inserted = 0
    batches = 0
    last_source_pk: Optional[int] = None

    # For HTTP-triggered runs we may want to cap total runtime to avoid CF/axios timeouts.
    start_time = time.monotonic()

    mssql_engine: Engine = create_engine_for_session(mssql_cfg)
    try:
        with mssql_engine.connect() as mssql_conn:
            offset = 0
            while True:
                if max_seconds is not None and batches > 0:
                    elapsed = time.monotonic() - start_time
                    if elapsed >= max_seconds:
                        break
                result = mssql_conn.execute(
                    select_sql,
                    {"min_pk": target_max_pk, "offset": offset, "limit": batch_size},
                )
                batch_rows = [dict(r) for r in result.mappings().all()]
                if not batch_rows:
                    break

                # Track max PK in this batch for diagnostic purposes.
                for row in batch_rows:
                    pk_val = row.get(pk_column)
                    if isinstance(pk_val, int):
                        if last_source_pk is None or pk_val > last_source_pk:
                            last_source_pk = pk_val

                with pg_engine.begin() as pg_conn:
                    pg_conn.execute(insert_sql, batch_rows)

                batch_count = len(batch_rows)
                rows_inserted += batch_count
                batches += 1
                offset += batch_count
    finally:
        mssql_engine.dispose()

    # Update worker state row (best-effort) if worker_id provided.
    with pg_engine.begin() as pg_conn:
        # Recompute target_max_pk after inserts for observability.
        new_target_max_pk = int(
            pg_conn.execute(
                text(
                    f'SELECT COALESCE(MAX("{pk_column}"), 0) FROM "{target_schema}"."{target_table}"'
                )
            ).scalar()
            or 0
        )
        # Counts for logging.
        source_count = None
        try:
            # Lightweight approximate count from MSSQL.
            src_engine: Engine = create_engine_for_session(mssql_cfg)
            with src_engine.connect() as sconn:
                csql = text(
                    f"SELECT COUNT(*) FROM [{source_schema}].[{source_table}]"
                )
                source_count = int(sconn.execute(csql).scalar() or 0)
        except Exception:  # noqa: BLE001
            source_count = None
        finally:
            try:
                src_engine.dispose()  # type: ignore[name-defined]
            except Exception:  # noqa: BLE001
                pass

        target_count = int(
            pg_conn.execute(
                text(
                    f'SELECT COUNT(*) FROM "{target_schema}"."{target_table}"'
                )
            ).scalar()
            or 0
        )

        if worker_id is not None:
            update_sql = text(
                """
                UPDATE db_migration_workers
                SET
                  last_run_started_at = COALESCE(last_run_started_at, NOW()),
                  last_run_finished_at = NOW(),
                  last_run_status = :status,
                  last_error = :error,
                  last_source_row_count = :source_count,
                  last_target_row_count = :target_count,
                  last_inserted_count = :inserted,
                  last_max_pk_source = :last_source_pk,
                  last_max_pk_target = :last_target_pk,
                  updated_at = NOW()
                WHERE id = :id
                """
            )
            pg_conn.execute(
                update_sql,
                {
                    "status": "ok",
                    "error": None,
                    "source_count": source_count,
                    "target_count": target_count,
                    "inserted": rows_inserted,
                    "last_source_pk": last_source_pk,
                    "last_target_pk": new_target_max_pk,
                    "id": worker_id,
                },
            )

    return {
        "status": "ok",
        "rows_inserted": rows_inserted,
        "batches": batches,
        "source_row_count": source_count,
        "target_row_count": target_count,
        "previous_target_max_pk": target_max_pk,
        "new_target_max_pk": new_target_max_pk,
    }


class MigrationWorkerPreview(BaseModel):
    """Lightweight preview for a worker run used in the UI confirmation modal."""

    source_database: str
    source_schema: str
    source_table: str
    target_schema: str
    target_table: str
    pk_column: str

    source_row_count: int
    target_row_count: int
    rows_to_copy: int
    source_max_pk: Optional[int]
    target_max_pk: Optional[int]


@router.get("/worker/state", response_model=List[MigrationWorkerState])
async def list_migration_workers(
    current_user: User = Depends(get_current_admin_user),
) -> List[MigrationWorkerState]:
    """Return all db_migration_workers rows.

    This is a thin wrapper over the db_migration_workers table for the admin UI.
    """

    sql = text("SELECT * FROM db_migration_workers ORDER BY id")
    with pg_engine.connect() as conn:
        rows = conn.execute(sql).mappings().all()
    return [MigrationWorkerState(**dict(row)) for row in rows]


@router.post("/worker/upsert", response_model=MigrationWorkerState)
async def upsert_migration_worker(
    payload: MigrationWorkerConfig,
    current_user: User = Depends(get_current_admin_user),
) -> MigrationWorkerState:
    """Create or update a db_migration_workers row.

    If pk_column is not provided, we attempt to auto-detect a single-column
    primary key from MSSQL.
    """

    if not payload.source_database:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="source_database is required",
        )

    # Ensure target table exists.
    target_cols = _get_pg_column_names(
        payload.target_schema or "public", payload.target_table
    )
    if not target_cols:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Target table {payload.target_schema or 'public'}.{payload.target_table} "
                "does not exist in Supabase."
            ),
        )

    # Auto-detect PK column if missing.
    pk_column = payload.pk_column
    mssql_cfg = MssqlConnectionConfig(
        host=None,
        port=1433,
        database=payload.source_database,
        username=None,
        password=None,
        encrypt=True,
    )
    if not pk_column:
        auto_pk = _get_mssql_single_pk_column(
            mssql_cfg, payload.source_schema or "dbo", payload.source_table
        )
        if not auto_pk:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Could not auto-detect a single-column primary key on MSSQL table "
                    f"{payload.source_schema or 'dbo'}.{payload.source_table}. "
                    "Specify pk_column explicitly."
                ),
            )
        pk_column = auto_pk

    payload.pk_column = pk_column

    # Default owner to the current admin user when not set
    if not payload.owner_user_id:
        payload.owner_user_id = current_user.id

    existing = _load_worker_by_identity(payload)

    with pg_engine.begin() as conn:
        if existing:
            sql = text(
                """
                UPDATE db_migration_workers
                SET
                  source_database = :source_database,
                  source_schema = :source_schema,
                  source_table = :source_table,
                  target_schema = :target_schema,
                  target_table = :target_table,
                  pk_column = :pk_column,
                  worker_enabled = :worker_enabled,
                  interval_seconds = :interval_seconds,
                  owner_user_id = :owner_user_id,
                  notify_on_success = :notify_on_success,
                  notify_on_error = :notify_on_error,
                  updated_at = NOW()
                WHERE id = :id
                RETURNING *
                """
            )
            row = conn.execute(
                sql,
                {
                    "id": existing["id"],
                    "source_database": payload.source_database,
                    "source_schema": payload.source_schema or "dbo",
                    "source_table": payload.source_table,
                    "target_schema": payload.target_schema or "public",
                    "target_table": payload.target_table,
                    "pk_column": pk_column,
                    "worker_enabled": payload.worker_enabled,
                    "interval_seconds": payload.interval_seconds,
                    "owner_user_id": existing.get("owner_user_id") or payload.owner_user_id,
                    "notify_on_success": payload.notify_on_success,
                    "notify_on_error": payload.notify_on_error,
                },
            ).mappings().first()
        else:
            sql = text(
                """
                INSERT INTO db_migration_workers (
                  source_database,
                  source_schema,
                  source_table,
                  target_schema,
                  target_table,
                  pk_column,
                  worker_enabled,
                  interval_seconds,
                  owner_user_id,
                  notify_on_success,
                  notify_on_error,
                  created_at,
                  updated_at
                ) VALUES (
                  :source_database,
                  :source_schema,
                  :source_table,
                  :target_schema,
                  :target_table,
                  :pk_column,
                  :worker_enabled,
                  :interval_seconds,
                  :owner_user_id,
                  :notify_on_success,
                  :notify_on_error,
                  NOW(),
                  NOW()
                )
                RETURNING *
                """
            )
            row = conn.execute(
                sql,
                {
                    "source_database": payload.source_database,
                    "source_schema": payload.source_schema or "dbo",
                    "source_table": payload.source_table,
                    "target_schema": payload.target_schema or "public",
                    "target_table": payload.target_table,
                    "pk_column": pk_column,
                    "worker_enabled": payload.worker_enabled,
                    "interval_seconds": payload.interval_seconds,
                    "owner_user_id": payload.owner_user_id,
                    "notify_on_success": payload.notify_on_success,
                    "notify_on_error": payload.notify_on_error,
                },
            ).mappings().first()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upsert migration worker",
        )

    return MigrationWorkerState(**dict(row))


@router.post("/worker/preview", response_model=MigrationWorkerPreview)
async def preview_migration_worker_run(
    req: MigrationWorkerRunOnceRequest,
    current_user: User = Depends(get_current_admin_user),
) -> MigrationWorkerPreview:
    """Compute a short summary of what a run would do, without inserting rows.

    Used by the admin UI to show a confirmation modal before running.
    """

    # Load the worker row (same logic as run-once).
    with pg_engine.connect() as conn:
        if req.id is not None:
            sql = text("SELECT * FROM db_migration_workers WHERE id = :id")
            row = conn.execute(sql, {"id": req.id}).mappings().first()
        else:
            if not (
                req.source_database
                and req.source_schema
                and req.source_table
                and req.target_schema
                and req.target_table
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Either id or full source/target identity must be provided.",
                )
            sql = text(
                """
                SELECT *
                FROM db_migration_workers
                WHERE source_database = :source_database
                  AND source_schema = :source_schema
                  AND source_table = :source_table
                  AND target_schema = :target_schema
                  AND target_table = :target_table
                """
            )
            row = conn.execute(
                sql,
                {
                    "source_database": req.source_database,
                    "source_schema": req.source_schema,
                    "source_table": req.source_table,
                    "target_schema": req.target_schema,
                    "target_table": req.target_table,
                },
            ).mappings().first()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Migration worker not found",
        )

    worker = dict(row)
    pk_column = worker["pk_column"]
    source_schema = worker["source_schema"] or "dbo"
    target_schema = worker["target_schema"] or "public"

    # Target stats (Supabase)
    with pg_engine.connect() as pg_conn:
        max_pk_sql = text(
            f'SELECT COALESCE(MAX("{pk_column}"), 0) FROM "{target_schema}"."{worker["target_table"]}"'
        )
        target_max_pk = int(pg_conn.execute(max_pk_sql).scalar() or 0)

        target_count_sql = text(
            f'SELECT COUNT(*) FROM "{target_schema}"."{worker["target_table"]}"'
        )
        target_row_count = int(pg_conn.execute(target_count_sql).scalar() or 0)

    # Source stats (MSSQL)
    mssql_cfg = MssqlConnectionConfig(
        host=None,
        port=1433,
        database=worker["source_database"],
        username=None,
        password=None,
        encrypt=True,
    )
    mssql_engine: Engine = create_engine_for_session(mssql_cfg)
    try:
        with mssql_engine.connect() as mssql_conn:
            source_count_sql = text(
                f"SELECT COUNT(*) FROM [{source_schema}].[{worker['source_table']}]"
            )
            source_row_count = int(
                mssql_conn.execute(source_count_sql).scalar() or 0
            )

            source_max_pk_sql = text(
                f"SELECT COALESCE(MAX([{pk_column}]), 0) FROM [{source_schema}].[{worker['source_table']}]"
            )
            source_max_pk = int(
                mssql_conn.execute(source_max_pk_sql).scalar() or 0
            )

            # How many rows would be copied if we ran now?
            rows_to_copy_sql = text(
                f"SELECT COUNT(*) FROM [{source_schema}].[{worker['source_table']}] "
                f"WHERE [{pk_column}] > :min_pk"
            )
            rows_to_copy = int(
                mssql_conn.execute(
                    rows_to_copy_sql, {"min_pk": target_max_pk}
                ).scalar()
                or 0
            )
    finally:
        mssql_engine.dispose()

    return MigrationWorkerPreview(
        source_database=worker["source_database"],
        source_schema=source_schema,
        source_table=worker["source_table"],
        target_schema=target_schema,
        target_table=worker["target_table"],
        pk_column=pk_column,
        source_row_count=source_row_count,
        target_row_count=target_row_count,
        rows_to_copy=rows_to_copy,
        source_max_pk=source_max_pk,
        target_max_pk=target_max_pk,
    )


@router.post("/worker/run-once")
async def run_migration_worker_once(
    req: MigrationWorkerRunOnceRequest,
    current_user: User = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Run a single incremental pass for one configured worker."""

    # Load the worker row.
    with pg_engine.connect() as conn:
        if req.id is not None:
            sql = text("SELECT * FROM db_migration_workers WHERE id = :id")
            row = conn.execute(sql, {"id": req.id}).mappings().first()
        else:
            if not (
                req.source_database
                and req.source_schema
                and req.source_table
                and req.target_schema
                and req.target_table
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Either id or full source/target identity must be provided.",
                )
            sql = text(
                """
                SELECT *
                FROM db_migration_workers
                WHERE source_database = :source_database
                  AND source_schema = :source_schema
                  AND source_table = :source_table
                  AND target_schema = :target_schema
                  AND target_table = :target_table
                """
            )
            row = conn.execute(
                sql,
                {
                    "source_database": req.source_database,
                    "source_schema": req.source_schema,
                    "source_table": req.source_table,
                    "target_schema": req.target_schema,
                    "target_table": req.target_table,
                },
            ).mappings().first()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Migration worker not found",
        )

    worker = dict(row)

    summary = run_worker_incremental_sync(
        source_database=worker["source_database"],
        source_schema=worker["source_schema"],
        source_table=worker["source_table"],
        target_schema=worker["target_schema"],
        target_table=worker["target_table"],
        pk_column=worker["pk_column"],
        batch_size=req.batch_size,
        worker_id=worker["id"],
        max_seconds=req.max_seconds,
    )

    return summary
