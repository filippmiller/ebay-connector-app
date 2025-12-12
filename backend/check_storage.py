from app.services.supabase_storage import get_supabase_client
from app.config import settings

def check_bucket():
    client = get_supabase_client()
    if not client:
        print("No client")
        return

    try:
        print(f"Checking buckets on {settings.SUPABASE_URL}")
        buckets = client.storage.list_buckets()
        bucket_names = [b.name for b in buckets]
        print(f"Buckets: {bucket_names}")
        
        if "bank-statements" in bucket_names:
            print("SUCCESS: bank-statements bucket exists.")
        else:
            print("FAILURE: bank-statements bucket NOT found. Creating it...")
            try:
                client.storage.create_bucket("bank-statements", options={"public": False})
                print("SUCCESS: Created bank-statements bucket.")
            except Exception as e:
                print(f"Error creating bucket: {e}")
            
    except Exception as e:
        print(f"Error listing buckets: {e}")

if __name__ == "__main__":
    check_bucket()
