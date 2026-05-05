#!/bin/bash
# Run this script on the VPS as root:
#   bash setup.sh YOUR_DOMAIN (e.g. bash setup.sh stockbot.example.com)

set -e
DOMAIN=${1:-""}
REPO_URL="https://github.com/sornzababad/my-stock-bot.git"
APP_DIR="/home/botuser/my-stock-bot"
SERVICE_NAME="stock-bot"

echo "=== Stock Bot VPS Setup ==="

# ── 1. Install system packages ────────────────────────────────────
apt-get update -qq
apt-get install -y python3-venv python3-pip nginx certbot python3-certbot-nginx git

# ── 2. Clone / update repo ────────────────────────────────────────
if [ -d "$APP_DIR/.git" ]; then
    echo "[git] Pulling latest..."
    sudo -u botuser git -C "$APP_DIR" pull
else
    echo "[git] Cloning repo..."
    sudo -u botuser git clone "$REPO_URL" "$APP_DIR"
fi

# ── 3. Python venv + dependencies ────────────────────────────────
echo "[python] Setting up venv..."
sudo -u botuser python3 -m venv "$APP_DIR/venv"
sudo -u botuser "$APP_DIR/venv/bin/pip" install -q --upgrade pip
sudo -u botuser "$APP_DIR/venv/bin/pip" install -q \
    flask gunicorn yfinance pandas requests \
    "anthropic>=0.25.0" gspread google-auth

# ── 4. Create .env if not exists ─────────────────────────────────
if [ ! -f "$APP_DIR/.env" ]; then
    cp "$APP_DIR/deploy/.env.example" "$APP_DIR/.env"
    chown botuser:botuser "$APP_DIR/.env"
    chmod 600 "$APP_DIR/.env"
    echo ""
    echo "⚠️  กรุณาแก้ไขไฟล์ .env ก่อน:"
    echo "    nano $APP_DIR/.env"
    echo ""
fi

# ── 5. Systemd service ───────────────────────────────────────────
cp "$APP_DIR/deploy/stock-bot.service" /etc/systemd/system/stock-bot.service
systemctl daemon-reload
systemctl enable stock-bot
systemctl restart stock-bot
echo "[service] stock-bot.service started"

# ── 6. Cron jobs (replace GitHub Actions) ────────────────────────
CRON_FILE="/etc/cron.d/stock-bot"
cat > "$CRON_FILE" << 'EOF'
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin

# Daily close scanners
5 10 * * 1-5 botuser cd /home/botuser/my-stock-bot && source .env && venv/bin/python trading_bot.py --market thai >> /var/log/stock-bot-cron.log 2>&1
5 21 * * 1-5 botuser cd /home/botuser/my-stock-bot && source .env && venv/bin/python trading_bot.py --market us >> /var/log/stock-bot-cron.log 2>&1

# Intraday scanner (every 1h during market hours)
0 2-10 * * 1-5 botuser cd /home/botuser/my-stock-bot && source .env && venv/bin/python intraday_scanner.py >> /var/log/stock-bot-cron.log 2>&1
0 14-21 * * 1-5 botuser cd /home/botuser/my-stock-bot && source .env && venv/bin/python intraday_scanner.py >> /var/log/stock-bot-cron.log 2>&1

# Pre-market news
30 1 * * 1-5 botuser cd /home/botuser/my-stock-bot && source .env && venv/bin/python premarket_news.py thai >> /var/log/stock-bot-cron.log 2>&1
30 13 * * 1-5 botuser cd /home/botuser/my-stock-bot && source .env && venv/bin/python premarket_news.py us >> /var/log/stock-bot-cron.log 2>&1

# Weekly summary (Friday)
30 10 * * 5 botuser cd /home/botuser/my-stock-bot && source .env && venv/bin/python weekly_summary.py >> /var/log/stock-bot-cron.log 2>&1
EOF
echo "[cron] Cron jobs installed"

# ── 7. Nginx + SSL ───────────────────────────────────────────────
if [ -n "$DOMAIN" ]; then
    sed "s/YOUR_DOMAIN_HERE/$DOMAIN/" "$APP_DIR/deploy/nginx-stock-bot.conf" \
        > /etc/nginx/sites-available/stock-bot
    ln -sf /etc/nginx/sites-available/stock-bot /etc/nginx/sites-enabled/stock-bot
    nginx -t && systemctl reload nginx
    echo "[nginx] Config installed for $DOMAIN"

    echo "[ssl] Getting Let's Encrypt certificate..."
    certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m admin@$DOMAIN
    echo "[ssl] Done! LINE webhook URL: https://$DOMAIN/webhook"
else
    echo ""
    echo "⚠️  ไม่ได้ระบุ domain — ข้าม nginx/SSL"
    echo "   รัน: bash setup.sh your.domain.com  เพื่อติด SSL"
    echo "   (LINE webhook ต้องการ HTTPS)"
fi

echo ""
echo "=== Setup เสร็จแล้ว! ==="
echo "ดู log: journalctl -u stock-bot -f"
echo "ดู cron log: tail -f /var/log/stock-bot-cron.log"
