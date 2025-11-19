import os
from sqlalchemy import create_engine, inspect


def main() -> None:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL is not set")

    engine = create_engine(url)
    insp = inspect(engine)
    cols = [c["name"] for c in insp.get_columns("ebay_messages")]
    print("COLUMNS:", ",".join(cols))


if __name__ == "__main__":
    main()
