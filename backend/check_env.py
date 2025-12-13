from dotenv import load_dotenv
import os

load_dotenv()
url = os.getenv("DATABASE_URL")
if url:
    print("DATABASE_URL FOUND")
    if url.startswith("postgres"):
        print("Starts with postgres")
    else:
        print(f"Starts with {url.split(':')[0]}")
else:
    print("DATABASE_URL NOT FOUND")
