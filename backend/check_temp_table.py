from sqlalchemy import create_engine, inspect
from app.config import settings

def check_temp_table():
    print(f"Connecting to {settings.DATABASE_URL}")
    engine = create_engine(settings.DATABASE_URL)
    inspector = inspect(engine)
    
    table_name = "TEMP_ebay_orders"
    if inspector.has_table(table_name):
        print(f"Table '{table_name}' EXISTS.")
        columns = inspector.get_columns(table_name)
        print(f"Columns: {[c['name'] for c in columns]}")
    else:
        # Try lowercase just in case
        table_name = "temp__ebay__orders"
        if inspector.has_table(table_name):
            print(f"Table '{table_name}' EXISTS.")
            columns = inspector.get_columns(table_name)
            print(f"Columns: {[c['name'] for c in columns]}")
        else:
            print(f"Table '{table_name}' DOES NOT EXIST.")

if __name__ == "__main__":
    check_temp_table()
