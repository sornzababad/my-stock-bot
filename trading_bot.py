import yfinance as yf
import pandas as pd
import requests
import os
from datetime import datetime, timezone, timedelta

TZ_THAI = timezone(timedelta(hours=7))

# --- 1. การเชื่อมต่อ LINE ---
LINE_ACCESS_TOKEN = os.getenv('CHANNEL_ACCESS_TOKEN')
LINE_USER_ID = os.getenv('USER_ID')

def send_to_line(message):
    if not LINE_ACCESS_TOKEN or not LINE_USER_ID:
        print(f"[ERROR] Missing secrets: TOKEN={'SET' if LINE_ACCESS_TOKEN else 'MISSING'}, USER_ID={'SET' if LINE_USER_ID else 'MISSING'}")
        return False

    url = 'https://api.line.me/v2/bot/message/push'
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {LINE_ACCESS_TOKEN}'
    }
    data = {
        'to': LINE_USER_ID,
        'messages': [{'type': 'text', 'text': message}]
    }

    try:
        response = requests.post(url, headers=headers, json=data, timeout=10)
        print(f"[LINE] Status: {response.status_code} | Body: {response.text}")
        return response.status_code == 200
    except Exception as e:
        print(f"[LINE ERROR] {e}")
        return False

def check_trade_signal(ticker):
    try:
        df = yf.download(ticker, period="1y", interval="1d", progress=False, auto_adjust=True)
        if df.empty or len(df) < 200:
            print(f"[SKIP] {ticker}: ข้อมูลไม่พอ ({len(df)} วัน)")
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # EMA
        df['EMA20'] = df['Close'].ewm(span=20, adjust=False).mean()
        df['EMA200'] = df['Close'].ewm(span=200, adjust=False).mean()

        # RSI
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))

        # ATR
        high_low = df['High'] - df['Low']
        high_close = abs(df['High'] - df['Close'].shift())
        low_close = abs(df['Low'] - df['Close'].shift())
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df['ATR'] = true_range.rolling(14).mean()

        last = df.iloc[-1]
        prev = df.iloc[-2]
        curr_price = float(last['Close'])
        atr = float(last['ATR']) if not pd.isna(last['ATR']) else 0
        rsi = float(last['RSI']) if not pd.isna(last['RSI']) else 0

        ema_cross_up = (float(prev['EMA20']) < float(prev['EMA200'])) and (float(last['EMA20']) > float(last['EMA200']))
        ema_cross_dn = (float(prev['EMA20']) > float(prev['EMA200'])) and (float(last['EMA20']) < float(last['EMA200']))

        if ema_cross_up and (45 < rsi < 75):
            sl = curr_price - (1.5 * atr)
            tp = curr_price + (3 * atr)
            return (
                f"🔵 [BUY] {ticker}\n"
                f"ราคา: {curr_price:.2f}\n"
                f"RSI: {rsi:.1f}\n"
                f"TP: {tp:.2f} | SL: {sl:.2f}"
            )

        elif ema_cross_dn:
            return (
                f"🔴 [SELL] {ticker}\n"
                f"ราคา: {curr_price:.2f}\n"
                f"RSI: {rsi:.1f}\n"
                f"สถานะ: EMA20 ตัดลงต่ำกว่า EMA200"
            )

        return None

    except Exception as e:
        print(f"[ERROR] {ticker}: {e}")
        return None

# --- รายชื่อหุ้น ---
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

# --- Main ---
print(f"[START] บอทเริ่มทำงาน {datetime.now(TZ_THAI).strftime('%Y-%m-%d %H:%M:%S')}")
print(f"[INFO] สแกนหุ้นทั้งหมด {len(stocks)} ตัว")

found_signals = []
for s in stocks:
    signal = check_trade_signal(s)
    if signal:
        print(f"[SIGNAL] {signal[:50]}...")
        found_signals.append(signal)

print(f"[DONE] พบสัญญาณ {len(found_signals)} ตัว")

if found_signals:
    for msg in found_signals:
        send_to_line(msg)
else:
    now_str = datetime.now(TZ_THAI).strftime('%d/%m/%Y %H:%M')
    send_to_line(
        f"✅ สแกนหุ้น {len(stocks)} ตัวเสร็จสิ้น\n"
        f"🕐 {now_str}\n"
        f"😴 ยังไม่มีสัญญาณใหม่"
    )
