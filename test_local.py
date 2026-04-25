import asyncio
import os
import sys
import inspect
from loguru import logger
from dotenv import load_dotenv

from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineTask, PipelineParams
from pipecat.services.google.gemini_live.llm import GeminiLiveLLMService
from pipecat.transports.local.audio import LocalAudioTransport, LocalAudioTransportParams
from pipecat.frames.frames import InputTextRawFrame, LLMContextFrame
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams

import pyaudio
load_dotenv()

# The globally managed background tasks to avoid GC destruction mid-execution
bg_tasks = set()

# Same exact prompt as your bot_live.py
DEFAULT_AGENT_PROMPT = """# System Instruction: Persona & Guidelines

## 1. Identity & Role
* **Name & Role:** Sudipta, a 20-something, warm, energetic educational counselor calling locally on behalf of **Sukanya Classes**.
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

## 4. Call Flow & Sales Strategy
Navigate fluidly; do not sound rehearsed. Follow this sequence exactly:
1. **Warm Opener (Turn 1):** You only say short greeting (like "Hello") and wait for them to respond. (Already handled by your first turn rule).
2. **The Introduction & Elevator Pitch (Turn 2):** When they reply to your greeting, immediately introduce yourself, state where you are calling from, and give a brief but comprehensive overview of Sukanya Classes. Mention exactly what we are (a coaching institute for CBSE/ICSE classes 1-12 with max 10 students per batch) and what our USPs are (practical labs, expert separate teachers, audio-visual methods). Help the parent fully understand WHY you are calling and what the institute is.
3. **Discovery & Needs Assessment:** ONLY AFTER you have given the overview, start inquiring. Ask if they have school-going kids at home, their class, board, and any educational concerns.
4. **Tailored Pitch (Value-Match):** Discuss ONLY the specific features that solve the problems they just mentioned (e.g. homework pressure, science fear).
5. **Call to Action/Closing:** If they show interest, ask permission to send details via WhatsApp and invite them to visit an offline branch. End naturally without rushing.
6. **Tool Execution Rule:** If you ever verbally promise to send a WhatsApp message or details to the user, you MUST simultaneously call the `send_whatsapp_message` function. Do NOT say you are sending it without executing the tool.

## 5. Handling Deviations
* **Adapt & Pivot:** If they interrupt, stop and listen. If they sound busy, offer a callback.
* **The "3-Turn" Limit & Off-Topic:** If they vent or drift to unrelated topics for 3 turns, gently pivot back: "Haa, thiki... kintu bachhader porashona niye..."
* **Information Locking:** Do NOT discuss pricing, discounts, or specific scholarships. Say: "Actually, it depends on the subjects; amader counselor branch-e bhalobhabe bolte parbe."

## 6. Knowledge Base

### Core Offerings
* **Boards:** CBSE & ICSE (Class 1-12).
* **Batch Size:** Strict max of 10 students for personalized care.
* **Methodology:** Separate expert teachers per subject, AI-driven audio-visual courses, full study materials. Motto: "Teach the way students learn."
* **Facilities:** Dedicated Practical Labs, Computer Lab, Pick-and-drop Transport.
* **Timings:** 10:30 AM - 9 PM.
* **Contact:** 8637583173, 9002005526. (Note: You cannot receive inbound calls. Refer callbacks to these numbers).
* **Video Link:** https://www.facebook.com/story.php?story_fbid=1631223218223650&id=100040079637254&rdid=keoUCWrYAB8yxMZu#

### Branch Locations (Suggest based on proximity)
1. **Phuljhore:** 1st Fl, Keshob Kunj Apt, Sarat Pally, Nehru Rd.
2. **Benachity:** Jalkhabar Goli, near DMC Parking.
3. **Raniganj:** Punjabi More, near Royal Care Hospital.

### Dynamic Value Pillars (Tailor to the Child)
* **Primary (Class 1-5):** *Pain Point:* Homework pressure. *Solution:* We take full responsibility for syllabus/homework via fun activities. Ready for April 2026 CBSE changes (AI/3rd Language).
* **Middle (Class 6-8):** *Pain Point:* Fear of complex subjects. *Solution:* Heavy hands-on practicals (e.g., microscopes, chemical reactions) to build genuine interest.  
* **Secondary (Class 9-12):** *Pain Point:* Board exam pressure. *Solution:* Strategic blueprint planning and maximizing scores based on personal strengths for massive syllabuses.

### Objection Handling
* **"We have a private tutor" ->** Validate ("That's great!"), but mention tutors lack hands-on Practical Labs and dedicated subject-expert teachers crucial for modern exams.
* **"Too far" ->** Find their location, map to the nearest branch, and highlight our dedicated Pick-and-Drop Transport.

### Standard Information (For WhatsApp)
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

async def list_audio_devices():
    p = pyaudio.PyAudio()
    info = p.get_host_api_info_by_index(0)
    num_devices = info.get('deviceCount')
    logger.info("Available Audio Devices:")
    for i in range(0, num_devices):
        device_info = p.get_device_info_by_host_api_device_index(0, i)
        logger.info(f"Device {i}: {device_info.get('name')} (Inputs: {device_info.get('maxInputChannels')})")
    p.terminate()

async def main():
    if "--list-devices" in sys.argv:
        await list_audio_devices()
        return

    input_index = None
    output_index = None
    
    if "--input-index" in sys.argv:
        idx = sys.argv.index("--input-index")
        input_index = int(sys.argv[idx + 1])
    
    if "--output-index" in sys.argv:
        idx = sys.argv.index("--output-index")
        output_index = int(sys.argv[idx + 1])

    logger.info(f"Initializing local testing Pipecat runner (Input: {input_index}, Output: {output_index})...")
    
    # We will use LocalAudioTransport allowing mic and hardware speakers!
    transport = LocalAudioTransport(
        LocalAudioTransportParams(
            audio_in_sample_rate=16000,
            audio_out_sample_rate=16000,
            audio_in_enabled=True,
            audio_out_enabled=True,
            audio_in_device_index=input_index,
            audio_out_device_index=output_index,
            vad_analyzer=SileroVADAnalyzer(
                params=VADParams(
                    stop_secs=0.2,   # Reduced from 0.5 for faster turn-taking
                    min_silence_duration_ms=100
                )
            )
        )
    )

    tools_def = [{
        "function_declarations": [{
            "name": "send_whatsapp_message",
            "description": "MUST BE CALLED IMMEDIATELY when the user agrees to receive details on WhatsApp, OR if you offer to send details on WhatsApp. Send a SHORT 1 sentence custom message addressing their specific needs (e.g. branch location). Do NOT include the boilerplate standard information, it is automatically appended.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "custom_message": {"type": "STRING"}
                },
                "required": ["custom_message"]
            }
        }]
    }]

    llm = GeminiLiveLLMService(
        api_key=os.getenv("GOOGLE_API_KEY"),
        settings=GeminiLiveLLMService.Settings(
            voice="Leda",
        ),
        system_instruction=DEFAULT_AGENT_PROMPT,
        tools=tools_def
    )

    # In local testing, you can freely replace the number.
    # Set to a default for testing purposes.
    test_phone_number = "+917044311109"

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

    async def send_whatsapp_message(custom_message: str = "", **kwargs):
        # Pipecat might pass arguments directly in kwargs, or nested inside "arguments"
        if not custom_message and "arguments" in kwargs:
            custom_message = kwargs["arguments"].get("custom_message", "Here are the details for Sukanya Classes.")
        elif not custom_message:
            custom_message = kwargs.get("custom_message", "Here are the details for Sukanya Classes.")
        
        result_callback = kwargs.get("result_callback")
        
        if not test_phone_number:
            fail_msg = "Failed to send WhatsApp because the user's phone number is unknown."
            if result_callback:
                if inspect.iscoroutinefunction(result_callback):
                    await result_callback(fail_msg)
                else:
                    result_callback(fail_msg)
            return fail_msg
        
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
        
        import asyncio
        task = asyncio.create_task(_do_send_whatsapp(test_phone_number, full_text))
        bg_tasks.add(task)
        task.add_done_callback(bg_tasks.discard)
        
        success_msg = "Message is queueing in the background. Immediately tell the parent 'Ami pathiye diyechi' (I have sent it) and end the call smoothly."
        
        logger.warning(f"LOCAL TESTING -> Generated WhatsApp payload to send to {test_phone_number}: {full_text}")
        
        if result_callback:
            if inspect.iscoroutinefunction(result_callback):
                await result_callback(success_msg)
            else:
                result_callback(success_msg)
                
        return success_msg

    llm.register_function("send_whatsapp_message", send_whatsapp_message)

    pipeline = Pipeline(
        [
            transport.input(),
            llm,
            transport.output(),
        ]
    )

    task = PipelineTask(pipeline, params=PipelineParams(allow_interruptions=True))
    
    @transport.event_handler("on_user_started_speaking")
    async def on_user_started_speaking(transport, participant):
        logger.info("VAD -> User started speaking")

    @transport.event_handler("on_user_stopped_speaking")
    async def on_user_stopped_speaking(transport, participant):
        logger.info("VAD -> User stopped speaking")

    async def start_bot_conversation():
        await asyncio.sleep(2.0)
        logger.info("Injecting start frame and context...")
        FIRST_TURN_INSTRUCTION = (
            "Start with an ultra-short greeting. Say ONLY 'Hello' or 'Hello, Namaskar'. "
            "Do not say anything else. Wait for the user to respond."
        )
        context = LLMContext(
            messages=[
                {"role": "system", "content": FIRST_TURN_INSTRUCTION}
            ]
        )
        await task.queue_frame(LLMContextFrame(context))
        await task.queue_frame(InputTextRawFrame(text="Please start the conversation based on the first turn instruction."))

    asyncio.create_task(start_bot_conversation())

    runner = PipelineRunner()

    logger.info("Speak into your microphone! Say 'CTRL+C' in terminal to stop.")
    await runner.run(task)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Local CLI Test Interrupted.")
