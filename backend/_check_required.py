import json, sys, os
p = os.path.join(os.path.dirname(__file__), '_vars.json')
try:
    with open(p, 'r', encoding='utf-8') as f:
        obj = json.load(f)
except Exception:
    print('MISSING: DATABASE_URL, VITE_SUPABASE_URL, VITE_SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY')
    sys.exit(0)
need = ['DATABASE_URL','VITE_SUPABASE_URL','VITE_SUPABASE_ANON_KEY','SUPABASE_SERVICE_ROLE_KEY']
missing = [k for k in need if not (k in obj and str(obj.get(k) or '').strip())]
if missing:
    print('MISSING: ' + ', '.join(missing))
else:
    print('ALL_PRESENT')
