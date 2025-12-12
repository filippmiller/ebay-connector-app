from sqlalchemy import create_engine, inspect

import os

# Direct DATABASE_URL fallback mirroring add_missing_columns.py so this script
# can run outside the FastAPI app context.
DEFAULT_DB_URL = "postgresql://postgres:EVfiVxDuuwRa8hAx@db.nrpfahjygulsfxmbmfzv.supabase.co:5432/postgres?sslmode=require"


def main() -> None:
    db_url = os.environ.get("DATABASE_URL") or DEFAULT_DB_URL
    engine = create_engine(db_url)
    insp = inspect(engine)

    tables = insp.get_table_names()
    print("TABLES:", tables)

    candidates = [t for t in tables if t.lower().startswith("sku") or "catalog" in t.lower() or "sq" in t.lower()]
    print("CANDIDATES:", candidates)

    for t in candidates:
        cols = insp.get_columns(t)
        print("TABLE", t, "COLUMNS:", [c["name"] for c in cols])


if __name__ == "__main__":
    main()
