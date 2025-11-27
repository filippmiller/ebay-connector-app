import os

import sqlalchemy as sa
from sqlalchemy import text


TABLES = [
    "buying",
    "inventory",
    "parts_detail",
    "transactions",
    "order_line_items",
    "ebay_finances_transactions",
    "ebay_finances_fees",
    "tbl_ebay_buyer",
    "tbl_ebay_fees",
    "tbl_parts_inventory",
]


def main() -> None:
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise SystemExit("DATABASE_URL not set in environment")

    engine = sa.create_engine(db_url)

    with engine.connect() as conn:
        prefix = db_url.split("@", 1)[0]
        print(f"# DB Introspection\n")
        print(f"*DATABASE_URL prefix*: `{prefix}`\n")

        # 1) List all tables in public
        print("## All tables in schema `public`\n")
        res = conn.execute(
            text(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                ORDER BY table_name;
                """
            )
        )
        print("| table_name |\n|------------|")
        for row in res:
            print(f"| {row.table_name} |")

        # 2) Columns for key tables in Markdown format
        print("\n## Key tables (columns)\n")
        res = conn.execute(
            text(
                """
                SELECT
                  table_name,
                  column_name,
                  data_type
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = ANY(:tables)
                ORDER BY table_name, ordinal_position;
                """
            ),
            {"tables": TABLES},
        )

        current_table = None
        rows = []
        for table_name, column_name, data_type in res:
            if current_table is None:
                current_table = table_name
            if table_name != current_table:
                _print_table_markdown(current_table, rows)
                current_table = table_name
                rows = []
            rows.append((column_name, data_type))

        if current_table is not None:
            _print_table_markdown(current_table, rows)


def _print_table_markdown(table_name: str, rows: list[tuple[str, str]]) -> None:
    print(f"\n### `{table_name}`\n")
    if not rows:
        print("_No columns found_\n")
        return
    print("| column_name | data_type |\n|-------------|-----------|")
    for col, dtype in rows:
        print(f"| {col} | {dtype} |")


if __name__ == "__main__":
    main()
