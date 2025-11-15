from __future__ import annotations

from typing import List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models_sqlalchemy import get_db, engine
from app.services.admin_auth import get_current_admin_user
from app.models.user import User

router = APIRouter(prefix="/api/admin/db", tags=["admin_db"])


ALLOWED_SCHEMAS = {"public"}


def _get_known_tables(db: Session) -> List[Dict[str, Any]]:
    """Return list of tables (schema, name, row_estimate) from information_schema / pg_class.

    This is used both for listing and for validating table_name inputs.
    """

    sql = text(
        """
        SELECT
            n.nspname AS schema,
            c.relname AS name,
            c.reltuples AS row_estimate
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = ANY(:schemas)
          AND c.relkind = 'r'
        ORDER BY n.nspname ASC, c.relname ASC
        """
    )
    result = db.execute(sql, {"schemas": list(ALLOWED_SCHEMAS)}).mappings().all()
    return [
        {
            "schema": row["schema"],
            "name": row["name"],
            "row_estimate": float(row["row_estimate"]) if row["row_estimate"] is not None else None,
        }
        for row in result
    ]


@router.get("/tables")
async def list_tables(
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """List all tables in allowed schemas (public by default).

    Returns: [{schema, name, row_estimate}, ...]
    """

    return _get_known_tables(db)


def _validate_table_name(db: Session, table_name: str) -> Dict[str, str]:
    if not table_name.isidentifier():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid table name",
        )

    tables = _get_known_tables(db)
    for t in tables:
        if t["name"] == table_name and t["schema"] in ALLOWED_SCHEMAS:
            return {"schema": t["schema"], "name": t["name"]}

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Table not found or not allowed",
    )


@router.get("/tables/{table_name}/schema")
async def get_table_schema(
    table_name: str,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Return column-level metadata for a specific table.

    Uses information_schema and pg_catalog to identify primary/foreign keys.
    """

    tbl = _validate_table_name(db, table_name)
    schema = tbl["schema"]

    # Column basics
    columns_sql = text(
        """
        SELECT
            c.column_name,
            c.data_type,
            c.is_nullable,
            c.column_default
        FROM information_schema.columns c
        WHERE c.table_schema = :schema
          AND c.table_name = :table
        ORDER BY c.ordinal_position
        """
    )
    cols = db.execute(columns_sql, {"schema": schema, "table": table_name}).mappings().all()

    # Primary key columns
    pk_sql = text(
        """
        SELECT kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.table_schema = kcu.table_schema
        WHERE tc.table_schema = :schema
          AND tc.table_name = :table
          AND tc.constraint_type = 'PRIMARY KEY'
        """
    )
    pk_cols = {row["column_name"] for row in db.execute(pk_sql, {"schema": schema, "table": table_name}).mappings()}

    # Foreign key columns
    fk_sql = text(
        """
        SELECT kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.table_schema = kcu.table_schema
        WHERE tc.table_schema = :schema
          AND tc.table_name = :table
          AND tc.constraint_type = 'FOREIGN KEY'
        """
    )
    fk_cols = {row["column_name"] for row in db.execute(fk_sql, {"schema": schema, "table": table_name}).mappings()}

    columns = []
    for col in cols:
        columns.append(
            {
                "name": col["column_name"],
                "data_type": col["data_type"],
                "is_nullable": (col["is_nullable"].lower() == "yes"),
                "is_primary_key": col["column_name"] in pk_cols,
                "is_foreign_key": col["column_name"] in fk_cols,
                "default": col["column_default"],
            }
        )

    return {
        "schema": schema,
        "name": table_name,
        "columns": columns,
    }


@router.get("/tables/{table_name}/rows")
async def get_table_rows(
    table_name: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Return last N rows for the table (read-only).

    Ordering rules:
    - If table has created_at: ORDER BY created_at DESC
    - Else if single-column primary key: ORDER BY pk DESC
    - Else: ORDER BY 1 DESC
    """

    tbl = _validate_table_name(db, table_name)
    schema = tbl["schema"]

    conn = engine.connect()
    try:
        # Detect created_at column
        has_created_at_sql = text(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = :schema
              AND table_name = :table
              AND column_name = 'created_at'
            LIMIT 1
            """
        )
        has_created_at = bool(
            conn.execute(has_created_at_sql, {"schema": schema, "table": table_name}).scalar()
        )

        # Detect primary key column
        pk_sql = text(
            """
            SELECT kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
            WHERE tc.table_schema = :schema
              AND tc.table_name = :table
              AND tc.constraint_type = 'PRIMARY KEY'
            ORDER BY kcu.ordinal_position
            """
        )
        pk_cols = [row[0] for row in conn.execute(pk_sql, {"schema": schema, "table": table_name}).fetchall()]

        if has_created_at:
            order_by = 'created_at'
        elif len(pk_cols) == 1:
            order_by = pk_cols[0]
        else:
            order_by = '1'

        rows_sql = text(
            f"SELECT * FROM {schema}.\"{table_name}\" ORDER BY {order_by} DESC LIMIT :limit OFFSET :offset"
        )
        rows_result = conn.execute(rows_sql, {"limit": limit, "offset": offset}).mappings().all()

        # Total estimate from pg_class
        est_sql = text(
            """
            SELECT c.reltuples
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = :schema
              AND c.relname = :table
            """
        )
        est = conn.execute(est_sql, {"schema": schema, "table": table_name}).scalar()
        total_estimate = float(est) if est is not None else None

        return {
            "rows": [dict(r) for r in rows_result],
            "limit": limit,
            "offset": offset,
            "total_estimate": total_estimate,
        }
    finally:
        conn.close()