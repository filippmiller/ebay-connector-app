from __future__ import annotations

import os
from typing import Any, Dict, List

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.engine import URL, create_engine, Engine
from sqlalchemy.dialects import registry as _sa_dialect_registry

# Ensure the `mssql+pytds` dialect is registered even if entry points are not
# discovered correctly in the deployment environment. This maps the
# "mssql.pytds" name used in the SQLAlchemy URL to the dialect implementation
# provided by the `sqlalchemy-pytds` package.
_sa_dialect_registry.register("mssql.pytds", "sqlalchemy_pytds", "MSDialect_pytds")

# NOTE: We intentionally avoid any ODBC-based drivers (pyodbc/msodbcsql).
# The MSSQL client uses the pure-Python `sqlalchemy-pytds` dialect
# (`mssql+pytds`) which only depends on python-tds and does not require
# unixODBC or system-level drivers. This is much more reliable on Railway.


class MssqlConnectionConfig(BaseModel):
    """Connection configuration for a temporary MSSQL session.

    This is used only in admin-only endpoints and never persisted.

    Host / username / password can be omitted by the client; in that case we fall
    back to Railway/host environment variables (mssql_url, mssql_username,
    mssql_password or their uppercase variants). This allows wiring credentials
    on the server side while keeping the UI credential-free.
    """

    host: str | None = None
    port: int = 1433
    database: str
    username: str | None = None
    password: str | None = Field(default=None, repr=False)
    encrypt: bool = True


def _resolve_host_user_password(config: MssqlConnectionConfig) -> tuple[str, str, str]:
    """Fill in host/username/password from env if they are missing/blank."""

    env_host = os.getenv("mssql_url") or os.getenv("MSSQL_URL")
    env_user = os.getenv("mssql_username") or os.getenv("MSSQL_USERNAME")
    env_pass = os.getenv("mssql_password") or os.getenv("MSSQL_PASSWORD")

    host = (config.host or "").strip() or env_host
    username = (config.username or "").strip() or env_user
    password = (config.password or "").strip() or env_pass

    if not host or not username or not password:
        raise RuntimeError(
            "MSSQL connection is not fully configured: host/username/password are missing. "
            "Configure mssql_url, mssql_username, and mssql_password in your environment.",
        )

    return host, username, password


def _build_url(config: MssqlConnectionConfig) -> URL:
    """Build a SQLAlchemy URL for MSSQL using the pure-Python pytds dialect.

    Driver string: ``mssql+pytds``

    We URL-encode username/password to avoid issues with special characters.
    The `encrypt` flag is currently not wired to pytds-specific params; for
    typical intranet / VPN deployments this is acceptable. If strict TLS
    configuration is required later, we can extend the query parameters
    accordingly (e.g. ``use_tls=1`` if supported).
    """

    host, username, password = _resolve_host_user_password(config)

    # Base query params; charset=utf8 is recommended for SQL Server.
    query: Dict[str, Any] = {
        "charset": "utf8",
    }

    return URL.create(
        drivername="mssql+pytds",
        username=username,
        password=password,
        host=host,
        port=config.port,
        database=config.database,
        query=query,
    )


def _create_engine(config: MssqlConnectionConfig) -> Engine:
    url = _build_url(config)
    # Small timeout, this is an interactive admin tool.
    engine = create_engine(url, pool_pre_ping=True, connect_args={"timeout": 5})
    return engine


def create_engine_for_session(config: MssqlConnectionConfig) -> Engine:
    """Public helper for creating a short-lived MSSQL engine.

    Used by admin-only tools such as the Dual-DB Migration Studio. The caller is
    responsible for disposing the engine after use.
    """

    return _create_engine(config)


def test_connection(config: MssqlConnectionConfig) -> Dict[str, Any]:
    """Validate that we can connect and run a trivial query.

    Returns basic metadata (e.g. server version, driver name).
    Raises an exception on failure.
    """

    engine = _create_engine(config)
    try:
        with engine.connect() as conn:
            # Use @@VERSION to get a human-readable SQL Server version string.
            version_result = conn.execute(text("SELECT @@VERSION AS version"))
            version_row = version_result.fetchone()
            server_version = str(version_row[0]) if version_row else "unknown"
    finally:
        engine.dispose()

    return {
        "server_version": server_version,
        "driver": "pytds",
    }


def get_schema_tree(config: MssqlConnectionConfig) -> Dict[str, Any]:
    """Return database -> schemas -> tables tree.

    Example:
    {
        "database": "DB_A28F26_parts",
        "schemas": [
            {"name": "dbo", "tables": [{"name": "tbl_ebay_seller_info"}, ...]},
        ],
    }
    """

    engine = _create_engine(config)
    with engine.connect() as conn:
        result = conn.execute(
            text(
                """
                SELECT TABLE_SCHEMA AS schema_name, TABLE_NAME AS table_name
                FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_TYPE = 'BASE TABLE'
                ORDER BY TABLE_SCHEMA, TABLE_NAME
                """
            )
        )
        rows = list(result.mappings())

    schemas: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        schema_name = row["schema_name"]
        table_name = row["table_name"]
        if schema_name not in schemas:
            schemas[schema_name] = {"name": schema_name, "tables": []}
        schemas[schema_name]["tables"].append({"name": table_name})

    return {
        "database": config.database,
        "schemas": list(schemas.values()),
    }


def get_table_columns(
    config: MssqlConnectionConfig, schema: str, table: str
) -> List[Dict[str, Any]]:
    """Return column metadata for a given table.

    Shape:
    [
      {
        "name": "TransactionID",
        "dataType": "bigint",
        "isNullable": False,
        "isPrimaryKey": False,
        "defaultValue": None,
      },
      ...
    ]
    """

    engine = _create_engine(config)
    with engine.connect() as conn:
        cols_result = conn.execute(
            text(
                """
                SELECT
                    c.COLUMN_NAME,
                    c.DATA_TYPE,
                    c.IS_NULLABLE,
                    c.COLUMN_DEFAULT
                FROM INFORMATION_SCHEMA.COLUMNS c
                WHERE c.TABLE_SCHEMA = :schema
                  AND c.TABLE_NAME = :table
                ORDER BY c.ORDINAL_POSITION
                """
            ),
            {"schema": schema, "table": table},
        )
        cols = list(cols_result.mappings())

        pk_result = conn.execute(
            text(
                """
                SELECT kcu.COLUMN_NAME
                FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
                JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
                  ON tc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME
                 AND tc.TABLE_SCHEMA = kcu.TABLE_SCHEMA
                WHERE tc.TABLE_SCHEMA = :schema
                  AND tc.TABLE_NAME = :table
                  AND tc.CONSTRAINT_TYPE = 'PRIMARY KEY'
                """
            ),
            {"schema": schema, "table": table},
        )
        pk_cols = {row["COLUMN_NAME"] for row in pk_result.mappings()}

    result: List[Dict[str, Any]] = []
    for col in cols:
        result.append(
            {
                "name": col["COLUMN_NAME"],
                "dataType": col["DATA_TYPE"],
                "isNullable": str(col["IS_NULLABLE"]).upper() == "YES",
                "isPrimaryKey": col["COLUMN_NAME"] in pk_cols,
                "defaultValue": col["COLUMN_DEFAULT"],
            }
        )
    return result


def get_table_preview(
    config: MssqlConnectionConfig,
    schema: str,
    table: str,
    limit: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """Return a small page of rows for the given table.

    Shape:
    {
      "columns": ["TransactionID", ...],
      "rows": [[123, ...], ...],
      "limit": 50,
      "offset": 0,
    }
    """

    if limit <= 0:
        limit = 50
    if offset < 0:
        offset = 0

    engine = _create_engine(config)
    with engine.connect() as conn:
        # NOTE: We use ORDER BY 1 here as a simple deterministic ordering.
        # For migration exploration this is sufficient.
        sql = text(
            f"SELECT * FROM [{schema}].[{table}] ORDER BY 1 OFFSET :offset ROWS FETCH NEXT :limit ROWS ONLY"
        )
        result = conn.execute(sql, {"offset": offset, "limit": limit})

        columns = list(result.keys())
        rows = [list(r) for r in result.fetchall()]

    return {
        "columns": columns,
        "rows": rows,
        "limit": limit,
        "offset": offset,
    }


def get_latest_rows(
    config: MssqlConnectionConfig,
    schema: str,
    table: str,
    limit: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """Return the latest rows for the given table.

    Ordering rules (mirrors Postgres admin_db.get_table_rows):
    - If table has created_at: ORDER BY created_at DESC
    - Else if single-column primary key: ORDER BY pk DESC
    - Else: ORDER BY 1 DESC
    """

    if limit <= 0:
        limit = 50
    if offset < 0:
        offset = 0

    engine = _create_engine(config)
    with engine.connect() as conn:
        # Detect created_at column
        has_created_at_sql = text(
            """
            SELECT 1
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = :schema
              AND TABLE_NAME = :table
              AND COLUMN_NAME = 'created_at'
            """
        )
        has_created_at = bool(
            conn.execute(has_created_at_sql, {"schema": schema, "table": table}).scalar()
        )

        # Detect primary key columns
        pk_sql = text(
            """
            SELECT kcu.COLUMN_NAME
            FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
            JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
              ON tc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME
             AND tc.TABLE_SCHEMA = kcu.TABLE_SCHEMA
            WHERE tc.TABLE_SCHEMA = :schema
              AND tc.TABLE_NAME = :table
              AND tc.CONSTRAINT_TYPE = 'PRIMARY KEY'
            ORDER BY kcu.ORDINAL_POSITION
            """
        )
        pk_cols = [row["COLUMN_NAME"] for row in conn.execute(pk_sql, {"schema": schema, "table": table}).mappings()]

        if has_created_at:
            order_by = "created_at"
        elif len(pk_cols) == 1:
            order_by = pk_cols[0]
        else:
            order_by = "1"

        sql = text(
            f"SELECT * FROM [{schema}].[{table}] ORDER BY {order_by} DESC OFFSET :offset ROWS FETCH NEXT :limit ROWS ONLY"
        )
        result = conn.execute(sql, {"offset": offset, "limit": limit})

        columns = list(result.keys())
        rows = [list(r) for r in result.fetchall()]

    return {
        "columns": columns,
        "rows": rows,
        "limit": limit,
        "offset": offset,
    }


def search_database(
    config: MssqlConnectionConfig,
    q: str,
    limit_per_table: int = 50,
) -> Dict[str, Any]:
    """Naive global search across all text-ish columns in the MSSQL database.

    This mirrors the Postgres admin_db.search endpoint but uses INFORMATION_SCHEMA
    and T-SQL. It is intended for ad-hoc admin troubleshooting, not for
    high-performance querying.
    """

    if limit_per_table <= 0:
        limit_per_table = 50

    engine = _create_engine(config)
    with engine.connect() as conn:
        # Discover text-like columns across all base tables in the database.
        cols_sql = text(
            """
            SELECT
                t.TABLE_SCHEMA AS schema_name,
                t.TABLE_NAME AS table_name,
                c.COLUMN_NAME AS column_name,
                c.DATA_TYPE AS data_type
            FROM INFORMATION_SCHEMA.TABLES t
            JOIN INFORMATION_SCHEMA.COLUMNS c
              ON t.TABLE_SCHEMA = c.TABLE_SCHEMA
             AND t.TABLE_NAME = c.TABLE_NAME
            WHERE t.TABLE_TYPE = 'BASE TABLE'
              AND c.DATA_TYPE IN (
                'varchar','nvarchar','nchar','char','text','ntext'
              )
            ORDER BY t.TABLE_SCHEMA, t.TABLE_NAME, c.ORDINAL_POSITION
            """
        )
        rows = list(conn.execute(cols_sql).mappings())

        tables: Dict[tuple[str, str], Dict[str, Any]] = {}
        for row in rows:
            key = (row["schema_name"], row["table_name"])
            if key not in tables:
                tables[key] = {"schema": row["schema_name"], "name": row["table_name"], "columns": []}
            tables[key]["columns"].append(row["column_name"])

        results: Dict[str, Any] = {"query": q, "tables": []}
        pattern = f"%{q.lower()}%"

        for (schema_name, table_name), info in tables.items():
            text_cols = info["columns"]
            if not text_cols:
                continue

            where_clauses = " OR ".join(
                [
                    f"LOWER(CAST([{col}] AS NVARCHAR(MAX))) LIKE :pattern"
                    for col in text_cols
                ]
            )

            search_sql = text(
                f"SELECT * FROM [{schema_name}].[{table_name}] WHERE {where_clauses} "
                "ORDER BY 1 OFFSET 0 ROWS FETCH NEXT :limit ROWS ONLY"
            )
            table_rows = conn.execute(search_sql, {"pattern": pattern, "limit": limit_per_table}).mappings().all()
            if table_rows:
                results["tables"].append(
                    {
                        "schema": schema_name,
                        "name": table_name,
                        "matched_columns": text_cols,
                        "rows": [dict(r) for r in table_rows],
                    }
                )

    return results
