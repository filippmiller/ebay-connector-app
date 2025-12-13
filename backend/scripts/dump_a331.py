import os
from pathlib import Path
from typing import Any, Iterable, Sequence

import sqlalchemy as sa
from sqlalchemy import text


OUTPUT_PATH = Path(__file__).resolve().parents[1] / "docs" / "EBAY_ANALYTICS_A331_DUMP.md"
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
            if v is None:
                vals.append("")
            else:
                vals.append(str(v))
        lines.append("| " + " | ".join(vals) + " |")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise SystemExit("DATABASE_URL not set in environment")

    engine = sa.create_engine(db_url)

    sections: list[str] = []

    with engine.connect() as conn:
        # 1) Buying
        sql_buying = """
        SELECT *
        FROM buying
        WHERE storage = :storage_id;
        """
        cols, rows = run_query(conn, sql_buying, {"storage_id": STORAGE_ID})
        sections.append(rows_to_markdown("Buying", sql_buying, cols, rows))

        # 2) Legacy inventory (tbl_parts_inventory)
        sql_legacy_inv = """
        SELECT *
        FROM tbl_parts_inventory
        WHERE "Storage" = :storage_id
           OR "AlternativeStorage" = :storage_id
           OR "StorageAlias" = :storage_id;
        """
        cols, rows = run_query(conn, sql_legacy_inv, {"storage_id": STORAGE_ID})
        sections.append(rows_to_markdown("tbl_parts_inventory (legacy inventory)", sql_legacy_inv, cols, rows))

        # 3) Modern inventory + parts_detail
        sql_inv_pd = """
        SELECT
          i.id                AS inventory_id,
          i.storage_id,
          i.storage,
          i.status,
          i.category,
          i.quantity,
          i.price,
          i.ebay_listing_id,
          i.parts_detail_id,
          pd.sku,
          pd.item_id,
          pd.storage        AS pd_storage
        FROM inventory i
        LEFT JOIN parts_detail pd
          ON pd.id = i.parts_detail_id
        WHERE i.storage_id = :storage_id;
        """
        cols, rows = run_query(conn, sql_inv_pd, {"storage_id": STORAGE_ID})
        sections.append(rows_to_markdown("Inventory + parts_detail", sql_inv_pd, cols, rows))

        # 4) DISTINCT SKU / ItemID
        sql_sku_item = """
        SELECT DISTINCT
          pd.sku,
          pd.item_id
        FROM inventory i
        LEFT JOIN parts_detail pd
          ON pd.id = i.parts_detail_id
        WHERE i.storage_id = :storage_id;
        """
        cols, rows = run_query(conn, sql_sku_item, {"storage_id": STORAGE_ID})
        sections.append(rows_to_markdown("Distinct SKU / ItemID for A331", sql_sku_item, cols, rows))

        # 5) Legacy eBay buyer
        sql_legacy_buyer = """
        SELECT *
        FROM tbl_ebay_buyer
        WHERE "Storage" = :storage_id
           OR "ItemID" IN (
             SELECT DISTINCT pd.item_id
             FROM inventory i
             JOIN parts_detail pd ON pd.id = i.parts_detail_id
             WHERE i.storage_id = :storage_id
           );
        """
        cols, rows = run_query(conn, sql_legacy_buyer, {"storage_id": STORAGE_ID})
        sections.append(rows_to_markdown("tbl_ebay_buyer (legacy buyer)", sql_legacy_buyer, cols, rows))

        # 6) Legacy fees for this Storage (narrowed to concrete keys to avoid timeouts)
        sql_legacy_fees = """
        SELECT f.*
        FROM tbl_ebay_fees f
        WHERE EXISTS (
            SELECT 1
            FROM tbl_ebay_buyer b
            WHERE b."Storage" = :storage_id
              AND (
                (b."ItemID" IS NOT NULL AND b."ItemID" = f."ItemID") OR
                (b."TransactionID" IS NOT NULL AND b."TransactionID" = f."TransactionID")
              )
        );
        """
        cols, rows = run_query(conn, sql_legacy_fees, {"storage_id": STORAGE_ID})
        sections.append(rows_to_markdown("tbl_ebay_fees (legacy fees, filtered by matching buyer rows)", sql_legacy_fees, cols, rows))

        # Helper CTE base for SKU list
        # 7) Modern transactions by SKU
        sql_tx = """
        WITH inv AS (
          SELECT DISTINCT pd.sku
          FROM inventory i
          JOIN parts_detail pd ON pd.id = i.parts_detail_id
          WHERE i.storage_id = :storage_id
            AND pd.sku IS NOT NULL
        )
        SELECT t.*
        FROM transactions t
        WHERE t.sku IN (SELECT sku FROM inv);
        """
        cols, rows = run_query(conn, sql_tx, {"storage_id": STORAGE_ID})
        sections.append(rows_to_markdown("Modern transactions by SKU", sql_tx, cols, rows))

        # 8) Order line items by SKU
        sql_oli = """
        WITH inv AS (
          SELECT DISTINCT pd.sku
          FROM inventory i
          JOIN parts_detail pd ON pd.id = i.parts_detail_id
          WHERE i.storage_id = :storage_id
            AND pd.sku IS NOT NULL
        )
        SELECT oli.*
        FROM order_line_items oli
        WHERE oli.sku IN (SELECT sku FROM inv);
        """
        cols, rows = run_query(conn, sql_oli, {"storage_id": STORAGE_ID})
        sections.append(rows_to_markdown("order_line_items by SKU", sql_oli, cols, rows))

        # 9) Finances transactions
        sql_fin_tx = """
        WITH tx AS (
          SELECT DISTINCT
            t.order_id,
            t.line_item_id
          FROM transactions t
          JOIN (
            SELECT DISTINCT pd.sku
            FROM inventory i
            JOIN parts_detail pd ON pd.id = i.parts_detail_id
            WHERE i.storage_id = :storage_id
              AND pd.sku IS NOT NULL
          ) inv ON inv.sku = t.sku
        )
        SELECT eft.*
        FROM ebay_finances_transactions eft
        WHERE eft.order_id IN (SELECT order_id FROM tx)
           OR eft.order_line_item_id IN (SELECT line_item_id FROM tx);
        """
        cols, rows = run_query(conn, sql_fin_tx, {"storage_id": STORAGE_ID})
        sections.append(rows_to_markdown("ebay_finances_transactions for A331", sql_fin_tx, cols, rows))

        # 10) Finances fees for those transactions
        sql_fin_fees = """
        WITH fin AS (
          SELECT DISTINCT transaction_id
          FROM ebay_finances_transactions eft
          WHERE eft.order_id IN (
                  SELECT DISTINCT t.order_id
                  FROM transactions t
                  JOIN (
                    SELECT DISTINCT pd.sku
                    FROM inventory i
                    JOIN parts_detail pd ON pd.id = i.parts_detail_id
                    WHERE i.storage_id = :storage_id
                      AND pd.sku IS NOT NULL
                  ) inv ON inv.sku = t.sku
               )
             OR eft.order_line_item_id IN (
                  SELECT DISTINCT t.line_item_id
                  FROM transactions t
                  JOIN (
                    SELECT DISTINCT pd.sku
                    FROM inventory i
                    JOIN parts_detail pd ON pd.id = i.parts_detail_id
                    WHERE i.storage_id = :storage_id
                      AND pd.sku IS NOT NULL
                  ) inv ON inv.sku = t.sku
               )
        )
        SELECT eff.*
        FROM ebay_finances_fees eff
        WHERE eff.transaction_id IN (SELECT transaction_id FROM fin);
        """
        cols, rows = run_query(conn, sql_fin_fees, {"storage_id": STORAGE_ID})
        sections.append(rows_to_markdown("ebay_finances_fees for A331", sql_fin_fees, cols, rows))

    # 11) Example combined tree query (not executed, just documented)
    example_sql = """
WITH inv AS (
  SELECT
    i.id          AS inventory_id,
    i.storage_id,
    i.status      AS inventory_status,
    i.ebay_listing_id,
    pd.sku,
    pd.item_id
  FROM inventory i
  LEFT JOIN parts_detail pd ON pd.id = i.parts_detail_id
  WHERE i.storage_id = 'A331'
),
tx AS (
  SELECT
    t.transaction_id,
    t.order_id,
    t.line_item_id,
    t.sku,
    t.sale_value,
    t.currency
  FROM transactions t
  JOIN inv ON inv.sku = t.sku
),
fin AS (
  SELECT
    eft.transaction_id,
    eft.order_id,
    eft.order_line_item_id,
    eft.transaction_amount_value,
    eft.transaction_amount_currency
  FROM ebay_finances_transactions eft
  JOIN tx ON tx.order_id = eft.order_id
          OR tx.line_item_id = eft.order_line_item_id
),
fees AS (
  SELECT
    eff.transaction_id,
    SUM(eff.amount_value) AS total_fee
  FROM ebay_finances_fees eff
  GROUP BY eff.transaction_id
)
SELECT
  inv.storage_id,
  inv.inventory_id,
  inv.sku,
  inv.item_id,
  tx.transaction_id,
  tx.order_id,
  tx.line_item_id,
  tx.sale_value,
  tx.currency,
  fin.transaction_amount_value,
  fin.transaction_amount_currency,
  fees.total_fee
FROM inv
LEFT JOIN tx   ON tx.sku = inv.sku
LEFT JOIN fin  ON fin.transaction_id = tx.transaction_id
LEFT JOIN fees ON fees.transaction_id = fin.transaction_id
ORDER BY inv.inventory_id, tx.transaction_id;
"""

    sections.append("# A331 Analytics Dump (StorageID = 'A331')\n")
    sections.append("\n## Example combined SELECT (not executed)\n")
    sections.append("```sql")
    sections.append(example_sql.strip())
    sections.append("```")

    content = "\n\n".join(sections) + "\n"
    OUTPUT_PATH.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    main()
