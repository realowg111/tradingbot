#!/usr/bin/env bash
# ============================================================================
# Trading Bot - VPS Installation Script (Ubuntu 22.04 / Debian 12)
# ============================================================================
# This script automates the deployment of the Trading Bot stack on a VPS.
# It installs Docker, MongoDB, Python, Node.js, and sets up the bot as a
# systemd service with automatic restart and basic security hardening.
#
# USAGE: bash install.sh
# ============================================================================

set -euo pipefail

echo "▶ Trading Bot VPS Installer"
echo "============================"

# --- Variables ---
APP_DIR="/opt/trading-bot"
SERVICE_USER="botuser"
PY_VERSION="3.11"

# --- System update ---
echo "▶ Mise à jour du système..."
apt-get update -y
apt-get upgrade -y

# --- Essentials ---
echo "▶ Installation des paquets essentiels..."
apt-get install -y curl git build-essential ufw fail2ban htop ca-certificates gnupg \
  software-properties-common python3 python3-pip python3-venv

# --- Node.js (for any auxiliary tooling) ---
if ! command -v node &> /dev/null; then
  echo "▶ Installation Node.js 20 LTS..."
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
  apt-get install -y nodejs
fi

# --- MongoDB 7 ---
if ! command -v mongod &> /dev/null; then
  echo "▶ Installation MongoDB 7..."
  curl -fsSL https://pgp.mongodb.com/server-7.0.asc | gpg -o /usr/share/keyrings/mongodb-server-7.0.gpg --dearmor
  echo "deb [ arch=amd64,arm64 signed-by=/usr/share/keyrings/mongodb-server-7.0.gpg ] https://repo.mongodb.org/apt/ubuntu jammy/mongodb-org/7.0 multiverse" | tee /etc/apt/sources.list.d/mongodb-org-7.0.list
  apt-get update -y
  apt-get install -y mongodb-org
  systemctl enable --now mongod
fi

# --- Create service user ---
if ! id -u "$SERVICE_USER" &> /dev/null; then
  echo "▶ Création utilisateur service '$SERVICE_USER'..."
  useradd -m -s /bin/bash "$SERVICE_USER"
fi

# --- App directory ---
mkdir -p "$APP_DIR"
chown -R "$SERVICE_USER:$SERVICE_USER" "$APP_DIR"

# --- Clone or sync code (placeholder) ---
echo "▶ Code application : copiez votre dossier backend dans $APP_DIR/backend"
echo "  (ou utilisez git clone) Exemple :"
echo "  cd $APP_DIR && git clone <votre-repo> backend"

# --- Python venv + deps (only if backend exists) ---
if [ -d "$APP_DIR/backend" ]; then
  sudo -u "$SERVICE_USER" python3 -m venv "$APP_DIR/venv"
  sudo -u "$SERVICE_USER" "$APP_DIR/venv/bin/pip" install --upgrade pip
  sudo -u "$SERVICE_USER" "$APP_DIR/venv/bin/pip" install -r "$APP_DIR/backend/requirements.txt"
fi

# --- systemd service ---
echo "▶ Création service systemd 'trading-bot'..."
cat > /etc/systemd/system/trading-bot.service <<EOF
[Unit]
Description=Trading Bot Backend (FastAPI + Bot Loop)
After=network.target mongod.service
Wants=mongod.service

[Service]
Type=simple
User=$SERVICE_USER
WorkingDirectory=$APP_DIR/backend
Environment=PYTHONPATH=$APP_DIR/backend
ExecStart=$APP_DIR/venv/bin/uvicorn server:app --host 0.0.0.0 --port 8001 --workers 1
Restart=always
RestartSec=5
StandardOutput=append:/var/log/trading-bot.log
StandardError=append:/var/log/trading-bot.err.log

# Hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable trading-bot.service

# --- Firewall (UFW) ---
echo "▶ Configuration UFW..."
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
# Backend NOT exposed externally - serve via nginx reverse proxy
# ufw allow 8001/tcp
ufw --force enable

# --- Fail2ban (SSH protection) ---
systemctl enable --now fail2ban

# --- Nginx reverse proxy (optional, requires nginx package) ---
if ! command -v nginx &> /dev/null; then
  apt-get install -y nginx
fi
cat > /etc/nginx/sites-available/trading-bot <<'NGINX'
server {
    listen 80;
    server_name _;

    location /api/ {
        proxy_pass http://127.0.0.1:8001;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }

    location / {
        return 200 'Trading Bot is running. API at /api/';
        add_header Content-Type text/plain;
    }
}
NGINX
ln -sf /etc/nginx/sites-available/trading-bot /etc/nginx/sites-enabled/trading-bot
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx || echo "⚠️ Nginx config check failed - skip reload"

# --- Monitoring (basic with htop / journalctl) ---
echo "▶ Monitoring : journalctl -u trading-bot -f"

# --- Cron job for auto-restart safety (optional) ---
echo "0 5 * * * systemctl restart trading-bot.service" > /tmp/tradingbot-cron
crontab -u "$SERVICE_USER" /tmp/tradingbot-cron 2>/dev/null || true

# --- Done ---
echo ""
echo "============================================"
echo "✅ Installation terminée."
echo ""
echo "Prochaines étapes :"
echo "  1. Déposez votre code backend dans : $APP_DIR/backend/"
echo "  2. Créez le fichier .env : $APP_DIR/backend/.env"
echo "     (incluez MONGO_URL, DB_NAME, JWT_SECRET_KEY, AES_SECRET_KEY_BASE64,"
echo "      ADMIN_EMAIL, ADMIN_PASSWORD)"
echo "  3. Démarrez le service : systemctl start trading-bot"
echo "  4. Vérifiez les logs : journalctl -u trading-bot -f"
echo "  5. Status : systemctl status trading-bot"
echo ""
echo "🔒 Sécurité activée :"
echo "  - UFW (firewall) : SSH + 80/443 uniquement"
echo "  - Fail2ban (anti brute-force SSH)"
echo "  - Nginx reverse proxy → /api/ proxy vers :8001"
echo "  - systemd avec Restart=always et hardening (NoNewPrivileges, PrivateTmp)"
echo "  - Cron de redémarrage quotidien à 5h00"
echo ""
echo "💡 Pour HTTPS : installer certbot et générer le certificat :"
echo "   apt install certbot python3-certbot-nginx && certbot --nginx"
echo "============================================"
