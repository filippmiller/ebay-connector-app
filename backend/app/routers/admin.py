from fastapi import APIRouter, Depends, Query, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc, or_, and_
from typing import Optional, Any
import os
from datetime import datetime, timezone, timedelta
from pydantic import BaseModel

from ..models_sqlalchemy import get_db
from ..models_sqlalchemy.models import SyncLog, EbayAccount, EbayToken, EbayAuthorization, EbayScopeDefinition, EbayEvent
from ..models_sqlalchemy.ebay_workers import (
    EbayWorkerRun,
    BackgroundWorker,
    EbayTokenRefreshLog,
)
from ..services.auth import admin_required
from ..models.user import User
from ..utils.logger import logger
from ..services.ebay import ebay_service
from ..services.ebay_connect_logger import ebay_connect_logger
from ..services.ebay_token_refresh_service import build_sanitized_refresh_preview_for_account, run_token_refresh_job
from ..services.ebay_notification_topics import SUPPORTED_TOPICS, PRIMARY_WEBHOOK_TOPIC_ID
from ..config import settings
from app.services.ebay_token_refresh_service import refresh_access_token_for_account
from app.workers.ebay_workers_loop import run_ebay_workers_once

FEATURE_TOKEN_INFO = os.getenv('FEATURE_TOKEN_INFO', 'false').lower() == 'true'

router = APIRouter(prefix="/api/admin", tags=["admin"])


# -------------------------------
# Test Computer Analytics (classic + graph)
# -------------------------------

# Helper: build WHERE clause for storage_id across variable column casing
def _build_storage_where(columns: set[str]) -> str:
    """Return SQL OR clause matching storage_id against known storage column variants."""
    candidates = [
        "storage",
        "Storage",
        "storage_id",
        "storageID",
        "StorageId",
        "storageid",
        "alternative_storage",
        "AlternativeStorage",
        "storage_alias",
        "StorageAlias",
    ]
    clauses: list[str] = []
    for col in candidates:
        if col in columns:
            clauses.append(f'lower(trim("{col}")) = lower(:storage_id)')
    return " OR ".join(clauses)


# Graph-mode default configuration for Test Computer Analytics. This is kept
# intentionally simple and JSON-friendly so it can be edited from the Admin UI
# without migrations. All fields are optional; when missing we fall back to
# safe defaults in the analytics endpoint.
DEFAULT_COMPUTER_ANALYTICS_GRAPH: dict[str, Any] = {
    "nodes": {
        "buying": {
            "label": "Buying",
            # Use the canonical Supabase mirror for VB buying records
            "table": "tbl_ebay_buyer",
            "storageColumns": ["storage"],
            "emit": {"storage": ["storage"]},
        },
        "inventory_legacy": {
            "label": "Legacy Inventory (tbl_parts_inventory)",
            "table": "tbl_parts_inventory",
            "storageColumns": ["Storage", "AlternativeStorage", "StorageAlias"],
            "skuColumns": ["SKU", "OverrideSKU"],
        },
        "inventory": {
            "label": "Inventory (modern)",
            "table": "inventory",
            "storageColumns": ["storage_id", "storage"],
            "skuColumns": ["sku"],
        },
        "transactions": {
            "label": "Sales Transactions",
            "table": "transactions",
            "matchFrom": {
                "sku": ["sku"],
            },
            "emit": {
                "order_id": ["order_id"],
                "transaction_id": ["transaction_id"],
                "line_item_id": ["line_item_id"],
            },
        },
        "finances_transactions": {
            "label": "Finances Transactions",
            "table": "ebay_finances_transactions",
            "matchFrom": {
                "order_id": ["order_id"],
                "line_item_id": ["order_line_item_id"],
            },
            "emit": {
                "transaction_id": ["transaction_id"],
                "order_id": ["order_id"],
            },
        },
        "returns_refunds": {
            "label": "Returns / Refunds",
            "table": "ebay_returns",
            "matchFrom": {
                "order_id": ["order_id"],
                "transaction_id": ["transaction_id"],
            },
        },
    },
    "order": [
        "buying",
        "inventory_legacy",
        "inventory",
        "transactions",
        "finances_transactions",
        "returns_refunds",
    ],
}


@router.get("/debug/environment")
async def debug_environment(db: Session = Depends(get_db)):
    """Debug endpoint to check environment configuration.
    
    This helps diagnose 401 errors by showing:
    - Current EBAY_ENVIRONMENT setting
    - Hash of JWT_SECRET (for verifying key consistency)
    - Token decryption test results
    """
    import hashlib
    from app.utils import crypto
    
    # Hash the secret key (never expose the actual key!)
    secret_key_hash = hashlib.sha256(settings.secret_key.encode()).hexdigest()[:16]
    
    # Test token decryption on first active account
    test_result = {"account": None, "decryption_works": None, "error": None}
    try:
        account = db.query(EbayAccount).filter(EbayAccount.is_active == True).first()
        if account:
            token = db.query(EbayToken).filter(EbayToken.ebay_account_id == account.id).first()
            if token and token._access_token:
                raw = token._access_token
                is_encrypted = raw.startswith("ENC:v1:") if raw else False
                decrypted = crypto.decrypt(raw) if raw else None
                decryption_works = decrypted and not decrypted.startswith("ENC:v1:") if is_encrypted else True
                
                test_result = {
                    "account": account.house_name,
                    "token_is_encrypted": is_encrypted,
                    "decryption_works": decryption_works,
                    "decrypted_prefix": decrypted[:20] + "..." if decrypted else None,
                    "token_hash": hashlib.sha256(decrypted.encode()).hexdigest()[:16] if decrypted else None,
                }
    except Exception as e:
        test_result["error"] = str(e)
    
    return {
        "EBAY_ENVIRONMENT": settings.EBAY_ENVIRONMENT,
        "secret_key_hash": secret_key_hash,
        "ebay_api_base_url": settings.ebay_api_base_url,
        "ebay_finances_base_url": settings.ebay_finances_base_url,
        "token_decryption_test": test_result,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }

# Default logical containers and their physical table names for Test Computer Analytics.
COMPUTER_ANALYTICS_DEFAULT_SOURCES: dict[str, dict[str, str]] = {
    # Default BUYING source points to the Supabase mirror table
    "root_purchase": {"table": "tbl_ebay_buyer"},
    "inventory_legacy": {"table": "tbl_parts_inventory"},
    "inventory": {"table": "inventory"},
    "transactions": {"table": "transactions"},
    "finances_transactions": {"table": "ebay_finances_transactions"},
    "finances_fees": {"table": "ebay_finances_fees"},
    # Configurable containers for invoices and returns/refunds.
    "invoices": {"table": "cvfii"},
    "returns_refunds": {"table": "ebay_returns"},
}


# Human-friendly metadata for each logical analytics container. Used by the
# frontend settings UI and for documentation in the "i" modal.
COMPUTER_ANALYTICS_CONTAINER_META: dict[str, dict[str, str]] = {
    "root_purchase": {
        "label": "VB / BUYING",
        "description": "Original computer purchase row (VB / buying) identified by storage.",
    },
    "inventory_legacy": {
        "label": "Legacy Inventory (tbl_parts_inventory)",
        "description": "Legacy parts inventory rows from tbl_parts_inventory linked by Storage / AlternativeStorage / StorageAlias.",
    },
    "inventory": {
        "label": "Inventory (modern)",
        "description": "Modern inventory + parts_detail rows born from this computer (linked by storage_id / storage).",
    },
    "transactions": {
        "label": "Sales Transactions",
        "description": "Sales history (transactions) for SKUs originating from this computer.",
    },
    "finances_transactions": {
        "label": "Finances Transactions",
        "description": "Sell Finances API ledger entries (ebay_finances_transactions) for related orders/line items.",
    },
    "finances_fees": {
        "label": "Finances Fees",
        "description": "Detailed fee lines (ebay_finances_fees) for those finances transactions.",
    },
    "invoices": {
        "label": "Invoices (CVFII)",
        "description": "Accounting invoices table or view (CVFII-style) linked by storage or order_id.",
    },
    "returns_refunds": {
        "label": "Returns / Refunds",
        "description": "Post-order returns/refunds records (ebay_returns or compatible view) for the same orders/transactions.",
    },
}


def _load_computer_analytics_sources(db: Session) -> dict:
    """Load mapping of logical analytics containers to physical tables.

    The mapping is stored in ui_tweak_settings.settings["computerAnalyticsSources"],
    with safe defaults when no custom config is present.

    IMPORTANT: in environments where the ui_tweak_settings table does not yet
    exist (migration not applied), this helper MUST NOT raise an error. In that
    case we simply return the built-in defaults so the analytics endpoint keeps
    working everywhere.
    """
    from sqlalchemy.exc import ProgrammingError
    from ..models_sqlalchemy.models import UiTweakSettings

    # Defaults can be overridden via UiTweakSettings.
    defaults: dict[str, dict[str, str]] = COMPUTER_ANALYTICS_DEFAULT_SOURCES

    try:
        row = db.query(UiTweakSettings).order_by(UiTweakSettings.id.asc()).first()
    except ProgrammingError as exc:  # e.g. relation "ui_tweak_settings" does not exist
        msg = str(exc)
        if "ui_tweak_settings" in msg and "UndefinedTable" in msg:
            # Mirror behaviour of the dedicated /ui-tweak router: log and
            # gracefully fall back to defaults without breaking admin APIs.
            # IMPORTANT: rollback the current DB session because this error
            # leaves the transaction in an aborted state; otherwise all
            # subsequent queries in this request would fail with
            # "current transaction is aborted".
            try:
                db.rollback()
            except Exception:  # pragma: no cover - defensive
                pass
            logger.error(
                "ui_tweak_settings table is missing; Test Computer Analytics "
                "will use built-in defaults only. Apply migration "
                "ui_tweak_settings_20251121 to enable persistence.",
            )
            return defaults
        raise

    if not row or not row.settings:
        return defaults

    cfg = row.settings.get("computerAnalyticsSources") or {}

    merged: dict[str, dict[str, str]] = {k: v.copy() for k, v in defaults.items()}
    for key, val in cfg.items():
        if key in merged and isinstance(val, dict):
            table_name = val.get("table")
            if isinstance(table_name, str) and table_name:
                merged[key]["table"] = table_name

    return merged


def _safe_table_name(name: str) -> str:
    """Very small guard against accidental SQL injection in configurable table names.

    Admin-only feature, but we still restrict characters to identifiers,
    schema-qualified names, and optional quotes.
    """
    import re

    if not isinstance(name, str) or not name:
        raise HTTPException(status_code=400, detail="invalid_table_name")
    if not re.match(r'^[A-Za-z0-9_\.\"]+$', name):
        raise HTTPException(status_code=400, detail="invalid_table_name")
    return name


class ComputerAnalyticsSourceConfig(BaseModel):
    """Single logical container configuration for Test Computer Analytics."""

    table: str


class ComputerAnalyticsSourcesPayload(BaseModel):
    """Payload for reading/updating analytics container → table mapping."""

    sources: dict[str, ComputerAnalyticsSourceConfig]


# -------------------------------
# Graph-mode configuration helpers
# -------------------------------


def _load_computer_analytics_graph(db: Session) -> dict[str, Any]:
    """Load graph-mode analytics configuration from UiTweakSettings.

    If the underlying ``ui_tweak_settings`` table is missing or the graph
    config is not set, this falls back to DEFAULT_COMPUTER_ANALYTICS_GRAPH.
    """
    from sqlalchemy.exc import ProgrammingError
    from ..models_sqlalchemy.models import UiTweakSettings

    cfg: dict[str, Any] = DEFAULT_COMPUTER_ANALYTICS_GRAPH

    try:
        row = db.query(UiTweakSettings).order_by(UiTweakSettings.id.asc()).first()
    except ProgrammingError as exc:  # pragma: no cover - defensive
        msg = str(exc)
        if "ui_tweak_settings" in msg and "UndefinedTable" in msg:
            # Same behaviour as classic path: log and fallback to defaults.
            logger.error(
                "ui_tweak_settings table is missing; Test Computer Analytics "
                "(graph) will use built-in defaults only. Apply migration "
                "ui_tweak_settings_20251121 to enable persistence.",
            )
            return cfg
        raise

    if not row or not row.settings:
        return cfg

    raw = row.settings.get("computerAnalyticsGraph")
    if not isinstance(raw, dict):
        return cfg

    # Shallow-merge nodes/order so that we always have the core defaults and
    # only override user-provided pieces.
    merged: dict[str, Any] = {
        "nodes": {**DEFAULT_COMPUTER_ANALYTICS_GRAPH.get("nodes", {}), **(raw.get("nodes") or {})},
        "order": raw.get("order") or DEFAULT_COMPUTER_ANALYTICS_GRAPH.get("order", []),
    }
    return merged


class ComputerAnalyticsGraphNodePayload(BaseModel):
    """Single node config for graph-mode analytics (JSON-friendly)."""

    label: Optional[str] = None
    table: Optional[str] = None
    storageColumns: Optional[list[str]] = None
    skuColumns: Optional[list[str]] = None
    matchFrom: Optional[dict[str, list[str]]] = None
    emit: Optional[dict[str, list[str]]] = None


class ComputerAnalyticsGraphPayload(BaseModel):
    """Payload for reading/updating computerAnalyticsGraph mapping."""

    nodes: dict[str, ComputerAnalyticsGraphNodePayload]
    order: Optional[list[str]] = None


@router.get("/test-computer-analytics/sources")
async def get_test_computer_analytics_sources(
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required),  # noqa: ARG001
):
    """Return effective container → table mapping for Test Computer Analytics.

    The response includes both the *current* table and the baked-in default
    table for each logical container, plus human-friendly labels and
    descriptions used by the Admin UI.
    """

    sources = _load_computer_analytics_sources(db)

    containers: list[dict[str, Any]] = []
    for key, cfg in sources.items():
        meta = COMPUTER_ANALYTICS_CONTAINER_META.get(key, {})
        default_cfg = COMPUTER_ANALYTICS_DEFAULT_SOURCES.get(key, {})
        containers.append(
            {
                "key": key,
                "table": cfg.get("table"),
                "default_table": default_cfg.get("table"),
                "label": meta.get("label", key),
                "description": meta.get("description", ""),
            }
        )

    return {"containers": containers}


@router.put("/test-computer-analytics/sources")
async def update_test_computer_analytics_sources(
    payload: ComputerAnalyticsSourcesPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required),  # noqa: ARG001
):
    """Update the container → table mapping for Test Computer Analytics.

    This endpoint only persists the subset of fields relevant to
    computerAnalyticsSources inside UiTweakSettings, leaving all other
    UITweak settings untouched.
    """
    from sqlalchemy.exc import ProgrammingError
    from ..models_sqlalchemy.models import UiTweakSettings

    try:
        row = db.query(UiTweakSettings).order_by(UiTweakSettings.id.asc()).first()
    except ProgrammingError as exc:  # pragma: no cover - defensive
        msg = str(exc)
        if "ui_tweak_settings" in msg and "UndefinedTable" in msg:
            raise HTTPException(
                status_code=503,
                detail=(
                    "ui_tweak_settings table is missing; apply the "
                    "ui_tweak_settings_20251121 migration before editing "
                    "computer analytics sources."
                ),
            )
        raise

    if row is None:
        row = UiTweakSettings(settings={})
        db.add(row)
        db.commit()
        db.refresh(row)

    settings_dict: dict[str, Any] = dict(row.settings or {})

    # Build a clean mapping with validated table names.
    new_sources: dict[str, dict[str, str]] = {}
    for key, cfg in payload.sources.items():
        if key not in COMPUTER_ANALYTICS_DEFAULT_SOURCES:
            # Ignore unknown container keys to keep config strict.
            continue
        table_name = _safe_table_name(cfg.table)
        new_sources[key] = {"table": table_name}

    settings_dict["computerAnalyticsSources"] = new_sources
    row.settings = settings_dict
    db.add(row)
    db.commit()
    db.refresh(row)

    # Return the same shape as the GET endpoint for convenience.
    merged = _load_computer_analytics_sources(db)
    containers: list[dict[str, Any]] = []
    for key, cfg in merged.items():
        meta = COMPUTER_ANALYTICS_CONTAINER_META.get(key, {})
        default_cfg = COMPUTER_ANALYTICS_DEFAULT_SOURCES.get(key, {})
        containers.append(
            {
                "key": key,
                "table": cfg.get("table"),
                "default_table": default_cfg.get("table"),
                "label": meta.get("label", key),
                "description": meta.get("description", ""),
            }
        )

    return {"containers": containers}


# -------------------------------
# Graph-mode endpoints
# -------------------------------


@router.get("/test-computer-analytics-graph/sources")
async def get_test_computer_analytics_graph_sources(
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required),  # noqa: ARG001
):
    """Return graph-mode nodes/order configuration.

    This is a thin wrapper around the computerAnalyticsGraph setting with
    sensible defaults so that the Admin UI can edit it without migrations.
    """

    graph_cfg = _load_computer_analytics_graph(db)
    return graph_cfg


@router.put("/test-computer-analytics-graph/sources")
async def update_test_computer_analytics_graph_sources(
    payload: ComputerAnalyticsGraphPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required),  # noqa: ARG001
):
    """Update graph-mode nodes/order configuration.

    This stores the payload under ui_tweak_settings.settings["computerAnalyticsGraph"].
    Other UITweak settings remain untouched.
    """
    from sqlalchemy.exc import ProgrammingError
    from ..models_sqlalchemy.models import UiTweakSettings

    try:
        row = db.query(UiTweakSettings).order_by(UiTweakSettings.id.asc()).first()
    except ProgrammingError as exc:  # pragma: no cover - defensive
        msg = str(exc)
        if "ui_tweak_settings" in msg and "UndefinedTable" in msg:
            raise HTTPException(
                status_code=503,
                detail=(
                    "ui_tweak_settings table is missing; apply Alembic migration "
                    "ui_tweak_settings_20251121 before editing graph analytics sources."
                ),
            )
        raise

    if row is None:
        row = UiTweakSettings(settings={})
        db.add(row)
        db.commit()
        db.refresh(row)

    settings_dict: dict[str, Any] = dict(row.settings or {})

    # Persist exactly what the client sent (Pydantic already validated types).
    graph_payload = {
        "nodes": {k: v.dict(exclude_none=True) for k, v in payload.nodes.items()},
        "order": payload.order,
    }
    settings_dict["computerAnalyticsGraph"] = graph_payload
    row.settings = settings_dict
    db.add(row)
    db.commit()
    db.refresh(row)

    # Return the merged effective config so the UI sees defaults filled in.
    graph_cfg = _load_computer_analytics_graph(db)
    return graph_cfg


@router.get("/test-computer-analytics-graph")
async def get_test_computer_analytics_graph(
    storage_id: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required),
):
    """Graph-mode variant of Test Computer Analytics for a single computer.

    For the first version this endpoint reuses the classic analytics logic to
    compute the actual rows, but it also returns the effective graph
    configuration so the frontend can experiment with table/column linking
    without breaking the existing implementation.
    """

    # Reuse the classic implementation by calling the same code path. To avoid
    # duplication we keep the main logic in the classic handler and treat this
    # endpoint as a thin wrapper.
    classic_result = await get_test_computer_analytics(storage_id=storage_id, db=db, current_user=current_user)

    graph_cfg = _load_computer_analytics_graph(db)

    return {
        "storage_id": classic_result["storage_id"],
        "graph": graph_cfg,
        "containers": classic_result.get("containers", []),
        "sections": {
            "buying": classic_result.get("buying", []),
            "legacy_inventory": classic_result.get("legacy_inventory", []),
            "inventory": classic_result.get("inventory", []),
            "transactions": classic_result.get("transactions", []),
            "finances_transactions": classic_result.get("finances_transactions", []),
            "finances_fees": classic_result.get("finances_fees", []),
            "invoices": classic_result.get("invoices", []),
            "returns_refunds": classic_result.get("returns_refunds", []),
        },
    }


@router.get("/test-computer-analytics")
async def get_test_computer_analytics(
    storage_id: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required),
):
    """Experimental analytics endpoint for a single computer by Storage ID.

    Given a Storage ID from buying.storage (e.g. A127 / A331), this endpoint
    returns a compact JSON tree grouped into logical containers:
    - root purchase (VB / BUYING)
    - inventory (legacy + modern)
    - sales transactions
    - finances transactions & fees
    - placeholders for invoices and returns/refunds

    The physical tables used for each container can be overridden via
    ui_tweak_settings.settings["computerAnalyticsSources"].
    """
    from sqlalchemy import text as sa_text, inspect as sa_inspect
    from datetime import datetime as dt_type
    from decimal import Decimal

    sources = _load_computer_analytics_sources(db)

    buying_table = _safe_table_name(sources["root_purchase"]["table"])
    inv_legacy_table = _safe_table_name(sources["inventory_legacy"]["table"])
    inv_table = _safe_table_name(sources["inventory"]["table"])
    tx_table = _safe_table_name(sources["transactions"]["table"])
    fin_tx_table = _safe_table_name(sources["finances_transactions"]["table"])
    fin_fee_table = _safe_table_name(sources["finances_fees"]["table"])

    # Determine whether the legacy inventory mirror table is present. When it
    # exists, we include its SKUs (and OverrideSKU) into the analytics chain so
    # that environments which have not fully migrated to the modern inventory
    # model still see transactions/finances linked correctly.
    has_legacy_inventory = False
    try:
        inspector = sa_inspect(db.bind)
        has_legacy_inventory = inv_legacy_table in inspector.get_table_names()
    except Exception:  # pragma: no cover - defensive fallback
        has_legacy_inventory = False

    # Resolve buying storage columns dynamically (accounts for case-sensitive columns)
    try:
        inspector = sa_inspect(db.bind)
        buying_columns = {col["name"] for col in inspector.get_columns(buying_table)}
    except Exception:  # pragma: no cover - defensive
        buying_columns = set()
    buying_where = _build_storage_where(buying_columns)
    if not buying_where:
        logger.error("No storage-like columns found in %s; returning empty buying set", buying_table)
        buying_where = "1 = 0"

    legacy_sku_union = ""
    if has_legacy_inventory:
        legacy_sku_union = f"""
          UNION
          SELECT DISTINCT CAST(pi.\"SKU\" AS text) AS sku
          FROM {inv_legacy_table} pi
          WHERE (lower(trim(pi.\"Storage\")) = lower(:storage_id)
                 OR lower(trim(pi.\"AlternativeStorage\")) = lower(:storage_id)
                 OR lower(trim(pi.\"StorageAlias\")) = lower(:storage_id))
          UNION
          SELECT DISTINCT CAST(pi.\"OverrideSKU\" AS text) AS sku
          FROM {inv_legacy_table} pi
          WHERE (lower(trim(pi.\"Storage\")) = lower(:storage_id)
                 OR lower(trim(pi.\"AlternativeStorage\")) = lower(:storage_id)
                 OR lower(trim(pi.\"StorageAlias\")) = lower(:storage_id))
            AND pi.\"OverrideSKU\" IS NOT NULL
        """

    norm_storage = storage_id.strip()

    def _normalize_row(row: dict) -> dict:
        out: dict = {}
        for k, v in row.items():
            if isinstance(v, dt_type):
                out[k] = v.isoformat()
            elif isinstance(v, Decimal):
                out[k] = float(v)
            else:
                out[k] = v
        return out

    result: dict = {"storage_id": norm_storage}

    # 1) Root purchase (BUYING / VB)
    sql_buying = sa_text(f"SELECT * FROM {buying_table} WHERE {buying_where}")
    buying_rows = db.execute(sql_buying, {"storage_id": norm_storage}).mappings().all()
    result["buying"] = [_normalize_row(dict(r)) for r in buying_rows]

    # 2) Legacy parts inventory (tbl_parts_inventory)
    try:
        sql_legacy_inv = sa_text(
            f"""
            SELECT *
            FROM {inv_legacy_table}
            WHERE lower(trim("Storage")) = lower(:storage_id)
               OR lower(trim("AlternativeStorage")) = lower(:storage_id)
               OR lower(trim("StorageAlias")) = lower(:storage_id)
            """
        )
        legacy_inv_rows = db.execute(sql_legacy_inv, {"storage_id": norm_storage}).mappings().all()
        result["legacy_inventory"] = [_normalize_row(dict(r)) for r in legacy_inv_rows]
    except Exception:
        # Legacy MSSQL/Supabase mirror may be absent in some environments
        result["legacy_inventory"] = []

    # 3) Modern inventory + parts_detail for this storage
    sql_inv_pd = sa_text(
        f"""
        SELECT
          i.id                AS inventory_id,
          i.storage_id,
          i.storage,
          i.status,
          i.category,
          i.quantity,
          i.price_value,
          i.price_currency,
          i.ebay_listing_id,
          i.parts_detail_id,
          pd.sku,
          pd.item_id         AS parts_item_id,
          pd.storage         AS parts_storage
        FROM {inv_table} i
        LEFT JOIN parts_detail pd
          ON pd.id = i.parts_detail_id
        WHERE lower(trim(i.storage_id)) = lower(:storage_id)
           OR lower(trim(i.storage))    = lower(:storage_id)
        """
    )
    inv_pd_rows = db.execute(sql_inv_pd, {"storage_id": norm_storage}).mappings().all()
    result["inventory"] = [_normalize_row(dict(r)) for r in inv_pd_rows]

    # 4) Transactions for SKUs originating from this storage
    sql_tx = sa_text(
        f"""
        WITH inv AS (
          SELECT DISTINCT pd.sku
          FROM {inv_table} i
          JOIN parts_detail pd ON pd.id = i.parts_detail_id
          WHERE (lower(trim(i.storage_id)) = lower(:storage_id)
                 OR lower(trim(i.storage)) = lower(:storage_id))
            AND pd.sku IS NOT NULL
          {legacy_sku_union}
        )
        SELECT t.*
        FROM {tx_table} t
        WHERE t.sku IN (SELECT sku FROM inv)
        """
    )
    tx_rows = db.execute(sql_tx, {"storage_id": norm_storage}).mappings().all()
    result["transactions"] = [_normalize_row(dict(r)) for r in tx_rows]

    # 5) Finances transactions (Sell Finances API) linked via order_id/line_item_id
    sql_fin_tx = sa_text(
        f"""
        WITH inv AS (
          SELECT DISTINCT pd.sku
          FROM {inv_table} i
          JOIN parts_detail pd ON pd.id = i.parts_detail_id
          WHERE (lower(trim(i.storage_id)) = lower(:storage_id)
                 OR lower(trim(i.storage)) = lower(:storage_id))
            AND pd.sku IS NOT NULL
          {legacy_sku_union}
        ),
        tx AS (
          SELECT DISTINCT t.order_id, t.line_item_id
          FROM {tx_table} t
          JOIN inv ON inv.sku = t.sku
        )
        SELECT eft.*
        FROM {fin_tx_table} eft
        WHERE (eft.order_id IS NOT NULL AND eft.order_id IN (SELECT order_id FROM tx))
           OR (eft.order_line_item_id IS NOT NULL AND eft.order_line_item_id IN (SELECT line_item_id FROM tx))
        """
    )
    fin_tx_rows = db.execute(sql_fin_tx, {"storage_id": norm_storage}).mappings().all()
    result["finances_transactions"] = [_normalize_row(dict(r)) for r in fin_tx_rows]

    # 6) Finances fees for those transactions
    sql_fin_fees = sa_text(
        f"""
        WITH inv AS (
          SELECT DISTINCT pd.sku
          FROM {inv_table} i
          JOIN parts_detail pd ON pd.id = i.parts_detail_id
          WHERE (lower(trim(i.storage_id)) = lower(:storage_id)
                 OR lower(trim(i.storage)) = lower(:storage_id))
            AND pd.sku IS NOT NULL
          {legacy_sku_union}
        ),
        tx AS (
          SELECT DISTINCT t.order_id, t.line_item_id, t.transaction_id
          FROM {tx_table} t
          JOIN inv ON inv.sku = t.sku
        ),
        fin AS (
          SELECT DISTINCT transaction_id
          FROM {fin_tx_table} eft
          WHERE (eft.order_id IS NOT NULL AND eft.order_id IN (SELECT order_id FROM tx))
             OR (eft.order_line_item_id IS NOT NULL AND eft.order_line_item_id IN (SELECT line_item_id FROM tx))
        )
        SELECT eff.*
        FROM {fin_fee_table} eff
        WHERE eff.transaction_id IN (SELECT transaction_id FROM fin)
        """
    )
    fin_fee_rows = db.execute(sql_fin_fees, {"storage_id": norm_storage}).mappings().all()
    result["finances_fees"] = [_normalize_row(dict(r)) for r in fin_fee_rows]

    # 7) Invoices (generic CVFII-like table, configurable)
    invoices_rows: list[dict] = []
    try:
        from sqlalchemy import inspect as sa_inspect

        invoices_table = _safe_table_name(sources["invoices"]["table"])
        inspector = sa_inspect(db.bind)
        cols = {c["name"] for c in inspector.get_columns(invoices_table)}

        where_clauses = []
        params = {"storage_id": norm_storage}

        # Prefer direct storage-based filter if table supports it
        if "storage_id" in cols:
            where_clauses.append("lower(trim(storage_id)) = lower(:storage_id)")
        if "storage" in cols:
            where_clauses.append("lower(trim(storage)) = lower(:storage_id)")

        # Fallback: filter by order_id using the same tx CTE we used above
        # (only if table has order_id column).
        if "order_id" in cols:
            where_clauses.append(
                "order_id IN (SELECT DISTINCT t.order_id FROM "
                f"{tx_table} t JOIN (SELECT DISTINCT pd.sku FROM {inv_table} i "
                "JOIN parts_detail pd ON pd.id = i.parts_detail_id "
                "WHERE (lower(trim(i.storage_id)) = lower(:storage_id) "
                "OR lower(trim(i.storage)) = lower(:storage_id)) AND pd.sku IS NOT NULL) inv "
                "ON inv.sku = t.sku)"
            )

        if where_clauses:
            where_sql = " OR ".join(f"({w})" for w in where_clauses)
            sql_invoices = sa_text(
                f"""
                SELECT *
                FROM {invoices_table}
                WHERE {where_sql}
                """
            )
            invoices_rows = [
                _normalize_row(dict(r))
                for r in db.execute(sql_invoices, params).mappings().all()
            ]
    except Exception:
        invoices_rows = []

    result["invoices"] = invoices_rows

    # 8) Returns & refunds (ebay_returns by default, configurable)
    returns_rows: list[dict] = []
    try:
        returns_table = _safe_table_name(sources["returns_refunds"]["table"])

        sql_returns = sa_text(
            f"""
            WITH inv AS (
              SELECT DISTINCT pd.sku
              FROM {inv_table} i
              JOIN parts_detail pd ON pd.id = i.parts_detail_id
              WHERE (lower(trim(i.storage_id)) = lower(:storage_id)
                     OR lower(trim(i.storage)) = lower(:storage_id))
                AND pd.sku IS NOT NULL
              {legacy_sku_union}
            ),
            tx AS (
              SELECT DISTINCT t.order_id, t.transaction_id
              FROM {tx_table} t
              JOIN inv ON inv.sku = t.sku
            ),
            fin AS (
              SELECT DISTINCT transaction_id, order_id
              FROM {fin_tx_table} eft
              WHERE (eft.order_id IS NOT NULL AND eft.order_id IN (SELECT order_id FROM tx))
                 OR (eft.transaction_id IS NOT NULL AND eft.transaction_id IN (SELECT transaction_id FROM tx))
            )
            SELECT r.*
            FROM {returns_table} r
            WHERE (r.order_id IS NOT NULL AND r.order_id IN (
                     SELECT order_id FROM tx
                     UNION
                     SELECT order_id FROM fin
                   ))
               OR (r.transaction_id IS NOT NULL AND r.transaction_id IN (
                     SELECT transaction_id FROM tx
                     UNION
                     SELECT transaction_id FROM fin
                   ))
            """
        )
        returns_rows = [
            _normalize_row(dict(r))
            for r in db.execute(sql_returns, {"storage_id": norm_storage}).mappings().all()
        ]
    except Exception:
        returns_rows = []

    result["returns_refunds"] = returns_rows

    # High-level containers description for UI
    result["containers"] = [
        {
            "key": "root_purchase",
            "label": "VB / BUYING",
            "table": sources["root_purchase"]["table"],
            "rows_key": "buying",
            "rows": result.get("buying", []),
        },
        {
            "key": "inventory_legacy",
            "label": "Legacy Inventory (tbl_parts_inventory)",
            "table": sources["inventory_legacy"]["table"],
            "rows_key": "legacy_inventory",
            "rows": result.get("legacy_inventory", []),
        },
        {
            "key": "inventory",
            "label": "Inventory (modern)",
            "table": sources["inventory"]["table"],
            "rows_key": "inventory",
            "rows": result.get("inventory", []),
        },
        {
            "key": "transactions",
            "label": "Sales Transactions",
            "table": sources["transactions"]["table"],
            "rows_key": "transactions",
            "rows": result.get("transactions", []),
        },
        {
            "key": "finances_transactions",
            "label": "Finances Transactions",
            "table": sources["finances_transactions"]["table"],
            "rows_key": "finances_transactions",
            "rows": result.get("finances_transactions", []),
        },
        {
            "key": "finances_fees",
            "label": "Finances Fees",
            "table": sources["finances_fees"]["table"],
            "rows_key": "finances_fees",
            "rows": result.get("finances_fees", []),
        },
        {
            "key": "invoices",
            "label": "Invoices (CVFII)",
            "table": sources["invoices"]["table"],
            "rows_key": "invoices",
            "rows": result.get("invoices", []),
        },
        {
            "key": "returns_refunds",
            "label": "Returns / Refunds",
            "table": sources["returns_refunds"]["table"],
            "rows_key": "returns_refunds",
            "rows": result.get("returns_refunds", []),
        },
    ]

    return result


class TokenRefreshDebugRequest(BaseModel):
    """Request body for /ebay/token/refresh-debug.

    We keep this minimal on purpose: the endpoint derives everything else from
    the account + DB state so that it always uses the same refresh token and
    environment as the background worker.
    """

    ebay_account_id: str


class InternalTokenRefreshRequest(BaseModel):
    """Request body for /internal/refresh-tokens."""
    internal_api_key: str


@router.post("/internal/refresh-tokens")
async def internal_refresh_tokens(
    payload: InternalTokenRefreshRequest,
    db: Session = Depends(get_db),
):
    """Internal endpoint for the worker to trigger token refresh.
    
    This allows the worker to delegate the actual refresh logic to the Web App,
    which can successfully decrypt tokens. The worker acts as a scheduler only.
    
    Authentication: Requires a shared INTERNAL_API_KEY (set in Railway vars).
    """
    expected_key = os.getenv("INTERNAL_API_KEY", "")
    if not expected_key or payload.internal_api_key != expected_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_internal_api_key"
        )
    
    try:
        # Use the shared service logic.
        # capture_http=True ensures logs appear in the terminal.
        result = await run_token_refresh_job(
            db,
            force_all=False,
            capture_http=True,
            triggered_by="scheduled_proxy"
        )
        return {
            "success": True,
            "refreshed_count": result.get("accounts_refreshed", 0),
            "failed_count": len(result.get("errors", [])),
        }
    except Exception as e:
        logger.error(f"Internal token refresh failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"refresh_failed: {str(e)}"
        )


@router.post("/internal/run-ebay-workers")
async def internal_run_ebay_workers(
    payload: InternalTokenRefreshRequest,
    db: Session = Depends(get_db),
):
    """Internal endpoint for the worker to trigger the main eBay workers loop.
    
    This uses the SAME code path as the manual "Run Now" button to ensure
    consistent behavior between manual and automatic runs.
    """
    expected_key = os.getenv("INTERNAL_API_KEY", "")
    if not expected_key or payload.internal_api_key != expected_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_internal_api_key"
        )
    
    # Import worker functions - same as manual "Run Now" endpoint
    from app.services.ebay_workers.orders_worker import run_orders_worker_for_account
    from app.services.ebay_workers.transactions_worker import run_transactions_worker_for_account
    from app.services.ebay_workers.offers_worker import run_offers_worker_for_account
    from app.services.ebay_workers.messages_worker import run_messages_worker_for_account
    from app.services.ebay_workers.active_inventory_worker import run_active_inventory_worker_for_account
    from app.services.ebay_workers.cases_worker import run_cases_worker_for_account
    from app.services.ebay_workers.finances_worker import run_finances_worker_for_account
    from app.services.ebay_workers.purchases_worker import run_purchases_worker_for_account
    from app.services.ebay_workers.inquiries_worker import run_inquiries_worker_for_account
    from app.services.ebay_workers.returns_worker import run_returns_worker_for_account
    from app.services.ebay_workers.state import are_workers_globally_enabled, get_or_create_sync_state
    from app.models_sqlalchemy.ebay_workers import EbaySyncState
    from app.services.ebay_token_refresh_service import run_token_refresh_job
    
    try:
        logger.info("Internal trigger: Running workers via manual code path...")
        
        # 1. Refresh tokens first (same as old scheduler)
        await run_token_refresh_job(db, triggered_by="internal_scheduler")
        
        # 2. Check if workers are globally enabled
        if not are_workers_globally_enabled(db):
            logger.info("Workers globally disabled - skipping")
            return {"status": "skipped", "reason": "workers_disabled"}
        
        # 3. Get all active accounts
        accounts = db.query(EbayAccount).filter(EbayAccount.is_active == True).all()
        if not accounts:
            logger.info("No active accounts found")
            return {"status": "ok", "accounts_processed": 0}
        
        results = []
        
        # 4. Run workers for each account using the SAME pattern as manual "Run Now"
        for account in accounts:
            account_id = account.id
            account_results = {"account_id": account_id, "house_name": account.house_name, "workers": []}
            
            # Map of API families to worker functions
            worker_map = {
                "orders": run_orders_worker_for_account,
                "transactions": run_transactions_worker_for_account,
                "offers": run_offers_worker_for_account,
                "messages": run_messages_worker_for_account,
                "active_inventory": run_active_inventory_worker_for_account,
                "buyer": run_purchases_worker_for_account,
                "cases": run_cases_worker_for_account,
                "inquiries": run_inquiries_worker_for_account,
                "finances": run_finances_worker_for_account,
                "returns": run_returns_worker_for_account,
            }
            
            for api_family, worker_func in worker_map.items():
                # Check if this worker is enabled for this account
                state = db.query(EbaySyncState).filter(
                    EbaySyncState.ebay_account_id == account_id,
                    EbaySyncState.api_family == api_family,
                ).first()
                
                if not state or not state.enabled:
                    continue
                
                try:
                    # Call worker with triggered_by="scheduler" - same as manual but marked as scheduler
                    # Using "manual" here to match the exact code path that works
                    run_id = await worker_func(account_id, triggered_by="manual")
                    account_results["workers"].append({
                        "api_family": api_family,
                        "status": "started" if run_id else "skipped",
                        "run_id": run_id,
                    })
                except Exception as e:
                    logger.error(f"Worker {api_family} failed for account {account_id}: {e}")
                    account_results["workers"].append({
                        "api_family": api_family,
                        "status": "error",
                        "error": str(e)[:100],
                    })
            
            results.append(account_results)
        
        return {"status": "ok", "accounts_processed": len(accounts), "results": results}
        
    except Exception as e:
        logger.error(f"Internal workers run failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"run_failed: {str(e)}"
        )

class InternalTransactionsRunOnceRequest(BaseModel):
    """Request body for /internal/workers/transactions/run-once."""
    internal_api_key: str
    account_id: Optional[str] = None  # Optional: run for specific account only


@router.post("/internal/workers/transactions/run-once")
async def internal_transactions_run_once(
    payload: InternalTransactionsRunOnceRequest,
    db: Session = Depends(get_db),
):
    """Internal endpoint for the Railway worker to trigger Transactions sync.
    
    This is the SINGLE entry point for automatic Transactions worker runs.
    It uses exactly the same code path as manual "Run Now" to ensure
    consistent token handling and API calls.
    
    Authentication: Requires INTERNAL_API_KEY header/body.
    
    Request body:
        - internal_api_key: Required for authentication
        - account_id: Optional - if provided, runs for that account only;
                      otherwise runs for ALL active accounts with transactions enabled
    
    Response:
        - status: "ok", "skipped", "error"
        - correlation_id: Unique ID for this run batch
        - accounts_processed, accounts_succeeded, accounts_failed, accounts_skipped
        - details: Per-account status information
        - started_at, finished_at, duration_ms
    """
    expected_key = os.getenv("INTERNAL_API_KEY", "")
    if not expected_key or payload.internal_api_key != expected_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_internal_api_key"
        )
    
    from app.services.ebay_workers.transactions_worker import (
        run_transactions_sync_for_all_accounts,
        run_transactions_worker_for_account,
    )
    
    try:
        if payload.account_id:
            # Run for a specific account only
            logger.info(
                "[internal_transactions] Running for single account=%s",
                payload.account_id
            )
            run_id = await run_transactions_worker_for_account(
                payload.account_id,
                triggered_by="internal_scheduler",
            )
            return {
                "status": "ok" if run_id else "skipped",
                "account_id": payload.account_id,
                "run_id": run_id,
                "reason": None if run_id else "already_running_or_disabled",
            }
        else:
            # Run for ALL accounts
            logger.info("[internal_transactions] Running for all accounts...")
            result = await run_transactions_sync_for_all_accounts(
                triggered_by="internal_scheduler"
            )
            return result
            
    except Exception as e:
        logger.error(
            "[internal_transactions] Error running transactions sync: %s",
            str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"transactions_sync_failed: {str(e)[:200]}"
        )


class InternalSyncOffersRequest(BaseModel):
    """Request body for /internal/sync-offers."""
    internal_api_key: str
    account_id: Optional[str] = None
    limit_per_run: Optional[int] = 100


@router.post("/internal/sync-offers")
async def internal_sync_offers(
    payload: InternalSyncOffersRequest,
    db: Session = Depends(get_db),
):
    """Internal endpoint to trigger offers sync.
    
    Authentication: Requires a shared INTERNAL_API_KEY.
    """
    expected_key = os.getenv("INTERNAL_API_KEY", "")
    if not expected_key or payload.internal_api_key != expected_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_internal_api_key"
        )
    
    from app.services.ebay_offers_service import ebay_offers_service
    
    query = db.query(EbayAccount).filter(EbayAccount.is_active == True)
    if payload.account_id:
        query = query.filter(EbayAccount.id == payload.account_id)
    
    accounts = query.all()
    results = {}
    
    for account in accounts:
        logger.info(f"Syncing offers for account {account.id} ({account.house_name})")
        stats = await ebay_offers_service.sync_offers_for_account(db, account)
        results[account.id] = stats
        
    return {"status": "ok", "results": results}


class InternalAccessTokenRequest(BaseModel):
    """Request body for /internal/ebay/accounts/{account_id}/access-token."""
    internal_api_key: str
    api_family: Optional[str] = None
    force_refresh: bool = False
    validate_with_identity_api: bool = False


@router.post("/internal/test-fetch-token")
async def internal_test_fetch_active_token(
    payload: dict,
    db: Session = Depends(get_db),
):
    """Test endpoint for fetch_active_ebay_token function.
    
    This endpoint allows testing the fetch_active_ebay_token function
    to verify token decryption works correctly.
    
    Authentication: Requires INTERNAL_API_KEY.
    
    Request body:
        {
            "internal_api_key": "your-internal-api-key",
            "ebay_account_id": "uuid-of-ebay-account",
            "triggered_by": "test" (optional),
            "api_family": "transactions" (optional)
        }
    
    Returns:
        {
            "success": true/false,
            "token_received": true/false,
            "token_prefix": "v^1.1#..." or "ENC:v1:..." (first 20 chars),
            "token_is_decrypted": true/false,
            "token_hash": "hash...",
            "error": "error message" (if failed)
        }
    """
    expected_key = os.getenv("INTERNAL_API_KEY", "")
    if not expected_key or payload.get("internal_api_key") != expected_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing INTERNAL_API_KEY",
        )
    
    ebay_account_id = payload.get("ebay_account_id")
    if not ebay_account_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ebay_account_id is required",
        )
    
    triggered_by = payload.get("triggered_by", "test")
    api_family = payload.get("api_family", "test")
    
    try:
        from app.services.ebay_token_fetcher import fetch_active_ebay_token
        from app.utils.build_info import get_build_number
        
        build_number = get_build_number()
        
        token = await fetch_active_ebay_token(
            db,
            ebay_account_id,
            triggered_by=triggered_by,
            api_family=api_family,
        )
        
        if not token:
            return {
                "success": False,
                "token_received": False,
                "token_prefix": None,
                "token_is_decrypted": False,
                "token_hash": None,
                "error": "fetch_active_ebay_token returned None - check logs for details",
                "build_number": build_number,
            }
        
        token_is_decrypted = not token.startswith("ENC:")
        token_hash = None
        if token:
            import hashlib
            token_hash = hashlib.sha256(token.encode()).hexdigest()[:12]
        
        return {
            "success": True,
            "token_received": True,
            "token_prefix": token[:20] + "..." if token else None,
            "token_is_decrypted": token_is_decrypted,
            "token_hash": token_hash,
            "error": None,
            "build_number": build_number,
        }
    except Exception as e:
        logger.error(f"Error testing fetch_active_ebay_token: {e}", exc_info=True)
        return {
            "success": False,
            "token_received": False,
            "token_prefix": None,
            "token_is_decrypted": False,
            "token_hash": None,
            "error": str(e),
            "build_number": get_build_number(),
        }


@router.post("/internal/ebay/accounts/{account_id}/access-token")
async def internal_get_ebay_access_token(
    account_id: str,
    payload: InternalAccessTokenRequest,
    db: Session = Depends(get_db),
):
    """Internal endpoint for workers to obtain a valid eBay access token.
    
    This is the single source of truth for all eBay workers (both manual "Run now"
    and background scheduler) to get tokens. It uses the unified EbayTokenProvider
    to ensure consistent token handling:
    
    1. Loads token from DB
    2. Checks expiry (refreshes if near expiry or force_refresh=True)
    3. Optionally validates via Identity API
    4. Returns a ready-to-use access token
    
    Authentication: Requires INTERNAL_API_KEY.
    
    Request body:
        - internal_api_key: Required for authentication
        - api_family: Optional label for logging (e.g., "transactions", "orders")
        - force_refresh: If True, refresh token even if not near expiry
        - validate_with_identity_api: If True, validate token via eBay Identity API
    
    Response (success):
        - success: true
        - access_token: The valid access token (masked in logs, full in response)
        - environment: "production" or "sandbox"
        - expires_at: ISO timestamp when token expires
        - source: "existing" or "refreshed"
        - token_hash: SHA256 hash prefix for debugging
        - account_id, ebay_user_id: Account identifiers
    
    Response (failure):
        - success: false
        - error_code: Short error code
        - error_message: Human-readable error description
    """
    expected_key = os.getenv("INTERNAL_API_KEY", "")
    if not expected_key or payload.internal_api_key != expected_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_internal_api_key"
        )
    
    from app.services.ebay_token_provider import get_valid_access_token
    
    result = await get_valid_access_token(
        db,
        account_id,
        api_family=payload.api_family,
        force_refresh=payload.force_refresh,
        validate_with_identity_api=payload.validate_with_identity_api,
        triggered_by="internal_api",
    )
    
    if not result.success:
        # Return 200 with structured error (not 4xx) so caller can handle gracefully
        return {
            "success": False,
            "error_code": result.error_code,
            "error_message": result.error_message,
            "account_id": result.account_id,
            "ebay_user_id": result.ebay_user_id,
            "environment": result.environment,
        }
    
    return {
        "success": True,
        "access_token": result.access_token,
        "environment": result.environment,
        "expires_at": result.expires_at.isoformat() if result.expires_at else None,
        "source": result.source,
        "token_db_id": result.token_db_id,
        "token_hash": result.token_hash,
        "account_id": result.account_id,
        "ebay_user_id": result.ebay_user_id,
        "api_family": payload.api_family,
    }


@router.get("/notifications/status")
async def get_notifications_status(
    current_user: User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    """Public wrapper for notifications status that never raises.

    Any internal error is converted into an ``ok=False`` response with an
    appropriate ``state`` and ``errorSummary`` so the UI never sees a raw 500.
    """

    env = settings.EBAY_ENVIRONMENT
    endpoint_url = settings.EBAY_NOTIFICATION_DESTINATION_URL
    checked_at = datetime.now(timezone.utc).isoformat()

    try:
        # Delegate to the core implementation which already handles most
        # Notification API and configuration errors in a structured way.
        return await _get_notifications_status_inner(current_user=current_user, db=db)
    except HTTPException as http_exc:
        # Do not propagate HTTPException status codes to the client; always
        # respond with HTTP 200 and a clear diagnostic payload.
        logger.warning(
            "Notifications status HTTPException in wrapper: %s",
            getattr(http_exc, "detail", http_exc),
        )
        detail = getattr(http_exc, "detail", None)
        message = str(detail) if detail else "Notification API error"
        return {
            "ok": False,
            "environment": env,
            "webhookUrl": endpoint_url,
            "state": "notification_api_error",
            "reason": message,
            "errorSummary": f"notification_api_error: {message}",
            "destination": None,
            "subscription": None,
            "destinationId": None,
            "subscriptionId": None,
            "destinationStatus": None,
            "subscriptionStatus": None,
            "verificationStatus": None,
            "recentEvents": {"count": 0, "lastEventTime": None},
            "checkedAt": checked_at,
            "account": None,
            "topics": [],
        }
    except Exception as exc:  # pragma: no cover - last-resort safety net
        logger.exception("Unexpected error in /api/admin/notifications/status wrapper")
        message = str(exc)
        return {
            "ok": False,
            "environment": env,
            "webhookUrl": endpoint_url,
            "state": "internal_error",
            "reason": message,
            "errorSummary": f"internal_error: {type(exc).__name__}: {message}",
            "destination": None,
            "subscription": None,
            "destinationId": None,
            "subscriptionId": None,
            "destinationStatus": None,
            "subscriptionStatus": None,
            "verificationStatus": None,
            "recentEvents": {"count": 0, "lastEventTime": None},
            "checkedAt": checked_at,
            "account": None,
            "topics": [],
        }

@router.post("/cases/sync")
async def admin_run_cases_sync_for_account(
    account_id: str = Query(..., description="eBay account id"),
    current_user: User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    """Run the Post-Order cases worker once for an account (admin-only).

    This wraps ``run_cases_worker_for_account`` so admins can trigger a cases
    sync directly from the Admin area and immediately see the resulting
    worker-run summary, including normalization statistics.
    """

    # Ensure the account belongs to the current org.
    account: Optional[EbayAccount] = (
        db.query(EbayAccount)
        .filter(EbayAccount.id == account_id, EbayAccount.org_id == current_user.id)
        .first()
    )
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="account_not_found")

    # Import here to avoid circular imports at module load time.
    from app.services.ebay_workers.cases_worker import run_cases_worker_for_account

    run_id = await run_cases_worker_for_account(account_id)
    if not run_id:
        # Worker may be disabled or a run lock could not be acquired.
        return {"status": "skipped", "reason": "not_started"}

    worker_run: Optional[EbayWorkerRun] = db.query(EbayWorkerRun).filter(EbayWorkerRun.id == run_id).first()
    if not worker_run:
        return {"status": "started", "run_id": run_id, "summary": None}

    return {
        "status": worker_run.status,
        "run_id": worker_run.id,
        "api_family": worker_run.api_family,
        "started_at": worker_run.started_at.isoformat() if worker_run.started_at else None,
        "finished_at": worker_run.finished_at.isoformat() if worker_run.finished_at else None,
        "summary": worker_run.summary_json or {},
    }


@router.get("/sync-jobs")
async def get_sync_jobs(
    endpoint: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(admin_required),
    db: Session = Depends(get_db)
):
    """Get all sync jobs for admin dashboard"""
    query = db.query(SyncLog).filter(SyncLog.user_id == current_user.id)
    
    if endpoint:
        query = query.filter(SyncLog.endpoint == endpoint)
    if status:
        query = query.filter(SyncLog.status == status)
    
    total = query.count()
    jobs = query.order_by(desc(SyncLog.sync_started_at)).offset(offset).limit(limit).all()
    
    return {
        "jobs": [
            {
                "id": j.id,
                "job_id": j.job_id,
                "endpoint": j.endpoint,
                "status": j.status,
                "pages_fetched": j.pages_fetched or 0,
                "records_fetched": j.records_fetched or 0,
                "records_stored": j.records_stored or 0,
                "duration_ms": j.duration_ms or 0,
                "error_text": j.error_text,
                "started_at": j.sync_started_at.isoformat() if j.sync_started_at else None,
                "completed_at": j.sync_completed_at.isoformat() if j.sync_completed_at else None
            }
            for j in jobs
        ],
        "total": total,
        "limit": limit,
        "offset": offset
    }


@router.get("/ebay/tokens/status")
async def get_ebay_token_status(
    current_user: User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    """Return per-account token status for the current org.

    This aggregates information from ebay_accounts, ebay_tokens and the
    ebay_token_refresh_log table so the Admin UI can quickly see which
    accounts are healthy, expiring soon, expired, or in error.
    """

    now_utc = datetime.now(timezone.utc)

    accounts = (
        db.query(EbayAccount)
        .filter(EbayAccount.org_id == current_user.id)
        .order_by(desc(EbayAccount.connected_at))
        .all()
    )

    def _to_utc(dt: Optional[datetime]) -> Optional[datetime]:
        if dt is None:
            return None
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    results = []
    for account in accounts:
        token: Optional[EbayToken] = (
            db.query(EbayToken)
            .filter(EbayToken.ebay_account_id == account.id)
            .order_by(desc(EbayToken.updated_at))
            .first()
        )

        expires_at_utc: Optional[datetime] = (
            _to_utc(token.expires_at) if token and token.expires_at else None
        )
        expires_in_seconds: Optional[int]
        if expires_at_utc is not None:
            expires_in_seconds = int((expires_at_utc - now_utc).total_seconds())
        else:
            expires_in_seconds = None

        has_refresh_token = bool(token and token.refresh_token)
        refresh_error = getattr(token, "refresh_error", None) if token else None

        # Latest refresh attempt for this account
        last_log: Optional[EbayTokenRefreshLog] = (
            db.query(EbayTokenRefreshLog)
            .filter(EbayTokenRefreshLog.ebay_account_id == account.id)
            .order_by(EbayTokenRefreshLog.started_at.desc())
            .first()
        )
        last_refresh_at: Optional[datetime] = None
        last_refresh_success: Optional[bool] = None
        last_refresh_error: Optional[str] = None

        if last_log is not None:
            last_refresh_at = last_log.finished_at or last_log.started_at
            last_refresh_success = last_log.success
            if not last_log.success:
                last_refresh_error = last_log.error_message

        # Count consecutive failures from the most recent logs (up to 10) so we
        # can surface "3 failures in a row"-style hints in the UI.
        recent_logs = (
            db.query(EbayTokenRefreshLog)
            .filter(EbayTokenRefreshLog.ebay_account_id == account.id)
            .order_by(EbayTokenRefreshLog.started_at.desc())
            .limit(10)
            .all()
        )
        failures_in_row = 0
        for log_row in recent_logs:
            if log_row.success:
                break
            failures_in_row += 1

        # Derive high-level status
        if token is None:
            status = "not_connected"
        else:
            if refresh_error:
                status = "error"
            elif expires_at_utc is None:
                status = "unknown"
            else:
                if expires_in_seconds is not None and expires_in_seconds <= 0:
                    status = "expired"
                elif (
                    expires_in_seconds is not None
                    and expires_in_seconds <= 600  # 10 minutes
                ):
                    status = "expiring_soon"
                else:
                    status = "ok"

        # Derive severity and whether a manual reconnect is required.
        #
        # - "ok": token valid for more than 60 minutes and no refresh_error
        # - "warning": token valid but within the next 60 minutes
        # - "error": token expired or has refresh_error / is not connected
        err_lower = (str(refresh_error or last_refresh_error or "") or "").lower()
        invalid_grant = "invalid_grant" in err_lower

        if status in ("expired", "error", "not_connected"):
            severity = "error"
        elif expires_in_seconds is not None and expires_in_seconds <= 3600:
            severity = "warning"
        else:
            severity = "ok"

        requires_reconnect = bool(invalid_grant or status in ("expired", "not_connected"))

        results.append(
            {
                "account_id": account.id,
                "account_name": account.house_name,
                "ebay_user_id": account.ebay_user_id,
                "status": status,
                "severity": severity,
                "requires_reconnect": requires_reconnect,
                "expires_at": expires_at_utc.isoformat() if expires_at_utc else None,
                "expires_in_seconds": expires_in_seconds,
                "has_refresh_token": has_refresh_token,
                "last_refresh_at": last_refresh_at.isoformat()
                if last_refresh_at
                else None,
                "last_refresh_success": last_refresh_success,
                "last_refresh_error": last_refresh_error,
                "refresh_failures_in_row": failures_in_row,
            }
        )

    return {"accounts": results}


@router.get("/workers/token-refresh/status")
async def get_token_refresh_worker_status(
    current_user: User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    """Return heartbeat/status information for the token refresh worker.

    NOTE: This endpoint is kept for backwards compatibility with existing
    frontend code. New clients should prefer
    ``/api/admin/ebay/workers/loop-status``, which aggregates both the token
    refresh and eBay workers loops.
    """

    # BackgroundWorker is global, not per-org, but we still require admin auth.
    worker: Optional[BackgroundWorker] = (
        db.query(BackgroundWorker)
        .filter(BackgroundWorker.worker_name == "token_refresh_worker")
        .one_or_none()
    )
    if worker is None:
        return {
            "worker_name": "token_refresh_worker",
            "interval_seconds": 600,
            "last_started_at": None,
            "last_finished_at": None,
            "last_status": None,
            "last_error_message": None,
            "runs_ok_in_row": 0,
            "runs_error_in_row": 0,
            "next_run_estimated_at": None,
        }

    interval = worker.interval_seconds or 600
    ref_time: Optional[datetime] = worker.last_started_at or worker.last_finished_at
    next_run_estimated_at: Optional[str] = None
    if ref_time is not None and interval:
        try:
            next_dt = ref_time + timedelta(seconds=interval)
            next_run_estimated_at = next_dt.astimezone(timezone.utc).isoformat()
        except Exception:  # pragma: no cover - defensive
            next_run_estimated_at = None

    return {
        "worker_name": worker.worker_name,
        "interval_seconds": interval,
        "last_started_at": worker.last_started_at.isoformat()
        if worker.last_started_at
        else None,
        "last_finished_at": worker.last_finished_at.isoformat()
        if worker.last_finished_at
        else None,
        "last_status": worker.last_status,
        "last_error_message": worker.last_error_message,
        "runs_ok_in_row": worker.runs_ok_in_row,
        "runs_error_in_row": worker.runs_error_in_row,
        "next_run_estimated_at": next_run_estimated_at,
    }


@router.post("/ebay/workers/run-once")
async def run_ebay_workers_once_admin(
    current_user: User = Depends(admin_required),
):
    """Trigger a single eBay workers cycle for all active accounts.

    This does **not** start the long-running loop; it just runs one
    on-demand iteration. The background loop will continue to run on its own
    schedule when enabled in the main API process.
    """
    try:
        # Fire-and-forget: let the background task run independently so the
        # admin call returns immediately.
        import asyncio

        asyncio.create_task(run_ebay_workers_once())
        return {"status": "started"}
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Failed to trigger on-demand eBay workers cycle: %s", exc, exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="run_once_failed")


@router.get("/ebay/workers/loop-status")
async def get_ebay_workers_loop_status(
    current_user: User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    """Return aggregated heartbeat for eBay data workers loop and token refresh loop.

    This is the primary endpoint the Admin Workers UI should use to display
    whether the long-running loops are healthy or stale.
    """

    loops: list[dict[str, Any]] = []

    now = datetime.now(timezone.utc)

    def _build_loop_payload(worker_name: str, loop_name: str, default_interval: int) -> dict[str, Any]:
        worker: Optional[BackgroundWorker] = (
            db.query(BackgroundWorker)
            .filter(BackgroundWorker.worker_name == worker_name)
            .one_or_none()
        )
        if worker is None:
            interval = default_interval
            last_started = None
            last_finished = None
            last_status = None
            last_error = None
        else:
            interval = worker.interval_seconds or default_interval
            last_started = worker.last_started_at
            last_finished = worker.last_finished_at
            last_status = worker.last_status
            last_error = worker.last_error_message

        # Consider a loop "stale" when we have never seen a finished run or the
        # time since the last finished run exceeds 3x the configured interval.
        stale = True
        last_finished_iso: Optional[str] = None
        last_started_iso: Optional[str] = None
        last_success_at_iso: Optional[str] = None

        if last_started is not None:
            try:
                last_started_iso = last_started.astimezone(timezone.utc).isoformat()
            except Exception:  # pragma: no cover - defensive
                last_started_iso = last_started.isoformat()

        if last_finished is not None:
            try:
                last_finished_utc = last_finished.astimezone(timezone.utc)
                last_finished_iso = last_finished_utc.isoformat()
            except Exception:  # pragma: no cover - defensive
                last_finished_utc = last_finished
                last_finished_iso = last_finished.isoformat()

            # If the last status was "ok", treat that finished_at as the last
            # success timestamp.
            if (last_status or "").lower() == "ok":
                last_success_at_iso = last_finished_utc.isoformat()

            try:
                if interval and (now - last_finished_utc).total_seconds() <= 3 * interval:
                    stale = False
            except Exception:  # pragma: no cover - defensive
                stale = True

        return {
            "loop_name": loop_name,
            "worker_name": worker_name,
            "interval_seconds": interval,
            "last_started_at": last_started_iso,
            "last_finished_at": last_finished_iso,
            "last_success_at": last_success_at_iso,
            "last_status": last_status,
            "last_error_message": last_error,
            "stale": stale,
            # For now the authoritative host is the main API process. If we
            # later move loops to dedicated services, this field can be
            # derived from environment.
            "source": "main_api",
        }

    # eBay data workers loop (every 5 minutes)
    loops.append(_build_loop_payload("ebay_workers_loop", "ebay_workers", 300))
    # Token refresh loop (every 10 minutes)
    loops.append(_build_loop_payload("token_refresh_worker", "token_refresh", 600))

    return {"loops": loops}


@router.get("/ebay/tokens/refresh/log")
async def get_ebay_token_refresh_log(
    account_id: str = Query(..., description="eBay account id"),
    limit: int = Query(50, ge=1, le=500),
    current_user: User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    """Return recent token refresh attempts for a single eBay account."""

    account: Optional[EbayAccount] = (
        db.query(EbayAccount)
        .filter(EbayAccount.id == account_id, EbayAccount.org_id == current_user.id)
        .first()
    )
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="account_not_found")

    logs = (
        db.query(EbayTokenRefreshLog)
        .filter(EbayTokenRefreshLog.ebay_account_id == account_id)
        .order_by(EbayTokenRefreshLog.started_at.desc())
        .limit(limit)
        .all()
    )

    return {
        "account": {
            "id": account.id,
            "ebay_user_id": account.ebay_user_id,
            "house_name": account.house_name,
        },
        "logs": [
            {
                "id": row.id,
                "started_at": row.started_at.isoformat() if row.started_at else None,
                "finished_at": row.finished_at.isoformat() if row.finished_at else None,
                "success": row.success,
                "error_code": row.error_code,
                "error_message": row.error_message,
                "old_expires_at": row.old_expires_at.isoformat()
                if row.old_expires_at
                else None,
                "new_expires_at": row.new_expires_at.isoformat()
                if row.new_expires_at
                else None,
                "triggered_by": row.triggered_by,
            }
            for row in logs
        ],
    }


@router.post("/ebay/token/refresh-debug")
async def debug_refresh_ebay_token(
    payload: TokenRefreshDebugRequest,
    current_user: User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    """Run a one-off token refresh for an account and capture raw HTTP.

    This uses the same request-building logic as the background token refresh
    worker but *does not* write secrets to normal logs. Instead it returns a
    structured payload with the exact HTTP request and response so the admin
    UI can display it in a terminal-like view.
    """

    account_id = payload.ebay_account_id

    account: Optional[EbayAccount] = (
        db.query(EbayAccount)
        .filter(EbayAccount.id == account_id, EbayAccount.org_id == current_user.id)
        .first()
    )
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="account_not_found")

    token: Optional[EbayToken] = (
        db.query(EbayToken)
        .filter(EbayToken.ebay_account_id == account.id)
        .order_by(EbayToken.updated_at.desc())
        .first()
    )

    env = settings.EBAY_ENVIRONMENT or "sandbox"

    if not token or not token.refresh_token:
        # Nothing to call eBay with; return a structured error without making
        # any external HTTP requests.
        return {
            "account": {
                "id": account.id,
                "ebay_user_id": account.ebay_user_id,
                "house_name": account.house_name,
            },
            "environment": env,
            "success": False,
            "error": "no_refresh_token",
            "error_description": "Account has no refresh token stored",
            "request": None,
            "response": None,
        }

    # Use the shared helper so that debug and worker flows share the same
    # refresh logic (load token -> decrypt -> call eBay -> persist + log).
    result = await refresh_access_token_for_account(
        db,
        account,
        triggered_by="debug",
        persist=True,
        capture_http=True,
    )

    debug_payload = result.get("http") or {
        "environment": env,
        "success": result.get("success", False),
        "error": result.get("error"),
        "error_description": result.get("error_message"),
        "request": None,
        "response": None,
    }

    # Attach basic account context; the rest of the shape comes from the
    # shared debug_refresh_access_token_http helper.
    return {
        "account": {
            "id": account.id,
            "ebay_user_id": account.ebay_user_id,
            "house_name": account.house_name,
        },
        **debug_payload,
    }


@router.get("/ebay/tokens/logs")
async def get_ebay_token_logs(
    env: str = Query(..., description="production only"),
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(admin_required)
):
    if not FEATURE_TOKEN_INFO:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="feature_disabled")
    if env != 'production':
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="env_not_supported")

    logs = ebay_connect_logger.get_logs(current_user.id, env, limit)
    # Only token-related actions
    filtered = [
        l for l in logs if l.get('action') in (
            'token_refreshed', 'token_refresh_failed', 'token_info_viewed', 'token_call_blocked_missing_scopes'
        )
    ]
    return {"logs": filtered}


@router.get("/ebay/tokens/terminal-logs")
async def get_ebay_token_terminal_logs(
    env: str = Query(..., description="production only"),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(admin_required),
):
    """Return detailed token-refresh HTTP logs for the Workers terminal view.

    This endpoint is admin-only and masks refresh_token values in the response
    body so they are safe to display in the UI while still being precise.
    """
    if env != "production":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="env_not_supported")

    logs = ebay_connect_logger.get_logs(current_user.id, env, limit)

    def _mask_refresh_token(value: str) -> str:
        if not isinstance(value, str):
            return value
        if len(value) <= 15:
            return value
        return f"{value[:10]}...{value[-5:]}"

    def _mask_request(req: dict | None) -> dict | None:
        if not isinstance(req, dict):
            return req
        body = req.get("body") or req.get("data")
        if isinstance(body, dict) and "refresh_token" in body:
            body = {**body, "refresh_token": _mask_refresh_token(body.get("refresh_token"))}
        return {**req, "body": body}

    entries: list[dict] = []
    for entry in logs:
        action = entry.get("action")
        if action not in {"token_refreshed", "token_refresh_failed", "token_refresh_debug", "worker_heartbeat"}:
            continue
        masked_req = _mask_request(entry.get("request"))
        entries.append(
            {
                "id": entry.get("id"),
                "created_at": entry.get("created_at"),
                "environment": entry.get("environment"),
                "action": action,
                "source": entry.get("source"),
                "request": masked_req,
                "response": entry.get("response"),
                "error": entry.get("error"),
            }
        )

    return {"entries": entries}


@router.post("/ebay/tokens/logs/blocked-scope")
async def log_blocked_scope(
    env: str = Query(..., description="production only"),
    details: dict = None,
    current_user: User = Depends(admin_required)
):
    if not FEATURE_TOKEN_INFO:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="feature_disabled")
    if env != 'production':
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="env_not_supported")
    try:
        ebay_connect_logger.log_event(
            user_id=current_user.id,
            environment=env,
            action="token_call_blocked_missing_scopes",
            request={"method": "POST", "url": "/api/admin/ebay/tokens/logs/blocked-scope", "body": details},
            response={"status": 200}
        )
        return {"ok": True}
    except Exception as e:
        logger.error(f"Failed to log blocked scope: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="log_failed")


@router.get("/ebay/connect/last")
async def get_last_connect_cycle(
    env: str = Query(..., description="sandbox or production"),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(admin_required),
    db: Session = Depends(get_db)
):
    """Return the most recent connect cycle summary: start_auth, callback, exchange, connect_success, plus current tokens/authorizations."""
    # Logs
    from ..services.database import db as db_svc
    logs = db_svc.get_connect_logs(current_user.id, env, limit)
    summary = {}
    for entry in logs:
        act = entry.get('action')
        if act and act not in summary:
            if act in ("start_auth", "callback_received", "exchange_code_for_token", "connect_success", "token_exchange_request", "token_exchange_response"):
                summary[act] = entry
        if len(summary) >= 4:
            # we captured key stages
            pass
    # Account snapshot
    account: Optional[EbayAccount] = db.query(EbayAccount).filter(
        EbayAccount.org_id == current_user.id,
        EbayAccount.is_active == True
    ).order_by(desc(EbayAccount.connected_at)).first()
    token = None
    auth = None
    if account:
        token = db.query(EbayToken).filter(EbayToken.ebay_account_id == account.id).order_by(desc(EbayToken.updated_at)).first()
        auth = db.query(EbayAuthorization).filter(EbayAuthorization.ebay_account_id == account.id).first()
    return {
        "logs": summary,
        "account": {
            "id": (account.id if account else None),
            "username": (account.username if account else None),
            "ebay_user_id": (account.ebay_user_id if account else None),
        },
        "token": {
            "access_len": (len(token.access_token) if token and token.access_token else 0),
            "access_expires_at": (token.expires_at.isoformat() if token and token.expires_at else None),
            "refresh_len": (len(token.refresh_token) if token and token.refresh_token else 0),
            "refresh_expires_at": (token.refresh_expires_at.isoformat() if token and token.refresh_expires_at else None),
        } if token else None,
        "authorizations": {
            "scopes": (auth.scopes if auth and auth.scopes else []),
            "count": (len(auth.scopes) if auth and auth.scopes else 0),
        }
    }

@router.get("/ebay/accounts/scopes")
async def get_ebay_accounts_scopes(
    current_user: User = Depends(admin_required),
    db: Session = Depends(get_db)
):
    """Return eBay accounts for this org with their stored scopes vs scope catalog.

    This is an admin-only view that shows:
    - scope_catalog: all active user/both scopes from ebay_scope_definitions
    - accounts: each EbayAccount + its authorizations.scopes and whether it has full catalog
    """
    # Load catalog of available scopes (user-consent and both)
    catalog_rows = (
        db.query(EbayScopeDefinition)
        .filter(
            EbayScopeDefinition.is_active == True,  # noqa: E712
            EbayScopeDefinition.grant_type.in_(['user', 'both']),
        )
        .order_by(EbayScopeDefinition.scope)
        .all()
    )
    catalog_scopes = [r.scope for r in catalog_rows]

    # All accounts for current org (including inactive, so admin sees history)
    accounts = (
        db.query(EbayAccount)
        .filter(EbayAccount.org_id == current_user.id)
        .order_by(desc(EbayAccount.connected_at))
        .all()
    )

    result_accounts = []
    for account in accounts:
        # All authorizations for this account
        auth_rows = (
            db.query(EbayAuthorization)
            .filter(EbayAuthorization.ebay_account_id == account.id)
            .order_by(EbayAuthorization.created_at.desc())
            .all()
        )
        scopes: list[str] = []
        for auth in auth_rows:
            if auth.scopes:
                scopes.extend(auth.scopes)
        # Unique + sorted scopes
        unique_scopes = sorted(set(scopes))
        missing_catalog_scopes = [s for s in catalog_scopes if s not in unique_scopes]
        has_all_catalog_scopes = bool(catalog_scopes) and not missing_catalog_scopes

        # Latest token snapshot (if exists) – minimal info only
        token = (
            db.query(EbayToken)
            .filter(EbayToken.ebay_account_id == account.id)
            .order_by(desc(EbayToken.updated_at))
            .first()
        )

        result_accounts.append({
            "id": account.id,
            "username": account.username,
            "ebay_user_id": account.ebay_user_id,
            "house_name": account.house_name,
            "is_active": account.is_active,
            "connected_at": account.connected_at.isoformat() if account.connected_at else None,
            "scopes": unique_scopes,
            "scopes_count": len(unique_scopes),
            "has_all_catalog_scopes": has_all_catalog_scopes,
            "missing_catalog_scopes": missing_catalog_scopes,
            "token": {
                "access_expires_at": token.expires_at.isoformat() if token and token.expires_at else None,
                "has_refresh_token": bool(token and token.refresh_token),
            } if token else None,
        })

    return {
        "scope_catalog": [
            {
                "scope": r.scope,
                "grant_type": r.grant_type,
                "description": r.description,
            }
            for r in catalog_rows
        ],
        "accounts": result_accounts,
    }


@router.get("/ebay/tokens/info")
async def get_ebay_tokens_info(
    env: str = Query(..., description="production only"),
    current_user: User = Depends(admin_required),
    db: Session = Depends(get_db)
):
    if not FEATURE_TOKEN_INFO:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="feature_disabled")
    if env != 'production':
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="env_not_supported")

    # Pick the first active account for this org (user)
    account: Optional[EbayAccount] = db.query(EbayAccount).filter(
        EbayAccount.org_id == current_user.id,
        EbayAccount.is_active == True
    ).order_by(EbayAccount.connected_at.desc()).first()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no_account")

    token: Optional[EbayToken] = db.query(EbayToken).filter(EbayToken.ebay_account_id == account.id).order_by(EbayToken.updated_at.desc()).first()
    auth: Optional[EbayAuthorization] = db.query(EbayAuthorization).filter(EbayAuthorization.ebay_account_id == account.id).first()

    now = datetime.now(timezone.utc)

    def mask(val: Optional[str]) -> Optional[str]:
        if not val:
            return None
        if len(val) <= 12:
            return "****"
        return f"{val[:6]}...{val[-6:]}"

    access_expires_at = token.expires_at if token and token.expires_at else None
    access_ttl_sec = int((access_expires_at - now).total_seconds()) if access_expires_at else None
    refresh_expires_at = token.refresh_expires_at if token and token.refresh_expires_at else None
    refresh_ttl_sec = int((refresh_expires_at - now).total_seconds()) if refresh_expires_at else None

    # Log view (no secrets)
    try:
        ebay_connect_logger.log_event(
            user_id=current_user.id,
            environment=env,
            action="token_info_viewed",
            request={"method": "GET", "url": f"/api/admin/ebay/tokens/info?env={env}"},
            response={
                "status": 200,
                "body": {
                    "meta": {
                        "ebay_account_id": str(account.id),
                        "ebay_username": account.username,
                        "access_len": (len(token.access_token) if token and token.access_token else 0),
                        "refresh_len": (len(token.refresh_token) if token and token.refresh_token else 0)
                    }
                }
            }
        )
    except Exception:
        pass

    return {
        "now_utc": now.isoformat(),
        "source": "account_level",
        "ebay_account": {
            "id": account.id,
            "username": account.username,
            "ebay_user_id": account.ebay_user_id,
        },
        "access_token_masked": mask(token.access_token if token else None),
        "access_expires_at": access_expires_at.isoformat() if access_expires_at else None,
        "access_ttl_sec": access_ttl_sec,
        "refresh_token_masked": mask(token.refresh_token if token else None),
        "refresh_expires_at": refresh_expires_at.isoformat() if refresh_expires_at else None,
        "refresh_ttl_sec": refresh_ttl_sec,
        "scopes": (auth.scopes if auth and auth.scopes else []),
    }


@router.post("/ebay/tokens/refresh")
async def refresh_ebay_access_token(
    env: str = Query(..., description="production only"),
    current_user: User = Depends(admin_required),
    db: Session = Depends(get_db)
):
    if not FEATURE_TOKEN_INFO:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="feature_disabled")
    if env != 'production':
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="env_not_supported")

    account: Optional[EbayAccount] = db.query(EbayAccount).filter(
        EbayAccount.org_id == current_user.id,
        EbayAccount.is_active == True
    ).order_by(EbayAccount.connected_at.desc()).first()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no_account")

    token: Optional[EbayToken] = db.query(EbayToken).filter(EbayToken.ebay_account_id == account.id).first()
    if not token or not token.refresh_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="no_refresh_token")

    # Execute refresh via the shared helper so behaviour matches the worker.
    try:
        result = await refresh_access_token_for_account(
            db,
            account,
            triggered_by="admin",
            persist=True,
            capture_http=False,
        )
        if not result.get("success"):
            msg = result.get("error_message") or result.get("error") or "refresh_failed"
            raise RuntimeError(msg)

        # Reload token to compute TTL and log meta without exposing secrets.
        token = db.query(EbayToken).filter(EbayToken.ebay_account_id == account.id).first() or token

        try:
            ebay_connect_logger.log_event(
                user_id=current_user.id,
                environment=env,
                action="token_refreshed",
                request={"method": "POST", "url": f"/api/admin/ebay/tokens/refresh?env={env}"},
                response={
                    "status": 200,
                    "body": {
                        "meta": {
                            "ebay_account_id": str(account.id),
                            "ebay_username": account.username,
                            "access_len": (len(token.access_token) if token and token.access_token else 0),
                            "refresh_len": (len(token.refresh_token) if token and token.refresh_token else 0),
                            "access_expires_at": token.expires_at.isoformat() if token.expires_at else None,
                            "refresh_expires_at": token.refresh_expires_at.isoformat() if getattr(token, "refresh_expires_at", None) else None,
                        }
                    },
                },
            )
        except Exception:
            pass
        logger.info(f"Admin token refresh for account {account.id}")
    except Exception as e:
        try:
            ebay_connect_logger.log_event(
                user_id=current_user.id,
                environment=env,
                action="token_refresh_failed",
                request={"method": "POST", "url": f"/api/admin/ebay/tokens/refresh?env={env}"},
                error=str(e),
            )
        except Exception:
            pass
        logger.error(f"Admin token refresh failed: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="refresh_failed")

    now = datetime.now(timezone.utc)
    access_expires_at = token.expires_at if token and token.expires_at else None
    ttl_sec = int((access_expires_at - now).total_seconds()) if access_expires_at else None

    return {
        "access_expires_at": access_expires_at.isoformat() if access_expires_at else None,
        "access_ttl_sec": ttl_sec,
    }


@router.post("/ebay/workers/token-refresh/run-once")
async def run_token_refresh_worker_once(
    current_user: User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    """Trigger a manual token refresh cycle for ALL active accounts.

    This forces a refresh attempt for every active account, regardless of
    expiry time, and logs full debug info to the terminal.
    """
    try:
        # Force refresh of ALL accounts.
        result = await run_token_refresh_job(
            db,
            force_all=True,
            capture_http=True,
            triggered_by="manual_loop"
        )
        return result
    except Exception as e:
        logger.error(f"Manual token refresh failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"run_once_failed: {str(e)}"
        )


@router.get("/ebay/token/refresh-preview/{ebay_account_id}")
async def get_ebay_token_refresh_preview(
    ebay_account_id: str,
    current_user: User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    """Admin-only, sanitized debug information about the token refresh request.

    Never returns full tokens or Authorization headers. This uses the same
    decrypted refresh_token and HTTP shape that the background worker uses
    when calling eBay to refresh access tokens.
    """
    account = db.query(EbayAccount).filter(
        EbayAccount.id == ebay_account_id,
        EbayAccount.org_id == current_user.id,
    ).first()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="account_not_found")

    preview = build_sanitized_refresh_preview_for_account(db, ebay_account_id)
    return preview


@router.get("/ebay-events")
async def list_ebay_events(
    topic: Optional[str] = Query(None, description="Exact topic or comma-separated list of topics"),
    entity_type: Optional[str] = Query(None, alias="entityType"),
    entity_id: Optional[str] = Query(None, alias="entityId"),
    ebay_account: Optional[str] = Query(None, alias="ebayAccount"),
    source: Optional[str] = Query(None),
    channel: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    from_ts: Optional[str] = Query(None, alias="from", description="ISO timestamp lower bound"),
    to_ts: Optional[str] = Query(None, alias="to", description="ISO timestamp upper bound"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    sort_by: Optional[str] = Query(None, alias="sortBy", description="event_time or created_at"),
    sort_dir: str = Query("desc", alias="sortDir", description="asc or desc"),
    current_user: User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    """List eBay events for the admin Notifications UI.

    Filtering is intentionally simple for the first version and can be
    extended as we add processors and more metadata.
    """

    query = db.query(EbayEvent)

    if topic:
        topics = [t.strip() for t in topic.split(",") if t.strip()]
        if topics:
            if len(topics) == 1:
                query = query.filter(EbayEvent.topic == topics[0])
            else:
                query = query.filter(EbayEvent.topic.in_(topics))

    if entity_type:
        query = query.filter(EbayEvent.entity_type == entity_type)
    if entity_id:
        query = query.filter(EbayEvent.entity_id == entity_id)
    if ebay_account:
        query = query.filter(EbayEvent.ebay_account == ebay_account)
    if source:
        query = query.filter(EbayEvent.source == source)
    if channel:
        query = query.filter(EbayEvent.channel == channel)
    if status:
        query = query.filter(EbayEvent.status == status)

    def _parse_iso(ts: Optional[str]) -> Optional[datetime]:
        if not ts:
            return None
        try:
            if ts.endswith("Z"):
                ts_local = ts.replace("Z", "+00:00")
            else:
                ts_local = ts
            return datetime.fromisoformat(ts_local)
        except Exception:
            return None

    from_dt = _parse_iso(from_ts)
    to_dt = _parse_iso(to_ts)

    if from_dt:
        query = query.filter(
            or_(
                and_(EbayEvent.event_time.isnot(None), EbayEvent.event_time >= from_dt),
                and_(EbayEvent.event_time.is_(None), EbayEvent.created_at >= from_dt),
            )
        )

    if to_dt:
        query = query.filter(
            or_(
                and_(EbayEvent.event_time.isnot(None), EbayEvent.event_time <= to_dt),
                and_(EbayEvent.event_time.is_(None), EbayEvent.created_at <= to_dt),
            )
        )

    total = query.count()

    # Sorting
    effective_sort_by = (sort_by or "event_time").lower()
    if effective_sort_by not in ("event_time", "created_at"):
        effective_sort_by = "event_time"

    sort_field = EbayEvent.event_time if effective_sort_by == "event_time" else EbayEvent.created_at
    if (sort_dir or "desc").lower() == "asc":
        query = query.order_by(sort_field.asc())
    else:
        query = query.order_by(sort_field.desc())

    events = query.offset(offset).limit(limit).all()

    items = []
    for ev in events:
        payload = ev.payload or {}
        payload_preview: Any

        if isinstance(payload, dict):
            # Prefer Notification API-style preview when available.
            preferred_keys = ["metadata", "notification"]
            preview = {k: payload.get(k) for k in preferred_keys if k in payload}

            if not preview:
                # Fallback: shallow preview of a few top-level keys.
                preview = {}
                for idx, (k, v) in enumerate(payload.items()):
                    preview[k] = v
                    if idx >= 4:
                        break
            payload_preview = preview
        else:
            payload_preview = payload

        items.append(
            {
                "id": str(ev.id),
                "created_at": ev.created_at.isoformat() if ev.created_at else None,
                "source": ev.source,
                "channel": ev.channel,
                "topic": ev.topic,
                "entity_type": ev.entity_type,
                "entity_id": ev.entity_id,
                "ebay_account": ev.ebay_account,
                "event_time": ev.event_time.isoformat() if ev.event_time else None,
                "publish_time": ev.publish_time.isoformat() if ev.publish_time else None,
                "status": ev.status,
                "error": ev.error,
                "signature_valid": ev.signature_valid,
                "signature_kid": ev.signature_kid,
                "payload_preview": payload_preview,
            }
        )

    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/ebay-events/{event_id}")
async def get_ebay_event_detail(
    event_id: str,
    current_user: User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    """Return full details (including headers+payload) for a single ebay_events row."""

    ev: Optional[EbayEvent] = db.query(EbayEvent).filter(EbayEvent.id == event_id).first()
    if not ev:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")

    return {
        "id": str(ev.id),
        "created_at": ev.created_at.isoformat() if ev.created_at else None,
        "source": ev.source,
        "channel": ev.channel,
        "topic": ev.topic,
        "entity_type": ev.entity_type,
        "entity_id": ev.entity_id,
        "ebay_account": ev.ebay_account,
        "event_time": ev.event_time.isoformat() if ev.event_time else None,
        "publish_time": ev.publish_time.isoformat() if ev.publish_time else None,
        "status": ev.status,
        "error": ev.error,
        "signature_valid": ev.signature_valid,
        "signature_kid": ev.signature_kid,
        "headers": ev.headers or {},
        "payload": ev.payload,
    }


# Internal helper implementing the core notifications status logic.
# The public route wrapper `get_notifications_status` below delegates to this
# helper and adds a final catch-all for robustness.
async def _get_notifications_status_inner(
    current_user: User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    """Return high-level health for the Notifications Center webhook.

    Status is derived from Notification API destination/subscription state and
    the presence of recent events for the primary webhook topic.

    This handler should *not* raise uncaught exceptions for normal
    misconfigurations or Notification API errors. Instead, it always returns
    HTTP 200 with an `ok` flag and structured error information.
    """

    from ..models_sqlalchemy.models import EbayAccount, EbayToken  # avoid cycles

    env = settings.EBAY_ENVIRONMENT
    endpoint_url = settings.EBAY_NOTIFICATION_DESTINATION_URL
    checked_at = datetime.now(timezone.utc).isoformat()

    def _build_topics_payload_for_error(error_reason: str, error_summary: str | None) -> list[dict]:
        """Best-effort per-topic diagnostics when Notification API calls fail.

        We still include recent event counts from the local database so the
        UI can show whether events have ever flowed for a topic.
        """

        topics_payload: list[dict] = []
        now_local = datetime.now(timezone.utc)
        window_start_local = now_local - timedelta(hours=24)

        for topic_cfg in SUPPORTED_TOPICS:
            topic_id = topic_cfg.topic_id
            recent_count = 0
            last_event_time: str | None = None

            try:
                topic_recent_q = db.query(EbayEvent).filter(EbayEvent.topic == topic_id)
                topic_recent_q = topic_recent_q.filter(
                    or_(
                        and_(
                            EbayEvent.event_time.isnot(None),
                            EbayEvent.event_time >= window_start_local,
                        ),
                        and_(
                            EbayEvent.event_time.is_(None),
                            EbayEvent.created_at >= window_start_local,
                        ),
                    )
                )
                recent_count = topic_recent_q.count()

                topic_latest = (
                    db.query(EbayEvent)
                    .filter(EbayEvent.topic == topic_id)
                    .order_by(
                        EbayEvent.event_time.desc().nullslast(),
                        EbayEvent.created_at.desc(),
                    )
                    .first()
                )
                if topic_latest:
                    base_ts = topic_latest.event_time or topic_latest.created_at
                    last_event_time = base_ts.isoformat() if base_ts else None
            except Exception:
                # DB diagnostics are best-effort; ignore failures here so we
                # still return structured status instead of HTTP 500.
                pass

            topics_payload.append(
                {
                    "topicId": topic_id,
                    "scope": None,
                    "destinationId": None,
                    "subscriptionId": None,
                    "destinationStatus": None,
                    "subscriptionStatus": None,
                    "verificationStatus": None,
                    "tokenType": None,
                    "status": "ERROR",
                    "error": error_summary or error_reason,
                    "recentEvents": {
                        "count": recent_count,
                        "lastEventTime": last_event_time,
                    },
                }
            )

        return topics_payload

    if not endpoint_url:
        error_summary = "EBAY_NOTIFICATION_DESTINATION_URL is not configured on the backend."
        return {
            "ok": False,
            "environment": env,
            "webhookUrl": None,
            "state": "misconfigured",
            "reason": "missing_destination_url",
            "errorSummary": error_summary,
            "destination": None,
            "subscription": None,
            "destinationId": None,
            "subscriptionId": None,
            "recentEvents": {"count": 0, "lastEventTime": None},
            "checkedAt": checked_at,
            "topics": [],
        }

    # Pick first active account for this org
    account: Optional[EbayAccount] = (
        db.query(EbayAccount)
        .filter(EbayAccount.org_id == current_user.id, EbayAccount.is_active == True)  # noqa: E712
        .order_by(desc(EbayAccount.connected_at))
        .first()
    )
    if not account:
        error_summary = "No active eBay account found for this organization. Connect an account first."
        return {
            "ok": False,
            "environment": env,
            "webhookUrl": endpoint_url,
            "state": "misconfigured",
            "reason": "no_account",
            "errorSummary": error_summary,
            "destination": None,
            "subscription": None,
            "destinationId": None,
            "subscriptionId": None,
            "recentEvents": {"count": 0, "lastEventTime": None},
            "checkedAt": checked_at,
            "account": None,
            "topics": [],
        }

    account_info = {
        "id": str(account.id),
        "username": account.username or account.ebay_user_id,
        "environment": env,
    }

    token: Optional[EbayToken] = (
        db.query(EbayToken)
        .filter(EbayToken.ebay_account_id == account.id)
        .order_by(desc(EbayToken.updated_at))
        .first()
    )
    if not token or not token.access_token:
        error_summary = (
            "No eBay access token found for the active account; reconnect eBay "
            "for this organization."
        )
        return {
            "ok": False,
            "environment": env,
            "webhookUrl": endpoint_url,
            "state": "misconfigured",
            "reason": "no_access_token",
            "errorSummary": error_summary,
            "destination": None,
            "subscription": None,
            "destinationId": None,
            "subscriptionId": None,
            "recentEvents": {"count": 0, "lastEventTime": None},
            "checkedAt": checked_at,
            "account": account_info,
            "topics": [],
        }

    access_token = token.access_token

    # Primary topic used for overall webhook health (currently MARKETPLACE_ACCOUNT_DELETION).
    primary_topic_id = PRIMARY_WEBHOOK_TOPIC_ID

    try:
        dest, sub = await ebay_service.get_notification_status(
            access_token,
            endpoint_url,
            primary_topic_id,
        )
    except HTTPException as exc:
        # Surface Notification API error as misconfigured state with structured payload for UI diagnostics.
        logger.error(
            "Notification status check failed via Notification API: status=%s detail=%s",
            exc.status_code,
            exc.detail,
        )
        detail = exc.detail
        if isinstance(detail, dict):
            nerr = {
                "status_code": detail.get("status_code", exc.status_code),
                "message": detail.get("message") or str(detail),
                "body": detail.get("body"),
            }
        else:
            nerr = {"status_code": exc.status_code, "message": str(detail)}

        # Try to detect explicit challenge verification failures (195020) so we
        # can surface a clearer reason in Diagnostics.
        reason = "notification_api_error"
        body_obj = nerr.get("body")
        if isinstance(body_obj, dict):
            try:
                errors = body_obj.get("errors") or []
                for err in errors:
                    if isinstance(err, dict) and err.get("errorId") == 195020:
                        reason = "verification_failed"
                        break
            except Exception:
                # Best-effort only; fall back to generic reason if parsing fails.
                pass

        body_preview = body_obj
        if isinstance(body_preview, (dict, list)):
            body_preview = str(body_preview)[:300]
        error_summary = f"Notification API HTTP {nerr.get('status_code')} - {nerr.get('message')}"
        if body_preview:
            error_summary += f" | body: {body_preview}"

        topics_payload = _build_topics_payload_for_error(reason, error_summary)

        return {
            "ok": False,
            "environment": env,
            "webhookUrl": endpoint_url,
            "state": "misconfigured",
            "reason": reason,
            "notificationError": nerr,
            "errorSummary": error_summary,
            "destination": None,
            "subscription": None,
            "destinationId": None,
            "subscriptionId": None,
            "recentEvents": {"count": 0, "lastEventTime": None},
            "checkedAt": checked_at,
            "account": account_info,
            "topics": topics_payload,
        }
    except Exception as exc:  # pragma: no cover - defensive; should be rare
        logger.exception(
            "Unexpected error while checking Notification API status for primary topic %s",
            primary_topic_id,
        )
        error_summary = f"Unexpected error while checking Notification API status: {exc}"
        topics_payload = _build_topics_payload_for_error("internal_error", error_summary)
        return {
            "ok": False,
            "environment": env,
            "webhookUrl": endpoint_url,
            "state": "misconfigured",
            "reason": "internal_error",
            "errorSummary": error_summary,
            "destination": None,
            "subscription": None,
            "destinationId": None,
            "subscriptionId": None,
            "recentEvents": {"count": 0, "lastEventTime": None},
            "checkedAt": checked_at,
            "account": account_info,
            "topics": topics_payload,
        }

    # Recent events for the primary topic in the last 24h
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(hours=24)

    recent_q = db.query(EbayEvent).filter(EbayEvent.topic == primary_topic_id)
    recent_q = recent_q.filter(
        or_(
            and_(EbayEvent.event_time.isnot(None), EbayEvent.event_time >= window_start),
            and_(EbayEvent.event_time.is_(None), EbayEvent.created_at >= window_start),
        )
    )
    recent_count = recent_q.count()

    latest = (
        db.query(EbayEvent)
        .filter(EbayEvent.topic == primary_topic_id)
        .order_by(
            EbayEvent.event_time.desc().nullslast(),
            EbayEvent.created_at.desc(),
        )
        .first()
    )
    last_event_time = None
    if latest:
        last_event_time = (latest.event_time or latest.created_at).isoformat() if (
            latest.event_time or latest.created_at
        ) else None

    state = "misconfigured"
    reason: str | None = None
    dest_status: str | None = None
    sub_status: str | None = None
    verification_status: str | None = None

    if dest is None:
        reason = "no_destination"
    else:
        dest_status = (dest.get("status") or "").upper() or "UNKNOWN"
        delivery_cfg = dest.get("deliveryConfig") or {}
        raw_ver_status = delivery_cfg.get("verificationStatus")
        if isinstance(raw_ver_status, str) and raw_ver_status:
            verification_status = raw_ver_status.upper()
        sub_status = (sub.get("status") or "").upper() if sub else None

        if dest_status != "INACTIVE" and dest_status != "ENABLED":
            # Destination exists but is not in an active state.
            reason = "destination_disabled"
        elif verification_status and verification_status not in ("CONFIRMED", "VERIFIED"):
            # eBay may report UNCONFIRMED / PENDING while the challenge flow is in progress.
            reason = "verification_pending"
        elif sub is None:
            reason = "no_subscription"
        elif sub_status not in (None, "ENABLED"):
            reason = "subscription_not_enabled"
        elif recent_count == 0:
            state = "no_events"
            reason = "no_recent_events"
        else:
            state = "ok"
            reason = "subscription_enabled"

    dest_id = dest.get("destinationId") or dest.get("id") if dest else None
    sub_id = sub.get("subscriptionId") or sub.get("id") if sub else None

    # Build per-topic status array for Diagnostics UI.
    topics_payload: list[dict] = []
    for topic_cfg in SUPPORTED_TOPICS:
        topic_id = topic_cfg.topic_id
        topic_error_reason: str | None = None
        topic_error_summary: str | None = None

        # Reuse primary topic data when possible; otherwise best-effort call.
        if topic_id == primary_topic_id:
            t_dest = dest
            t_sub = sub
        else:
            try:
                t_dest, t_sub = await ebay_service.get_notification_status(
                    access_token,
                    endpoint_url,
                    topic_id,
                )
            except HTTPException as exc:
                logger.error(
                    "Notification status check failed for topic %s via Notification API: status=%s detail=%s",
                    topic_id,
                    exc.status_code,
                    exc.detail,
                )
                detail = exc.detail
                if isinstance(detail, dict):
                    nerr = {
                        "status_code": detail.get("status_code", exc.status_code),
                        "message": detail.get("message") or str(detail),
                        "body": detail.get("body"),
                    }
                else:
                    nerr = {"status_code": exc.status_code, "message": str(detail)}

                topic_error_reason = "notification_api_error"
                body_obj = nerr.get("body")
                body_preview = body_obj
                if isinstance(body_preview, (dict, list)):
                    body_preview = str(body_preview)[:300]
                topic_error_summary = f"Notification API HTTP {nerr.get('status_code')} - {nerr.get('message')}"
                if body_preview:
                    topic_error_summary += f" | body: {body_preview}"

                t_dest, t_sub = None, None
            except Exception as exc:  # pragma: no cover - defensive
                logger.exception(
                    "Unexpected error while checking Notification API status for topic %s",
                    topic_id,
                )
                topic_error_reason = "internal_error"
                topic_error_summary = str(exc)
                t_dest, t_sub = None, None

        t_dest_id = t_dest.get("destinationId") or t_dest.get("id") if t_dest else None
        t_sub_id = t_sub.get("subscriptionId") or t_sub.get("id") if t_sub else None

        t_dest_status: str | None = None
        t_sub_status: str | None = None
        t_verification_status: str | None = None
        if t_dest is not None:
            t_dest_status = (t_dest.get("status") or "").upper() or "UNKNOWN"
            t_delivery_cfg = t_dest.get("deliveryConfig") or {}
            t_raw_ver = t_delivery_cfg.get("verificationStatus")
            if isinstance(t_raw_ver, str) and t_raw_ver:
                t_verification_status = t_raw_ver.upper()
            t_sub_status = (t_sub.get("status") or "").upper() if t_sub else None

        # Topic metadata (scope) is best-effort; errors here do not affect core state.
        topic_scope: str | None = None
        try:
            topic_meta = await ebay_service.get_notification_topic_metadata(
                access_token,
                topic_id,
            )
            raw_scope = topic_meta.get("scope")
            if isinstance(raw_scope, str) and raw_scope:
                topic_scope = raw_scope.upper()
        except Exception:
            topic_scope = None

        token_type: str | None = None
        if topic_scope == "APPLICATION":
            token_type = "application"
        elif topic_scope == "USER":
            token_type = "user"

        # Recent events per topic (24h window), independent of primary stats.
        topic_recent_q = db.query(EbayEvent).filter(EbayEvent.topic == topic_id)
        topic_recent_q = topic_recent_q.filter(
            or_(
                and_(
                    EbayEvent.event_time.isnot(None),
                    EbayEvent.event_time >= window_start,
                ),
                and_(
                    EbayEvent.event_time.is_(None),
                    EbayEvent.created_at >= window_start,
                ),
            )
        )
        topic_recent_count = topic_recent_q.count()

        topic_latest = (
            db.query(EbayEvent)
            .filter(EbayEvent.topic == topic_id)
            .order_by(
                EbayEvent.event_time.desc().nullslast(),
                EbayEvent.created_at.desc(),
            )
            .first()
        )
        topic_last_event_time: str | None = None
        if topic_latest:
            base_ts = topic_latest.event_time or topic_latest.created_at
            topic_last_event_time = base_ts.isoformat() if base_ts else None

        topic_status_flag: str | None = None
        if topic_error_reason is not None:
            topic_status_flag = "ERROR"
        elif t_dest_status == "ENABLED" and (
            not t_verification_status or t_verification_status in ("CONFIRMED", "VERIFIED")
        ) and t_sub_status == "ENABLED":
            topic_status_flag = "OK"

        topics_payload.append(
            {
                "topicId": topic_id,
                "scope": topic_scope,
                "destinationId": t_dest_id,
                "subscriptionId": t_sub_id,
                "destinationStatus": t_dest_status,
                "subscriptionStatus": t_sub_status,
                "verificationStatus": t_verification_status,
                "tokenType": token_type,
                "status": topic_status_flag,
                "error": topic_error_summary,
                "recentEvents": {
                    "count": topic_recent_count,
                    "lastEventTime": topic_last_event_time,
                },
            }
        )

        # Derive a concise error summary for non-OK states so the UI does not
        # have to guess based on ``state``/``reason``.
        error_summary: Optional[str] = None
        if state == "no_events":
            error_summary = "No recent events received for the primary webhook topic in the last 24 hours."
        elif state == "misconfigured":
            if reason == "no_destination":
                error_summary = "Notification destination does not exist for the configured webhook URL."
            elif reason == "destination_disabled":
                error_summary = "Notification destination is not ENABLED."
            elif reason == "verification_pending":
                # eBay may report UNCONFIRMED / PENDING while the challenge flow is in progress.
                error_summary = "Notification destination verification is not yet complete."
            elif reason == "no_subscription":
                error_summary = "No subscription exists for the primary webhook topic."
            elif reason == "subscription_not_enabled":
                error_summary = "Subscription for the primary webhook topic is not ENABLED."
    ok = state == "ok"

    return {
        "ok": ok,
        "environment": env,
        "webhookUrl": endpoint_url,
        "state": state,
        "reason": reason,
        "destination": dest,
        "subscription": sub,
        "destinationId": dest_id,
        "subscriptionId": sub_id,
        "destinationStatus": dest_status,
        "subscriptionStatus": sub_status,
        "verificationStatus": verification_status,
        "recentEvents": {"count": recent_count, "lastEventTime": last_event_time},
        "checkedAt": checked_at,
        "account": account_info,
        "topics": topics_payload,
        "errorSummary": error_summary,
    }


@router.post("/notifications/test-marketplace-deletion")
async def test_marketplace_account_deletion_notification(
    current_user: User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    """Trigger a Notification API test for MARKETPLACE_ACCOUNT_DELETION.

    This endpoint ensures that a destination and subscription exist for the
    configured webhook URL, then calls the Notification API test operation.
    """

    from ..models_sqlalchemy.models import EbayAccount, EbayToken  # avoid cycles

    env = settings.EBAY_ENVIRONMENT
    endpoint_url = settings.EBAY_NOTIFICATION_DESTINATION_URL
    logger.info(
        "[notifications:test] Starting MARKETPLACE_ACCOUNT_DELETION test env=%s endpoint_url=%s user_id=%s",
        env,
        endpoint_url,
        current_user.id,
    )

    if not endpoint_url:
        payload = {
            "ok": False,
            "reason": "no_destination_url",
            "message": "EBAY_NOTIFICATION_DESTINATION_URL is not configured on the backend.",
            "environment": env,
        }
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=payload)

    account: Optional[EbayAccount] = (
        db.query(EbayAccount)
        .filter(EbayAccount.org_id == current_user.id, EbayAccount.is_active == True)  # noqa: E712
        .order_by(desc(EbayAccount.connected_at))
        .first()
    )
    if not account:
        payload = {
            "ok": False,
            "reason": "no_account",
            "message": "No active eBay account found for this organization.",
            "environment": env,
        }
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=payload)

    token: Optional[EbayToken] = (
        db.query(EbayToken)
        .filter(EbayToken.ebay_account_id == account.id)
        .order_by(desc(EbayToken.updated_at))
        .first()
    )
    if not token or not token.access_token:
        payload = {
            "ok": False,
            "reason": "no_access_token",
            "message": "No eBay access token available for the selected account.",
            "environment": env,
            "account": {
                "id": str(account.id),
                "username": account.username or account.ebay_user_id,
                "environment": env,
            },
        }
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=payload)

    access_token = token.access_token
    verification_token = settings.EBAY_NOTIFICATION_VERIFICATION_TOKEN
    if not verification_token:
        payload = {
            "ok": False,
            "reason": "no_verification_token",
            "message": "EBAY_NOTIFICATION_VERIFICATION_TOKEN is required to create a destination.",
            "environment": env,
        }
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=payload)

    topic_id = "MARKETPLACE_ACCOUNT_DELETION"
    debug_log: list[str] = []
    account_info = {
        "id": str(account.id),
        "username": account.username or account.ebay_user_id,
        "environment": env,
    }
    try:
        logger.info(
            "[notifications:test] Ensuring destination for account_id=%s username=%s",
            account.id,
            account.username,
        )
        dest = await ebay_service.ensure_notification_destination(
            access_token,
            endpoint_url,
            verification_token=verification_token,
            debug_log=debug_log,
        )
        dest_id = dest.get("destinationId") or dest.get("id")
        logger.info("[notifications:test] Destination ready id=%s", dest_id)

        # For MARKETPLACE_ACCOUNT_DELETION (APPLICATION-scope topic), use an
        # application access token (client_credentials) for subscription and
        # test calls, per eBay Notification API requirements.
        app_access_token = await ebay_service.get_app_access_token()
        debug_log.append("[token] Using eBay application access token (client_credentials) for subscription + test")

        sub = await ebay_service.ensure_notification_subscription(
            access_token,
            dest_id,
            topic_id,
            debug_log=debug_log,
        )
        sub_id = sub.get("subscriptionId") or sub.get("id")
        logger.info("[notifications:test] Subscription ready id=%s status=%s", sub_id, sub.get("status"))

        if not sub_id:
            msg = (
                "Subscription was created or retrieved but subscriptionId is missing; "
                "cannot invoke Notification API test for MARKETPLACE_ACCOUNT_DELETION."
            )
            logger.error("[notifications:test] %s", msg)
            debug_log.append(f"[subscription] ERROR: {msg}")
            payload = {
                "ok": False,
                "reason": "no_subscription_id",
                "message": msg,
                "environment": env,
                "webhookUrl": endpoint_url,
                "logs": debug_log,
                "account": account_info,
            }
            return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=payload)

        test_result = await ebay_service.test_notification_subscription(
            app_access_token,
            sub_id,
            debug_log=debug_log,
        )
        logger.info(
            "[notifications:test] Test notification call completed status_code=%s",
            test_result.get("status_code"),
        )
    except HTTPException as exc:
        detail = exc.detail
        if isinstance(detail, dict):
            notification_error = {
                "status_code": detail.get("status_code", exc.status_code),
                "message": detail.get("message") or str(detail),
                "body": detail.get("body"),
            }
        else:
            notification_error = {
                "status_code": exc.status_code,
                "message": str(detail),
            }

        body_preview = notification_error.get("body")
        if isinstance(body_preview, (dict, list)):
            body_preview = str(body_preview)[:300]
        error_summary = f"Notification API HTTP {notification_error.get('status_code')} - {notification_error.get('message')}"
        if body_preview:
            error_summary += f" | body: {body_preview}"

        logger.error(
            "[notifications:test] Notification API error during test: %s",
            notification_error,
        )
        payload = {
            "ok": False,
            "reason": "notification_api_error",
            "message": "Notification API returned an error while creating destination/subscription or sending the test notification.",
            "environment": env,
            "webhookUrl": endpoint_url,
            "notificationError": notification_error,
            "errorSummary": error_summary,
            "logs": debug_log,
            "account": account_info,
            "error": error_summary,
        }
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=payload)
    except Exception as exc:  # pragma: no cover - defensive catch-all
        logger.error("[notifications:test] Unexpected error during notification test", exc_info=True)
        message = f"Unexpected error: {type(exc).__name__}: {exc}"
        payload = {
            "ok": False,
            "reason": "unexpected_error",
            "message": message,
            "environment": env,
            "webhookUrl": endpoint_url,
            "account": account_info,
            "error": message,
        }
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=payload)

    return {
        "ok": True,
        "environment": env,
        "destinationId": dest_id,
        "subscriptionId": sub_id,
        "message": "Test notification requested; check ebay_events and Notifications UI.",
        "notificationTest": test_result,
        "logs": debug_log,
        "account": account_info,
    }


@router.post("/notifications/test-topic")
async def test_notification_topic(
    body: dict,
    current_user: User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    """Generic Notification API test endpoint for an arbitrary topicId.

    For now this is effectively limited to the topics listed in
    ``SUPPORTED_TOPICS`` (MARKETPLACE_ACCOUNT_DELETION in Phase 1), but the
    wiring is generic so that future order/fulfillment/finances topics can be
    added without changing this handler.
    """

    from ..models_sqlalchemy.models import EbayAccount, EbayToken  # avoid cycles

    env = settings.EBAY_ENVIRONMENT
    endpoint_url = settings.EBAY_NOTIFICATION_DESTINATION_URL

    topic_raw = body.get("topicId") or body.get("topic_id")
    topic_id = str(topic_raw).strip() if topic_raw is not None else ""
    supported_topic_ids = {cfg.topic_id for cfg in SUPPORTED_TOPICS}

    if not topic_id:
        payload = {
            "ok": False,
            "reason": "missing_topic_id",
            "message": "Request body must include topicId.",
            "environment": env,
        }
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=payload)

    if topic_id not in supported_topic_ids:
        payload = {
            "ok": False,
            "reason": "unsupported_topic",
            "message": f"TopicId {topic_id!r} is not configured for this application.",
            "environment": env,
        }
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=payload)

    logger.info(
        "[notifications:test] Starting generic notification test topic=%s env=%s endpoint_url=%s user_id=%s",
        topic_id,
        env,
        endpoint_url,
        current_user.id,
    )

    if not endpoint_url:
        payload = {
            "ok": False,
            "reason": "no_destination_url",
            "message": "EBAY_NOTIFICATION_DESTINATION_URL is not configured on the backend.",
            "environment": env,
        }
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=payload)

    account: Optional[EbayAccount] = (
        db.query(EbayAccount)
        .filter(EbayAccount.org_id == current_user.id, EbayAccount.is_active == True)  # noqa: E712
        .order_by(desc(EbayAccount.connected_at))
        .first()
    )
    if not account:
        payload = {
            "ok": False,
            "reason": "no_account",
            "message": "No active eBay account found for this organization.",
            "environment": env,
        }
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=payload)

    token: Optional[EbayToken] = (
        db.query(EbayToken)
        .filter(EbayToken.ebay_account_id == account.id)
        .order_by(desc(EbayToken.updated_at))
        .first()
    )
    if not token or not token.access_token:
        payload = {
            "ok": False,
            "reason": "no_access_token",
            "message": "No eBay access token available for the selected account.",
            "environment": env,
            "account": {
                "id": str(account.id),
                "username": account.username or account.ebay_user_id,
                "environment": env,
            },
        }
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=payload)

    access_token = token.access_token
    verification_token = settings.EBAY_NOTIFICATION_VERIFICATION_TOKEN
    if not verification_token:
        payload = {
            "ok": False,
            "reason": "no_verification_token",
            "message": "EBAY_NOTIFICATION_VERIFICATION_TOKEN is required to create a destination.",
            "environment": env,
        }
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=payload)

    debug_log: list[str] = []
    account_info = {
        "id": str(account.id),
        "username": account.username or account.ebay_user_id,
        "environment": env,
    }

    try:
        logger.info(
            "[notifications:test] Ensuring destination for account_id=%s username=%s topic=%s",
            account.id,
            account.username,
            topic_id,
        )
        dest = await ebay_service.ensure_notification_destination(
            access_token,
            endpoint_url,
            verification_token=verification_token,
            debug_log=debug_log,
        )
        dest_id = dest.get("destinationId") or dest.get("id")
        logger.info("[notifications:test] Destination ready id=%s", dest_id)

        sub = await ebay_service.ensure_notification_subscription(
            access_token,
            dest_id,
            topic_id,
            debug_log=debug_log,
        )
        sub_id = sub.get("subscriptionId") or sub.get("id")
        logger.info(
            "[notifications:test] Subscription ready id=%s status=%s topic=%s",
            sub_id,
            sub.get("status"),
            topic_id,
        )

        if not sub_id:
            msg = (
                "Subscription was created or retrieved but subscriptionId is missing; "
                f"cannot invoke Notification API test for topic {topic_id}."
            )
            logger.error("[notifications:test] %s", msg)
            debug_log.append(f"[subscription] ERROR: {msg}")
            payload = {
                "ok": False,
                "reason": "no_subscription_id",
                "message": msg,
                "environment": env,
                "webhookUrl": endpoint_url,
                "logs": debug_log,
                "account": account_info,
                "topicId": topic_id,
            }
            return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=payload)

        # Decide which token type to use for the test call based on topic scope.
        topic_meta = await ebay_service.get_notification_topic_metadata(
            access_token,
            topic_id,
            debug_log=debug_log,
        )
        raw_scope = topic_meta.get("scope") if isinstance(topic_meta, dict) else None
        scope_upper = raw_scope.upper() if isinstance(raw_scope, str) else None

        if scope_upper == "APPLICATION":
            app_access_token = await ebay_service.get_app_access_token()
            test_access_token = app_access_token
            debug_log.append(
                "[token] Using eBay application access token (client_credentials) for subscription + test",
            )
            token_type = "application"
        else:
            test_access_token = access_token
            debug_log.append("[token] Using eBay user access token for subscription + test")
            token_type = "user"

        test_result = await ebay_service.test_notification_subscription(
            test_access_token,
            sub_id,
            debug_log=debug_log,
        )
        logger.info(
            "[notifications:test] Test notification call completed status_code=%s topic=%s",
            test_result.get("status_code"),
            topic_id,
        )

        # Optional: process recently received events so that [event] lines can
        # be surfaced in the debug log for this test. This is best-effort and
        # will be a no-op until the ingestion helper is implemented.
        try:
            from ..services.ebay_event_processor import process_pending_events  # type: ignore[attr-defined]

            summary = process_pending_events(limit=50, debug_log=debug_log)
            logger.info(
                "[notifications:test] Processed pending events after test topic=%s summary=%s",
                topic_id,
                summary,
            )
        except Exception:
            # Ingestion failures must not break the Notification API test flow.
            logger.warning(
                "[notifications:test] Failed to process pending events after test for topic=%s",
                topic_id,
                exc_info=True,
            )

    except HTTPException as exc:
        detail = exc.detail
        if isinstance(detail, dict):
            notification_error = {
                "status_code": detail.get("status_code", exc.status_code),
                "message": detail.get("message") or str(detail),
                "body": detail.get("body"),
            }
        else:
            notification_error = {
                "status_code": exc.status_code,
                "message": str(detail),
            }

        body_preview = notification_error.get("body")
        if isinstance(body_preview, (dict, list)):
            body_preview = str(body_preview)[:300]
        error_summary = f"Notification API HTTP {notification_error.get('status_code')} - {notification_error.get('message')}"
        if body_preview:
            error_summary += f" | body: {body_preview}"

        logger.error(
            "[notifications:test] Notification API error during generic test topic=%s error=%s",
            topic_id,
            notification_error,
        )
        payload = {
            "ok": False,
            "reason": "notification_api_error",
            "message": "Notification API returned an error while creating destination/subscription or sending the test notification.",
            "environment": env,
            "webhookUrl": endpoint_url,
            "notificationError": notification_error,
            "errorSummary": error_summary,
            "logs": debug_log,
            "account": account_info,
            "topicId": topic_id,
            "error": error_summary,
            "tokenType": token_type if 'token_type' in locals() else None,
        }
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=payload)
    except Exception as exc:  # pragma: no cover - defensive catch-all
        logger.error(
            "[notifications:test] Unexpected error during generic notification test topic=%s",
            topic_id,
            exc_info=True,
        )
        message = f"Unexpected error: {type(exc).__name__}: {exc}"
        payload = {
            "ok": False,
            "reason": "unexpected_error",
            "message": message,
            "environment": env,
            "webhookUrl": endpoint_url,
            "account": account_info,
            "topicId": topic_id,
            "error": message,
        }
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=payload)

    return {
        "ok": True,
        "environment": env,
        "destinationId": dest_id,
        "subscriptionId": sub_id,
        "message": "Test notification requested; check ebay_events and Notifications UI.",
        "notificationTest": test_result,
        "logs": debug_log,
        "account": account_info,
        "topicId": topic_id,
        "tokenType": token_type,
    }
