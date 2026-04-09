import yfinance as yf
import pandas as pd
import pandas_ta as ta
import requests
import os

# --- 1. ตั้งค่าการเชื่อมต่อ (ดึงจาก GitHub Secrets ของคุณ Apisorn) ---
LINE_ACCESS_TOKEN = os.getenv('CHANNEL_ACCESS_TOKEN')
LINE_USER_ID = os.getenv('USER_ID')

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
    try:
        response = requests.post(url, headers=headers, json=data)
        return response.status_code
    except Exception as e:
        print(f"ส่ง LINE ไม่สำเร็จ: {e}")
        return None

# --- 2. ฟังก์ชันแสกนหาจุดตัด EMA 20/200 ---
def check_trade_signal(ticker):
    try:
        # ดึงข้อมูลย้อนหลัง 1 ปี (เพื่อให้เส้น 200 นิ่ง)
        df = yf.download(ticker, period="1y", interval="1d", progress=False)
        if df.empty or len(df) < 200:
            return None

        # ปรับ Format ข้อมูล (แก้ปัญหา Multi-index ของ yfinance รุ่นใหม่)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # คำนวณ Technical Indicators
        df['EMA20'] = ta.ema(df['Close'], length=20)
        df['EMA200'] = ta.ema(df['Close'], length=200)
        df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)

        # ข้อมูลวันนี้และเมื่อวาน
        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        curr_price = float(last['Close'])
        atr = float(last['ATR']) if not pd.isna(last['ATR']) else 0

        # --- กรณี Golden Cross (ตัดขึ้น) ---
        if (prev['EMA20'] < prev['EMA200']) and (last['EMA20'] > last['EMA200']):
            sl = curr_price - (2 * atr)
            tp = curr_price + (4 * atr)
            return f"🚀 [GOLDEN CROSS] {ticker}\nราคา: {curr_price:.2f}\nเป้ากำไร: {tp:.2f}\nตัดขาดทุน: {sl:.2f}"

        # --- กรณี Death Cross (ตัดลง) ---
        elif (prev['EMA20'] > prev['EMA200']) and (last['EMA20'] < last['EMA200']):
            return f"💀 [DEATH CROSS] {ticker}\nราคา: {curr_price:.2f}\nสถานะ: เพิ่งตัดลงเป็นขาลง (พิจารณาขาย)"

        return None
    except Exception as e:
        print(f"Error {ticker}: {e}")
        return None

# --- 3. รายชื่อหุ้นชุดใหญ่ (100+ ตัว) ---
stocks = [
    # US Tech & AI
    'AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA', 'META', 'AMZN', 'NFLX', 'AMD', 'AVGO', 
    'SMCI', 'PLTR', 'ARM', 'ORCL', 'ADBE', 'PYPL', 'INTC', 'QCOM', 'MU', 'PANW', 'ASML',
    # US Financial & Blue Chip
    'V', 'MA', 'JPM', 'BAC', 'GS', 'WMT', 'COST', 'DIS', 'NKE', 'SBUX', 'KO', 'PEP', 
    'PFE', 'JNJ', 'UNH', 'XOM', 'CVX', 'BA', 'CAT', 'GE', 'ABNB', 'UBER',
    # Thai Energy & Utility
    'PTT.BK', 'PTTEP.BK', 'TOP.BK', 'GULF.BK', 'GPSC.BK', 'BGRIM.BK', 'EA.BK', 'BCP.BK', 
    'IRPC.BK', 'SPRC.BK', 'OR.BK', 'EGCO.BK', 'RATCH.BK', 'BANPU.BK', 'IVL.BK', 'PTTGC.BK',
    # Thai Banking & Finance
    'KBANK.BK', 'SCB.BK', 'BBL.BK', 'KTB.BK', 'TISCO.BK', 'TTB.BK', 'KKP.BK', 'SAWAD.BK', 'MTC.BK', 'TIDLOR.BK',
    # Thai Blue Chip & Retail
    'CPALL.BK', 'AOT.BK', 'ADVANC.BK', 'DELTA.BK', 'SCC.BK', 'BDMS.BK', 'BH.BK', 'CPN.BK', 
    'HMPRO.BK', 'GLOBAL.BK', 'CBG.BK', 'OSP.BK', 'MINT.BK', 'CRC.BK', 'TU.BK',
    # Thai Tech & Logis
    'TRUE.BK', 'HANA.BK', 'KCE.BK', 'JMT.BK', 'BTS.BK', 'BEM.BK', 'WHA.BK', 'AMATA.BK', 
    'CENTEL.BK', 'COM7.BK', 'SCGP.BK', 'LH.BK', 'AP.BK', 'SIRI.BK'
]

# --- 4. รันระบบแสกน ---
found_signals = []
print(f"กำลังเริ่มแสกนหุ้นทั้งหมด {len(stocks)} ตัว...")

for s in stocks:
    signal = check_trade_signal(s)
    if signal:
        found_signals.append(signal)

# --- 5. ส่งสรุปผลเข้า LINE ---
if found_signals:
    for msg in found_signals:
        send_to_line(msg)
else:
    summary_text = (f"✅ บอทแสกนหุ้น {len(stocks)} ตัวเสร็จสิ้น\n"
                    f"สถานะ: 😴 ไม่พบสัญญาณตัดกัน (Crossover) ของวันนี้ครับ")
    send_to_line(summary_text)

print("รันเสร็จเรียบร้อย!")
