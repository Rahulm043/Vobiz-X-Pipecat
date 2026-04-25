#
# Copyright (c) 2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

import os
import time
import asyncio
import inspect
from dotenv import load_dotenv
from loguru import logger

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.frames.frames import (
    EndFrame,
    EndTaskFrame,
    InputTextRawFrame,
    LLMContextFrame,
)
from pipecat.processors.frame_processor import FrameDirection
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import parse_telephony_websocket
from pipecat.serializers.vobiz import VobizFrameSerializer
from pipecat.services.google.gemini_live.llm import GeminiLiveLLMService
from pipecat.transports.base_transport import BaseTransport
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)

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
6. **Tool Execution Rule:** If you ever verbally promise to send a WhatsApp message or details to the user, you MUST simultaneously call the `send_whatsapp_message` function. Do NOT say you are sending it without executing the tool.

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

## 7. WhatsApp Tool Execution Guidelines (STRICT)

* **When to call:** Call `send_whatsapp_message` IMMEDIATELY when you say "I am sending details" or if the user asks for anything (address, fees, timing, etc.).
* **Composition Rule:** In the `custom_message` field, write a warm, helpful summary in natural language (Bengali/English mix). 
    * **Example:** "Phuljhore branch address holo: 1st Floor, Keshob Kunj Apt, Nehru Road. Amader batches Class 1 theke 12 porjonto hoy."
* **No Schema/Metadata:** Never mention "tool," "function," or "JSON." Do not verbally describe the tool call.
* **Automatic Footer:** A standard business card footer is AUTOMATICALLY added by the system. Do NOT repeat general links or the institute name in your `custom_message`. Focus on the specific answers the user requested.
* **Termination Rule:** You are responsible for hanging up the call. Call the 'end_call' tool immediately when the conversation reaches its natural conclusion or when the user indicates they want to finish the conversation. This includes(and not limited to) natural sign-offs like "Goodbye", "Byebye", "Rakho", "Katun", or simply "Thank you, that's all."
* **Deduplication Rule:** Only call 'send_whatsapp_message' ONCE per request. If you have already executed it in this conversation for the current details, do not call it again.
* **Non-Blocking:** Once you call a tool, assume it is delivered and continue the conversation or end it naturally.
"""



async def run_bot(transport: BaseTransport, handle_sigint: bool, phone_number: str = None, call_id: str = None):
    bg_tasks = set()
    state = {"whatsapp_sent_at": 0}

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
        data = {"to": ph_num, "text": text_content}
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

    async def send_whatsapp_message(*args, **kwargs):
        # 1. Try to get from args if passed positionally (Pipecat sometimes does this)
        custom_message = args[0] if args else None
        # 1. Select the content robustly
        if isinstance(custom_message, dict):
            custom_message = custom_message.get("custom_message") or custom_message.get("arguments", {}).get("custom_message", "")
        elif hasattr(custom_message, "arguments"):
            custom_message = custom_message.arguments.get("custom_message", "")
        
        # 2. Fallback to kwargs
        if not custom_message or not isinstance(custom_message, str):
            args = kwargs.get("arguments", {})
            custom_message = args.get("custom_message") or kwargs.get("custom_message")
        
        # 3. Final default
        custom_message = str(custom_message) if custom_message else "Amader institute somporke daitails pathiye dilam."

        logger.info(f"📤 WHATSAPP TRIGGERED: {custom_message}")
        
        if not phone_number:
            logger.error("No phone number available.")
            return "ERROR: No phone number."
        
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
            return "Function result: WhatsApp message was already sent recently. Do not repeat."
        
        state["whatsapp_sent_at"] = now

        # Non-blocking background task
        asyncio.create_task(_do_send_whatsapp(phone_number, full_text))
        
        # Directive return value to nudge the model to speak
        return "Function result: WhatsApp message successfully sent. You MUST confirm this verbally to the user."

    async def _vobiz_rest_hangup():
        if not call_id:
            return
        auth_id = os.getenv("VOBIZ_AUTH_ID")
        auth_token = os.getenv("VOBIZ_AUTH_TOKEN")
        if not auth_id or not auth_token:
            return
        
        logger.info(f"☎️ Attempting Vobiz REST API hangup fallback for {call_id}")
        url = f"https://api.vobiz.ai/api/v1/Account/{auth_id}/Call/{call_id}/"
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

    async def end_call(*args, **kwargs):
        logger.info("🛑 END CALL TOOL TRIGGERED - HANGING UP")
        
        # 1. Schedule a hard-cancel safety net (3 seconds to allow final audio to clear)
        async def safety_cancel():
            await asyncio.sleep(3)
            if not task.finished:
                logger.info("⏳ Safety canceler triggered - forcing task shutdown")
                # Try REST API hangup as final fallback
                await _vobiz_rest_hangup()
                await task.cancel()
        
        asyncio.create_task(safety_cancel())

        # 2. Push EndFrame directly to the transport to bypass Gemini Live's deferral
        # This ensures the WebSocket closes and the call is released by Vobiz promptly.
        await transport.push_frame(EndFrame())
        
        # 3. Standard pipeline termination frames
        await task.queue_frame(EndFrame())
        await llm.push_frame(EndTaskFrame(), FrameDirection.UPSTREAM)
        
        return "Function result: Call termination initiated."

    llm.register_function("send_whatsapp_message", send_whatsapp_message)
    llm.register_function("end_call", end_call)

    # Pipeline
    pipeline = Pipeline(
        [
            transport.input(),
            llm,
            transport.output(),
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
        
        # PROPER INITIALIZATION
        context = LLMContext(
            messages=[
                {"role": "system", "content": FIRST_TURN_INSTRUCTION}
            ]
        )
        # 2. Queue the context frame (Gemini Live uses this to seed the session)
        await task.queue_frame(LLMContextFrame(context))
        
        # 3. Queue an InputTextRawFrame to 'provoke' the first response
        # Gemini often needs a small nudge or turn_complete to start talking.
        # We tell it gently to speak the first greeting.
        await task.queue_frame(InputTextRawFrame(text="Please start the conversation based on the first turn instruction."))

    # Register transport-level handlers
    transport.add_event_handler("on_client_connected", on_client_connected)
    
    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Outbound call ended")
        await task.cancel()

    runner = PipelineRunner(handle_sigint=handle_sigint)
    await runner.run(task)


async def bot(runner_args: RunnerArguments, call_id: str = None, stream_id: str = None, body_data: dict = None):
    """Main bot entry point compatible with Pipecat Cloud."""
    
    phone_number = body_data.get("phone_number") if body_data else None

    if not call_id:
        transport_type, call_data = await parse_telephony_websocket(runner_args.websocket)
        logger.info(f"Transport type: {transport_type}, Call data: {call_data}")
        stream_id = call_data.get("stream_id", "")
        call_id = call_data.get("call_id", "")
    elif not stream_id:
        logger.info(f"Using call_id as stream_id - Call ID: {call_id}")
        stream_id = call_id
    else:
        logger.info(f"Using pre-parsed call data - Call ID: {call_id}, Stream ID: {stream_id}")

    serializer = VobizFrameSerializer(
        stream_id=stream_id,
        call_id=call_id,
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
            vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=0.3)),
        ),
    )

    handle_sigint = runner_args.handle_sigint
    await run_bot(transport, handle_sigint, phone_number, call_id=call_id)
