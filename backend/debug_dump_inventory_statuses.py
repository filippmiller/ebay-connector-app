from app.database import SessionLocal
from sqlalchemy.sql import text

if __name__ == "__main__":  # pragma: no cover
    # Simple helper to print out legacy inventory statuses
    session = SessionLocal()
    rows = session.execute(
        text('SELECT "InventoryStatus_ID", "InventoryStatus_Name", "InventoryShortStatus_Name" '
             'FROM "tbl_parts_inventorystatus" ORDER BY "InventoryStatus_ID"')
    ).fetchall()
    for r in rows:
        print(r)
