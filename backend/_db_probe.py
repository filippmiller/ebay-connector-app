import os, re, json, sys
import psycopg2
from urllib.parse import urlparse, parse_qs, urlencode

# Read DATABASE_URL from env
url = os.environ.get('DATABASE_URL')
if not url:
    print('DB: AUTH_FAILED')
    print('ACTION: Update DATABASE_URL in Railway to the exact Supabase *Session Pooler* URL (user=postgres, host=*.pooler.supabase.com, port 5432 or 6543, sslmode=require).')
    sys.exit(0)

p = urlparse(url)
user = p.username or ''
host = p.hostname or ''
port = p.port or 5432
dbname = p.path.lstrip('/') or 'postgres'
q = parse_qs(p.query)
sslmode = (q.get('sslmode',[None])[0] or 'require')

hosts = [host]
# If matches aws-[0-1]-us-east-1.pooler.supabase.com try both 0 and 1
m = re.match(r"aws-[01]-us-east-1\.pooler\.supabase\.com", host or '')
if m:
    hosts = ['aws-0-us-east-1.pooler.supabase.com','aws-1-us-east-1.pooler.supabase.com']

users = [user] if user else []
if 'postgres' not in users:
    users.append('postgres')

ports = [5432, 6543]

ok_candidates = []
for u in users:
    for h in hosts:
        for prt in ports:
            # Build DSN preserving password but not printing it
            try:
                password = p.password or ''
            except Exception:
                password = ''
            netloc = f"{u}:{'***'}@{h}:{prt}"
            # Keep sslmode=require
            dsn = f"postgresql://{u}:{password}@{h}:{prt}/{dbname}?{urlencode({'sslmode':'require'})}"
            try:
                conn = psycopg2.connect(dsn, connect_timeout=5)
                cur = conn.cursor()
                cur.execute('SELECT 1')
                cur.fetchone()
                conn.close()
                print(f"PROBE  user={u} host={h} port={prt} -> OK")
                ok_candidates.append((u,h,prt))
                if len(ok_candidates)==1:
                    # keep first OK as recommended but continue printing other probes
                    pass
            except Exception as e:
                print(f"PROBE  user={u} host={h} port={prt} -> FAIL:{e.__class__.__name__}")

if ok_candidates:
    u,h,prt = ok_candidates[0]
    print(f"RECOMMENDED: user={u} host={h} port={prt} db={dbname} sslmode=require")
else:
    print('DB: AUTH_FAILED')
    print('ACTION: Update DATABASE_URL in Railway to the exact Supabase *Session Pooler* URL (user=postgres, host=*.pooler.supabase.com, port 5432 or 6543, sslmode=require).')
