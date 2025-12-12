from __future__ import annotations

import os
import sys

from sqlalchemy import create_engine, text

# Ensure project root (with app package) is on sys.path
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app.config import settings  # type: ignore


def main() -> None:
    eng = create_engine(settings.DATABASE_URL)
    with eng.connect() as conn:
        res = conn.execute(
            text(
                "SELECT column_name, data_type, is_nullable, column_default "
                "FROM information_schema.columns "
                "WHERE table_name = 'tbl_parts_inventorystatus' "
                "ORDER BY ordinal_position"
            )
        )
        rows = list(res)
        for r in rows:
            print(r)


if __name__ == "__main__":
    main()
