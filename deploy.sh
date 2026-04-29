#!/bin/bash
# Deployment setup script for Vobiz-X-Pipecat backend
set -e

DOMAIN="provaani1.progressive-digital.xyz"
VPS_IP="172.188.122.209"
PROJECT_DIR="/home/rahulm/Vobiz-X-Pipecat"
SERVICE_NAME="vobiz-pipecat"

echo "=== Vobiz-X-Pipecat Backend Deployment ==="

# Step 1: Check DNS
echo ""
echo "[1/6] Checking DNS resolution for $DOMAIN..."
DNS_IP=$(dig +short "$DOMAIN" A 2>/dev/null | head -1)

if [ "$DNS_IP" != "$VPS_IP" ]; then
    echo "❌ DNS NOT CONFIGURED!"
    echo ""
    echo "You need to add an A record in your DNS provider:"
    echo "  Type: A"
    echo "  Name: provaani1.progressive-digital.xyz"
    echo "  Value: $VPS_IP"
    echo ""
    echo "Then wait for DNS propagation (usually 1-5 minutes)."
    echo "Run this script again after DNS is configured."
    exit 1
fi
echo "✅ DNS resolved to $DNS_IP"

# Step 2: Check .env file
echo ""
echo "[2/6] Checking .env file..."
if [ ! -f "$PROJECT_DIR/.env" ]; then
    echo "❌ .env file not found!"
    echo "Copy env.example to .env and fill in your credentials:"
    echo "  cp $PROJECT_DIR/env.example $PROJECT_DIR/.env"
    echo "  nano $PROJECT_DIR/.env"
    exit 1
fi
echo "✅ .env file found"

# Step 3: Install SSL certificate
echo ""
echo "[3/6] Installing SSL certificate..."
sudo certbot certonly --webroot -w /var/www/certbot -d "$DOMAIN" --non-interactive --agree-tos --email rahulm@example.com --force-renewal 2>/dev/null || {
    echo "Attempting SSL certificate with certbot..."
    sudo certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --email rahulm@example.com --redirect 2>/dev/null || {
        echo "⚠️ Certbot failed. You may need to run manually:"
        echo "  sudo certbot --nginx -d $DOMAIN"
    }
}

# Step 4: Update nginx with full config
echo ""
echo "[4/6] Configuring nginx..."
sudo tee /etc/nginx/sites-available/provaani1 > /dev/null << 'NGINX_EOF'
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}

upstream vobiz_backend {
    server 127.0.0.1:7860;
}

server {
    listen 80;
    server_name provaani1.progressive-digital.xyz;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 301 https://$host$request_uri;
    }
}

server {
    listen 443 ssl http2;
    server_name provaani1.progressive-digital.xyz;

    ssl_certificate /etc/letsencrypt/live/provaani1.progressive-digital.xyz/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/provaani1.progressive-digital.xyz/privkey.pem;

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
NGINX_EOF

sudo ln -sf /etc/nginx/sites-available/provaani1 /etc/nginx/sites-enabled/provaani1
sudo nginx -t && sudo systemctl reload nginx
echo "✅ Nginx configured"

# Step 5: Install systemd service
echo ""
echo "[5/6] Installing systemd service..."
sudo cp "$PROJECT_DIR/vobiz-pipecat.service" /etc/systemd/system/$SERVICE_NAME.service
sudo systemctl daemon-reload
sudo systemctl enable $SERVICE_NAME
echo "✅ Systemd service installed"

# Step 6: Create recordings directory
echo ""
echo "[6/6] Setting up directories..."
mkdir -p "$PROJECT_DIR/recordings"
echo "✅ Directories ready"

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo "1. Start the service: sudo systemctl start $SERVICE_NAME"
echo "2. Check logs: sudo journalctl -u $SERVICE_NAME -f"
echo "3. Test: curl https://$DOMAIN/answer"
echo ""
