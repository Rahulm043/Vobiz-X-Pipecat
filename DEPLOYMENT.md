# Vobiz-X-Pipecat Deployment Guide

Complete deployment guide for the backend (VPS) and frontend (Vercel).

---

## Table of Contents

1. [Backend Deployment (VPS)](#backend-deployment-vps)
2. [Frontend Deployment (Vercel)](#frontend-deployment-vercel)
3. [Testing the Backend](#testing-the-backend)
4. [Useful Commands](#useful-commands)
5. [Troubleshooting](#troubleshooting)

---

## Backend Deployment (VPS)

### Prerequisites

- Ubuntu 22.04/24.04 VPS with root/sudo access
- Domain pointing to VPS IP (A record)
- Required credentials:
  - OpenAI API key
  - Sarvam API key (STT + TTS)
  - Vobiz Auth ID and Auth Token
  - Vobiz phone number
  - Supabase URL, Service Key, and Anon Key
  - Transfer agent phone number (optional)

### Step 1: Clone the Repository

```bash
git clone https://github.com/Rahulm043/Vobiz-X-Pipecat.git
cd Vobiz-X-Pipecat
```

### Step 2: Install System Dependencies

```bash
sudo apt update && sudo apt install -y python3.12-venv nginx certbot python3-certbot-nginx
```

### Step 3: Set Up Python Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install pyngrok
```

### Step 4: Create `.env` File

```bash
cp env.example .env
nano .env
```

Fill in all credentials. Required variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes | OpenAI API key for LLM (gpt-4o-mini) |
| `SARVAM_API_KEY` | Yes | Sarvam API key for STT and TTS |
| `VOBIZ_AUTH_ID` | Yes | Your Vobiz Auth ID (MA_XXXXXXXX) |
| `VOBIZ_AUTH_TOKEN` | Yes | Your Vobiz Auth Token |
| `VOBIZ_PHONE_NUMBER` | Yes | Your Vobiz phone number (+91XXXXXXXXXX) |
| `SUPABASE_URL` | Yes | Supabase project URL |
| `SUPABASE_SERVICE_KEY` | Yes | Supabase service role key |
| `VITE_SUPABASE_ANON_KEY` | Yes | Supabase anon key (for auth backend) |
| `PUBLIC_URL` | Yes | Your domain URL (https://your-domain.com) |
| `ENV` | Yes | Set to `production` |
| `TRANSFER_AGENT_NUMBER` | No | Human agent number for transfers |

### Step 5: Open Firewall Ports

```bash
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw reload
```

> **IMPORTANT:** Also open ports 80 and 443 in your VPS provider's cloud firewall/security group (AWS Security Groups, DigitalOcean Firewall, etc.). UFW alone is not enough.

### Step 6: Configure Nginx

Create `/etc/nginx/sites-available/your-domain`:

```nginx
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}

upstream vobiz_backend {
    server 127.0.0.1:7860;
}

server {
    listen 80;
    server_name your-domain.com;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 301 https://$host$request_uri;
    }
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $connection_upgrade;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    proxy_read_timeout 86400s;
    proxy_send_timeout 86400s;

    location / {
        proxy_pass http://vobiz_backend;
    }

    location /recordings/ {
        proxy_pass http://vobiz_backend;
    }
}
```

Enable the site:

```bash
sudo mkdir -p /var/www/certbot
sudo ln -sf /etc/nginx/sites-available/your-domain /etc/nginx/sites-enabled/your-domain
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

### Step 7: Get SSL Certificate

```bash
sudo certbot certonly --webroot -w /var/www/certbot -d your-domain.com --non-interactive --agree-tos --email your@email.com
```

Then reload nginx to pick up the SSL certificates:

```bash
sudo systemctl reload nginx
```

### Step 8: Create Systemd Service

Create `/etc/systemd/system/vobiz-pipecat.service`:

```ini
[Unit]
Description=Vobiz-X-Pipecat AI Voice Agent Backend
After=network.target nginx.service

[Service]
Type=simple
User=your-username
WorkingDirectory=/path/to/Vobiz-X-Pipecat
Environment=PATH=/path/to/Vobiz-X-Pipecat/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
ExecStart=/path/to/Vobiz-X-Pipecat/venv/bin/python server.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

# Security hardening
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/path/to/Vobiz-X-Pipecat/recordings

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable vobiz-pipecat
sudo systemctl start vobiz-pipecat
```

### Step 9: Verify

```bash
sudo systemctl status vobiz-pipecat
curl -s https://your-domain.com/answer
```

You should get XML with a WebSocket URL.

---

## Frontend Deployment (Vercel)

### Prerequisites

- Vercel account (free tier works)
- Supabase project configured
- Backend deployed and running

### Step 1: Push Frontend to GitHub (if not already)

The frontend is at `frontend/` within this repo. You have two options:

**Option A: Deploy the monorepo on Vercel (recommended)**
- Connect the full `Vobiz-X-Pipecat` repo to Vercel
- Set the Root Directory to `frontend`

**Option B: Create a separate repo for frontend**
```bash
cd frontend
git init
git remote add origin https://github.com/your-username/vobiz-frontend.git
git add . && git commit -m "Initial frontend"
git push -u origin main
```

### Step 2: Deploy on Vercel

1. Go to [vercel.com](https://vercel.com) → **Add New Project**
2. Import your GitHub repository
3. Configure:
   - **Framework Preset:** Vite
   - **Root Directory:** `frontend` (if using monorepo)
   - **Build Command:** `npm run build` (auto-detected)
   - **Output Directory:** `dist` (auto-detected)

### Step 3: Set Environment Variables

In Vercel → Project Settings → Environment Variables, add:

| Variable | Value |
|----------|-------|
| `VITE_API_BASE` | `https://your-backend-domain.com` (e.g. `https://provaani1.progressive-digital.xyz`) |
| `VITE_SUPABASE_URL` | Your Supabase project URL |
| `VITE_SUPABASE_ANON_KEY` | Your Supabase anon key |

### Step 4: Deploy

Click **Deploy**. Vercel will build and deploy your frontend. You'll get a URL like `your-project.vercel.app`.

### Step 5: Add Frontend URL to Backend CORS

Add your Vercel domain to the CORS allowed origins in `server.py` (line ~214), or set it via environment variable. Current allowed origins:

```python
allowed_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://your-project.vercel.app",  # Add your Vercel URL
]
```

---

## Testing the Backend

### 1. Check Service Status

```bash
sudo systemctl status vobiz-pipecat
sudo journalctl -u vobiz-pipecat -f  # Live logs
```

### 2. Test the `/answer` Endpoint

```bash
curl -X POST https://your-domain.com/answer -v
```

Expected response: XML with `<Stream>` element containing `wss://your-domain.com/voice/ws?...`

### 3. Test with a Real Call

Use the Vobiz API directly:

```bash
curl -X POST https://api.vobiz.ai/api/v1/Account/YOUR_AUTH_ID/Call/ \
  -H "X-Auth-ID: YOUR_AUTH_ID" \
  -H "X-Auth-Token: YOUR_AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "from": "YOUR_VOBIZ_PHONE_NUMBER",
    "to": "NUMBER_TO_CALL",
    "answer_url": "https://your-domain.com/answer",
    "answer_method": "POST"
  }'
```

### 4. Test API Endpoints (with auth)

```bash
# Agent status
curl https://your-domain.com/api/agent/status \
  -H "Authorization: Bearer YOUR_SUPABASE_JWT"

# Active calls
curl https://your-domain.com/api/active-calls \
  -H "Authorization: Bearer YOUR_SUPABASE_JWT"

# Call stats
curl https://your-domain.com/api/agent/stats \
  -H "Authorization: Bearer YOUR_SUPABASE_JWT"
```

### 5. Test WebSocket (Browser)

Open browser console and run:

```javascript
const ws = new WebSocket('wss://your-domain.com/web-ws');
ws.onopen = () => console.log('Connected!');
ws.onmessage = (e) => console.log('Message:', e.data);
ws.onerror = (e) => console.error('Error:', e);
```

### 6. Test Recordings

After a call, check recordings are accessible:

```bash
curl -I https://your-domain.com/recordings/
```

### 7. Test via Frontend

1. Deploy the frontend (see above)
2. Open the Vercel URL in browser
3. Log in with Supabase auth
4. Try making a single call from the Dashboard
5. Check that the call appears in the dashboard

---

## Useful Commands

```bash
# Service management
sudo systemctl start vobiz-pipecat
sudo systemctl stop vobiz-pipecat
sudo systemctl restart vobiz-pipecat
sudo systemctl status vobiz-pipecat

# View logs
sudo journalctl -u vobiz-pipecat -f         # Live tail
sudo journalctl -u vobiz-pipecat --since "1 hour ago"
sudo journalctl -u vobiz-pipecat -n 100      # Last 100 lines

# Nginx
sudo nginx -t                                # Test config
sudo systemctl reload nginx                  # Reload config
sudo systemctl status nginx

# SSL
sudo certbot certificates                    # List certs
sudo certbot renew --dry-run                 # Test renewal

# Firewall
sudo ufw status
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
```

---

## Troubleshooting

### Service won't start

```bash
sudo journalctl -u vobiz-pipecat -n 50 --no-pager
```

Common issues:
- Missing `.env` file or wrong credentials
- Port 7860 already in use: `sudo ss -tlnp | grep 7860`
- Python venv not set up: check `ExecStart` path in service file

### SSL certificate failed

- Check DNS: `dig +short your-domain.com A` should resolve to your VPS IP
- Check port 80 is open in BOTH UFW and cloud firewall
- Check nginx is running: `sudo systemctl status nginx`

### WebSocket connection fails

- Verify nginx proxy config has WebSocket upgrade headers
- Check `proxy_read_timeout` is set to `86400s` for long connections
- Verify SSL is working (WebSocket requires WSS in production)

### 401 Unauthorized on API endpoints

- The backend uses Supabase JWT auth
- Get a valid token from Supabase client or frontend
- Check `[AUTH]` logs: `sudo journalctl -u vobiz-pipecat | grep AUTH`

### Calls not connecting

1. Check `/answer` returns valid XML
2. Check Vobiz API response (call_uuid returned?)
3. Check server logs for WebSocket connection attempts
4. Verify `PUBLIC_URL` in `.env` matches your domain

### Vobiz can't reach the server

- Most common: cloud provider firewall blocking ports 80/443
- Test: `curl -s -I http://your-domain.com` from another machine
- Check: VPS provider dashboard → Firewall/Security Groups

---

## Architecture Summary

```
User Browser → Vercel (Frontend) → HTTPS → VPS (Backend)
                                           ↓
                                    nginx (443) → Uvicorn (7860)
                                           ↓
                                    server.py (FastAPI)
                                           ↓
                                    bot.py (Pipecat Pipeline)
                                    STT (Sarvam) → LLM (OpenAI) → TTS (Sarvam)
                                           ↓
                                    WebSocket → Vobiz → Phone Network
```

### Key Files

| File | Purpose |
|------|---------|
| `server.py` | FastAPI server - HTTP endpoints, WebSocket handler |
| `bot.py` | Pipecat voice agent pipeline (cascaded STT→LLM→TTS) |
| `bot_live.py` | Alternative live bot (Gemini 3.1 Flash) |
| `call_manager.py` | Call state management |
| `call_store.py` | Supabase persistence for calls/campaigns |
| `auth_backend.py` | Supabase JWT verification |
| `supabase_storage.py` | Recording upload to Supabase Storage |
| `csv_parser.py` | CSV/Excel recipient parsing |
| `transcriber.py` | Post-call transcription |
| `frontend/` | React + Vite dashboard |
