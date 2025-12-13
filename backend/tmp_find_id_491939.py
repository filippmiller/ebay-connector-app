from app.models_sqlalchemy import engine
from sqlalchemy import inspect, text
import json

TARGET = "491939"


def main() -> None:
    insp = inspect(engine)
    results = []

    with engine.connect() as conn:
        for table in insp.get_table_names():
            # ищем только колонки, где в имени есть 'id'
            columns = [c["name"] for c in insp.get_columns(table) if "id" in c["name"].lower()]
            if not columns:
                continue

            for col in columns:
                # Пробуем искать по приведению к тексту, чтобы поймать и int, и text
                sql = text(f"SELECT 1 FROM \"{table}\" WHERE CAST(\"{col}\" AS TEXT) = :val LIMIT 1")
                try:
                    row = conn.execute(sql, {"val": TARGET}).first()
                except Exception:
                    # какие-то типы могут не каститься в TEXT — просто пропускаем
                    continue
                if row is not None:
                    results.append({"table": table, "column": col})

    print(json.dumps(results, ensure_ascii=False))


if __name__ == "__main__":
    main()
