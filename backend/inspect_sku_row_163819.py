from sqlalchemy import create_engine, text

from inspect_sku_table import DEFAULT_DB_URL


def main() -> None:
    engine = create_engine(DEFAULT_DB_URL)
    with engine.connect() as conn:
        # Show columns for SKU_catalog
        print("--- DESCRIBE SKU_catalog ---")
        rows = conn.execute(
            text(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_name = 'SKU_catalog' ORDER BY ordinal_position"
            )
        ).fetchall()
        for name, dtype in rows:
            print(f"{name}: {dtype}")

        # Fetch specific row by ID
        print("\n--- ROW ID=163819 ---")
        row = conn.execute(
            text("SELECT * FROM \"SKU_catalog\" WHERE \"ID\" = :id"),
            {"id": 163819},
        ).mappings().first()
        if not row:
            print("No row with ID=163819 found")
        else:
            # Print key fields
            for key in sorted(row.keys()):
                if key.lower() in {"id", "sku", "model", "model_id", "title", "part", "category", "description", "conditionid", "shippinggroup"}:
                    print(f"{key} = {row[key]!r}")


if __name__ == "__main__":
    main()
