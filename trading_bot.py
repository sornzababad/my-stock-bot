import yfinance as yf
import pandas as pd
import pandas_ta as ta
import requests
import os

# ตั้งค่า LINE
LINE_ACCESS_TOKEN = os.getenv('LINE_ACCESS_TOKEN')
LINE_USER_ID = os.getenv('LINE_USER_ID')

def send_to_line(message):
    url = 'https://api.line.me/v2/bot/message/push'
    headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {LINE_ACCESS_TOKEN}'}
    data = {'to': LINE_USER_ID, 'messages': [{'type': 'text', 'text': message}]}
    requests.post(url, headers=headers, json=data)

def check_trade_signal(ticker):
    try:
        df = yf.download(ticker, period="1y", interval="1d", progress=False)
        if df.empty or len(df) < 200: return None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df['EMA20'] = ta.ema(df['Close'], length=20)
        df['EMA200'] = ta.ema(df['Close'], length=200)
        df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)

        last_row = df.iloc[-1]
        prev_row = df.iloc[-2]
        
        current_price = float(last_row['Close'])
        atr = float(last_row['ATR']) if not pd.isna(last_row['ATR']) else 0

        # --- เช็ค Golden Cross ---
        if (prev_row['EMA20'] < prev_row['EMA200']) and (last_row['EMA20'] > last_row['EMA200']):
            sl = current_price - (2 * atr)
            tp = current_price + (4 * atr)
            return f"🚀 [GOLDEN CROSS] {ticker} @ {current_price:.2f} (Target: {tp:.2f}, SL: {sl:.2f})"

        # --- เช็ค Death Cross ---
        elif (prev_row['EMA20'] > prev_row['EMA200']) and (last_row['EMA20'] < last_row['EMA200']):
            return f"💀 [DEATH CROSS] {ticker} @ {current_price:.2f} (ควรขาย/ลดพอร์ต)"

        return None
    except Exception as e:
        print(f"Error {ticker}: {e}")
        return None

# รายชื่อหุ้น
stocks = ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA', 'CPALL.BK', 'AOT.BK', 'PTT.BK']
found_signals = []

for s in stocks:
    signal = check_trade_signal(s)
    if signal:
        found_signals.append(signal)

# --- ส่วนที่เพิ่มใหม่: สรุปผลการรัน ---
if found_signals:
    # ถ้าเจอสัญญาณ ให้ส่งแยกตัวละครโทรศัพท์เด้งหลายรอบ
    for msg in found_signals:
        send_to_line(msg)
else:
    # ถ้าไม่เจอเลย ให้ส่งบอกว่ารันเสร็จแล้วแต่ไม่พบอะไร
    stock_list_str = ", ".join(stocks)
    send_to_line(f"✅ บอทแสกนเสร็จแล้ว\nหุ้นที่ตรวจสอบ: {stock_list_str}\n\nสถานะ: 😴 ยังไม่พบสัญญาณ Golden/Death Cross ในวันนี้ครับ")
