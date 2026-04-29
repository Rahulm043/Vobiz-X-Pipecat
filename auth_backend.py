"""supabase_auth.py

Backend authentication utility for Supabase JWT verification.
"""

import os
from typing import Optional
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv(override=True)

SUPABASE_URL = os.getenv("SUPABASE_URL")
# Use ANON key for verification client
ANON_KEY = os.getenv("VITE_SUPABASE_ANON_KEY") or os.getenv("SUPABASE_ANON_KEY")
if not SUPABASE_URL or not ANON_KEY:
    auth_client: Client = None
else:
    auth_client: Client = create_client(SUPABASE_URL, ANON_KEY)

security = HTTPBearer()

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    FastAPI dependency to verify Supabase JWT.
    Returns the user object if valid, else raises 401.
    """
    if not auth_client:
        print("[AUTH] Auth client NOT initialized (missing keys)")
        raise HTTPException(status_code=500, detail="Auth not configured on backend")

    token = credentials.credentials
    if not token:
        print("[AUTH] No token found in credentials")
        raise HTTPException(status_code=401, detail="Missing token")

    print(f"[AUTH DEBUG] Verifying token: {token[:10]}...")

    try:
        # Use Supabase client to get the user from the token
        user_res = auth_client.auth.get_user(token)
        
        if not user_res or not user_res.user:
            print(f"[AUTH] No user found for token. Response: {user_res}")
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        
        # print(f"[AUTH] Verified user: {user_res.user.email}")
        return user_res.user
    except Exception as e:
        print(f"[AUTH ERROR] Token verification failed for token {token[:10]}... : {e}")
        raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")
