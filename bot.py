#
# Copyright (c) 2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

import datetime
import os
import wave

from dotenv import load_dotenv
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.processors.audio.audio_buffer_processor import AudioBufferProcessor
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.frames.frames import LLMContextFrame, TextFrame
from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import LocalSmartTurnAnalyzerV3
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.turns.user_stop import TurnAnalyzerUserTurnStopStrategy
from pipecat.turns.user_turn_strategies import UserTurnStrategies
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import parse_telephony_websocket
from pipecat.serializers.vobiz import VobizFrameSerializer
from pipecat.services.openai.llm import OpenAILLMService
# from pipecat.services.deepgram.stt import DeepgramSTTService
# from pipecat.services.deepgram.tts import DeepgramTTSService
from pipecat.services.google.llm import GoogleLLMService
from pipecat.services.sarvam.stt import SarvamSTTService
from pipecat.services.sarvam.tts import SarvamTTSService
from pipecat.transports.base_transport import BaseTransport
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)

load_dotenv(override=True)
import time

# Initialize Smart Turn Analyzer once at startup to avoid per-call loading latency (15-20s)
try:
    from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import LocalSmartTurnAnalyzerV3
    smart_turn_analyzer = LocalSmartTurnAnalyzerV3()
except ImportError:
    smart_turn_analyzer = None


async def run_bot(transport: BaseTransport, handle_sigint: bool, phone_number: str = None, call_id: str = None):
    # ── NativeRecording ─────────────────────────────────────────────────────
    # Records inside the Pipecat pipeline at full 24kHz quality.
    # Stereo: user audio on the left channel, bot TTS on the right channel.
    audiobuffer = AudioBufferProcessor(
        num_channels=2,         # stereo: user=L, bot=R
        enable_turn_audio=True, # also emit per-turn clips via on_*_turn_audio_data
    )
    # ────────────────────────────────────────────────────────────────────────
    llm = OpenAILLMService(
        api_key=os.getenv("OPENAI_API_KEY"),
        model="gpt-4o-mini"
    )

    stt = SarvamSTTService(
        api_key=os.getenv("SARVAM_API_KEY"),
        sample_rate=16000,
    )

    tts = SarvamTTSService(
        api_key=os.getenv("SARVAM_API_KEY"),
        settings=SarvamTTSService.Settings(voice="aditya", model="bulbul:v3"),
        sample_rate=24000,
    )

    messages = [
        {
            "role": "system",
            "content": (
                "You are a helpful assistant. "
                "Keep your responses very brief and conversational, as they will be spoken. "
                "Start with a friendly one-sentence greeting when you first connect."
            ),
        },
    ]

    context = LLMContext(messages)
    context_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            user_turn_strategies=UserTurnStrategies(
                stop=[
                    TurnAnalyzerUserTurnStopStrategy(
                        turn_analyzer=smart_turn_analyzer
                    )
                ]
            )
        )
    )

    pipeline = Pipeline(
        [
            transport.input(),           # Websocket input from client
            stt,                         # Speech-To-Text
            context_aggregator.user(),
            llm,                         # LLM
            tts,                         # Text-To-Speech
            transport.output(),          # Websocket output to client
            audiobuffer,                 # ← Native recording (after output so both tracks captured)
            context_aggregator.assistant(),
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=16000,
            audio_out_sample_rate=24000,
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
    )

    # Register transcript logging on the user aggregator (where final transcribed text ends up)
    @context_aggregator.user().event_handler("on_user_turn_stopped")
    async def on_user_transcript(aggregator, turn_data, *args):
        # In Pipecat 1.0.0, the last user message is in turn_data or context
        pass

    @llm.event_handler("on_response_started")
    async def on_response_started(llm):
        logger.info("LLM Response started")

    @tts.event_handler("on_audio_started")
    async def on_audio_started(tts):
        logger.info("TTS Audio started")

    # Store temporary session state (timing, flags) locally instead of on the task object
    # to avoid "PipelineTask object has no attribute 'set_metadata'" errors.
    session_state = {"turn_start_time": time.time()}

    # Turn tracking on the user aggregator (more reliable than transport VAD events)
    @context_aggregator.user().event_handler("on_user_turn_started")
    async def on_user_turn_started(aggregator, *args):
        logger.info(f"User started speaking (Turn Started)")
        session_state["turn_start_time"] = time.time()

    @context_aggregator.user().event_handler("on_user_turn_stopped")
    async def on_user_turn_stopped(aggregator, *args):
        duration = time.time() - session_state.get("turn_start_time", time.time())
        logger.info(f"User finished speaking (Turn Stopped, Duration: {duration:.2f}s)")

    # ── Recording event handlers ─────────────────────────────────────────────
    @audiobuffer.event_handler("on_audio_data")
    async def on_audio_data(buffer, audio, sample_rate, num_channels):
        """Fires at end of call (or when buffer_size threshold is hit).
        Saves a single stereo WAV: user=left channel, bot=right channel."""
        os.makedirs("recordings", exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        label = call_id or ts
        fname = f"recordings/call_{label}_stereo.wav"
        with wave.open(fname, "wb") as wf:
            wf.setnchannels(num_channels)  # 2
            wf.setsampwidth(2)             # 16-bit PCM
            wf.setframerate(sample_rate)   # 24000 Hz
            wf.writeframes(audio)
        logger.info(f"[RECORDING] ✅ Stereo WAV saved → {fname} "
                    f"({num_channels}ch, {sample_rate}Hz, {len(audio)//2//num_channels//sample_rate:.1f}s)")

    @audiobuffer.event_handler("on_track_audio_data")
    async def on_track_audio_data(buffer, user_audio, bot_audio, sample_rate, num_channels):
        """Also saves separate user/bot mono WAVs alongside the stereo file."""
        os.makedirs("recordings", exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        label = call_id or ts
        for track_name, track_audio in (("user", user_audio), ("bot", bot_audio)):
            fname = f"recordings/call_{label}_{track_name}.wav"
            with wave.open(fname, "wb") as wf:
                wf.setnchannels(1)              # mono per track
                wf.setsampwidth(2)              # 16-bit PCM
                wf.setframerate(sample_rate)    # 24000 Hz
                wf.writeframes(track_audio)
            logger.info(f"[RECORDING] ✅ {track_name.upper()} mono WAV saved → {fname}")
    # ────────────────────────────────────────────────────────────────────────

    async def on_client_connected(transport, client):
        logger.info(f"Starting outbound call conversation. Client: {client}")
        # Start native Pipecat recording
        await audiobuffer.start_recording()
        logger.info("[RECORDING] 🎙️ Native recording started")

        # TRIGGER INSTANT GREETING
        # Instead of waiting for the LLM to generate a response, we provide a pre-defined greeting.
        # This eliminates the initial 7-10s delay.
        greeting = "Hello! I am your AI assistant. How can I help you today?"
        
        # 1. Update the LLM context manually so it knows it has greeted the user
        context.add_message({"role": "assistant", "content": greeting})
        
        # 2. Queue the text frame directly to the pipeline.
        # This will be processed by TTS and sent to the transport immediately.
        await task.queue_frame(TextFrame(greeting))

    # Register transport-level handlers
    transport.add_event_handler("on_client_connected", on_client_connected)
    
    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Outbound call ended")
        # Stop recording — this flushes buffered audio and fires on_audio_data / on_track_audio_data
        await audiobuffer.stop_recording()
        logger.info("[RECORDING] 🎙️ Native recording stopped")
        await task.cancel()

    runner = PipelineRunner(handle_sigint=handle_sigint)

    await runner.run(task)


async def bot(runner_args: RunnerArguments, call_id: str = None, stream_id: str = None):
    """Main bot entry point compatible with Pipecat Cloud."""

    # If call_id/stream_id not provided, try to parse from WebSocket (legacy behavior)
    if not call_id:
        # Parse the telephony WebSocket to extract stream_id and call_id
        # NOTE: This can be problematic if it consumes the handshake message!
        transport_type, call_data = await parse_telephony_websocket(runner_args.websocket)
        logger.info(f"Transport type: {transport_type}, Call data: {call_data}")
        stream_id = call_data.get("stream_id", "")
        call_id = call_data.get("call_id", "")
    elif not stream_id:
        # If we have call_id (from query params) but no stream_id, 
        # we skip the parsing to avoid consuming handshake messages and just use call_id as stream_id.
        # Vobiz integration works fine with this for initial handshake.
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
            encoding="audio/x-mulaw",  # Standard telephony encoding
            sample_rate=None,  # Uses pipeline default
            auto_hang_up=True  # Automatically hangs up on EndFrame
        )
    )

    transport = FastAPIWebsocketTransport(
        websocket=runner_args.websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,  # CRITICAL: Must be False for telephony
            serializer=serializer,  
            vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=0.25)), # Balanced for natural flow
        ),
    )

    handle_sigint = runner_args.handle_sigint

    await run_bot(transport, handle_sigint, phone_number=None, call_id=call_id)
