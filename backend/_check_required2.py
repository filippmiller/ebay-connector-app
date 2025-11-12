import json, sys
p = sys.argv[1]
obj = json.load(open(p,  r, encoding=utf-8))
need = [DATABASE_URL,VITE_SUPABASE_URL,VITE_SUPABASE_ANON_KEY,SUPABASE_SERVICE_ROLE_KEY]
missing = [k for k in need if not (k in obj and str(obj.get(k) or ).strip())]
print(ALL_PRESENT if not missing else MISSING:  +  .join(missing))
