import os
import psycopg2
from psycopg2 import OperationalError

url = os.environ["DATABASE_URL"]
print("USING:", url)

try:
    conn = psycopg2.connect(url, connect_timeout=5)
    cur = conn.cursor()
    cur.execute("select current_database(), current_user, now();")
    rows = cur.fetchall()
    print("RESULT:", rows)
    conn.close()
    print("OK: connected to Supabase Postgres.")
except OperationalError as e:
    print("FAILED to connect:")
    print(e)
