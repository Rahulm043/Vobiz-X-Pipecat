"""call_store.py

JSON-file-based persistence for call logs and campaign data.
All data stored alongside recordings in the recordings/ directory.
Designed for easy migration to Supabase later.
"""

import json
import math
import os
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


# --------------- Paths --------------- #

RECORDINGS_DIR = os.path.join(os.path.dirname(__file__), "recordings")
CALL_LOG_FILE = os.path.join(RECORDINGS_DIR, "call_log.json")
CAMPAIGNS_FILE = os.path.join(RECORDINGS_DIR, "campaigns.json")

os.makedirs(RECORDINGS_DIR, exist_ok=True)


# --------------- Helpers --------------- #

_lock = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


def round_up_minutes(seconds: float) -> int:
    """Round seconds up to nearest minute. 0s -> 0, 3s -> 1, 60s -> 1, 61s -> 2."""
    if seconds <= 0:
        return 0
    return math.ceil(seconds / 60)


def _read_json(path: str) -> list:
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except (json.JSONDecodeError, IOError):
        return []


def _write_json(path: str, data: list):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)


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
    """Save or update a call record in the log."""
    with _lock:
        calls = _read_json(CALL_LOG_FILE)
        # Update if exists, else append
        idx = next((i for i, c in enumerate(calls) if c["call_id"] == call["call_id"]), None)
        if idx is not None:
            calls[idx] = call
        else:
            calls.append(call)
        _write_json(CALL_LOG_FILE, calls)


def get_call(call_id: str) -> Optional[Dict[str, Any]]:
    """Get a call record by ID (either internal call_id or vobiz_call_uuid)."""
    calls = _read_json(CALL_LOG_FILE)
    return next((c for c in calls if c["call_id"] == call_id or c.get("vobiz_call_uuid") == call_id), None)


def list_calls(
    campaign_id: Optional[str] = None,
    status: Optional[str] = None,
    call_type: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    date_str: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """List call records with optional filters. Returns newest first."""
    calls = _read_json(CALL_LOG_FILE)

    if campaign_id is not None:
        calls = [c for c in calls if c.get("campaign_id") == campaign_id]
    if status:
        calls = [c for c in calls if c.get("status") == status]
    if call_type:
        calls = [c for c in calls if c.get("call_type") == call_type]
    if date_str:
        calls = [c for c in calls if c.get("created_at", "").startswith(date_str)]

    # Sort newest first
    calls.sort(key=lambda c: c.get("created_at", ""), reverse=True)
    return calls[offset: offset + limit]


def update_call(call_id: str, **fields) -> Optional[Dict[str, Any]]:
    """Update specific fields on a call record. Searches by call_id or vobiz_call_uuid."""
    with _lock:
        calls = _read_json(CALL_LOG_FILE)
        idx = next((i for i, c in enumerate(calls) if c["call_id"] == call_id or c.get("vobiz_call_uuid") == call_id), None)
        if idx is None:
            return None
        for k, v in fields.items():
            calls[idx][k] = v
        # Auto-calculate duration_minutes when duration_seconds changes
        if "duration_seconds" in fields:
            calls[idx]["duration_minutes"] = round_up_minutes(fields["duration_seconds"])
        _write_json(CALL_LOG_FILE, calls)
        return calls[idx]


def count_calls(campaign_id: Optional[str] = None) -> int:
    calls = _read_json(CALL_LOG_FILE)
    if campaign_id:
        return sum(1 for c in calls if c.get("campaign_id") == campaign_id)
    return len(calls)


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
    with _lock:
        campaigns = _read_json(CAMPAIGNS_FILE)
        idx = next(
            (i for i, c in enumerate(campaigns) if c["campaign_id"] == campaign["campaign_id"]),
            None,
        )
        if idx is not None:
            campaigns[idx] = campaign
        else:
            campaigns.append(campaign)
        _write_json(CAMPAIGNS_FILE, campaigns)


def get_campaign(campaign_id: str) -> Optional[Dict[str, Any]]:
    campaigns = _read_json(CAMPAIGNS_FILE)
    return next((c for c in campaigns if c["campaign_id"] == campaign_id), None)


def list_campaigns(limit: int = 50) -> List[Dict[str, Any]]:
    campaigns = _read_json(CAMPAIGNS_FILE)
    campaigns.sort(key=lambda c: c.get("created_at", ""), reverse=True)
    return campaigns[:limit]


def update_campaign(campaign_id: str, **fields) -> Optional[Dict[str, Any]]:
    with _lock:
        campaigns = _read_json(CAMPAIGNS_FILE)
        idx = next(
            (i for i, c in enumerate(campaigns) if c["campaign_id"] == campaign_id),
            None,
        )
        if idx is None:
            return None
        for k, v in fields.items():
            campaigns[idx][k] = v
        _write_json(CAMPAIGNS_FILE, campaigns)
        return campaigns[idx]


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
    """Get aggregated stats for a given day or range (ISO strings)."""
    calls = _read_json(CALL_LOG_FILE)

    if start_date and end_date:
        # Range filtering (inclusive)
        # Assuming created_at is ISO format
        filtered_calls = [
            c for c in calls 
            if c.get("created_at") and start_date <= c.get("created_at") <= end_date
        ]
        label = f"{start_date[:10]} to {end_date[:10]}"
    elif date_str:
        # Legacy single day filtering
        filtered_calls = [c for c in calls if c.get("created_at", "").startswith(date_str)]
        label = date_str
    else:
        # Default to today UTC
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        filtered_calls = [c for c in calls if c.get("created_at", "").startswith(today)]
        label = today

    total_calls = len(filtered_calls)
    total_seconds = sum(c.get("duration_seconds", 0) for c in filtered_calls)
    total_minutes = sum(round_up_minutes(c.get("duration_seconds", 0)) for c in filtered_calls)

    connected = sum(1 for c in filtered_calls if c.get("status") == "completed")
    failed = sum(1 for c in filtered_calls if c.get("status") in ("failed", "error"))
    rejected = sum(1 for c in filtered_calls if c.get("status") == "rejected")
    in_progress = sum(1 for c in filtered_calls if c.get("status") in ("ringing", "connected", "in_progress"))

    # Daily breakdown for charting
    breakdown = {}
    for c in filtered_calls:
        day = c.get("created_at", "")[:10]
        if not day: continue
        if day not in breakdown:
            breakdown[day] = {"calls": 0, "minutes": 0}
        breakdown[day]["calls"] += 1
        breakdown[day]["minutes"] += round_up_minutes(c.get("duration_seconds", 0))

    # Sort breakdown by date
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
