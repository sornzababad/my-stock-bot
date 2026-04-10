import yfinance as yf
import pandas as pd
import requests
import os

# --- 1. การเชื่อมต่อ LINE ---
LINE_ACCESS_TOKEN = os.getenv('CHANNEL_ACCESS_TOKEN')
LINE_USER_ID = os.getenv('USER_ID')

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

        # --- คำนวณเองแบบไม่ง้อ Library เสริม ---
        # EMA
        df['EMA20'] = df['Close'].ewm(span=20, adjust=False).mean()
        df['EMA200'] = df['Close'].ewm(span=200, adjust=False).mean()
        
        # RSI
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))

        # ATR (เพื่อหาจุด Stop Loss)
        high_low = df['High'] - df['Low']
        high_close = abs(df['High'] - df['Close'].shift())
        low_close = abs(df['Low'] - df['Close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = ranges.max(axis=1)
        df['ATR'] = true_range.rolling(14).mean()

        last = df.iloc[-1]
        prev = df.iloc[-2]
        curr_price = float(last['Close'])
        atr = float(last['ATR']) if not pd.isna(last['ATR']) else 0

        # --- ตรรกะ Moderate ---
        if (prev['EMA20'] < prev['EMA200']) and (last['EMA20'] > last['EMA200']):
            if 50 < last['RSI'] < 70:
                sl = curr_price - (1.5 * atr)
                tp = curr_price + (3 * atr)
                return (f"🔵 [MODERATE BUY] {ticker}\nราคา: {curr_price:.2f}\nRSI: {last['RSI']:.1f}\nเป้ากำไร: {tp:.2f} / คัดขาดทุน: {sl:.2f}")

        elif (prev['EMA20'] > prev['EMA200']) and (last['EMA20'] < last['EMA200']):
            return f"⚠️ [SELL SIGNAL] {ticker}\nราคา: {curr_price:.2f}\nสถานะ: ตัดลง ควรขายครับ"

        return None
    except:
        return None

# --- รายชื่อหุ้นชุดใหญ่ (150+ ตัว) ---
stocks = [
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'TSLA', 'NVDA', 'AVGO', 'ORCL', 'ADBE',
    'NFLX', 'AMD', 'CRM', 'INTC', 'QCOM', 'TXN', 'AMAT', 'MU', 'LRCX', 'PANW',
    'V', 'MA', 'JPM', 'BAC', 'WFC', 'GS', 'MS', 'BLK', 'AXP', 'PYPL',
    'WMT', 'COST', 'TGT', 'HD', 'LOW', 'NKE', 'SBUX', 'MCD', 'KO', 'PEP',
    'PFE', 'JNJ', 'UNH', 'ABBV', 'MRK', 'LLY', 'TMO', 'DHR', 'ISRG', 'AMGN',
    'XOM', 'CVX', 'COP', 'SLB', 'EOG', 'BA', 'CAT', 'DE', 'GE', 'MMM',
    'SPY', 'VOO', 'QQQ', 'DIA', 'VTI', 'SCHD', 'VIG', 'VYM', 'XLK', 'XLF', 'SOXX',
    'PTT.BK', 'PTTEP.BK', 'TOP.BK', 'OR.BK', 'BCP.BK', 'IRPC.BK', 'PTTGC.BK', 'IVL.BK',
    'CPALL.BK', 'CPAXT.BK', 'BJC.BK', 'HMPRO.BK', 'GLOBAL.BK', 'CRC.BK', 'CPN.BK',
    'AOT.BK', 'BA.BK', 'BEM.BK', 'BTS.BK', 'WHA.BK', 'AMATA.BK',
    'ADVANC.BK', 'TRUE.BK', 'INTUCH.BK', 'DELTA.BK', 'HANA.BK', 'KCE.BK',
    'KBANK.BK', 'SCB.BK', 'BBL.BK', 'KTB.BK', 'TTB.BK', 'TISCO.BK', 'KKP.BK',
    'BDMS.BK', 'BH.BK', 'BCH.BK', 'CHG.BK', 'GULF.BK', 'GPSC.BK', 'BGRIM.BK',
    'EA.BK', 'EGCO.BK', 'RATCH.BK', 'BANPU.BK', 'SCC.BK', 'SCGP.BK', 'CBG.BK',
    'OSP.BK', 'TU.BK', 'MINT.BK', 'LH.BK', 'AP.BK', 'SIRI.BK'
]

found_signals = []
for s in stocks:
    signal = check_trade_signal(s)
    if signal: found_signals.append(signal)

if found_signals:
    for msg in found_signals: send_to_line(msg)
else:
    send_to_line(f"✅ บอทแสกนหุ้น {len(stocks)} ตัวเสร็จสิ้น (17:00)\nสถานะ: 😴 ยังไม่มีสัญญาณใหม่ครับ")
