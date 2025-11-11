import os, sys
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
try:
    u = make_url(os.environ['DATABASE_URL'])
    ok = (u.get_backend_name()=='postgresql' and 'supabase.com' in (u.host or '') and (u.query.get('sslmode')=='require' or u.query.get('sslmode')==['require']))
    if not ok:
        print('DB_ERROR:URL')
        sys.exit(1)
    eng = create_engine(os.environ['DATABASE_URL'])
    with eng.connect() as conn:
        conn.execute(text('SELECT 1'))
        conn.commit()
    print('DB_OK')
except Exception as e:
    cls = type(e).__name__
    s = str(e).lower()
    if 'auth' in s or 'password' in s:
        print('DB_ERROR:AUTH_FAILED')
    elif 'timeout' in s or 'network' in s:
        print('DB_ERROR:NETWORK_ERROR')
    else:
        print('DB_ERROR:'+cls)
