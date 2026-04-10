import yfinance as yf
import pandas as pd
import requests
import anthropic
import os
from datetime import datetime, timezone, timedelta

TZ_THAI = timezone(timedelta(hours=7))

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

def analyze_with_claude(ticker, signal_type, price, rsi, atr, tp=None, sl=None):
    try:
        client = anthropic.Anthropic()
        tp_sl_text = f"TP: {tp:.2f} | SL: {sl:.2f}" if tp and sl else ""
        prompt = f"""คุณเป็นนักวิเคราะห์หุ้นสำหรับนักลงทุนระยะกลาง-ยาว

หุ้น {ticker} เกิดสัญญาณ {signal_type}
ราคาปัจจุบัน: {price:.2f}
RSI: {rsi:.1f}
ATR: {atr:.2f}
{tp_sl_text}

วิเคราะห์สั้นๆ ภาษาไทย ไม่เกิน 4 บรรทัด:
1. ทำไม setup นี้น่าสนใจหรือน่ากังวล
2. ความเสี่ยงหลักที่ควรระวัง
3. เหมาะกับระยะเวลาถือครองแค่ไหน

สุดท้ายให้คะแนน Conviction: X/5 เท่านั้น ไม่ต้องอธิบายเพิ่ม"""

        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}]
        )
        return message.content[0].text
    except Exception as e:
        print(f"[CLAUDE ERROR] {ticker}: {e}")
        return None

def get_conviction_score(ai_text):
    try:
        import re
        match = re.search(r'Conviction:\s*(\d)', ai_text)
        if match:
            return int(match.group(1))
    except:
        pass
    return 3

def check_trade_signal(ticker):
    try:
        df = yf.download(ticker, period="1y", interval="1d", progress=False, auto_adjust=True)
        if df.empty or len(df) < 200:
            print(f"[SKIP] {ticker}: ข้อมูลไม่พอ ({len(df)} วัน)")
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df['EMA20'] = df['Close'].ewm(span=20, adjust=False).mean()
        df['EMA50'] = df['Close'].ewm(span=50, adjust=False).mean()
        df['EMA200'] = df['Close'].ewm(span=200, adjust=False).mean()

        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))

        high_low = df['High'] - df['Low']
        high_close = abs(df['High'] - df['Close'].shift())
        low_close = abs(df['Low'] - df['Close'].shift())
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df['ATR'] = true_range.rolling(14).mean()

        avg_vol = df['Volume'].rolling(20).mean()
        df['VOL_SURGE'] = df['Volume'] > (avg_vol * 1.3)

        last = df.iloc[-1]
        prev = df.iloc[-2]
        curr_price = float(last['Close'])
        atr = float(last['ATR']) if not pd.isna(last['ATR']) else 0
        rsi = float(last['RSI']) if not pd.isna(last['RSI']) else 0
        vol_surge = bool(last['VOL_SURGE'])

        ema_cross_up = (float(prev['EMA20']) < float(prev['EMA200'])) and (float(last['EMA20']) > float(last['EMA200']))
        ema_cross_dn = (float(prev['EMA20']) > float(prev['EMA200'])) and (float(last['EMA20']) < float(last['EMA200']))
        ema_aligned = float(last['EMA20']) > float(last['EMA50']) > float(last['EMA200'])

        if ema_cross_up and (45 < rsi < 75) and ema_aligned:
            sl = curr_price - (2.0 * atr)
            tp = curr_price + (4 * atr)
            vol_text = "📊 Volume surge ยืนยัน" if vol_surge else "⚠️ Volume ปกติ"
            signal_text = (
                f"🔵 [BUY] {ticker}\n"
                f"ราคา: {curr_price:.2f}\n"
                f"RSI: {rsi:.1f} | {vol_text}\n"
                f"EMA: 20>50>200 ✅\n"
                f"TP: {tp:.2f} | SL: {sl:.2f}"
            )
            return ("BUY", signal_text, curr_price, rsi, atr, tp, sl)

        elif ema_cross_dn:
            signal_text = (
                f"🔴 [SELL] {ticker}\n"
                f"ราคา: {curr_price:.2f}\n"
                f"RSI: {rsi:.1f}\n"
                f"สถานะ: EMA20 ตัดลงต่ำกว่า EMA200"
            )
            return ("SELL", signal_text, curr_price, rsi, atr, None, None)

        return None

    except Exception as e:
        print(f"[ERROR] {ticker}: {e}")
        return None

# --- รายชื่อหุ้น 250+ ตัว ---
stocks = [
    # US Mega Cap
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'TSLA', 'NVDA', 'AVGO', 'ORCL', 'ADBE',
    'NFLX', 'AMD', 'CRM', 'INTC', 'QCOM', 'TXN', 'AMAT', 'MU', 'LRCX', 'PANW',

    # US Finance
    'V', 'MA', 'JPM', 'BAC', 'WFC', 'GS', 'MS', 'BLK', 'AXP', 'PYPL',
    'SCHW', 'C', 'USB', 'PNC', 'TFC', 'COF', 'SQ', 'HOOD',

    # US Consumer
    'WMT', 'COST', 'TGT', 'HD', 'LOW', 'NKE', 'SBUX', 'MCD', 'KO', 'PEP',
    'AMZN', 'BABA', 'JD', 'PDD', 'MELI', 'SE',

    # US Healthcare
    'PFE', 'JNJ', 'UNH', 'ABBV', 'MRK', 'LLY', 'TMO', 'DHR', 'ISRG', 'AMGN',
    'GILD', 'REGN', 'VRTX', 'MRNA', 'BMY', 'CVS', 'CI',

    # US Energy & Industrial
    'XOM', 'CVX', 'COP', 'SLB', 'EOG', 'BA', 'CAT', 'DE', 'GE', 'MMM',
    'HON', 'RTX', 'LMT', 'NOC', 'UPS', 'FDX',

    # US Growth & Tech
    'PLTR', 'ARM', 'SMCI', 'CRWD', 'SNOW', 'DDOG', 'NET', 'COIN',
    'UBER', 'LYFT', 'ABNB', 'DASH', 'RBLX', 'U', 'UNITY',
    'ZM', 'DOCU', 'TWLO', 'OKTA', 'MDB', 'ESTC',
    'SHOP', 'ETSY', 'PINS', 'SNAP', 'SPOT',
    'MSTR', 'RIOT', 'MARA', 'HUT',

    # US ETF
    'SPY', 'VOO', 'QQQ', 'DIA', 'VTI', 'SCHD', 'VIG', 'VYM',
    'XLK', 'XLF', 'XLE', 'XLV', 'XLI', 'XLY', 'XLP',
    'SOXX', 'ARKK', 'BOTZ', 'CIBR', 'ICLN', 'GDX', 'GDXJ',
    'TLT', 'GLD', 'SLV', 'USO',

    # Thai SET50 & Large Cap
    'PTT.BK', 'PTTEP.BK', 'TOP.BK', 'OR.BK', 'BCP.BK', 'IRPC.BK', 'PTTGC.BK', 'IVL.BK',
    'CPALL.BK', 'CPAXT.BK', 'BJC.BK', 'HMPRO.BK', 'GLOBAL.BK', 'CRC.BK', 'CPN.BK',
    'AOT.BK', 'BA.BK', 'BEM.BK', 'BTS.BK', 'WHA.BK', 'AMATA.BK',
    'ADVANC.BK', 'TRUE.BK', 'INTUCH.BK', 'DELTA.BK', 'HANA.BK', 'KCE.BK',
    'KBANK.BK', 'SCB.BK', 'BBL.BK', 'KTB.BK', 'TTB.BK', 'TISCO.BK', 'KKP.BK',
    'BDMS.BK', 'BH.BK', 'BCH.BK', 'CHG.BK', 'GULF.BK', 'GPSC.BK', 'BGRIM.BK',
    'EA.BK', 'EGCO.BK', 'RATCH.BK', 'BANPU.BK', 'SCC.BK', 'SCGP.BK', 'CBG.BK',
    'OSP.BK', 'TU.BK', 'MINT.BK', 'LH.BK', 'AP.BK', 'SIRI.BK',

    # Thai Mid Cap
    'AWC.BK', 'CENTEL.BK', 'ERW.BK', 'DUSIT.BK',
    'MTC.BK', 'TIDLOR.BK', 'SAWAD.BK', 'AEONTS.BK',
    'ORI.BK', 'SPALI.BK', 'LPN.BK', 'SC.BK', 'NOBLE.BK',
    'STEC.BK', 'CK.BK', 'ITD.BK', 'SEAFCO.BK',
    'MAKRO.BK', 'ROBINS.BK', 'COM7.BK', 'SYNEX.BK',
    'TKN.BK', 'COCOCO.BK', 'ICHI.BK', 'EVER.BK',
    'BEAUTY.BK', 'GFPT.BK', 'NRF.BK', 'TFG.BK',
    'IRPC.BK', 'TPIPP.BK', 'SUPER.BK', 'SPCG.BK',
]

stocks = list(dict.fromkeys(stocks))

# --- Main ---
print(f"[START] บอทเริ่มทำงาน {datetime.now(TZ_THAI).strftime('%Y-%m-%d %H:%M:%S')}")
print(f"[INFO] สแกนหุ้นทั้งหมด {len(stocks)} ตัว")

found_signals = []
for s in stocks:
    result = check_trade_signal(s)
    if result:
        signal_type, signal_text, price, rsi, atr, tp, sl = result
        print(f"[SIGNAL] {s} — {signal_type}")

        ai_text = analyze_with_claude(s, signal_type, price, rsi, atr, tp, sl)

        if ai_text:
            conviction = get_conviction_score(ai_text)
            print(f"[CONVICTION] {s}: {conviction}/5")

            if conviction >= 3:
                full_message = signal_text + "\n\n🤖 AI วิเคราะห์:\n" + ai_text
                found_signals.append(full_message)
            else:
                print(f"[FILTERED] {s} conviction ต่ำเกินไป ({conviction}/5) ไม่ส่ง LINE")
        else:
            found_signals.append(signal_text)

print(f"[DONE] พบสัญญาณ {len(found_signals)} ตัว (ผ่าน AI filter)")

if found_signals:
    for msg in found_signals:
        send_to_line(msg)
else:
    now_str = datetime.now(TZ_THAI).strftime('%d/%m/%Y %H:%M')
    send_to_line(
        f"✅ สแกนหุ้น {len(stocks)} ตัวเสร็จสิ้น\n"
        f"🕐 {now_str}\n"
        f"😴 ยังไม่มีสัญญาณที่ผ่าน AI filter"
    )
