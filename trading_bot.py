import yfinance as yf
import pandas_ta as ta
import os
from linebot import LineBotApi
from linebot.models import TextSendMessage

# 1. ตั้งค่า LINE (ดึงจาก Secrets)
CHANNEL_ACCESS_TOKEN = os.getenv('CHANNEL_ACCESS_TOKEN')
USER_ID = os.getenv('USER_ID')
line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)

def send_to_line(message):
    try:
        line_bot_api.push_message(USER_ID, TextSendMessage(text=message))
    except Exception as e:
        print(f"LINE Error: {e}")

def check_trade_signal(ticker):
    try:
        # ดึงข้อมูลย้อนหลัง 1 ปี
        df = yf.download(ticker, period="1y", interval="1d", progress=False)
        if len(df) < 200: return
        
        # คำนวณอินดิเคเตอร์
        df['EMA20'] = ta.ema(df['Close'], length=20)
        df['EMA200'] = ta.ema(df['Close'], length=200)
        df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)
        
        # แก้ไขจุดนี้: ใช้ .iloc[-1] และ .item() เพื่อดึงค่าตัวเลขออกมาให้ชัวร์
        last_price = float(df['Close'].iloc[-1].iloc[0] if hasattr(df['Close'].iloc[-1], '__len__') else df['Close'].iloc[-1])
        ema20 = float(df['EMA20'].iloc[-1])
        ema200 = float(df['EMA200'].iloc[-1])
        atr = float(df['ATR'].iloc[-1])

        # 🟢 เงื่อนไขการซื้อ: ขาขึ้น และ ราคาย่อมาใกล้เส้น EMA20
        if last_price > ema200 and last_price <= (ema20 * 1.01):
            stop_loss = last_price - (2 * atr)
            msg = (f"\n🎯 [Signal] {ticker}\n"
                   f"Price: {last_price:.2f}\n"
                   f"Stop Loss: {stop_loss:.2f}")
            send_to_line(msg)
            print(f"Found signal for {ticker}")
            
    except Exception as e:
        print(f"Error checking {ticker}: {e}")
my_watchlist = [
    # US Stocks (S&P 100)
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
    # Thai Stocks
    "PTT.BK", "CPALL.BK", "ADVANC.BK", "GULF.BK", "AOT.BK"
]

if __name__ == "__main__":
    print(f"Scanning {len(my_watchlist)} stocks...")
    for stock in my_watchlist:
        check_trade_signal(stock)
    print("Scan completed.")
