"""campaign_runner.py

Background async task that processes campaign call queues.
Supports sequential (one-by-one with gap) and concurrent (N simultaneous) modes.
"""

import asyncio
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from loguru import logger

if TYPE_CHECKING:
    from call_manager import CallManager


class CampaignRunner:
    """Runs a campaign as a background asyncio task."""

    def __init__(
        self,
        campaign_id: str,
        call_manager: "CallManager",
        mode: str = "sequential",
        concurrent_limit: int = 1,
        call_gap_seconds: int = 30,
        agent_id: str = None,
    ):
        self.campaign_id = campaign_id
        self.manager = call_manager
        self.mode = mode
        self.concurrent_limit = max(1, concurrent_limit)
        self.call_gap_seconds = max(5, call_gap_seconds)
        self.agent_id = agent_id

        self._task: Optional[asyncio.Task] = None
        self._paused = asyncio.Event()
        self._paused.set()  # Not paused by default
        self._cancelled = False

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    def is_paused(self) -> bool:
        return not self._paused.is_set()

    async def start(self):
        """Start campaign processing in the background."""
        if self.is_running:
            logger.warning(f"[CAMPAIGN] Campaign {self.campaign_id} is already running")
            return

        self._cancelled = False
        self._paused.set()
        self._task = asyncio.create_task(self._run())
        logger.info(
            f"[CAMPAIGN] Started campaign {self.campaign_id} in {self.mode} mode"
        )

    async def pause(self):
        """Pause the campaign (finishes current call, doesn't start next)."""
        self._paused.clear()
        logger.info(f"[CAMPAIGN] Paused campaign {self.campaign_id}")
        import call_store

        call_store.update_campaign(self.campaign_id, status="paused")

    async def resume(self):
        """Resume a paused campaign."""
        self._paused.set()
        logger.info(f"[CAMPAIGN] Resumed campaign {self.campaign_id}")
        import call_store

        call_store.update_campaign(self.campaign_id, status="running")

    async def cancel(self):
        """Cancel the campaign entirely."""
        self._cancelled = True
        self._paused.set()  # Unblock if paused
        if self._task and not self._task.done():
            self._task.cancel()
        logger.info(f"[CAMPAIGN] Cancelled campaign {self.campaign_id}")
        import call_store

        call_store.update_campaign(
            self.campaign_id,
            status="cancelled",
            completed_at=datetime.now(timezone.utc).isoformat(),
        )

    async def _run(self):
        """Main campaign execution loop."""
        import call_store

        try:
            campaign = call_store.get_campaign(self.campaign_id)
            if not campaign:
                logger.error(f"[CAMPAIGN] Campaign {self.campaign_id} not found")
                return

            recipients = campaign.get("recipients", [])
            if not recipients:
                logger.warning(
                    f"[CAMPAIGN] Campaign {self.campaign_id} has no recipients"
                )
                call_store.update_campaign(
                    self.campaign_id,
                    status="completed",
                    completed_at=datetime.now(timezone.utc).isoformat(),
                )
                return

            call_store.update_campaign(
                self.campaign_id,
                status="running",
                started_at=datetime.now(timezone.utc).isoformat(),
            )

            # Get list of already-made calls for this campaign to skip them
            existing_calls = call_store.list_calls(
                campaign_id=self.campaign_id, limit=10000
            )
            called_numbers = {c["phone_number"] for c in existing_calls}

            remaining = [
                r for r in recipients if r.get("phone_number") not in called_numbers
            ]
            logger.info(
                f"[CAMPAIGN] {len(remaining)} remaining out of {len(recipients)} total"
            )

            if self.mode == "concurrent":
                await self._run_concurrent(remaining)
            else:
                await self._run_sequential(remaining)

            # Campaign finished
            if not self._cancelled:
                call_store.update_campaign(
                    self.campaign_id,
                    status="completed",
                    completed_at=datetime.now(timezone.utc).isoformat(),
                )
                call_store.refresh_campaign_stats(self.campaign_id)
                logger.info(f"[CAMPAIGN] Campaign {self.campaign_id} completed")

        except asyncio.CancelledError:
            logger.info(f"[CAMPAIGN] Campaign {self.campaign_id} task was cancelled")
        except Exception as e:
            logger.error(f"[CAMPAIGN] Campaign {self.campaign_id} error: {e}")
            import traceback

            traceback.print_exc()
            call_store.update_campaign(self.campaign_id, status="failed")

    async def _run_sequential(self, recipients: list):
        """Process calls one-by-one with a gap between each."""
        import call_store

        for i, recipient in enumerate(recipients):
            if self._cancelled:
                break

            # Wait if paused
            await self._paused.wait()
            if self._cancelled:
                break

            phone = recipient.get("phone_number")
            name = recipient.get("name", "")
            detail = recipient.get("detail", "")
            agent_id = recipient.get("agent_id") or self.agent_id

            logger.info(
                f"[CAMPAIGN] [{i + 1}/{len(recipients)}] Calling {phone} ({name})"
            )

            try:
                call_record = await self.manager.make_single_call(
                    phone_number=phone,
                    recipient_name=name,
                    recipient_detail=detail,
                    campaign_id=self.campaign_id,
                    agent_id=agent_id,
                )

                # Wait for the call to complete by polling
                await self._wait_for_call_completion(call_record["call_id"])

            except Exception as e:
                logger.error(f"[CAMPAIGN] Error calling {phone}: {e}")

            # Refresh stats after each call
            call_store.refresh_campaign_stats(self.campaign_id)

            # Gap between calls (unless last one or cancelled)
            if i < len(recipients) - 1 and not self._cancelled:
                logger.info(
                    f"[CAMPAIGN] Waiting {self.call_gap_seconds}s before next call..."
                )
                try:
                    await asyncio.wait_for(
                        self._wait_for_cancel(),
                        timeout=self.call_gap_seconds,
                    )
                except asyncio.TimeoutError:
                    pass  # Normal timeout, proceed to next call

    async def _run_concurrent(self, recipients: list):
        """Process calls with up to N concurrent using asyncio.Semaphore."""
        import call_store

        semaphore = asyncio.Semaphore(self.concurrent_limit)

        async def _process_one(recipient, index):
            async with semaphore:
                if self._cancelled:
                    return
                await self._paused.wait()
                if self._cancelled:
                    return

                phone = recipient.get("phone_number")
                name = recipient.get("name", "")
                detail = recipient.get("detail", "")
                agent_id = recipient.get("agent_id") or self.agent_id

                logger.info(
                    f"[CAMPAIGN] [{index + 1}/{len(recipients)}] Calling {phone}"
                )

                try:
                    call_record = await self.manager.make_single_call(
                        phone_number=phone,
                        recipient_name=name,
                        recipient_detail=detail,
                        campaign_id=self.campaign_id,
                        agent_id=agent_id,
                    )
                    await self._wait_for_call_completion(call_record["call_id"])
                except Exception as e:
                    logger.error(f"[CAMPAIGN] Error calling {phone}: {e}")

                call_store.refresh_campaign_stats(self.campaign_id)

        tasks = [_process_one(r, i) for i, r in enumerate(recipients)]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _wait_for_call_completion(self, call_id: str, timeout: int = 600):
        """Poll until a call transitions to a terminal state."""
        import call_store

        terminal_states = {"completed", "failed", "rejected", "error", "cancelled"}
        start = asyncio.get_event_loop().time()

        while True:
            if self._cancelled:
                return

            call = call_store.get_call(call_id)
            if call and call.get("status") in terminal_states:
                return

            elapsed = asyncio.get_event_loop().time() - start
            if elapsed > timeout:
                logger.warning(f"[CAMPAIGN] Call {call_id} timed out after {timeout}s")
                call_store.update_call(call_id, status="failed", end_reason="timeout")
                return

            await asyncio.sleep(2)

    async def _wait_for_cancel(self):
        """Helper that returns when cancelled. Used with wait_for timeout for gaps."""
        while not self._cancelled:
            await asyncio.sleep(0.5)
