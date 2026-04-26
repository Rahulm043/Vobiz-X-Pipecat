

"""server.py

Webhook server to handle outbound call requests, initiate calls via Vobiz API,
and handle subsequent WebSocket connections for Media Streams.
"""

import base64
import json
import os
import urllib.parse
from contextlib import asynccontextmanager
from datetime import datetime

import aiohttp
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pyngrok import ngrok
load_dotenv(override=True)

# Bot selection logic
use_live = os.getenv("USE_LIVE_BOT", "false").lower() == "true"
print(f"[DEBUG] USE_LIVE_BOT env: '{os.getenv('USE_LIVE_BOT')}', Effective: {use_live}")

if use_live:
    import bot_live as bot_module
    print("[INFO] Using Gemini 3.1 Flash Live bot (bot_live.py)")
else:
    import bot as bot_module
    print("[INFO] Using cascaded STT-LLM-TTS bot (bot.py)")

bot = bot_module.bot
run_bot = bot_module.run_bot


# ----------------- ACTIVE CALLS TRACKING ----------------- #

# Dictionary to store active call information
# In production, use Redis or a database instead of in-memory dict
active_calls = {}


# ----------------- HELPERS ----------------- #


async def make_vobiz_call(
    session: aiohttp.ClientSession, to_number: str, from_number: str, answer_url: str
):
    """Make an outbound call using Vobiz's REST API."""
    print("\n[DEBUG] ========== VOBIZ API CALL START ==========")

    auth_id = os.getenv("VOBIZ_AUTH_ID")
    auth_token = os.getenv("VOBIZ_AUTH_TOKEN")

    if not auth_id:
        raise ValueError("Missing Vobiz Auth ID (VOBIZ_AUTH_ID)")

    if not auth_token:
        raise ValueError("Missing Vobiz Auth Token (VOBIZ_AUTH_TOKEN)")

    print(f"[DEBUG] Auth ID: {auth_id}")
    print(f"[DEBUG] Auth Token: {auth_token[:10]}...{auth_token[-10:]}")  # Partial token for security

    headers = {
        "Content-Type": "application/json",
        "X-Auth-ID": auth_id,
        "X-Auth-Token": auth_token,
    }

    data = {
        "to": to_number,
        "from": from_number,
        "answer_url": answer_url,
        "answer_method": "POST",
    }

    url = f"https://api.vobiz.ai/api/v1/Account/{auth_id}/Call/"

    print(f"[DEBUG] API URL: {url}")
    print(f"[DEBUG] Request Headers: {headers}")
    print(f"[DEBUG] Request Body: {json.dumps(data, indent=2)}")
    print(f"[DEBUG] Answer URL being sent: {answer_url}")

    try:
        async with session.post(url, headers=headers, json=data) as response:
            response_text = await response.text()
            print(f"[DEBUG] Response Status: {response.status}")
            print(f"[DEBUG] Response Body: {response_text}")

            if response.status != 201:
                print(f"[ERROR] Vobiz API call failed!")
                print(f"[ERROR] Status: {response.status}")
                print(f"[ERROR] Response: {response_text}")
                raise Exception(f"Vobiz API error ({response.status}): {response_text}")

            result = json.loads(response_text)
            print(f"[SUCCESS] Vobiz API call successful!")
            print(f"[SUCCESS] Call UUID: {result.get('call_uuid', 'N/A')}")
            print("[DEBUG] ========== VOBIZ API CALL END ==========\n")
            return result

    except Exception as e:
        print(f"[ERROR] Exception during Vobiz API call: {e}")
        print(f"[ERROR] Exception type: {type(e).__name__}")
        import traceback
        print(f"[ERROR] Traceback:\n{traceback.format_exc()}")
        print("[DEBUG] ========== VOBIZ API CALL END (WITH ERROR) ==========\n")
        raise


def get_host_and_protocol(request: Request = None):
    """Get host and protocol, prioritizing PUBLIC_URL environment variable.

    Returns:
        tuple: (host, protocol)
    """
    public_url = os.getenv("PUBLIC_URL")

    if public_url:
        # Use configured public URL
        print(f"[INFO] Using PUBLIC_URL from environment: {public_url}")
        # Extract host and protocol from PUBLIC_URL
        if public_url.startswith("https://"):
            protocol = "https"
            host = public_url.replace("https://", "").rstrip("/")
        elif public_url.startswith("http://"):
            protocol = "http"
            host = public_url.replace("http://", "").rstrip("/")
        else:
            # No protocol specified, assume https
            protocol = "https"
            host = public_url.rstrip("/")
        print(f"[INFO] Extracted - Host: {host}, Protocol: {protocol}")
        return host, protocol
    else:
        # Fall back to request headers
        if request is None:
            raise ValueError("Request object required when PUBLIC_URL is not set")

        host = request.headers.get("host")
        if not host:
            raise ValueError("Cannot determine server host from request headers")

        print(f"[DEBUG] Host from request headers: {host}")

        # Detect protocol
        # Check X-Forwarded-Proto header (set by ngrok/proxies) or scheme
        forwarded_proto = request.headers.get("x-forwarded-proto", "")
        if forwarded_proto:
            protocol = forwarded_proto
        else:
            # Fall back to checking if host looks like localhost
            protocol = (
                "http"
                if host.startswith("localhost") or host.startswith("127.0.0.1")
                else "https"
            )

        # Warn if using localhost without PUBLIC_URL set
        if host.startswith("localhost") or host.startswith("127.0.0.1"):
            print("[WARNING] [ALERT] Using localhost for URL!")
            print("[WARNING] [ALERT] Vobiz will NOT be able to reach this URL!")
            print("[WARNING] [ALERT] Solution: Set PUBLIC_URL in .env")

        print(f"[DEBUG] Detected protocol: {protocol}")
        return host, protocol


def get_websocket_url(host: str):
    """Construct WebSocket URL for Vobiz Stream XML.

    """
    env = os.getenv("ENV", "local").lower()

    if env == "production":
        # For production, use Pipecat Cloud WebSocket URL (Plivo endpoint works for Vobiz)
        return "wss://api.pipecat.daily.co/ws/plivo"
    else:
        # Return WebSocket URL for local/ngrok deployment
        return f"wss://{host}/ws"


# ----------------- API ----------------- #


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create aiohttp session for Vobiz API calls
    app.state.session = aiohttp.ClientSession()
    yield
    # Close session when shutting down
    await app.state.session.close()


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for testing
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/start")
async def initiate_outbound_call(request: Request) -> JSONResponse:
    """Handle outbound call request and initiate call via Vobiz."""
    print("Received outbound call request")

    try:
        data = await request.json()

        # Validate request data
        if not data.get("phone_number"):
            raise HTTPException(
                status_code=400, detail="Missing 'phone_number' in the request body"
            )

        # Extract the phone number to dial
        phone_number = str(data["phone_number"])

        # Extract body data if provided
        body_data = data.get("body", {})
        
        # Inject the parsed phone number into body_data so it reaches Pipecat
        body_data["phone_number"] = phone_number
        
        print(f"\n[INFO] Processing outbound call to {phone_number}")
        print(f"[DEBUG] Body data: {body_data}")

        # Get server URL for answer URL using helper function
        host, protocol = get_host_and_protocol(request)

        # Add body data as query parameters to answer URL
        answer_url = f"{protocol}://{host}/answer"
        if body_data:
            body_json = json.dumps(body_data)
            body_encoded = urllib.parse.quote(body_json)
            answer_url = f"{answer_url}?body_data={body_encoded}"

        print(f"[INFO] Answer URL that will be sent to Vobiz: {answer_url}")

        # Get the from number (optional - can be provided in request body)
        from_number = data.get("from_number") or os.getenv("VOBIZ_PHONE_NUMBER")
        print(f"[DEBUG] From number: {from_number}")

        if not from_number:
            print("[ERROR] VOBIZ_PHONE_NUMBER not set in environment and 'from_number' not provided in request")
            raise HTTPException(
                status_code=400,
                detail="Either set VOBIZ_PHONE_NUMBER in .env or provide 'from_number' in request body"
            )

        # Initiate outbound call via Vobiz
        try:
            print(f"[INFO] Initiating Vobiz API call...")
            call_result = await make_vobiz_call(
                session=request.app.state.session,
                to_number=phone_number,
                from_number=from_number,
                answer_url=answer_url,
            )

            # Extract call UUID from Vobiz response
            call_uuid = call_result.get("request_uuid") or call_result.get("call_uuid") or "unknown"
            print(f"[SUCCESS] Call initiated successfully! Call UUID: {call_uuid}")

            # Pre-create entry in active_calls for transfer tracking
            # This allows /answer to check transfer state using CallUUID from Vobiz
            if call_uuid and call_uuid != "unknown":
                active_calls[call_uuid] = {
                    "status": "initiated",
                    "started_at": datetime.now().isoformat(),
                    "transfer_requested": False,
                    "websocket": None
                }
                print(f"[CALL] Pre-registered call {call_uuid} in active_calls")

        except Exception as e:
            print(f"[ERROR] Failed to initiate Vobiz call: {e}")
            import traceback
            print(f"[ERROR] Full traceback:\n{traceback.format_exc()}")
            raise HTTPException(status_code=500, detail=f"Failed to initiate call: {str(e)}")

    except HTTPException:
        raise
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")

    return JSONResponse(
        {
            "call_uuid": call_uuid,
            "status": "call_initiated",
            "phone_number": phone_number,
        }
    )


@app.api_route("/answer", methods=["GET", "POST"])
async def get_answer_xml(
    request: Request,
    CallUUID: str = Query(None, description="Vobiz call UUID"),
    body_data: str = Query(None, description="JSON encoded body data"),
) -> HTMLResponse:
    """Return XML instructions for connecting call to WebSocket or transferring to human."""
    print("\n[ANSWER] ========== ANSWER XML REQUEST ==========")
    
    # Try to get CallUUID from query params if None
    if not CallUUID:
        CallUUID = request.query_params.get("CallUUID")

    # If still None, try to get from POST body
    parsed_body_data = {}
    try:
        body_bytes = await request.body()
        if body_bytes:
            body_text = body_bytes.decode("utf-8")
            # Try to parse as JSON or Form data
            try:
                parsed_body_data = json.loads(body_text)
            except json.JSONDecodeError:
                from urllib.parse import parse_qs
                parsed_body_data = {k: v[0] for k, v in parse_qs(body_text).items()}
            
            # Check for CallUUID in standard Vobiz/Plivo fields
            if not CallUUID:
                CallUUID = parsed_body_data.get("CallUUID") or parsed_body_data.get("call_uuid") or parsed_body_data.get("request_uuid")
    except Exception as e:
        print(f"[ANSWER] Error parsing body: {e}")

    # Merge injected body_data from query parameters (contains phone_number)
    if body_data:
        try:
            import urllib.parse
            injected_data = json.loads(urllib.parse.unquote(body_data))
            parsed_body_data.update(injected_data)
        except Exception as e:
            print(f"[ANSWER] Error parsing query body_data: {e}")

    print(f"[ANSWER] Call UUID: {CallUUID}")

    # Check if this call is marked for transfer
    if CallUUID and CallUUID in active_calls:
        call_info = active_calls[CallUUID]
        if call_info.get("transfer_requested"):
            print(f"[ANSWER] [TRANSFER] Call {CallUUID} is marked for transfer - returning Dial XML")

            # Get transfer destination
            agent_number = os.getenv("TRANSFER_AGENT_NUMBER", "+919148227303")

            # Return transfer XML with Dial element
            xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Speak voice="WOMAN" language="en-US">
        Please hold while I transfer you to a human agent.
    </Speak>
    <Dial>{agent_number}</Dial>
</Response>"""

            print(f"[ANSWER] Transferring to: {agent_number}")
            print(f"[ANSWER] Returning Dial XML")
            print("[ANSWER] ========== ANSWER XML END (TRANSFER) ==========\n")

            # Clean up transfer flag
            call_info["transfer_requested"] = False
            call_info["status"] = "transferred"

            return HTMLResponse(content=xml_content, media_type="application/xml")

    # Normal flow: Return Stream XML for bot conversation
    print(f"[ANSWER] Normal call flow - returning Stream XML")

    # Log call details
    if CallUUID:
        if parsed_body_data:
            print(f"[ANSWER] Body data: {parsed_body_data}")

    try:
        # Get the server host and protocol using helper function
        # This ensures we use PUBLIC_URL if configured
        host, protocol = get_host_and_protocol(request)

        # Get base WebSocket URL (Vobiz uses wss:// protocol)
        base_ws_url = get_websocket_url(host)

        # Add query parameters to WebSocket URL
        query_params = []

        # Add serviceHost for production
        env = os.getenv("ENV", "local").lower()
        if env == "production":
            agent_name = os.getenv("AGENT_NAME")
            org_name = os.getenv("ORGANIZATION_NAME")
            service_host = f"{agent_name}.{org_name}"
            query_params.append(f"serviceHost={service_host}")

        # Add body data if available
        if parsed_body_data:
            body_json = json.dumps(parsed_body_data)
            body_encoded = base64.b64encode(body_json.encode("utf-8")).decode("utf-8")
            query_params.append(f"body={body_encoded}")

        # Add CallUUID if available
        if CallUUID:
            query_params.append(f"call_uuid={CallUUID}")

        # NOTE: Vobiz-level <Record> element removed.
        # Recording is now handled natively by Pipecat's AudioBufferProcessor
        # inside bot.py / bot_live.py at full 16-24kHz lossless WAV quality.

        # Construct final WebSocket URL with query parameters
        ws_url_base = f"wss://{host}/voice/ws"
        
        # Ensure call_uuid is in query_params if we have it
        if CallUUID and not any(p.startswith("call_uuid=") for p in query_params):
            query_params.append(f"call_uuid={CallUUID}")
            
        final_ws_url = f"{ws_url_base}?{'&amp;'.join(query_params)}" if query_params else ws_url_base

        xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
        <Stream bidirectional="true" audioTrack="inbound" contentType="audio/x-mulaw;rate=8000" keepCallAlive="true">
            {final_ws_url}
        </Stream>
</Response>"""

        print(f"[DEBUG] XML Response:\n{xml_content}")
        print("[ANSWER] ========== ANSWER XML END (STREAM) ==========\n")

        return HTMLResponse(content=xml_content, media_type="application/xml")

    except Exception as e:
        print(f"Error generating answer XML: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate XML: {str(e)}")


@app.api_route("/recording-finished", methods=["GET", "POST"])
async def recording_finished(request: Request) -> HTMLResponse:
    """Called by Vobiz when recording stops"""
    print("\n[RECORDING] ========== RECORDING FINISHED ==========")

    # Vobiz sends form data, not JSON
    data = await request.form()

    recording_url = data.get("RecordUrl")
    duration = data.get("RecordingDuration")
    duration_ms = data.get("RecordingDurationMs")
    recording_id = data.get("RecordingID")
    call_uuid = data.get("CallUUID")
    recording_start_ms = data.get("RecordingStartMs")
    recording_end_ms = data.get("RecordingEndMs")
    recording_end_reason = data.get("RecordingEndReason")

    print(f"[RECORDING] Recording URL: {recording_url}")
    print(f"[RECORDING] Duration: {duration} seconds ({duration_ms} ms)")
    print(f"[RECORDING] Recording ID: {recording_id}")
    print(f"[RECORDING] Call UUID: {call_uuid}")
    print(f"[RECORDING] End Reason: {recording_end_reason}")
    print(f"[RECORDING] Start Time: {recording_start_ms}")
    print(f"[RECORDING] End Time: {recording_end_ms}")

    # Store recording ID in active_calls for easy lookup
    if call_uuid and call_uuid in active_calls:
        active_calls[call_uuid]["recording_id"] = recording_id
        active_calls[call_uuid]["recording_url"] = recording_url
        print(f"[RECORDING] [SUCCESS] Stored recording ID {recording_id} for call {call_uuid}")
    else:
        print(f"[RECORDING] [WARNING] Call {call_uuid} not found in active_calls (may have ended)")

    # Optional: Download the recording
    # if recording_url:
    #     async with aiohttp.ClientSession() as session:
    #         async with session.get(recording_url) as resp:
    #             audio_data = await resp.read()
    #             with open(f"recordings/{recording_id}.mp3", "wb") as f:
    #                 f.write(audio_data)
    #     print(f"[RECORDING] Downloaded to recordings/{recording_id}.mp3")

    print("[RECORDING] ========== RECORDING FINISHED END ==========\n")

    # Return empty XML response
    return HTMLResponse(content="<Response></Response>", media_type="application/xml")


@app.api_route("/recording-ready", methods=["GET", "POST"])
async def recording_ready(request: Request) -> HTMLResponse:
    """Called by Vobiz when recording file is ready to download (via callbackUrl)"""
    print("\n[RECORDING CALLBACK] ========== RECORDING FILE READY ==========")

    # Vobiz sends form data
    data = await request.form()

    recording_url = data.get("RecordUrl")
    recording_id = data.get("RecordingID")
    call_uuid = data.get("CallUUID")

    print(f"[RECORDING CALLBACK] Recording file is ready for download!")
    print(f"[RECORDING CALLBACK] URL: {recording_url}")
    print(f"[RECORDING CALLBACK] Recording ID: {recording_id}")
    print(f"[RECORDING CALLBACK] Call UUID: {call_uuid}")

    # Auto-download the recording file with authentication
    if recording_url and recording_id:
        try:
            # Create recordings directory if it doesn't exist
            os.makedirs("recordings", exist_ok=True)

            # Get Vobiz credentials for authenticated download
            auth_id = os.getenv("VOBIZ_AUTH_ID")
            auth_token = os.getenv("VOBIZ_AUTH_TOKEN")

            headers = {
                "X-Auth-ID": auth_id,
                "X-Auth-Token": auth_token,
            }

            print(f"[RECORDING CALLBACK] Downloading recording...")

            async with aiohttp.ClientSession() as session:
                async with session.get(recording_url, headers=headers) as resp:
                    if resp.status == 200:
                        audio_data = await resp.read()
                        filename = f"recordings/{recording_id}.mp3"
                        with open(filename, "wb") as f:
                            f.write(audio_data)
                        print(f"[RECORDING CALLBACK] [SUCCESS] Downloaded to {filename}")
                        print(f"[RECORDING CALLBACK] File size: {len(audio_data)} bytes")
                    else:
                        print(f"[RECORDING CALLBACK] [ERROR] Download failed: HTTP {resp.status}")
                        error_text = await resp.text()
                        print(f"[RECORDING CALLBACK] Error: {error_text}")
        except Exception as e:
            print(f"[RECORDING CALLBACK] [ERROR] Error downloading recording: {e}")
            import traceback
            print(f"[RECORDING CALLBACK] Traceback:\n{traceback.format_exc()}")

    print("[RECORDING CALLBACK] ========== RECORDING FILE READY END ==========\n")

    # Return empty XML response
    return HTMLResponse(content="<Response></Response>", media_type="application/xml")


@app.post("/transfer-to-human")
async def transfer_to_human(request: Request) -> HTMLResponse:
    """Return XML to transfer call to a human agent"""
    print("\n[TRANSFER] ========== TRANSFER TO HUMAN ==========")

    # Get transfer destination from query params or use default
    agent_number = os.getenv("TRANSFER_AGENT_NUMBER", "+919148227303")

    print(f"[TRANSFER] Transferring call to human agent: {agent_number}")

    # XML to transfer call to human
    xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Speak voice="WOMAN" language="en-US">
        Please hold while I transfer you to a human agent.
    </Speak>
    <Dial>+919148227303</Dial>
</Response>"""

    print(f"[TRANSFER] Returning transfer XML")
    print("[TRANSFER] ========== TRANSFER TO HUMAN END ==========\n")

    return HTMLResponse(content=xml_content, media_type="application/xml")


@app.post("/initiate-transfer")
async def initiate_transfer(request: Request) -> JSONResponse:
    """Trigger call transfer via Vobiz API"""
    print("\n[TRANSFER] ========== INITIATE TRANSFER ==========")

    data = await request.json()
    call_uuid = data.get("call_uuid")

    if not call_uuid:
        raise HTTPException(status_code=400, detail="Missing 'call_uuid' in request body")

    # Check if call exists in active_calls
    if call_uuid not in active_calls:
        raise HTTPException(status_code=404, detail=f"Call {call_uuid} not found in active calls")

    call_info = active_calls[call_uuid]

    # Mark call as transferring
    call_info["status"] = "transferring"
    print(f"[TRANSFER] Marked call {call_uuid} as transferring")

    # Get Vobiz credentials
    auth_id = os.getenv("VOBIZ_AUTH_ID")
    auth_token = os.getenv("VOBIZ_AUTH_TOKEN")

    # Get PUBLIC_URL for transfer endpoint
    public_url = os.getenv("PUBLIC_URL")
    if not public_url:
        raise HTTPException(status_code=500, detail="PUBLIC_URL not configured in .env")

    # Construct transfer URL
    if public_url.startswith("http://") or public_url.startswith("https://"):
        transfer_url = f"{public_url}/transfer-to-human"
    else:
        transfer_url = f"https://{public_url}/transfer-to-human"

    print(f"[TRANSFER] Call UUID: {call_uuid}")
    print(f"[TRANSFER] Transfer URL: {transfer_url}")

    # Vobiz Transfer API endpoint
    vobiz_url = f"https://api.vobiz.ai/api/v1/Account/{auth_id}/Call/{call_uuid}/"

    headers = {
        "X-Auth-ID": auth_id,
        "X-Auth-Token": auth_token,
        "Content-Type": "application/json"
    }

    transfer_data = {
        "legs": "aleg",  # Transfer the caller (A leg)
        "aleg_url": transfer_url,
        "aleg_method": "POST"
    }

    print(f"[TRANSFER] Calling Vobiz Transfer API...")
    print(f"[TRANSFER] URL: {vobiz_url}")
    print(f"[TRANSFER] Data: {json.dumps(transfer_data, indent=2)}")
    print(f"[TRANSFER] NOTE: Transfer API should close Stream and fetch new XML from {transfer_url}")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(vobiz_url, headers=headers, json=transfer_data) as resp:
                response_text = await resp.text()
                print(f"[TRANSFER] Vobiz Response Status: {resp.status}")
                print(f"[TRANSFER] Vobiz Response Body: {response_text}")

                if resp.status == 202:  # 202 Accepted
                    result = json.loads(response_text)
                    print(f"[TRANSFER] ✅ Transfer API call successful!")
                    print(f"[TRANSFER] Vobiz should now fetch XML from {transfer_url}")
                    print("[TRANSFER] ========== INITIATE TRANSFER END ==========\n")

                    return JSONResponse({
                        "status": "transfer_initiated",
                        "call_uuid": call_uuid,
                        "transfer_url": transfer_url,
                        "vobiz_response": result
                    })
                else:
                    print(f"[TRANSFER] ❌ Transfer failed!")
                    print("[TRANSFER] ========== INITIATE TRANSFER END (FAILED) ==========\n")
                    raise HTTPException(
                        status_code=resp.status,
                        detail=f"Vobiz transfer failed: {response_text}"
                    )

    except Exception as e:
        print(f"[TRANSFER] ❌ Error during transfer: {e}")
        import traceback
        print(f"[TRANSFER] Traceback:\n{traceback.format_exc()}")
        print("[TRANSFER] ========== INITIATE TRANSFER END (ERROR) ==========\n")
        raise HTTPException(status_code=500, detail=f"Transfer error: {str(e)}")


@app.get("/active-calls")
async def get_active_calls() -> JSONResponse:
    """List all currently active calls"""
    print("[ACTIVE CALLS] Fetching active calls list")

    # Create a serializable version of active_calls (excluding websocket objects)
    calls_info = {}
    for call_uuid, call_data in active_calls.items():
        calls_info[call_uuid] = {
            "status": call_data.get("status"),
            "started_at": call_data.get("started_at"),
            "path": call_data.get("path"),
            "recording_id": call_data.get("recording_id"),  # Include recording ID if available
            "recording_url": call_data.get("recording_url")  # Include recording URL if available
            # Exclude 'websocket' as it's not JSON serializable
        }

    return JSONResponse({
        "active_calls": list(active_calls.keys()),
        "count": len(active_calls),
        "calls": calls_info
    })


async def handle_vobiz_websocket(
    websocket: WebSocket,
    path: str,
    body: str = None,
    serviceHost: str = None,
):
    """Common handler for Vobiz WebSocket connections on any path."""
    print("[DEBUG] ========================================")
    print(f"[DEBUG] WebSocket connection attempt on path: {path}")
    print(f"[DEBUG] Client: {websocket.client}")
    print(f"[DEBUG] Headers: {dict(websocket.headers)}")
    print(f"[DEBUG] Query params - body: {body}, serviceHost: {serviceHost}")
    print("[DEBUG] ========================================")

    try:
        # Accept the connection with the appropriate subprotocol for Vobiz/SIP
        await websocket.accept(subprotocol="audio.drachtio.org")
        print("[SUCCESS] WebSocket connection accepted for outbound call")
    except Exception as e:
        print(f"[ERROR] Failed to accept WebSocket connection: {e}")
        raise

    # Decode body parameter if provided
    body_data = {}
    if body:
        try:
            # Base64 decode the JSON (it was base64-encoded in the answer endpoint)
            decoded_json = base64.b64decode(body).decode("utf-8")
            body_data = json.loads(decoded_json)
            print(f"Decoded body data: {body_data}")
        except Exception as e:
            print(f"Error decoding body parameter: {e}")
    else:
        print("No body parameter received")

    call_uuid = None

    try:
        from pipecat.runner.types import WebSocketRunnerArguments
        from pipecat.runner.utils import parse_telephony_websocket

        print("[DEBUG] Starting bot initialization...")

        print("[DEBUG] Starting bot initialization...")

        # CRITICAL FIX: Do NOT parse the WebSocket here using parse_telephony_websocket(websocket)
        # That would consume the initial handshake messages, leaving the socket "empty" for the Pipecat transport.
        # Instead, we rely on the query parameters we put in the XML (call_uuid).
        
        # Get IDs from query params (preferred) or just generate/placeholder if missing
        call_uuid = websocket.query_params.get("call_uuid")
        if not call_uuid:
             call_uuid = websocket.query_params.get("call_id")
        
        # Stream ID might come later in the protocol, but for Vobiz/Plivo it's often in the start message.
        # Since we can't read the start message here without breaking Pipecat, we pass None
        # and let bot.py's transport handle the protocol handshake naturally.
        stream_id = None 

        if call_uuid:
            # Update or create entry in active_calls with WebSocket reference
            if call_uuid in active_calls:
                # Update existing entry (from /start pre-registration)
                active_calls[call_uuid]["status"] = "active"
                active_calls[call_uuid]["websocket"] = websocket
                active_calls[call_uuid]["path"] = path
                print(f"[CALL] [SUCCESS] Updated existing call {call_uuid} with WebSocket")
            else:
                # Create new entry
                active_calls[call_uuid] = {
                    "status": "active",
                    "started_at": datetime.now().isoformat(),
                    "path": path,
                    "websocket": websocket,
                    "transfer_requested": False
                }
                print(f"[CALL] [SUCCESS] Created new call entry for {call_uuid}")

            print(f"[CALL] Active calls count: {len(active_calls)}")
        else:
            print("[CALL] [WARNING] No call UUID found in URL query params")

        # Create runner arguments and run the bot
        runner_args = WebSocketRunnerArguments(websocket=websocket)
        runner_args.handle_sigint = False

        print("[DEBUG] Calling bot function...")
        # Make a backwards-compatible call, passing body_data to bot if it supports it
        import inspect
        sig = inspect.signature(bot)
        if "body_data" in sig.parameters:
            await bot(runner_args, call_id=call_uuid, stream_id=stream_id, body_data=body_data)
        else:
            await bot(runner_args, call_id=call_uuid, stream_id=stream_id)

        print("[DEBUG] Bot function completed")

    except Exception as e:
        print(f"[ERROR] Error in WebSocket endpoint: {e}")
        import traceback
        print(f"[ERROR] Traceback:\n{traceback.format_exc()}")
        try:
            await websocket.close()
        except:
            pass
    finally:
        # Remove call from active_calls when WebSocket closes
        # BUT: Don't remove if call is being transferred (status == "transferring")
        if call_uuid and call_uuid in active_calls:
            call_status = active_calls[call_uuid].get("status", "active")
            if call_status == "transferring":
                print(f"[CALL] [TRANSFER] Call {call_uuid} is being transferred - keeping in active_calls")
                # Remove websocket reference but keep call record for transfer
                active_calls[call_uuid]["websocket"] = None
            else:
                # Normal call end - remove completely
                del active_calls[call_uuid]
                print(f"[CALL] [CLEANUP] Removed call UUID: {call_uuid}")
                print(f"[CALL] Active calls count: {len(active_calls)}")


# ----------------- WEB CLIENT (RTVI WebSocket) ----------------- #


async def _run_web_bot(websocket: WebSocket):
    """Run the bot pipeline for browser clients using the RTVI WebSocket protocol.

    Unlike the Vobiz telephony endpoints this does NOT use VobizFrameSerializer.
    The browser connects with @pipecat-ai/client-js WebSocketTransport which
    speaks the standard RTVI framing over a plain WebSocket.
    """
    from pipecat.serializers.protobuf import ProtobufFrameSerializer
    from pipecat.transports.websocket.fastapi import (
        FastAPIWebsocketParams,
        FastAPIWebsocketTransport,
    )
    from pipecat.audio.vad.silero import SileroVADAnalyzer
    from pipecat.audio.vad.vad_analyzer import VADParams

    print("[WEB] Browser client connected via /web-ws")

    try:
        await websocket.accept()
    except Exception as e:
        print(f"[WEB] Failed to accept WebSocket: {e}")
        return

    # IMPORTANT: audio_out_sample_rate must be explicitly declared here so that
    # the ProtobufFrameSerializer / RTVI bot-ready message tells the browser
    # client-react AudioWorklet to play at 16kHz, not the browser default 48kHz.
    # Mismatch => Bugs Bunny 3x pitch shift.
    WEB_SAMPLE_RATE = 16000

    transport = FastAPIWebsocketTransport(
        websocket=websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            vad_enabled=True,
            vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=0.5)),
            serializer=ProtobufFrameSerializer(),
            audio_out_sample_rate=WEB_SAMPLE_RATE,  # must match bot_live PipelineParams
        ),
    )

    # Unique call_id per session so recordings don't overwrite each other
    web_call_id = f"web-{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    print(f"[WEB] Session ID: {web_call_id}")

    try:
        await run_bot(transport, handle_sigint=False, phone_number="web-user", call_id=web_call_id)
    except Exception as e:
        import traceback
        print(f"[WEB] Error running web bot: {e}")
        print(traceback.format_exc())
    finally:
        print("[WEB] Browser client disconnected")


@app.websocket("/web-ws")
async def websocket_web_client(websocket: WebSocket):
    """RTVI WebSocket endpoint for browser clients.

    Connect from the React frontend:
        const transport = new WebSocketTransport();
        await client.connect({ url: 'ws://localhost:7860/web-ws' });
    """
    await _run_web_bot(websocket)


# ----------------- TELEPHONY WebSocket endpoints ----------------- #

# Register WebSocket endpoints for common paths Vobiz might use
@app.websocket("/ws")
async def websocket_ws(
    websocket: WebSocket,
    body: str = Query(None),
    serviceHost: str = Query(None),
):
    """Handle WebSocket connection at /ws path."""
    await handle_vobiz_websocket(websocket, "/ws", body, serviceHost)


@app.websocket("/")
async def websocket_root(
    websocket: WebSocket,
    body: str = Query(None),
    serviceHost: str = Query(None),
):
    """Handle WebSocket connection at root path."""
    await handle_vobiz_websocket(websocket, "/", body, serviceHost)


@app.websocket("/voice/ws")
async def websocket_voice_ws(
    websocket: WebSocket,
    body: str = Query(None),
    serviceHost: str = Query(None),
):
    """Handle WebSocket connection at /voice/ws path to match user XML."""
    await handle_vobiz_websocket(websocket, "/voice/ws", body, serviceHost)


@app.websocket("/stream")
async def websocket_stream(
    websocket: WebSocket,
    body: str = Query(None),
    serviceHost: str = Query(None),
):
    """Handle WebSocket connection at /stream path."""
    await handle_vobiz_websocket(websocket, "/stream", body, serviceHost)


# ----------------- Main ----------------- #


if __name__ == "__main__":
    print(f"\n[DEBUG] Server starting...")
    print(f"[DEBUG] ENV: {os.getenv('ENV')}")
    print(f"[DEBUG] PUBLIC_URL: {os.getenv('PUBLIC_URL')}")

    # Start ngrok tunnel in local environment
    if os.getenv("ENV", "local").lower() == "local":
        print(f"[NGROK] Attempting to start tunnel on port 7860...")
        try:
            # Kill existing ngrok instances to avoid conflicts
            import subprocess
            subprocess.run(["taskkill", "/F", "/IM", "ngrok.exe"], 
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            port = 7860
            public_url = ngrok.connect(port).public_url
            print(f"\n[NGROK] Tunnel active at: {public_url}")
            os.environ["PUBLIC_URL"] = public_url
        except Exception as e:
            print(f"[NGROK] Failed to start tunnel: {e}")

    uvicorn.run(app, host="127.0.0.1", port=7860)
