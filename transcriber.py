"""transcriber.py

Post-call transcription using Gemini 1.5 Flash.
Sends the stereo WAV recording and gets back a diarized transcript
with speaker labels (user vs bot) in JSON format.
"""

import asyncio
import base64
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp
from loguru import logger

RECORDINGS_DIR = os.path.join(os.path.dirname(__file__), "recordings")

TRANSCRIPTION_PROMPT = """You are a transcription assistant. You will receive an audio recording of a phone call between a bot (AI agent) and a user (human caller).

The audio is stereo: the USER is on the left channel and the BOT is on the right channel. Use this information to accurately attribute each utterance to the correct speaker.

Transcribe the ENTIRE conversation, with accurate diarization. Return ONLY a valid JSON array with no other text. Each element should be an object with these fields:
- "role": either "user" or "bot"
- "text": the transcribed text for that utterance (in the original language spoken - could be Bengali, Hindi, or English)

Example output format:
[
  {"role": "bot", "text": "Hello, ami Sukanya Classes theke bolchhi."},
  {"role": "user", "text": "Haan bolun."},
  {"role": "bot", "text": "Apnar barite ki school-going baccha ache?"}
]

Important rules:
1. Transcribe in the ORIGINAL language spoken (Bengali, Hindi, English, or mixed)
2. Include ALL utterances, even short ones like "hmm", "haan", "ok"
3. Keep the chronological order of the conversation
4. If you can't understand a part, write "[inaudible]"
5. Do NOT add any text outside the JSON array. No markdown, no explanation.
"""


async def transcribe_call(
    call_id: str,
    recording_file: str = None,
) -> List[Dict[str, str]]:
    """
    Transcribe a call recording using Gemini 1.5 Flash with retry logic.

    Args:
        call_id: The call ID to look up the recording
        recording_file: Optional specific recording file path

    Returns:
        List of transcript messages [{"role": "user"|"bot", "text": "..."}]
    """
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        logger.error("[TRANSCRIBER] GOOGLE_API_KEY not set")
        return []

    # Find the stereo recording file
    if recording_file:
        audio_path = os.path.join(RECORDINGS_DIR, recording_file)
    else:
        # Build list of candidate IDs to try: internal call_id first, then vobiz_call_uuid
        candidate_ids = [call_id]
        try:
            import call_store as _cs
            call_record = _cs.get_call(call_id)
            if call_record:
                vobiz_uuid = call_record.get("vobiz_call_uuid", "")
                if vobiz_uuid and vobiz_uuid != call_id:
                    candidate_ids.append(vobiz_uuid)
                    logger.info(f"[TRANSCRIBER] Will also try Vobiz UUID: {vobiz_uuid}")
        except Exception as _e:
            logger.warning(f"[TRANSCRIBER] Could not look up call record for fallback UUID: {_e}")

        audio_path = None
        for cid in candidate_ids:
            for pattern in [
                f"call_{cid}_stereo.wav",
                f"call_{cid}_user.wav",  # Fallback to user-only
            ]:
                candidate = os.path.join(RECORDINGS_DIR, pattern)
                if os.path.exists(candidate):
                    audio_path = candidate
                    if cid != call_id:
                        logger.info(f"[TRANSCRIBER] Found recording via Vobiz UUID fallback: {pattern}")
                    break
            if audio_path:
                break

        if not audio_path:
            logger.warning(f"[TRANSCRIBER] No recording found for call {call_id} (tried IDs: {candidate_ids})")
            return []

    if not os.path.exists(audio_path):
        logger.warning(f"[TRANSCRIBER] Recording file not found: {audio_path}")
        return []

    file_size = os.path.getsize(audio_path)
    logger.info(f"[TRANSCRIBER] Transcribing {audio_path} ({file_size / 1024:.0f} KB)")

    # Read and base64 encode the audio file
    with open(audio_path, "rb") as f:
        audio_data = base64.standard_b64encode(f.read()).decode("utf-8")

    # Determine MIME type
    mime_type = "audio/wav"
    if audio_path.endswith(".mp3"):
        mime_type = "audio/mp3"

    # Call Gemini API — using gemini-3.1-flash-lite-preview
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite-preview:generateContent?key={api_key}"

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "inline_data": {
                            "mime_type": mime_type,
                            "data": audio_data,
                        }
                    },
                    {
                        "text": TRANSCRIPTION_PROMPT,
                    },
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.1,
            "responseMimeType": "application/json",
        },
    }

    max_retries = 3
    for attempt in range(max_retries):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=300),
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        break
                    elif response.status == 503 and attempt < max_retries - 1:
                        wait_time = (2 ** attempt) + 2
                        logger.warning(f"[TRANSCRIBER] Gemini 503 (Busy). Retrying in {wait_time}s... (Attempt {attempt+1}/{max_retries})")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        error_text = await response.text()
                        logger.error(f"[TRANSCRIBER] Gemini API error ({response.status}): {error_text}")
                        return []
        except asyncio.TimeoutError:
            if attempt < max_retries - 1:
                logger.warning(f"[TRANSCRIBER] Timeout. Retrying... (Attempt {attempt+1}/{max_retries})")
                continue
            logger.error(f"[TRANSCRIBER] Final timeout transcribing call {call_id}")
            return []
        except Exception as e:
            logger.error(f"[TRANSCRIBER] Error on attempt {attempt+1}: {e}")
            if attempt < max_retries - 1: continue
            return []

    # Parse the response
    candidates = result.get("candidates", [])
    if not candidates:
        logger.warning("[TRANSCRIBER] No candidates in Gemini response")
        return []

    content = candidates[0].get("content", {})
    parts = content.get("parts", [])
    if not parts:
        logger.warning("[TRANSCRIBER] No parts in Gemini response")
        return []

    raw_text = parts[0].get("text", "").strip()

    # Parse JSON from the response
    transcript = _parse_transcript_json(raw_text)

    if transcript:
        logger.info(f"[TRANSCRIBER] ✅ Got {len(transcript)} transcript entries for call {call_id}")
    else:
        logger.warning(f"[TRANSCRIBER] Failed to parse transcript for call {call_id}")

    return transcript


def _parse_transcript_json(raw_text: str) -> List[Dict[str, str]]:
    """Parse the transcript JSON from Gemini's response, handling edge cases and truncation."""
    def try_parse(text):
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return [
                    {"role": str(item.get("role", "bot")).lower(), "text": str(item.get("text", ""))}
                    for item in data
                    if isinstance(item, dict) and item.get("text")
                ]
        except json.JSONDecodeError:
            return None
        return None

    # 1. Try direct JSON parse
    res = try_parse(raw_text)
    if res: return res

    # 2. Try cleaning markdown and then parse
    clean_text = raw_text.strip()
    if clean_text.startswith("```"):
        import re
        json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", clean_text, re.DOTALL)
        if json_match:
            res = try_parse(json_match.group(1))
            if res: return res

    # 3. Try finding the first '[' and last ']'
    import re
    bracket_match = re.search(r"\[.*\]", raw_text, re.DOTALL)
    if bracket_match:
        res = try_parse(bracket_match.group(0))
        if res: return res

    # 4. Handle TRUNCATED JSON: If it starts with '[' but doesn't end with ']'
    if clean_text.startswith("[") and not clean_text.endswith("]"):
        logger.info("[TRANSCRIBER] Attempting to repair truncated JSON...")
        # Try to find the last complete object and close the array
        last_obj_end = clean_text.rfind("}")
        if last_obj_end != -1:
            repaired = clean_text[:last_obj_end+1] + "]"
            res = try_parse(repaired)
            if res: return res

    logger.warning(f"[TRANSCRIBER] Could not parse JSON from response: {raw_text[:200]}")
    return []


async def transcribe_and_store(call_id: str, recording_file: str = None):
    """
    Transcribe a call and store the result in CallManager.
    This is meant to be called as a background task after a call ends.
    """
    try:
        # Small delay to ensure file write buffers are flushed
        await asyncio.sleep(2)
        
        transcript = await transcribe_call(call_id, recording_file)
        if transcript:
            from call_manager import get_call_manager
            cm = get_call_manager()
            cm.on_transcript_update(call_id, transcript)
            logger.info(f"[TRANSCRIBER] ✅ Transcript stored for call {call_id} ({len(transcript)} messages)")
        else:
            logger.warning(f"[TRANSCRIBER] No transcript generated for call {call_id}")
    except Exception as e:
        logger.error(f"[TRANSCRIBER] Error in transcribe_and_store for {call_id}: {e}")
