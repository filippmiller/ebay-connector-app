from __future__ import annotations

import os
import sys

from sqlalchemy import text

# Ensure project root (the directory containing the `app` package) is on sys.path
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if ROOT_DIR not in sys.path:
  sys.path.insert(0, ROOT_DIR)

from app.models_sqlalchemy import SessionLocal


def main() -> None:
  db = SessionLocal()
  try:
    # Resolve InventoryStatus_ID for TEST from tbl_parts_inventorystatus
    status_id = db.execute(
      text(
        'SELECT "InventoryStatus_ID" FROM "tbl_parts_inventorystatus" '
        'WHERE "InventoryStatus_Name" = :name OR "InventoryShortStatus_Name" = :name '
        'LIMIT 1'
      ),
      {"name": "TEST"},
    ).scalar()

    if status_id is None:
      raise SystemExit("TEST status not found in tbl_parts_inventorystatus")

    # Update the legacy inventory row
    db.execute(
      text(
        'UPDATE "tbl_parts_inventory" '
        'SET "StatusSKU" = :sid '
        'WHERE "ID" = :iid'
      ),
      {"sid": int(status_id), "iid": 501610},
    )
    db.commit()
  finally:
    db.close()


if __name__ == "__main__":
  main()
