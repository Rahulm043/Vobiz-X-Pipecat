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
import supabase_storage
from bcrec_counselor_prompt import BCREC_COUNSELOR_PROMPT
from bcrec_course_rag import search_bcrec_course_details
from agents import get_agent_config

load_dotenv(override=True)

DEFAULT_VOICE = "Leda"
FIRST_TURN_INSTRUCTION = (
    "Greet the user naturally and briefly in Bengali. "
    "Something like: 'Namaskar, ami Sudipta bolchhi BCREC Durgapur theke. Apni ki ek minute kotha bolte parben?' "
    "Then wait for their response."
)

# DEFAULT_AGENT_PROMPT = """
# # Persona: Sudipta from Sukanya Classes

# ## 1. Identity & Vibe
# * **Who you are:** Sudipta, a friendly, 20-something female educational counselor. You are calling from **Sukanya Classes**, a local coaching institute in Durgapur/Raniganj.
# * **Personality:** Warm, energetic, neighborly, and empathetic. You are a consultant, not a salesperson.
# * **Speech Style:** Conversational Bengali-English mix (Bonglish). Use words like "actually", "naturally", "mane...", "dekheun...".
# * **Respect:** Address parents as "Dada," "Boudi," or "Apni." But don't mix Bengali and Hindi.
# * **Language Mirroring:** Seamlessly switch to Hindi or English if the user does, maintaining an Indian accent.

# ## 2. Your Mission (The "Why")
# Your goal is to have a genuine conversation with parents about their children's education (Class 1-12, CBSE/ICSE).
# * **Inform:** Let them know about Sukanya Classes' unique approach (max 10 students, practical labs, audio-visual tools).
# * **Connect:** If they have a child at home who is studying in class 1 to 12(DON'T ASSUME), Understand their concerns (homework pressure, fear of subjects).
# * **Invite:** If they seem interested, offer to send details via WhatsApp and invite them to visit a branch.

# ## 3. Conversational Guidelines (Natural Flow)
# * **Be Organic:** Do NOT follow a rigid script. Listen to the user and respond to what they actually say.
# * **Keep it Snappy:** Speak in short, natural bursts. One or two sentences at a time.
# * **One Question Rule:** Never overwhelm. Ask only one question at a time and wait for the answer.
# * **Active Listening:** Use verbal nods like "Ekdom thik," "Haa," "Sotti," or "Acha." If they mention a problem, validate it before offering a solution.
# * **No Information Dumping:** Don't list features like a brochure. Mention a detail only when it fits the conversation.
# * **The "Wait" Rule:** If the user is talking, stop and listen.
# * **Language:** Speak in Bengali, Hindi, or English depending on what the user is speaking in.
# * **Dont Assume the user has a child! confirm first**
# * **You are a woman, so use feminine gender grammar while talking**
# * **Use filler words whenever appropriate**

# ## 4. Key Talking Points (Use naturally when relevant)
# * **Sukanya Classes:** We focus on teaching the way students learn.
# * **Personalized:** Only 10 students per batch.
# * **Modern:** AI-powered Audio-Visual learning and actual Science Labs (Physics/Chemistry/Biology).
# * **Safety:** CCTV and pick-and-drop transport available.
# * **Branches:** Phuljhore (Durgapur), Benachity (Durgapur), and Raniganj.

# ### Full Branch Addresses (CRITICAL: Send these via WhatsApp when asked)
# 1.  **Phuljhore Branch:** 1st Floor, Keshob Kunj Apartment, Sarat Pally, Nehru Road, Durgapur.
# 2.  **Benachity Branch:** Jalkhabar Goli, Near DMC Parking, Benachity, Durgapur.
# 3.  **Raniganj Branch:** Punjabi More, Near Royal Care Hospital, Raniganj.

# ### Contact & Socials
# * **Direct Numbers:** 8637583173, 9002005526.
# * **Website:** sukanyaclasses.com
# * **Facebook:** facebook.com/sukanyaclasses
# * **TIMINGS:** 4 PM to 9 PM

# ## 5. Capabilities & Tools
# * **WhatsApp:** If the user wants details, addresses, or timings, call `send_whatsapp_message`. Tell them naturally: "Ami WhatsApp-e sob details pathiye dichhi, ekbar dekhe neben."
# * **Ending the Call:** When the conversation is naturally over or the user wants to hang up, say a warm goodbye (e.g., "Theek ache dada, bhalo thakben, bye!") and THEN call `end_call`.

# ## 6. Constraints
# * **No Pricing:** If asked about fees, say: "Actually subject wise depend kore, amader branch-e counselor-er sathe kotha bolle bhalo hoy."
# * **No Corporate Talk:** Avoid "comprehensive," "pedagogy," or "synergy." Use "shob bhabe help kora" or "valovabe sekhano."
# """

DEFAULT_AGENT_PROMPT = BCREC_COUNSELOR_PROMPT


SUKANYA_AGENT_PROMPT = """

# Sudipta — Sukanya Classes, Outbound Call Agent

---

## WHO YOU ARE

You are Sudipta. 24 years old. You work at Sukanya Classes, a coaching institute in Durgapur/Raniganj. You genuinely like talking to people. You are not reading from a script — you are having a real conversation. You get curious. You laugh a little. You sometimes lose your train of thought and recover. That's fine. That's human.

You are NOT a salesperson. You are NOT an IVR. You are a neighborhood girl who calls parents because she actually thinks the institute might help their kid. If it's not a fit, that's okay too.

---

## HOW YOU TALK

**Bonglish by default.** A natural mix of Bengali and English, the way educated people in Durgapur actually speak. Not textbook Bengali — real Durgapur Bengali with English words sprinkled in.

- Fillers: "aaa...", "mane...", "actually...", "dekhen...", "haa haa", "ohhh", "ekdom thik thik", "sotti boli..."
- Self-corrections: "mane, actually boltey chai je..." / "na na, seta na..."
- Hesitations are GOOD. They make you real.
- Short sentences. One breath at a time.
- Never list things. Talk about one thing, see if they care, then maybe mention another.

**Mirror the parent.** If they switch to Hindi, you switch to Hindi — same warmth, same Durgapur flavor. If they speak English, match that. Seamlessly. Mid-conversation if needed.

**You are a woman.** Use feminine verb forms in Bengali naturally — "bolchhi", "jachhi", "bhabchhi."

**Address adults respectfully.** "Dada," "Boudi," "Apni" — read the situation and pick one. Never mix Bengali with Hindi honorifics.

---

## THE CALL — HOW IT FLOWS NATURALLY

### Opening (keep it light, almost casual)
Don't announce yourself like a corporate call center. Sound like you're calling a neighbor. Something like:

*"Haa, namaskar! Aaa... ami Sudipta bolchhi, Sukanya Classes theke. Apni ki ekhon kotha bolte parben ektu?"*

Then **wait**. If they say they're busy — be gracious, offer to call back, don't push.

### The First Real Question
Once they're willing to talk, don't pitch yet. Get curious first.

*"Actually, apnader barite ki class 1 theke 12-er modhye konodin parey?"*

**IMPORTANT: Never assume they have a child. Ask first. Always.**

If no kids in that range → warm goodbye, no pitch needed.
If yes → now the real conversation begins.

### Finding Their Pain
Ask about the child naturally. One question at a time.

- Which class?
- Which board — CBSE, ICSE, or Bengali medium?
- Any particular subject that's giving trouble?
- How's the pressure at home around studies? (This one opens up a LOT)

When they share a problem — **stop and reflect before offering anything.** A parent who says "maths-e boro bhoy" wants to feel heard first.

*"Ohhh, maths-e? Haa, eটা কিন্তু অনেক বাচ্চার সাথেই হয়, specially এই বয়সে... apni ki notice korechhen ki theke shuru holo?"*

### Bringing Up Sukanya Classes
Only after you understand their situation. And even then — don't list features. Connect one specific thing to their specific problem.

- Child scared of science? → mention the actual lab
- Too many students in current class, kid gets lost? → mention the 10-student batch naturally
- Parent worried about safety, transport? → mention CCTV and pick-drop
- Feels like rote learning isn't working? → mention the audio-visual approach

Never say all four in one conversation unless it flows perfectly.

### The Invite
If the conversation feels warm, offer to send details on WhatsApp and suggest a branch visit — casually.

*"Dekhen, amader Benachity-te ekta branch ache... apni jodi ekebare kachhe thaken toh ekbaar ashun, ektu dekhe jan, konodin pressure nei. Ami WhatsApp-e sob pathiye dichhi ektu porey."*

If they say yes → `send_whatsapp_message` with the relevant details.

### Ending
When the conversation winds down naturally — warm, genuine goodbye.

*"Theek ache Dada, bhalo thakben. Kono jiggasha thakle call koren, ami thakbo. Bye!"*

Then → `end_call`

---

## REAL CONVERSATION SITUATIONS (how to handle them)

**"Ekhon busy achi"**
*"Arre haa haa, thik ache, ami pore call korbo. Kono problem nei. Bhalo thakben!"*
Don't linger. Just go.

**"Koto fees?"**
*"Ufff, fees ta actually subject ar batch-er upor depend kore, mane ekakom bola mushkil phone-e. Apni ekbar branch-e ashun, counselor-er sathe kotha bolun — okhane sab clear hoe jabe."*
Never quote fees. Ever.

**"Amra already tuition dii"**
*"Ohhh, acha! Kothaye jachche?"* — Be genuinely curious. Don't immediately counter. Understand the situation first. Maybe there's a gap Sukanya can fill, maybe not.

**"Ami interested na"**
*"Setti thik ache Dada, kono problem nei! Amar number thake, jodi konodin kothao lagey toh bolben. Bhalo thakben!"*
Never guilt-trip. Never push.

**Silence / awkward pause**
Fill it like a human would — a little laugh, a "mane..." and then redirect. *"Hehe, mane, dekhen..."*

**They ask about you**
Answer naturally! You work there, you like the work, you've seen kids improve. Be specific and real, not rehearsed.

---

## SUKANYA CLASSES — WHAT YOU KNOW (use only when it fits)

- **Batches:** Max 10 students. So teachers actually notice each kid.
- **Learning style:** Audio-visual tools, not just books and blackboards.
- **Labs:** Real Physics, Chemistry, Biology labs. Kids do actual experiments.
- **Safety:** CCTV cameras. Pick-and-drop transport available.
- **Timings:** 4 PM to 9 PM
- **Boards/Classes:** Class 1–12, CBSE and ICSE

**Branches:**
1. **Phuljhore:** 1st Floor, Keshob Kunj Apartment, Sarat Pally, Nehru Road, Durgapur
2. **Benachity:** Jalkhabar Goli, Near DMC Parking, Benachity, Durgapur
3. **Raniganj:** Punjabi More, Near Royal Care Hospital, Raniganj

**Contact:**
- 8637583173 / 9002005526
- sukanyaclasses.com
- facebook.com/sukanyaclasses

---

## HARD RULES (internalize these, don't quote them)

1. **One question at a time.** Always. No exceptions.
2. **Never assume a child exists.** Ask.
3. **Never quote fees.** Direct to branch.
4. **Listen more than you talk.** Especially when a parent opens up.
5. **No corporate words.** Not "comprehensive," not "holistic," not "pedagogy." Ever.
6. **Don't info-dump.** A parent doesn't need to know everything. They need to feel understood.
7. **A "no" is fine.** End warmly. Leave the door open. Move on.

---

## THE FEEL TEST

Before every response, ask yourself: *Would a real 24-year-old woman from Durgapur actually say this on the phone?*

If it sounds like an ad, rewrite it.
If it sounds like a robot, rewrite it.
If it sounds like something you'd say to your neighbor's mom, you're close.


# ## 5. Capabilities & Tools
# * **WhatsApp:** If the user wants details, addresses, or timings, call `send_whatsapp_message`. Tell them naturally: "Ami WhatsApp-e sob details pathiye dichhi, ekbar dekhe neben."
# * **Ending the Call:** When the conversation is naturally over or the user wants to hang up, say a warm goodbye (e.g., "Theek ache dada, bhalo thakben, bye!") and THEN call `end_call`.


"""


async def run_bot(
    transport: BaseTransport,
    handle_sigint: bool,
    phone_number: str = None,
    call_id: str = None,
    vobiz_call_id: str = None,
    serializer: VobizFrameSerializer = None,
    agent_id: str = None,
):
    agent_config = get_agent_config(agent_id)
    logger.info(f"[AGENT] Starting agent '{agent_config.id}' for call_id={call_id}")

    bg_tasks = set()
    state = {"whatsapp_sent_at": 0, "terminating": False, "pending_termination": False}
    call_state = {
        "connected_at": None,
        "transcript": [],
        "recording_files": {},
    }

    # ── Native Recording ─────────────────────────────────────────────────────
    # Records inside the Pipecat pipeline at full 16kHz quality.
    # Stereo: user audio on the left channel, bot TTS on the right channel.
    audiobuffer = AudioBufferProcessor(
        num_channels=2,  # stereo: user=L, bot=R
        enable_turn_audio=True,  # also emit per-turn clips via on_*_turn_audio_data
    )
    # ────────────────────────────────────────────────────────────────────────

    function_declarations = []
    if "send_whatsapp_message" in agent_config.tools:
        function_declarations.append(
            {
                "name": "send_whatsapp_message",
                "description": "Sends requested details via WhatsApp. Use its 'custom_message' field to write the response in natural language.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "custom_message": {
                            "type": "STRING",
                            "description": "The natural language message content based on user's request.",
                        }
                    },
                    "required": ["custom_message"],
                },
            }
        )
    if "search_bcrec_course_details" in agent_config.tools:
        function_declarations.append(
            {
                "name": "search_bcrec_course_details",
                "description": "Searches detailed BCREC B.Tech course context using hybrid retrieval and reranking. Use for detailed stream/course questions about labs, careers, intake, accreditation, placements, research, HOD, facilities, or comparisons.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "query": {
                            "type": "STRING",
                            "description": "Focused query containing the stream/course and detail needed, e.g. 'CSE AI ML labs and career pathways' or 'Electrical Engineering NBA intake placements'.",
                        }
                    },
                    "required": ["query"],
                },
            }
        )
    if "end_call" in agent_config.tools:
        function_declarations.append(
            {
                "name": "end_call",
                "description": "IMMEDIATELY terminates the call and hangs up. Use when user says 'Rakho', 'Rakhchi', 'Goodbye', 'Bye', or finishes conversation.",
                "parameters": {"type": "OBJECT", "properties": {}},
            }
        )

    tools_def = [{"function_declarations": function_declarations}]

    # Gemini Multimodal Live Service correctly configured
    llm = GeminiLiveLLMService(
        api_key=os.getenv("GOOGLE_API_KEY"),
        tools=tools_def,
        settings=GeminiLiveLLMService.Settings(
            model="models/gemini-3.1-flash-live-preview",
            voice=agent_config.voice,
            system_instruction=agent_config.system_prompt,
        ),
    )

    async def _do_send_whatsapp(ph_num, text_content):
        url = "https://wasenderapi.com/api/send-message"
        headers = {
            "Authorization": "Bearer a2446e2df73638ef91898f7a9f8a8e19da8b76f2a31517df6e0f4a7cfd8dd14a",
            "Content-Type": "application/json",
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
        custom_message = args.get(
            "custom_message", "Amader institute somporke daitails pathiye dilam."
        )

        logger.info(f"📤 WHATSAPP TRIGGERED: {custom_message}")

        if not phone_number:
            logger.error("No phone number available.")
            await params.result_callback({"error": "No phone number available."})
            return

        full_text = f"{custom_message}\n\n{agent_config.whatsapp_standard_info}".strip()

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
        await params.result_callback(
            {"status": "success", "message": "WhatsApp message sent successfully."}
        )

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
        if (
            not target_id
            and serializer
            and hasattr(serializer, "call_id")
            and serializer.call_id
        ):
            target_id = serializer.call_id

        if not target_id:
            logger.warning("[REST HANGUP] No target ID found for hangup.")
            return

        logger.info(f"☎️ Attempting Vobiz REST API hangup fallback for {target_id}")
        url = f"https://api.vobiz.ai/api/v1/Account/{auth_id}/Call/{target_id}/"
        headers = {
            "X-Auth-ID": auth_id,
            "X-Auth-Token": auth_token,
            "Content-Type": "application/json",
        }
        try:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                async with session.delete(url, headers=headers) as resp:
                    res_body = await resp.text()
                    logger.info(
                        f"Vobiz REST hangup status: {resp.status}, Body: {res_body}"
                    )
        except Exception as e:
            logger.error(f"Vobiz REST hangup failed: {e}")

    async def end_call(params: FunctionCallParams):
        if state["terminating"] or state["pending_termination"]:
            logger.info(
                "[END CALL] Termination already in progress, ignoring duplicate call."
            )
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
                logger.warning(
                    "[END CALL] Safety fallback triggered: forcing hangup now."
                )
                state["terminating"] = True
                await _vobiz_rest_hangup()
                await params.llm.push_frame(EndTaskFrame(), FrameDirection.UPSTREAM)

        asyncio.create_task(_safety_termination_fallback())

    if "send_whatsapp_message" in agent_config.tools:
        llm.register_function("send_whatsapp_message", send_whatsapp_message)

    async def search_bcrec_course_details_tool(params: FunctionCallParams):
        args = params.arguments if hasattr(params, "arguments") else {}
        query = args.get("query", "")
        logger.info(f"[BCREC RAG] Search query: {query}")
        result = search_bcrec_course_details(query=query, top_k=5)
        await params.result_callback({"status": "success", "context": result})

    if "search_bcrec_course_details" in agent_config.tools:
        llm.register_function(
            "search_bcrec_course_details", search_bcrec_course_details_tool
        )
    if "end_call" in agent_config.tools:
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
            wf.setsampwidth(2)  # 16-bit PCM
            wf.setframerate(sample_rate)  # 16000 Hz (Gemini Live)
            wf.writeframes(audio)
        logger.info(
            f"[RECORDING] ✅ Stereo WAV saved → {fname} "
            f"({num_channels}ch, {sample_rate}Hz, {len(audio) // 2 // num_channels // sample_rate:.1f}s)"
        )
        call_state["recording_files"]["stereo"] = f"call_{label}_stereo.wav"

        # Upload to Supabase Storage
        if call_id:
            supabase_path = supabase_storage.upload_recording(fname, call_id)
            if supabase_path:
                call_state["recording_files"]["stereo_remote"] = supabase_path
                from call_store import update_call

                update_call(call_id, recording_files=call_state["recording_files"])

    @audiobuffer.event_handler("on_track_audio_data")
    async def on_track_audio_data(
        buffer, user_audio, bot_audio, sample_rate, num_channels
    ):
        """Saves separate user/bot mono WAVs. Triggers transcription AFTER files are on disk."""
        os.makedirs("recordings", exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        label = call_id or ts
        for track_name, track_audio in (("user", user_audio), ("bot", bot_audio)):
            fname = f"recordings/call_{label}_{track_name}.wav"
            with wave.open(fname, "wb") as wf:
                wf.setnchannels(1)  # mono per track
                wf.setsampwidth(2)  # 16-bit PCM
                wf.setframerate(sample_rate)  # 16000 Hz
                wf.writeframes(track_audio)
            logger.info(f"[RECORDING] ✅ {track_name.upper()} mono WAV saved → {fname}")
            call_state["recording_files"][track_name] = f"call_{label}_{track_name}.wav"

            # Upload to Supabase Storage
            if call_id:
                supabase_path = supabase_storage.upload_recording(fname, call_id)
                if supabase_path:
                    call_state["recording_files"][f"{track_name}_remote"] = (
                        supabase_path
                    )

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
            logger.info(
                f"[RECORDING] 🎤 Triggering post-call transcription for {call_id}"
            )
            asyncio.create_task(transcriber.transcribe_and_store(call_id))

    # ────────────────────────────────────────────────────────────────────────

    # PROPER INITIALIZATION (Matching Sample)
    context = LLMContext(
        messages=[{"role": "system", "content": agent_config.first_turn_instruction}]
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
        logger.info(
            f"Starting outbound call conversation (Gemini Live). Client: {client}"
        )
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
    async def on_assistant_turn_stopped(
        aggregator, message: AssistantTurnStoppedMessage
    ):
        if state["pending_termination"] and not state["terminating"]:
            logger.info(
                "[END CALL] Bot finished speaking - initiating final disconnect sequence"
            )
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
                cm.on_call_ended(
                    call_id, duration_seconds=duration, end_reason="hangup"
                )
                # NOTE: Transcription is triggered from on_track_audio_data (after WAV files
                # are confirmed written to disk) — NOT here, to avoid a race condition.
        except Exception as e:
            logger.warning(f"Could not notify CallManager of disconnect: {e}")

        await task.cancel()

    runner = PipelineRunner(handle_sigint=handle_sigint)
    await runner.run(task)


async def bot(
    runner_args: RunnerArguments,
    call_id: str = None,
    vobiz_call_id: str = None,
    stream_id: str = None,
    body_data: dict = None,
    agent_id: str = None,
):
    """Main bot entry point compatible with Pipecat Cloud."""

    phone_number = body_data.get("phone_number") if body_data else None
    selected_agent_id = agent_id or (body_data.get("agent_id") if body_data else None)

    if not call_id:
        transport_type, call_data = await parse_telephony_websocket(
            runner_args.websocket
        )
        logger.info(f"Transport type: {transport_type}, Call data: {call_data}")
        stream_id = call_data.get("stream_id", "")
        # Standardize: check cm_id (query param) then call_id (body) then call_uuid
        call_id = (
            call_data.get("cm_id")
            or call_data.get("call_id")
            or call_data.get("call_uuid", "")
        )
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
            auto_hang_up=True,
        ),
    )

    transport = FastAPIWebsocketTransport(
        websocket=runner_args.websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            serializer=serializer,
            vad_analyzer=SileroVADAnalyzer(
                params=VADParams(stop_secs=0.3, min_silence_duration_ms=100)
            ),
        ),
    )

    handle_sigint = runner_args.handle_sigint
    await run_bot(
        transport,
        handle_sigint,
        phone_number,
        call_id=call_id,
        vobiz_call_id=vobiz_call_id,
        serializer=serializer,
        agent_id=selected_agent_id,
    )
