from app.models_sqlalchemy import engine
from sqlalchemy import text
import json

SQL = text(
    'SELECT DISTINCT "AccountDetailsEntryType" '
    'FROM ('
    '  SELECT "AccountDetailsEntryType" '
    '  FROM tbl_ebay_fees '
    '  ORDER BY "Date" DESC '
    '  LIMIT 5000'
    ') sub '
    'WHERE "AccountDetailsEntryType" IS NOT NULL '
    'ORDER BY "AccountDetailsEntryType"'
)


def main() -> None:
    with engine.connect() as conn:
        rows = conn.execute(SQL).scalars().all()
    print(json.dumps(rows, ensure_ascii=False))


if __name__ == "__main__":
    main()
