import os
import subprocess

# Set the database URL
os.environ["DATABASE_URL"] = "postgresql://postgres.nrpfahjygulsfxmbmfzv:2Hu505ZIgaJQECzW@aws-1-us-east-1.pooler.supabase.com:6543/postgres?sslmode=require"

# Run alembic upgrade heads
try:
    result = subprocess.run(["alembic", "upgrade", "heads"], cwd="backend", capture_output=True, text=True)
    print("Return Code:", result.returncode)
    print("Stdout:", result.stdout)
    print("Stderr:", result.stderr)
except Exception as e:
    print("Error:", e)
