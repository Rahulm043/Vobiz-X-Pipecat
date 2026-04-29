"""supabase_storage.py

Utility to upload call recordings to Supabase Storage.
"""

import os
from typing import Optional
from loguru import logger
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv(override=True)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_ANON_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    supabase: Client = None
else:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def upload_recording(file_path: str, call_id: str) -> Optional[str]:
    """Upload a recording file to Supabase Storage and return the public URL (or path)."""
    if not supabase:
        logger.warning("[STORAGE] Supabase not configured, skipping upload.")
        return None

    if not os.path.exists(file_path):
        logger.error(f"[STORAGE] File not found: {file_path}")
        return None

    file_name = os.path.basename(file_path)
    # Store in a folder named after the call_id
    storage_path = f"{call_id}/{file_name}"

    try:
        with open(file_path, "rb") as f:
            # upsert=True allows replacing if it already exists
            res = supabase.storage.from_("recordings").upload(
                path=storage_path,
                file=f,
                file_options={"content-type": "audio/wav", "x-upsert": "true"}
            )
        
        # Get the public URL if the bucket is public, or just return the path
        # For now, let's return the path as it's safer
        logger.info(f"[STORAGE] Uploaded {file_name} to Supabase: {storage_path}")
        return storage_path
    except Exception as e:
        logger.error(f"[STORAGE] Failed to upload {file_name}: {e}")
        return None

def get_signed_url(storage_path: str, expires_in: int = 3600) -> Optional[str]:
    """Get a temporary signed URL for a private recording."""
    if not supabase or not storage_path:
        return None
    
    try:
        res = supabase.storage.from_("recordings").create_signed_url(storage_path, expires_in)
        return res.get("signedURL")
    except Exception as e:
        logger.error(f"[STORAGE] Failed to get signed URL for {storage_path}: {e}")
        return None
