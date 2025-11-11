import os, sys
import psycopg2

try:
    dsn = os.environ['DATABASE_URL']
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()
    cur.execute('SELECT 1')
    cur.fetchone()
    conn.close()
    print('DB_OK')
except Exception as e:
    s = str(e).lower()
    if 'password' in s or 'auth' in s:
        print('DB_ERROR:AUTH_FAILED')
    elif 'timeout' in s or 'network' in s:
        print('DB_ERROR:NETWORK')
    else:
        print('DB_ERROR:' + e.__class__.__name__)
