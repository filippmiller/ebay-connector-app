import os
need = ['DATABASE_URL','VITE_SUPABASE_URL','VITE_SUPABASE_ANON_KEY','SUPABASE_SERVICE_ROLE_KEY']
missing = [k for k in need if not os.getenv(k)]
if missing:
    print('MISSING: ' + ', '.join(missing))
else:
    print('ALL_PRESENT')
