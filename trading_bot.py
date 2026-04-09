import yfinance as yf
import pandas_ta as ta
import os
import pandas as pd
from linebot import LineBotApi
from linebot.models import TextSendMessage

# 1. ตั้งค่าระบบ
CHANNEL_ACCESS_TOKEN = os.getenv('CHANNEL_ACCESS_TOKEN')
USER_ID = os.getenv('USER_ID')

def send_to_line(message):
    try:
        line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
        line_bot_api.push_message(USER_ID, TextSendMessage(text=message))
    except Exception as e:
        print(f"LINE Error: {e}")

def check_trade_signal(ticker):
    try:
        # ดึงข้อมูล และบังคับให้เหลือมิติเดียวด้วย .squeeze()
        df = yf.download(ticker, period="1y", interval="1d", progress=False)
        
        if df.empty or len(df) < 200:
            return

        # แก้ไขปัญหา Multi-index: บังคับให้หัวตารางเหลือชั้นเดียว
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # คำนวณอินดิเคเตอร์
        df['EMA20'] = ta.ema(df['Close'], length=20)
        df['EMA200'] = ta.ema(df['Close'], length=200)
        df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)

        # ดึงแถวล่าสุดออกมา และทำให้มั่นใจว่าเป็นค่าเดี่ยวด้วย .item()
        last_price = float(df['Close'].iloc[-1])
        ema20 = float(df['EMA20'].iloc[-1])
        ema200 = float(df['EMA200'].iloc[-1])
        atr = float(df['ATR'].iloc[-1]) if not pd.isna(df['ATR'].iloc[-1]) else 0

        # --- กลยุทธ์ Bullish Pullback ---
        if last_price > ema200: # ขาขึ้น
            # ราคาอยู่ใกล้ EMA20 ในระยะ +/- 1.5%
            if (ema20 * 0.985) <= last_price <= (ema20 * 1.015):
                stop_loss = last_price - (2 * atr)
                msg = (f"\n🎯 [Signal] {ticker}\n"
                       f"Price: {last_price:.2f}\n"
                       f"SL: {stop_loss:.2f}\n"
                       f"Trend: Above EMA200")
                send_to_line(msg)
                print(f"✅ Found signal for {ticker}")

    except Exception as e:
        print(f"❌ Error checking {ticker}: {str(e)}")

# รายชื่อหุ้น (Top 100 US + Thai)
my_watchlist = [
    "AAPL", "ABBV", "ABT", "ACN", "ADBE", "AMAT", "AMD", "AMGN", "AMT", "AMZN",
    "AVGO", "AXP", "BA", "BAC", "BK", "BKNG", "BLK", "BMY", "C", "CAT",
    "CL", "CMCSA", "COF", "COP", "COST", "CRM", "CSCO", "CVS", "CVX", "DE",
    "DHR", "DIS", "DUK", "EMR", "FDX", "GD", "GE", "GEV", "GILD", "GM",
    "GOOG", "GOOGL", "GS", "HD", "HON", "IBM", "INTC", "INTU", "ISRG", "JNJ",
    "JPM", "KO", "LIN", "LLY", "LMT", "LOW", "LRCX", "MA", "MCD", "MDLZ",
    "MDT", "META", "MMM", "MO", "MRK", "MS", "MSFT", "NEE", "NFLX", "NKE",
    "NVDA", "ORCL", "PEP", "PFE", "PG", "PM", "PYPL", "QCOM", "RTX", "SBUX",
    "SCHW", "SO", "SPGI", "T", "TGT", "TJX", "TMUS", "TSLA", "TXN", "UNH",
    "UNP", "UPS", "USB", "V", "VZ", "WFC", "WMT", "XOM",
    "PTT.BK", "CPALL.BK", "ADVANC.BK", "GULF.BK", "AOT.BK"
]

if __name__ == "__main__":
    print(f"🚀 Starting scan for {len(my_watchlist)} stocks...")
    for stock in my_watchlist:
        check_trade_signal(stock)
    print("✅ Scan completed successfully.")
