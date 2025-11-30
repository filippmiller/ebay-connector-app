import os
from pathlib import Path
from typing import Any, Iterable, Sequence

import sqlalchemy as sa
from sqlalchemy import text

OUTPUT_PATH = Path(__file__).resolve().parents[1] / "docs" / "EBAY_ANALYTICS_A331_CHAIN.md"
STORAGE_ID = "a331"  # lower-case input for comparisons


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
        vals = ["" if v is None else str(v) for v in row]
        lines.append("| " + " | ".join(vals) + " |")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise SystemExit("DATABASE_URL not set in environment")

    engine = sa.create_engine(db_url)

    sections: list[str] = []
    sections.append("# Storage A331 — Inventory → Sales → SellerTransactions → Fees (Legacy)\n")

    with engine.connect() as conn:
        # 1. Schema introspection
        schema_sql = """
        SELECT 
          table_name, 
          column_name, 
          data_type
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name IN (
            'tbl_parts_inventory',
            'tbl_ebay_buyer',
            'tbl_ebay_buyer_log',
            'ebay_sellerTransactions',
            'tbl_ebay_fees'
          )
        ORDER BY table_name, ordinal_position;
        """
        cols, rows = run_query(conn, schema_sql)
        sections.append("## Schema\n")
        sections.append("```sql")
        sections.append(schema_sql.strip())
        sections.append("```\n")
        if rows:
            sections.append("| table_name | column_name | data_type |")
            sections.append("|------------|-------------|-----------|")
            for table_name, column_name, data_type in rows:
                sections.append(f"| {table_name} | {column_name} | {data_type} |")
            sections.append("")
        else:
            sections.append("_No columns found for requested tables._\n")

        # 2. Inventory rows
        sql_inv = """
        SELECT *
        FROM tbl_parts_inventory pi
        WHERE lower(trim(pi."Storage")) = lower(:storage_id)
           OR lower(trim(pi."AlternativeStorage")) = lower(:storage_id);
        """
        cols, rows = run_query(conn, sql_inv, {"storage_id": STORAGE_ID})
        sections.append(rows_to_markdown("Inventory rows (tbl_parts_inventory)", sql_inv, cols, rows))

        # 2b. Distinct SKU/ItemID by Storage
        sql_inv_distinct = """
        SELECT DISTINCT
          lower(trim(pi."Storage"))        AS storage,
          pi."SKU",
          pi."OverrideSKU",
          pi."ItemID",
          pi."OverridePrice",
          pi."StatusSKU",
          pi."OverrideTitle"
        FROM tbl_parts_inventory pi
        WHERE lower(trim(pi."Storage")) = lower(:storage_id)
           OR lower(trim(pi."AlternativeStorage")) = lower(:storage_id);
        """
        cols, rows = run_query(conn, sql_inv_distinct, {"storage_id": STORAGE_ID})
        sections.append(rows_to_markdown("Distinct SKU/ItemID by Storage", sql_inv_distinct, cols, rows))

        # 3.1 Sales (tbl_ebay_buyer)
        sql_buyer = """
        WITH inv AS (
          SELECT DISTINCT
            lower(trim("Storage")) AS storage,
            lower(trim("ItemID"))  AS itemid
          FROM tbl_parts_inventory
          WHERE lower(trim("Storage")) = lower(:storage_id)
             OR lower(trim("AlternativeStorage")) = lower(:storage_id)
        )
        SELECT b.*
        FROM tbl_ebay_buyer b
        LEFT JOIN inv
          ON lower(trim(b."Storage")) = inv.storage
          OR lower(trim(b."ItemID"))  = inv.itemid
        WHERE inv.storage IS NOT NULL
           OR inv.itemid  IS NOT NULL;
        """
        cols, rows = run_query(conn, sql_buyer, {"storage_id": STORAGE_ID})
        sections.append(rows_to_markdown("Sales (tbl_ebay_buyer)", sql_buyer, cols, rows))

        # 3.2 Sales Log (tbl_ebay_buyer_log)
        sql_buyer_log = """
        WITH inv AS (
          SELECT DISTINCT
            lower(trim("Storage")) AS storage,
            lower(trim("ItemID"))  AS itemid
          FROM tbl_parts_inventory
          WHERE lower(trim("Storage")) = lower(:storage_id)
             OR lower(trim("AlternativeStorage")) = lower(:storage_id)
        )
        SELECT bl.*
        FROM tbl_ebay_buyer_log bl
        LEFT JOIN inv
          ON lower(trim(bl."Storage")) = inv.storage
          OR lower(trim(bl."ItemID"))  = inv.itemid
        WHERE inv.storage IS NOT NULL
           OR inv.itemid  IS NOT NULL;
        """
        cols, rows = run_query(conn, sql_buyer_log, {"storage_id": STORAGE_ID})
        sections.append(rows_to_markdown("Sales Log (tbl_ebay_buyer_log)", sql_buyer_log, cols, rows))

        # 3.3 Key set (ItemID / TransactionID) – legacy tables do not expose OrderID/OrderLineItemID here
        sql_keys = """
        WITH keys AS (
          SELECT DISTINCT
            lower(trim("ItemID"))          AS itemid,
            NULL::text                      AS orderid,
            NULL::text                      AS orderlineitemid,
            lower(trim("TransactionID"))   AS transactionid
          FROM tbl_ebay_buyer
          UNION
          SELECT DISTINCT
            lower(trim("ItemID")),
            NULL::text,
            NULL::text,
            lower(trim("TransactionID"))
          FROM tbl_ebay_buyer_log
        )
        SELECT * FROM keys;
        """
        cols, rows = run_query(conn, sql_keys)
        sections.append(rows_to_markdown("Key set (ItemID / OrderID / OrderLineItemID / TransactionID)", sql_keys, cols, rows))

        # 4. Seller Transactions (ebay_sellerTransactions) – uses ItemID/TransactionID where possible
        try:
            sql_seller_tx = """
            WITH keys AS (
              SELECT DISTINCT
                lower(trim("ItemID"))        AS itemid,
                lower(trim("TransactionID")) AS transactionid
              FROM tbl_ebay_buyer
              UNION
              SELECT DISTINCT
                lower(trim("ItemID")),
                lower(trim("TransactionID"))
              FROM tbl_ebay_buyer_log
            )
            SELECT st.*
            FROM ebay_sellerTransactions st
            JOIN keys k
              ON lower(trim(st."TransactionID")) = k.transactionid
              OR (st."ItemID" IS NOT NULL AND lower(trim(st."ItemID")) = k.itemid);
            """
            cols, rows = run_query(conn, sql_seller_tx)
            sections.append(rows_to_markdown("Seller Transactions (ebay_sellerTransactions)", sql_seller_tx, cols, rows))
        except Exception:
            # Missing table or other error; rollback this failed transaction
            try:
                conn.rollback()
            except Exception:
                pass
            sections.append("## Seller Transactions (ebay_sellerTransactions)\n")
            sections.append("Table ebay_sellerTransactions not present or query failed; skipping.\n")

        # 5. eBay Fees (tbl_ebay_fees) – joined by ItemID/TransactionID, scoped to A331-related rows
        sql_fees = """
        WITH inv AS (
          SELECT DISTINCT
            lower(trim("Storage")) AS storage,
            lower(trim("ItemID"))  AS itemid
          FROM tbl_parts_inventory
          WHERE lower(trim("Storage")) = lower(:storage_id)
             OR lower(trim("AlternativeStorage")) = lower(:storage_id)
        ),
        keys AS (
          SELECT DISTINCT
            lower(trim(b."ItemID"))        AS itemid,
            lower(trim(b."TransactionID")) AS transactionid
          FROM tbl_ebay_buyer b
          JOIN inv i
            ON lower(trim(b."Storage")) = i.storage
           OR lower(trim(b."ItemID"))  = i.itemid
          UNION
          SELECT DISTINCT
            lower(trim(bl."ItemID")),
            lower(trim(bl."TransactionID"))
          FROM tbl_ebay_buyer_log bl
          JOIN inv i
            ON lower(trim(bl."Storage")) = i.storage
           OR lower(trim(bl."ItemID"))  = i.itemid
        )
        SELECT f.*
        FROM tbl_ebay_fees f
        JOIN keys k
          ON lower(trim(f."TransactionID")) = k.transactionid
          OR (f."ItemID" IS NOT NULL AND lower(trim(f."ItemID")) = k.itemid);
        """
        cols, rows = run_query(conn, sql_fees, {"storage_id": STORAGE_ID})
        sections.append(rows_to_markdown("eBay Fees (tbl_ebay_fees)", sql_fees, cols, rows))

        # 6. Combined view SQL (documented, not executed)
        combined_sql = """
WITH inv AS (
  SELECT
    pi."ID"                AS parts_inventory_id,
    lower(trim(pi."Storage"))  AS storage,
    pi."SKU",
    pi."ItemID",
    pi."OverridePrice",
    pi."OverrideTitle"
  FROM tbl_parts_inventory pi
  WHERE lower(trim(pi."Storage")) = lower(:storage_id)
     OR lower(trim(pi."AlternativeStorage")) = lower(:storage_id)
),
sales AS (
  SELECT
    b."ID"                 AS buyer_id,
    lower(trim(b."Storage"))       AS storage,
    lower(trim(b."ItemID"))        AS itemid,
    lower(trim(b."TransactionID")) AS transactionid,
    lower(trim(b."OrderID"))       AS orderid,
    lower(trim(b."OrderLineItemID")) AS orderlineitemid,
    b."TotalPrice",
    b."TotalTransactionPrice",
    b."PaidTime",
    b."ShippedTime"
  FROM tbl_ebay_buyer b
),
keys AS (
  SELECT DISTINCT
    s.transactionid,
    s.orderid,
    s.orderlineitemid,
    s.itemid
  FROM sales s
  JOIN inv i ON i.storage = s.storage OR i."ItemID" = s.itemid
),
st AS (
  SELECT *
  FROM ebay_sellerTransactions st
  JOIN keys k
    ON lower(trim(st."TransactionID"))   = k.transactionid
    OR lower(trim(st."OrderLineItemID")) = k.orderlineitemid
    OR lower(trim(st."OrderID"))         = k.orderid
    OR lower(trim(st."ItemID"))          = k.itemid
),
fees AS (
  SELECT *
  FROM tbl_ebay_fees f
  JOIN keys k
    ON lower(trim(f."TransactionID"))   = k.transactionid
    OR lower(trim(f."OrderLineItemID")) = k.orderlineitemid
    OR lower(trim(f."OrderID"))         = k.orderid
    OR lower(trim(f."ItemID"))          = k.itemid
)
SELECT
  inv.storage,
  inv.parts_inventory_id,
  inv."SKU",
  inv."ItemID",
  sales.transactionid,
  sales.orderid,
  sales.orderlineitemid,
  sales."TotalPrice",
  sales."TotalTransactionPrice",
  st."FinalValueFee",
  st."PaymentsFeeOrCreditAmount",
  st."RefundsRefundAmount",
  st."RefundsFeeOrCreditAmount",
  fees."GrossDetailAmount",
  fees."DiscountAmount",
  fees."NetDetailAmount",
  fees."AccountDetailsEntryType",
  fees."Description",
  fees."RefNumber"
FROM inv
LEFT JOIN sales
  ON inv.storage = sales.storage
 AND inv."ItemID" = sales.itemid
LEFT JOIN st
  ON lower(trim(st."TransactionID")) = sales.transactionid
LEFT JOIN fees
  ON lower(trim(fees."TransactionID")) = sales.transactionid
ORDER BY inv.parts_inventory_id, sales.transactionid;
"""

        sections.append("## Combined view: Inventory → Sales → SellerTransactions → Fees (Storage A331)\n")
        sections.append("```sql")
        sections.append(combined_sql.strip())
        sections.append("```")

    OUTPUT_PATH.write_text("\n\n".join(sections) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
