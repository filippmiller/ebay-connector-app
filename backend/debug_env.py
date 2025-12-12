from dotenv import load_dotenv
import os

load_dotenv()
print(f"SUPABASE_URL from env: {os.getenv('SUPABASE_URL')}")
print(f"SUPABASE_KEY present: {bool(os.getenv('SUPABASE_KEY'))}")

from app.config import settings
print(f"Settings.SUPABASE_URL: {settings.SUPABASE_URL}")
