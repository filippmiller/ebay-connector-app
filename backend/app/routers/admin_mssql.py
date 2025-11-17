from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.models.user import User
from app.services.admin_auth import get_current_admin_user
from app.services import mssql_client
from app.services.mssql_client import MssqlConnectionConfig

router = APIRouter(prefix="/api/admin/mssql", tags=["admin_mssql"])


class SchemaTreeRequest(MssqlConnectionConfig):
    pass


class TableColumnsRequest(MssqlConnectionConfig):
    schema: str
    table: str


class TablePreviewRequest(TableColumnsRequest):
    limit: int = 50
    offset: int = 0


@router.post("/test-connection")
async def test_connection_endpoint(
    config: MssqlConnectionConfig,
    current_user: User = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Test MSSQL connection without persisting credentials.

    Returns {"ok": true, "details": {...}} on success,
    or {"ok": false, "error": "...", "raw_error": "..."} on failure.
    """

    try:
        details = mssql_client.test_connection(config)
        return {
            "ok": True,
            "message": "Connection successful",
            "details": details,
        }
    except Exception as e:  # noqa: BLE001 - we want to surface driver errors as text
        raw_message = str(e) or "Connection failed"

        # Hide very low-level driver messages from the UI, but keep them in raw_error for logs.
        if "libodbc.so" in raw_message:
            safe_message = "MSSQL ODBC driver is not available on the server. Please contact the administrator."
        else:
            safe_message = raw_message

        return {"ok": False, "error": safe_message, "raw_error": raw_message}


@router.post("/schema-tree")
async def get_schema_tree_endpoint(
    payload: SchemaTreeRequest,
    current_user: User = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Return MSSQL database -> schemas -> tables tree for the given connection."""

    try:
        tree = mssql_client.get_schema_tree(payload)
        return tree
    except Exception as e:  # noqa: BLE001
        message = str(e) or "Failed to fetch schema tree"
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        ) from e


@router.post("/table-columns")
async def get_table_columns_endpoint(
    payload: TableColumnsRequest,
    current_user: User = Depends(get_current_admin_user),
) -> List[Dict[str, Any]]:
    """Return column metadata for a given MSSQL table."""

    try:
        cols = mssql_client.get_table_columns(payload, schema=payload.schema, table=payload.table)
        return cols
    except Exception as e:  # noqa: BLE001
        message = str(e) or "Failed to fetch table columns"
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        ) from e


@router.post("/table-preview")
async def get_table_preview_endpoint(
    payload: TablePreviewRequest,
    current_user: User = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Return a page of sample rows for a given MSSQL table."""

    try:
        preview = mssql_client.get_table_preview(
            payload,
            schema=payload.schema,
            table=payload.table,
            limit=payload.limit,
            offset=payload.offset,
        )
        return preview
    except Exception as e:  # noqa: BLE001
        message = str(e) or "Failed to fetch table preview"
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        ) from e
