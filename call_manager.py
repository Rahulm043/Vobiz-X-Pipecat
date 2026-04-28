"""call_manager.py

Central orchestrator for all call operations.
Manages single calls, campaigns, agent status, and call lifecycle events.
"""

import asyncio
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import aiohttp
from loguru import logger

import call_store
from campaign_runner import CampaignRunner


class CallManager:
    """Singleton call manager — coordinates all calling activity."""

    def __init__(self):
        self.active_campaigns: Dict[str, CampaignRunner] = {}
        self._current_call_id: Optional[str] = None
        self._http_session: Optional[aiohttp.ClientSession] = None

    def set_http_session(self, session: aiohttp.ClientSession):
        self._http_session = session

    # --------------- Agent Status --------------- #

    def get_agent_status(self) -> Dict[str, Any]:
        """Return current agent status and activity."""
        # Check for running campaigns
        running_campaigns = {
            cid: runner for cid, runner in self.active_campaigns.items()
            if runner.is_running
        }

        if running_campaigns:
            # Get the first running campaign details
            cid = next(iter(running_campaigns))
            runner = running_campaigns[cid]
            campaign = call_store.get_campaign(cid)
            campaign_name = campaign["name"] if campaign else cid
            stats = campaign.get("stats", {}) if campaign else {}

            status = "on_campaign"
            if runner.is_paused:
                status = "campaign_paused"

            return {
                "status": status,
                "campaign_id": cid,
                "campaign_name": campaign_name,
                "campaign_stats": stats,
                "active_campaigns_count": len(running_campaigns),
            }

        if self._current_call_id:
            call = call_store.get_call(self._current_call_id)
            if call and call.get("status") in ("ringing", "connected", "in_progress"):
                # Staleness check: auto-fail calls stuck for longer than 10 minutes
                created_at = call.get("ringing_at") or call.get("created_at", "")
                try:
                    from datetime import timezone
                    call_age_seconds = 0
                    if created_at:
                        ts = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                        call_age_seconds = (datetime.now(timezone.utc) - ts).total_seconds()
                except Exception:
                    call_age_seconds = 0

                if call_age_seconds > 600:  # 10 minutes
                    logger.warning(f"[CALLMGR] Call {self._current_call_id} stuck in ringing for {call_age_seconds:.0f}s — auto-failing")
                    call_store.update_call(
                        self._current_call_id,
                        status="failed",
                        ended_at=datetime.now(timezone.utc).isoformat(),
                        end_reason="timeout (no hangup received)",
                    )
                    self._current_call_id = None
                else:
                    return {
                        "status": "on_call",
                        "call_id": self._current_call_id,
                        "phone_number": call.get("phone_number"),
                        "call_status": call.get("status"),
                        "started_at": call.get("created_at"),
                    }

        return {"status": "idle"}

    def get_today_stats(self) -> Dict[str, Any]:
        """Return today's aggregated call statistics."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return call_store.get_agent_stats(today)

    # --------------- Single Call --------------- #

    async def make_single_call(
        self,
        phone_number: str,
        recipient_name: str = "",
        recipient_detail: str = "",
        campaign_id: Optional[str] = None,
        call_type: str = "sip",
    ) -> Dict[str, Any]:
        """Initiate a single outbound SIP call via Vobiz API."""

        # Create call record
        call_record = call_store.make_call_record(
            phone_number=phone_number,
            call_type=call_type,
            campaign_id=campaign_id,
            recipient_name=recipient_name,
            recipient_detail=recipient_detail,
        )
        call_store.save_call(call_record)

        if call_type == "web":
            # Web calls are initiated from the browser, just track them
            self._current_call_id = call_record["call_id"]
            return call_record

        # SIP call via Vobiz API
        try:
            call_store.update_call(call_record["call_id"], status="ringing",
                                   ringing_at=datetime.now(timezone.utc).isoformat())
            self._current_call_id = call_record["call_id"]

            result = await self._initiate_vobiz_call(phone_number, call_record["call_id"])

            vobiz_uuid = result.get("request_uuid") or result.get("call_uuid") or "unknown"
            call_store.update_call(
                call_record["call_id"],
                vobiz_call_uuid=vobiz_uuid,
            )

            logger.info(f"[CALLMGR] Call {call_record['call_id']} initiated → Vobiz UUID: {vobiz_uuid}")
            return call_store.get_call(call_record["call_id"])

        except Exception as e:
            logger.error(f"[CALLMGR] Failed to initiate call to {phone_number}: {e}")
            call_store.update_call(
                call_record["call_id"],
                status="failed",
                end_reason=str(e),
                ended_at=datetime.now(timezone.utc).isoformat(),
            )
            raise

    async def _initiate_vobiz_call(self, phone_number: str, call_id: str) -> dict:
        """Make the actual Vobiz REST API call."""
        import json
        import urllib.parse

        auth_id = os.getenv("VOBIZ_AUTH_ID")
        auth_token = os.getenv("VOBIZ_AUTH_TOKEN")
        from_number = os.getenv("VOBIZ_PHONE_NUMBER")
        public_url = os.getenv("PUBLIC_URL")

        if not all([auth_id, auth_token, from_number, public_url]):
            raise ValueError("Missing Vobiz credentials or PUBLIC_URL in .env")

        # Build answer URL with call metadata
        body_data = {"phone_number": phone_number, "call_manager_id": call_id}
        body_encoded = urllib.parse.quote(json.dumps(body_data))

        protocol = "https" if public_url.startswith("https") else "http"
        host = public_url.replace("https://", "").replace("http://", "").rstrip("/")
        answer_url = f"{protocol}://{host}/answer?body_data={body_encoded}"

        headers = {
            "Content-Type": "application/json",
            "X-Auth-ID": auth_id,
            "X-Auth-Token": auth_token,
        }
        data = {
            "to": phone_number,
            "from": from_number,
            "answer_url": answer_url,
            "answer_method": "POST",
        }
        url = f"https://api.vobiz.ai/api/v1/Account/{auth_id}/Call/"

        session = self._http_session or aiohttp.ClientSession()
        close_session = self._http_session is None

        try:
            async with session.post(url, headers=headers, json=data) as response:
                response_text = await response.text()
                if response.status != 201:
                    raise Exception(f"Vobiz API error ({response.status}): {response_text}")
                return json.loads(response_text)
        finally:
            if close_session:
                await session.close()

    # --------------- Campaign Management --------------- #

    async def start_campaign(
        self,
        name: str,
        recipients: List[Dict[str, str]],
        mode: str = "sequential",
        concurrent_limit: int = 1,
        call_gap_seconds: int = 30,
    ) -> Dict[str, Any]:
        """Create and start a new campaign."""
        campaign = call_store.make_campaign_record(
            name=name,
            recipients=recipients,
            mode=mode,
            concurrent_limit=concurrent_limit,
            call_gap_seconds=call_gap_seconds,
        )
        call_store.save_campaign(campaign)

        runner = CampaignRunner(
            campaign_id=campaign["campaign_id"],
            call_manager=self,
            mode=mode,
            concurrent_limit=concurrent_limit,
            call_gap_seconds=call_gap_seconds,
        )
        self.active_campaigns[campaign["campaign_id"]] = runner
        await runner.start()

        logger.info(f"[CALLMGR] Campaign '{name}' started with {len(recipients)} recipients")
        return campaign

    async def pause_campaign(self, campaign_id: str):
        runner = self.active_campaigns.get(campaign_id)
        if runner and runner.is_running:
            await runner.pause()
        else:
            raise ValueError(f"Campaign {campaign_id} is not running")

    async def resume_campaign(self, campaign_id: str):
        runner = self.active_campaigns.get(campaign_id)
        if runner:
            await runner.resume()
        else:
            # Recreate runner for a previously paused campaign
            campaign = call_store.get_campaign(campaign_id)
            if not campaign:
                raise ValueError(f"Campaign {campaign_id} not found")
            runner = CampaignRunner(
                campaign_id=campaign_id,
                call_manager=self,
                mode=campaign.get("mode", "sequential"),
                concurrent_limit=campaign.get("concurrent_limit", 1),
                call_gap_seconds=campaign.get("call_gap_seconds", 30),
            )
            self.active_campaigns[campaign_id] = runner
            await runner.start()

    async def cancel_campaign(self, campaign_id: str):
        runner = self.active_campaigns.get(campaign_id)
        if runner:
            await runner.cancel()
        else:
            call_store.update_campaign(
                campaign_id,
                status="cancelled",
                completed_at=datetime.now(timezone.utc).isoformat(),
            )

    def register_external_call(
        self,
        call_id: str,
        phone_number: str = "",
        call_type: str = "sip",
        campaign_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Register an already-initiated call (e.g. from Vobiz webhook)."""
        existing = call_store.get_call(call_id)
        if existing:
            return existing

        call_record = call_store.make_call_record(
            call_id=call_id,
            phone_number=phone_number,
            call_type=call_type,
            campaign_id=campaign_id,
        )
        call_record["status"] = "ringing"
        call_record["ringing_at"] = datetime.now(timezone.utc).isoformat()
        call_store.save_call(call_record)
        
        self._current_call_id = call_id
        logger.info(f"[CALLMGR] Registered external call {call_id} (to: {phone_number})")
        return call_record

    # --------------- Call Lifecycle Events (from bot_live.py) --------------- #

    def on_call_connected(self, call_id: str, vobiz_uuid: Optional[str] = None):
        """Called when a call is answered."""
        fields = {
            "status": "connected",
            "connected_at": datetime.now(timezone.utc).isoformat(),
        }
        if vobiz_uuid:
            fields["vobiz_call_uuid"] = vobiz_uuid
        call_store.update_call(call_id, **fields)
        self._current_call_id = call_id
        logger.info(f"[CALLMGR] Call {call_id} connected")

    def on_call_ended(self, call_id: str, duration_seconds: float = 0, end_reason: str = "hangup"):
        """Called when a call ends."""
        call_store.update_call(
            call_id,
            status="completed",
            ended_at=datetime.now(timezone.utc).isoformat(),
            duration_seconds=round(duration_seconds, 1),
            duration_minutes=call_store.round_up_minutes(duration_seconds),
            end_reason=end_reason,
        )
        if self._current_call_id == call_id:
            self._current_call_id = None
        logger.info(f"[CALLMGR] Call {call_id} ended — {duration_seconds:.1f}s ({end_reason})")

    def on_transcript_update(self, call_id: str, messages: list):
        """Called to update transcript for a call."""
        call_store.update_call(call_id, transcript=messages)

    def on_recording_saved(self, call_id: str, recording_files: Dict[str, str]):
        """Called when recordings are saved to disk."""
        call_store.update_call(call_id, recording_files=recording_files)
        logger.info(f"[CALLMGR] Recordings saved for call {call_id}")

    def on_call_failed(self, call_id: str, reason: str = "error"):
        """Called when a call fails."""
        call_store.update_call(
            call_id,
            status="failed",
            ended_at=datetime.now(timezone.utc).isoformat(),
            end_reason=reason,
        )
        if self._current_call_id == call_id:
            self._current_call_id = None
        logger.info(f"[CALLMGR] Call {call_id} failed: {reason}")


# --------------- Singleton --------------- #

_instance: Optional[CallManager] = None


def get_call_manager() -> CallManager:
    """Get or create the global CallManager instance."""
    global _instance
    if _instance is None:
        _instance = CallManager()
    return _instance
