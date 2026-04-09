import yfinance as yf
import pandas_ta as ta
import os
from linebot import LineBotApi
from linebot.models import TextSendMessage

# 1. ดึงรหัสลับจาก GitHub Secrets (ที่เราตั้งค่าไว้ก่อนหน้านี้)
CHANNEL_ACCESS_TOKEN = os.getenv('CHANNEL_ACCESS_TOKEN')
USER_ID = os.getenv('USER_ID')

# ตรวจสอบว่ามี Token หรือไม่
if not CHANNEL_ACCESS_TOKEN or not USER_ID:
    print("Error: Missing LINE_ACCESS_TOKEN or LINE_USER_ID in Secrets")
    exit()

line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)

def send_to_line(message):
    try:
        line_bot_api.push_message(USER_ID, TextSendMessage(text=message))
        print(f"Message sent: {message}")
    except Exception as e:
        print(f"LINE Error: {e}")

def check_trade_signal(ticker):
    try:
        # ดึงข้อมูลย้อนหลัง 1 ปี (แท่งวัน)
        df = yf.download(ticker, period="1y", interval="1d", progress=False)
        if len(df) < 200: return
        
        # คำนวณอินดิเคเตอร์ที่คุยกันไว้ (ความเสี่ยงต่ำ)
        df['EMA20'] = ta.ema(df['Close'], length=20)
        df['EMA200'] = ta.ema(df['Close'], length=200)
        df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)
        
        last_price = df['Close'].iloc[-1]
        ema20 = df['EMA20'].iloc[-1]
        ema200 = df['EMA200'].iloc[-1]
        atr = df['ATR'].iloc[-1]

        # 🟢 เงื่อนไขการซื้อ: ขาขึ้น (เหนือ EMA200) และราคาย่อมาหาเส้น EMA20
        if last_price > ema200 and last_price <= ema20 * 1.01:
            stop_loss = last_price - (2 * atr)
            shares = int(50000 / last_price) # สมมติงบไม้ละ 50,000 บาท
            msg = (f"\n🎯 [สัญญาณซื้อ] {ticker}\n"
                   f"ราคา: {last_price:.2f} บาท\n"
                   f"แนะนำซื้อ: {shares:,} หุ้น\n"
                   f"จุดตัดขาดทุน (SL): {stop_loss:.2f} บาท")
            send_to_line(msg)
            
        # 🔴 เงื่อนไขการขาย: ราคาหลุดเส้น EMA20
        elif last_price < ema20:
            # เพื่อไม่ให้เตือนพร่ำเพรื่อ คุณอาจจะเช็คเฉพาะตัวที่คุณมีในพอร์ต
            # ในที่นี้ให้ระบบเตือนแจ้งสถานะแนวโน้มปัจจุบัน
            print(f"{ticker} is currently in a down-trend (below EMA20)")

    except Exception as e:
        print(f"Error checking {ticker}: {e}")

# รายชื่อหุ้นที่คุณสนใจ (เปลี่ยนหรือเพิ่มได้ตามต้องการ)
my_watchlist = ["PTT.BK", "CPALL.BK", "ADVANC.BK", "GULF.BK", "AOT.BK", "KBANK.BK"]

if __name__ == "__main__":
    print("Starting stock scan...")
    for stock in my_watchlist:
        check_trade_signal(stock)
    print("Scan completed.")
