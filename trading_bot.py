import yfinance as yf
import pandas_ta as ta
import os
import pandas as pd
from linebot import LineBotApi
from linebot.models import TextSendMessage

# 1. ตั้งค่าระบบ (ดึงความลับจาก GitHub Secrets)
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
        # ดึงข้อมูลย้อนหลัง 1 ปี (ใช้ auto_adjust เพื่อลดปัญหาหัวตารางซ้อน)
        df = yf.download(ticker, period="1y", interval="1d", progress=False, auto_adjust=True)
        
        if df.empty or len(df) < 200:
            return

        # คำนวณอินดิเคเตอร์
        df['EMA20'] = ta.ema(df['Close'], length=20)
        df['EMA200'] = ta.ema(df['Close'], length=200)
        df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)

        # เช็คว่าแถวล่าสุดมีค่าครบไหม (ป้องกัน NoneType Error)
        last_row = df.iloc[-1]
        if pd.isna(last_row['EMA20']) or pd.isna(last_row['EMA200']) or pd.isna(last_row['Close']):
            return

        # ดึงค่าออกมาเป็นตัวเลขทศนิยมเดี่ยวๆ
        current_price = float(last_row['Close'])
        ema20 = float(last_row['EMA20'])
        ema200 = float(last_row['EMA200'])
        atr = float(last_row['ATR']) if not pd.isna(last_row['ATR']) else 0

        # --- กลยุทธ์ Bullish Pullback (เน้นความเสี่ยงต่ำ) ---
        # 1. ราคาต้องอยู่เหนือ EMA 200 (แนวโน้มขาขึ้นใหญ่)
        # 2. ราคาต้องอยู่ใกล้เส้น EMA 20 (จุดย่อตัวเพื่อเข้าซื้อ)
        
        if current_price > ema200:
            # ถ้าราคาปัจจุบัน ต่ำกว่า EMA20 เล็กน้อย หรือ สูงกว่าไม่เกิน 1.5%
            if current_price <= (ema20 * 1.015) and current_price >= (ema20 * 0.985):
                stop_loss = current_price - (2 * atr)
                
                msg = (f"\n🎯 [Signal Found] {ticker}\n"
                       f"Price: {current_price:.2f}\n"
                       f"EMA20: {ema20:.2f}\n"
                       f"Stop Loss: {stop_loss:.2f}\n"
                       f"Trend: Bullish (Above EMA200)")
                
                send_to_line(msg)
                print(f"✅ Found signal for {ticker}")

    except Exception as e:
        print(f"❌ Error checking {ticker}: {str(e)}")

# รายชื่อหุ้น (Top 100 US + หุ้นไทย)
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
