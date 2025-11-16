from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.engine import URL, create_engine, Engine


class MssqlConnectionConfig(BaseModel):
    """Connection configuration for a temporary MSSQL session.

    This is used only in admin-only endpoints and never persisted.
    """

    host: str
    port: int = 1433
    database: str
    username: str
    password: str = Field(repr=False)
    encrypt: bool = True


def _build_url(config: MssqlConnectionConfig) -> URL:
    """Build a SQLAlchemy URL for MSSQL+pyodbc without leaking passwords in logs.

    We rely on the standard `ODBC Driver 18 for SQL Server` by default.
    """

    query: Dict[str, Any] = {
        "driver": "ODBC Driver 18 for SQL Server",
        # Encrypt flag can be toggled; TrustServerCertificate=yes is convenient for internal use.
        "Encrypt": "yes" if config.encrypt else "no",
        "TrustServerCertificate": "yes",
    }

    return URL.create(
        drivername="mssql+pyodbc",
        username=config.username,
        password=config.password,
        host=config.host,
        port=config.port,
        database=config.database,
        query=query,
    )


def _create_engine(config: MssqlConnectionConfig) -> Engine:
    url = _build_url(config)
    # Small timeout, this is an interactive admin tool.
    engine = create_engine(url, pool_pre_ping=True, connect_args={"timeout": 5})
    return engine


def test_connection(config: MssqlConnectionConfig) -> None:
    """Validate that we can connect and run a trivial query.

    Raises an exception on failure.
    """

    engine = _create_engine(config)
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))


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
