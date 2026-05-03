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
- Domain with DNS access (A record to point to VPS IP)
- Required credentials:
  - Google API key (for Gemini 3.1 Flash Live model)
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

> **Note:** `pyngrok` is imported in `server.py` but is **not** in `requirements.txt`. It must be installed manually.

### Step 4: Create `.env` File

```bash
cp env.example .env
nano .env
```

Fill in all credentials. Required variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `GOOGLE_API_KEY` | Yes | Google API key for Gemini 3.1 Flash Live (bot_live.py) |
| `VOBIZ_AUTH_ID` | Yes | Your Vobiz Auth ID (MA_XXXXXXXX) |
| `VOBIZ_AUTH_TOKEN` | Yes | Your Vobiz Auth Token |
| `VOBIZ_PHONE_NUMBER` | Yes | Your Vobiz phone number (+91XXXXXXXXXX) |
| `SUPABASE_URL` | Yes | Supabase project URL |
| `SUPABASE_SERVICE_KEY` | Yes | Supabase service role key |
| `VITE_SUPABASE_ANON_KEY` | Yes | Supabase anon key (for auth backend) |
| `PUBLIC_URL` | Yes | Your domain URL (https://your-domain.com) |
| `ENV` | Yes | Set to `production` |
| `USE_LIVE_BOT` | Yes | Set to `true` (uses bot_live.py with Gemini) |
| `TRANSFER_AGENT_NUMBER` | No | Human agent number for transfers |
| `AGENT_NAME` | No | Agent name (for Pipecat Cloud / display) |
| `ORGANIZATION_NAME` | No | Organization name (for Pipecat Cloud) |

> **Note:** `OPENAI_API_KEY` and `SARVAM_API_KEY` are only needed if using `bot.py` (cascaded STT→LLM→TTS pipeline). For `bot_live.py` (Gemini), only `GOOGLE_API_KEY` is required.

### Step 5: Open Firewall Ports

```bash
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw reload
```

> **IMPORTANT:** Also open ports 22, 80, and 443 in your VPS provider's cloud firewall/security group (Azure NSG, AWS Security Groups, DigitalOcean Firewall, etc.). UFW alone is not enough on cloud providers.

### Step 6: Set Up DNS

Create an A record in your DNS provider:

| Type | Host / Name | Value | TTL |
|------|-------------|-------|-----|
| A | `your-subdomain` (e.g., `provaani-main-demo`) | `<your-vps-public-ip>` | Auto or 3600 |

> **Note:** The Host/Name field is just the subdomain part. If your DNS provider requires a full FQDN, use `your-subdomain.your-domain.com.` (with trailing dot).

Verify DNS resolves to your VPS:

```bash
dig +short your-domain.com A
# Should return your VPS public IP
```

> **Wait for DNS propagation** before requesting an SSL certificate. Certbot will fail if the domain doesn't resolve to your server yet.

### Step 7: Configure Nginx (HTTP first, for SSL cert)

Create the initial HTTP-only nginx config at `/etc/nginx/sites-available/your-domain`:

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
        proxy_pass http://vobiz_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
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

### Step 8: Get SSL Certificate

Stop nginx temporarily (certbot standalone mode binds to port 80 directly, which is more reliable than webroot on cloud providers):

```bash
sudo systemctl stop nginx
sudo certbot certonly --standalone -d your-domain.com --non-interactive --agree-tos --email your@email.com --no-eff-email --http-01-port=80
```

After the certificate is issued, update the nginx config to use HTTPS. Replace `/etc/nginx/sites-available/your-domain` with:

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

Reload nginx to apply:

```bash
sudo nginx -t && sudo systemctl start nginx && sudo systemctl reload nginx
```

> **Note:** `proxy_read_timeout` and `proxy_send_timeout` must be set to `86400s` for long-running WebSocket voice calls. The default (60s) will disconnect active calls.

### Step 9: Create Systemd Service

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
EnvironmentFile=/path/to/Vobiz-X-Pipecat/.env
ExecStart=/path/to/Vobiz-X-Pipecat/venv/bin/python server.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

> **Important:** `EnvironmentFile` is required so the service reads your `.env` variables. Without it, the service will start with placeholder values and fail.

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable vobiz-pipecat
sudo systemctl start vobiz-pipecat
```

### Step 10: Configure CORS

Add your frontend domain to `server.py` (line ~214):

```python
allowed_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://your-frontend-domain.com",
    "https://*.vercel.app",
]
```

Then restart the backend:

```bash
sudo systemctl restart vobiz-pipecat
```

### Step 11: Verify

```bash
sudo systemctl status vobiz-pipecat
curl -s https://your-domain.com/answer
```

You should get XML with a WebSocket URL:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Response>
        <Stream bidirectional="true" audioTrack="inbound" contentType="audio/x-mulaw;rate=8000" keepCallAlive="true">
            wss://your-domain.com/voice/ws?serviceHost=your-agent-name.your-org-name
        </Stream>
</Response>
```

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
| `VITE_API_BASE` | `https://your-backend-domain.com` (e.g., `https://provaani-main-demo.progressive-digital.xyz`) |
| `VITE_SUPABASE_URL` | Your Supabase project URL |
| `VITE_SUPABASE_ANON_KEY` | Your Supabase anon key |
| `VITE_AGENT_NAME` | (Optional) Display name shown in Dashboard |

### Step 4: Deploy

Click **Deploy**. Vercel will build and deploy your frontend. You'll get a URL like `your-project.vercel.app`.

> **Note:** If using a custom domain on Vercel (e.g., `app.your-domain.com`), make sure to also add it to the backend CORS origins in `server.py` and restart the service.

---

## Testing the Backend

### 1. Check Service Status

```bash
sudo systemctl status vobiz-pipecat
sudo journalctl -u vobiz-pipecat -f  # Live logs
```

### 2. Test the `/answer` Endpoint

```bash
curl -s https://your-domain.com/answer
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
- **Missing `.env` file or wrong credentials** — check with `cat .env`
- **Port 7860 already in use** — `sudo ss -tlnp | grep 7860`
- **Python venv not set up** — check `ExecStart` path in service file
- **`ModuleNotFoundError: No module named 'pyngrok'`** — run `pip install pyngrok` in the venv
- **Missing `EnvironmentFile` in systemd service** — the service won't read `.env` variables without it

### SSL certificate failed

- **DNS not propagated** — `dig +short your-domain.com A` should resolve to your VPS IP
- **Port 80 not open** — check both UFW (`sudo ufw status`) and cloud provider firewall/security group
- **Nginx not running** — `sudo systemctl status nginx`
- **Use `--standalone` mode** — if `--webroot` fails (common on cloud providers), stop nginx and use `sudo certbot certonly --standalone -d your-domain.com`

### WebSocket connection fails

- Verify nginx proxy config has WebSocket upgrade headers (`$http_upgrade`, `$connection_upgrade`)
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
5. Check that `AGENT_NAME` and `ORGANIZATION_NAME` in `.env` are set correctly (they appear in the WebSocket URL)

### Vobiz can't reach the server

- Most common: cloud provider firewall blocking ports 80/443 (Azure NSG, AWS Security Groups, etc.)
- Test: `curl -s -I http://your-domain.com` from another machine
- Check: VPS provider dashboard → Firewall/Security Groups
- Verify the VPS public IP matches the DNS A record: `curl -s ifconfig.me`

### CORS errors from frontend

- Add the frontend domain to `allowed_origins` in `server.py` (line ~214)
- Restart the backend: `sudo systemctl restart vobiz-pipecat`
- Use `https://*.vercel.app` to allow all Vercel preview deployments

---

## Architecture Summary

```
User Browser → Vercel (Frontend) → HTTPS → VPS (Backend)
                                           ↓
                                    nginx (443) → Uvicorn (7860)
                                           ↓
                                    server.py (FastAPI)
                                           ↓
                                    bot_live.py (Pipecat Pipeline)
                                    Gemini 3.1 Flash Live (STT + LLM + TTS)
                                           ↓
                                    WebSocket → Vobiz → Phone Network
```

### Key Files

| File | Purpose |
|------|---------|
| `server.py` | FastAPI server - HTTP endpoints, WebSocket handler |
| `bot.py` | Pipecat voice agent pipeline (cascaded STT→LLM→TTS) |
| `bot_live.py` | Live bot using Gemini 3.1 Flash (STT + LLM + TTS in one model) |
| `call_manager.py` | Call state management |
| `call_store.py` | Supabase persistence for calls/campaigns |
| `auth_backend.py` | Supabase JWT verification |
| `supabase_storage.py` | Recording upload to Supabase Storage |
| `csv_parser.py` | CSV/Excel recipient parsing |
| `campaign_runner.py` | Automated campaign execution |
| `transcriber.py` | Post-call transcription |
| `frontend/` | React + Vite dashboard |
