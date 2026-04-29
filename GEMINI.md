# Vobiz-X-Pipecat: AI Voice Agent & Campaign Manager

## Project Overview
Vobiz-X-Pipecat is an AI-powered outbound calling system designed for automated conversations and campaign management. It integrates the [Vobiz](https://vobiz.ai) telephony API with the [Pipecat](https://pipecat.ai) voice agent framework to deliver natural, low-latency AI voice interactions.

### Core Features
- 🤖 **Multi-Modal AI Agents**: Supports cascaded STT-LLM-TTS pipelines (via `bot.py`) and high-performance Gemini Flash Live (via `bot_live.py`).
- 📞 **Outbound SIP Calling**: Programmatic call initiation via Vobiz's REST API.
- 📊 **Campaign Management**: Batch calling from CSV/Excel lists with support for sequential or concurrent modes.
- 🎙️ **Native Recording**: High-quality stereo recordings (User: Left, Bot: Right) captured directly in the pipeline.
- 🖥️ **Web Dashboard**: React-based frontend for monitoring active calls, managing campaigns, and reviewing transcripts/recordings.
- 🔄 **Real-time Streaming**: Bidirectional audio via WebSockets using the Vobiz Media Stream protocol.

### Technical Stack
- **Backend**: Python 3.10+ (FastAPI, Pipecat, Uvicorn, aiohttp).
- **Frontend**: React (Vite, Lucide-React, React Router, Pipecat Client SDKs).
- **AI Services**: OpenAI (GPT-4o), Google (Gemini 1.5 Flash), Sarvam AI (Indian language STT/TTS), Deepgram (STT).
- **Persistence**: Local JSON-based storage for call logs and campaign metadata in the `recordings/` directory.

---

## Building and Running

### Prerequisites
- **Python 3.10+**
- **Node.js & npm** (for frontend)
- **ngrok** (for local development webhooks)
- **Vobiz Account** (Auth ID and Token)
- **API Keys**: OpenAI, Sarvam, or Google Gemini.

### Backend Setup
1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Configure environment:
   ```bash
   cp env.example .env
   # Edit .env with your credentials
   ```
3. Run the server:
   ```bash
   python server.py
   ```
   The server runs on `http://127.0.0.1:7860`. It will attempt to start an ngrok tunnel automatically in local mode.

### Frontend Setup
1. Navigate to the frontend directory:
   ```bash
   cd frontend
   ```
2. Install dependencies:
   ```bash
   npm install
   ```
3. Run in development mode:
   ```bash
   npm run dev
   ```

---

## Key Components

### Backend Logic
- `server.py`: Handles HTTP API endpoints, Vobiz XML callbacks (`/answer`), and WebSocket connections for media streams.
- `bot.py`: Defines the cascaded voice pipeline (STT -> LLM -> TTS).
- `bot_live.py`: Defines the Gemini 1.5 Flash Live pipeline for ultra-low latency.
- `call_manager.py`: High-level orchestrator for single calls and campaigns.
- `campaign_runner.py`: Async background worker for processing campaign queues.
- `call_store.py`: Persistence layer handling JSON file I/O for logs and campaigns.

### Telephony Flow
1. **Initiation**: `POST /start` -> `make_vobiz_call` -> Vobiz API.
2. **Callback**: Vobiz calls `POST /answer` -> Server returns XML with `<Stream>` (WebSocket URL).
3. **Audio**: Vobiz connects to `wss://{host}/voice/ws` -> Pipecat pipeline starts.
4. **Completion**: Call ends -> Recording is saved -> `call_log.json` is updated.

---

## Development Conventions

### Coding Style
- **Python**: Follows standard PEP 8. Uses `loguru` for structured logging. Async-first architecture using `asyncio` and `FastAPI`.
- **Frontend**: Functional React components with hooks. Uses Tailwind-like Vanilla CSS in `index.css`.

### Testing
- Use `test_local.py` for testing the Pipecat pipeline without telephony.
- Use `test_sarvam.py` or `test_whatsapp_parsing.py` for specific module verification.

### Data Management
- All persistent data (logs, campaigns, recordings) is stored in the `recordings/` folder.
- Call records use UUIDs for internal tracking and map them to Vobiz's `call_uuid`.

### Customization
- **Bot Personality**: Edit the `messages` array in `bot.py` or `bot_live.py`.
- **Voices**: Configure `SarvamTTSService` settings in `bot.py`.
- **Transfer**: Set `TRANSFER_AGENT_NUMBER` in `.env` for the "Transfer to Human" feature.

## graphify

This project has a graphify knowledge graph at graphify-out/.

Rules:
- Before answering architecture or codebase questions, read graphify-out/GRAPH_REPORT.md for god nodes and community structure
- If graphify-out/wiki/index.md exists, navigate it instead of reading raw files
- For cross-module "how does X relate to Y" questions, prefer `graphify query "<question>"`, `graphify path "<A>" "<B>"`, or `graphify explain "<concept>"` over grep — these traverse the graph's EXTRACTED + INFERRED edges instead of scanning files
- After modifying code files in this session, run `graphify update .` to keep the graph current (AST-only, no API cost)
