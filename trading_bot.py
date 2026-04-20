import yfinance as yf
import pandas as pd
import requests
import anthropic
import os
import re
import time
from datetime import datetime, timezone, timedelta

TZ_THAI = timezone(timedelta(hours=7))

LINE_ACCESS_TOKEN = os.getenv('CHANNEL_ACCESS_TOKEN')
LINE_USER_ID      = os.getenv('USER_ID')

# ─────────────────────────────────────────────────────────────────
#  LINE  (uses push API with user ID)
# ─────────────────────────────────────────────────────────────────

def send_to_line(message: str) -> bool:
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
        print(f"[LINE] Status: {response.status_code} | Body: {response.text[:200]}")
        return response.status_code == 200
    except Exception as e:
        print(f"[LINE ERROR] {e}")
        return False

def send_to_line_chunks(message: str):
    """Split long messages into ≤1000-char chunks at newline boundaries."""
    if len(message) <= 1000:
        send_to_line(message)
        return
    chunks, current = [], ""
    for line in message.split("\n"):
        if len(current) + len(line) + 1 > 1000:
            if current:
                send_to_line(current)
                time.sleep(0.4)
            current = line
        else:
            current = current + "\n" + line if current else line
    if current:
        send_to_line(current)

# ─────────────────────────────────────────────────────────────────
#  BEAUTIFUL FORMATTER  (matches your screenshot style)
# ─────────────────────────────────────────────────────────────────

def format_header(market_label: str, flag: str, index_name: str,
                  index_price: float, index_chg: float,
                  scan_count: int, scan_secs: float,
                  buy_n: int, watch_n: int, exit_n: int,
                  ai_filtered: int, summary: str) -> str:
    now = datetime.now(TZ_THAI).strftime("%d %b %Y  %H:%M")
    arrow = "↑" if index_chg >= 0 else "↓"
    sign  = "+" if index_chg >= 0 else ""
    chg   = f"{arrow}{sign}{index_chg:.2f}%"
    lines = [
        "",
        f"{flag} {market_label} Alert — Market Close 📊",
        "━" * 30,
        f"📅 {now}",
        "",
        f"{index_name}    {index_price:,.2f}  {chg}",
        "",
        f"สแกน {scan_count} หุ้น  •  {scan_secs:.1f}s",
        f"🟢 BUY {buy_n}   🟡 WATCH {watch_n}   🔴 EXIT {exit_n}",
        f"🤖 AI กรองออก {ai_filtered} สัญญาณ",
    ]
    if summary:
        lines += ["", summary]
    return "\n".join(lines)


def format_stock_card(ticker: str, signal_type: str, price: float,
                      rsi: float, atr: float, macd_hist: float,
                      ema_cross: str, bb_pos: str,
                      reasons: list, ai_text: str,
                      conviction: int, tp=None, sl=None,
                      currency: str = "$") -> str:
    # Badge
    if signal_type == "BUY":
        badge = "🟢 BUY / ซื้อ"
    elif conviction >= 4:
        badge = "🔴 EXIT / ขาย"
    else:
        badge = "🟡 WATCH / เฝ้าดู"

    # MA arrow
    ma_arrow = "↑" if ema_cross == "golden" else ("↓" if ema_cross == "death" else "→")

    # BB label
    bb_lbl = {"above": "Breakout↑", "below": "Squeeze↓", "inside": "Normal"}.get(bb_pos, "")

    # AI score
    if conviction >= 4:
        ai_score = f"{conviction}/5 STR 🔥"
    elif conviction == 3:
        ai_score = f"{conviction}/5 MOD 💡"
    else:
        ai_score = f"{conviction}/5 WEK"

    # TP/SL line
    tp_sl = f"TP: {tp:.2f}  SL: {sl:.2f}" if tp and sl else ""

    card = [
        "─" * 26,
        badge,
        f"{ticker:<16}{currency}{price:,.2f}",
        _clean_reason(reasons[0]) if reasons else "",
        f"RSI {rsi:.1f}   ATR {atr:.2f}",
        f"MA {ma_arrow}   BB {bb_lbl}",
    ]
    if tp_sl:
        card.append(tp_sl)
    card.append(f"🤖 AI {ai_score}")

    if ai_text:
        # Trim to 3 lines max so card stays compact
        ai_lines = [l.strip() for l in ai_text.strip().split("\n") if l.strip()][:4]
        card += ["", "📝 AI วิเคราะห์:"] + ai_lines

    return "\n".join(card)


def _clean_reason(r: str) -> str:
    rl = r.lower()
    if "buy" in rl and "ema" in rl:   return "Golden Cross EMA ✨"
    if "sell" in rl and "ema" in rl:  return "Death Cross EMA ☠️"
    if "rsi" in rl and "45" in rl:    return "RSI Bullish Zone 📈"
    if "rsi" in rl:                    return "RSI Signal 📊"
    return r


def market_summary(index_chg: float, market: str) -> str:
    if abs(index_chg) < 0.1:
        mood = "ทรงตัว ไม่มีทิศทางชัดเจน"
    elif index_chg > 1.0:
        mood = "ปรับขึ้นแรง มีแรงซื้อเข้ามาหนุน"
    elif index_chg > 0:
        mood = "ปรับขึ้นเล็กน้อย แนวโน้มเป็นบวก"
    elif index_chg < -1.0:
        mood = "ปรับลงแรง แรงขายครอบงำตลาด"
    else:
        mood = "ปรับลงเล็กน้อย ควรระวังความเสี่ยง"
    return (
        f"ดัชนี {market} วันนี้{mood} ({index_chg:+.2f}%)\n"
        f"ภาพรวมตลาดยังควรติดตามปัจจัยข่าวและสัญญาณเทคนิค"
    )

# ─────────────────────────────────────────────────────────────────
#  FETCH INDEX PRICE
# ─────────────────────────────────────────────────────────────────

def get_index(ticker: str):
    try:
        df = yf.download(ticker, period="5d", interval="1d",
                         auto_adjust=True, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if len(df) >= 2:
            prev  = float(df['Close'].iloc[-2])
            close = float(df['Close'].iloc[-1])
            pct   = round((close - prev) / prev * 100, 2)
            return round(close, 2), pct
    except Exception as e:
        print(f"[INDEX ERROR] {ticker}: {e}")
    return 0.0, 0.0

# ─────────────────────────────────────────────────────────────────
#  CLAUDE AI ANALYSIS
# ─────────────────────────────────────────────────────────────────

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


def get_conviction_score(ai_text: str) -> int:
    try:
        match = re.search(r'Conviction:\s*(\d)', ai_text)
        if match:
            return int(match.group(1))
    except:
        pass
    return 3

# ─────────────────────────────────────────────────────────────────
#  TECHNICAL SIGNAL DETECTION  (your original logic, unchanged)
# ─────────────────────────────────────────────────────────────────

def check_trade_signal(ticker):
    try:
        df = yf.download(ticker, period="1y", interval="1d", progress=False, auto_adjust=True)
        if df.empty or len(df) < 200:
            print(f"[SKIP] {ticker}: ข้อมูลไม่พอ ({len(df)} วัน)")
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df['EMA20']  = df['Close'].ewm(span=20,  adjust=False).mean()
        df['EMA50']  = df['Close'].ewm(span=50,  adjust=False).mean()
        df['EMA200'] = df['Close'].ewm(span=200, adjust=False).mean()

        delta = df['Close'].diff()
        gain  = delta.where(delta > 0, 0).rolling(14).mean()
        loss  = (-delta.where(delta < 0, 0)).rolling(14).mean()
        df['RSI'] = 100 - (100 / (1 + gain / loss))

        hl   = df['High'] - df['Low']
        hc   = abs(df['High'] - df['Close'].shift())
        lc   = abs(df['Low']  - df['Close'].shift())
        df['ATR'] = pd.concat([hl, hc, lc], axis=1).max(axis=1).rolling(14).mean()

        avg_vol = df['Volume'].rolling(20).mean()
        df['VOL_SURGE'] = df['Volume'] > (avg_vol * 1.3)

        last = df.iloc[-1]
        prev = df.iloc[-2]
        price     = float(last['Close'])
        atr       = float(last['ATR'])   if not pd.isna(last['ATR'])  else 0
        rsi       = float(last['RSI'])   if not pd.isna(last['RSI'])  else 0
        vol_surge = bool(last['VOL_SURGE'])

        ema_cross_up = float(prev['EMA20']) < float(prev['EMA200']) and float(last['EMA20']) > float(last['EMA200'])
        ema_cross_dn = float(prev['EMA20']) > float(prev['EMA200']) and float(last['EMA20']) < float(last['EMA200'])
        ema_aligned  = float(last['EMA20']) > float(last['EMA50']) > float(last['EMA200'])

        # Determine EMA / BB metadata for card
        ema_cross = "golden" if float(last['EMA20']) > float(last['EMA200']) else "death"

        # Simple Bollinger for card display
        bb_mid   = df['Close'].rolling(20).mean().iloc[-1]
        bb_std   = df['Close'].rolling(20).std().iloc[-1]
        bb_upper = bb_mid + 2 * bb_std
        bb_lower = bb_mid - 2 * bb_std
        bb_pos   = "above" if price > bb_upper else ("below" if price < bb_lower else "inside")

        if ema_cross_up and (45 < rsi < 75) and ema_aligned:
            sl = price - (2.0 * atr)
            tp = price + (4.0 * atr)
            vol_txt = "Volume surge ยืนยัน" if vol_surge else "Volume ปกติ"
            reasons = [f"EMA20 cross above EMA200 ({vol_txt})", f"RSI {rsi:.1f} bullish zone"]
            return ("BUY", price, rsi, atr, ema_cross, bb_pos, reasons, tp, sl)

        elif ema_cross_dn:
            reasons = ["EMA20 ตัดลงต่ำกว่า EMA200"]
            return ("SELL", price, rsi, atr, ema_cross, bb_pos, reasons, None, None)

        return None

    except Exception as e:
        print(f"[ERROR] {ticker}: {e}")
        return None

# ─────────────────────────────────────────────────────────────────
#  WATCHLIST  (your original 250+ stocks)
# ─────────────────────────────────────────────────────────────────

stocks = [
    # US Mega Cap
    'AAPL','MSFT','GOOGL','AMZN','META','TSLA','NVDA','AVGO','ORCL','ADBE',
    'NFLX','AMD','CRM','INTC','QCOM','TXN','AMAT','MU','LRCX','PANW',
    # US Finance
    'V','MA','JPM','BAC','WFC','GS','MS','BLK','AXP','PYPL',
    'SCHW','C','USB','PNC','TFC','COF','SQ','HOOD',
    # US Consumer
    'WMT','COST','TGT','HD','LOW','NKE','SBUX','MCD','KO','PEP',
    'BABA','JD','PDD','MELI','SE',
    # US Healthcare
    'PFE','JNJ','UNH','ABBV','MRK','LLY','TMO','DHR','ISRG','AMGN',
    'GILD','REGN','VRTX','MRNA','BMY','CVS','CI',
    # US Energy & Industrial
    'XOM','CVX','COP','SLB','EOG','BA','CAT','DE','GE','MMM',
    'HON','RTX','LMT','NOC','UPS','FDX',
    # US Growth & Tech
    'PLTR','ARM','SMCI','CRWD','SNOW','DDOG','NET','COIN',
    'UBER','LYFT','ABNB','DASH','RBLX','ZM','DOCU','TWLO','OKTA',
    'MDB','ESTC','SHOP','ETSY','PINS','SNAP','SPOT',
    'MSTR','RIOT','MARA','HUT',
    # US ETF
    'SPY','VOO','QQQ','DIA','VTI','SCHD','VIG','VYM',
    'XLK','XLF','XLE','XLV','XLI','XLY','XLP',
    'SOXX','ARKK','BOTZ','CIBR','ICLN','GDX','GDXJ',
    'TLT','GLD','SLV','USO',
    # Thai SET50 & Large Cap
    'PTT.BK','PTTEP.BK','TOP.BK','OR.BK','BCP.BK','IRPC.BK','PTTGC.BK','IVL.BK',
    'CPALL.BK','CPAXT.BK','BJC.BK','HMPRO.BK','GLOBAL.BK','CRC.BK','CPN.BK',
    'AOT.BK','BA.BK','BEM.BK','BTS.BK','WHA.BK','AMATA.BK',
    'ADVANC.BK','TRUE.BK','INTUCH.BK','DELTA.BK','HANA.BK','KCE.BK',
    'KBANK.BK','SCB.BK','BBL.BK','KTB.BK','TTB.BK','TISCO.BK','KKP.BK',
    'BDMS.BK','BH.BK','BCH.BK','CHG.BK','GULF.BK','GPSC.BK','BGRIM.BK',
    'EA.BK','EGCO.BK','RATCH.BK','BANPU.BK','SCC.BK','SCGP.BK','CBG.BK',
    'OSP.BK','TU.BK','MINT.BK','LH.BK','AP.BK','SIRI.BK',
    # Thai Mid Cap
    'AWC.BK','CENTEL.BK','ERW.BK','DUSIT.BK',
    'MTC.BK','TIDLOR.BK','SAWAD.BK','AEONTS.BK',
    'ORI.BK','SPALI.BK','LPN.BK','SC.BK','NOBLE.BK',
    'STEC.BK','CK.BK','ITD.BK','SEAFCO.BK',
    'MAKRO.BK','ROBINS.BK','COM7.BK','SYNEX.BK',
    'TKN.BK','ICHI.BK','EVER.BK','BEAUTY.BK',
    'GFPT.BK','NRF.BK','TFG.BK','TPIPP.BK','SUPER.BK','SPCG.BK',
]
stocks = list(dict.fromkeys(stocks))  # deduplicate

# ─────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────

def main():
    start_time = time.time()
    now_str = datetime.now(TZ_THAI).strftime('%Y-%m-%d %H:%M:%S')
    print(f"[START] บอทเริ่มทำงาน {now_str}")
    print(f"[INFO] สแกนหุ้นทั้งหมด {len(stocks)} ตัว")

    # ── Fetch indices ─────────────────────────────────────────────
    set_price,  set_chg  = get_index("^SET.BK")
    sp500_price, sp500_chg = get_index("^GSPC")

    # ── Scan all stocks ───────────────────────────────────────────
    thai_signals, us_signals = [], []
    total_filtered = 0

    for ticker in stocks:
        result = check_trade_signal(ticker)
        if not result:
            continue

        signal_type, price, rsi, atr, ema_cross, bb_pos, reasons, tp, sl = result
        print(f"[SIGNAL] {ticker} — {signal_type}")

        ai_text    = analyze_with_claude(ticker, signal_type, price, rsi, atr, tp, sl)
        conviction = get_conviction_score(ai_text) if ai_text else 3

        print(f"[CONVICTION] {ticker}: {conviction}/5")

        if conviction < 3:
            total_filtered += 1
            print(f"[FILTERED] {ticker} conviction ต่ำ ({conviction}/5)")
            continue

        is_thai = ticker.endswith(".BK")
        currency = "฿" if is_thai else "$"

        card = format_stock_card(
            ticker=ticker.replace(".BK", "") if is_thai else ticker,
            signal_type=signal_type,
            price=price,
            rsi=rsi,
            atr=atr,
            macd_hist=0.0,   # not used in original detection
            ema_cross=ema_cross,
            bb_pos=bb_pos,
            reasons=reasons,
            ai_text=ai_text,
            conviction=conviction,
            tp=tp,
            sl=sl,
            currency=currency,
        )

        if is_thai:
            thai_signals.append((signal_type, conviction, card))
        else:
            us_signals.append((signal_type, conviction, card))

    scan_secs = round(time.time() - start_time, 1)
    print(f"[DONE] พบสัญญาณ {len(thai_signals)+len(us_signals)} ตัว | กรองออก {total_filtered} | เวลา {scan_secs}s")

    # ── Build & send Thai message ─────────────────────────────────
    _send_market_message(
        signals=thai_signals,
        market_label="SET",
        flag="🏦",
        index_name="SET Index",
        index_price=set_price,
        index_chg=set_chg,
        scan_count=sum(1 for s in stocks if s.endswith(".BK")),
        scan_secs=scan_secs,
        ai_filtered=total_filtered,
    )

    # ── Build & send US message ───────────────────────────────────
    _send_market_message(
        signals=us_signals,
        market_label="US",
        flag="🗽",
        index_name="S&P 500",
        index_price=sp500_price,
        index_chg=sp500_chg,
        scan_count=sum(1 for s in stocks if not s.endswith(".BK")),
        scan_secs=scan_secs,
        ai_filtered=total_filtered,
    )


def _send_market_message(signals, market_label, flag, index_name,
                         index_price, index_chg, scan_count, scan_secs, ai_filtered):
    buy_n   = sum(1 for sig, _, _ in signals if sig == "BUY")
    watch_n = sum(1 for sig, conv, _ in signals if sig == "SELL" and conv < 4)
    exit_n  = sum(1 for sig, conv, _ in signals if sig == "SELL" and conv >= 4)

    header = format_header(
        market_label=market_label,
        flag=flag,
        index_name=index_name,
        index_price=index_price,
        index_chg=index_chg,
        scan_count=scan_count,
        scan_secs=scan_secs,
        buy_n=buy_n,
        watch_n=watch_n,
        exit_n=exit_n,
        ai_filtered=ai_filtered,
        summary=market_summary(index_chg, market_label),
    )

    if signals:
        cards_block = "\n━" * 30 + "\n📋 สัญญาณที่น่าสนใจ\n"
        cards_block += "\n\n".join(card for _, _, card in signals)
        footer = "\n\n━" * 30 + "\n⚠️  ไม่ใช่คำแนะนำการลงทุน  |  Not financial advice"
        full_msg = header + cards_block + footer
    else:
        full_msg = (
            header
            + "\n\n😴 ไม่พบสัญญาณที่ผ่าน AI filter"
            + "\n\n━" * 30
            + "\n⚠️  ไม่ใช่คำแนะนำการลงทุน"
        )

    send_to_line_chunks(full_msg)


if __name__ == "__main__":
    main()
