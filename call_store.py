"""call_store.py

Supabase-based persistence for call logs and campaign data.
Replaces the local JSON storage to make the application stateless.
"""

import math
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv(override=True)

# --------------- Supabase Config --------------- #

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_ANON_KEY") or os.getenv("VITE_SUPABASE_ANON_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("[WARNING] Supabase credentials not found in environment!")
    supabase: Optional[Client] = None
else:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --------------- Helpers --------------- #

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _new_id() -> str:
    return str(uuid.uuid4())

def round_up_minutes(seconds: float) -> int:
    """Round seconds up to nearest minute. 0s -> 0, 3s -> 1, 60s -> 1, 61s -> 2."""
    if seconds <= 0:
        return 0
    return math.ceil(seconds / 60)

# --------------- Call Record --------------- #

def make_call_record(
    phone_number: str,
    call_type: str = "sip",
    campaign_id: Optional[str] = None,
    recipient_name: str = "",
    recipient_detail: str = "",
    call_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a new call record dict with defaults."""
    cid = call_id or _new_id()
    return {
        "call_id": cid,
        "campaign_id": campaign_id,
        "phone_number": phone_number,
        "recipient_name": recipient_name,
        "recipient_detail": recipient_detail,
        "call_type": call_type,  # "sip" or "web"
        "status": "queued",
        "direction": "outbound",
        "created_at": _now_iso(),
        "ringing_at": None,
        "connected_at": None,
        "ended_at": None,
        "duration_seconds": 0,
        "duration_minutes": 0,
        "vobiz_call_uuid": None,
        "recording_files": {
            "stereo": None,
            "user": None,
            "bot": None,
            "vobiz_mp3": None,
        },
        "transcript": [],
        "summary": None,
        "end_reason": None,
        "transfer_requested": False,
        "metadata": {},
    }

# --------------- Call CRUD --------------- #

def save_call(call: Dict[str, Any]):
    """Save or update a call record in Supabase."""
    if not supabase: return
    
    # Supabase upsert uses the primary key (call_id)
    try:
        supabase.table("calls").upsert(call).execute()
    except Exception as e:
        print(f"[ERROR] Supabase save_call failed: {e}")

def get_call(call_id: str) -> Optional[Dict[str, Any]]:
    """Get a call record by ID (either internal call_id or vobiz_call_uuid)."""
    if not supabase: return None
    
    try:
        # Try by call_id first
        res = supabase.table("calls").select("*").eq("call_id", call_id).execute()
        if res.data:
            return res.data[0]
        
        # Then by vobiz_call_uuid
        res = supabase.table("calls").select("*").eq("vobiz_call_uuid", call_id).execute()
        if res.data:
            return res.data[0]
    except Exception as e:
        print(f"[ERROR] Supabase get_call failed: {e}")
    
    return None

def list_calls(
    campaign_id: Optional[str] = None,
    status: Optional[str] = None,
    call_type: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    date_str: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """List call records with optional filters. Returns newest first."""
    if not supabase: return []
    
    try:
        query = supabase.table("calls").select("*").order("created_at", desc=True)
        
        if campaign_id:
            query = query.eq("campaign_id", campaign_id)
        if status:
            query = query.eq("status", status)
        if call_type:
            query = query.eq("call_type", call_type)
        if date_str:
            # Simple prefix match for created_at
            query = query.like("created_at", f"{date_str}%")
            
        res = query.range(offset, offset + limit - 1).execute()
        return res.data or []
    except Exception as e:
        print(f"[ERROR] Supabase list_calls failed: {e}")
        return []

def update_call(call_id: str, **fields) -> Optional[Dict[str, Any]]:
    """Update specific fields on a call record."""
    if not supabase: return None
    
    try:
        # First, find the primary key if call_id is a vobiz_call_uuid
        actual_call_id = call_id
        if not _is_valid_uuid(call_id):
            existing = get_call(call_id)
            if existing:
                actual_call_id = existing["call_id"]
            else:
                return None

        # Auto-calculate duration_minutes if duration_seconds is provided
        if "duration_seconds" in fields:
            fields["duration_minutes"] = round_up_minutes(fields["duration_seconds"])

        res = supabase.table("calls").update(fields).eq("call_id", actual_call_id).execute()
        if res.data:
            return res.data[0]
    except Exception as e:
        print(f"[ERROR] Supabase update_call failed: {e}")
    
    return None

def _is_valid_uuid(val: str) -> bool:
    try:
        uuid.UUID(str(val))
        return True
    except ValueError:
        return False

def count_calls(campaign_id: Optional[str] = None) -> int:
    if not supabase: return 0
    
    try:
        query = supabase.table("calls").select("*", count="exact")
        if campaign_id:
            query = query.eq("campaign_id", campaign_id)
        
        res = query.execute()
        return res.count if res.count is not None else 0
    except Exception as e:
        print(f"[ERROR] Supabase count_calls failed: {e}")
        return 0

# --------------- Campaign CRUD --------------- #

def make_campaign_record(
    name: str,
    recipients: List[Dict[str, str]],
    mode: str = "sequential",
    concurrent_limit: int = 1,
    call_gap_seconds: int = 30,
) -> Dict[str, Any]:
    """Create a new campaign record."""
    return {
        "campaign_id": _new_id(),
        "name": name,
        "status": "created",  # created | running | paused | completed | cancelled
        "mode": mode,  # sequential | concurrent
        "concurrent_limit": concurrent_limit,
        "call_gap_seconds": call_gap_seconds,
        "created_at": _now_iso(),
        "started_at": None,
        "completed_at": None,
        "recipients": recipients,
        "stats": {
            "total": len(recipients),
            "completed": 0,
            "failed": 0,
            "rejected": 0,
            "active": 0,
            "queued": len(recipients),
        },
    }

def save_campaign(campaign: Dict[str, Any]):
    """Save or update a campaign record."""
    if not supabase: return
    
    try:
        supabase.table("campaigns").upsert(campaign).execute()
    except Exception as e:
        print(f"[ERROR] Supabase save_campaign failed: {e}")

def get_campaign(campaign_id: str) -> Optional[Dict[str, Any]]:
    if not supabase: return None
    
    try:
        res = supabase.table("campaigns").select("*").eq("campaign_id", campaign_id).execute()
        if res.data:
            return res.data[0]
    except Exception as e:
        print(f"[ERROR] Supabase get_campaign failed: {e}")
    return None

def list_campaigns(limit: int = 50) -> List[Dict[str, Any]]:
    if not supabase: return []
    
    try:
        res = supabase.table("campaigns").select("*").order("created_at", desc=True).limit(limit).execute()
        return res.data or []
    except Exception as e:
        print(f"[ERROR] Supabase list_campaigns failed: {e}")
        return []

def update_campaign(campaign_id: str, **fields) -> Optional[Dict[str, Any]]:
    if not supabase: return None
    
    try:
        res = supabase.table("campaigns").update(fields).eq("campaign_id", campaign_id).execute()
        if res.data:
            return res.data[0]
    except Exception as e:
        print(f"[ERROR] Supabase update_campaign failed: {e}")
    return None

def refresh_campaign_stats(campaign_id: str) -> Dict[str, int]:
    """Recompute campaign stats from call records."""
    calls = list_calls(campaign_id=campaign_id, limit=10000)
    stats = {"total": 0, "completed": 0, "failed": 0, "rejected": 0, "active": 0, "queued": 0}

    campaign = get_campaign(campaign_id)
    if campaign:
        stats["total"] = len(campaign.get("recipients", []))

    for call in calls:
        s = call.get("status", "queued")
        if s == "completed":
            stats["completed"] += 1
        elif s in ("failed", "error"):
            stats["failed"] += 1
        elif s == "rejected":
            stats["rejected"] += 1
        elif s in ("ringing", "connected", "in_progress"):
            stats["active"] += 1
        elif s == "queued":
            stats["queued"] += 1

    # Queued = total - (all others)
    accounted = stats["completed"] + stats["failed"] + stats["rejected"] + stats["active"]
    stats["queued"] = max(0, stats["total"] - accounted)

    update_campaign(campaign_id, stats=stats)
    return stats

# --------------- Agent Stats --------------- #

def get_agent_stats(
    date_str: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> Dict[str, Any]:
    """Get aggregated stats for a given day or range."""
    if not supabase: return {}
    
    try:
        query = supabase.table("calls").select("duration_seconds, status, created_at")
        
        if start_date and end_date:
            query = query.gte("created_at", start_date).lte("created_at", end_date)
            label = f"{start_date[:10]} to {end_date[:10]}"
        elif date_str:
            query = query.like("created_at", f"{date_str}%")
            label = date_str
        else:
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            query = query.like("created_at", f"{today}%")
            label = today
            
        res = query.execute()
        filtered_calls = res.data or []
        
        total_calls = len(filtered_calls)
        total_seconds = sum(c.get("duration_seconds", 0) or 0 for c in filtered_calls)
        total_minutes = sum(round_up_minutes(c.get("duration_seconds", 0) or 0) for c in filtered_calls)

        connected = sum(1 for c in filtered_calls if c.get("status") == "completed")
        failed = sum(1 for c in filtered_calls if c.get("status") in ("failed", "error"))
        rejected = sum(1 for c in filtered_calls if c.get("status") == "rejected")
        in_progress = sum(1 for c in filtered_calls if c.get("status") in ("ringing", "connected", "in_progress"))

        # Daily breakdown
        breakdown = {}
        for c in filtered_calls:
            day = c.get("created_at", "")[:10]
            if not day: continue
            if day not in breakdown:
                breakdown[day] = {"calls": 0, "minutes": 0}
            breakdown[day]["calls"] += 1
            breakdown[day]["minutes"] += round_up_minutes(c.get("duration_seconds", 0) or 0)

        sorted_breakdown = [
            {"date": d, "calls": v["calls"], "minutes": v["minutes"]}
            for d, v in sorted(breakdown.items())
        ]

        return {
            "label": label,
            "total_calls": total_calls,
            "total_seconds": total_seconds,
            "total_minutes": total_minutes,
            "connected": connected,
            "failed": failed,
            "rejected": rejected,
            "in_progress": in_progress,
            "breakdown": sorted_breakdown
        }
    except Exception as e:
        print(f"[ERROR] Supabase get_agent_stats failed: {e}")
        return {}
