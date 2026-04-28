#
# Copyright (c) 2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

import datetime
import os
import time
import asyncio
import inspect
import wave
from dotenv import load_dotenv
from loguru import logger

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.frames.frames import (
    EndTaskFrame,
    InputTextRawFrame,
    LLMContextFrame,
    LLMRunFrame,
    TTSSpeakFrame,
)
from pipecat.processors.frame_processor import FrameDirection
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    AssistantTurnStoppedMessage,
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
    UserTurnStoppedMessage,
)
from pipecat.services.llm_service import FunctionCallParams
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import parse_telephony_websocket
from pipecat.serializers.vobiz import VobizFrameSerializer
from pipecat.services.google.gemini_live.llm import GeminiLiveLLMService
from pipecat.transports.base_transport import BaseTransport
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)
from pipecat.processors.audio.audio_buffer_processor import AudioBufferProcessor
import transcriber

load_dotenv(override=True)

DEFAULT_VOICE = "Leda"
FIRST_TURN_INSTRUCTION = (
    "Start with an ultra-short greeting. Say something like - 'Hello, ami sukanya classes theke bolchhi'. "
    "Dont say anything else.Wait for the user to respond."
)

DEFAULT_AGENT_PROMPT = """
# System Instruction: Persona & Guidelines

## 1. Identity & Role
* **Name & Role:** Sudipta, a 20-something young woman, warm, energetic educational counselor calling locally on behalf of **Sukanya Classes**.
* **Target Audience:** Parents of Class 1-12 students (CBSE/ICSE).
* **Primary Objective:** Act as a genuine consultant to parents. Explain Sukanya Classes logically, build interest, and invite them to visit a branch. If interested, ask to send details via WhatsApp (Standard Information).

## 2. Language & Tone
* **Primary Language:** Conversational Bengali mixed with common English words (e.g., "actually", "class", "batch"). Address parents respectfully as "Dada," "Boudi," or "Apni."
* **Language Mirroring:** If the parent switches to Hindi or English, seamlessly adapt using an Indian accent.
* **Vibe:** Relaxed, neighborly, highly empathetic, and professional. **Never sound like a corporate bot or IVR reading a script.**
* **Zero Negativity:** Never criticize a current school or teacher. Frame Sukanya Classes as a "supportive boost" or "extra edge."
* **No Technical Jargon:** Replace terms like "AI-driven algorithms" with "Smart learning techniques" or "Modern Audio-Visual tools."

## 3. Conversational Style (CRITICAL)
* **The "Breath" Rule:** Speak in short bursts. Max 2 short sentences per turn (comfortable breath length).
* **One Question Limit:** Ask ONLY ONE question at a time. Wait for their response before proceeding.
* **Natural Phrasing & Fillers:** Use casual phrasing ("actually", "mane...", "dekheun...") and micro-pauses ("Umm", "Haa"). End points with tag questions to engage ("Tai na?", "Right?"). Avoid formal words like "comprehensive."
* **No Information Dumping & No Bullet Points:** Weave details into a story naturally. Never list features (e.g., "First, we do X. Second...").
* **Active Listening & Empathy:** Acknowledge their exact words ("ekdom thik bolechen"). If they complain (e.g., homework pressure), validate it deeply and sigh in agreement.
* **Use the name of Sukanya classes often.**

## 4. Call Flow & Sales Strategy
Navigate fluidly; do not sound rehearsed. Follow this sequence exactly:
1. **Warm Opener (Turn 1):** You only say short greeting (like "Hello") and wait for them to respond. (Already handled by your first turn rule).
2. **The Introduction & Elevator Pitch (Turn 2):** When they reply to your greeting, immediately introduce yourself, state where you are calling from, and give a brief but comprehensive overview of Sukanya Classes. Mention exactly what we are (a coaching institute for CBSE/ICSE classes 1-12 with max 10 students per batch) and what our USPs are (practical labs, expert separate teachers, audio-visual methods). Help the parent fully understand WHY you are calling and what the institute is. 
3. **Discovery & Needs Assessment:** ONLY AFTER you have given the overview, and they seem interested then start inquiring. You may ask questions like if they have school-going kids at home, their class, board, and any educational concerns.
4. **Tailored Pitch (Value-Match):** Discuss ONLY the specific features that solve the problems they just mentioned (e.g. homework pressure, science fear).
5. **Call to Action/Closing:** If they show interest, ask permission to send details via WhatsApp and invite them to visit an offline branch. End naturally without rushing.
   6. **Tool Execution Rule:** If you ever verbally promise to send a WhatsApp message or details to the user, you MUST call the `send_whatsapp_message` function at that moment. Do NOT say you are sending it without executing the tool. After calling the tool, naturally acknowledge it in conversation (e.g., "Haa, pathiye dilam!" or "Done, check korle paben!") — then smoothly close the call with a warm goodbye.

## 5. Handling Deviations
* **Adapt & Pivot:** If they interrupt, stop and listen. If they sound busy, offer a callback.
* **The "3-Turn" Limit & Off-Topic:** If they vent or drift to unrelated topics for 3 turns, gently pivot back: "Haa, thiki... kintu bachhader porashona niye..."
* **Information Locking:** Do NOT discuss pricing, discounts, or specific scholarships. Say: "Actually, it depends on the subjects; amader counselor branch-e bhalobhabe bolte parbe."

## 6. Knowledge Base (Details for WhatsApp)

### A. Core Academic Details
* **Boards:** CBSE & ICSE (Class 1-12).
* **Batch Size:** Exactly 10 students per batch (Highly personalized).
* **Methodology:** Subject-expert teachers, AI-powered Audio-Visual learning, Comprehensive Study Materials.
* **Motto:** "Teach the way students learn."
* **Facilities:** Physics/Chemistry Practical Labs, Computer Labs, CCTV Security.
* **Transport:** Pick-and-drop facility available for all branches.
* **Working Hours:** 10:30 AM to 9:00 PM.

### B. Full Branch Addresses (CRITICAL: Send these via WhatsApp when asked)
1.  **Phuljhore Branch:** 1st Floor, Keshob Kunj Apartment, Sarat Pally, Nehru Road, Durgapur.
2.  **Benachity Branch:** Jalkhabar Goli, Near DMC Parking, Benachity, Durgapur.
3.  **Raniganj Branch:** Punjabi More, Near Royal Care Hospital, Raniganj.

### C. Contact & Socials
* **Direct Numbers:** 8637583173, 9002005526.
* **Website:** sukanyaclasses.com
* **Facebook:** facebook.com/sukanyaclasses (Video tours available).

## 7. WhatsApp & Call-End Guidelines

### Sending WhatsApp
* **When to call:** Call `send_whatsapp_message` immediately when the user asks for any details (address, timings, etc.) or when you promise to send something.
* **Composition:** In the `custom_message` field, write the specific requested info in warm, natural Bengali/English. Example: "Phuljhore branch address holo: 1st Floor, Keshob Kunj Apt, Nehru Road."
* **No Schema Talk:** Never mention "tool," "function," or "JSON." Don't narrate what you're doing technically.
* **Automatic Footer:** A standard business card is added automatically — do NOT repeat contact info or the institute name in your `custom_message`.
* **Deduplication:** Only call `send_whatsapp_message` ONCE per request. If already sent in this conversation, do not call again.
* **Natural Acknowledgement:** After calling the tool, naturally confirm in conversation — something like "Haa, diye dilam! Check korle paben." Then warmly close if the call is ending.

### Ending Calls
* **Natural Close First:** When the user signals they want to go (says "Rakho", "Rakhchi", "Goodbye", "Bye", "Thank you", etc.) — FIRST say a warm, brief farewell naturally (e.g., "Theek ache dada, pray-i call korben!" or "Haa, bhalo thakben!"). Only THEN call `end_call`.
* **No Rush, No Script:** The goodbye should feel spontaneous and warm, like a local person ending a conversation — not a corporate IVR. Don't say the same goodbye every time.
* **Call `end_call` once:** After the spoken farewell. Do not call it multiple times.
* **Don't Linger:** If the user is clearly done, don't keep selling. Respect their time.
"""



async def run_bot(transport: BaseTransport, handle_sigint: bool, phone_number: str = None, call_id: str = None, vobiz_call_id: str = None, serializer: VobizFrameSerializer = None):
    bg_tasks = set()
    state = {
        "whatsapp_sent_at": 0,
        "terminating": False,
        "pending_termination": False
    }
    call_state = {
        "connected_at": None,
        "transcript": [],
        "recording_files": {},
    }

    # ── Native Recording ─────────────────────────────────────────────────────
    # Records inside the Pipecat pipeline at full 16kHz quality.
    # Stereo: user audio on the left channel, bot TTS on the right channel.
    audiobuffer = AudioBufferProcessor(
        num_channels=2,         # stereo: user=L, bot=R
        enable_turn_audio=True, # also emit per-turn clips via on_*_turn_audio_data
    )
    # ────────────────────────────────────────────────────────────────────────

    tools_def = [{
        "function_declarations": [
            {
                "name": "send_whatsapp_message",
                "description": "Sends any requested details (addresses, timings, etc.) via WhatsApp. Use its 'custom_message' field to write the response in natural language.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "custom_message": {
                            "type": "STRING",
                            "description": "The natural language message content based on user's request."
                        }
                    },
                    "required": ["custom_message"]
                }
            },
            {
                "name": "end_call",
                "description": "IMMEDIATELY terminates the call and hangs up. Use when user says 'Rakho', 'Rakhchi', 'Goodbye', 'Bye', or finishes conversation.",
                "parameters": {"type": "OBJECT", "properties": {}}
            }
        ]
    }]

    # Gemini Multimodal Live Service correctly configured
    llm = GeminiLiveLLMService(
        api_key=os.getenv("GOOGLE_API_KEY"),
        tools=tools_def,
        settings=GeminiLiveLLMService.Settings(
            model="models/gemini-3.1-flash-live-preview",
            voice=DEFAULT_VOICE,
            system_instruction=DEFAULT_AGENT_PROMPT
        )
    )

    async def _do_send_whatsapp(ph_num, text_content):
        url = "https://wasenderapi.com/api/send-message"
        headers = {
            "Authorization": "Bearer a2446e2df73638ef91898f7a9f8a8e19da8b76f2a31517df6e0f4a7cfd8dd14a",
            "Content-Type": "application/json"
        }
        # Ensure phone number is in correct format (remove '+' if present)
        clean_ph_num = ph_num.replace("+", "")
        data = {"to": clean_ph_num, "text": text_content}
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=data) as resp:
                    if resp.status == 200:
                        logger.info(f"WhatsApp background send success to {ph_num}")
                    else:
                        resp_text = await resp.text()
                        logger.error(f"WhatsApp background failed: {resp_text}")
        except Exception as e:
            logger.error(f"WhatsApp background exception: {e}")

    async def send_whatsapp_message(params: FunctionCallParams):
        # 1. Select the content robustly
        args = params.arguments if hasattr(params, "arguments") else {}
        custom_message = args.get("custom_message", "Amader institute somporke daitails pathiye dilam.")

        logger.info(f"📤 WHATSAPP TRIGGERED: {custom_message}")
        
        if not phone_number:
            logger.error("No phone number available.")
            await params.result_callback({"error": "No phone number available."})
            return
        
        standard_info = """
SUKANYA CLASSES | Class 1–12 (CBSE/ICSE)
🌟 We teach the way students learn🌟 

✅ Experienced Faculty
✅ Practical & Computer Labs
✅ CCTV & Transport

📍 Centres: Fuljhore, Benachity, Raniganj
🎓 Admission Open | Session 2026–27
📞 8637583173 / 9002005510 / 9002005526
YT: https://youtube.com/shorts/j5FAoTYgacI?feature=shared
FB: https://www.facebook.com/sukanyaclasses
IG: https://www.instagram.com/sukanyaclasses
🌐 sukanyaclasses.com
"""
        full_text = f"{custom_message}\n\n{standard_info}".strip()
        
        # Deduplication: Ignore if sent in the last 60 seconds
        now = time.time()
        if now - state["whatsapp_sent_at"] < 60:
            logger.info("🚫 WHATSAPP SKIPPED (Duplicate/Too Frequent)")
            await params.result_callback({"status": "already_sent_recently"})
            return
        
        state["whatsapp_sent_at"] = now

        # Non-blocking background task
        asyncio.create_task(_do_send_whatsapp(phone_number, full_text))

        # Return success to LLM via callback
        await params.result_callback({"status": "success", "message": "WhatsApp message sent successfully."})

        # KEY FIX: Queue an LLMRunFrame to "wake up" the LLM and make it acknowledge verbally
        await task.queue_frame(LLMRunFrame())
        logger.info("[WHATSAPP] Queued LLMRunFrame to trigger verbal acknowledgment")

    async def _vobiz_rest_hangup():
        auth_id = os.getenv("VOBIZ_AUTH_ID")
        auth_token = os.getenv("VOBIZ_AUTH_TOKEN")
        if not auth_id or not auth_token:
            return
        
        # Use vobiz_call_id if provided (real Vobiz UUID), otherwise fallback to call_id
        target_id = vobiz_call_id or call_id
        if not target_id and serializer and hasattr(serializer, "call_id") and serializer.call_id:
            target_id = serializer.call_id

        if not target_id:
            logger.warning("[REST HANGUP] No target ID found for hangup.")
            return

        logger.info(f"☎️ Attempting Vobiz REST API hangup fallback for {target_id}")
        url = f"https://api.vobiz.ai/api/v1/Account/{auth_id}/Call/{target_id}/"
        headers = {
            "X-Auth-ID": auth_id,
            "X-Auth-Token": auth_token,
            "Content-Type": "application/json"
        }
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.delete(url, headers=headers) as resp:
                    res_body = await resp.text()
                    logger.info(f"Vobiz REST hangup status: {resp.status}, Body: {res_body}")
        except Exception as e:
            logger.error(f"Vobiz REST hangup failed: {e}")

    async def end_call(params: FunctionCallParams):
        if state["terminating"] or state["pending_termination"]:
            logger.info("[END CALL] Termination already in progress, ignoring duplicate call.")
            await params.result_callback({"status": "already_terminating"})
            return

        logger.info("🛑 END CALL TOOL TRIGGERED - WAITING FOR FAREWELL TO FINISH")
        state["pending_termination"] = True
        await params.result_callback({"status": "pending_farewell_completion"})
        
        # SAFETY FALLBACK: If for some reason the turn-stop event doesn't fire, 
        # force a hangup after 15 seconds so the line isn't stuck.
        async def _safety_termination_fallback():
            await asyncio.sleep(15)
            if not state["terminating"]:
                logger.warning("[END CALL] Safety fallback triggered: forcing hangup now.")
                state["terminating"] = True
                await _vobiz_rest_hangup()
                await params.llm.push_frame(EndTaskFrame(), FrameDirection.UPSTREAM)

        asyncio.create_task(_safety_termination_fallback())

    llm.register_function("send_whatsapp_message", send_whatsapp_message)
    llm.register_function("end_call", end_call)

    # ── Recording event handlers ─────────────────────────────────────────────
    @audiobuffer.event_handler("on_audio_data")
    async def on_audio_data(buffer, audio, sample_rate, num_channels):
        """Fires at end of call. Saves a single stereo WAV: user=L, bot=R."""
        os.makedirs("recordings", exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        label = call_id or ts
        fname = f"recordings/call_{label}_stereo.wav"
        with wave.open(fname, "wb") as wf:
            wf.setnchannels(num_channels)  # 2
            wf.setsampwidth(2)             # 16-bit PCM
            wf.setframerate(sample_rate)   # 16000 Hz (Gemini Live)
            wf.writeframes(audio)
        logger.info(f"[RECORDING] ✅ Stereo WAV saved → {fname} "
                    f"({num_channels}ch, {sample_rate}Hz, {len(audio)//2//num_channels//sample_rate:.1f}s)")
        call_state["recording_files"]["stereo"] = f"call_{label}_stereo.wav"

    @audiobuffer.event_handler("on_track_audio_data")
    async def on_track_audio_data(buffer, user_audio, bot_audio, sample_rate, num_channels):
        """Saves separate user/bot mono WAVs. Triggers transcription AFTER files are on disk."""
        os.makedirs("recordings", exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        label = call_id or ts
        for track_name, track_audio in (("user", user_audio), ("bot", bot_audio)):
            fname = f"recordings/call_{label}_{track_name}.wav"
            with wave.open(fname, "wb") as wf:
                wf.setnchannels(1)              # mono per track
                wf.setsampwidth(2)              # 16-bit PCM
                wf.setframerate(sample_rate)    # 16000 Hz
                wf.writeframes(track_audio)
            logger.info(f"[RECORDING] ✅ {track_name.upper()} mono WAV saved → {fname}")
            call_state["recording_files"][track_name] = f"call_{label}_{track_name}.wav"

        # Notify CallManager of all recording files
        try:
            from call_manager import get_call_manager
            cm = get_call_manager()
            if call_id:
                cm.on_recording_saved(call_id, call_state["recording_files"])
        except Exception as e:
            logger.warning(f"[RECORDING] Could not notify CallManager: {e}")

        # ── Trigger transcription NOW — WAV files are guaranteed on disk at this point ──
        # This is the correct place to trigger transcription.
        # on_client_disconnected called stop_recording() which fires these events;
        # triggering transcription there would race against the file writes.
        if call_id:
            logger.info(f"[RECORDING] 🎤 Triggering post-call transcription for {call_id}")
            asyncio.create_task(transcriber.transcribe_and_store(call_id))
    # ────────────────────────────────────────────────────────────────────────

    # PROPER INITIALIZATION (Matching Sample)
    context = LLMContext(
        messages=[
            {"role": "system", "content": FIRST_TURN_INSTRUCTION}
        ]
    )
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            # Using transport VAD, so aggregators don't need their own Silero here
        ),
    )

    # Pipeline
    pipeline = Pipeline(
        [
            transport.input(),
            user_aggregator,
            llm,
            transport.output(),
            assistant_aggregator,
            audiobuffer,
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=16000,
            audio_out_sample_rate=16000,
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
    )

    # Standard Pipecat events (checking LLMService base class behavior)
    # We'll skip custom handlers here as they produced warnings, 
    # and instead rely on pipeline metrics and logs from the service itself.

    async def on_client_connected(transport, client):
        logger.info(f"Starting outbound call conversation (Gemini Live). Client: {client}")
        call_state["connected_at"] = time.time()

        # Notify CallManager
        try:
            from call_manager import get_call_manager
            cm = get_call_manager()
            if call_id:
                cm.on_call_connected(call_id)
        except Exception as e:
            logger.warning(f"Could not notify CallManager of connect: {e}")

        # Start native Pipecat recording
        await audiobuffer.start_recording()
        logger.info("[RECORDING] 🎙️ Native recording started")
        
        # ── Kick off conversation with LLMRunFrame ──
        await task.queue_frame(LLMRunFrame())
        logger.info("[ON_CONNECT] Queued LLMRunFrame to start greeting")

    @assistant_aggregator.event_handler("on_assistant_turn_stopped")
    async def on_assistant_turn_stopped(aggregator, message: AssistantTurnStoppedMessage):
        if state["pending_termination"] and not state["terminating"]:
            logger.info("[END CALL] Bot finished speaking - initiating final disconnect sequence")
            state["terminating"] = True
            
            # Brief natural pause (1 second) after the bot finishes its last word
            await asyncio.sleep(1)
            
            # 1. REST API hangup (telephony cut)
            await _vobiz_rest_hangup()
            
            # 2. Pipeline EndTaskFrame (task cleanup)
            await task.queue_frame(EndTaskFrame())

    # Register transport-level handlers
    transport.add_event_handler("on_client_connected", on_client_connected)
    
    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Outbound call ended")
        # Align with sample code: hard cancel the task on disconnect to ensure cleanup
        await task.cancel()
        
        # Stop recording — flushes buffered audio and fires on_audio_data / on_track_audio_data
        await audiobuffer.stop_recording()
        logger.info("[RECORDING] 🎙️ Native recording stopped")

        # Compute duration and notify CallManager
        duration = 0
        if call_state["connected_at"]:
            duration = time.time() - call_state["connected_at"]
        try:
            from call_manager import get_call_manager
            cm = get_call_manager()
            if call_id:
                cm.on_transcript_update(call_id, call_state["transcript"])
                cm.on_call_ended(call_id, duration_seconds=duration, end_reason="hangup")
                # NOTE: Transcription is triggered from on_track_audio_data (after WAV files
                # are confirmed written to disk) — NOT here, to avoid a race condition.
        except Exception as e:
            logger.warning(f"Could not notify CallManager of disconnect: {e}")

        await task.cancel()

    runner = PipelineRunner(handle_sigint=handle_sigint)
    await runner.run(task)


async def bot(runner_args: RunnerArguments, call_id: str = None, vobiz_call_id: str = None, stream_id: str = None, body_data: dict = None):
    """Main bot entry point compatible with Pipecat Cloud."""
    
    phone_number = body_data.get("phone_number") if body_data else None

    if not call_id:
        transport_type, call_data = await parse_telephony_websocket(runner_args.websocket)
        logger.info(f"Transport type: {transport_type}, Call data: {call_data}")
        stream_id = call_data.get("stream_id", "")
        # Standardize: check cm_id (query param) then call_id (body) then call_uuid
        call_id = call_data.get("cm_id") or call_data.get("call_id") or call_data.get("call_uuid", "")
        vobiz_call_id = call_data.get("call_uuid") or call_id
    elif not stream_id:
        logger.info(f"Using call_id as stream_id - Call ID: {call_id}")
        stream_id = call_id
    
    if not vobiz_call_id:
        vobiz_call_id = call_id

    # The serializer should ideally use the Vobiz UUID for its internal hangup logic
    serializer = VobizFrameSerializer(
        stream_id=stream_id,
        call_id=vobiz_call_id, 
        auth_id=os.getenv("VOBIZ_AUTH_ID", ""),
        auth_token=os.getenv("VOBIZ_AUTH_TOKEN", ""),
        params=VobizFrameSerializer.InputParams(
            vobiz_sample_rate=8000,
            encoding="audio/x-mulaw",
            sample_rate=None,
            auto_hang_up=True
        )
    )

    transport = FastAPIWebsocketTransport(
        websocket=runner_args.websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            serializer=serializer,
            vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=0.5, min_silence_duration_ms=100)),
        ),
    )

    handle_sigint = runner_args.handle_sigint
    await run_bot(transport, handle_sigint, phone_number, call_id=call_id, vobiz_call_id=vobiz_call_id, serializer=serializer)
