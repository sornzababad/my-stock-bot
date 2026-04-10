import yfinance as yf
import pandas as pd
import pandas_ta as ta
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
        # ดึงข้อมูลย้อนหลัง 1 ปี (รายวัน)
        df = yf.download(ticker, period="1y", interval="1d", progress=False)
        if df.empty or len(df) < 200: return None

        # ปรับหัวตารางให้รองรับ yfinance เวอร์ชั่นใหม่
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # คำนวณอินดิเคเตอร์ (Moderate Risk)
        df['EMA20'] = ta.ema(df['Close'], length=20)
        df['EMA200'] = ta.ema(df['Close'], length=200)
        df['RSI'] = ta.rsi(df['Close'], length=14)
        df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)

        last = df.iloc[-1]
        prev = df.iloc[-2]
        curr_price = float(last['Close'])
        atr = float(last['ATR']) if not pd.isna(last['ATR']) else 0

        # --- ตรรกะการคัดกรองสัญญาณ ---
        # 1. Golden Cross (EMA20 ตัดขึ้นเหนือ EMA200) + กรองด้วย RSI
        if (prev['EMA20'] < prev['EMA200']) and (last['EMA20'] > last['EMA200']):
            if 50 < last['RSI'] < 70: 
                sl = curr_price - (1.5 * atr)
                tp = curr_price + (3 * atr)
                return (f"🔵 [MODERATE BUY] {ticker}\n"
                        f"ราคา: {curr_price:.2f}\n"
                        f"RSI: {last['RSI']:.1f}\n"
                        f"เป้ากำไร: {tp:.2f} / คัดขาดทุน: {sl:.2f}")

        # 2. Death Cross (EMA20 ตัดลงต่ำกว่า EMA200)
        elif (prev['EMA20'] > prev['EMA200']) and (last['EMA20'] < last['EMA200']):
            return f"⚠️ [SELL SIGNAL] {ticker}\nราคา: {curr_price:.2f}\nสถานะ: ตัดลง จบรอบขาขึ้น"

        return None
    except Exception:
        return None

# --- 2. รายชื่อหุ้นชุดใหญ่ (150+ ตัว) ---
stocks = [
    # US Tech & Blue Chip
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'TSLA', 'NVDA', 'AVGO', 'ORCL', 'ADBE',
    'NFLX', 'AMD', 'CRM', 'INTC', 'QCOM', 'TXN', 'AMAT', 'MU', 'LRCX', 'PANW',
    'V', 'MA', 'JPM', 'BAC', 'WFC', 'GS', 'MS', 'BLK', 'AXP', 'PYPL',
    'WMT', 'COST', 'TGT', 'HD', 'LOW', 'NKE', 'SBUX', 'MCD', 'KO', 'PEP',
    'PFE', 'JNJ', 'UNH', 'ABBV', 'MRK', 'LLY', 'TMO', 'DHR', 'ISRG', 'AMGN',
    'XOM', 'CVX', 'COP', 'SLB', 'EOG', 'BA', 'CAT', 'DE', 'GE', 'MMM',
    
    # ETFs (กองทุนดัชนี)
    'SPY', 'VOO', 'QQQ', 'DIA', 'VTI', 'SCHD', 'VIG', 'VYM', 'XLK', 'XLF', 'SOXX',

    # หุ้นไทย (SET50/100)
    'PTT.BK', 'PTTEP.BK', 'TOP.BK', 'OR.BK', 'BCP.BK', 'IRPC.BK', 'PTTGC.BK', 'IVL.BK',
    'CPALL.BK', 'CPAXT.BK', 'BJC.BK', 'HMPRO.BK', 'GLOBAL.BK', 'CRC.BK', 'CPN.BK',
    'AOT.BK', 'BA.BK', 'BEM.BK', 'BTS.BK', 'WHA.BK', 'AMATA.BK',
    'ADVANC.BK', 'TRUE.BK', 'INTUCH.BK', 'DELTA.BK', 'HANA.BK', 'KCE.BK',
    'KBANK.BK', 'SCB.BK', 'BBL.BK', 'KTB.BK', 'TTB.BK', 'TISCO.BK', 'KKP.BK',
    'BDMS.BK', 'BH.BK', 'BCH.BK', 'CHG.BK', 'GULF.BK', 'GPSC.BK', 'BGRIM.BK',
    'EA.BK', 'EGCO.BK', 'RATCH.BK', 'BANPU.BK', 'SCC.BK', 'SCGP.BK', 'CBG.BK',
    'OSP.BK', 'TU.BK', 'MINT.BK', 'LH.BK', 'AP.BK', 'SIRI.BK'
]

# --- 3. เริ่มรันระบบ ---
found_signals = []
for s in stocks:
    signal = check_trade_signal(s)
    if signal:
        found_signals.append(signal)

if found_signals:
    for msg in found_signals:
        send_to_line(msg)
else:
    # ข้อความสรุปรายวันตอน 17:00
    send_to_line(f"✅ บอทแสกนหุ้น {len(stocks)} ตัวเสร็จแล้ว\nสถานะ: 😴 ยังไม่พบสัญญาณซื้อ/ขายใหม่ครับ")
