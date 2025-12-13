import os
from pathlib import Path
from typing import Any, Iterable, Sequence

import sqlalchemy as sa
from sqlalchemy import text

OUTPUT_PATH = Path(__file__).resolve().parents[1] / "docs" / "EBAY_ANALYTICS_A331_LEGACY.md"
STORAGE_ID = "A331"


def run_query(conn, sql: str, params: dict[str, Any] | None = None):
    result = conn.execute(text(sql), params or {})
    rows = result.fetchall()
    columns = result.keys()
    return columns, rows


def rows_to_markdown(title: str, sql: str, columns: Iterable[str], rows: Sequence[Sequence[Any]]) -> str:
    lines: list[str] = []
    lines.append(f"## {title}\n")
    lines.append("### SQL")
    lines.append("```sql")
    lines.append(sql.strip())
    lines.append("```")
    lines.append("\n### Result")
    if not rows:
        lines.append("_No rows_\n")
        return "\n".join(lines)

    cols = list(columns)
    header = "| " + " | ".join(cols) + " |"
    sep = "|" + "|".join(["-" * (len(c) + 2) for c in cols]) + "|"
    lines.append(header)
    lines.append(sep)
    for row in rows:
        vals = []
        for v in row:
            vals.append("" if v is None else str(v))
        lines.append("| " + " | ".join(vals) + " |")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise SystemExit("DATABASE_URL not set in environment")

    engine = sa.create_engine(db_url)

    sections: list[str] = []
    sections.append("# Legacy Analytics Dump for StorageID 'A331'\n")

    with engine.connect() as conn:
        # 1.1 Buying
        sql_buying = """
        SELECT *
        FROM buying
        WHERE storage = :storage_id
           OR storage ILIKE :storage_prefix;
        """
        cols, rows = run_query(conn, sql_buying, {"storage_id": STORAGE_ID, "storage_prefix": STORAGE_ID + "%"})
        sections.append(rows_to_markdown("Buying (A331)", sql_buying, cols, rows))

        # 1.2 Parts inventory
        sql_parts_inv = """
        SELECT *
        FROM tbl_parts_inventory
        WHERE "Storage" = :storage_id
           OR "AlternativeStorage" = :storage_id;
        """
        cols, rows = run_query(conn, sql_parts_inv, {"storage_id": STORAGE_ID})
        sections.append(rows_to_markdown("PartsInventory (tbl_parts_inventory, A331)", sql_parts_inv, cols, rows))

        # DISTINCT SKU/OverrideSKU/ItemID/UserName/StatusSKU
        sql_parts_distinct = """
        SELECT DISTINCT
          "SKU",
          "OverrideSKU",
          "ItemID",
          "UserName",
          "StatusSKU"
        FROM tbl_parts_inventory
        WHERE "Storage" = :storage_id
           OR "AlternativeStorage" = :storage_id;
        """
        cols, rows = run_query(conn, sql_parts_distinct, {"storage_id": STORAGE_ID})
        sections.append(rows_to_markdown("Distinct SKU/OverrideSKU/ItemID/UserName/StatusSKU", sql_parts_distinct, cols, rows))

        # 1.3 Legacy eBay buyer
        sql_buyer = """
        SELECT *
        FROM tbl_ebay_buyer
        WHERE "Storage" = :storage_id
           OR "ItemID" IN (
               SELECT DISTINCT "ItemID"
               FROM tbl_parts_inventory
               WHERE "Storage" = :storage_id
                  OR "AlternativeStorage" = :storage_id
           );
        """
        cols, rows = run_query(conn, sql_buyer, {"storage_id": STORAGE_ID})
        sections.append(rows_to_markdown("EbayBuyer (tbl_ebay_buyer, A331)", sql_buyer, cols, rows))

        # 1.4 Legacy eBay buyer log
        sql_buyer_log = """
        SELECT *
        FROM tbl_ebay_buyer_log
        WHERE "Storage" = :storage_id
           OR "ItemID" IN (
               SELECT DISTINCT "ItemID"
               FROM tbl_parts_inventory
               WHERE "Storage" = :storage_id
                  OR "AlternativeStorage" = :storage_id
           );
        """
        cols, rows = run_query(conn, sql_buyer_log, {"storage_id": STORAGE_ID})
        sections.append(rows_to_markdown("EbayBuyerLog (tbl_ebay_buyer_log, A331)", sql_buyer_log, cols, rows))

        # 1.5 Parts detail log by SKU (only if table exists)
        try:
            sql_parts_detail_log = """
            SELECT *
            FROM tbl_parts_detail_log
            WHERE "SKU" IN (
                SELECT DISTINCT "SKU"
                FROM tbl_parts_inventory
                WHERE "Storage" = :storage_id
                   OR "AlternativeStorage" = :storage_id
            );
            """
            cols, rows = run_query(conn, sql_parts_detail_log, {"storage_id": STORAGE_ID})
            sections.append(rows_to_markdown("PartsDetailLog (tbl_parts_detail_log, by SKU for A331)", sql_parts_detail_log, cols, rows))
        except Exception as e:
            # Table may not exist yet in this Supabase schema
            sections.append("## PartsDetailLog (tbl_parts_detail_log, by SKU for A331)\n")
            sections.append("tbl_parts_detail_log not present in this database; skipping query.\n")

    # Combined SELECT (tree) - documented but not executed here
    combined_sql = """
WITH inv AS (
  SELECT
    pi."ID"              AS parts_inventory_id,
    pi."Storage"         AS storage,
    pi."AlternativeStorage",
    pi."SKU",
    pi."OverrideSKU",
    pi."ItemID",
    pi."Quantity",
    pi."OverridePrice",
    pi."OverrideTitle",
    pi."UserName",
    pi."StatusSKU"
  FROM tbl_parts_inventory pi
  WHERE pi."Storage" = 'A331'
     OR pi."AlternativeStorage" = 'A331'
),
buy AS (
  SELECT *
  FROM buying
  WHERE storage = 'A331'
     OR storage ILIKE 'A331%'
),
buyer AS (
  SELECT
    b.* 
  FROM tbl_ebay_buyer b
  WHERE b."Storage" = 'A331'
     OR b."ItemID" IN (SELECT DISTINCT "ItemID" FROM inv)
),
buyer_log AS (
  SELECT
    bl.*
  FROM tbl_ebay_buyer_log bl
  WHERE bl."Storage" = 'A331'
     OR bl."ItemID" IN (SELECT DISTINCT "ItemID" FROM inv)
)
SELECT
  inv.storage,
  inv.parts_inventory_id,
  inv."SKU",
  inv."ItemID",
  inv."OverridePrice",
  inv."OverrideTitle",
  buyer."TransactionID",
  buyer."OrderLineItemID",
  buyer."TotalPrice",
  buyer."TotalTransactionPrice",
  buyer."ShippingServiceCost",
  buyer."BuyerID",
  buyer."PaidTime",
  buyer."ShippedTime",
  buyer_log."Profit",
  buyer_log."Refund",
  buyer_log."RefundFlag"
FROM inv
LEFT JOIN buyer    ON buyer."ItemID"   = inv."ItemID"
                  AND buyer."Storage"  = inv.storage
LEFT JOIN buyer_log bl ON bl."ItemID"  = inv."ItemID"
                      AND bl."Storage" = inv.storage
ORDER BY inv.parts_inventory_id, buyer."TransactionID";
"""

    sections.append("## Combined SELECT (tree)\n")
    sections.append("```sql")
    sections.append(combined_sql.strip())
    sections.append("```")

    OUTPUT_PATH.write_text("\n\n".join(sections) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
