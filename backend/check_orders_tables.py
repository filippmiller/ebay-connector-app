import os
from sqlalchemy import create_engine, inspect, text
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)
inspector = inspect(engine)

print("Checking tables...")
tables = inspector.get_table_names()
print(f"ebay_orders exists: {'ebay_orders' in tables}")
print(f"temp__ebay__orders exists: {'temp__ebay__orders' in tables}")

if 'temp__ebay__orders' in tables:
    print("\nSample rows from temp__ebay__orders:")
    with engine.connect() as conn:
        result = conn.execute(text("SELECT * FROM temp__ebay__orders LIMIT 3"))
        columns = result.keys()
        for row in result:
            print(dict(zip(columns, row)))
            
        print("\nColumn types in temp__ebay__orders:")
        for col in inspector.get_columns('temp__ebay__orders'):
            print(f"{col['name']}: {col['type']}")
