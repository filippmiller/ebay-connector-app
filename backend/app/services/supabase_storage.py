from supabase import create_client, Client
from app.config import settings
from app.utils.logger import logger
import io

_supabase_client: Client = None

def get_supabase_client() -> Client:
    global _supabase_client
    if _supabase_client:
        return _supabase_client
    
    url = settings.SUPABASE_URL
    key = settings.SUPABASE_SERVICE_KEY or settings.SUPABASE_KEY
    
    if not url or not key:
        logger.warning("SUPABASE_URL or SUPABASE_KEY/SERVICE_KEY not set. Storage operations will fail.")
        return None
        
    _supabase_client = create_client(url, key)
    return _supabase_client

def upload_file_to_storage(bucket_name: str, path: str, file_bytes: bytes, content_type: str = "application/octet-stream") -> str:
    """
    Uploads bytes to Supabase Storage.
    Returns the path if successful (which allows subsequent download/signed URL generation).
    """
    client = get_supabase_client()
    if not client:
        raise RuntimeError("Supabase client not initialized")
    
    logger.info(f"Uploading file to Supabase Storage: bucket={bucket_name}, path={path}, size={len(file_bytes)}")
    
    try:
        # Supabase Python client 'upload' method expects bytes or file-like object
        # NOTE: upsert=True is supported in newer versions, checking if we need it.
        # It's safer to attempt upload.
        res = client.storage.from_(bucket_name).upload(
            path=path,
            file=file_bytes,
            file_options={"content-type": content_type, "upsert": "true"}
        )
        logger.info(f"Upload successful: {res}")
        return path
    except Exception as e:
        logger.error(f"Failed to upload to Supabase Storage: {e}")
        raise e

def get_signed_url(bucket_name: str, path: str, expiry_seconds: int = 3600) -> str:
    client = get_supabase_client()
    if not client:
        return ""
    try:
        res = client.storage.from_(bucket_name).create_signed_url(path, expiry_seconds)
        if isinstance(res, dict) and "signedURL" in res:
             return res["signedURL"]
        # Recent library versions might return an object or direct string? 
        # API docs say it returns dictionary with signedURL
        return res
    except Exception as e:
        logger.error(f"Failed to get signed URL: {e}")
        return ""
