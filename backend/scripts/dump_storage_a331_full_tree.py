import os
from pathlib import Path
from typing import Any, Iterable, Sequence

import sqlalchemy as sa
from sqlalchemy import text

OUTPUT_PATH = Path(__file__).resolve().parents[1] / "docs" / "EBAY_ANALYTICS_A331_FULL_TREE.md"
STORAGE_ID = "a331"  # use lower-case for comparisons


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
    sections.append("# Storage A331 — Full Lifecycle Analysis (Legacy)\n")

    with engine.connect() as conn:
        # 1.1 Buying
        sql_buying = """
        SELECT *
        FROM buying
        WHERE lower(trim(storage)) = lower(:storage_id)
           OR lower(trim(storage)) LIKE lower('%' || :storage_id || '%');
        """
        cols, rows = run_query(conn, sql_buying, {"storage_id": STORAGE_ID})
        sections.append(rows_to_markdown("Buying (Storage A331)", sql_buying, cols, rows))

        # 1.2 Parts Inventory (all details)
        sql_parts_inv = """
        SELECT *
        FROM tbl_parts_inventory
        WHERE lower(trim("Storage")) = lower(:storage_id)
           OR lower(trim("AlternativeStorage")) = lower(:storage_id);
        """
        cols, rows = run_query(conn, sql_parts_inv, {"storage_id": STORAGE_ID})
        sections.append(rows_to_markdown("Inventory (tbl_parts_inventory, A331)", sql_parts_inv, cols, rows))

        # 1.2 Distinct SKU/OverrideSKU/ItemID/UserName/StatusSKU
        sql_parts_distinct = """
        SELECT DISTINCT
          "SKU",
          "OverrideSKU",
          "ItemID",
          "UserName",
          "StatusSKU"
        FROM tbl_parts_inventory
        WHERE lower(trim("Storage")) = lower(:storage_id)
           OR lower(trim("AlternativeStorage")) = lower(:storage_id);
        """
        cols, rows = run_query(conn, sql_parts_distinct, {"storage_id": STORAGE_ID})
        sections.append(rows_to_markdown("Inventory Distinct (SKU / OverrideSKU / ItemID / UserName / StatusSKU)", sql_parts_distinct, cols, rows))

        # 1.3 Buyer (sales)
        sql_buyer = """
        SELECT *
        FROM tbl_ebay_buyer
        WHERE lower(trim("Storage")) = lower(:storage_id)
           OR lower(trim("ItemID")) IN (
              SELECT lower(trim("ItemID"))
              FROM tbl_parts_inventory
              WHERE lower(trim("Storage")) = lower(:storage_id)
           );
        """
        cols, rows = run_query(conn, sql_buyer, {"storage_id": STORAGE_ID})
        sections.append(rows_to_markdown("First & Second sales (tbl_ebay_buyer, A331)", sql_buyer, cols, rows))

        # 1.4 Buyer Log (history, profit/refund)
        sql_buyer_log = """
        SELECT *
        FROM tbl_ebay_buyer_log
        WHERE lower(trim("Storage")) = lower(:storage_id)
           OR lower(trim("ItemID")) IN (
              SELECT lower(trim("ItemID"))
              FROM tbl_parts_inventory
              WHERE lower(trim("Storage")) = lower(:storage_id)
           );
        """
        cols, rows = run_query(conn, sql_buyer_log, {"storage_id": STORAGE_ID})
        sections.append(rows_to_markdown("BuyerLog (tbl_ebay_buyer_log, A331)", sql_buyer_log, cols, rows))

        # 1.5 Parts DETAIL LOG (by SKU)
        try:
            sql_parts_detail_log = """
            SELECT *
            FROM tbl_parts_detail_log
            WHERE lower(trim("SKU")) IN (
              SELECT lower(trim("SKU"))
              FROM tbl_parts_inventory
              WHERE lower(trim("Storage")) = lower(:storage_id)
            );
            """
            cols, rows = run_query(conn, sql_parts_detail_log, {"storage_id": STORAGE_ID})
            sections.append(rows_to_markdown("PartsDetailLog (tbl_parts_detail_log, by SKU for A331)", sql_parts_detail_log, cols, rows))
        except Exception:
            sections.append("## PartsDetailLog (tbl_parts_detail_log, by SKU for A331)\n")
            sections.append("tbl_parts_detail_log not present in this database; skipping query.\n")

        # 1.6 Parts INVENTORY LOG (if exists)
        try:
            sql_parts_inventory_log = """
            SELECT *
            FROM tbl_parts_inventory_log
            WHERE lower(trim("Storage")) = lower(:storage_id);
            """
            cols, rows = run_query(conn, sql_parts_inventory_log, {"storage_id": STORAGE_ID})
            sections.append(rows_to_markdown("PartsInventoryLog (tbl_parts_inventory_log, A331)", sql_parts_inventory_log, cols, rows))
        except Exception:
            sections.append("## PartsInventoryLog (tbl_parts_inventory_log, A331)\n")
            sections.append("tbl_parts_inventory_log not present in this database; skipping query.\n")

        # 2. Combined tree SELECT (not executed here, just documented)
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
  WHERE lower(trim(pi."Storage")) = lower('a331')
     OR lower(trim(pi."AlternativeStorage")) = lower('a331')
),
buy AS (
  SELECT *
  FROM buying
  WHERE lower(trim(storage)) = lower('a331')
     OR lower(trim(storage)) LIKE lower('%a331%')
),
buyer AS (
  SELECT
    b.* 
  FROM tbl_ebay_buyer b
  WHERE lower(trim(b."Storage")) = lower('a331')
     OR lower(trim(b."ItemID")) IN (SELECT lower(trim("ItemID")) FROM inv)
),
buyer_log AS (
  SELECT
    bl.*
  FROM tbl_ebay_buyer_log bl
  WHERE lower(trim(bl."Storage")) = lower('a331')
     OR lower(trim(bl."ItemID")) IN (SELECT lower(trim("ItemID")) FROM inv)
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
LEFT JOIN buyer    ON lower(trim(buyer."ItemID"))  = lower(trim(inv."ItemID"))
                  AND lower(trim(buyer."Storage")) = lower(trim(inv.storage))
LEFT JOIN buyer_log bl ON lower(trim(bl."ItemID")) = lower(trim(inv."ItemID"))
                      AND lower(trim(bl."Storage")) = lower(trim(inv.storage))
ORDER BY inv.parts_inventory_id, buyer."TransactionID";
"""

    sections.append("## Combined SELECT (tree)\n")
    sections.append("```sql")
    sections.append(combined_sql.strip())
    sections.append("```")

    OUTPUT_PATH.write_text("\n\n".join(sections) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
