import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv(override=True)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("Supabase credentials missing!")
else:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    res = supabase.table("calls").select("call_id", "created_at").limit(10).execute()
    print(f"Total calls in DB (limited to 10): {len(res.data)}")
    for row in res.data:
        print(f"- {row['call_id']} (Created: {row['created_at']})")
