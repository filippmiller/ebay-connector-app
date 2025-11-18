from __future__ import annotations

from typing import Any, Dict, List, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.models.user import User
from app.services.admin_auth import get_current_admin_user
from app.services.mssql_client import MssqlConnectionConfig, get_table_columns, create_engine_for_session
from app.models_sqlalchemy import engine as pg_engine


router = APIRouter(prefix="/api/admin/migration", tags=["admin_migration"])


class OneToOneMigrationRequest(BaseModel):
    """Request payload for MSSQL → Supabase 1:1 table migration.

    MSSQL credentials are supplied per request and never persisted on the server.
    """

    mssql: MssqlConnectionConfig = Field(..., description="Ephemeral MSSQL connection configuration")
    source_schema: str = Field(..., description="MSSQL schema name (e.g. dbo)")
    source_table: str = Field(..., description="MSSQL table name")
    target_schema: str = Field("public", description="Supabase/Postgres schema name")
    target_table: str = Field(..., description="Target Supabase table name")
    mode: Literal["new-table", "existing"] = Field(
        "existing",
        description="Whether to create a new target table or insert into an existing one.",
    )
    batch_size: int = Field(1000, ge=1, le=10_000, description="Number of rows to copy per batch")


class OneToOneMigrationResult(BaseModel):
    status: str
    mode: str
    source: Dict[str, str]
    target: Dict[str, str]
    rows_inserted: int
    batches: int
    source_row_count: int | None = None
    target_row_count_before: int | None = None
    target_row_count_after: int | None = None


def _ensure_target_table_exists(
    pg_conn, *, schema: str, table: str, mssql_columns: List[Dict[str, Any]], mode: str
) -> None:
    """Create target table for 'new-table' mode or validate existence for 'existing'."""

    exists_sql = text(
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = :schema AND table_name = :table
        LIMIT 1
        """
    )
    exists = bool(pg_conn.execute(exists_sql, {"schema": schema, "table": table}).scalar())

    if mode == "new-table":
        if exists:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Target table {schema}.{table} already exists in Supabase.",
            )

        # Build a minimal CREATE TABLE statement based on MSSQL columns.
        col_defs: List[str] = []
        for col in mssql_columns:
            name = col["name"]
            mssql_type = str(col["dataType"])
            nullable = bool(col["isNullable"])
            pg_type = _map_mssql_to_postgres_type(mssql_type)
            parts = [f'"{name}"', pg_type]
            if not nullable:
                parts.append("NOT NULL")
            col_defs.append(" ".join(parts))

        if not col_defs:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Source table has no columns; nothing to create in Supabase.",
            )

        create_sql = text(
            f'CREATE TABLE "{schema}"."{table}" (\n  ' + ",\n  ".join(col_defs) + "\n)"
        )
        pg_conn.execute(create_sql)

    else:  # existing
        if not exists:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Target table {schema}.{table} does not exist in Supabase.",
            )


def _get_postgres_columns(pg_conn, *, schema: str, table: str) -> List[Dict[str, Any]]:
    cols_sql = text(
        """
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_schema = :schema AND table_name = :table
        ORDER BY ordinal_position
        """
    )
    rows = pg_conn.execute(cols_sql, {"schema": schema, "table": table}).mappings().all()
    return [
        {
            "name": r["column_name"],
            "data_type": r["data_type"],
            "is_nullable": str(r["is_nullable"]).lower() == "yes",
        }
        for r in rows
    ]


def _map_mssql_to_postgres_type(mssql_type: str) -> str:
    t = mssql_type.lower()
    if "bigint" in t:
        return "bigint"
    if t == "int" or "int" in t:
        return "integer"
    if any(x in t for x in ("decimal", "numeric", "money")):
        return "numeric"
    if "date" in t or "time" in t:
        return "timestamp"
    if "bit" in t:
        return "boolean"
    if any(x in t for x in ("char", "text", "nchar", "nvarchar", "varchar")):
        return "text"
    return "text"


@router.post("/mssql-to-supabase/one-to-one", response_model=OneToOneMigrationResult)
async def run_one_to_one_migration(
    payload: OneToOneMigrationRequest,
    current_user: User = Depends(get_current_admin_user),
) -> OneToOneMigrationResult:
    """Run a synchronous 1:1 table migration from MSSQL into Supabase.

    This endpoint is admin-only and uses MSSQL credentials provided in the request
    body (never persisted). Data is read-only on MSSQL and written into Supabase
    using the main application PostgreSQL connection.
    """

    # Load MSSQL column metadata first; this also validates connection and table.
    mssql_columns = get_table_columns(
        payload.mssql,
        schema=payload.source_schema,
        table=payload.source_table,
    )

    if not mssql_columns:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Source MSSQL table appears to have no columns.",
        )

    # Open MSSQL and Postgres connections.
    mssql_engine: Engine = create_engine_for_session(payload.mssql)
    rows_inserted = 0
    batches = 0
    source_row_count: int | None = None
    target_row_count_before: int | None = None
    target_row_count_after: int | None = None

    try:
        with mssql_engine.connect() as mssql_conn, pg_engine.begin() as pg_conn:
            # Ensure target table is present / created depending on mode.
            _ensure_target_table_exists(
                pg_conn,
                schema=payload.target_schema,
                table=payload.target_table,
                mssql_columns=mssql_columns,
                mode=payload.mode,
            )

            # Fetch Postgres columns and validate that every MSSQL column has a match.
            pg_columns = _get_postgres_columns(
                pg_conn,
                schema=payload.target_schema,
                table=payload.target_table,
            )
            pg_by_name = {c["name"].lower(): c for c in pg_columns}

            missing = [c["name"] for c in mssql_columns if c["name"].lower() not in pg_by_name]
            if missing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "message": "Target table is missing columns required for 1:1 migration.",
                        "missing_columns": missing,
                    },
                )

            # Duplicate check for existing tables: if there are already duplicate groups in
            # the target based on all columns, abort to avoid compounding duplicates.
            if payload.mode == "existing":
                if not pg_columns:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Target table has no columns; cannot perform duplicate check.",
                    )
                cols_list = ", ".join(f'"{c["name"]}'" for c in pg_columns)
                dup_sql = text(
                    f"""
                    SELECT COUNT(*) FROM (
                      SELECT 1
                      FROM {payload.target_schema}."{payload.target_table}"
                      GROUP BY {cols_list}
                      HAVING COUNT(*) > 1
                    ) AS dup
                    """
                )
                dup_groups = int(pg_conn.execute(dup_sql).scalar() or 0)
                if dup_groups > 0:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail={
                            "message": "Target table already contains duplicate groups; clean up duplicates before running another 1:1 migration.",
                            "duplicate_groups": dup_groups,
                        },
                    )

            # Compute counts before migration for visibility/verification.
            count_sql_mssql = text(
                f"SELECT COUNT(*) FROM [{payload.source_schema}].[{payload.source_table}]"
            )
            source_row_count = int(mssql_conn.execute(count_sql_mssql).scalar() or 0)

            count_sql_pg = text(
                f'SELECT COUNT(*) FROM "{payload.target_schema}"."{payload.target_table}"'
            )
            target_row_count_before = int(pg_conn.execute(count_sql_pg).scalar() or 0)

            # Column list for SELECT and INSERT (preserve MSSQL order).
            column_names: List[str] = [c["name"] for c in mssql_columns]

            # Build MSSQL SELECT (paged).
            select_cols = ", ".join(f"[{name}]" for name in column_names)
            select_sql = text(
                f"SELECT {select_cols} FROM [{payload.source_schema}].[{payload.source_table}] "
                "ORDER BY 1 OFFSET :offset ROWS FETCH NEXT :limit ROWS ONLY"
            )

            # Build Postgres INSERT.
            insert_cols = ", ".join(f'"{name}"' for name in column_names)
            value_placeholders = ", ".join(f":{name}" for name in column_names)
            insert_sql = text(
                f'INSERT INTO "{payload.target_schema}"."{payload.target_table}" '
                f'({insert_cols}) VALUES ({value_placeholders})'
            )

            offset = 0
            batch_size = payload.batch_size

            while True:
                result = mssql_conn.execute(select_sql, {"offset": offset, "limit": batch_size})
                rows = [dict(r) for r in result.mappings().all()]
                if not rows:
                    break

                pg_conn.execute(insert_sql, rows)

                batch_count = len(rows)
                rows_inserted += batch_count
                batches += 1
                offset += batch_count

            # Count rows after migration for verification.
            target_row_count_after = int(pg_conn.execute(count_sql_pg).scalar() or 0)

    finally:
        mssql_engine.dispose()

    return OneToOneMigrationResult(
        status="success",
        mode=payload.mode,
        source={"schema": payload.source_schema, "table": payload.source_table},
        target={"schema": payload.target_schema, "table": payload.target_table},
        rows_inserted=rows_inserted,
        batches=batches,
        source_row_count=source_row_count,
        target_row_count_before=target_row_count_before,
        target_row_count_after=target_row_count_after,
    )
