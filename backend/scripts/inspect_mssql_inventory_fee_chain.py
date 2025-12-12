import os
import sys

# Ensure the backend root (which contains the `app` package) is on sys.path
BACKEND_ROOT = os.path.dirname(os.path.dirname(__file__))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from app.services.mssql_client import MssqlConnectionConfig, create_engine_for_session
from sqlalchemy import text

TABLES = [
    "tbl_parts_Inventory",
    "tbl_ebay_InventorySold",
    "tbl_ebay_SellerTransactions",
    "tbl_ebay_seller_info",
    "tbl_ebay_fees",
    "tbl_ListingFees",
]


def main() -> None:
    cfg = MssqlConnectionConfig(database="DB_A28F26_parts")
    engine = create_engine_for_session(cfg)

    with engine.connect() as conn:
        for table in TABLES:
            print("=" * 80)
            print(f"Table: dbo.{table}")
            print("-- COLUMNS --")
            cols = conn.execute(
                text(
                    """
                    SELECT COLUMN_NAME, DATA_TYPE, COLLATION_NAME
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_SCHEMA = 'dbo'
                      AND TABLE_NAME = :t
                    ORDER BY ORDINAL_POSITION
                    """
                ),
                {"t": table},
            ).fetchall()
            for name, dtype, coll in cols:
                print(f"{name:40} {dtype:20} {coll}")

            print("-- TOP 5 --")
            preview = conn.execute(text(f"SELECT TOP 5 * FROM dbo.{table}"))
            rows = preview.mappings().all()
            if not rows:
                print("[no rows]")
            else:
                columns = list(rows[0].keys())
                print(" | ".join(columns))
                for r in rows:
                    print(
                        " | ".join(
                            "" if r[c] is None else str(r[c])
                            for c in columns
                        )
                    )


if __name__ == "__main__":
    main()
