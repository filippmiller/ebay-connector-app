from datetime import datetime, timezone, timedelta
import os
from pathlib import Path

from sqlalchemy import inspect, text


backend_root = Path(__file__).resolve().parent.parent


def _ensure_database_url_from_env() -> str:
    """Ensure DATABASE_URL is set in os.environ.

    Priority:
    1. Existing DATABASE_URL
    2. SUPABASE_DB_SESSION_URL
    3. SUPABASE_DB_DIRECT_URL
    4. SUPABASE_URL (last-resort, may not be a full DSN)
    """
    # Try direct env first (in Railway run this should already be present)
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        db_url = (
            os.environ.get("SUPABASE_DB_SESSION_URL")
            or os.environ.get("SUPABASE_DB_DIRECT_URL")
            or os.environ.get("SUPABASE_URL")
        )
        if db_url:
            os.environ["DATABASE_URL"] = db_url
    if not os.environ.get("DATABASE_URL"):
        raise RuntimeError("DATABASE_URL not set even after SUPABASE_* fallback")
    return os.environ["DATABASE_URL"]


from typing import List, Dict, Any


def _snapshot_accounts_and_tokens(engine) -> (List[Dict[str, Any]], List[Dict[str, Any]]):
    from sqlalchemy import text as _text

    accounts: List[Dict[str, Any]] = []
    rows: List[Dict[str, Any]] = []

    with engine.connect() as conn:
        acc_rows = conn.execute(
            _text(
                "SELECT id, ebay_user_id, username, house_name, is_active, connected_at "
                "FROM ebay_accounts WHERE is_active = true ORDER BY connected_at ASC"
            )
        ).mappings().all()
        for acc in acc_rows:
            accounts.append(dict(acc))

        for acc in accounts:
            tok_rows = conn.execute(
                _text(
                    "SELECT id, ebay_account_id, expires_at, last_refreshed_at, "
                    "refresh_error, created_at, updated_at "
                    "FROM ebay_tokens WHERE ebay_account_id = :acc_id LIMIT 1"
                ),
                {"acc_id": acc["id"]},
            ).mappings().all()

            if not tok_rows:
                rows.append(
                    {
                        "house_name": acc["house_name"],
                        "ebay_account_id": acc["id"],
                        "expires_at": None,
                        "last_refreshed_at": None,
                        "refresh_error": None,
                        "created_at": None,
                        "updated_at": None,
                    }
                )
                continue

            tok = tok_rows[0]
            def _iso(val):
                return val.isoformat() if hasattr(val, "isoformat") else (str(val) if val is not None else None)

            rows.append(
                {
                    "house_name": acc["house_name"],
                    "ebay_account_id": tok["ebay_account_id"],
                    "expires_at": _iso(tok["expires_at"]),
                    "last_refreshed_at": _iso(tok["last_refreshed_at"]),
                    "refresh_error": (tok["refresh_error"] or "").replace("\n", " ")[:300]
                    if tok["refresh_error"]
                    else None,
                    "created_at": _iso(tok["created_at"]),
                    "updated_at": _iso(tok["updated_at"]),
                }
            )

    return accounts, rows


def _find_refresh_log_tables(engine):
    insp = inspect(engine)
    tables = insp.get_table_names()
    candidates = [t for t in tables if "refresh" in t.lower() and "token" in t.lower()]
    return candidates


def _dump_refresh_logs_generic(engine, table_name: str, account_ids):
    """Best-effort dump of recent refresh logs for given ebay_account_ids.

    This assumes the table has ebay_account_id and started_at-ish columns.
    Returns dict[account_id] -> list[rows].
    """
    from collections import defaultdict

    result = defaultdict(list)
    with engine.connect() as conn:
        insp = inspect(engine)
        cols = [c["name"] for c in insp.get_columns(table_name)]

        started_col = "started_at" if "started_at" in cols else ("created_at" if "created_at" in cols else None)
        finished_col = "finished_at" if "finished_at" in cols else ("completed_at" if "completed_at" in cols else None)

        since = datetime.now(timezone.utc) - timedelta(days=7)
        where_parts = ["ebay_account_id = :acc_id"]
        params = {}
        if started_col:
            where_parts.append(f"{started_col} >= :since")
            params["since"] = since
        where_clause = " AND ".join(where_parts)

        for acc_id in account_ids:
            params_local = dict(params)
            params_local["acc_id"] = acc_id
            order_by = started_col or finished_col or cols[0]
            sql = text(
                f"SELECT * FROM {table_name} WHERE {where_clause} "
                f"ORDER BY {order_by} ASC LIMIT 20"
            )
            rows = conn.execute(sql, params_local).fetchall()
            compact_rows = []
            for row in rows[-10:]:
                as_dict = dict(row._mapping)
                # Trim noisy fields
                for k in list(as_dict.keys()):
                    v = as_dict[k]
                    if isinstance(v, str) and len(v) > 200:
                        as_dict[k] = v[:200] + "..."
                compact_rows.append(as_dict)
            result[acc_id] = compact_rows
    return result


from sqlalchemy import create_engine


def main():
    # 1) Ensure DATABASE_URL is set (using Railway env inside `railway run`)
    db_url = _ensure_database_url_from_env()

    # 2) Create engine directly from DATABASE_URL (no app imports)
    engine = create_engine(db_url)

    # 3) Snapshot accounts/tokens
    accounts, token_rows = _snapshot_accounts_and_tokens(engine)
    account_ids = [a["id"] for a in accounts]

    # 4) Try to discover any token-refresh log tables and pull last 7 days
    log_tables = _find_refresh_log_tables(engine)
    logs_by_table = {}
    for tname in log_tables:
        logs_by_table[tname] = _dump_refresh_logs_generic(engine, tname, account_ids)

    # 5) Emit compact JSON-like summary to stdout
    import json

    summary = {
        "db_url_source": "DATABASE_URL" if "postgresql" in db_url else "SUPABASE_FALLBACK",
        "token_state": token_rows,
        "refresh_logs": logs_by_table,
    }
    print(json.dumps(summary, default=str, indent=2))


if __name__ == "__main__":
    main()
