import yfinance as yf
import pandas as pd
import pandas_ta as ta
import requests
import os

# ตั้งค่า LINE (ดึงจาก GitHub Secrets)
LINE_ACCESS_TOKEN = os.getenv('LINE_ACCESS_TOKEN')
LINE_USER_ID = os.getenv('LINE_USER_ID')

def send_to_line(message):
    url = 'https://api.line.me/v2/bot/message/push'
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {LINE_ACCESS_TOKEN}'
    }
    data = {
        'to': LINE_USER_ID,
        'messages': [{'type': 'text', 'text': message}]
    }
    response = requests.post(url, headers=headers, json=data)
    return response.status_code

def check_trade_signal(ticker):
    try:
        # 1. ดึงข้อมูล (ใช้ระยะเวลา 1 ปีเพื่อให้เส้น EMA200 นิ่งพอ)
        df = yf.download(ticker, period="1y", interval="1d", progress=False)
        if df.empty or len(df) < 200: return

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # 2. คำนวณเส้น EMA 20 และ 200
        df['EMA20'] = ta.ema(df['Close'], length=20)
        df['EMA200'] = ta.ema(df['Close'], length=200)
        df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)

        # 3. ดึงข้อมูล "วันนี้" และ "เมื่อวาน" มาเปรียบเทียบ
        last_row = df.iloc[-1]
        prev_row = df.iloc[-2]
        
        current_price = float(last_row['Close'])
        atr = float(last_row['ATR']) if not pd.isna(last_row['ATR']) else 0

        # --- 🚀 สัญญาณตัดขึ้น (Golden Cross) ---
        # เมื่อวาน 20 < 200 และ วันนี้ 20 > 200
        if (prev_row['EMA20'] < prev_row['EMA200']) and (last_row['EMA20'] > last_row['EMA200']):
            sl = current_price - (2 * atr)
            tp = current_price + (4 * atr)
            msg = (f"\n🚀 [GOLDEN CROSS] {ticker}\n"
                   f"Price: {current_price:.2f}\n"
                   f"Signal: เส้นสั้นตัดขึ้น (เพิ่งเปลี่ยนเป็นขาขึ้นวันนี้)\n"
                   f"Target Profit: {tp:.2f}\n"
                   f"Stop Loss: {sl:.2f}")
            send_to_line(msg)

        # --- 💀 สัญญาณตัดลง (Death Cross) ---
        # เมื่อวาน 20 > 200 และ วันนี้ 20 < 200
        elif (prev_row['EMA20'] > prev_row['EMA200']) and (last_row['EMA20'] < last_row['EMA200']):
            msg = (f"\n💀 [DEATH CROSS] {ticker}\n"
                   f"Price: {current_price:.2f}\n"
                   f"Signal: เส้นสั้นตัดลง (เพิ่งหลุดเป็นขาลงวันนี้)\n"
                   f"Action: พิจารณาขายทำกำไร/ลดพอร์ตครับ")
            send_to_line(msg)

    except Exception as e:
        print(f"❌ Error checking {ticker}: {str(e)}")

# รายชื่อหุ้นที่ต้องการแสกน (คุณเพิ่ม/ลดเองได้ที่นี่)
stocks = ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA', 'CPALL.BK', 'AOT.BK', 'PTT.BK']

for s in stocks:
    check_trade_signal(s)
