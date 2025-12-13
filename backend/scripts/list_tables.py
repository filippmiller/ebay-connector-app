import os
import json
from sqlalchemy import create_engine, inspect

def get_database_url():
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    try:
        with open("railway_vars_dump.json", "r", encoding="utf-16") as f:
            data = json.load(f)
            return data.get("DATABASE_URL")
    except Exception:
        return None

def main():
    db_url = get_database_url()
    if not db_url:
        print("DATABASE_URL not found.")
        return

    engine = create_engine(db_url)
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    with open("tables_list.txt", "w", encoding="utf-8") as f:
        for t in sorted(tables):
            f.write(t + "\n")
    print("Table list saved to tables_list.txt")

if __name__ == "__main__":
    main()
