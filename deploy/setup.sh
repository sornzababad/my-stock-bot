#!/bin/bash
# Deploy stock-bot on existing DigitalOcean VPS (push-only, no webhook server needed)
# Run as root: bash setup.sh

set -e
REPO_URL="https://github.com/sornzababad/my-stock-bot.git"
APP_DIR="/home/botuser/my-stock-bot"

echo "=== Stock Bot VPS Setup ==="

# ── 1. Install packages ───────────────────────────────────────────
apt-get update -qq
apt-get install -y python3-venv python3-pip git

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
    yfinance pandas requests "anthropic>=0.25.0" \
    flask gspread google-auth

# ── 4. Create .env if not exists ─────────────────────────────────
if [ ! -f "$APP_DIR/.env" ]; then
    cp "$APP_DIR/deploy/.env.example" "$APP_DIR/.env"
    chown botuser:botuser "$APP_DIR/.env"
    chmod 600 "$APP_DIR/.env"
fi

echo ""
echo "⚠️  ใส่ secrets ก่อน แล้วค่อยรัน step ต่อไป:"
echo "    nano $APP_DIR/.env"
echo ""
read -p "กด Enter เมื่อใส่ .env เสร็จแล้ว..."

# ── 5. Cron jobs ─────────────────────────────────────────────────
cat > /etc/cron.d/stock-bot << 'EOF'
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin

# Daily close scanners (UTC)
5 10 * * 1-5 botuser set -a; source /home/botuser/my-stock-bot/.env; set +a; cd /home/botuser/my-stock-bot && venv/bin/python trading_bot.py --market thai >> /var/log/stock-bot.log 2>&1
5 21 * * 1-5 botuser set -a; source /home/botuser/my-stock-bot/.env; set +a; cd /home/botuser/my-stock-bot && venv/bin/python trading_bot.py --market us   >> /var/log/stock-bot.log 2>&1

# Intraday scanner (every 1h during market hours, UTC)
0 2-10  * * 1-5 botuser set -a; source /home/botuser/my-stock-bot/.env; set +a; cd /home/botuser/my-stock-bot && venv/bin/python intraday_scanner.py >> /var/log/stock-bot.log 2>&1
0 14-21 * * 1-5 botuser set -a; source /home/botuser/my-stock-bot/.env; set +a; cd /home/botuser/my-stock-bot && venv/bin/python intraday_scanner.py >> /var/log/stock-bot.log 2>&1

# Pre-market news (UTC)
30 1  * * 1-5 botuser set -a; source /home/botuser/my-stock-bot/.env; set +a; cd /home/botuser/my-stock-bot && venv/bin/python premarket_news.py thai >> /var/log/stock-bot.log 2>&1
30 13 * * 1-5 botuser set -a; source /home/botuser/my-stock-bot/.env; set +a; cd /home/botuser/my-stock-bot && venv/bin/python premarket_news.py us   >> /var/log/stock-bot.log 2>&1

# Weekly summary Friday (UTC)
30 10 * * 5 botuser set -a; source /home/botuser/my-stock-bot/.env; set +a; cd /home/botuser/my-stock-bot && venv/bin/python weekly_summary.py >> /var/log/stock-bot.log 2>&1
EOF

touch /var/log/stock-bot.log
chown botuser:botuser /var/log/stock-bot.log

echo "[cron] Cron jobs installed"
echo ""
echo "=== Setup เสร็จแล้ว! ==="
echo "ทดสอบ: sudo -u botuser bash -c 'set -a; source /home/botuser/my-stock-bot/.env; set +a; cd /home/botuser/my-stock-bot && venv/bin/python trading_bot.py --market thai'"
echo "ดู log:  tail -f /var/log/stock-bot.log"
