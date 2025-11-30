import os
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from sqlalchemy import text

OUTPUT_PATH = Path(__file__).resolve().parents[1] / "docs" / "EBAY_LEGACY_SCHEMA_CORE.md"
TABLES = [
    "buying",
    "tbl_parts_inventory",
    "tbl_ebay_buyer",
    "tbl_ebay_buyer_log",
    "tbl_parts_detail_log",
]


def main() -> None:
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise SystemExit("DATABASE_URL not set in environment")

    engine = sa.create_engine(db_url)

    with engine.connect() as conn:
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

        sections: list[str] = []
        sections.append("# Legacy Core Schema (buying + parts/buyer logs)\n")

        current_table: str | None = None
        rows: list[tuple[str, str]] = []

        for table_name, column_name, data_type in res:
            if current_table is None:
                current_table = table_name
            if table_name != current_table:
                sections.append(render_table(current_table, rows))
                current_table = table_name
                rows = []
            rows.append((column_name, data_type))

        if current_table is not None:
            sections.append(render_table(current_table, rows))

    OUTPUT_PATH.write_text("\n\n".join(sections) + "\n", encoding="utf-8")


def render_table(table_name: str, rows: list[tuple[str, str]]) -> str:
    lines: list[str] = []
    lines.append(f"## `{table_name}`\n")
    if not rows:
        lines.append("_No columns found_\n")
        return "\n".join(lines)
    lines.append("| column_name | data_type |")
    lines.append("|-------------|-----------|")
    for col, dtype in rows:
        lines.append(f"| {col} | {dtype} |")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
