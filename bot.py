#
# Copyright (c) 2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

import os

from dotenv import load_dotenv
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.frames.frames import LLMContextFrame, TextFrame
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import parse_telephony_websocket
from pipecat.serializers.vobiz import VobizFrameSerializer
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.deepgram.tts import DeepgramTTSService
from pipecat.transports.base_transport import BaseTransport
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)

load_dotenv(override=True)


async def run_bot(transport: BaseTransport, handle_sigint: bool):
    llm = OpenAILLMService(
        api_key=os.getenv("OPENAI_API_KEY"),
        model="gpt-4o-mini"
    )

    stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY"))

    tts = DeepgramTTSService(
        api_key=os.getenv("DEEPGRAM_API_KEY"),
        voice="aura-asteria-en",
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
    context_aggregator = LLMContextAggregatorPair(context)

    pipeline = Pipeline(
        [
            transport.input(),  # Websocket input from client
            stt,  # Speech-To-Text
            context_aggregator.user(),
            llm,  # LLM
            tts,  # Text-To-Speech
            transport.output(),  # Websocket output to client
            context_aggregator.assistant(),
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=8000,   # Vobiz MULAW input (8kHz telephony)
            audio_out_sample_rate=8000,  # Deepgram MULAW output (8kHz telephony)
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
    )

    async def on_transcription(stt, text):
        logger.info(f"STT Transcription: {text}")

    async def on_response_started(llm):
        logger.info("LLM Response started")

    async def on_audio_started(tts):
        logger.info("TTS Audio started")

    async def on_client_connected(transport, client):
        logger.info(f"Starting outbound call conversation. Client: {client}")
        # TRIGGER INSTANT GREETING
        # Instead of waiting for the LLM to generate a response, we provide a pre-defined greeting.
        # This eliminates the initial 7-10s delay.
        greeting = "Hello! I am your AI assistant. How can I help you today?"
        
        # 1. Update the LLM context manually so it knows it has greeted the user
        context.add_message({"role": "assistant", "content": greeting})
        
        # 2. Queue the text frame directly to the pipeline.
        # This will be processed by TTS and sent to the transport immediately.
        await task.queue_frame(TextFrame(greeting))

    async def on_vad_started(transport):
        logger.info("VAD Started - User is speaking")

    async def on_vad_stopped(transport):
        logger.info("VAD Stopped - User finished speaking")

    # Register handlers using add_event_handler (more reliable in Pipecat 1.0.0)
    stt.add_event_handler("on_transcription", on_transcription)
    llm.add_event_handler("on_response_started", on_response_started)
    tts.add_event_handler("on_audio_started", on_audio_started)
    transport.add_event_handler("on_client_connected", on_client_connected)
    transport.add_event_handler("on_vad_started", on_vad_started)
    transport.add_event_handler("on_vad_stopped", on_vad_stopped)
    
    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Outbound call ended")
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
            vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=0.5)), # Back to 0.5 for stability
        ),
    )

    handle_sigint = runner_args.handle_sigint

    await run_bot(transport, handle_sigint)
